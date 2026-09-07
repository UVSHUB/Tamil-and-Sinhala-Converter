"""Primary SinhalaTamilConverter class implementation."""

import asyncio
import re
from typing import List, Optional, Union

from sinhala_tamil_converter.backends.base import BaseTranslationBackend
from sinhala_tamil_converter.backends.gemini import GeminiTranslationBackend
from sinhala_tamil_converter.exceptions import InvalidInputError, LanguageDetectionError
from sinhala_tamil_converter.models import Language, TranslationResult


class SinhalaTamilConverter:
    """Core converter class providing bidirectional translation between Sinhala and Tamil.

    Attributes:
        backend (BaseTranslationBackend): The translation backend used for inference.
    """

    # Unicode ranges for script detection:
    # Sinhala: U+0D80 to U+0DFF
    # Tamil:   U+0B80 to U+0BFF
    _SINHALA_REGEX = re.compile(r"[\u0D80-\u0DFF]")
    _TAMIL_REGEX = re.compile(r"[\u0B80-\u0BFF]")

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        backend: Optional[BaseTranslationBackend] = None,
    ) -> None:
        """Initialize the converter.

        Args:
            api_key: Optional Gemini API key. If None, lazily reads from `GEMINI_API_KEY` env var.
            model: Model name to use for conversion (defaults to 'gemini-2.0-flash').
            backend: Custom backend instance adhering to `BaseTranslationBackend`.
        """
        self.backend = backend or GeminiTranslationBackend(api_key=api_key, model=model)

    @classmethod
    def detect_language(cls, text: str) -> Language:
        """Detect whether the provided string is primarily Sinhala or Tamil script.

        Args:
            text: Input string.

        Returns:
            Language: Detected `Language.SINHALA` or `Language.TAMIL`.

        Raises:
            InvalidInputError: If text is empty or only whitespace.
            LanguageDetectionError: If neither Sinhala nor Tamil script is detected.
        """
        if not text or not text.strip():
            raise InvalidInputError("Cannot detect language of empty or whitespace text.")

        sinhala_count = len(cls._SINHALA_REGEX.findall(text))
        tamil_count = len(cls._TAMIL_REGEX.findall(text))

        if sinhala_count == 0 and tamil_count == 0:
            raise LanguageDetectionError("Unable to detect Sinhala or Tamil script in input text.")

        return Language.SINHALA if sinhala_count >= tamil_count else Language.TAMIL

    def _resolve_languages(
        self,
        text: str,
        source: Union[str, Language] = "auto",
        target: Optional[Union[str, Language]] = None,
    ) -> tuple[Language, Language]:
        """Resolve and validate source and target languages."""
        if isinstance(source, str) and source.lower() == "auto":
            source_lang = self.detect_language(text)
        elif isinstance(source, str):
            source_lang = Language(source.lower())
        else:
            source_lang = source

        if target is None:
            target_lang = Language.TAMIL if source_lang == Language.SINHALA else Language.SINHALA
        elif isinstance(target, str):
            target_lang = Language(target.lower())
        else:
            target_lang = target

        return source_lang, target_lang

    def translate(
        self,
        text: str,
        source: Union[str, Language] = "auto",
        target: Optional[Union[str, Language]] = None,
        temperature: float = 0.2,
    ) -> TranslationResult:
        """Translate text between Sinhala and Tamil synchronously.

        Args:
            text: Text to be translated.
            source: Source language ('sinhala', 'tamil', or 'auto'). Defaults to 'auto'.
            target: Target language ('sinhala' or 'tamil'). Defaults to opposite of source.
            temperature: Sampling temperature for AI generation (default: 0.2).

        Returns:
            TranslationResult: Result containing translated text and metadata.

        Raises:
            InvalidInputError: If text is empty or invalid.
            TranslationAPIError: If translation engine encounters an error.
        """
        if not text or not text.strip():
            raise InvalidInputError("Input text cannot be empty.")

        source_lang, target_lang = self._resolve_languages(text, source, target)

        if source_lang == target_lang:
            return TranslationResult(
                text=text.strip(),
                source_language=source_lang,
                target_language=target_lang,
            )

        return self.backend.translate(
            text=text.strip(),
            source_lang=source_lang,
            target_lang=target_lang,
            temperature=temperature,
        )

    async def translate_async(
        self,
        text: str,
        source: Union[str, Language] = "auto",
        target: Optional[Union[str, Language]] = None,
        temperature: float = 0.2,
    ) -> TranslationResult:
        """Translate text between Sinhala and Tamil asynchronously.

        Args:
            text: Text to be translated.
            source: Source language ('sinhala', 'tamil', or 'auto'). Defaults to 'auto'.
            target: Target language ('sinhala' or 'tamil'). Defaults to opposite of source.
            temperature: Sampling temperature for AI generation (default: 0.2).

        Returns:
            TranslationResult: Result containing translated text and metadata.

        Raises:
            InvalidInputError: If text is empty or invalid.
            TranslationAPIError: If translation engine encounters an error.
        """
        if not text or not text.strip():
            raise InvalidInputError("Input text cannot be empty.")

        source_lang, target_lang = self._resolve_languages(text, source, target)

        if source_lang == target_lang:
            return TranslationResult(
                text=text.strip(),
                source_language=source_lang,
                target_language=target_lang,
            )

        return await self.backend.translate_async(
            text=text.strip(),
            source_lang=source_lang,
            target_lang=target_lang,
            temperature=temperature,
        )

    def batch_translate(
        self,
        texts: List[str],
        source: Union[str, Language] = "auto",
        target: Optional[Union[str, Language]] = None,
        temperature: float = 0.2,
    ) -> List[TranslationResult]:
        """Translate a batch of strings synchronously.

        Args:
            texts: List of strings to translate.
            source: Source language ('sinhala', 'tamil', or 'auto').
            target: Target language ('sinhala' or 'tamil').
            temperature: Sampling temperature for generation.

        Returns:
            List[TranslationResult]: Translated results in corresponding order.
        """
        return [
            self.translate(t, source=source, target=target, temperature=temperature)
            for t in texts
        ]

    async def batch_translate_async(
        self,
        texts: List[str],
        source: Union[str, Language] = "auto",
        target: Optional[Union[str, Language]] = None,
        temperature: float = 0.2,
    ) -> List[TranslationResult]:
        """Translate a batch of strings asynchronously concurrently.

        Args:
            texts: List of strings to translate.
            source: Source language ('sinhala', 'tamil', or 'auto').
            target: Target language ('sinhala' or 'tamil').
            temperature: Sampling temperature for generation.

        Returns:
            List[TranslationResult]: Translated results in corresponding order.
        """
        tasks = [
            self.translate_async(t, source=source, target=target, temperature=temperature)
            for t in texts
        ]
        return await asyncio.gather(*tasks)
