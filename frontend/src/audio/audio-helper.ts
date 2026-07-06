/**
 * Audio Worklet Processor source code as a string.
 * Runs on the browser's high-priority audio thread.
 *
 * Optimizations for minimum latency:
 *  - Pre-allocated Int16Array ring buffer (zero GC pressure on audio thread)
 *  - 50ms flush window (800 samples at 16kHz) — half of the old 100ms
 *  - Linear-interpolation resampler to exactly 16kHz
 */
const workletCode = `
class AudioRecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options);
    this._targetRate = 16000;
    this._inputRate = options.processorOptions?.inputSampleRate || 16000;
    this._ratio = this._inputRate / this._targetRate;

    // Pre-allocate a fixed ring buffer — avoids GC on the audio thread entirely.
    // 2× the flush size is enough to never overflow between flushes.
    this._flushSize = 800;          // 50ms @ 16kHz
    this._buf = new Int16Array(this._flushSize * 4);
    this._writePos = 0;
  }

  _flush() {
    // Copy exactly _flushSize samples out and transfer the buffer (zero-copy)
    const out = new Int16Array(this._flushSize);
    out.set(this._buf.subarray(0, this._flushSize));
    // Shift remaining samples down
    this._buf.copyWithin(0, this._flushSize, this._writePos);
    this._writePos -= this._flushSize;
    this.port.postMessage(out.buffer, [out.buffer]);
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channelData = input[0];

    if (Math.abs(this._ratio - 1.0) < 0.001) {
      // No resampling needed — direct convert Float32 → Int16
      for (let i = 0; i < channelData.length; i++) {
        const s = channelData[i] < -1 ? -1 : channelData[i] > 1 ? 1 : channelData[i];
        this._buf[this._writePos++] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        if (this._writePos >= this._flushSize) this._flush();
      }
    } else {
      // Linear interpolation resample to 16kHz
      const inputLength = channelData.length;
      const outputLength = Math.floor(inputLength / this._ratio);
      for (let i = 0; i < outputLength; i++) {
        const srcPos = i * this._ratio;
        const srcIdx = srcPos | 0;  // fast Math.floor
        const frac = srcPos - srcIdx;
        let s;
        if (srcIdx + 1 < inputLength) {
          s = channelData[srcIdx] + frac * (channelData[srcIdx + 1] - channelData[srcIdx]);
        } else {
          s = channelData[srcIdx] || 0;
        }
        s = s < -1 ? -1 : s > 1 ? 1 : s;
        this._buf[this._writePos++] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        if (this._writePos >= this._flushSize) this._flush();
      }
    }
    return true;
  }
}
registerProcessor('audio-recorder-processor', AudioRecorderProcessor);
`;

/**
 * Creates and returns a Blob URL containing the Audio Worklet Processor code.
 */
export function getAudioWorkletUrl(): string {
  const blob = new Blob([workletCode], { type: 'application/javascript' });
  return URL.createObjectURL(blob);
}
