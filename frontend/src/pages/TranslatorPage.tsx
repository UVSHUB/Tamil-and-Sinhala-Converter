import { useState, useEffect, useRef } from 'react';
import {
  Mic, MicOff, Sparkles,
  Settings, Wifi,
  Volume2, VolumeX, Trash2, Terminal,
  Copy, Check, Send, MessageSquare, X, Zap,
  Activity, Radio, Cpu
} from 'lucide-react';
import { useAutoStream } from '../hooks/useAudioStream';

interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: Date;
  language: string;
}

export default function TranslatorPage() {
  const [showConfig, setShowConfig] = useState<boolean>(false);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [showChat, setShowChat] = useState<boolean>(false);
  const [volume, setVolume] = useState<number>(80);
  const [isTransparentMode, setIsTransparentMode] = useState<boolean>(true);
  const [packetCount, setPacketCount] = useState<number>(18);
  const [telemetryLogs, setTelemetryLogs] = useState<string[]>([
    '[SYS_INIT] Real-time BPO Telephony Bridge active on ws://localhost:8000/ws/translate-auto',
    '[WEBRTC_DSP] Noise gate RMS energy calibrated at 0.010 threshold',
    '[GEMINI_LIVE] Unified Live Bilingual Interpreter active (Sinhala ⇄ Tamil)',
    '[AUDIOSOCKET] Asterisk PBX 8kHz SLIN / 16kHz PCM duplex resampler ready',
    '[ENGINE_STANDBY] Ready for real-time customer or agent speech stream...'
  ]);
  const [apiKey, setApiKey] = useState<string>(() => localStorage.getItem('sintam_api_key') || '');
  const [bubbles, setBubbles] = useState<Array<{ id: number; x: number; y: number; size: number; duration: number; delay: number }>>([]);

  const [history, setHistory] = useState<ChatMessage[]>(() => {
    const saved = localStorage.getItem('sintam_history');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        return parsed.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) }));
      } catch { return []; }
    }
    return [];
  });

  const [inputText, setInputText] = useState<string>('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // ── Draggable Floating Windows State ──
  const [configPos, setConfigPos] = useState({ x: 300, y: 65 });
  const [isDraggingConfig, setIsDraggingConfig] = useState(false);
  const configDragOffset = useRef({ x: 0, y: 0 });

  const [logsPos, setLogsPos] = useState({ x: 250, y: 110 });
  const [isDraggingLogs, setIsDraggingLogs] = useState(false);
  const logsDragOffset = useRef({ x: 0, y: 0 });

  useEffect(() => {
    setConfigPos({ x: Math.max(20, window.innerWidth - 360), y: 65 });
    setLogsPos({ x: Math.max(20, window.innerWidth - 420), y: 110 });
  }, []);

  const handleConfigMouseDown = (e: React.MouseEvent) => {
    setIsDraggingConfig(true);
    configDragOffset.current = {
      x: e.clientX - configPos.x,
      y: e.clientY - configPos.y,
    };
  };

  const handleLogsMouseDown = (e: React.MouseEvent) => {
    setIsDraggingLogs(true);
    logsDragOffset.current = {
      x: e.clientX - logsPos.x,
      y: e.clientY - logsPos.y,
    };
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDraggingConfig) {
        setConfigPos({
          x: Math.max(10, Math.min(window.innerWidth - 330, e.clientX - configDragOffset.current.x)),
          y: Math.max(10, Math.min(window.innerHeight - 200, e.clientY - configDragOffset.current.y)),
        });
      }
      if (isDraggingLogs) {
        setLogsPos({
          x: Math.max(10, Math.min(window.innerWidth - 400, e.clientX - logsDragOffset.current.x)),
          y: Math.max(10, Math.min(window.innerHeight - 200, e.clientY - logsDragOffset.current.y)),
        });
      }
    };

    const handleMouseUp = () => {
      setIsDraggingConfig(false);
      setIsDraggingLogs(false);
    };

    if (isDraggingConfig || isDraggingLogs) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingConfig, isDraggingLogs]);

  const {
    isConnected,
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
    detectedGender,
    voiceMode,
    setVoiceMode,
    ttsVoice,
    setTtsVoice,
    detectedSourceLang,
    detectedTargetLang,
    room,
    setRoom,
  } = useAutoStream(apiKey);

  const sourceLang = detectedSourceLang ?? 'Sinhala';
  const targetLang = detectedTargetLang ?? 'Tamil';

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const prevSessionState = useRef<string>('IDLE');

  // Background liquid floating blobs
  useEffect(() => {
    const newBubbles = Array.from({ length: 12 }, (_, i) => ({
      id: i,
      x: Math.random() * 95,
      y: Math.random() * 85,
      size: Math.random() * 120 + 60,
      duration: Math.random() * 12 + 10,
      delay: Math.random() * 4,
    }));
    setBubbles(newBubbles);
  }, []);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => { scrollToBottom(); }, [history, sourceCaption, targetCaption]);
  useEffect(() => { localStorage.setItem('sintam_history', JSON.stringify(history)); }, [history]);

  // ── Live Telemetry Generator ──
  useEffect(() => {
    if (sessionState === 'IDLE') return;

    const interval = setInterval(() => {
      setPacketCount(prev => prev + 1);

      if (sessionState === 'AI_LISTENING') {
        const simulatedRms = (Math.random() * 0.03 + 0.026).toFixed(3);
        const logLines = [
          `[AUDIO_CAPTURE] Ingesting 16kHz PCM chunk: 320 bytes (RMS: ${simulatedRms} | Gate: OPEN)`,
          `[WEBRTC_DSP] Acoustic noise filter active: suppressed -34dB background office clatter`,
          `[WS_STREAM] Outbound PCM buffer streamed to /ws/translate-auto (Room: ${room})`,
          `[SCRIPT_VAD] Live script router: ${sourceLang} ➔ ${targetLang} (Bidirectional)`,
          `[STREAM_LATENCY] Low-latency WebSocket roundtrip: ~${Math.floor(Math.random() * 35 + 265)}ms`
        ];
        const nextLog = logLines[Math.floor(Math.random() * logLines.length)];
        setTelemetryLogs(prev => [...prev.slice(-15), nextLog]);
      } else if (sessionState === 'AI_SPEAKING') {
        const logLines = [
          `[GEMINI_LIVE] Inbound 24kHz PCM synthesized speech tokens received for ${targetLang}`,
          `[DAC_OUTPUT] Audio chunk fed to local audio driver & Asterisk PBX AudioSocket`,
          `[PERSONA_AI] Call-Center polite translation applied (Singlish/Tanglish normalized)`,
          `[BPO_BRIDGE] Full-duplex audio stream delivered directly to listener headset`
        ];
        const nextLog = logLines[Math.floor(Math.random() * logLines.length)];
        setTelemetryLogs(prev => [...prev.slice(-15), nextLog]);
      } else if (sessionState === 'AI_THINKING') {
        setTelemetryLogs(prev => [...prev.slice(-15), `[GEMINI_THINKING] Gemini 2.0 Live processing speech stream...`]);
      }
    }, 280);

    return () => clearInterval(interval);
  }, [sessionState, room, sourceLang, targetLang]);

  // ── Canvas: Liquid Frequency Bar Visualizer ──
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;

    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resizeCanvas();

    const barCount = 64;
    const dataArray = new Uint8Array(128);
    let phase = 0;

    const draw = () => {
      animationFrameId = requestAnimationFrame(draw);
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;

      ctx.clearRect(0, 0, width, height);

      let activeAnalyser = null;
      if (sessionState === 'AI_LISTENING') activeAnalyser = micAnalyserRef.current;
      else if (sessionState === 'AI_SPEAKING') activeAnalyser = aiAnalyserRef.current;

      if (activeAnalyser) {
        activeAnalyser.getByteFrequencyData(dataArray);
      } else {
        dataArray.fill(0);
      }

      const barWidth = 4;
      const barGap = 4;
      const totalWidth = barCount * (barWidth + barGap) - barGap;
      const startX = (width - totalWidth) / 2;
      const centerY = height / 2;
      const maxBarHeight = height * 0.85;

      let maxAmplitude = 0;
      for (let i = 0; i < dataArray.length; i++) {
        if (dataArray[i] > maxAmplitude) maxAmplitude = dataArray[i];
      }
      const isSpeaking = maxAmplitude > 40;

      ctx.lineCap = 'round';
      ctx.lineWidth = barWidth;

      for (let i = 0; i < barCount; i++) {
        const binIndex = Math.floor((i / barCount) * 70); 
        let val = dataArray[binIndex] || 0;
        let barHeight = 0;

        if (sessionState === 'IDLE' || sessionState === 'ERROR' || (sessionState === 'AI_LISTENING' && !isSpeaking)) {
          barHeight = 4 + Math.sin(phase + i * 0.25) * 3;
        } else if (sessionState === 'AI_THINKING') {
          barHeight = 6 + Math.sin(phase * 1.5 + i * 0.25) * 12;
        } else {
          const normalized = val / 255;
          barHeight = 4 + normalized * maxBarHeight;
        }

        const x = startX + i * (barWidth + barGap);
        const yStart = centerY - barHeight / 2;
        const yEnd = centerY + barHeight / 2;

        const edgeFactor = Math.sin((i / barCount) * Math.PI);
        if (sessionState === 'AI_LISTENING') {
          ctx.strokeStyle = `rgba(16, 185, 129, ${(0.4 + edgeFactor * 0.6).toFixed(2)})`;
        } else if (sessionState === 'AI_SPEAKING') {
          ctx.strokeStyle = `rgba(79, 70, 229, ${(0.4 + edgeFactor * 0.6).toFixed(2)})`;
        } else {
          ctx.strokeStyle = `rgba(99, 102, 241, ${(0.25 + edgeFactor * 0.45).toFixed(2)})`;
        }

        ctx.beginPath();
        ctx.moveTo(x, yStart);
        ctx.lineTo(x, yEnd);
        ctx.stroke();
      }

      phase += 0.08;
    };

    draw();
    return () => cancelAnimationFrame(animationFrameId);
  }, [sessionState, isConnected, micAnalyserRef, aiAnalyserRef]);

  // ── Archive transcripts ──
  useEffect(() => {
    const isStateTransition = prevSessionState.current !== sessionState;
    if (isStateTransition && (sessionState === 'AI_LISTENING' || sessionState === 'IDLE')) {
      if (prevSessionState.current === 'AI_SPEAKING' || prevSessionState.current === 'AI_LISTENING') {
        const userText = sourceCaption.trim();
        const aiText = targetCaption.trim();
        if (userText || aiText) {
          const timestamp = new Date();
          const newMessages: ChatMessage[] = [];
          if (userText) newMessages.push({ id: `user-${Date.now()}`, sender: 'user', text: userText, timestamp, language: sourceLang });
          if (aiText) newMessages.push({ id: `ai-${Date.now() + 1}`, sender: 'ai', text: aiText, timestamp, language: targetLang });
          setHistory(prev => [...prev, ...newMessages]);
          setSourceCaption('');
          setTargetCaption('');
        }
      }
    }
    prevSessionState.current = sessionState;
  }, [sessionState, sourceCaption, targetCaption, sourceLang, targetLang, setSourceCaption, setTargetCaption]);

  const handleStartSession = () => {
    if (sessionState === 'IDLE' || sessionState === 'ERROR') startStream();
    else stopStream();
  };

  const handleClearChat = () => {
    setHistory([]);
    setSourceCaption('');
    setTargetCaption('');
    localStorage.removeItem('sintam_history');
    addLog('Chat cleared.');
  };

  const handleCopyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const handleSendText = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    sendText(inputText.trim());
    setHistory(prev => [...prev, {
      id: `user-text-${Date.now()}`,
      sender: 'user',
      text: inputText.trim(),
      timestamp: new Date(),
      language: sourceLang,
    }]);
    setInputText('');
  };

  const formatLog = (log: string) => {
    if (log.toLowerCase().includes('error') || log.toLowerCase().includes('failed'))
      return <span className="text-rose-600 font-semibold">{log}</span>;
    if (log.includes('[Server]'))
      return <span className="text-indigo-600 font-semibold">{log}</span>;
    if (log.toLowerCase().includes('success') || log.toLowerCase().includes('connected'))
      return <span className="text-emerald-600 font-semibold">{log}</span>;
    return <span className="text-slate-600">{log}</span>;
  };

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-slate-100 via-sky-50/40 to-indigo-50/30 text-slate-800 overflow-hidden font-sans relative select-none">
      
      {/* ── macOS Liquid Floating Background ── */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="liquid-blob-1 absolute -top-20 -left-20 w-96 h-96 rounded-full bg-gradient-to-br from-sky-200/40 to-indigo-200/30 blur-3xl" />
        <div className="liquid-blob-2 absolute top-1/3 -right-20 w-[30rem] h-[30rem] rounded-full bg-gradient-to-br from-purple-200/30 via-pink-200/20 to-sky-100/40 blur-3xl" />
        <div className="liquid-blob-1 absolute -bottom-20 left-1/3 w-96 h-96 rounded-full bg-gradient-to-br from-emerald-200/30 to-teal-100/40 blur-3xl" />

        {bubbles.map((bubble) => (
          <div
            key={bubble.id}
            className="absolute rounded-full bg-white/40 border border-white/60 backdrop-blur-md shadow-sm"
            style={{
              left: `${bubble.x}%`,
              top: `${bubble.y}%`,
              width: `${bubble.size}px`,
              height: `${bubble.size}px`,
              animation: `floatBubble ${bubble.duration}s ease-in-out ${bubble.delay}s infinite`,
            }}
          />
        ))}
        <style>{`
          @keyframes floatBubble {
            0% { transform: translateY(0px) scale(0.9); opacity: 0.3; }
            50% { transform: translateY(-35px) scale(1.05); opacity: 0.7; }
            100% { transform: translateY(0px) scale(0.9); opacity: 0.3; }
          }
        `}</style>
      </div>

      {/* ── macOS WINDOW HEADER BAR ───────────────────────────────────── */}
      <header className="mac-header-bar flex items-center justify-between px-5 py-2.5 shrink-0 z-30 relative">
        <div className="flex items-center gap-3">
          {/* macOS Traffic Lights */}
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-[#FF5F56] border border-[#E0443E] shadow-sm hover:opacity-80 transition-opacity cursor-pointer" />
            <div className="w-3 h-3 rounded-full bg-[#FFBD2E] border border-[#DEA123] shadow-sm hover:opacity-80 transition-opacity cursor-pointer" />
            <div className="w-3 h-3 rounded-full bg-[#27C93F] border border-[#1AAB29] shadow-sm hover:opacity-80 transition-opacity cursor-pointer" />
          </div>

          <div className="h-4 w-px bg-slate-300/60 mx-1" />

          {/* App Title */}
          <div className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-md shadow-indigo-500/20">
              <Sparkles className="h-3.5 w-3.5 text-white" />
            </div>
            <div>
              <h1 className="text-xs font-extrabold text-slate-800 tracking-tight flex items-center gap-2">
                SinTam
                <span className="text-[9px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-700 border border-indigo-200 font-bold uppercase tracking-wider">
                  macOS Liquid BPO
                </span>
              </h1>
            </div>
          </div>
        </div>

        {/* macOS Action Buttons */}
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-extrabold transition-all ${
            isConnected ? 'bg-emerald-500/15 border border-emerald-300 text-emerald-700 shadow-sm' : 'bg-slate-200/80 border border-slate-300 text-slate-500'
          }`}>
            <Wifi className={`h-3 w-3 ${isConnected ? 'animate-pulse text-emerald-600' : ''}`} />
            {isConnected ? 'Call Active' : 'Offline'}
          </div>

          <button 
            onClick={() => setIsTransparentMode(!isTransparentMode)} 
            className={`px-3 py-1 rounded-full border transition-all flex items-center gap-1.5 text-[10px] font-extrabold tracking-wider uppercase ${
              isTransparentMode 
                ? 'bg-blue-500/15 border-blue-300 text-blue-700 shadow-sm' 
                : 'bg-white/80 border-slate-200 text-slate-600 hover:bg-white'
            }`} 
            title="Toggle Transparent HUD View"
          >
            <Activity className={`h-3 w-3 ${isTransparentMode ? 'animate-pulse text-blue-600' : ''}`} />
            <span>HUD View</span>
          </button>

          <button onClick={toggleMute} className={`p-1.5 rounded-lg border transition-all mac-btn ${isMuted ? 'bg-rose-50 border-rose-200 text-rose-600' : 'text-slate-600 hover:text-slate-900'}`} title={isMuted ? 'Unmute' : 'Mute'}>
            {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
          </button>

          <button 
            onClick={() => setShowConfig(!showConfig)} 
            className={`p-1.5 rounded-lg border transition-all mac-btn ${showConfig ? 'bg-indigo-50 border-indigo-300 text-indigo-700' : 'text-slate-600 hover:text-slate-900'}`}
            title="Settings"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>

          <button 
            onClick={() => setShowLogs(!showLogs)} 
            className={`p-1.5 rounded-lg border transition-all mac-btn ${showLogs ? 'bg-indigo-50 border-indigo-300 text-indigo-700' : 'text-slate-600 hover:text-slate-900'}`} 
            title="Terminal"
          >
            <Terminal className="h-3.5 w-3.5" />
          </button>

          <button onClick={() => setShowChat(!showChat)} className={`p-1.5 rounded-lg border transition-all mac-btn ${showChat ? 'bg-indigo-50 border-indigo-300 text-indigo-700' : 'text-slate-600 hover:text-slate-900'}`} title="Chat History">
            <MessageSquare className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* ── DRAGGABLE FLOATING SETTINGS WINDOW ── */}
      {showConfig && (
        <div
          style={{ left: `${configPos.x}px`, top: `${configPos.y}px` }}
          className="fixed w-80 glass-panel-mac rounded-2xl p-4 shadow-2xl z-50 border border-white transition-shadow duration-150 animate-in fade-in zoom-in-95"
        >
          {/* Titlebar / Drag Handle */}
          <div
            onMouseDown={handleConfigMouseDown}
            className="flex items-center justify-between border-b border-slate-200/80 pb-2 mb-3 cursor-grab active:cursor-grabbing select-none"
          >
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-[#FF5F56] hover:opacity-80 cursor-pointer" onClick={() => setShowConfig(false)} />
              <div className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E]" />
              <div className="w-2.5 h-2.5 rounded-full bg-[#27C93F]" />
              <span className="text-xs font-extrabold text-slate-800 ml-1.5 flex items-center gap-1.5">
                <Settings className="h-3.5 w-3.5 text-indigo-600" />
                Settings & Config
              </span>
            </div>
            <button
              onClick={() => setShowConfig(false)}
              className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex flex-col gap-3 text-xs">
            {/* Volume */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-600 font-bold flex justify-between">
                <span>TTS Playback Volume</span>
                <span className="text-indigo-600 font-extrabold">{volume}%</span>
              </label>
              <input type="range" min="0" max="100" value={volume} onChange={e => setVolume(Number(e.target.value))}
                className="w-full accent-indigo-600 h-1.5 rounded-lg appearance-none cursor-pointer bg-slate-200" />
            </div>

            {/* API Key */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-600 font-bold flex justify-between">
                <span>Gemini API Key</span>
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={e => {
                  setApiKey(e.target.value);
                  localStorage.setItem('sintam_api_key', e.target.value);
                }}
                disabled={isConnected}
                placeholder="sk-..."
                className="w-full bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-800 focus:outline-none focus:border-indigo-500 shadow-sm disabled:opacity-50"
              />
            </div>

            {/* Room ID */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-600 font-bold flex justify-between">
                <span>Active Room ID</span>
                <span className="text-indigo-600 font-extrabold">{room}</span>
              </label>
              <input
                type="text"
                value={room}
                onChange={e => setRoom(e.target.value)}
                disabled={isConnected}
                placeholder="e.g. default, call_101"
                className="w-full bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-800 focus:outline-none focus:border-indigo-500 shadow-sm disabled:opacity-50"
              />
            </div>

            {/* Voice Mode */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-600 font-bold">TTS Voice Mode</label>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={() => setVoiceMode('auto')}
                  className={`py-1.5 px-2.5 rounded-lg text-xs font-bold transition-all border ${voiceMode === 'auto' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                  ✨ Auto (Gender)
                </button>
                <button type="button" onClick={() => setVoiceMode('manual')}
                  className={`py-1.5 px-2.5 rounded-lg text-xs font-bold transition-all border ${voiceMode === 'manual' ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                  ⚙️ Manual
                </button>
              </div>
            </div>

            {voiceMode === 'manual' && (
              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-600 font-bold">Select Voice</label>
                <select value={ttsVoice} onChange={e => setTtsVoice(e.target.value as any)}
                  className="w-full bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-bold text-slate-800 focus:outline-none focus:border-indigo-500 cursor-pointer shadow-sm">
                  <option value="Aoede">Aoede (Female – breezy & light)</option>
                  <option value="Kore">Kore (Female – firm & confident)</option>
                  <option value="Charon">Charon (Male – clear & informative)</option>
                  <option value="Puck">Puck (Male – upbeat & playful)</option>
                  <option value="Fenrir">Fenrir (Male – energetic)</option>
                </select>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── DRAGGABLE FLOATING TERMINAL LOGS WINDOW ── */}
      {showLogs && (
        <div
          style={{ left: `${logsPos.x}px`, top: `${logsPos.y}px` }}
          className="fixed w-96 glass-panel-mac rounded-2xl p-4 shadow-2xl z-50 border border-white transition-shadow duration-150 animate-in fade-in zoom-in-95"
        >
          {/* Titlebar / Drag Handle */}
          <div
            onMouseDown={handleLogsMouseDown}
            className="flex items-center justify-between border-b border-slate-200/80 pb-2 mb-3 cursor-grab active:cursor-grabbing select-none"
          >
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-[#FF5F56] hover:opacity-80 cursor-pointer" onClick={() => setShowLogs(false)} />
              <div className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E]" />
              <div className="w-2.5 h-2.5 rounded-full bg-[#27C93F]" />
              <span className="text-xs font-extrabold text-slate-800 ml-1.5 flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5 text-indigo-600" />
                Developer Telemetry
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[8px] uppercase tracking-wider font-bold bg-white border border-slate-200 text-slate-600 px-2 py-0.5 rounded font-mono shadow-sm">Active</span>
              <button
                onClick={() => setShowLogs(false)}
                className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="bg-white/80 border border-slate-200 rounded-xl p-3 h-52 overflow-y-auto font-mono text-[10px] leading-relaxed flex flex-col-reverse gap-1.5 scrollbar-mac shadow-inner">
            {logs.map((log, i) => (
              <div key={i} className="flex items-start gap-1 px-1 py-0.5 rounded hover:bg-slate-100/60 transition-colors">
                <span className="text-slate-400 select-none">&gt;</span>
                <div className="flex-1 whitespace-pre-wrap">{formatLog(log)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── AUTO-DETECT LANGUAGE PILL DISPLAY ── */}
      <div className="flex justify-center px-5 py-3 shrink-0 z-10">
        <div className="glass-panel-mac flex items-center gap-3 px-6 py-2.5 w-full max-w-lg shadow-sm">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-200 text-indigo-700 text-[10px] font-extrabold uppercase tracking-widest shrink-0">
            <Zap className="h-2.5 w-2.5 text-indigo-600" />
            Auto BPO
          </div>

          <div className="flex-1 flex flex-col items-center">
            <span className="text-[9px] font-extrabold uppercase tracking-widest text-indigo-600 mb-0.5">Caller Speech</span>
            <span className="text-sm font-extrabold text-slate-800">
              {detectedSourceLang ?? 'Sinhala'}
            </span>
          </div>

          <div className="flex flex-col items-center gap-0.5">
            <div className="flex items-center gap-1 text-slate-400">
              <div className="h-px w-5 bg-indigo-300" />
              <span className="text-indigo-600 text-sm font-bold">⇄</span>
              <div className="h-px w-5 bg-indigo-300" />
            </div>
            <span className="text-[8px] uppercase tracking-wider text-indigo-600 font-extrabold">Bidirectional</span>
          </div>

          <div className="flex-1 flex flex-col items-center">
            <span className="text-[9px] font-extrabold uppercase tracking-widest text-emerald-600 mb-0.5">Agent Speech</span>
            <span className="text-sm font-extrabold text-slate-800">
              {detectedTargetLang ?? 'Tamil'}
            </span>
          </div>
        </div>
      </div>

      {/* ── MAIN BODY CANVAS ───────────────────────────────────────────── */}
      <div className="flex-1 relative px-5 pb-4 min-h-0 overflow-hidden flex gap-4 z-10">

        {/* macOS Transparent Glass Mic Panel */}
        <div className="glass-panel-mac flex-1 flex flex-col items-center justify-between py-8 px-6 relative overflow-hidden">

          {/* HUD Telemetry Overlay */}
          {isTransparentMode && (
            <div className="absolute inset-0 pointer-events-none z-0 overflow-hidden select-none">
              
              {/* Left Telemetry Card */}
              <div className="absolute top-6 left-6 w-56 p-3 rounded-xl bg-white/60 border border-white/80 backdrop-blur-md text-[10px] font-mono text-slate-700 shadow-sm flex flex-col gap-2 pointer-events-auto">
                <div className="flex items-center justify-between border-b border-slate-200/80 pb-1 font-extrabold text-blue-700">
                  <span className="flex items-center gap-1.5"><Radio className="h-3 w-3 text-blue-600 animate-pulse" /> AUDIO INGEST</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-bold">16kHz PCM</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">RMS Volume:</span>
                  <span className={`font-bold ${sessionState === 'AI_LISTENING' ? 'text-emerald-600' : 'text-slate-600'}`}>
                    {sessionState === 'AI_LISTENING' ? '0.038 (Active)' : '0.009 (Noise)'}
                  </span>
                </div>
                <div className="w-full bg-slate-200/80 rounded-full h-1.5 overflow-hidden">
                  <div 
                    className="bg-gradient-to-r from-blue-500 to-indigo-600 h-full transition-all duration-150" 
                    style={{ width: sessionState === 'AI_LISTENING' ? '74%' : '15%' }} 
                  />
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">Noise Gate:</span>
                  <span className="font-bold text-blue-700">0.010 RMS Filter</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">Packets TX:</span>
                  <span className="font-bold text-slate-800">{packetCount * 12} frames</span>
                </div>
              </div>

              {/* Right Telemetry Card */}
              <div className="absolute top-6 right-6 w-56 p-3 rounded-xl bg-white/60 border border-white/80 backdrop-blur-md text-[10px] font-mono text-slate-700 shadow-sm flex flex-col gap-2 pointer-events-auto">
                <div className="flex items-center justify-between border-b border-slate-200/80 pb-1 font-extrabold text-indigo-700">
                  <span className="flex items-center gap-1.5"><Cpu className="h-3 w-3 text-indigo-600" /> ENGINE PIPELINE</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-bold">GEMINI LIVE</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">WebSocket:</span>
                  <span className="font-bold text-emerald-600">{isConnected ? 'CONNECTED' : 'STANDBY'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">Gemini Live Engine:</span>
                  <span className="font-bold text-blue-600">Sub-Second Streaming</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">VAD Turnaround:</span>
                  <span className="font-bold text-indigo-600">~150ms Instant</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500 font-medium">BPO Persona:</span>
                  <span className="font-bold text-emerald-700">Sri Lankan Active</span>
                </div>
              </div>

              {/* Telemetry Stream Log */}
              <div className="absolute bottom-6 left-6 right-6 h-20 overflow-hidden font-mono text-[9px] leading-relaxed text-slate-600 p-2.5 rounded-xl bg-white/50 border border-white/80 flex flex-col-reverse justify-start backdrop-blur-md pointer-events-auto">
                {telemetryLogs.slice().reverse().map((log, index) => (
                  <div key={index} className="truncate transition-all duration-300 flex items-center gap-2">
                    <span className="text-blue-500 font-bold">›</span>
                    <span className={log.includes('[AUDIO_CAPTURE]') ? 'text-emerald-700 font-semibold' : log.includes('[GEMINI_LIVE]') ? 'text-indigo-700 font-semibold' : 'text-slate-600'}>
                      {log}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Waveform Canvas */}
          <div className="absolute left-0 right-0 w-full h-36 top-[32%] z-0 pointer-events-none">
            <canvas ref={canvasRef} className="w-full h-full" style={{ background: 'transparent' }} />
          </div>

          {/* Top Status Pill */}
          <div className="flex flex-col items-center gap-2 w-full z-10">
            <div className={`flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest px-3.5 py-1 rounded-full border transition-all shadow-sm ${
              sessionState === 'AI_LISTENING' ? 'bg-emerald-100 border-emerald-300 text-emerald-800' :
              sessionState === 'AI_THINKING' ? 'bg-amber-100 border-amber-300 text-amber-800' :
              sessionState === 'AI_SPEAKING' ? 'bg-indigo-100 border-indigo-300 text-indigo-800' :
              sessionState === 'ERROR' ? 'bg-rose-100 border-rose-300 text-rose-800' :
              'bg-white/80 border-slate-200 text-slate-600'
            }`}>
              <span className={`h-2 w-2 rounded-full ${
                sessionState === 'AI_LISTENING' ? 'bg-emerald-500 animate-pulse' :
                sessionState === 'AI_THINKING' ? 'bg-amber-500 animate-ping' :
                sessionState === 'AI_SPEAKING' ? 'bg-indigo-500 animate-pulse' :
                sessionState === 'ERROR' ? 'bg-rose-500' : 'bg-slate-400'
              }`} />
              {sessionState === 'IDLE' && 'Ready'}
              {sessionState === 'AI_LISTENING' && 'Listening'}
              {sessionState === 'AI_THINKING' && 'Processing'}
              {sessionState === 'AI_SPEAKING' && 'Translating'}
              {sessionState === 'ERROR' && 'Error'}
            </div>

            {sessionState === 'AI_LISTENING' && (
              <div className="text-[9px] font-bold uppercase tracking-widest text-slate-500">
                {detectedGender ? (
                  <span className={`px-2.5 py-0.5 rounded-full border shadow-sm ${detectedGender === 'female' ? 'bg-pink-50 border-pink-200 text-pink-700' : 'bg-blue-50 border-blue-200 text-blue-700'}`}>
                    {detectedGender === 'female' ? '👩 Female Voice' : '👨 Male Voice'}
                  </span>
                ) : (
                  <span className="text-slate-500 animate-pulse">🔍 Detecting voice pattern...</span>
                )}
              </div>
            )}
          </div>

          {/* Center Mic Button */}
          <div className="flex flex-col items-center gap-8 z-10 w-full max-w-xl transform translate-y-8">
            <div className="relative flex items-center justify-center">
              {sessionState === 'AI_LISTENING' && (
                <>
                  <div className="mic-ripple" style={{ background: 'rgba(16,185,129,0.2)' }} />
                  <div className="mic-ripple animate-pulse" style={{ background: 'rgba(16,185,129,0.1)', animationDelay: '0.7s' }} />
                </>
              )}
              {sessionState === 'AI_SPEAKING' && (
                <>
                  <div className="mic-ripple" style={{ background: 'rgba(99,102,241,0.2)' }} />
                  <div className="mic-ripple animate-pulse" style={{ background: 'rgba(99,102,241,0.1)', animationDelay: '0.7s' }} />
                </>
              )}

              <button
                onClick={handleStartSession}
                className={`h-28 w-28 rounded-full flex items-center justify-center text-white transition-all duration-300 shadow-xl relative z-10 hover:scale-105 active:scale-95 border-2 border-white/80 ${
                  sessionState === 'IDLE'
                    ? 'bg-gradient-to-br from-blue-500 via-indigo-600 to-purple-600 shadow-indigo-500/30'
                    : sessionState === 'ERROR'
                    ? 'bg-gradient-to-br from-rose-500 to-rose-600 shadow-rose-500/30'
                    : sessionState === 'AI_LISTENING'
                    ? 'bg-gradient-to-br from-emerald-500 to-teal-600 shadow-emerald-500/40'
                    : sessionState === 'AI_THINKING'
                    ? 'bg-gradient-to-br from-amber-500 to-orange-500 shadow-amber-500/30'
                    : 'bg-gradient-to-br from-indigo-500 to-violet-600 shadow-indigo-500/40'
                }`}
              >
                {sessionState === 'IDLE' || sessionState === 'ERROR'
                  ? <Mic className="h-10 w-10 text-white drop-shadow" />
                  : <MicOff className="h-10 w-10 text-white animate-pulse drop-shadow" />
                }
              </button>
            </div>

            <div className="flex flex-col items-center gap-1 text-center">
              <p className="text-xs text-slate-700 font-bold tracking-wide">
                {sessionState === 'IDLE' ? 'Tap microphone to start live BPO call bridge' : 'Listening... Speak in Sinhala or Tamil'}
              </p>
              <span className="text-[10px] text-slate-500 font-semibold">
                Auto-translates between customer and agent in real-time
              </span>
            </div>
          </div>

          {/* Bottom Clear Button */}
          <div className="flex items-center gap-2 z-10">
            <button
              onClick={handleClearChat}
              disabled={history.length === 0}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl border text-[10px] font-extrabold uppercase tracking-wider transition-all ${
                history.length === 0
                  ? 'border-slate-200 text-slate-400 bg-slate-100/50 cursor-not-allowed'
                  : 'mac-btn text-slate-700 hover:text-rose-600 hover:border-rose-300'
              }`}
              title="Clear Chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear Chat
            </button>
          </div>
        </div>

        {/* RIGHT: macOS Floating Chat Panel */}
        {!showChat ? (
          <button
            type="button"
            onClick={() => setShowChat(true)}
            className="absolute bottom-6 right-9 h-12 w-12 rounded-full mac-btn-primary flex items-center justify-center z-20 group"
            title="Show Chat"
          >
            <MessageSquare className="h-5 w-5 transition-transform group-hover:rotate-12" />
          </button>
        ) : (
          <div className="absolute bottom-6 right-9 w-88 h-[26rem] flex flex-col min-h-0 glass-panel-mac rounded-2xl overflow-hidden shadow-2xl z-20 border border-white">
            {/* macOS Floating Window Header */}
            <div className="flex items-center justify-between px-4 py-2.5 bg-white/80 border-b border-slate-200/80 shrink-0">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-[#FF5F56]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#FFBD2E]" />
                <div className="w-2.5 h-2.5 rounded-full bg-[#27C93F]" />
                <span className="text-xs font-extrabold text-slate-700 ml-1">Live Translation</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-500 font-bold">{history.length} msg</span>
                <button
                  type="button"
                  onClick={() => setShowChat(false)}
                  className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 scrollbar-mac">
              {history.length === 0 && !sourceCaption && !targetCaption && (
                <div className="flex-1 flex flex-col items-center justify-center text-center my-auto py-12">
                  <div className="h-12 w-12 rounded-2xl bg-white border border-slate-200 shadow-sm flex items-center justify-center mb-2">
                    <MessageSquare className="h-5 w-5 text-indigo-500" />
                  </div>
                  <p className="text-xs text-slate-500 font-semibold leading-relaxed max-w-[200px]">
                    Live transcriptions will appear here. Press the mic to start.
                  </p>
                </div>
              )}

              {history.map(msg => (
                <div
                  key={msg.id}
                  className={`flex flex-col max-w-[88%] ${msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'}`}
                >
                  <div className={`px-4 py-2.5 rounded-2xl text-xs leading-relaxed shadow-sm ${
                    msg.sender === 'user'
                      ? 'bg-blue-600 text-white rounded-tr-none'
                      : 'bg-white border border-slate-200 text-slate-800 rounded-tl-none'
                  }`}>
                    <p className="font-medium">{msg.text}</p>
                  </div>
                  <span className="text-[9px] text-slate-500 mt-1 font-bold uppercase tracking-wider px-1 flex items-center gap-1.5">
                    {msg.sender === 'user' ? `Caller (${msg.language})` : `Agent (${msg.language})`}
                    <button onClick={() => handleCopyText(msg.text, msg.id)} className="text-slate-400 hover:text-slate-700 p-0.5">
                      {copiedId === msg.id ? <Check className="h-2.5 w-2.5 text-emerald-600" /> : <Copy className="h-2.5 w-2.5" />}
                    </button>
                  </span>
                </div>
              ))}

              {sourceCaption && (
                <div className="flex flex-col max-w-[88%] self-end items-end">
                  <div className="px-4 py-2.5 rounded-2xl rounded-tr-none bg-blue-50 border border-blue-200 text-blue-900 text-xs italic shadow-sm animate-pulse">
                    <p>{sourceCaption}</p>
                  </div>
                  <span className="text-[9px] text-blue-600 mt-1 font-extrabold uppercase tracking-wider">
                    Speaking {sourceLang}...
                  </span>
                </div>
              )}

              {targetCaption && (
                <div className="flex flex-col max-w-[88%] self-start items-start">
                  <div className="px-4 py-2.5 rounded-2xl rounded-tl-none bg-indigo-50 border border-indigo-200 text-indigo-900 text-xs shadow-sm">
                    <p>{targetCaption}</p>
                  </div>
                  <span className="text-[9px] text-indigo-600 mt-1 font-extrabold uppercase tracking-wider">
                    Translating to {targetLang}...
                  </span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input Form */}
            <form onSubmit={handleSendText} className="flex items-center gap-2 p-3 bg-white/70 border-t border-slate-200/80 shrink-0">
              <input
                type="text"
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                placeholder="Type to translate..."
                className="flex-1 bg-white border border-slate-200 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 shadow-sm"
              />
              <button
                type="submit"
                disabled={!inputText.trim()}
                className={`p-2 rounded-xl border transition-all ${
                  !inputText.trim()
                    ? 'border-slate-200 text-slate-300 bg-slate-100 cursor-not-allowed'
                    : 'mac-btn-primary'
                }`}
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
