"""Unit tests for the live interpreter engine's pure helper functions (no network)."""

from backend.websocket.live_interpreter_handler import (
    build_config,
    build_instruction,
    detect_language,
    is_silent,
    normalize_target,
)


def test_detect_language_scripts():
    assert detect_language("මට ක්‍රෙඩිට් කාඩ් බිල්පත ගැන දැනගන්න ඕනේ") == "Sinhala"
    assert detect_language("எனக்கு கிரெடிட் கார்டு பில் பற்றி தெரிய வேண்டும்") == "Tamil"
    assert detect_language("I want to check my balance") == "English"
    assert detect_language("12345 ...") is None


def test_detect_language_mixed_speech():
    # Singlish / Tanglish: native script wins over a few English words
    assert detect_language("මට credit card bill එක check කරන්න ඕනේ") == "Sinhala"
    assert detect_language("எனக்கு credit card bill balance பார்க்கணும்") == "Tamil"


def test_normalize_target():
    assert normalize_target("Sinhala") == "Sinhala"
    assert normalize_target("sinhala") == "Sinhala"
    assert normalize_target("Tamil") == "Tamil"
    assert normalize_target("") == "Tamil"


def test_instruction_is_interpreter_only():
    text = build_instruction("Tamil")
    assert "into Tamil" in text
    assert "never answer questions" in text.lower()
    assert "Recent conversation" not in text


def test_instruction_includes_recent_history():
    history = [{"speaker": "speaker", "text": f"line {i}"} for i in range(20)]
    text = build_instruction("Sinhala", history)
    assert "Recent conversation" in text
    assert "line 19" in text
    assert "line 0" not in text  # only the most recent turns are kept


def test_build_config_simultaneous():
    config = build_config("Sinhala", "Charon", engine="simultaneous")
    assert config.response_modalities == ["AUDIO"]
    assert config.translation_config.target_language_code == "si"
    assert config.translation_config.echo_target_language is False  # no echo loop
    assert config.system_instruction is None
    assert config.input_audio_transcription is not None
    assert config.output_audio_transcription is not None


def test_build_config_turn_based():
    config = build_config("Sinhala", "Charon", engine="live")
    assert config.translation_config is None
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Charon"
    assert "into Sinhala" in config.system_instruction.parts[0].text


def test_is_silent():
    assert is_silent(bytes(4800))
    assert is_silent(b"")
    loud = (8000).to_bytes(2, "little", signed=True) * 100
    assert not is_silent(loud)
