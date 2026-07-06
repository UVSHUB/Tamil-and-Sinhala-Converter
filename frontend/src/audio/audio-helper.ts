/**
 * Audio Worklet Processor source code as a string.
 * Runs on the browser's high-priority audio thread.
 * Buffers microphone audio to 100ms chunks (1600 samples at 16kHz)
 * for optimal speech recognition and activity detection in Gemini Live.
 */
const workletCode = `
class AudioRecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options);
    this._targetRate = 16000;
    this._inputRate = options.processorOptions?.inputSampleRate || 16000;
    this._ratio = this._inputRate / this._targetRate;
    this._accumulated = [];
    this._flushSize = 1600; // 100ms buffer at 16kHz
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0]; // Mono channel 0
      
      let resampled;
      if (Math.abs(this._ratio - 1.0) < 0.001) {
        const length = channelData.length;
        resampled = new Int16Array(length);
        for (let i = 0; i < length; i++) {
          const sample = Math.max(-1.0, Math.min(1.0, channelData[i]));
          resampled[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        }
      } else {
        const inputLength = channelData.length;
        const outputLength = Math.floor(inputLength / this._ratio);
        resampled = new Int16Array(outputLength);
        for (let i = 0; i < outputLength; i++) {
          const srcPos = i * this._ratio;
          const srcIdx = Math.floor(srcPos);
          const frac = srcPos - srcIdx;
          
          let sample;
          if (srcIdx + 1 < inputLength) {
            sample = channelData[srcIdx] * (1 - frac) + channelData[srcIdx + 1] * frac;
          } else {
            sample = channelData[srcIdx] || 0;
          }
          
          sample = Math.max(-1.0, Math.min(1.0, sample));
          resampled[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        }
      }
      
      // Accumulate resampled samples
      for (let i = 0; i < resampled.length; i++) {
        this._accumulated.push(resampled[i]);
      }
      
      // Flush in 100ms chunks (1600 samples)
      while (this._accumulated.length >= this._flushSize) {
        const chunk = new Int16Array(this._flushSize);
        for (let i = 0; i < this._flushSize; i++) {
          chunk[i] = this._accumulated[i];
        }
        this._accumulated = this._accumulated.slice(this._flushSize);
        this.port.postMessage(chunk.buffer, [chunk.buffer]);
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
