import { downsampleBuffer } from '../audio/downsampler';

let inputSampleRate = 44100;

/**
 * Handle incoming events from the primary Web Audio capture hook.
 * Offloads compute-heavy downsampling processes to secondary worker thread threads.
 */
self.onmessage = (event: MessageEvent) => {
  const { command, payload } = event.data;

  switch (command) {
    case 'init':
      // Initialize target input rates from browser recording contexts
      if (payload && payload.sampleRate) {
        inputSampleRate = payload.sampleRate;
      }
      break;

    case 'process':
      if (payload && payload.buffer) {
        const float32Array = new Float32Array(payload.buffer);
        const pcm16Data = downsampleBuffer(float32Array, inputSampleRate);
        
        // Post downsampled PCM back to React UI WebSocket stream queue
        // Transfer the underlying ArrayBuffer memory space for zero-copy performance
        self.postMessage({
          type: 'pcm',
          buffer: pcm16Data.buffer
        }, [pcm16Data.buffer]);
      }
      break;

    default:
      break;
  }
};
