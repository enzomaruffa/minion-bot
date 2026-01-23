import logging
import tempfile
from pathlib import Path

from openai import OpenAI

from src.config import settings

logger = logging.getLogger(__name__)


def transcribe_voice(audio_data: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe audio data using OpenAI Whisper.

    Args:
        audio_data: Raw audio bytes.
        filename: Original filename with extension for format detection.

    Returns:
        Transcribed text.
    """
    client = OpenAI(api_key=settings.openai_api_key)

    # Write to temp file since Whisper API needs a file
    suffix = Path(filename).suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_data)
        temp_path = f.name

    try:
        with open(temp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="pt",  # Portuguese - can be made configurable
            )
        return transcript.text
    finally:
        Path(temp_path).unlink(missing_ok=True)
