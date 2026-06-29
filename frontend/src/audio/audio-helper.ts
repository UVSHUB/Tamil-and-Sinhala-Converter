/**
 * Audio Worklet Processor source code as a string.
 * This runs on the browser's high-priority audio thread, converting 
 * Float32 microphone input directly to 16-bit Int16 PCM.
 */
const workletCode = `
class AudioRecorderProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0]; // Mono channel 0
      const length = channelData.length;
      const pcmBuffer = new Int16Array(length);
      
      for (let i = 0; i < length; i++) {
        // Clamp float sample value to [-1.0, 1.0] and convert to 16-bit signed integer
        const sample = Math.max(-1.0, Math.min(1.0, channelData[i]));
        pcmBuffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
      }
      
      // Transfer the underlying ArrayBuffer to the main thread with zero-copy overhead
      this.port.postMessage(pcmBuffer.buffer, [pcmBuffer.buffer]);
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
