"""Google GenAI integration for image and video generation.

Supports:
- Nano Banana (gemini-2.5-flash-image): text-to-image + natural language editing
- Imagen 4: high-quality text-to-image
- Veo (2, 3, 3.1): text-to-video, image-to-video, frame interpolation
"""

import hashlib
import logging
import time
from pathlib import Path

from PIL import Image

from src.config import settings

logger = logging.getLogger(__name__)

MEDIA_DIR = Path("data/media")

VEO_MODELS = {
    "veo-2": "veo-2.0-generate-001",
    "veo-3": "veo-3.0-generate-001",
    "veo-3-fast": "veo-3.0-fast-generate-001",
    "veo-3.1": "veo-3.1-generate-preview",
    "veo-3.1-fast": "veo-3.1-fast-generate-preview",
    "veo-3.1-lite": "veo-3.1-lite-generate-001",
}

# Models that support native audio
VEO_AUDIO_MODELS = {"veo-3", "veo-3-fast", "veo-3.1", "veo-3.1-fast", "veo-3.1-lite"}

VIDEO_POLL_INTERVAL = 10  # seconds
VIDEO_TIMEOUT = 360  # 6 minutes


_client = None
_vertex_client = None


def _get_client():
    """Lazy singleton GenAI client (Gemini API — uses API key)."""
    global _client
    if _client is None:
        from google import genai

        if not settings.google_genai_api_key:
            raise ValueError("GOOGLE_API_KEY not configured")
        _client = genai.Client(api_key=settings.google_genai_api_key)
    return _client


def _get_vertex_client():
    """Lazy singleton Vertex AI client (supports audio generation).

    Requires GOOGLE_CLOUD_PROJECT and GOOGLE_APPLICATION_CREDENTIALS env vars.
    Falls back to the regular API key client if not configured.
    """
    global _vertex_client
    if _vertex_client is None:
        from google import genai

        if settings.google_cloud_project:
            _vertex_client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
            )
        else:
            # Fall back to Gemini API client (no audio support)
            _vertex_client = _get_client()
    return _vertex_client


def _ensure_media_dir() -> Path:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return MEDIA_DIR


def _make_filename(prefix: str, ext: str, prompt: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    short_hash = hashlib.md5(prompt.encode()).hexdigest()[:6]
    return f"{prefix}_{ts}_{short_hash}.{ext}"


def generate_image_flash(prompt: str, input_image_paths: list[str] | None = None) -> str:
    """Generate or edit an image using Nano Banana (gemini-2.5-flash-image).

    Args:
        prompt: Text prompt or editing instruction.
        input_image_paths: Optional list of source image paths. Supports multiple
            images for merging, compositing, or multi-reference editing.

    Returns:
        Path to saved output image.
    """
    from google.genai import types

    client = _get_client()
    contents: list = []

    if input_image_paths:
        for path in input_image_paths:
            contents.append(Image.open(path))

    contents.append(prompt)

    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )

    # Extract image from response parts
    for part in response.parts:
        if part.inline_data is not None:
            out_dir = _ensure_media_dir()
            filename = _make_filename("img", "png", prompt)
            out_path = out_dir / filename
            pil_image = part.as_image()
            pil_image.save(str(out_path))
            logger.info(f"Generated image saved to {out_path}")
            return str(out_path.resolve())

    raise RuntimeError("No image returned in response")


def generate_image_imagen(prompt: str) -> str:
    """Generate a high-quality image using Imagen 4.

    Args:
        prompt: Text description of the image.

    Returns:
        Path to saved output image.
    """
    from google.genai import types

    client = _get_client()

    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=prompt,
        config=types.GenerateImagesConfig(number_of_images=1),
    )

    if not response.generated_images:
        raise RuntimeError("No image returned from Imagen")

    out_dir = _ensure_media_dir()
    filename = _make_filename("img", "png", prompt)
    out_path = out_dir / filename
    response.generated_images[0].image.save(str(out_path))
    logger.info(f"Imagen image saved to {out_path}")
    return str(out_path.resolve())


def generate_video(
    prompt: str,
    image_path: str | None = None,
    last_frame_path: str | None = None,
    model: str = "veo-3.1",
    duration: int = 8,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    audio: bool = True,
    negative_prompt: str | None = None,
    enhance_prompt: bool = True,
    seed: int | None = None,
) -> str:
    """Generate a video using Veo.

    Args:
        prompt: Video description.
        image_path: Optional start frame image path.
        last_frame_path: Optional end frame image path (frame interpolation).
        model: Model alias (veo-2, veo-3, veo-3.1, veo-3.1-fast, veo-3.1-lite).
        duration: Duration in seconds (4-8, model-dependent).
        resolution: "720p", "1080p", or "4k" (model-dependent).
        aspect_ratio: "16:9" or "9:16".
        audio: Generate native audio (Veo 3+ only).
        negative_prompt: What to exclude from output.
        enhance_prompt: Let Google enhance the prompt.
        seed: Determinism seed (Veo 3 only).

    Returns:
        Path to saved output video.
    """
    from google.genai import types

    # Use Gemini API client — Veo 3+ generates audio natively (always on, no param needed)
    client = _get_client()

    model_id = VEO_MODELS.get(model)
    if not model_id:
        raise ValueError(f"Unknown video model '{model}'. Options: {', '.join(VEO_MODELS.keys())}")

    # Build config
    config_kwargs: dict = {
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration_seconds": duration,
        "enhance_prompt": enhance_prompt,
        "number_of_videos": 1,
    }

    # Veo 3+ generates audio natively on Gemini API (always on, no param).
    # Don't pass generate_audio — it's not a valid param on Gemini API.

    if negative_prompt:
        config_kwargs["negative_prompt"] = negative_prompt

    if seed is not None:
        config_kwargs["seed"] = seed

    # End frame for interpolation
    if last_frame_path:
        config_kwargs["last_frame"] = Image.open(last_frame_path)

    config = types.GenerateVideosConfig(**config_kwargs)

    # Build generation kwargs
    gen_kwargs: dict = {
        "model": model_id,
        "prompt": prompt,
        "config": config,
    }

    # Start frame
    if image_path:
        gen_kwargs["image"] = Image.open(image_path)

    logger.info(f"Starting video generation: model={model_id}, resolution={resolution}, duration={duration}s")
    operation = client.models.generate_videos(**gen_kwargs)

    # Poll until done
    elapsed = 0
    while not operation.done:
        if elapsed >= VIDEO_TIMEOUT:
            raise TimeoutError(f"Video generation timed out after {VIDEO_TIMEOUT}s")
        time.sleep(VIDEO_POLL_INTERVAL)
        elapsed += VIDEO_POLL_INTERVAL
        operation = client.operations.get(operation)
        logger.debug(f"Video generation polling... {elapsed}s elapsed")

    if not operation.response or not operation.response.generated_videos:
        raise RuntimeError("Video generation completed but no video returned")

    # Download and save
    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)

    out_dir = _ensure_media_dir()
    filename = _make_filename("vid", "mp4", prompt)
    out_path = out_dir / filename
    generated_video.video.save(str(out_path))
    logger.info(f"Video saved to {out_path} ({elapsed}s generation time)")
    return str(out_path.resolve())
