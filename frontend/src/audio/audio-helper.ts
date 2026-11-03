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
    // Resample ratio: how many input samples per 1 output sample
    this._ratio = this._inputRate / this._targetRate;
    this._chunkSize = 1600; // 100ms chunks (1600 samples at 16kHz) for ultra-low latency & clean streaming
    this._accumulated = [];

    // Noise gate: silence is not sent (the server fills pauses in), but speech must never be cut.
    // - Hangover: keep sending 400 ms after the voice drops, so short dips between
    //   syllables and words do not chop speech apart.
    // - Pre-roll: keep the last 300 ms of "silence" and send it when speech starts, so
    //   the quiet beginning of the first word is not lost.
    this._threshold = 0.010;
    this._hangoverFrames = Math.ceil(0.4 * this._inputRate / 128); // process() gets 128-sample frames
    this._hangover = 0;
    this._preRollMax = Math.round(0.3 * this._targetRate);
    this._preRoll = [];
  }

  _resample(channelData) {
    const out = [];
    if (Math.abs(this._ratio - 1.0) < 0.001) {
      for (let i = 0; i < channelData.length; i++) {
        const sample = Math.max(-1.0, Math.min(1.0, channelData[i]));
        out.push(sample < 0 ? sample * 0x8000 : sample * 0x7FFF);
      }
      return out;
    }
    const inputLength = channelData.length;
    const outputLength = Math.floor(inputLength / this._ratio);
    for (let i = 0; i < outputLength; i++) {
      const srcPos = i * this._ratio;
      const srcIdx = Math.floor(srcPos);
      const frac = srcPos - srcIdx;
      let sample = channelData[srcIdx] || 0;
      if (srcIdx + 1 < inputLength) {
        sample = channelData[srcIdx] * (1 - frac) + channelData[srcIdx + 1] * frac;
      }
      sample = Math.max(-1.0, Math.min(1.0, sample));
      out.push(sample < 0 ? sample * 0x8000 : sample * 0x7FFF);
    }
    return out;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0]; // Mono channel 0

      // Fast RMS calculation for Voice Activity Detection
      let sumSquares = 0;
      for (let i = 0; i < channelData.length; i++) {
        sumSquares += channelData[i] * channelData[i];
      }
      const rms = Math.sqrt(sumSquares / channelData.length);
      const samples = this._resample(channelData);

      if (rms >= this._threshold) {
        if (this._hangover === 0 && this._preRoll.length > 0) {
          // Speech is starting: send the buffered lead-in first
          for (let i = 0; i < this._preRoll.length; i++) this._accumulated.push(this._preRoll[i]);
          this._preRoll = [];
        }
        this._hangover = this._hangoverFrames;
      } else if (this._hangover > 0) {
        this._hangover--;
      } else {
        // Silence: flush what is left of the speech, then keep a short pre-roll only
        if (this._accumulated.length > 0) {
          const pcmBuffer = new Int16Array(this._accumulated);
          this.port.postMessage(pcmBuffer.buffer, [pcmBuffer.buffer]);
          this._accumulated = [];
        }
        for (let i = 0; i < samples.length; i++) this._preRoll.push(samples[i]);
        if (this._preRoll.length > this._preRollMax) {
          this._preRoll.splice(0, this._preRoll.length - this._preRollMax);
        }
        return true; // Drop silence
      }

      for (let i = 0; i < samples.length; i++) this._accumulated.push(samples[i]);

      // Dispatch audio chunk when we hit 100ms (1600 samples)
      while (this._accumulated.length >= this._chunkSize) {
        const chunk = this._accumulated.splice(0, this._chunkSize);
        const pcmBuffer = new Int16Array(chunk);
        this.port.postMessage(pcmBuffer.buffer, [pcmBuffer.buffer]);
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
