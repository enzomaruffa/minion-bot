"""FFmpeg tools — video/audio editing, stitching, trimming, and conversion."""

import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MEDIA_DIR = Path("data/media")
_TIMEOUT = 300  # 5 minutes max per ffmpeg operation


def _ensure_media_dir() -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return MEDIA_DIR


def _run_ffmpeg(args: list[str], timeout: int = _TIMEOUT) -> tuple[bool, str]:
    """Run an ffmpeg command and return (success, output)."""
    cmd = ["ffmpeg", "-y"] + args  # -y to overwrite without asking
    logger.info(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return False, result.stderr[-2000:]
        return True, result.stderr[-500:]  # ffmpeg outputs info to stderr
    except subprocess.TimeoutExpired:
        return False, f"FFmpeg timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


def _out_path(prefix: str, ext: str) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return _ensure_media_dir() / f"{prefix}_{ts}.{ext}"


def trim_video(file_path: str, start: str = "0", end: str = "", duration: str = "") -> str:
    """Trim a video to a specific time range.

    Args:
        file_path: Absolute path to the input video.
        start: Start time (e.g., "00:00:05" or "5" for 5 seconds in).
        end: End time (e.g., "00:00:15" or "15"). Mutually exclusive with duration.
        duration: Duration to keep (e.g., "10" for 10 seconds). Mutually exclusive with end.

    Returns:
        Confirmation with output path, or error message.
    """
    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    out = _out_path("trim", "mp4")
    args = ["-i", file_path, "-ss", start]
    if end:
        args += ["-to", end]
    elif duration:
        args += ["-t", duration]
    args += ["-c", "copy", str(out)]

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Trim failed: {msg}"
    return f"Trimmed video saved to {out.resolve()}"


def concat_videos(file_paths: str, crossfade: float = 0) -> str:
    """Concatenate multiple videos into one.

    Args:
        file_paths: Comma-separated absolute paths to videos (in order).
        crossfade: Optional crossfade duration in seconds between clips (0 = hard cut).

    Returns:
        Confirmation with output path, or error message.
    """
    paths = [p.strip() for p in file_paths.split(",") if p.strip()]
    if len(paths) < 2:
        return "Need at least 2 video paths (comma-separated)."

    for p in paths:
        if not Path(p).exists():
            return f"File not found: {p}"

    out = _out_path("concat", "mp4")

    if crossfade > 0:
        # Use xfade filter for crossfade transitions
        inputs = []
        for p in paths:
            inputs += ["-i", p]

        # Build xfade filter chain
        n = len(paths)
        if n == 2:
            filter_str = f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset=0[v]"
            args = inputs + ["-filter_complex", filter_str, "-map", "[v]", "-an", str(out)]
        else:
            # Chain xfade filters for 3+ videos
            filters = []
            prev = "0:v"
            for i in range(1, n):
                out_label = f"v{i}" if i < n - 1 else "v"
                filters.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={crossfade}:offset=0[{out_label}]")
                prev = out_label
            filter_str = ";".join(filters)
            args = inputs + ["-filter_complex", filter_str, "-map", "[v]", "-an", str(out)]
    else:
        # Use concat demuxer for lossless concatenation
        import tempfile

        fd, tmp = tempfile.mkstemp(suffix=".txt")
        import os

        os.close(fd)
        list_file = Path(tmp)
        try:
            list_file.write_text("\n".join(f"file '{p}'" for p in paths))
            args = ["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)]
            ok, msg = _run_ffmpeg(args)
        finally:
            list_file.unlink(missing_ok=True)

        if not ok:
            return f"Concatenation failed: {msg}"
        return f"Concatenated {len(paths)} videos. Saved to {out.resolve()}"

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Concatenation failed: {msg}"
    return f"Concatenated {len(paths)} videos with {crossfade}s crossfade. Saved to {out.resolve()}"


def add_audio(video_path: str, audio_path: str, mix: bool = False, volume: float = 1.0) -> str:
    """Add or replace audio track on a video.

    Args:
        video_path: Absolute path to the input video.
        audio_path: Absolute path to the audio file (mp3, wav, m4a, etc.).
        mix: If True, mix with existing audio. If False (default), replace it.
        volume: Volume multiplier for the added audio (0.0-2.0, default 1.0).

    Returns:
        Confirmation with output path, or error message.
    """
    for p, name in [(video_path, "Video"), (audio_path, "Audio")]:
        if not Path(p).exists():
            return f"{name} not found: {p}"

    out = _out_path("audio", "mp4")

    if mix:
        vol_filter = f"[1:a]volume={volume}[a1];[0:a][a1]amix=inputs=2:duration=first[aout]"
        args = [
            "-i",
            video_path,
            "-i",
            audio_path,
            "-filter_complex",
            vol_filter,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-shortest",
            str(out),
        ]
    else:
        args = ["-i", video_path, "-i", audio_path, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-shortest", str(out)]
        if volume != 1.0:
            args = [
                "-i",
                video_path,
                "-i",
                audio_path,
                "-filter_complex",
                f"[1:a]volume={volume}[aout]",
                "-map",
                "0:v",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-shortest",
                str(out),
            ]

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Add audio failed: {msg}"
    return f"Audio added to video. Saved to {out.resolve()}"


def extract_audio(file_path: str, format: str = "mp3") -> str:
    """Extract the audio track from a video.

    Args:
        file_path: Absolute path to the input video.
        format: Output format — "mp3", "wav", "m4a", "aac". Default "mp3".

    Returns:
        Confirmation with output path, or error message.
    """
    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    out = _out_path("audio", format)
    args = ["-i", file_path, "-vn", "-q:a", "2", str(out)]

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Audio extraction failed: {msg}"
    return f"Audio extracted. Saved to {out.resolve()}"


def resize_video(file_path: str, resolution: str = "720p") -> str:
    """Resize a video to a target resolution.

    Args:
        file_path: Absolute path to the input video.
        resolution: Target resolution — "480p", "720p", "1080p", or WxH like "1920x1080".

    Returns:
        Confirmation with output path, or error message.
    """
    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    presets = {"480p": "854:480", "720p": "1280:720", "1080p": "1920:1080", "4k": "3840:2160"}
    scale = presets.get(resolution, resolution.replace("x", ":"))

    out = _out_path("resize", "mp4")
    args = [
        "-i",
        file_path,
        "-vf",
        f"scale={scale}:force_original_aspect_ratio=decrease,pad={scale}:-1:-1",
        "-c:a",
        "copy",
        str(out),
    ]

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Resize failed: {msg}"
    return f"Video resized to {resolution}. Saved to {out.resolve()}"


def speed_video(file_path: str, factor: float = 2.0) -> str:
    """Speed up or slow down a video (with audio pitch correction).

    Args:
        file_path: Absolute path to the input video.
        factor: Speed multiplier. >1 = faster, <1 = slower. E.g., 2.0 = 2x speed, 0.5 = half speed.

    Returns:
        Confirmation with output path, or error message.
    """
    if not Path(file_path).exists():
        return f"File not found: {file_path}"
    if factor <= 0:
        return "Speed factor must be positive."

    out = _out_path("speed", "mp4")
    video_filter = f"setpts={1 / factor}*PTS"
    audio_filter = f"atempo={factor}" if 0.5 <= factor <= 2.0 else f"atempo={min(max(factor, 0.5), 2.0)}"

    args = ["-i", file_path, "-filter:v", video_filter, "-filter:a", audio_filter, str(out)]

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Speed change failed: {msg}"
    return f"Video speed changed to {factor}x. Saved to {out.resolve()}"


def add_text_overlay(
    file_path: str,
    text: str,
    position: str = "bottom",
    font_size: int = 48,
    color: str = "white",
    start: str = "",
    end: str = "",
) -> str:
    """Add text overlay to a video.

    Args:
        file_path: Absolute path to the input video.
        text: Text to display on the video.
        position: "top", "center", "bottom" (default), or custom "x=100:y=200".
        font_size: Font size in pixels (default 48).
        color: Text color name (default "white").
        start: Start time for text appearance (e.g., "2" for 2s in). Empty = from start.
        end: End time for text (e.g., "5"). Empty = until end.

    Returns:
        Confirmation with output path, or error message.
    """
    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    pos_map = {
        "top": "x=(w-text_w)/2:y=40",
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
        "bottom": "x=(w-text_w)/2:y=h-text_h-40",
    }
    pos = pos_map.get(position, position)

    # Escape special chars for ffmpeg drawtext
    safe_text = text.replace("'", "\\'").replace(":", "\\:")
    dt = f"drawtext=text='{safe_text}':{pos}:fontsize={font_size}:fontcolor={color}:borderw=2:bordercolor=black"

    if start or end:
        enable_parts = []
        if start:
            enable_parts.append(f"gte(t\\,{start})")
        if end:
            enable_parts.append(f"lte(t\\,{end})")
        enable = "*".join(enable_parts)
        dt += f":enable='{enable}'"

    out = _out_path("text", "mp4")
    args = ["-i", file_path, "-vf", dt, "-c:a", "copy", str(out)]

    ok, msg = _run_ffmpeg(args)
    if not ok:
        return f"Text overlay failed: {msg}"
    return f"Text overlay added. Saved to {out.resolve()}"


def probe_media(file_path: str) -> str:
    """Get detailed info about a media file (duration, resolution, codecs, etc.).

    Args:
        file_path: Absolute path to the media file.

    Returns:
        Media file information (duration, resolution, codecs, bitrate).
    """
    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"Probe failed: {result.stderr[-500:]}"

        import json

        data = json.loads(result.stdout)

        lines = []
        fmt = data.get("format", {})
        if fmt.get("duration"):
            lines.append(f"Duration: {float(fmt['duration']):.1f}s")
        if fmt.get("size"):
            lines.append(f"Size: {int(fmt['size']) / (1024 * 1024):.1f} MB")
        if fmt.get("format_long_name"):
            lines.append(f"Format: {fmt['format_long_name']}")

        for s in data.get("streams", []):
            if s["codec_type"] == "video":
                lines.append(
                    f"Video: {s.get('width')}x{s.get('height')} {s.get('codec_name')} @ {s.get('r_frame_rate')} fps"
                )
            elif s["codec_type"] == "audio":
                lines.append(f"Audio: {s.get('codec_name')} {s.get('sample_rate')}Hz {s.get('channels')}ch")

        return "\n".join(lines) if lines else result.stdout[:2000]
    except Exception as e:
        return f"Probe failed: {e}"
