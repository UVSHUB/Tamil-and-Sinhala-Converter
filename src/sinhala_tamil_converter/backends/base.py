"""Abstract base class for conversion backends."""

from abc import ABC, abstractmethod
from sinhala_tamil_converter.models import Language, TranslationResult


class BaseTranslationBackend(ABC):
    """Abstract interface for translation service providers."""

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        """Translate text synchronously.

        Args:
            text: The text to translate.
            source_lang: Source language enum.
            target_lang: Target language enum.
            temperature: Sampling temperature for AI model inference.

        Returns:
            TranslationResult containing translated text and metadata.
        """
        pass

    @abstractmethod
    async def translate_async(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        """Translate text asynchronously.

        Args:
            text: The text to translate.
            source_lang: Source language enum.
            target_lang: Target language enum.
            temperature: Sampling temperature for AI model inference.

        Returns:
            TranslationResult containing translated text and metadata.
        """
        pass
