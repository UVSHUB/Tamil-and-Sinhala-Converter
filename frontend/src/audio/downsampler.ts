/**
 * Downsamples Float32 Audio Buffer to 16kHz 16-bit Int16 PCM (Linear PCM).
 * This format is optimal and required for low-latency speech-to-text models like Gemini Live API.
 */
export function downsampleBuffer(
  buffer: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number = 16000
): Int16Array {
  if (inputSampleRate === outputSampleRate) {
    return convertFloat32ToInt16(buffer);
  }

  const sampleRateRatio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(buffer.length / sampleRateRatio);
  const result = new Int16Array(newLength);
  
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio);
    let accum = 0;
    let count = 0;

    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      accum += buffer[i];
      count++;
    }

    const sample = count > 0 ? accum / count : 0;
    // Clamp sample float limits to [-1.0, 1.0] and map to signed 16-bit integers
    result[offsetResult] = Math.min(1, Math.max(-1, sample)) * 0x7FFF;
    
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }

  return result;
}

/**
 * Direct mapping converter helper when sample rates align.
 */
function convertFloat32ToInt16(buffer: Float32Array): Int16Array {
  const length = buffer.length;
  const int16Buffer = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    int16Buffer[i] = Math.min(1, Math.max(-1, buffer[i])) * 0x7FFF;
  }
  return int16Buffer;
}
