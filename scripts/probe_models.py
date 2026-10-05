"""Diagnostic helper: list Gemini models usable with the key in .env (never prints the key)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai  # noqa: E402
from backend.config.settings import settings  # noqa: E402

client = genai.Client(api_key=settings.GEMINI_API_KEY)
wanted = ("flash", "tts", "live", "native-audio", "translate")
for m in client.models.list():
    name = m.name or ""
    actions = getattr(m, "supported_actions", None) or []
    if any(w in name for w in wanted):
        print(f"{name:70s} {','.join(actions)}")
