import unittest
from backend.websocket.auto_stream_handler import _detect_language, _make_config, _build_companion_instruction

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

if __name__ == "__main__":
    unittest.main()
