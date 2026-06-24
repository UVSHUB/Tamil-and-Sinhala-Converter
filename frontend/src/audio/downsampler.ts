/**
 * Stateful Downsampler for Float32 Audio Streams.
 * Converts Float32 Audio Buffer chunks to 16kHz 16-bit Int16 PCM (Linear PCM).
 * This class maintains state across consecutive calls to prevent chunk-boundary clicks and timing drift.
 */
export class AudioDownsampler {
  private sampleRateRatio: number;
  private leftovers: Float32Array;
  private inputIdxFraction: number;

  constructor(inputSampleRate: number, outputSampleRate: number = 16000) {
    this.sampleRateRatio = inputSampleRate / outputSampleRate;
    this.leftovers = new Float32Array(0);
    this.inputIdxFraction = 0.0;
  }

  /**
   * Resets the internal downsampler state (buffers and fractional index pointers).
   */
  public reset(): void {
    this.leftovers = new Float32Array(0);
    this.inputIdxFraction = 0.0;
  }

  /**
   * Processes a chunk of float32 samples.
   * Dynamically downmixes stereo/multi-channel to mono (if input buffer is interleaved)
   * and downsamples to raw 16-bit PCM.
   */
  public process(inputBuffer: Float32Array, numChannels: number = 1): Int16Array {
    // 1. If multi-channel interleaved, downmix to mono
    let monoBuffer: Float32Array;
    if (numChannels > 1) {
      const length = inputBuffer.length / numChannels;
      monoBuffer = new Float32Array(length);
      for (let i = 0; i < length; i++) {
        let sum = 0;
        for (let ch = 0; ch < numChannels; ch++) {
          sum += inputBuffer[i * numChannels + ch];
        }
        monoBuffer[i] = sum / numChannels;
      }
    } else {
      monoBuffer = inputBuffer;
    }

    // 2. Concatenate leftovers from the previous chunk
    let combined: Float32Array;
    if (this.leftovers.length > 0) {
      combined = new Float32Array(this.leftovers.length + monoBuffer.length);
      combined.set(this.leftovers, 0);
      combined.set(monoBuffer, this.leftovers.length);
    } else {
      combined = monoBuffer;
    }

    const ratio = this.sampleRateRatio;
    const availableInputLength = combined.length;
    let inputIdx = this.inputIdxFraction;

    // Calculate maximum output samples we can extract
    const outputSamplesCount = Math.floor((availableInputLength - inputIdx) / ratio);
    if (outputSamplesCount <= 0) {
      // Keep everything in leftovers
      this.leftovers = combined;
      this.inputIdxFraction = inputIdx;
      return new Int16Array(0);
    }

    const outputBuffer = new Int16Array(outputSamplesCount);
    let outputIdx = 0;

    // Downsample using window averaging
    while (outputIdx < outputSamplesCount) {
      const start = inputIdx;
      const end = inputIdx + ratio;
      const startInt = Math.floor(start);
      const endInt = Math.floor(end);

      let sum = 0;
      let count = 0;

      for (let i = startInt; i < endInt && i < availableInputLength; i++) {
        sum += combined[i];
        count++;
      }

      const sample = count > 0 ? sum / count : 0.0;
      // Clamp float sample value to [-1.0, 1.0] and convert to 16-bit signed integer (little-endian representation)
      outputBuffer[outputIdx] = Math.min(1.0, Math.max(-1.0, sample)) * 0x7FFF;

      outputIdx++;
      inputIdx = end;
    }

    // 3. Slice leftovers and save the fractional index position
    const leftoverStartInt = Math.floor(inputIdx);
    this.leftovers = combined.slice(leftoverStartInt);
    this.inputIdxFraction = inputIdx - leftoverStartInt;

    return outputBuffer;
  }
}

/**
 * Legacy utility: Downsamples a single Float32 Audio Buffer to 16kHz 16-bit Int16 PCM.
 * Useful for single-shot, non-streaming conversion.
 */
export function downsampleBuffer(
  buffer: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number = 16000
): Int16Array {
  const downsampler = new AudioDownsampler(inputSampleRate, outputSampleRate);
  return downsampler.process(buffer);
}
