/**
 * Audio Worklet Processor source code as a string.
 * This runs on the browser's high-priority audio thread, converting 
 * Float32 microphone input directly to 16-bit Int16 PCM.
 * 
 * IMPORTANT: This worklet resamples audio to exactly 16kHz which Gemini Live requires.
 * It uses a simple linear interpolation resampler to handle any input sample rate.
 */
const workletCode = `
class AudioRecorderProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super(options);
    this._targetRate = 16000;
    this._inputRate = options.processorOptions?.inputSampleRate || 16000;
    this._ratio = this._inputRate / this._targetRate;
    this._position = 0.0;
    this._lastSample = 0.0;
    this._hasLastSample = false;
    
    // Buffer for ~100ms chunks (1600 samples at 16kHz = 3200 bytes)
    this._chunkSize = 1600;
    this._chunk = new Int16Array(this._chunkSize);
    this._chunkIdx = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      const inputLength = channelData.length;
      if (inputLength === 0) return true;

      let srcPos = this._position;
      while (srcPos < inputLength) {
        const srcIdx = Math.floor(srcPos);
        const frac = srcPos - srcIdx;
        const s0 = (srcIdx === 0 && this._hasLastSample) ? this._lastSample : (channelData[srcIdx] || 0.0);
        const s1 = (srcIdx + 1 < inputLength) ? channelData[srcIdx + 1] : channelData[srcIdx];
        const sample = s0 * (1.0 - frac) + s1 * frac;
        const clamped = Math.max(-1.0, Math.min(1.0, sample));
        
        this._chunk[this._chunkIdx++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF;
        if (this._chunkIdx >= this._chunkSize) {
          const bufferToSend = this._chunk.buffer.slice(0);
          this.port.postMessage(bufferToSend, [bufferToSend]);
          this._chunkIdx = 0;
        }
        srcPos += this._ratio;
      }

      this._position = srcPos - inputLength;
      this._lastSample = channelData[inputLength - 1];
      this._hasLastSample = true;
    }
    return true;
  }
}
registerProcessor('audio-recorder-processor', AudioRecorderProcessor);
`;

/**
 * Creates and returns a Blob URL containing the Audio Worklet Processor code.
 * This allows us to load the worklet dynamically in any browser.
 */
export function getAudioWorkletUrl(): string {
  const blob = new Blob([workletCode], { type: 'application/javascript' });
  return URL.createObjectURL(blob);
}

/**
 * Encodes 16-bit linear PCM audio into a standard WAV Blob (with 44-byte RIFF header).
 * Can be played by any standard HTML5 Audio element across all browsers.
 */
export function pcm16ToWavBlob(pcmInput: Int16Array | Int16Array[], sampleRate: number = 24000): Blob {
  let pcmData: Int16Array;
  if (Array.isArray(pcmInput)) {
    const totalLength = pcmInput.reduce((acc, chunk) => acc + chunk.length, 0);
    pcmData = new Int16Array(totalLength);
    let offset = 0;
    for (const chunk of pcmInput) {
      pcmData.set(chunk, offset);
      offset += chunk.length;
    }
  } else {
    pcmData = pcmInput;
  }

  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = pcmData.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  function writeString(offset: number, str: string) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  }

  // RIFF header
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');

  // fmt subchunk
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);

  // data subchunk
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  // Copy samples
  const pcmOutput = new Int16Array(buffer, 44, pcmData.length);
  pcmOutput.set(pcmData);

  return new Blob([buffer], { type: 'audio/wav' });
}
