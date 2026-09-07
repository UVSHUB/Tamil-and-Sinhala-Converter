"""Unit tests for Sinhala-Tamil converter package."""

import pytest
from backend.websocket.auto_stream_handler import _build_companion_instruction
from sinhala_tamil_converter import (
    Language,
    SinhalaTamilConverter,
    TranslationResult,
    auto_translate,
    detect_language,
)
from sinhala_tamil_converter.backends.base import BaseTranslationBackend
from sinhala_tamil_converter.exceptions import (
    InvalidInputError,
    LanguageDetectionError,
    TranslationAPIError,
)


class MockTranslationBackend(BaseTranslationBackend):
    """Mock backend for deterministic offline unit testing."""

    def translate(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        if "FAIL" in text:
            raise TranslationAPIError("Simulated API failure")
        # Simple deterministic transformation for mock test
        translated = f"MOCK_{target_lang.value.upper()}_{text}"
        return TranslationResult(
            text=translated,
            source_language=source_lang,
            target_language=target_lang,
            confidence=0.99,
        )

    async def translate_async(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        return self.translate(text, source_lang, target_lang, temperature)


@pytest.fixture
def mock_converter():
    backend = MockTranslationBackend()
    return SinhalaTamilConverter(backend=backend)


def test_detect_language(mock_converter):
    sinhala_text = "ආයුබෝවන්"
    tamil_text = "வணக்கம்"

    assert mock_converter.detect_language(sinhala_text) == Language.SINHALA
    assert mock_converter.detect_language(tamil_text) == Language.TAMIL


def test_detect_language_errors(mock_converter):
    with pytest.raises(InvalidInputError):
        mock_converter.detect_language("")

    with pytest.raises(InvalidInputError):
        mock_converter.detect_language("   ")

    with pytest.raises(LanguageDetectionError):
        mock_converter.detect_language("Hello World! 12345")


def test_translate_sync(mock_converter):
    res = mock_converter.translate("ආයුබෝවන්", source="sinhala", target="tamil")
    assert res.text == "MOCK_TAMIL_ආයුබෝවන්"
    assert res.source_language == Language.SINHALA
    assert res.target_language == Language.TAMIL


def test_translate_auto_detection(mock_converter):
    res = mock_converter.translate("ආයුබෝවන්")  # Auto source -> Sinhala, Auto target -> Tamil
    assert res.source_language == Language.SINHALA
    assert res.target_language == Language.TAMIL
    assert res.text == "MOCK_TAMIL_ආයුබෝවන්"

    res2 = mock_converter.translate("வணக்கம்")  # Auto source -> Tamil, Auto target -> Sinhala
    assert res2.source_language == Language.TAMIL
    assert res2.target_language == Language.SINHALA
    assert res2.text == "MOCK_SINHALA_வணக்கம்"


def test_translate_same_language(mock_converter):
    res = mock_converter.translate("ආයුබෝවන්", source=Language.SINHALA, target=Language.SINHALA)
    assert res.text == "ආයුබෝවන්"
    assert res.source_language == Language.SINHALA
    assert res.target_language == Language.SINHALA


def test_translate_empty_error(mock_converter):
    with pytest.raises(InvalidInputError):
        mock_converter.translate("")


def test_translate_failure(mock_converter):
    with pytest.raises(TranslationAPIError):
        mock_converter.translate("FAIL text", source="sinhala", target="tamil")


def test_build_companion_instruction():
    history = [
        {"speaker": "user", "text": "සුභ උදෑසනක්"},
        {"speaker": "ai", "text": "காலை வணக்கம்"},
    ]
    prompt = _build_companion_instruction("Sinhala", "Tamil", history)

    assert "translation engine" in prompt.lower()
    assert "output only the translated text in tamil" in prompt.lower()
    assert "do not translate into any other language" in prompt.lower()
    assert "context" in prompt.lower()
    assert "සුභ උදෑසනක්" in prompt


@pytest.mark.asyncio
async def test_translate_async(mock_converter):
    res = await mock_converter.translate_async("ආයුබෝවන්", source="sinhala", target="tamil")
    assert res.text == "MOCK_TAMIL_ආයුබෝවන්"


def test_batch_translate(mock_converter):
    texts = ["ආයුබෝවන්", "ස්තූතියි"]
    results = mock_converter.batch_translate(texts, source="sinhala", target="tamil")
    assert len(results) == 2
    assert results[0].text == "MOCK_TAMIL_ආයුබෝවන්"
    assert results[1].text == "MOCK_TAMIL_ස්තූතියි"


@pytest.mark.asyncio
async def test_batch_translate_async(mock_converter):
    texts = ["ආයුබෝවන්", "ස්තූතියි"]
    results = await mock_converter.batch_translate_async(texts, source="sinhala", target="tamil")
    assert len(results) == 2
    assert results[0].text == "MOCK_TAMIL_ආයුබෝවන්"
    assert results[1].text == "MOCK_TAMIL_ස්තූතියි"
