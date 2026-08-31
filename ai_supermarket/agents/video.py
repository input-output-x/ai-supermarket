"""ai-video：视频/剪辑 Agent（必备，流量引擎第 3 环）—— 接真实 TTS + ffmpeg 出成片。

职责：根据口播稿生成抖音竖版成片（背景 + 中文字幕 + 中文配音），并产出封面图。

真实能力接入点（已全部落地，带优雅降级）：
  - TTS：edge-tts（微软免费中文语音，venv 已装）。无网络/不可用时降级为静音视频。
  - 字幕：PIL 渲染中文字幕 PNG -> ffmpeg overlay 逐段叠加（不依赖 libass，跨平台通用）。
  - 剪辑：ffmpeg 合成 1080x1920（9:16 抖音标准），libx264 + aac。

输入：voiceover / shots / captionTiming
输出：videoPath / cover / duration / hasAudio
"""
import os
import re
import time
import asyncio
import subprocess

from ..core.agent import AbstractAgent
from ..core.context import AgentContext


def _project_root() -> str:
    # ai_supermarket/agents/video.py -> ai_supermarket_python
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _candidate_fonts() -> list[str]:
    return [
        "/System/Library/Fonts/Songti.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/STHeiti Regular.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]


def _find_cjk_font() -> str | None:
    for p in _candidate_fonts():
        if os.path.exists(p):
            return p
    return None


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", "", text or "")
    parts = re.split(r"(?<=[。！？!?])", text)
    return [p for p in parts if p]


def _timeline(sentences: list[str], total_dur: float) -> list[tuple[str, float]]:
    n = max(len(sentences), 1)
    weights = [max(len(s), 1) for s in sentences] or [1]
    total_w = sum(weights)
    out, t = [], 0.0
    for s, w in zip(sentences, weights):
        d = total_dur * (w / total_w)
        out.append((s, d))
        t += d
    return out


def _render_subtitle_png(text: str, path: str, font_path: str) -> bool:
    """把一句口播渲染成 1080x1920 透明 PNG（底部居中、带半透明底框）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        print(f"[video] PIL 不可用，跳过字幕：{e}")
        return False
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, 56)
    except Exception:
        font = ImageFont.load_default()
    # 自动换行（中文按字符宽度）
    max_w = int(W * 0.86)
    lines, cur = [], ""
    for ch in text:
        if ch in "。！？!?，,、":
            cur += ch
            continue
        test = cur + ch
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    lines = lines[-6:]  # 最多 6 行
    lh = 78
    box_h = lh * len(lines) + 40
    box_y = H - 260 - box_h
    box = (int(W * 0.05), box_y, int(W * 0.95), box_y + box_h)
    draw.rounded_rectangle(box, radius=24, fill=(10, 10, 30, 165))
    y = box_y + 20
    for ln in lines:
        tw = draw.textlength(ln, font=font)
        draw.text(((W - tw) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += lh
    img.save(path)
    return True


def _run(cmd: list[str]) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if r.returncode != 0:
            print(f"[ffmpeg][FAIL] {' '.join(cmd[:6])}...\n{r.stderr[-800:]}")
            return False
        return True
    except Exception as e:
        print(f"[ffmpeg][EXC] {e}")
        return False


def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=20)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


class TTSEngine:
    def synth(self, text: str, out_path: str) -> bool:
        raise NotImplementedError


class EdgeTTSEngine(TTSEngine):
    """微软 edge-tts 免费中文语音（需 venv 安装 edge-tts 且有网络）。"""

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
        self.voice = voice

    def synth(self, text: str, out_path: str) -> bool:
        try:
            import edge_tts
        except Exception as e:
            print(f"[tts] edge-tts 不可用：{e}")
            return False

        async def _go() -> None:
            comm = edge_tts.Communicate(text, self.voice)
            await comm.save(out_path)

        try:
            asyncio.run(_go())
            return os.path.exists(out_path) and os.path.getsize(out_path) > 0
        except Exception as e:
            print(f"[tts] edge-tts 合成失败（可能无网络）：{e}")
            return False


class VideoAgent(AbstractAgent):
    name = "video"

    def _run(self, ctx: AgentContext) -> AgentContext:
        voiceover = ctx.get("voiceover", "")
        if not voiceover:
            voiceover = "（空口播稿，已用占位文案演示成片流程）"

        out_dir = os.path.join(_project_root(), "output")
        os.makedirs(out_dir, exist_ok=True)
        base = str(int(time.time() * 1000))
        audio_path = os.path.join(out_dir, base + ".mp3")
        video_path = os.path.join(out_dir, base + ".mp4")
        cover_path = os.path.join(out_dir, base + ".jpg")
        silent_path = os.path.join(out_dir, base + "_silent.mp4")

        # 1) TTS 配音
        has_audio = EdgeTTSEngine().synth(voiceover, audio_path)
        duration = _probe_duration(audio_path) if has_audio else max(8.0, len(voiceover) / 6.0)
        if duration <= 0:
            duration = max(8.0, len(voiceover) / 6.0)

        # 2) 字幕 PNG（逐句）
        font = _find_cjk_font()
        sentences = _split_sentences(voiceover)
        tl = _timeline(sentences, duration)
        seg_paths = []
        use_sub = bool(font)
        if use_sub:
            for i, (s, d) in enumerate(tl):
                png = os.path.join(out_dir, f"{base}_sub{i}.png")
                if not _render_subtitle_png(s, png, font):
                    use_sub = False
                    break
                seg = os.path.join(out_dir, f"{base}_seg{i}.mp4")
                # 背景 + 该句字幕叠加，时长 d
                cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
                       f"color=c=0x12122b:s=1080x1920:d={d:.2f}",
                       "-loop", "1", "-i", png,
                       "-filter_complex", "[0][1]overlay=shortest=1",
                       "-c:v", "libx264", "-pix_fmt", "yuv420p", seg]
                if _run(cmd):
                    seg_paths.append(seg)
                else:
                    use_sub = False
                    break

        # 3) 合成静音成片（无字幕时退化为纯背景）
        if use_sub and seg_paths:
            concat = os.path.join(out_dir, base + "_concat.txt")
            with open(concat, "w", encoding="utf-8") as f:
                for s in seg_paths:
                    f.write(f"file '{os.path.abspath(s)}'\n")
            ok = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                       "-i", concat, "-c", "copy", silent_path])
        else:
            ok = _run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                       f"color=c=0x12122b:s=1080x1920:d={duration:.2f}",
                       "-c:v", "libx264", "-pix_fmt", "yuv420p", silent_path])

        # 4) 混音 -> 最终成片
        if ok and has_audio:
            ok = _run(["ffmpeg", "-y", "-i", silent_path, "-i", audio_path,
                       "-c:v", "copy", "-c:a", "aac", "-shortest", video_path])
        elif ok:
            ok = _run(["ffmpeg", "-y", "-i", silent_path, "-c", "copy", video_path])

        # 5) 封面
        if ok and _run(["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", cover_path]):
            pass
        else:
            _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1f1f3a:s=1080x1920",
                  "-frames:v", "1", cover_path])

        self.log.info("rendered -> %s (audio=%s, sub=%s, dur=%.1fs)",
                      video_path, has_audio, use_sub, duration)
        return (ctx.put("videoPath", video_path if ok else "")
                   .put("cover", cover_path if os.path.exists(cover_path) else "")
                   .put("duration", round(duration, 1))
                   .put("hasAudio", has_audio)
                   .put("hasSubtitle", use_sub))
