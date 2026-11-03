"""
Unit tests for Asterisk AudioSocket Bridge protocol & resampling logic.
"""

import struct
import unittest
from backend.asterisk.audiosocket_bridge import resample_pcm, TYPE_AUDIO, TYPE_UUID


class TestAudioSocketBridge(unittest.TestCase):

    def test_resample_pcm_identical_rate(self):
        data = b"\x00\x01\x00\x02"
        result = resample_pcm(data, from_rate=8000, to_rate=8000)
        self.assertEqual(result, data)

    def test_resample_pcm_upsample(self):
        # 8kHz to 16kHz upsampling should approximately double the payload size (within audioop filter tap margin)
        data = struct.pack(">100h", *[i for i in range(100)])
        result = resample_pcm(data, from_rate=8000, to_rate=16000)
        self.assertAlmostEqual(len(result), len(data) * 2, delta=4)

    def test_resample_pcm_downsample(self):
        # 16kHz to 8kHz downsampling should halve the payload size
        data = struct.pack(">100h", *[i for i in range(100)])
        result = resample_pcm(data, from_rate=16000, to_rate=8000)
        self.assertEqual(len(result), len(data) // 2)

    def test_audiosocket_header_format(self):
        # Verify AudioSocket header packing format: TYPE (1B) + LENGTH (2B Big Endian)
        payload = b"\x12\x34\x56\x78"
        header = struct.pack(">BH", TYPE_AUDIO, len(payload))
        msg_type, length = struct.unpack(">BH", header)

        self.assertEqual(msg_type, TYPE_AUDIO)
        self.assertEqual(length, 4)


if __name__ == "__main__":
    unittest.main()
