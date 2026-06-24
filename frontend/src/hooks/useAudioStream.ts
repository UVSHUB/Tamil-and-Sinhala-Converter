import { useState, useEffect, useRef, useCallback } from 'react';

type SessionState = 'IDLE' | 'AI_LISTENING' | 'AI_THINKING' | 'AI_SPEAKING' | 'ERROR';

/**
 * Custom hook to manage the full life-cycle of low-latency client-side audio streaming:
 * 1. Grabs mic inputs via getUserMedia.
 * 2. Offloads downsampling compute to secondary Web Worker thread.
 * 3. Streams resulting raw 16-bit mono 16kHz PCM data over WebSocket.
 * 4. Aggregates stream telemetry and logs.
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

      // 1. Capture microphone hardware stream
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
      const wsUrl = `ws://${window.location.hostname}:8000/ws/translate`;
      addLog(`Connecting WebSocket to gateway: ${wsUrl}...`);
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;
      socket.binaryType = 'arraybuffer';

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

      // Capture native float32 chunks (4096 samples provides safe latency buffer)
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
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
        try {
          const response = JSON.parse(e.data);
          if (response.status === 'received') {
            addLog(`Telemetry: server received ${response.bytes} bytes. ${response.message}`);
          } else {
            addLog(`Received backend command: ${e.data}`);
          }
        } catch (err) {
          addLog(`Received message frame: ${e.data}`);
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
  }, [addLog, stopStream]);

  // Clean up references on unmount
  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  // Simulation loop for voice-to-caption flow to verify state machine and visuals
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    if (isRecording && sessionState === 'AI_LISTENING') {
      let count = 0;
      interval = setInterval(() => {
        count++;
        if (count === 3) {
          setSessionState('AI_THINKING');
          if (langMode === 'SI_TO_TA') {
            setSinhalaCaption('ආයුබෝවන්, මට උදව් කරන්න පුළුවන්ද?');
            addLog('Sinhala speech detected: "ආයුබෝවන්, මට උදව් කරන්න පුළුවන්ද?"');
          } else {
            setTamilCaption('வணக்கம், நான் உங்களுக்கு உதவ முடியுமா?');
            addLog('Tamil speech detected: "வணக்கம், நான் உங்களுக்கு உதவ முடியுமா?"');
          }
        }
        if (count === 6) {
          setSessionState('AI_SPEAKING');
          if (langMode === 'SI_TO_TA') {
            setTamilCaption('வணக்கம், நான் உங்களுக்கு உதவ முடியுமா?');
            addLog('Gemini live generated Tamil synthesis audio stream...');
          } else {
            setSinhalaCaption('ආයුබෝවන්, මට උදව් කරන්න පුළුවන්ද?');
            addLog('Gemini live generated Sinhala synthesis audio stream...');
          }
        }
        if (count === 9) {
          setSessionState('AI_LISTENING');
          count = 0;
        }
      }, 1500);
    }

    return () => {
      if (interval !== null) {
        clearInterval(interval);
      }
    };
  }, [isRecording, sessionState, langMode, addLog]);

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
