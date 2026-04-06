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
            path = generate_image_flash(prompt, input_image_path=source_image_path or None)

        caption = f"Generated: {prompt[:180]}"
        send_file(path, caption)
        return f"Image generated and sent. Saved at {path}"
    except Exception as e:
        logger.exception("Image generation failed")
        return f"Image generation failed: {e}"


def edit_image(image_path: str, instruction: str) -> str:
    """Edit an existing image using natural language instructions.

    Uses Nano Banana (Gemini) to understand the image and apply edits described in plain text.
    No masks needed — just describe what you want changed.

    Args:
        image_path: Absolute path to the image to edit.
        instruction: Natural language description of the desired edit (e.g., "remove the background",
            "make it look like a watercolor painting", "add sunglasses to the person").

    Returns:
        Confirmation message after sending the edited image.
    """
    from src.integrations.media_gen import generate_image_flash

    try:
        path = generate_image_flash(instruction, input_image_path=image_path)
        caption = f"Edited: {instruction[:180]}"
        send_file(path, caption)
        return f"Image edited and sent. Saved at {path}"
    except Exception as e:
        logger.exception("Image editing failed")
        return f"Image editing failed: {e}"


def generate_video(
    prompt: str,
    model: str = "veo-3.1",
    start_image_path: str = "",
    end_image_path: str = "",
    duration: int = 8,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    audio: bool = True,
    negative_prompt: str = "",
    enhance_prompt: bool = True,
) -> str:
    """Generate a video from a text prompt, optionally with start/end frame images.

    Supports text-to-video, image-to-video (start frame), and frame interpolation (start + end frames).
    Video generation takes 1-5 minutes depending on settings.

    Args:
        prompt: Text description of the video to generate.
        model: Video model to use. Options: "veo-2", "veo-3", "veo-3-fast", "veo-3.1" (default),
            "veo-3.1-fast", "veo-3.1-lite".
        start_image_path: Optional path to starting frame image for image-to-video.
        end_image_path: Optional path to ending frame image for frame interpolation.
        duration: Video duration in seconds. Veo 2 supports 5-8, Veo 3+ supports 4/6/8. Default 8.
        resolution: Video resolution. "720p" (default, all models), "1080p" (Veo 3+, requires duration=8),
            "4k" (Veo 3.1/3.1-fast only, requires duration=8).
        aspect_ratio: "16:9" (landscape, default) or "9:16" (portrait).
        audio: Generate native audio with the video (Veo 3+ only, default True).
        negative_prompt: What to exclude from the video (visual and audio).
        enhance_prompt: Let Google rewrite/enhance the prompt for better results (default True).

    Returns:
        Confirmation message after sending the generated video.
    """
    import asyncio
    import concurrent.futures

    from src.integrations.media_gen import generate_video as _generate_video

    # Notify user about the wait
    try:
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            loop.run_in_executor(pool, lambda: asyncio.run(notify("Generating video, this may take a few minutes...")))
    except RuntimeError:
        asyncio.run(notify("Generating video, this may take a few minutes..."))

    try:
        path = _generate_video(
            prompt=prompt,
            image_path=start_image_path or None,
            last_frame_path=end_image_path or None,
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            audio=audio,
            negative_prompt=negative_prompt or None,
            enhance_prompt=enhance_prompt,
        )

        caption = f"Generated: {prompt[:180]}"
        send_file(path, caption)
        return f"Video generated and sent. Saved at {path}"
    except TimeoutError:
        return "Video generation timed out after 6 minutes. Try a simpler prompt or lower resolution."
    except Exception as e:
        logger.exception("Video generation failed")
        return f"Video generation failed: {e}"
