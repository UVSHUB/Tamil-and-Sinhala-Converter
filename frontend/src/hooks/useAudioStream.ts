import { useState, useEffect, useRef, useCallback } from 'react';

type SessionState = 'IDLE' | 'AI_LISTENING' | 'AI_THINKING' | 'AI_SPEAKING' | 'ERROR';

/**
 * Custom hook to manage the full life-cycle of low-latency client-side audio streaming:
 * 1. Grabs mic inputs via getUserMedia.
 * 2. Offloads downsampling compute to secondary Web Worker thread.
 * 3. Streams resulting raw 16-bit mono 16kHz PCM data over WebSocket.
 * 4. Receives translated text and 24kHz synthesized audio bytes from the server.
 * 5. Schedules PCM playback chunks sequentially to prevent gaps/clicks.
 */
export function useAudioStream(langMode: 'SI_TO_TA' | 'TA_TO_SI') {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [sessionState, setSessionState] = useState<SessionState>('IDLE');
  const [sinhalaCaption, setSinhalaCaption] = useState<string>('');
  const [tamilCaption, setTamilCaption] = useState<string>('');
  const [logs, setLogs] = useState<string[]>([
    'System initialized. Awaiting user interaction...',
  ]);

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 15)]);
  }, []);

  // Web API references
  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const workerRef = useRef<Worker | null>(null);

  // Playback queue reference
  const nextPlaybackTimeRef = useRef<number>(0);

  // Converts 16-bit PCM ArrayBuffer (24kHz) to Float32 and schedules it on AudioContext
  const playAudioChunk = useCallback((arrayBuffer: ArrayBuffer) => {
    if (!audioContextRef.current) return;

    const audioCtx = audioContextRef.current;
    const int16Array = new Int16Array(arrayBuffer);
    if (int16Array.length === 0) return;

    // Convert Int16 [-32768, 32767] to Float32 [-1.0, 1.0]
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    // Create 24kHz mono AudioBuffer (Gemini Live audio output rate)
    const audioBuffer = audioCtx.createBuffer(1, float32Array.length, 24000);
    audioBuffer.copyToChannel(float32Array, 0);

    // Create Buffer Source Node
    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    // Reset playback pointer if it fell behind actual time
    if (nextPlaybackTimeRef.current < now) {
      nextPlaybackTimeRef.current = now;
    }

    source.start(nextPlaybackTimeRef.current);
    nextPlaybackTimeRef.current += audioBuffer.duration;

    // Update state to AI speaking when we receive output audio
    setSessionState('AI_SPEAKING');
  }, []);

  // Force-terminates all audio capture and streaming channels
  const stopStream = useCallback(() => {
    setIsRecording(false);
    setSessionState('IDLE');

    if (processorNodeRef.current) {
      processorNodeRef.current.disconnect();
      processorNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (workerRef.current) {
      workerRef.current.terminate();
      workerRef.current = null;
    }
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    setIsConnected(false);
    addLog('Session closed. Audio capture and WebSocket pipeline terminated.');
  }, [addLog]);

  // Connects socket, grabs mic, spins up worker, starts downsampling pipeline
  const startStream = useCallback(async () => {
    try {
      addLog('Initiating session. Requesting microphone credentials...');
      setSessionState('AI_LISTENING');

      // 1. Validate secure context/microphone support
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(
          'Microphone API is disabled/blocked. Browsers require a Secure Context (localhost/127.0.0.1 or HTTPS) to access audio. Please visit http://localhost:5180 instead of a network IP.'
        );
      }

      // Capture microphone hardware stream
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      mediaStreamRef.current = stream;
      addLog('Microphone access granted.');

      // 2. Establish WebSocket socket pipeline
      const wsUrl = `ws://${window.location.hostname}:8000/ws/translate?mode=${langMode}`;
      addLog(`Connecting WebSocket to gateway: ${wsUrl}...`);
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;
      socket.binaryType = 'arraybuffer';

      // Reset playback timer
      nextPlaybackTimeRef.current = 0;

      // 3. Spawn downsampler worker thread
      addLog('Spawning background Web Worker thread for 16kHz PCM downsampling...');
      const worker = new Worker(
        new URL('../workers/audio-processor.worker.ts', import.meta.url),
        { type: 'module' }
      );
      workerRef.current = worker;

      // 4. Configure Web Audio Graph
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const sampleRate = audioCtx.sampleRate;
      addLog(`Native Web Audio capture context active at ${sampleRate}Hz.`);

      // Send initial sampling parameters to the worker thread
      worker.postMessage({
        command: 'init',
        payload: { sampleRate },
      });

      // Handle raw downsampled PCM chunks returned from worker thread
      worker.onmessage = (event: MessageEvent) => {
        const { type, buffer } = event.data;
        if (type === 'pcm' && socket.readyState === WebSocket.OPEN) {
          // Stream raw 16-bit PCM packet to WebSocket gateway
          socket.send(buffer);
        }
      };

      // Connect nodes
      const source = audioCtx.createMediaStreamSource(stream);
      sourceNodeRef.current = source;

      // Capture native float32 chunks (2048 samples provides low latency buffer)
      const processor = audioCtx.createScriptProcessor(2048, 1, 1);
      processorNodeRef.current = processor;

      processor.onaudioprocess = (e) => {
        const inputChannelData = e.inputBuffer.getChannelData(0);
        // Slice a copy to prevent garbage collector collisions when transferring ownership
        const bufferCopy = new Float32Array(inputChannelData).buffer;

        // Post chunk buffer to worker for off-thread processing
        worker.postMessage({
          command: 'process',
          payload: {
            buffer: bufferCopy,
            channels: 1,
          },
        }, [bufferCopy]);
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      // WebSocket Handlers
      socket.onopen = () => {
        setIsConnected(true);
        setIsRecording(true);
        addLog('WebSocket link established. Streaming frames to Gemini API...');
      };

      socket.onmessage = (e) => {
        if (typeof e.data === 'string') {
          try {
            const response = JSON.parse(e.data);
            if (response.type === 'status') {
              addLog(`[Server] ${response.payload.message}`);
            } else if (response.type === 'translation') {
              const text = response.payload.text;
              if (langMode === 'SI_TO_TA') {
                setTamilCaption((prev) => prev + text);
              } else {
                setSinhalaCaption((prev) => prev + text);
              }
              // Switch UI state to active speaking
              setSessionState('AI_SPEAKING');
            } else if (response.type === 'turn_complete') {
              addLog('Gemini Live finished turn output.');
              setSessionState('AI_LISTENING');
            }
          } catch (err) {
            addLog(`Received text message: ${e.data}`);
          }
        } else if (e.data instanceof ArrayBuffer) {
          // Play back the raw 24kHz synthesized audio bytes
          playAudioChunk(e.data);
        }
      };

      socket.onerror = () => {
        addLog('WebSocket connection error.');
        setSessionState('ERROR');
      };

      socket.onclose = (event) => {
        addLog(`WebSocket connection closed (code: ${event.code}).`);
        setIsConnected(false);
        setIsRecording(false);
        setSessionState('IDLE');
      };
    } catch (error: any) {
      addLog(`Failed to initialize stream pipeline: ${error.message || error}`);
      setSessionState('ERROR');
      stopStream();
    }
  }, [addLog, stopStream, langMode, playAudioChunk]);

  // Clean up references on unmount
  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  return {
    isConnected,
    isRecording,
    sessionState,
    sinhalaCaption,
    tamilCaption,
    logs,
    startStream,
    stopStream,
    setSinhalaCaption,
    setTamilCaption,
    addLog,
  };
}
