import pytest
from backend.audio.twilio_audio import (
    mulaw_to_pcm16_8k,
    resample_8k_to_16k,
    pcm16_to_bytes,
    bytes_to_pcm16,
    resample_24k_to_8k,
    pcm16_to_mulaw
)

def test_mulaw_pcm_roundtrip():
    # Test a few representative sample values
    test_samples = [0, 100, -100, 1000, -1000, 5000, -5000]
    
    # Convert PCM to mu-law bytes
    mulaw_bytes = pcm16_to_mulaw(test_samples)
    assert len(mulaw_bytes) == len(test_samples)
    
    # Convert mu-law bytes back to PCM
    decoded_samples = mulaw_to_pcm16_8k(mulaw_bytes)
    assert len(decoded_samples) == len(test_samples)
    
    # G.711 is a lossy companding format, so there will be some quantization error.
    # We verify that the decoded values are close to the original values.
    for orig, dec in zip(test_samples, decoded_samples):
        assert abs(orig - dec) < 150  # Dynamic range tolerance for low resolution G.711

def test_resampling_8k_to_16k():
    samples_8k = [10, 20, 30]
    samples_16k = resample_8k_to_16k(samples_8k)
    
    # Length should be exactly doubled
    assert len(samples_16k) == 6
    
    # Checks linear interpolation: (10 + 20) // 2 = 15, etc.
    assert samples_16k == [10, 15, 20, 25, 30, 30]

def test_resampling_24k_to_8k():
    samples_24k = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    samples_8k = resample_24k_to_8k(samples_24k)
    
    # Should take every 3rd sample
    assert samples_8k == [1, 4, 7]

def test_pcm16_bytes_conversion():
    pcm_samples = [123, -456, 789]
    pcm_bytes = pcm16_to_bytes(pcm_samples)
    
    # 3 samples of 16-bit (2 bytes each) = 6 bytes
    assert len(pcm_bytes) == 6
    
    decoded_samples = bytes_to_pcm16(pcm_bytes)
    assert decoded_samples == pcm_samples
