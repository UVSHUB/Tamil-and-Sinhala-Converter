"""Custom exceptions for the Sinhala-Tamil Converter package."""


class ConverterError(Exception):
    """Base exception for all converter-related errors."""

    pass


class InvalidInputError(ConverterError):
    """Raised when the provided input text is empty or invalid."""

    pass


class LanguageDetectionError(ConverterError):
    """Raised when the language cannot be reliably determined."""

    pass


class TranslationAPIError(ConverterError):
    """Raised when the underlying AI / translation engine fails."""

    pass
