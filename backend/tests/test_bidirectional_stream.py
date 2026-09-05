import unittest
from backend.websocket.auto_stream_handler import (
    _detect_language,
    _make_config,
    _build_companion_instruction,
    _build_live_interpreter_instruction,
    _make_live_interpreter_config,
)

class TestBidirectionalAutoStream(unittest.TestCase):
    def test_detect_sinhala(self):
        text = "මට මේ බිල්පත ගැන විස්තර දැනගන්න පුළුවන්ද?"
        lang = _detect_language(text)
        self.assertEqual(lang, "Sinhala")

    def test_detect_tamil(self):
        text = "இந்த பில் பற்றிய விவரங்களை நான் தெரிந்து கொள்ளலாமா?"
        lang = _detect_language(text)
        self.assertEqual(lang, "Tamil")

    def test_detect_singlish(self):
        # Sinhala with English loanwords
        text = "මට credit card bill එක check කරන්න පුළුවන්ද?"
        lang = _detect_language(text)
        self.assertEqual(lang, "Sinhala")

    def test_detect_tanglish(self):
        # Tamil with English loanwords
        text = "எனக்கு credit card bill balance பார்க்க முடியுமா?"
        lang = _detect_language(text)
        self.assertEqual(lang, "Tamil")

    def test_make_config_tamil_target(self):
        config = _make_config("ta")
        self.assertEqual(config.translation_config.target_language_code, "ta")
        instr = config.system_instruction.parts[0].text
        self.assertIn("Sinhala", instr)
        self.assertIn("Tamil", instr)

    def test_make_config_sinhala_target(self):
        config = _make_config("si")
        self.assertEqual(config.translation_config.target_language_code, "si")
        instr = config.system_instruction.parts[0].text
        self.assertIn("Tamil", instr)
        self.assertIn("Sinhala", instr)

    def test_make_live_interpreter_config(self):
        config = _make_live_interpreter_config(voice="Aoede")
        self.assertEqual(config.response_modalities, ["AUDIO"])
        self.assertEqual(config.speech_config.voice_config.prebuilt_voice_config.voice_name, "Aoede")
        self.assertEqual(config.realtime_input_config.automatic_activity_detection.silence_duration_ms, 150)
        instr = config.system_instruction.parts[0].text
        self.assertIn("Sinhala", instr)
        self.assertIn("Tamil", instr)
        self.assertIn("Singlish", instr)
        self.assertIn("Tanglish", instr)

    def test_live_interpreter_instruction_history(self):
        history = [
            {"speaker": "user", "text": "Hello"},
            {"speaker": "ai", "text": "Vanakkam"},
        ]
        instr = _build_live_interpreter_instruction(history)
        self.assertIn("Recent conversation context:", instr)
        self.assertIn("Vanakkam", instr)

if __name__ == "__main__":
    unittest.main()

