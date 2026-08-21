"""Sinhala and Tamil Conversion & Translation Library.

Exported Convenience Functions:
- `translate_sinhala_to_tamil(text: str) -> str`
- `translate_tamil_to_sinhala(text: str) -> str`
- `auto_translate(text: str) -> TranslationResult`
- `detect_language(text: str) -> Language`

Core Classes:
- `SinhalaTamilConverter`
- `Language`
- `TranslationResult`
"""

from typing import Optional
from sinhala_tamil_converter.converter import SinhalaTamilConverter
from sinhala_tamil_converter.exceptions import (
    ConverterError,
    InvalidInputError,
    LanguageDetectionError,
    TranslationAPIError,
)
from sinhala_tamil_converter.models import Language, TranslationResult

__version__ = "1.0.0"

_default_converter: Optional[SinhalaTamilConverter] = None


def _get_converter() -> SinhalaTamilConverter:
    """Retrieve or lazily initialize the default singleton converter instance."""
    global _default_converter
    if _default_converter is None:
        _default_converter = SinhalaTamilConverter()
    return _default_converter


def translate_sinhala_to_tamil(text: str) -> str:
    """Translate Sinhala text into Tamil.

    Args:
        text (str): Sinhala input string.

    Returns:
        str: Tamil translated string.

    Example:
        >>> from sinhala_tamil_converter import translate_sinhala_to_tamil
        >>> translate_sinhala_to_tamil("ආයුබෝවන්")
        'வணக்கம்'
    """
    return _get_converter().translate(text, source=Language.SINHALA, target=Language.TAMIL).text


def translate_tamil_to_sinhala(text: str) -> str:
    """Translate Tamil text into Sinhala.

    Args:
        text (str): Tamil input string.

    Returns:
        str: Sinhala translated string.

    Example:
        >>> from sinhala_tamil_converter import translate_tamil_to_sinhala
        >>> translate_tamil_to_sinhala("வணக்கம்")
        'ආයුබෝවන්'
    """
    return _get_converter().translate(text, source=Language.TAMIL, target=Language.SINHALA).text


def auto_translate(text: str) -> TranslationResult:
    """Auto-detect language (Sinhala or Tamil) and translate to the opposite language.

    Args:
        text (str): Input string in either Sinhala or Tamil.

    Returns:
        TranslationResult: Container with `.text`, `.source_language`, and `.target_language`.

    Example:
        >>> from sinhala_tamil_converter import auto_translate
        >>> res = auto_translate("සුභ උදෑසනක්")
        >>> print(res.text)
    """
    return _get_converter().translate(text, source="auto")


def detect_language(text: str) -> Language:
    """Identify if the text is Sinhala or Tamil script.

    Args:
        text (str): Text string.

    Returns:
        Language: `Language.SINHALA` or `Language.TAMIL`.
    """
    return SinhalaTamilConverter.detect_language(text)


__all__ = [
    "SinhalaTamilConverter",
    "Language",
    "TranslationResult",
    "ConverterError",
    "InvalidInputError",
    "LanguageDetectionError",
    "TranslationAPIError",
    "translate_sinhala_to_tamil",
    "translate_tamil_to_sinhala",
    "auto_translate",
    "detect_language",
    "__version__",
]
