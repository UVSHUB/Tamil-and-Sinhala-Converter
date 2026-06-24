import { AudioDownsampler } from '../audio/downsampler';

let downsampler: AudioDownsampler | null = null;
let inputSampleRate = 44100;

/**
 * Handle incoming events from the primary Web Audio capture hook.
 * Offloads compute-heavy downsampling processes to secondary worker thread.
 */
self.onmessage = (event: MessageEvent) => {
  const { command, payload } = event.data;

  switch (command) {
    case 'init':
      // Initialize target input rates from browser recording contexts
      if (payload && payload.sampleRate) {
        inputSampleRate = payload.sampleRate;
      }
      // Instantiate or re-instantiate downsampler state machine
      downsampler = new AudioDownsampler(inputSampleRate);
      break;

    case 'process':
      if (payload && payload.buffer) {
        if (!downsampler) {
          downsampler = new AudioDownsampler(inputSampleRate);
        }

        const float32Array = new Float32Array(payload.buffer);
        const numChannels = payload.channels || 1;
        const pcm16Data = downsampler.process(float32Array, numChannels);

        // Send downsampled PCM buffer back if we have accumulated enough data
        if (pcm16Data.length > 0) {
          // Transfer the underlying ArrayBuffer memory space for zero-copy performance
          (self as any).postMessage({
            type: 'pcm',
            buffer: pcm16Data.buffer
          }, [pcm16Data.buffer]);
        }
      }
      break;

    case 'reset':
      if (downsampler) {
        downsampler.reset();
      }
      break;

    default:
      break;
  }
};
