"""Data models and Enums used across the conversion package."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Language(str, Enum):
    """Supported language codes."""

    SINHALA = "sinhala"
    TAMIL = "tamil"
    UNKNOWN = "unknown"


class TranslationResult(BaseModel):
    """Structured response container for a translation request."""

    text: str = Field(description="The translated output string.")
    source_language: Language = Field(description="The identified or supplied source language.")
    target_language: Language = Field(description="The requested target language.")
    confidence: Optional[float] = Field(default=1.0, description="Confidence score between 0.0 and 1.0.")

    def __str__(self) -> str:
        return self.text
