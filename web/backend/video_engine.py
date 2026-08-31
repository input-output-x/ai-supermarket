"""口播视频生成引擎：可插拔 Provider。

本地 fallback：上传图 + edge-tts 配音 + PIL 字幕 + ffmpeg 合成 9:16 竖版视频，
并叠加一个简单的嘴部动画（本地模拟，非真实唇形同步）。

真实唇形同步请配置：
  LIPSYNC_PROVIDER=heygen  + HEYGEN_API_KEY
  或后续接入 D-ID / Kling / 其他数字人 API。
"""
import os
import re
import time
import asyncio
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None


def _run(cmd: list[str], timeout: int = 240) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
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


def _candidate_fonts() -> list[str]:
    return [
        "/System/Library/Fonts/Songti.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/STHeiti Regular.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]


def _find_cjk_font() -> Optional[str]:
    for p in _candidate_fonts():
        if os.path.exists(p):
            return p
    return None


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", "", text or "")
    parts = re.split(r"(?<=[。！？!?])", text)
    return [p for p in parts if p]


def _timeline(sentences: list[str], total_dur: float) -> list[tuple[str, float]]:
    weights = [max(len(s), 1) for s in sentences] or [1]
    total_w = sum(weights)
    out = []
    for s, w in zip(sentences, weights):
        out.append((s, total_dur * (w / total_w)))
    return out


def _render_subtitle_png(text: str, path: str, font_path: Optional[str]) -> bool:
    if Image is None:
        return False
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, 56) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    max_w = int(W * 0.86)
    lines, cur = [], ""
    for ch in text:
        if ch in "。！？!?，,、":
            cur += ch
            continue
        test = cur + ch
        try:
            fits = draw.textlength(test, font=font) <= max_w
        except Exception:
            fits = len(test) * 28 <= max_w
        if fits:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    lines = lines[-6:]
    lh = 78
    box_h = lh * len(lines) + 40
    box_y = H - 260 - box_h
    draw.rounded_rectangle((int(W * 0.05), box_y, int(W * 0.95), box_y + box_h),
                           radius=24, fill=(10, 10, 30, 165))
    y = box_y + 20
    for ln in lines:
        try:
            tw = draw.textlength(ln, font=font)
        except Exception:
            tw = len(ln) * 28
        draw.text(((W - tw) / 2, y), ln, font=font, fill=(255, 255, 255, 255))
        y += lh
    img.save(path)
    return True


def _make_mouth_loop(path: str, frames: int = 10) -> bool:
    """生成一个带透明通道的嘴部动画短视频（本地模拟用）。"""
    if Image is None:
        return False
    tmp_dir = Path(path).parent / "mouth_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    W, H = 120, 80
    for i in range(frames):
        t = i / frames
        # 嘴巴高度在 0.4~1.0 之间正弦变化
        k = 0.7 + 0.3 * (0.5 + 0.5 * __import__("math").sin(t * 2 * __import__("math").pi))
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        w = int(W * 0.7)
        h = int(H * 0.35 * k)
        x0, y0 = (W - w) // 2, (H - h) // 2
        draw.ellipse([x0, y0, x0 + w, y0 + h], fill=(255, 120, 130, 220))
        img.save(tmp_dir / f"mouth_{i:02d}.png")
    ok = _run([
        "ffmpeg", "-y", "-framerate", "10", "-i", str(tmp_dir / "mouth_%02d.png"),
        "-c:v", "png", "-movflags", "+faststart", path,
    ])
    # 清理帧
    for f in tmp_dir.glob("*.png"):
        f.unlink()
    tmp_dir.rmdir()
    return ok


def _generate_audio(text: str, out_path: str, voice: str) -> bool:
    try:
        import edge_tts
    except Exception as e:
        print(f"[tts] edge_tts 不可用：{e}")
        return False

    async def _go():
        comm = edge_tts.Communicate(text, voice)
        await comm.save(out_path)

    try:
        asyncio.run(_go())
        return os.path.exists(out_path) and os.path.getsize(out_path) > 0
    except Exception as e:
        print(f"[tts] edge_tts 合成失败：{e}")
        return False


class LipSyncProvider(ABC):
    @abstractmethod
    def generate(self, job_id: str, image_path: str, script: str, voice: str, output_dir: Path) -> dict:
        """Return dict with keys: video_path, audio_path, cover_path, duration, message."""
        ...


class LocalProvider(LipSyncProvider):
    """本地 TTS + 图片背景 + 字幕 + 简单嘴部动画（无需外部 key）。"""

    def generate(self, job_id: str, image_path: str, script: str, voice: str, output_dir: Path) -> dict:
        out_dir = output_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        base = str(int(time.time() * 1000))

        audio_path = out_dir / f"{base}.mp3"
        video_path = out_dir / f"{base}.mp4"
        cover_path = out_dir / f"{base}.jpg"
        silent_path = out_dir / f"{base}_silent.mp4"
        mouth_path = out_dir / f"{base}_mouth.mov"

        # 1) TTS
        has_audio = _generate_audio(script, str(audio_path), voice)
        duration = _probe_duration(str(audio_path)) if has_audio else max(8.0, len(script) / 6.0)
        if duration <= 0:
            duration = max(8.0, len(script) / 6.0)

        # 2) 字幕 + 片段
        font = _find_cjk_font()
        sentences = _split_sentences(script)
        tl = _timeline(sentences, duration)
        seg_paths = []
        use_sub = bool(font and sentences)
        if use_sub:
            for i, (s, d) in enumerate(tl):
                png = out_dir / f"{base}_sub{i}.png"
                if not _render_subtitle_png(s, str(png), font):
                    use_sub = False
                    break
                seg = out_dir / f"{base}_seg{i}.mp4"
                # 图片背景片段（9:16 裁剪填充）
                ok = _run([
                    "ffmpeg", "-y", "-loop", "1", "-i", image_path,
                    "-t", f"{d:.2f}",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(seg)
                ])
                if not ok:
                    use_sub = False
                    break
                seg_sub = out_dir / f"{base}_seg{i}_sub.mp4"
                ok = _run([
                    "ffmpeg", "-y", "-i", str(seg), "-loop", "1", "-i", str(png),
                    "-filter_complex", "[0][1]overlay=shortest=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(seg_sub)
                ])
                if ok:
                    seg_paths.append(str(seg_sub))
                else:
                    use_sub = False
                    break

        # 3) 拼接静音成片
        if use_sub and seg_paths:
            concat = out_dir / f"{base}_concat.txt"
            with open(concat, "w", encoding="utf-8") as f:
                for s in seg_paths:
                    f.write(f"file '{os.path.abspath(s)}'\n")
            ok = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                       "-i", str(concat), "-c", "copy", str(silent_path)])
        else:
            ok = _run([
                "ffmpeg", "-y", "-loop", "1", "-i", image_path,
                "-t", f"{duration:.2f}",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(silent_path)
            ])

        # 4) 嘴部动画叠加（本地模拟）
        if ok and _make_mouth_loop(str(mouth_path)):
            mouth_out = out_dir / f"{base}_mouth_overlay.mp4"
            ok2 = _run([
                "ffmpeg", "-y", "-i", str(silent_path),
                "-stream_loop", "-1", "-i", str(mouth_path),
                "-filter_complex",
                "[0][1]overlay=(W-w)/2:H-h-320:shortest=1:format=auto",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(mouth_out)
            ])
            if ok2:
                silent_path = mouth_out

        # 5) 混音
        final_video = out_dir / f"{base}_final.mp4"
        if ok and has_audio:
            ok = _run([
                "ffmpeg", "-y", "-i", str(silent_path), "-i", str(audio_path),
                "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_video)
            ])
        elif ok:
            ok = _run(["ffmpeg", "-y", "-i", str(silent_path), "-c", "copy", str(final_video)])

        # 6) 封面
        if ok:
            _run(["ffmpeg", "-y", "-i", str(final_video), "-frames:v", "1", str(cover_path)])

        return {
            "video_path": str(final_video) if ok and final_video.exists() else str(silent_path) if ok else None,
            "audio_path": str(audio_path) if has_audio else None,
            "cover_path": str(cover_path) if cover_path.exists() else None,
            "duration": round(duration, 1),
            "message": "本地 fallback 成片（图片+配音+字幕+嘴部动画），真实唇形同步请配置 HeyGen/D-ID/Kling Provider" if ok else "视频生成失败",
        }


class HeyGenProvider(LipSyncProvider):
    """HeyGen 真实数字人唇形同步（需 HEYGEN_API_KEY）。当前为占位实现，接入方式预留。"""

    def generate(self, job_id: str, image_path: str, script: str, voice: str, output_dir: Path) -> dict:
        api_key = os.getenv("HEYGEN_API_KEY")
        if not api_key:
            raise RuntimeError("LIPSYNC_PROVIDER=heygen 需要设置 HEYGEN_API_KEY")
        # TODO: 调用 HeyGen Streaming Avatar / Video Translate API，上传图片+音频，轮询结果
        return LocalProvider().generate(job_id, image_path, script, voice, output_dir)


_PROVIDERS = {
    "local": LocalProvider,
    "heygen": HeyGenProvider,
}


def get_provider(name: Optional[str] = None) -> LipSyncProvider:
    name = (name or os.getenv("LIPSYNC_PROVIDER", "local")).lower()
    cls = _PROVIDERS.get(name, LocalProvider)
    return cls()
