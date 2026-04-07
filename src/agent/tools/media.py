"""Media generation tools — image and video creation/editing via Google GenAI."""

import logging

from src.agent.tools.files import send_file
from src.notifications import notify

logger = logging.getLogger(__name__)


def generate_image(prompt: str, model: str = "flash", source_image_path: str = "") -> str:
    """Generate an image from a text prompt, or edit an existing image with natural language.

    Args:
        prompt: Text description of the image to generate, or editing instruction if source_image_path is provided.
        model: "flash" for fast generation/editing (default), "imagen" for high-quality generation only.
        source_image_path: Optional absolute path to an existing image to edit (only works with flash model).

    Returns:
        Confirmation message after sending the generated image.
    """
    from src.integrations.media_gen import generate_image_flash, generate_image_imagen

    if source_image_path and model == "imagen":
        return "Imagen only supports text-to-image generation. Use model='flash' for image editing."

    try:
        if model == "imagen":
            path = generate_image_imagen(prompt)
        else:
            paths = [source_image_path] if source_image_path else None
            path = generate_image_flash(prompt, input_image_paths=paths)

        caption = f"Generated: {prompt[:180]}"
        send_file(path, caption)
        return f"Image generated and sent. Saved at {path}"
    except Exception as e:
        logger.exception("Image generation failed")
        return f"Image generation failed: {e}"


def edit_image(image_paths: str, instruction: str) -> str:
    """Edit or combine images using natural language instructions.

    Uses Nano Banana (Gemini) to understand images and apply edits described in plain text.
    No masks needed — just describe what you want. Supports multiple input images for
    merging, compositing, style transfer, or any multi-image operation.

    Args:
        image_paths: Absolute path(s) to image(s). Comma-separated for multiple images
            (e.g., "/path/to/cat.jpg" or "/path/to/bg.jpg,/path/to/person.jpg").
        instruction: Natural language description of the desired edit (e.g., "remove the background",
            "merge these two images", "place the person from the second image onto the background
            of the first image", "combine these in the style of a collage").

    Returns:
        Confirmation message after sending the edited image.
    """
    from src.integrations.media_gen import generate_image_flash

    paths = [p.strip() for p in image_paths.split(",") if p.strip()]
    if not paths:
        return "No image paths provided."

    try:
        path = generate_image_flash(instruction, input_image_paths=paths)
        caption = f"Edited: {instruction[:180]}"
        send_file(path, caption)
        return f"Image edited and sent. Saved at {path}"
    except Exception as e:
        logger.exception("Image editing failed")
        return f"Image editing failed: {e}"


def generate_video(
    prompt: str,
    start_image_path: str = "",
    duration: int = 8,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    negative_prompt: str = "",
) -> str:
    """Generate a video from a text prompt, optionally from a start frame image.

    Uses veo-3.1-lite (fast, cheap, has native audio). Takes 1-5 minutes.
    Audio is always generated — describe sounds/dialogue in the prompt for best results.

    Args:
        prompt: Text description of the video to generate. Include dialogue in quotes.
        start_image_path: Optional path to starting frame image for image-to-video.
        duration: Video duration in seconds (4, 6, or 8). Default 8.
        resolution: "720p" (default) or "1080p" (requires duration=8).
        aspect_ratio: "16:9" (landscape, default) or "9:16" (portrait).
        negative_prompt: What to exclude from the video (visual and audio).

    Returns:
        Confirmation message after sending the generated video.
    """
    import asyncio

    from src.integrations.media_gen import generate_video as _generate_video

    # Notify user about the wait
    try:
        asyncio.run(notify("Generating video, this may take a few minutes..."))
    except Exception:
        logger.debug("Could not send video generation notification")

    try:
        path = _generate_video(
            prompt=prompt,
            image_path=start_image_path or None,
            model="veo-3.1-lite",
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt or None,
        )

        caption = f"Generated: {prompt[:180]}"
        send_file(path, caption)
        return f"Video generated and sent. Saved at {path}"
    except TimeoutError:
        return "Video generation timed out after 6 minutes. Try a simpler prompt or lower resolution."
    except Exception as e:
        logger.exception("Video generation failed")
        return f"Video generation failed: {e}"
