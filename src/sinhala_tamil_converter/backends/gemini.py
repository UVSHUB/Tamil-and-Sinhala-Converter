"""Google Gemini Live / GenAI Translation Backend."""

import os
from typing import Optional
from google import genai
from google.genai import types

from sinhala_tamil_converter.backends.base import BaseTranslationBackend
from sinhala_tamil_converter.exceptions import TranslationAPIError
from sinhala_tamil_converter.models import Language, TranslationResult


class GeminiTranslationBackend(BaseTranslationBackend):
    """Translation engine powered by Google GenAI."""

    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize the Gemini backend.

        Args:
            api_key: Optional Gemini API key. If not provided, it will be lazily loaded from
                     the `GEMINI_API_KEY` environment variable when translation is requested.
            model: Gemini model identifier (defaults to 'gemini-2.0-flash').
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize and return the Google GenAI client."""
        if self._client is None:
            resolved_key = self.api_key or os.environ.get("GEMINI_API_KEY")
            if not resolved_key:
                raise TranslationAPIError(
                    "Gemini API Key not found. Provide `api_key` or set the `GEMINI_API_KEY` environment variable."
                )
            self._client = genai.Client(api_key=resolved_key)
        return self._client

    def _build_prompt(self, text: str, source_lang: Language, target_lang: Language) -> str:
        return (
            f"You are a native professional translator between Sinhala and Tamil.\n"
            f"Translate the following {source_lang.value.title()} text into accurate, natural {target_lang.value.title()}.\n"
            f"Only return the raw translated text. Do not include notes, explanations, or transliteration brackets.\n\n"
            f"Input Text:\n{text}"
        )

    def translate(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        prompt = self._build_prompt(text, source_lang, target_lang)
        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            translated_text = (response.text or "").strip()
            return TranslationResult(
                text=translated_text,
                source_language=source_lang,
                target_language=target_lang,
            )
        except Exception as exc:
            if isinstance(exc, TranslationAPIError):
                raise
            raise TranslationAPIError(f"Gemini translation failed: {exc}") from exc

    async def translate_async(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        prompt = self._build_prompt(text, source_lang, target_lang)
        client = self._get_client()
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            translated_text = (response.text or "").strip()
            return TranslationResult(
                text=translated_text,
                source_language=source_lang,
                target_language=target_lang,
            )
        except Exception as exc:
            if isinstance(exc, TranslationAPIError):
                raise
            raise TranslationAPIError(f"Async Gemini translation failed: {exc}") from exc
