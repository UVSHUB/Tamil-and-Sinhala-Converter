import { useState, useEffect, useRef, useCallback } from 'react';
import { getAudioWorkletUrl } from '../audio/audio-helper';

type SessionState = 'IDLE' | 'AI_LISTENING' | 'AI_THINKING' | 'AI_SPEAKING' | 'ERROR';

/**
 * Custom hook to manage the full life-cycle of low-latency client-side audio streaming:
 * 1. Grabs mic inputs via getUserMedia.
 * 2. Uses an Audio Worklet running on a high-priority thread to capture and convert audio.
 * 3. Streams resulting raw 16-bit mono 16kHz PCM data over WebSocket.
 * 4. Receives translated text and 24kHz synthesized audio bytes from the server.
 * 5. Schedules PCM playback chunks sequentially to prevent gaps/clicks.
 * 6. Integrates Audio Analysers for real-time visualization of mic and AI voice.
 * 7. Automatically reconnects if the connection drops unexpectedly.
 */
export function useAudioStream(sourceLang: string, targetLang: string) {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [sessionState, setSessionState] = useState<SessionState>('IDLE');
  const [sourceCaption, setSourceCaption] = useState<string>('');
  const [targetCaption, setTargetCaption] = useState<string>('');
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [logs, setLogs] = useState<string[]>([
    'System initialized. Awaiting user interaction...',
  ]);

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 15)]);
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted((prev) => !prev);
  }, []);

  // Web API references
  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);

  // Analyser nodes for visualizer
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const aiAnalyserRef = useRef<AnalyserNode | null>(null);

  // Reconnection refs
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimerRef = useRef<any>(null);
  const isManualCloseRef = useRef<boolean>(false);
  const pendingTextRef = useRef<string | null>(null);

  // Playback queue reference
  const nextPlaybackTimeRef = useRef<number>(0);

  // Converts 16-bit PCM ArrayBuffer (24kHz) to Float32 and schedules it on AudioContext
  const playAudioChunk = useCallback((arrayBuffer: ArrayBuffer) => {
    if (isMuted) return; // Discard audio if muted
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

    // Connect source -> aiAnalyser -> destination
    if (!aiAnalyserRef.current) {
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      aiAnalyserRef.current = analyser;
    }
    source.connect(aiAnalyserRef.current);
    aiAnalyserRef.current.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    // Reset playback pointer if it fell behind actual time
    if (nextPlaybackTimeRef.current < now) {
      nextPlaybackTimeRef.current = now;
    }

    source.start(nextPlaybackTimeRef.current);
    nextPlaybackTimeRef.current += audioBuffer.duration;

    // Update state to AI speaking when we receive output audio
    setSessionState('AI_SPEAKING');
  }, [isMuted]);

  // Force-terminates all audio capture and streaming channels
  const stopStream = useCallback(() => {
    isManualCloseRef.current = true;
    setIsRecording(false);
    setSessionState('IDLE');

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectAttemptsRef.current = 0;

    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
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
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    micAnalyserRef.current = null;
    aiAnalyserRef.current = null;
    setIsConnected(false);
    addLog('Session closed. Audio capture and WebSocket pipeline terminated.');
  }, [addLog]);

  // Connects socket, grabs mic, loads worklet, starts streaming pipeline
  const startStream = useCallback(async () => {
    try {
      isManualCloseRef.current = false;
      addLog(`Initiating session. Requesting microphone credentials for ${sourceLang} ↔ ${targetLang}...`);
      setSessionState('AI_LISTENING');

      // 1. Validate secure context/microphone support
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(
          'Microphone API is disabled/blocked. Browsers require a Secure Context (localhost/127.0.0.1 or HTTPS) to access audio.'
        );
      }

      // Capture microphone hardware stream with auto gain, noise suppression and echo cancellation
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;
      addLog('Microphone access granted.');

      // 2. Establish WebSocket socket pipeline passing source/target language parameters
      const wsUrl = `ws://${window.location.hostname}:8000/ws/translate?source=${encodeURIComponent(sourceLang)}&target=${encodeURIComponent(targetLang)}`;
      addLog(`Connecting WebSocket to gateway: ${wsUrl}...`);
      const socket = new WebSocket(wsUrl);
      socketRef.current = socket;
      socket.binaryType = 'arraybuffer';

      // Reset playback timer
      nextPlaybackTimeRef.current = 0;

      // Reset captions
      setSourceCaption('');
      setTargetCaption('');

      // 3. Configure Web Audio Graph with native 16kHz sample rate for high-quality browser downsampling
      let audioCtx: AudioContext;
      try {
        audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)({
          sampleRate: 16000,
        });
        addLog('Successfully initialized native 16kHz AudioContext.');
      } catch (e) {
        addLog('Native 16kHz context not supported. Falling back to default native sample rate.');
        audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      }
      audioContextRef.current = audioCtx;
      const sampleRate = audioCtx.sampleRate;
      addLog(`Native Web Audio capture context active at ${sampleRate}Hz.`);

      // 4. Load and register the Audio Worklet Processor
      addLog('Loading AudioWorklet module for low-latency recording...');
      const workletUrl = getAudioWorkletUrl();
      await audioCtx.audioWorklet.addModule(workletUrl);

      // Create the AudioWorkletNode
      const workletNode = new AudioWorkletNode(audioCtx, 'audio-recorder-processor');
      workletNodeRef.current = workletNode;

      // Handle raw downsampled PCM chunks returned from worklet
      workletNode.port.onmessage = (event: MessageEvent) => {
        const pcmBuffer = event.data; // ArrayBuffer of Int16 PCM
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(pcmBuffer);
        }
      };

      // Create Analyser Node for microphone
      const micAnalyser = audioCtx.createAnalyser();
      micAnalyser.fftSize = 256;
      micAnalyserRef.current = micAnalyser;

      // Connect nodes: source -> micAnalyser -> workletNode -> destination
      const source = audioCtx.createMediaStreamSource(stream);
      sourceNodeRef.current = source;

      source.connect(micAnalyser);
      micAnalyser.connect(workletNode);
      workletNode.connect(audioCtx.destination);
      addLog('AudioWorkletNode and Analyser connected and streaming.');

      // WebSocket Handlers
      socket.onopen = () => {
        setIsConnected(true);
        setIsRecording(true);
        reconnectAttemptsRef.current = 0;
        addLog(`WebSocket link established. Streaming ${sourceLang} speech to Gemini...`);
        if (pendingTextRef.current) {
          socket.send(pendingTextRef.current);
          addLog(`Sent pending text message: "${pendingTextRef.current}"`);
          pendingTextRef.current = null;
        }
      };

      socket.onmessage = (e) => {
        if (typeof e.data === 'string') {
          try {
            const response = JSON.parse(e.data);
            if (response.type === 'status') {
              addLog(`[Server] ${response.payload.message}`);
            } else if (response.type === 'transcription') {
              const text = response.payload.text;
              setSourceCaption((prev) => prev + text);
            } else if (response.type === 'translation') {
              const text = response.payload.text;
              setTargetCaption((prev) => prev + text);
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

        // Auto-reconnect if it was not a manual stop and we have attempts remaining
        if (!isManualCloseRef.current && reconnectAttemptsRef.current < 5) {
          setSessionState('AI_THINKING');
          reconnectAttemptsRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
          addLog(`Unexpected disconnect. Reconnecting in ${delay}ms (Attempt ${reconnectAttemptsRef.current}/5)...`);
          
          reconnectTimerRef.current = setTimeout(() => {
            startStream();
          }, delay);
        } else {
          setSessionState('IDLE');
        }
      };
    } catch (error: any) {
      addLog(`Failed to initialize stream pipeline: ${error.message || error}`);
      setSessionState('ERROR');
      stopStream();
    }
  }, [addLog, stopStream, sourceLang, targetLang, playAudioChunk]);

  const sendText = useCallback((text: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(text);
      addLog(`Sent text message: "${text}"`);
    } else {
      pendingTextRef.current = text;
      addLog(`Queueing text message and connecting: "${text}"`);
      startStream();
    }
  }, [addLog, startStream]);

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
    sourceCaption,
    targetCaption,
    logs,
    isMuted,
    toggleMute,
    sendText,
    startStream,
    stopStream,
    setSourceCaption,
    setTargetCaption,
    addLog,
    micAnalyserRef,
    aiAnalyserRef,
  };
}
