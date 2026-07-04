import struct

# G.711 mu-law parameters
BIAS = 0x84
CLIP = 32635

def decode_ulaw_sample(u_val: int) -> int:
    """Converts a single 8-bit mu-law byte to a 16-bit signed PCM sample."""
    BIAS = 0x84
    u_val = ~u_val & 0xFF
    
    sign = u_val & 0x80
    exponent = (u_val >> 4) & 0x07
    mantissa = u_val & 0x0F
    
    sample = (mantissa << 3) + BIAS
    sample <<= exponent
    
    return -sample + BIAS if sign else sample - BIAS

def encode_ulaw_sample(pcm_val: int) -> int:
    """Converts a single 16-bit signed PCM sample to an 8-bit mu-law byte."""
    BIAS = 0x84
    CLIP = 32635
    
    # Clip value to valid range
    if pcm_val < -CLIP:
        pcm_val = -CLIP
    elif pcm_val > CLIP:
        pcm_val = CLIP
        
    sign = 0x80 if pcm_val < 0 else 0
    if sign:
        pcm_val = -pcm_val
        
    pcm_val += BIAS
    
    # Determine exponent
    exponent = 7
    temp = pcm_val << 1
    if temp >= 0x4000: exponent = 6
    elif temp >= 0x2000: exponent = 5
    elif temp >= 0x1000: exponent = 4
    elif temp >= 0x0800: exponent = 3
    elif temp >= 0x0400: exponent = 2
    elif temp >= 0x0200: exponent = 1
    elif temp >= 0x0100: exponent = 0
    
    mantissa = (pcm_val >> (exponent + 3)) & 0x0F
    ulaw = ~(sign | (exponent << 4) | mantissa)
    return ulaw & 0xFF

# Precompute lookup tables at startup for high-performance conversion
ULAW_TO_PCM = [decode_ulaw_sample(i) for i in range(256)]
PCM_TO_ULAW = [encode_ulaw_sample(i - 32768) for i in range(65536)]

def mulaw_to_pcm16_8k(mulaw_bytes: bytes) -> list[int]:
    """Converts G.711 mu-law 8kHz bytes to a list of signed 16-bit PCM samples."""
    return [ULAW_TO_PCM[b] for b in mulaw_bytes]

def resample_8k_to_16k(pcm_samples: list[int]) -> list[int]:
    """Resamples 16-bit linear PCM from 8kHz to 16kHz using linear interpolation."""
    out = []
    if not pcm_samples:
        return out
    for i in range(len(pcm_samples) - 1):
        s1 = pcm_samples[i]
        s2 = pcm_samples[i+1]
        out.append(s1)
        out.append((s1 + s2) // 2)
    # Handle the last sample
    out.append(pcm_samples[-1])
    out.append(pcm_samples[-1])
    return out

def pcm16_to_bytes(pcm_samples: list[int]) -> bytes:
    """Converts a list of signed 16-bit integers to little-endian bytes."""
    out_bytes = bytearray(len(pcm_samples) * 2)
    struct.pack_into(f'<{len(pcm_samples)}h', out_bytes, 0, *pcm_samples)
    return bytes(out_bytes)

def bytes_to_pcm16(pcm_bytes: bytes) -> list[int]:
    """Converts little-endian 16-bit PCM bytes to a list of signed 16-bit integers."""
    num_samples = len(pcm_bytes) // 2
    return list(struct.unpack(f'<{num_samples}h', pcm_bytes))

def resample_24k_to_8k(pcm_samples: list[int]) -> list[int]:
    """Downsamples 16-bit linear PCM from 24kHz to 8kHz by keeping every 3rd sample."""
    return pcm_samples[::3]

def resample_16k_to_8k(pcm_samples: list[int]) -> list[int]:
    """Downsamples 16-bit linear PCM from 16kHz to 8kHz by keeping every 2nd sample."""
    return pcm_samples[::2]

def pcm16_to_mulaw(pcm_samples: list[int]) -> bytes:
    """Converts a list of signed 16-bit integers to G.711 mu-law bytes."""
    return bytes(PCM_TO_ULAW[s + 32768] for s in pcm_samples)
