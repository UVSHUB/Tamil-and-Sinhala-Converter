import { useState, useEffect, useRef, useCallback } from 'react';
import { getAudioWorkletUrl } from '../audio/audio-helper';

type SessionState = 'IDLE' | 'AI_LISTENING' | 'AI_THINKING' | 'AI_SPEAKING' | 'ERROR';

/**
 * Autocorrelation algorithm to detect the fundamental frequency (pitch) of human voice.
 */
function autoCorrelate(buffer: Float32Array, sampleRate: number): number {
  const SIZE = buffer.length;
  let rms = 0;
  for (let i = 0; i < SIZE; i++) {
    const val = buffer[i];
    rms += val * val;
  }
  rms = Math.sqrt(rms / SIZE);
  // Lower the sensitivity threshold so normal speech isn't rejected.
  if (rms < 0.003) return -1;

  let r1 = 0;
  let r2 = SIZE - 1;
  const thres = 0.2;
  for (let i = 0; i < SIZE / 2; i++) {
    if (Math.abs(buffer[i]) < thres) { r1 = i; } else { break; }
  }
  for (let i = SIZE - 1; i >= SIZE / 2; i--) {
    if (Math.abs(buffer[i]) < thres) { r2 = i; } else { break; }
  }

  const signal = buffer.subarray(r1, r2);
  const len = signal.length;
  if (len < 128) return -1;

  const c = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    for (let j = 0; j < len - i; j++) {
      c[i] += signal[j] * signal[j + i];
    }
  }

  let d = 0;
  while (d < len - 1 && c[d] > c[d + 1]) d++;

  let maxval = -1;
  let maxpos = -1;
  for (let i = d; i < len - 1; i++) {
    if (c[i] > c[i - 1] && c[i] > c[i + 1]) {
      if (c[i] > maxval) { maxval = c[i]; maxpos = i; }
    }
  }

  if (maxpos !== -1) {
    const pitch = sampleRate / maxpos;
    // Accept a wider human-voice range so quieter voices can still register.
    if (pitch >= 50 && pitch <= 500) return pitch;
  }
  return -1;
}

/**
 * Custom hook to manage the full life-cycle of low-latency audio streaming.
 * Fixed: language not updating mid-session, no response output, excessive delay,
 * language switching bugs, stale closures in reconnect, and text sending issues.
 */
export function useAudioStream(sourceLang: string, targetLang: string, autoMode: boolean = false) {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [room, setRoom] = useState<string>('default');
  const [sessionState, setSessionState] = useState<SessionState>('IDLE');
  const [sourceCaption, setSourceCaption] = useState<string>('');
  const [targetCaption, setTargetCaption] = useState<string>('');
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [logs, setLogs] = useState<string[]>(['System initialized. Awaiting user interaction...']);

  const [detectedGender, setDetectedGender] = useState<'male' | 'female' | null>(null);
  const [voiceMode, setVoiceMode] = useState<'auto' | 'manual'>('auto');
  const [ttsVoice, setTtsVoice] = useState<'Aoede' | 'Kore' | 'Charon' | 'Puck' | 'Fenrir'>('Aoede');
  const [detectedSourceLang, setDetectedSourceLang] = useState<string | null>(null);
  const [detectedTargetLang, setDetectedTargetLang] = useState<string | null>(null);

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev.slice(0, 15)]);
  }, []);

  const toggleMute = useCallback(() => setIsMuted((prev) => !prev), []);

  // Refs for WebSocket and audio infra
  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const detectedGenderRef = useRef<'male' | 'female' | null>(null);
  const pitchIntervalRef = useRef<any>(null);
  const pcmBufferQueueRef = useRef<ArrayBuffer[]>([]);
  const isWsConnectingRef = useRef<boolean>(false);
  const micAnalyserRef = useRef<AnalyserNode | null>(null);
  const aiAnalyserRef = useRef<AnalyserNode | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimerRef = useRef<any>(null);
  const isManualCloseRef = useRef<boolean>(false);
  const pendingTextRef = useRef<string | null>(null);
  const nextPlaybackTimeRef = useRef<number>(0);
  const isActiveSessionRef = useRef<boolean>(false);
  const isAiSpeakingRef = useRef<boolean>(false);
  const aiSpeakingTimerRef = useRef<any>(null);

  // Always-current language/voice refs (avoid stale closures)
  const sourceLangRef = useRef<string>(sourceLang);
  const targetLangRef = useRef<string>(targetLang);
  const voiceModeRef = useRef<'auto' | 'manual'>(voiceMode);
  const ttsVoiceRef = useRef<string>(ttsVoice);

  useEffect(() => { sourceLangRef.current = sourceLang; }, [sourceLang]);
  useEffect(() => { targetLangRef.current = targetLang; }, [targetLang]);
  useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);
  useEffect(() => { ttsVoiceRef.current = ttsVoice; }, [ttsVoice]);

  // Play synthesized 24kHz PCM audio chunk from Gemini
  const playAudioChunk = useCallback((arrayBuffer: ArrayBuffer) => {
    if (isMuted) return;
    if (!audioContextRef.current) return;

    const audioCtx = audioContextRef.current;
    const int16Array = new Int16Array(arrayBuffer);
    if (int16Array.length === 0) return;

    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const audioBuffer = audioCtx.createBuffer(1, float32Array.length, 24000);
    audioBuffer.copyToChannel(float32Array, 0);

    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;

    if (!aiAnalyserRef.current) {
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      aiAnalyserRef.current = analyser;
    }
    source.connect(aiAnalyserRef.current);
    aiAnalyserRef.current.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    if (nextPlaybackTimeRef.current < now) {
      nextPlaybackTimeRef.current = now;
    } else if (nextPlaybackTimeRef.current - now > 0.25) {
      // Clamp playback drift: prevents artificial audio queuing delay
      nextPlaybackTimeRef.current = now + 0.05;
    }
    source.start(nextPlaybackTimeRef.current);
    nextPlaybackTimeRef.current += audioBuffer.duration;

    // Acoustic Echo Guard: Mark AI speaking and suppress mic streaming while audio plays
    isAiSpeakingRef.current = true;
    setSessionState('AI_SPEAKING');

    if (aiSpeakingTimerRef.current) {
      clearTimeout(aiSpeakingTimerRef.current);
    }
    const msUntilEnd = Math.max(120, Math.round((nextPlaybackTimeRef.current - now) * 1000) + 120);
    aiSpeakingTimerRef.current = setTimeout(() => {
      isAiSpeakingRef.current = false;
      setSessionState('AI_LISTENING');
    }, msUntilEnd);
  }, [isMuted]);

  // Close only the WebSocket without tearing down mic/audio
  const closeSocket = useCallback(() => {
    if (socketRef.current) {
      const s = socketRef.current;
      s.onclose = null;
      s.onerror = null;
      s.onmessage = null;
      s.onopen = null;
      if (s.readyState === WebSocket.OPEN || s.readyState === WebSocket.CONNECTING) {
        s.close();
      }
      socketRef.current = null;
    }
    setIsConnected(false);
    isWsConnectingRef.current = false;
  }, []);

  // Open (or reopen) the WebSocket, reusing existing mic/audio context
  const connectWebSocket = useCallback((voiceName: string, src: string, tgt: string) => {
    if (isWsConnectingRef.current) return;
    closeSocket();
    isWsConnectingRef.current = true;

    const wsUrl = `ws://${window.location.hostname}:8000/ws/translate?source=${encodeURIComponent(src)}&target=${encodeURIComponent(tgt)}&voice=${encodeURIComponent(voiceName)}&room=${encodeURIComponent(room)}`;
    addLog(`Connecting (Room: ${room}): ${src} → ${tgt} | voice: ${voiceName}`);

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;
    socket.binaryType = 'arraybuffer';
    nextPlaybackTimeRef.current = 0;

    socket.onopen = () => {
      setIsConnected(true);
      setIsRecording(true);
      setSessionState('AI_LISTENING');
      isWsConnectingRef.current = false;
      reconnectAttemptsRef.current = 0;
      addLog(`Connected: ${src} → ${tgt}. Start speaking!`);

      // Flush buffered audio — but only if it's a small queue (recent audio)
      // A large queue means we're replaying stale audio which floods the API
      if (pcmBufferQueueRef.current.length > 0 && pcmBufferQueueRef.current.length <= 30) {
        for (const chunk of pcmBufferQueueRef.current) socket.send(chunk);
        addLog(`Flushed ${pcmBufferQueueRef.current.length} buffered packets.`);
      } else if (pcmBufferQueueRef.current.length > 30) {
        addLog(`Discarded ${pcmBufferQueueRef.current.length} stale audio packets (too old).`);
      }
      pcmBufferQueueRef.current = [];

      // Send pending text
      if (pendingTextRef.current) {
        socket.send(pendingTextRef.current);
        addLog(`Sent pending text: "${pendingTextRef.current}"`);
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
            setSourceCaption(response.payload.text);
          } else if (response.type === 'translation') {
            setTargetCaption(response.payload.text);
            setSessionState('AI_SPEAKING');
          } else if (response.type === 'turn_complete') {
            addLog('Turn complete.');
            const now = audioContextRef.current ? audioContextRef.current.currentTime : 0;
            const msUntilEnd = Math.max(80, Math.round((nextPlaybackTimeRef.current - now) * 1000) + 80);
            if (aiSpeakingTimerRef.current) clearTimeout(aiSpeakingTimerRef.current);
            aiSpeakingTimerRef.current = setTimeout(() => {
              isAiSpeakingRef.current = false;
              setSessionState('AI_LISTENING');
            }, msUntilEnd);
          } else if (response.type === 'lang_detected') {
            setDetectedSourceLang(response.payload.source);
            setDetectedTargetLang(response.payload.target);
            addLog(`Auto-detected: ${response.payload.source} → ${response.payload.target}`);
          }
        } catch {
          addLog(`Raw message: ${e.data}`);
        }
      } else if (e.data instanceof ArrayBuffer) {
        playAudioChunk(e.data);
      }
    };

    socket.onerror = () => {
      addLog('WebSocket error.');
      setSessionState('ERROR');
    };

    socket.onclose = (event) => {
      addLog(`WebSocket closed (code: ${event.code}).`);
      setIsConnected(false);
      setIsRecording(false);
      isWsConnectingRef.current = false;

      if (!isManualCloseRef.current && isActiveSessionRef.current && reconnectAttemptsRef.current < 5) {
        setSessionState('AI_THINKING');
        reconnectAttemptsRef.current += 1;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
        addLog(`Reconnecting in ${delay}ms (Attempt ${reconnectAttemptsRef.current}/5)...`);

        reconnectTimerRef.current = setTimeout(() => {
          const voice = voiceModeRef.current === 'manual'
            ? ttsVoiceRef.current
            : (detectedGenderRef.current === 'male' ? 'Charon' : 'Aoede');
          connectWebSocket(voice, sourceLangRef.current, targetLangRef.current);
        }, delay);
      } else {
        if (!isActiveSessionRef.current) setSessionState('IDLE');
      }
    };
  }, [addLog, closeSocket, playAudioChunk, room]);

  // Open the auto-detect WebSocket (no source/target params needed)
  const connectAutoWebSocket = useCallback((voiceName: string) => {
    if (isWsConnectingRef.current) return;
    closeSocket();
    isWsConnectingRef.current = true;

    const wsUrl = `ws://${window.location.hostname}:8000/ws/translate-auto?voice=${encodeURIComponent(voiceName)}&room=${encodeURIComponent(room)}`;
    addLog(`Connecting auto-detect mode (Room: ${room}) | voice: ${voiceName}`);

    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;
    socket.binaryType = 'arraybuffer';
    nextPlaybackTimeRef.current = 0;

    socket.onopen = () => {
      setIsConnected(true);
      setIsRecording(true);
      setSessionState('AI_LISTENING');
      isWsConnectingRef.current = false;
      reconnectAttemptsRef.current = 0;
      addLog('Auto-detect connected! Speak in Sinhala or Tamil.');

      if (pcmBufferQueueRef.current.length > 0 && pcmBufferQueueRef.current.length <= 30) {
        for (const chunk of pcmBufferQueueRef.current) socket.send(chunk);
        addLog(`Flushed ${pcmBufferQueueRef.current.length} buffered packets.`);
      } else if (pcmBufferQueueRef.current.length > 30) {
        addLog(`Discarded ${pcmBufferQueueRef.current.length} stale audio packets.`);
      }
      pcmBufferQueueRef.current = [];

      if (pendingTextRef.current) {
        socket.send(pendingTextRef.current);
        addLog(`Sent pending text: "${pendingTextRef.current}"`);
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
            setSourceCaption(response.payload.text);
          } else if (response.type === 'translation') {
            setTargetCaption(response.payload.text);
            setSessionState('AI_SPEAKING');
          } else if (response.type === 'turn_complete') {
            addLog('Turn complete.');
            const now = audioContextRef.current ? audioContextRef.current.currentTime : 0;
            const msUntilEnd = Math.max(80, Math.round((nextPlaybackTimeRef.current - now) * 1000) + 80);
            if (aiSpeakingTimerRef.current) clearTimeout(aiSpeakingTimerRef.current);
            aiSpeakingTimerRef.current = setTimeout(() => {
              isAiSpeakingRef.current = false;
              setSessionState('AI_LISTENING');
            }, msUntilEnd);
          } else if (response.type === 'lang_detected') {
            setDetectedSourceLang(response.payload.source);
            setDetectedTargetLang(response.payload.target);
            addLog(`Auto-detected: ${response.payload.source} → ${response.payload.target}`);
          }
        } catch {
          addLog(`Raw message: ${e.data}`);
        }
      } else if (e.data instanceof ArrayBuffer) {
        playAudioChunk(e.data);
      }
    };

    socket.onerror = () => {
      addLog('WebSocket error (auto).');
      setSessionState('ERROR');
    };

    socket.onclose = (event) => {
      addLog(`WebSocket closed (auto, code: ${event.code}).`);
      setIsConnected(false);
      setIsRecording(false);
      isWsConnectingRef.current = false;

      if (!isManualCloseRef.current && isActiveSessionRef.current && reconnectAttemptsRef.current < 5) {
        setSessionState('AI_THINKING');
        reconnectAttemptsRef.current += 1;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000);
        addLog(`Reconnecting in ${delay}ms (Attempt ${reconnectAttemptsRef.current}/5)...`);

        reconnectTimerRef.current = setTimeout(() => {
          const voice = voiceModeRef.current === 'manual'
            ? ttsVoiceRef.current
            : (detectedGenderRef.current === 'male' ? 'Charon' : 'Aoede');
          connectAutoWebSocket(voice);
        }, delay);
      } else {
        if (!isActiveSessionRef.current) setSessionState('IDLE');
      }
    };
  }, [addLog, closeSocket, playAudioChunk, room]);

  // Full session start: grab mic, load worklet, connect WebSocket
  const startStream = useCallback(async () => {
    try {
      isManualCloseRef.current = false;
      isActiveSessionRef.current = true;
      reconnectAttemptsRef.current = 0;

      const src = sourceLangRef.current;
      const tgt = targetLangRef.current;
      addLog(`Starting session: ${src} → ${tgt}`);
      setSessionState('AI_LISTENING');

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Microphone not supported. Use localhost or HTTPS.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      mediaStreamRef.current = stream;
      addLog('Microphone access granted (Acoustic Echo Cancellation active).');
      pcmBufferQueueRef.current = [];
      isWsConnectingRef.current = false;
      setSourceCaption('');
      setTargetCaption('');

      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioCtx;
      addLog(`Audio context at ${audioCtx.sampleRate}Hz.`);

      const workletUrl = getAudioWorkletUrl();
      await audioCtx.audioWorklet.addModule(workletUrl);

      const workletNode = new AudioWorkletNode(audioCtx, 'audio-recorder-processor', {
        processorOptions: { inputSampleRate: audioCtx.sampleRate }
      });
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (event: MessageEvent) => {
        // Acoustic Echo Guard: Suppress microphone streaming while AI is playing translated speech
        // This prevents the speaker output from bleeding into the mic, stopping barge-in self-interruption.
        if (isAiSpeakingRef.current) {
          return;
        }

        const pcmBuffer = event.data;
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(pcmBuffer);
        } else if (isWsConnectingRef.current) {
          // Cap the queue — only keep the most recent ~250ms of audio (30 packets × ~8ms each)
          // Older audio is stale and flooding Gemini with it causes 1011 errors
          pcmBufferQueueRef.current.push(pcmBuffer);
          if (pcmBufferQueueRef.current.length > 30) {
            pcmBufferQueueRef.current.shift(); // drop oldest
          }
        }
      };

      const micAnalyser = audioCtx.createAnalyser();
      micAnalyser.fftSize = 2048;
      micAnalyserRef.current = micAnalyser;

      const source = audioCtx.createMediaStreamSource(stream);
      sourceNodeRef.current = source;
      source.connect(micAnalyser);
      micAnalyser.connect(workletNode);
      addLog('Audio pipeline ready.');

      const currentVoiceMode = voiceModeRef.current;
      const currentTtsVoice = ttsVoiceRef.current;

      if (autoMode) {
        // Auto-detect mode: connect to /ws/translate-auto regardless of voice mode
        if (currentVoiceMode === 'manual') {
          connectAutoWebSocket(currentTtsVoice);
        } else {
          const pitchBuffer = new Float32Array(2048);
          const consecutiveGenders: ('male' | 'female')[] = [];

          const timeoutId = setTimeout(() => {
            if (pitchIntervalRef.current) {
              clearInterval(pitchIntervalRef.current);
              pitchIntervalRef.current = null;
            }
            if (!socketRef.current && !isWsConnectingRef.current) {
              addLog('Pitch timeout. Connecting with default voice (Aoede)...');
              connectAutoWebSocket('Aoede');
            }
          }, 1000);

          pitchIntervalRef.current = setInterval(() => {
            if (!micAnalyserRef.current) return;
            micAnalyserRef.current.getFloatTimeDomainData(pitchBuffer);
            const pitch = autoCorrelate(pitchBuffer, audioCtx.sampleRate);

            if (pitch > 0) {
              const gender = pitch >= 160 ? 'female' : 'male';
              consecutiveGenders.push(gender);
              if (consecutiveGenders.length > 3) consecutiveGenders.shift();

              if (consecutiveGenders.length === 3 && consecutiveGenders.every(g => g === consecutiveGenders[0])) {
                clearTimeout(timeoutId);
                clearInterval(pitchIntervalRef.current);
                pitchIntervalRef.current = null;

                const stableGender = consecutiveGenders[0];
                detectedGenderRef.current = stableGender;
                setDetectedGender(stableGender);
                addLog(`Voice: ${stableGender} (${Math.round(pitch)}Hz). Connecting auto-detect...`);

                connectAutoWebSocket(stableGender === 'male' ? 'Charon' : 'Aoede');
              }
            }
          }, 150);
        }
      } else if (currentVoiceMode === 'manual') {
        connectWebSocket(currentTtsVoice, src, tgt);
      } else {
        const pitchBuffer = new Float32Array(2048);
        const consecutiveGenders: ('male' | 'female')[] = [];

        const timeoutId = setTimeout(() => {
          if (pitchIntervalRef.current) {
            clearInterval(pitchIntervalRef.current);
            pitchIntervalRef.current = null;
          }
          if (!socketRef.current && !isWsConnectingRef.current) {
            addLog('Pitch timeout. Connecting with default voice (Aoede)...');
            connectWebSocket('Aoede', src, tgt);
          }
        }, 1000);

        pitchIntervalRef.current = setInterval(() => {
          if (!micAnalyserRef.current) return;
          micAnalyserRef.current.getFloatTimeDomainData(pitchBuffer);
          const pitch = autoCorrelate(pitchBuffer, audioCtx.sampleRate);

          if (pitch > 0) {
            const gender = pitch >= 160 ? 'female' : 'male';
            consecutiveGenders.push(gender);
            if (consecutiveGenders.length > 3) consecutiveGenders.shift();

            if (consecutiveGenders.length === 3 && consecutiveGenders.every(g => g === consecutiveGenders[0])) {
              clearTimeout(timeoutId);
              clearInterval(pitchIntervalRef.current);
              pitchIntervalRef.current = null;

              const stableGender = consecutiveGenders[0];
              detectedGenderRef.current = stableGender;
              setDetectedGender(stableGender);
              addLog(`Voice: ${stableGender} (${Math.round(pitch)}Hz). Connecting...`);

              connectWebSocket(stableGender === 'male' ? 'Charon' : 'Aoede', src, tgt);
            }
          }
        }, 150);
      }
    } catch (error: any) {
      const errMsg = error.message || error;
      addLog(`Failed to start: ${errMsg}`);
      setSessionState('ERROR');
      stopStream();

      if (!navigator.mediaDevices?.getUserMedia) {
        alert(
          "Microphone Blocked!\n\n" +
          "Your mobile browser requires a secure HTTPS context to use the microphone.\n\n" +
          "Please enable the Chrome flag bypass (chrome://flags/#unsafely-treat-insecure-origin-as-secure) or expose your local server using a secure tunnel (like Ngrok)."
        );
      } else {
        alert(`Failed to start microphone: ${errMsg}\n\nPlease verify browser microphone permissions.`);
      }
    }
  }, [addLog, connectWebSocket, connectAutoWebSocket, autoMode]);

  // Full session stop: tear down everything
  const stopStream = useCallback(() => {
    isManualCloseRef.current = true;
    isActiveSessionRef.current = false;
    setIsRecording(false);
    setSessionState('IDLE');

    if (aiSpeakingTimerRef.current) {
      clearTimeout(aiSpeakingTimerRef.current);
      aiSpeakingTimerRef.current = null;
    }
    isAiSpeakingRef.current = false;

    if (pitchIntervalRef.current) {
      clearInterval(pitchIntervalRef.current);
      pitchIntervalRef.current = null;
    }
    detectedGenderRef.current = null;
    setDetectedGender(null);
    pcmBufferQueueRef.current = [];

    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectAttemptsRef.current = 0;

    if (workletNodeRef.current) { workletNodeRef.current.disconnect(); workletNodeRef.current = null; }
    if (sourceNodeRef.current) { sourceNodeRef.current.disconnect(); sourceNodeRef.current = null; }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    closeSocket();
    micAnalyserRef.current = null;
    aiAnalyserRef.current = null;
    addLog('Session terminated.');
  }, [addLog, closeSocket]);

  const sendText = useCallback((text: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(text);
      addLog(`Sent text: "${text}"`);
    } else {
      pendingTextRef.current = text;
      addLog(`Queuing text: "${text}"`);
      if (!isActiveSessionRef.current) startStream();
    }
  }, [addLog, startStream]);

  // Restart WebSocket when language changes mid-session (don't re-grab mic)
  useEffect(() => {
    if (!isActiveSessionRef.current || !audioContextRef.current) return;
    if (!socketRef.current && !isWsConnectingRef.current) return;

    addLog(`Language changed: ${sourceLang} → ${targetLang}. Reconnecting...`);
    setSourceCaption('');
    setTargetCaption('');

    const voice = voiceModeRef.current === 'manual'
      ? ttsVoiceRef.current
      : (detectedGenderRef.current === 'male' ? 'Charon' : 'Aoede');

    connectWebSocket(voice, sourceLang, targetLang);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceLang, targetLang]);

  // Reconnect with new voice when manual voice changes
  useEffect(() => {
    if (voiceMode === 'manual' && socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      addLog(`Voice changed to ${ttsVoice}. Reconnecting...`);
      connectWebSocket(ttsVoice, sourceLangRef.current, targetLangRef.current);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ttsVoice, voiceMode]);

  // Cleanup on unmount
  useEffect(() => { return () => { stopStream(); }; }, [stopStream]);

  return {
    isConnected, isRecording, sessionState, sourceCaption, targetCaption,
    logs, isMuted, toggleMute, sendText, startStream, stopStream,
    setSourceCaption, setTargetCaption, addLog, micAnalyserRef, aiAnalyserRef,
    detectedGender, voiceMode, setVoiceMode, ttsVoice, setTtsVoice,
    detectedSourceLang, detectedTargetLang,
    room, setRoom,
  };
}

/**
 * Bidirectional voice translation mode for call-center and live conversations.
 * Connects to /ws/translate-auto to automatically translate Sinhala <-> Tamil in real time.
 */
export function useAutoStream() {
  return useAudioStream('Sinhala', 'Tamil', true);
}
