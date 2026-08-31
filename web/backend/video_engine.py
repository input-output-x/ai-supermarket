"""口播视频生成引擎：可插拔 Provider。

本地 fallback：上传图 + edge-tts 配音 + PIL 字幕 + ffmpeg 合成 9:16 竖版视频，
并叠加一个简单的嘴部动画（本地模拟，非真实唇形同步）。

真实唇形同步：
  - BailianProvider（阿里云百炼 / DashScope）：wan2.2-s2v 万相数字人，
    单张图 + 音频 → 逼真对口型说话视频。
    配置：LIPSYNC_PROVIDER=bailian + DASHSCOPE_API_KEY=sk-xxx
  - HeyGenProvider：预留真实数字人接入点（需 HEYGEN_API_KEY）。
"""
import os
import re
import time
import glob
import asyncio
import subprocess
import base64
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

try:
    import requests  # 百炼 HTTP 调用
except Exception:
    requests = None

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None


def _run(cmd: list[str], timeout: int = 300) -> bool:
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
    import math
    for i in range(frames):
        t = i / frames
        k = 0.7 + 0.3 * (0.5 + 0.5 * math.sin(t * 2 * math.pi))
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


# ---------------------------------------------------------------------------
# Provider 抽象
# ---------------------------------------------------------------------------
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

        # 校验图片有效性，避免把损坏/非图片文件丢给 ffmpeg 导致卡死
        if Image is not None:
            try:
                with Image.open(image_path) as _im:
                    _im.verify()
            except Exception:
                return {
                    "video_path": None, "audio_path": None, "cover_path": None,
                    "duration": 0, "message": "图片文件无效，无法生成视频（请上传有效的 jpg/png/webp）",
                }

        audio_path = out_dir / f"{base}.mp3"
        video_path = out_dir / f"{base}.mp4"
        cover_path = out_dir / f"{base}.jpg"
        silent_path = out_dir / f"{base}_silent.mp4"
        mouth_path = out_dir / f"{base}_mouth.mov"

        has_audio = _generate_audio(script, str(audio_path), voice)
        duration = _probe_duration(str(audio_path)) if has_audio else max(8.0, len(script) / 6.0)
        if duration <= 0:
            duration = max(8.0, len(script) / 6.0)

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
                ok = _run([
                    "ffmpeg", "-y", "-loop", "1", "-r", "30", "-i", image_path,
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

        if use_sub and seg_paths:
            concat = out_dir / f"{base}_concat.txt"
            with open(concat, "w", encoding="utf-8") as f:
                for s in seg_paths:
                    f.write(f"file '{os.path.abspath(s)}'\n")
            ok = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                       "-i", str(concat), "-c", "copy", str(silent_path)])
        else:
            ok = _run([
                "ffmpeg", "-y", "-loop", "1", "-r", "30", "-i", image_path,
                "-t", f"{duration:.2f}",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(silent_path)
            ])

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

        final_video = out_dir / f"{base}_final.mp4"
        if ok and has_audio:
            ok = _run([
                "ffmpeg", "-y", "-i", str(silent_path), "-i", str(audio_path),
                "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_video)
            ])
        elif ok:
            ok = _run(["ffmpeg", "-y", "-i", str(silent_path), "-c", "copy", str(final_video)])

        if ok:
            _run(["ffmpeg", "-y", "-i", str(final_video), "-frames:v", "1", str(cover_path)])

        return {
            "video_path": str(final_video) if ok and final_video.exists() else str(silent_path) if ok else None,
            "audio_path": str(audio_path) if has_audio else None,
            "cover_path": str(cover_path) if cover_path.exists() else None,
            "duration": round(duration, 1),
            "message": "本地 fallback 成片（图片+配音+字幕+嘴部动画），真实唇形同步请配置 Bailian/HeyGen Provider" if ok else "视频生成失败",
        }


# ---------------------------------------------------------------------------
# 阿里云百炼 / DashScope：wan2.2-s2v 万相数字人（真实对口型）
# ---------------------------------------------------------------------------
class BailianProvider(LipSyncProvider):
    """万相数字人 wan2.2-s2v：单张图 + 人声音频 → 逼真对口型说话视频。

    流程：edge-tts 生成配音 → 上传图/音频到百炼临时存储拿 oss:// URL
          → 调用 wan2.2-s2v（异步）→ 轮询 → 下载成片 → 适配 9:16 + 字幕。
    约束：音频须 < 20s（视频时长 = 音频时长），长口播稿自动切片。
    """

    MODEL = "wan2.2-s2v"
    BASE = "https://dashscope.aliyuncs.com"

    def _upload(self, file_path: str, api_key: str) -> Optional[str]:
        """上传本地文件到百炼临时存储，返回 oss:// 临时 URL（有效期 48h）。"""
        if requests is None:
            return None
        try:
            r = requests.get(
                f"{self.BASE}/api/v1/uploads",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                params={"action": "getPolicy", "model": self.MODEL},
                timeout=30,
            )
            if r.status_code != 200:
                print(f"[bailian][upload] getPolicy 失败 {r.status_code}: {r.text[:300]}")
                return None
            data = r.json().get("data", {})
            key = f"{data['upload_dir']}/{Path(file_path).name}"
            files = {
                "OSSAccessKeyId": (None, data["oss_access_key_id"]),
                "Signature": (None, data["signature"]),
                "policy": (None, data["policy"]),
                "x-oss-object-acl": (None, data["x_oss_object_acl"]),
                "x-oss-forbid-overwrite": (None, data["x_oss_forbid_overwrite"]),
                "key": (None, key),
                "success_action_status": (None, "200"),
                "file": (Path(file_path).name, open(file_path, "rb")),
            }
            r2 = requests.post(data["upload_host"], files=files, timeout=120)
            if r2.status_code not in (200, 204):
                print(f"[bailian][upload] OSS 上传失败 {r2.status_code}: {r2.text[:300]}")
                return None
            # getPolicy 返回的 upload_dir 已含 dashscope-instant 前缀，这里直接拼 oss:// 即可
            return f"oss://{key}"
        except Exception as e:
            print(f"[bailian][upload] 异常：{e}")
            return None

    def _create_task(self, image_url: str, audio_url: str, api_key: str) -> Optional[str]:
        if requests is None:
            return None
        # 分辨率：默认 480P（0.5元/秒，抖音竖屏够用）；要更清晰设 BAILIAN_RESOLUTION=720P（0.9元/秒）
        _res = os.environ.get("BAILIAN_RESOLUTION", "480P").upper()
        resolution = "720P" if _res == "720P" else "480P"
        body = {
            "model": self.MODEL,
            "input": {"image_url": image_url, "audio_url": audio_url},
            "parameters": {"style": "speech", "resolution": resolution},
        }
        try:
            r = requests.post(
                f"{self.BASE}/api/v1/services/aigc/image2video/video-synthesis",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                    "X-DashScope-OssResourceResolve": "enable",
                },
                json=body,
                timeout=60,
            )
            if r.status_code != 200:
                print(f"[bailian][task] 建任务失败 {r.status_code}: {r.text[:500]}")
                return None
            return r.json().get("output", {}).get("task_id")
        except Exception as e:
            print(f"[bailian][task] 异常：{e}")
            return None

    def _poll(self, task_id: str, api_key: str, timeout: int = 600) -> Optional[str]:
        if requests is None:
            return None
        url = f"{self.BASE}/api/v1/tasks/{task_id}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
                if r.status_code != 200:
                    time.sleep(6)
                    continue
                js = r.json()
                st = js.get("output", {}).get("task_status")
                if st == "SUCCEEDED":
                    out = js.get("output", {})
                    # 兼容两种返回结构：output.video_url 或 output.results.video_url
                    vurl = out.get("video_url") or (out.get("results") or {}).get("video_url")
                    print(f"[bailian][poll] 任务成功，视频地址已获取")
                    return vurl
                if st == "FAILED":
                    print(f"[bailian][poll] 任务失败: {js.get('output')}")
                    return None
            except Exception as e:
                print(f"[bailian][poll] 异常：{e}")
            time.sleep(8)
        return None

    def _download(self, url: str, dest: Path) -> bool:
        if requests is None:
            return False
        try:
            r = requests.get(url, timeout=180, stream=True)
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                return dest.exists()
        except Exception as e:
            print(f"[bailian][download] 异常：{e}")
        return False

    def _split_audio(self, audio_path: str, out_dir: Path) -> list[str]:
        """把配音切成 <=12s 的小段（百炼要求单段 < 20s）。"""
        dur = _probe_duration(audio_path)
        if dur <= 19:
            return [audio_path]
        pattern = str(out_dir / "chunk_%03d.mp3")
        if not _run([
            "ffmpeg", "-y", "-i", audio_path, "-f", "segment", "-segment_time", "12",
            "-reset_timestamps", "1", pattern,
        ]):
            return [audio_path]
        files = sorted(glob.glob(str(out_dir / "chunk_*.mp3")))
        return files or [audio_path]

    def _concat(self, videos: list, out: Path) -> bool:
        lst = out.parent / "bailian_concat.txt"
        with open(lst, "w", encoding="utf-8") as f:
            for v in videos:
                f.write(f"file '{os.path.abspath(str(v))}'\n")
        return _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
        ], timeout=300)

    def _pad_to_9_16(self, src: str, dst: str, script: str) -> bool:
        """统一适配为 1080x1920 竖版，并在底部叠加口播稿字幕（非致命）。"""
        filter_chain = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p"
        )
        ok = _run([
            "ffmpeg", "-y", "-i", src, "-vf", filter_chain,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", dst,
        ])
        if not ok:
            return False
        font = _find_cjk_font()
        if font and script:
            sub_png = Path(dst).parent / (Path(dst).stem + "_sub.png")
            if _render_subtitle_png(script, str(sub_png), font):
                sub_out = Path(dst).parent / (Path(dst).stem + "_subd.mp4")
                ok2 = _run([
                    "ffmpeg", "-y", "-i", dst, "-loop", "1", "-i", str(sub_png),
                    "-filter_complex", "[0][1]overlay=shortest=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", str(sub_out),
                ])
                if ok2 and sub_out.exists():
                    sub_out.replace(Path(dst))
        return True

    def generate(self, job_id: str, image_path: str, script: str, voice: str, output_dir: Path) -> dict:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        # 分辨率：默认 480P（0.5元/秒）；BAILIAN_RESOLUTION=720P 更清晰但 0.9元/秒
        _res = os.environ.get("BAILIAN_RESOLUTION", "480P").upper()
        resolution = "720P" if _res == "720P" else "480P"
        out_dir = output_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        base = str(int(time.time() * 1000))
        audio_path = out_dir / f"{base}.mp3"
        final_video = out_dir / f"{base}_final.mp4"
        cover_path = out_dir / f"{base}.jpg"

        # 缺少 key → 降级本地
        if not api_key or requests is None:
            res = LocalProvider().generate(job_id, image_path, script, voice, output_dir)
            res["message"] = "未配置 DASHSCOPE_API_KEY（或缺失 requests），已降级为本地 fallback"
            return res

        # 1) 配音
        has_audio = _generate_audio(script, str(audio_path), voice)
        if not has_audio:
            res = LocalProvider().generate(job_id, image_path, script, voice, output_dir)
            res["message"] = "edge-tts 配音失败，已降级为本地 fallback"
            return res

        # 2) 上传图片（一次）
        image_url = self._upload(image_path, api_key)
        if not image_url:
            res = LocalProvider().generate(job_id, image_path, script, voice, output_dir)
            res["message"] = "百炼上传图片失败，已降级为本地 fallback"
            return res

        # 3) 切片 + 逐段生成（每段失败最多重试 1 次，仍失败才降级本地 fallback）
        chunks = self._split_audio(str(audio_path), out_dir)
        seg_videos = []
        for i, ch in enumerate(chunks):
            audio_url = self._upload(ch, api_key)
            if not audio_url:
                break
            result_url = None
            for attempt in range(2):  # 0=首次，1=重试一次
                task_id = self._create_task(image_url, audio_url, api_key)
                if not task_id:
                    print(f"[bailian] 第{i}段 创建任务失败（尝试 {attempt+1}/2）")
                    continue
                result_url = self._poll(task_id, api_key)
                if result_url:
                    break
                print(f"[bailian] 第{i}段 轮询未拿到视频（尝试 {attempt+1}/2）")
            if not result_url:
                print("[bailian] 分段百炼生成重试后仍失败")
                break
            local_v = out_dir / f"{base}_bailian_{i}.mp4"
            if self._download(result_url, local_v):
                seg_videos.append(local_v)

        if not seg_videos:
            res = LocalProvider().generate(job_id, image_path, script, voice, output_dir)
            res["message"] = "百炼生成失败，已降级为本地 fallback"
            return res

        # 4) 拼接多段
        raw = out_dir / f"{base}_bailian_raw.mp4"
        if len(seg_videos) > 1:
            if not self._concat(seg_videos, raw):
                raw = seg_videos[0]
        else:
            raw = seg_videos[0]

        # 5) 适配 9:16 + 字幕
        ok = self._pad_to_9_16(str(raw), str(final_video), script)
        duration = _probe_duration(str(final_video)) if ok else 0
        if ok:
            _run(["ffmpeg", "-y", "-i", str(final_video), "-frames:v", "1", str(cover_path)])

        return {
            "video_path": str(final_video) if ok and final_video.exists() else None,
            "audio_path": str(audio_path) if has_audio else None,
            "cover_path": str(cover_path) if cover_path.exists() else None,
            "duration": round(duration, 1),
            "message": f"✅ 阿里云百炼 wan2.2-s2v 数字人成片（真实对口型，{resolution}）" if ok else "百炼成片后处理失败",
        }


class HeyGenProvider(LipSyncProvider):
    """HeyGen 真实数字人唇形同步（需 HEYGEN_API_KEY）。当前为占位实现，接入方式预留。"""

    def generate(self, job_id: str, image_path: str, script: str, voice: str, output_dir: Path) -> dict:
        api_key = os.getenv("HEYGEN_API_KEY")
        if not api_key:
            res = LocalProvider().generate(job_id, image_path, script, voice, output_dir)
            res["message"] = "LIPSYNC_PROVIDER=heygen 需要设置 HEYGEN_API_KEY，已降级本地"
            return res
        # TODO: 调用 HeyGen Streaming Avatar / Video Translate API，上传图片+音频，轮询结果
        return LocalProvider().generate(job_id, image_path, script, voice, output_dir)


_PROVIDERS = {
    "local": LocalProvider,
    "bailian": BailianProvider,
    "heygen": HeyGenProvider,
}


def get_provider(name: Optional[str] = None) -> LipSyncProvider:
    name = (name or os.getenv("LIPSYNC_PROVIDER", "local")).lower()
    cls = _PROVIDERS.get(name, LocalProvider)
    return cls()
