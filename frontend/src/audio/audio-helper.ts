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
    // Target sample rate is always 16000 for Gemini Live API
    this._targetRate = 16000;
    this._inputRate = options.processorOptions?.inputSampleRate || 16000;
    this._buffer = [];
    // Resample ratio: how many input samples per 1 output sample
    this._ratio = this._inputRate / this._targetRate;
    this._position = 0;
    this._hangover = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0]; // Mono channel 0
      
      // WebRTC DSP Preprocessor (Noise Gate)
      // Calculate Root Mean Square (RMS) volume
      let sumSquares = 0;
      for (let i = 0; i < channelData.length; i++) {
        sumSquares += channelData[i] * channelData[i];
      }
      const rms = Math.sqrt(sumSquares / channelData.length);
      
      // If volume is below threshold (ambient noise), stop sending packets
      // INCREASED from 0.005 to 0.025 to block loud background chatter
      if (rms < 0.025) {
        if (this._hangover > 0) {
          this._hangover--;
        } else {
          return true; // Drop packet, don't send to WebSocket
        }
      } else {
        this._hangover = 20; // Keep sending for ~20 frames after speech ends (hangover)
      }
      
      // If sample rate matches target, convert directly
      if (Math.abs(this._ratio - 1.0) < 0.001) {
        const length = channelData.length;
        const pcmBuffer = new Int16Array(length);
        for (let i = 0; i < length; i++) {
          const sample = Math.max(-1.0, Math.min(1.0, channelData[i]));
          pcmBuffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        }
        this.port.postMessage(pcmBuffer.buffer, [pcmBuffer.buffer]);
      } else {
        // Linear interpolation resampling to 16kHz
        const inputLength = channelData.length;
        const outputLength = Math.floor(inputLength / this._ratio);
        const pcmBuffer = new Int16Array(outputLength);
        
        for (let i = 0; i < outputLength; i++) {
          const srcPos = i * this._ratio;
          const srcIdx = Math.floor(srcPos);
          const frac = srcPos - srcIdx;
          
          let sample;
          if (srcIdx + 1 < inputLength) {
            // Linear interpolation between adjacent samples
            sample = channelData[srcIdx] * (1 - frac) + channelData[srcIdx + 1] * frac;
          } else {
            sample = channelData[srcIdx] || 0;
          }
          
          sample = Math.max(-1.0, Math.min(1.0, sample));
          pcmBuffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        }
        
        if (outputLength > 0) {
          this.port.postMessage(pcmBuffer.buffer, [pcmBuffer.buffer]);
        }
      }
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
