import base64
import logging

from openai import OpenAI

from src.config import settings

logger = logging.getLogger(__name__)


def analyze_image(image_data: bytes, prompt: str = "Describe this image.") -> str:
    """Analyze an image using GPT-4o vision.

    Args:
        image_data: Raw image bytes.
        prompt: Question or instruction about the image.

    Returns:
        Analysis result text.
    """
    client = OpenAI(api_key=settings.openai_api_key)

    # Encode image to base64
    base64_image = base64.b64encode(image_data).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
        max_tokens=500,
    )

    return response.choices[0].message.content or ""


def extract_task_from_image(image_data: bytes) -> str:
    """Extract potential tasks or actionable items from an image.

    Args:
        image_data: Raw image bytes.

    Returns:
        Extracted information that might be relevant for task creation.
    """
    prompt = """Analyze this image and extract any information that might be relevant
for task management or reminders. This could include:
- Text from documents, notes, or whiteboards
- Dates, times, or deadlines visible
- To-do items or action items
- Event information
- Any other actionable content

Provide a concise summary of what you see that might need follow-up action."""

    return analyze_image(image_data, prompt)
