import { useState, useEffect, useRef, useCallback } from 'react';
import { getAudioWorkletUrl, pcm16ToWavBlob } from '../audio/audio-helper';

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
export function useAudioStream(
  sourceLang: string,
  targetLang: string,
  autoMode: boolean = false,
  volume: number = 80
) {
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
  const gainNodeRef = useRef<GainNode | null>(null);
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

  // Echo cancellation & voice playback synchronization refs
  const isAiSpeakingRef = useRef<boolean>(false);
  const hasAudioInTurnRef = useRef<boolean>(false);
  const aiSpeechCooldownTimerRef = useRef<any>(null);
  const sourceCaptionRef = useRef<string>('');
  const targetCaptionRef = useRef<string>('');
  const volumeRef = useRef<number>(volume);
  const isMutedRef = useRef<boolean>(isMuted);
  const detectedTargetLangRef = useRef<string | null>(null);
  const turnPcmSamplesRef = useRef<Int16Array[]>([]);

  // Always-current language/voice refs (avoid stale closures)
  const sourceLangRef = useRef<string>(sourceLang);
  const targetLangRef = useRef<string>(targetLang);
  const voiceModeRef = useRef<'auto' | 'manual'>(voiceMode);
  const ttsVoiceRef = useRef<string>(ttsVoice);

  useEffect(() => { sourceLangRef.current = sourceLang; }, [sourceLang]);
  useEffect(() => { targetLangRef.current = targetLang; }, [targetLang]);
  useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);
  useEffect(() => { ttsVoiceRef.current = ttsVoice; }, [ttsVoice]);
  useEffect(() => { volumeRef.current = volume; }, [volume]);
  useEffect(() => { isMutedRef.current = isMuted; }, [isMuted]);
  useEffect(() => { detectedTargetLangRef.current = detectedTargetLang; }, [detectedTargetLang]);
  useEffect(() => { sourceCaptionRef.current = sourceCaption; }, [sourceCaption]);
  useEffect(() => { targetCaptionRef.current = targetCaption; }, [targetCaption]);

  // Robust AudioContext getter and node validator
  const ensureAudioContext = useCallback(() => {
    let audioCtx = audioContextRef.current;
    if (!audioCtx || audioCtx.state === 'closed') {
      audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioCtx;
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {});
    }

    if (!gainNodeRef.current || gainNodeRef.current.context !== audioCtx) {
      try { gainNodeRef.current?.disconnect(); } catch {}
      const gainNode = audioCtx.createGain();
      gainNode.gain.value = isMutedRef.current ? 0 : Math.max(0, Math.min(1, volumeRef.current / 100));
      gainNode.connect(audioCtx.destination);
      gainNodeRef.current = gainNode;
    }

    if (!aiAnalyserRef.current || aiAnalyserRef.current.context !== audioCtx) {
      try { aiAnalyserRef.current?.disconnect(); } catch {}
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.connect(gainNodeRef.current);
      aiAnalyserRef.current = analyser;
    }

    return audioCtx;
  }, []);

  // Sync volume & mute state to GainNode
  useEffect(() => {
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = isMuted ? 0 : Math.max(0, Math.min(1, volume / 100));
    }
  }, [volume, isMuted]);

  // Unlock audio on any page interaction (click, tap, keypress)
  useEffect(() => {
    const unlock = () => {
      if (audioContextRef.current && audioContextRef.current.state === 'suspended') {
        audioContextRef.current.resume().catch(() => {});
      }
    };
    window.addEventListener('click', unlock, { passive: true });
    window.addEventListener('touchstart', unlock, { passive: true });
    window.addEventListener('keydown', unlock, { passive: true });
    return () => {
      window.removeEventListener('click', unlock);
      window.removeEventListener('touchstart', unlock);
      window.removeEventListener('keydown', unlock);
    };
  }, []);

  // Play synthesized 24kHz PCM audio chunk from Gemini
  const playAudioChunk = useCallback(async (arrayBuffer: ArrayBuffer) => {
    if (isMutedRef.current) return;

    const audioCtx = ensureAudioContext();
    if (audioCtx.state === 'suspended') {
      try {
        await audioCtx.resume();
      } catch (err) {
        console.warn('AudioContext resume failed:', err);
      }
    }

    const byteLength = arrayBuffer.byteLength;
    if (byteLength < 2) return;
    const numSamples = Math.floor(byteLength / 2);
    const int16Array = new Int16Array(arrayBuffer, 0, numSamples);
    if (int16Array.length === 0) return;

    turnPcmSamplesRef.current.push(int16Array);

    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const audioBuffer = audioCtx.createBuffer(1, float32Array.length, 24000);
    audioBuffer.copyToChannel(float32Array, 0);

    const source = audioCtx.createBufferSource();
    source.buffer = audioBuffer;

    if (aiAnalyserRef.current) {
      source.connect(aiAnalyserRef.current);
    } else if (gainNodeRef.current) {
      source.connect(gainNodeRef.current);
    } else {
      source.connect(audioCtx.destination);
    }

    const now = audioCtx.currentTime;
    let startTime = nextPlaybackTimeRef.current;
    if (startTime < now || startTime > now + 2.0) {
      startTime = now + 0.02;
    }
    source.start(startTime);
    nextPlaybackTimeRef.current = startTime + audioBuffer.duration;

    isAiSpeakingRef.current = true;
    hasAudioInTurnRef.current = true;
    if (aiSpeechCooldownTimerRef.current) {
      clearTimeout(aiSpeechCooldownTimerRef.current);
      aiSpeechCooldownTimerRef.current = null;
    }
    setSessionState('AI_SPEAKING');

    source.onended = () => {
      if (audioContextRef.current && audioContextRef.current.currentTime >= nextPlaybackTimeRef.current - 0.05) {
        if (aiSpeechCooldownTimerRef.current) clearTimeout(aiSpeechCooldownTimerRef.current);
        aiSpeechCooldownTimerRef.current = setTimeout(() => {
          isAiSpeakingRef.current = false;
          if (isActiveSessionRef.current) setSessionState('AI_LISTENING');
          else setSessionState('IDLE');
        }, 250);
      }
    };
  }, [ensureAudioContext]);

  // Direct 3-tone chime to test user speakers and verify AudioContext
  const playTestSound = useCallback(async () => {
    try {
      const audioCtx = ensureAudioContext();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }

      const now = audioCtx.currentTime;
      // 3 melodic ascending tones: C5 (523Hz), E5 (659Hz), G5 (784Hz)
      const freqs = [523.25, 659.25, 783.99];
      freqs.forEach((freq, idx) => {
        const osc = audioCtx.createOscillator();
        const noteGain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, now + idx * 0.12);

        const startTime = now + idx * 0.12;
        const endTime = startTime + 0.18;

        noteGain.gain.setValueAtTime(0.001, startTime);
        const targetGain = Math.max(0.05, Math.min(0.35, (volumeRef.current / 100) * 0.35));
        noteGain.gain.linearRampToValueAtTime(targetGain, startTime + 0.02);
        noteGain.gain.exponentialRampToValueAtTime(0.0001, endTime);

        osc.connect(noteGain);
        if (aiAnalyserRef.current) {
          noteGain.connect(aiAnalyserRef.current);
        } else if (gainNodeRef.current) {
          noteGain.connect(gainNodeRef.current);
        } else {
          noteGain.connect(audioCtx.destination);
        }

        osc.start(startTime);
        osc.stop(endTime);
      });

      addLog('Speaker test sound played.');
      return true;
    } catch (err: any) {
      addLog(`Speaker test failed: ${err?.message || err}`);
      return false;
    }
  }, [ensureAudioContext, addLog]);

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
            sourceCaptionRef.current = response.payload.text;
          } else if (response.type === 'translation') {
            setTargetCaption(response.payload.text);
            targetCaptionRef.current = response.payload.text;
            setSessionState('AI_SPEAKING');
          } else if (response.type === 'turn_complete') {
            addLog('Turn complete.');
            const finalAiText = response.payload?.ai_text || targetCaptionRef.current;
            if (!hasAudioInTurnRef.current && turnPcmSamplesRef.current.length > 0) {
              try {
                const wavBlob = pcm16ToWavBlob(turnPcmSamplesRef.current, 24000);
                const audioUrl = URL.createObjectURL(wavBlob);
                const fallbackAudio = new Audio(audioUrl);
                fallbackAudio.volume = Math.max(0, Math.min(1, volumeRef.current / 100));
                fallbackAudio.play().catch(e => console.warn('WAV fallback play error:', e));
              } catch (wavErr) {
                console.warn('WAV conversion error:', wavErr);
              }
            } else if (!hasAudioInTurnRef.current && finalAiText && !isMutedRef.current && 'speechSynthesis' in window) {
              addLog(`TTS Fallback: speaking "${finalAiText.slice(0, 30)}..." via browser synthesis.`);
              window.speechSynthesis.cancel();
              const utter = new SpeechSynthesisUtterance(finalAiText);
              const target = detectedTargetLangRef.current || targetLangRef.current;
              utter.lang = target === 'Sinhala' ? 'si-LK' : 'ta-IN';
              utter.volume = Math.max(0, Math.min(1, volumeRef.current / 100));
              utter.onstart = () => { isAiSpeakingRef.current = true; setSessionState('AI_SPEAKING'); };
              utter.onend = () => { isAiSpeakingRef.current = false; if (isActiveSessionRef.current) setSessionState('AI_LISTENING'); };
              utter.onerror = () => { isAiSpeakingRef.current = false; if (isActiveSessionRef.current) setSessionState('AI_LISTENING'); };
              window.speechSynthesis.speak(utter);
            } else if (!isAiSpeakingRef.current) {
              if (isActiveSessionRef.current) setSessionState('AI_LISTENING');
            }
            hasAudioInTurnRef.current = false;
            nextPlaybackTimeRef.current = 0;
            turnPcmSamplesRef.current = [];
          } else if (response.type === 'lang_detected') {
            setDetectedSourceLang(response.payload.source);
            setDetectedTargetLang(response.payload.target);
            addLog(`Detected: ${response.payload.source} → ${response.payload.target}`);
          }
        } catch {
          addLog(`Raw message: ${e.data}`);
        }
      } else if (e.data instanceof ArrayBuffer) {
        playAudioChunk(e.data);
      } else if (e.data instanceof Blob) {
        e.data.arrayBuffer().then(playAudioChunk);
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
            sourceCaptionRef.current = response.payload.text;
          } else if (response.type === 'translation') {
            setTargetCaption(response.payload.text);
            targetCaptionRef.current = response.payload.text;
            setSessionState('AI_SPEAKING');
          } else if (response.type === 'turn_complete') {
            addLog('Turn complete.');
            const finalAiText = response.payload?.ai_text || targetCaptionRef.current;
            if (!hasAudioInTurnRef.current && turnPcmSamplesRef.current.length > 0) {
              try {
                const wavBlob = pcm16ToWavBlob(turnPcmSamplesRef.current, 24000);
                const audioUrl = URL.createObjectURL(wavBlob);
                const fallbackAudio = new Audio(audioUrl);
                fallbackAudio.volume = Math.max(0, Math.min(1, volumeRef.current / 100));
                fallbackAudio.play().catch(e => console.warn('WAV fallback play error:', e));
              } catch (wavErr) {
                console.warn('WAV conversion error:', wavErr);
              }
            } else if (!hasAudioInTurnRef.current && finalAiText && !isMutedRef.current && 'speechSynthesis' in window) {
              addLog(`TTS Fallback: speaking "${finalAiText.slice(0, 30)}..." via browser synthesis.`);
              window.speechSynthesis.cancel();
              const utter = new SpeechSynthesisUtterance(finalAiText);
              const target = detectedTargetLangRef.current || targetLangRef.current;
              utter.lang = target === 'Sinhala' ? 'si-LK' : 'ta-IN';
              utter.volume = Math.max(0, Math.min(1, volumeRef.current / 100));
              utter.onstart = () => { isAiSpeakingRef.current = true; setSessionState('AI_SPEAKING'); };
              utter.onend = () => { isAiSpeakingRef.current = false; if (isActiveSessionRef.current) setSessionState('AI_LISTENING'); };
              utter.onerror = () => { isAiSpeakingRef.current = false; if (isActiveSessionRef.current) setSessionState('AI_LISTENING'); };
              window.speechSynthesis.speak(utter);
            } else if (!isAiSpeakingRef.current) {
              if (isActiveSessionRef.current) setSessionState('AI_LISTENING');
            }
            hasAudioInTurnRef.current = false;
            nextPlaybackTimeRef.current = 0;
            turnPcmSamplesRef.current = [];
          } else if (response.type === 'lang_detected') {
            setDetectedSourceLang(response.payload.source);
            setDetectedTargetLang(response.payload.target);
            addLog(`Detected: ${response.payload.source} → ${response.payload.target}`);
          }
        } catch {
          addLog(`Raw message: ${e.data}`);
        }
      } else if (e.data instanceof ArrayBuffer) {
        playAudioChunk(e.data);
      } else if (e.data instanceof Blob) {
        e.data.arrayBuffer().then(playAudioChunk);
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

      // CRITICAL: Synchronously acquire/resume AudioContext during user click gesture
      // so Chrome/Safari does not suspend audio output!
      const audioCtx = ensureAudioContext();
      if (audioCtx.state === 'suspended') {
        audioCtx.resume().catch(() => {});
      }

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
      addLog('Microphone access granted.');
      pcmBufferQueueRef.current = [];
      isWsConnectingRef.current = false;
      setSourceCaption('');
      setTargetCaption('');

      addLog(`Audio context active at ${audioCtx.sampleRate}Hz.`);

      const workletUrl = getAudioWorkletUrl();
      await audioCtx.audioWorklet.addModule(workletUrl);

      const workletNode = new AudioWorkletNode(audioCtx, 'audio-recorder-processor', {
        processorOptions: { inputSampleRate: audioCtx.sampleRate }
      });
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (event: MessageEvent) => {
        // Acoustic Echo Cancellation / Ducking:
        // Do NOT send microphone input while the laptop speakers are outputting AI voice.
        // This prevents Gemini's barge-in detection from interrupting itself.
        if (isAiSpeakingRef.current) {
          return;
        }
        const pcmBuffer = event.data;
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          socketRef.current.send(pcmBuffer);
        } else if (isWsConnectingRef.current) {
          pcmBufferQueueRef.current.push(pcmBuffer);
          if (pcmBufferQueueRef.current.length > 20) {
            pcmBufferQueueRef.current.shift();
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

      // Keep worklet alive in Chrome by connecting to a silent gain node
      const silentGain = audioCtx.createGain();
      silentGain.gain.value = 0;
      workletNode.connect(silentGain);
      silentGain.connect(audioCtx.destination);
      addLog('Audio pipeline ready.');

      const currentVoiceMode = voiceModeRef.current;
      const currentTtsVoice = ttsVoiceRef.current;
      const initialVoice = currentVoiceMode === 'manual'
        ? currentTtsVoice
        : (detectedGenderRef.current === 'male' ? 'Charon' : 'Aoede');

      // Connect immediately to eliminate startup latency
      if (autoMode) {
        connectAutoWebSocket(initialVoice);
      } else {
        connectWebSocket(initialVoice, src, tgt);
      }

      // Background pitch detection to refine voice if auto mode is enabled
      if (currentVoiceMode === 'auto') {
        const pitchBuffer = new Float32Array(2048);
        const consecutiveGenders: ('male' | 'female')[] = [];

        pitchIntervalRef.current = setInterval(() => {
          if (!micAnalyserRef.current) return;
          micAnalyserRef.current.getFloatTimeDomainData(pitchBuffer);
          const pitch = autoCorrelate(pitchBuffer, audioCtx.sampleRate);

          if (pitch > 0) {
            const gender = pitch >= 160 ? 'female' : 'male';
            consecutiveGenders.push(gender);
            if (consecutiveGenders.length > 3) consecutiveGenders.shift();

            if (consecutiveGenders.length === 3 && consecutiveGenders.every(g => g === consecutiveGenders[0])) {
              if (pitchIntervalRef.current) {
                clearInterval(pitchIntervalRef.current);
                pitchIntervalRef.current = null;
              }
              const stableGender = consecutiveGenders[0];
              if (detectedGenderRef.current !== stableGender) {
                detectedGenderRef.current = stableGender;
                setDetectedGender(stableGender);
                addLog(`Detected voice profile: ${stableGender} (${Math.round(pitch)}Hz)`);
              }
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
  }, [ensureAudioContext, addLog, connectWebSocket, connectAutoWebSocket, autoMode]);

  // Full session stop: tear down everything
  const stopStream = useCallback(() => {
    isManualCloseRef.current = true;
    isActiveSessionRef.current = false;
    setIsRecording(false);
    setSessionState('IDLE');

    if (pitchIntervalRef.current) {
      clearInterval(pitchIntervalRef.current);
      pitchIntervalRef.current = null;
    }
    if (aiSpeechCooldownTimerRef.current) {
      clearTimeout(aiSpeechCooldownTimerRef.current);
      aiSpeechCooldownTimerRef.current = null;
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    isAiSpeakingRef.current = false;
    hasAudioInTurnRef.current = false;
    nextPlaybackTimeRef.current = 0;
    turnPcmSamplesRef.current = [];
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
    if (gainNodeRef.current) {
      try { gainNodeRef.current.disconnect(); } catch {}
      gainNodeRef.current = null;
    }
    if (aiAnalyserRef.current) {
      try { aiAnalyserRef.current.disconnect(); } catch {}
      aiAnalyserRef.current = null;
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

  const sendText = useCallback(async (text: string) => {
    const audioCtx = ensureAudioContext();
    if (audioCtx.state === 'suspended') {
      await audioCtx.resume().catch(() => {});
    }

    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(text);
      addLog(`Sent text: "${text}"`);
    } else {
      pendingTextRef.current = text;
      addLog(`Connecting and sending: "${text}"`);
      if (!isActiveSessionRef.current) startStream();
    }
  }, [ensureAudioContext, addLog, startStream]);

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
    playTestSound, ensureAudioContext,
  };
}

/**
 * Tamil-only voice translation mode for the app's current requirement.
 * This keeps the session pinned to Sinhala input -> Tamil output and avoids
 * the bidirectional auto-detect drift that can produce wrong languages.
 */
export function useAutoStream(volume: number = 80) {
  return useAudioStream('Sinhala', 'Tamil', false, volume);
}
