import { useState, useEffect, useRef } from 'react';
import {
  Mic, MicOff, Sparkles, RefreshCw,
  Settings, Wifi, ShieldAlert,
  Volume2, VolumeX, Trash2, Terminal,
  Copy, Check, Send, MessageSquare, X,
} from 'lucide-react';
import { useAudioStream } from '../hooks/useAudioStream';

interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: Date;
  language: string;
}

const LANGUAGES = [
  { code: 'Sinhala', name: 'Sinhala' },
  { code: 'Tamil', name: 'Tamil' },
  { code: 'English', name: 'English' },
  { code: 'Korean', name: 'Korean' },
  { code: 'Spanish', name: 'Spanish' },
  { code: 'Japanese', name: 'Japanese' },
  { code: 'Chinese', name: 'Chinese' },
  { code: 'French', name: 'French' },
  { code: 'German', name: 'German' },
];

export default function TranslatorPage() {
  const [sourceLang, setSourceLang] = useState<string>('Sinhala');
  const [targetLang, setTargetLang] = useState<string>('Tamil');
  const [showConfig, setShowConfig] = useState<boolean>(false);
  const [showLogs, setShowLogs] = useState<boolean>(false);
  const [showChat, setShowChat] = useState<boolean>(false);
  const [volume, setVolume] = useState<number>(80);

  const sourceLangArchiveRef = useRef<string>('Sinhala');
  const targetLangArchiveRef = useRef<string>('Tamil');
  useEffect(() => { sourceLangArchiveRef.current = sourceLang; }, [sourceLang]);
  useEffect(() => { targetLangArchiveRef.current = targetLang; }, [targetLang]);

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
  } = useAudioStream(sourceLang, targetLang);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const prevSessionState = useRef<string>('IDLE');

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => { scrollToBottom(); }, [history, sourceCaption, targetCaption]);
  useEffect(() => { localStorage.setItem('sintam_history', JSON.stringify(history)); }, [history]);

  // ── Spacebar shortcut: toggle recording when focus is not in a text field ─
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return;
      const tag = (e.target as HTMLElement).tagName.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      e.preventDefault(); // prevent page scroll
      handleStartSession();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionState]);

  // ── Canvas: Mirrored frequency bar visualizer ─────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;

    // Resize canvas pixel buffer to match CSS size × DPR — called once per
    // resize event so ctx.scale() is never stacked across effect re-runs.
    const syncCanvasSize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      const w = Math.round(rect.width * dpr);
      const h = Math.round(rect.height * dpr);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    };
    syncCanvasSize();

    const resizeObserver = new ResizeObserver(syncCanvasSize);
    resizeObserver.observe(canvas);

    const barCount = 64;
    // 128 bins gives enough resolution to downsample smoothly across barCount
    const dataArray = new Uint8Array(128);
    let phase = 0;

    const draw = () => {
      animationFrameId = requestAnimationFrame(draw);

      const dpr = window.devicePixelRatio || 1;
      // Draw in physical pixels — no ctx.scale() needed
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;

      // Scale the context to physical pixels for crisp rendering
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Transparent clear so it floats on the slate-950 background
      ctx.clearRect(0, 0, width, height);

      // Pick the right analyser based on current session state
      let activeAnalyser: AnalyserNode | null = null;
      if (sessionState === 'AI_LISTENING') activeAnalyser = micAnalyserRef.current;
      else if (sessionState === 'AI_SPEAKING') activeAnalyser = aiAnalyserRef.current;

      if (activeAnalyser) {
        // Real-time frequency amplitude from the microphone / AI audio
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

      ctx.lineCap = 'round';
      ctx.lineWidth = barWidth;

      for (let i = 0; i < barCount; i++) {
        // Map bar index into the lower-mid voice frequency bins (0–70 of 128)
        const binIndex = Math.floor((i / barCount) * 70);
        const val = dataArray[binIndex] || 0;

        let barHeight: number;

        if (sessionState === 'IDLE' || sessionState === 'ERROR') {
          // Subtle ambient idle ripple
          barHeight = 4 + Math.sin(phase + i * 0.25) * 3;
        } else if (sessionState === 'AI_THINKING') {
          // Smooth loading wave
          barHeight = 6 + Math.sin(phase * 1.5 + i * 0.25) * 12;
        } else {
          // AI_LISTENING / AI_SPEAKING: height driven by live frequency data
          const normalized = val / 255;
          barHeight = 4 + normalized * maxBarHeight;
        }

        const x = startX + i * (barWidth + barGap);
        const yStart = centerY - barHeight / 2;
        const yEnd = centerY + barHeight / 2;

        // Opacity envelope: brighter in the centre, softer at the edges
        const edgeFactor = Math.sin((i / barCount) * Math.PI);
        ctx.strokeStyle = `rgba(255,255,255,${(0.3 + edgeFactor * 0.7).toFixed(2)})`;

        ctx.beginPath();
        ctx.moveTo(x, yStart);
        ctx.lineTo(x, yEnd);
        ctx.stroke();
      }

      phase += 0.08;
    };

    draw();

    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
    };
  }, [sessionState, isConnected, micAnalyserRef, aiAnalyserRef]);

  // ── Archive transcripts on turn complete ───────────────────────────────
  useEffect(() => {
    const isStateTransition = prevSessionState.current !== sessionState;
    if (isStateTransition && (sessionState === 'AI_LISTENING' || sessionState === 'IDLE')) {
      if (prevSessionState.current === 'AI_SPEAKING' || prevSessionState.current === 'AI_LISTENING') {
        const userText = sourceCaption.trim();
        const aiText = targetCaption.trim();
        if (userText || aiText) {
          const timestamp = new Date();
          const newMessages: ChatMessage[] = [];
          const currentSrc = sourceLangArchiveRef.current;
          const currentTgt = targetLangArchiveRef.current;
          if (userText) newMessages.push({ id: `user-${Date.now()}`, sender: 'user', text: userText, timestamp, language: currentSrc });
          if (aiText) newMessages.push({ id: `ai-${Date.now() + 1}`, sender: 'ai', text: aiText, timestamp, language: currentTgt });
          setHistory(prev => [...prev, ...newMessages]);
          setSourceCaption('');
          setTargetCaption('');
        }
      }
    }
    prevSessionState.current = sessionState;
  }, [sessionState, sourceCaption, targetCaption, setSourceCaption, setTargetCaption]);

  const handleStartSession = () => {
    if (sessionState === 'IDLE' || sessionState === 'ERROR') startStream();
    else stopStream();
  };

  const handleSwapLanguages = () => {
    const temp = sourceLang;
    setSourceLang(targetLang);
    setTargetLang(temp);
    setSourceCaption('');
    setTargetCaption('');
    addLog(`Swapped: ${targetLang} ↔ ${temp}`);
  };

  const handleClearChat = () => {
    setHistory([]);
    setSourceCaption('');
    setTargetCaption('');
    localStorage.removeItem('sintam_history');
    addLog('Chat cleared.');
  };

  const handleDeleteMessage = (id: string) => {
    setHistory(prev => prev.filter(m => m.id !== id));
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
    if (log.toLowerCase().includes('error') || log.toLowerCase().includes('failed') || log.toLowerCase().includes('terminated'))
      return <span className="text-rose-400 font-medium">{log}</span>;
    if (log.includes('[Server]'))
      return <span className="text-indigo-400">{log}</span>;
    if (log.toLowerCase().includes('established') || log.toLowerCase().includes('granted') || log.toLowerCase().includes('success') || log.toLowerCase().includes('reconnected') || log.toLowerCase().includes('connected'))
      return <span className="text-emerald-400 font-medium">{log}</span>;
    return <span className="text-slate-400">{log}</span>;
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 overflow-hidden font-sans">

      {/* ── HEADER ───────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Sparkles className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
              SinTam
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold uppercase tracking-wider">Live</span>
            </h1>
            <p className="text-[10px] text-slate-500">Real-Time Voice Translator</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Connection pill */}
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold transition-all ${isConnected ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-400' : 'bg-slate-800 border border-slate-700 text-slate-500'}`}>
            <Wifi className={`h-3 w-3 ${isConnected ? 'animate-pulse' : ''}`} />
            {isConnected ? 'Live' : 'Offline'}
          </div>
          <button onClick={toggleMute} className={`p-1.5 rounded-lg border transition-all ${isMuted ? 'bg-rose-500/15 border-rose-500/30 text-rose-400' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`} title={isMuted ? 'Unmute' : 'Mute'}>
            {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
          </button>
          <button onClick={() => setShowConfig(!showConfig)} className={`p-1.5 rounded-lg border transition-all ${showConfig ? 'bg-indigo-500/15 border-indigo-500/30 text-indigo-400' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`}>
            <Settings className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => setShowLogs(!showLogs)} className={`p-1.5 rounded-lg border transition-all ${showLogs ? 'bg-indigo-500/15 border-indigo-500/30 text-indigo-400' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`} title="Terminal">
            <Terminal className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => setShowChat(!showChat)} className={`p-1.5 rounded-lg border transition-all ${showChat ? 'bg-indigo-500/15 border-indigo-500/30 text-indigo-400' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`} title="Chat History">
            <MessageSquare className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* ── LANGUAGE SELECTOR (top center) ───────────────────── */}
      <div className="flex justify-center px-5 py-4 shrink-0">
        <div className="flex items-center gap-3 bg-slate-900 border border-slate-700/60 rounded-2xl px-4 py-3 shadow-xl shadow-black/30 w-full max-w-lg">
          {/* Source */}
          <div className="flex-1 relative">
            <label className="block text-[9px] font-bold uppercase tracking-widest text-indigo-400 mb-1 pl-0.5">From</label>
            <div className="relative">
              <select
                value={sourceLang}
                onChange={e => setSourceLang(e.target.value)}
                aria-label="Source language — translate from"
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-xs font-bold text-white focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all appearance-none cursor-pointer"
              >
                {LANGUAGES.map(l => <option key={l.code} value={l.code} className="bg-slate-800">{l.name}</option>)}
              </select>
              <div className="absolute inset-y-0 right-2.5 flex items-center pointer-events-none text-indigo-400">
                <svg className="w-3 h-3 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" /></svg>
              </div>
            </div>
          </div>

          {/* Swap button */}
          <div className="flex flex-col items-center gap-0.5 pt-4">
            <button onClick={handleSwapLanguages} aria-label="Swap source and target languages" className="p-2 rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:border-indigo-500/50 hover:bg-indigo-500/10 transition-all hover:scale-110 active:scale-95 shadow-md">
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>

          {/* Target */}
          <div className="flex-1 relative">
            <label className="block text-[9px] font-bold uppercase tracking-widest text-emerald-400 mb-1 pl-0.5">To</label>
            <div className="relative">
              <select
                value={targetLang}
                onChange={e => setTargetLang(e.target.value)}
                aria-label="Target language — translate to"
                className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-xs font-bold text-white focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-all appearance-none cursor-pointer"
              >
                {LANGUAGES.map(l => <option key={l.code} value={l.code} className="bg-slate-800">{l.name}</option>)}
              </select>
              <div className="absolute inset-y-0 right-2.5 flex items-center pointer-events-none text-emerald-400">
                <svg className="w-3 h-3 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" /></svg>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── MAIN BODY (large mic screen + floating chat in corner) ──────────── */}
      <div className="flex-1 relative px-5 pb-4 min-h-0 overflow-hidden flex gap-4">

        {/* LARGE: Dark Mic Panel (Fills the screen) */}
        <div className="flex-1 flex flex-col items-center justify-between bg-slate-950 border border-slate-800 rounded-2xl py-8 px-6 shadow-2xl shadow-black/50 relative overflow-hidden">

          {/* Background radial glow behind mic */}
          <div className={`absolute inset-0 transition-all duration-700 pointer-events-none ${
            sessionState === 'AI_LISTENING' ? 'bg-[radial-gradient(ellipse_at_center,rgba(16,185,129,0.08)_0%,transparent_70%)]' :
            sessionState === 'AI_SPEAKING' ? 'bg-[radial-gradient(ellipse_at_center,rgba(99,102,241,0.08)_0%,transparent_70%)]' :
            sessionState === 'AI_THINKING' ? 'bg-[radial-gradient(ellipse_at_center,rgba(245,158,11,0.06)_0%,transparent_70%)]' :
            'bg-[radial-gradient(ellipse_at_center,rgba(30,41,59,0.5)_0%,transparent_70%)]'
          }`} />

          {/* Waveform canvas — full screen length, absolutely positioned underneath other elements */}
          <div className="absolute left-0 right-0 w-full h-36 top-[32%] z-0 pointer-events-none">
            <canvas ref={canvasRef} className="w-full h-full" style={{ background: 'transparent' }} />
          </div>

          {/* Top: status badge */}
          <div className="flex flex-col items-center gap-2 w-full z-10">
            <div
              role="status"
              aria-live="polite"
              aria-atomic="true"
              className={`flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest px-3 py-1 rounded-full border transition-all duration-300 ${
              sessionState === 'AI_LISTENING' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' :
              sessionState === 'AI_THINKING' ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' :
              sessionState === 'AI_SPEAKING' ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400' :
              sessionState === 'ERROR' ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' :
              'bg-slate-800/80 border-slate-700 text-slate-500'
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${
                sessionState === 'AI_LISTENING' ? 'bg-emerald-500 animate-pulse' :
                sessionState === 'AI_THINKING' ? 'bg-amber-500 animate-ping' :
                sessionState === 'AI_SPEAKING' ? 'bg-indigo-500 animate-pulse' :
                sessionState === 'ERROR' ? 'bg-rose-500' : 'bg-slate-600'
              }`} />
              {sessionState === 'IDLE' && 'Ready'}
              {sessionState === 'AI_LISTENING' && 'Listening'}
              {sessionState === 'AI_THINKING' && 'Processing'}
              {sessionState === 'AI_SPEAKING' && 'Translating'}
              {sessionState === 'ERROR' && 'Error'}
            </div>

            {/* Gender detection */}
            {sessionState === 'AI_LISTENING' && (
              <div className="text-[9px] font-bold uppercase tracking-widest text-slate-500">
                {detectedGender ? (
                  <span className={`px-2 py-0.5 rounded-full border ${detectedGender === 'female' ? 'bg-pink-500/10 border-pink-500/30 text-pink-400' : 'bg-blue-500/10 border-blue-500/30 text-blue-400'}`}>
                    {detectedGender === 'female' ? '👩 Female' : '👨 Male'}
                  </span>
                ) : (
                  <span className="text-slate-600 animate-pulse">🔍 detecting voice...</span>
                )}
              </div>
            )}
          </div>

          {/* Center: waveform + mic button */}
          <div className="flex flex-col items-center gap-8 z-10 w-full max-w-xl transform translate-y-8">
            {/* Big mic button */}
            <div className="relative flex items-center justify-center">
              {/* Ripple rings */}
              {sessionState === 'AI_LISTENING' && (
                <>
                  <div className="mic-ripple" style={{ background: 'rgba(16,185,129,0.12)' }} />
                  <div className="mic-ripple animate-pulse" style={{ background: 'rgba(16,185,129,0.06)', animationDelay: '0.7s' }} />
                </>
              )}
              {sessionState === 'AI_SPEAKING' && (
                <>
                  <div className="mic-ripple" style={{ background: 'rgba(99,102,241,0.12)' }} />
                  <div className="mic-ripple animate-pulse" style={{ background: 'rgba(99,102,241,0.06)', animationDelay: '0.7s' }} />
                </>
              )}
              {sessionState === 'AI_THINKING' && (
                <div className="mic-ripple animate-pulse" style={{ background: 'rgba(245,158,11,0.1)' }} />
              )}

              <button
                onClick={handleStartSession}
                aria-label={sessionState === 'IDLE' || sessionState === 'ERROR' ? 'Start recording (Space)' : 'Stop recording (Space)'}
                aria-pressed={sessionState !== 'IDLE' && sessionState !== 'ERROR'}
                className={`h-28 w-28 rounded-full flex items-center justify-center text-white transition-all duration-300 shadow-2xl relative z-10 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${
                  sessionState === 'IDLE'
                    ? 'bg-gradient-to-br from-indigo-600 to-violet-700 shadow-indigo-500/30 hover:shadow-indigo-500/50'
                    : sessionState === 'ERROR'
                    ? 'bg-gradient-to-br from-rose-600 to-rose-700 shadow-rose-500/30'
                    : sessionState === 'AI_LISTENING'
                    ? 'bg-gradient-to-br from-emerald-500 to-teal-600 shadow-emerald-500/40'
                    : sessionState === 'AI_THINKING'
                    ? 'bg-gradient-to-br from-amber-500 to-orange-600 shadow-amber-500/30'
                    : 'bg-gradient-to-br from-indigo-500 to-violet-600 shadow-indigo-500/40'
                }`}
              >
                {sessionState === 'IDLE' || sessionState === 'ERROR'
                  ? <Mic className="h-10 w-10 text-white" />
                  : <MicOff className="h-10 w-10 text-white animate-pulse" />
                }
              </button>
            </div>

            <p className="text-xs text-slate-500 font-medium tracking-wide">
              {sessionState === 'IDLE' ? 'Tap to start' : 'Tap to stop'}
            </p>
          </div>

          {/* Bottom: clear + actions */}
          <div className="flex items-center gap-2 z-10">
            <button
              onClick={handleClearChat}
              disabled={history.length === 0}
              aria-label="Clear all translation history"
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg border text-[10px] font-bold uppercase tracking-wider transition-all ${
                history.length === 0
                  ? 'border-slate-800 text-slate-700 cursor-not-allowed'
                  : 'border-slate-700 text-slate-400 hover:text-rose-400 hover:border-rose-500/40 hover:bg-rose-500/10'
              }`}
              title="Clear all translation history"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </button>
          </div>
        </div>

        {/* RIGHT: Floating Chat panel in the corner */}
        {!showChat ? (
          <button
            type="button"
            onClick={() => setShowChat(true)}
            className="absolute bottom-6 right-9 h-12 w-12 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white flex items-center justify-center shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 transition-all hover:scale-105 active:scale-95 z-20 group border border-indigo-400/20"
            title="Show Chat"
          >
            <MessageSquare className="h-5 w-5 transition-transform group-hover:rotate-12" />
          </button>
        ) : (
          <div className="absolute bottom-6 right-9 w-80 h-96 flex flex-col min-h-0 bg-slate-900/90 backdrop-blur border border-slate-800 rounded-2xl overflow-hidden shadow-2xl shadow-black/80 z-20 animate-in fade-in slide-in-from-bottom-4 duration-200">

            {/* Chat header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-3.5 w-3.5 text-slate-500" />
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Translation</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-600 font-medium">{history.length} message{history.length !== 1 ? 's' : ''}</span>
                <button
                  type="button"
                  onClick={() => setShowChat(false)}
                  className="p-1 rounded-md text-slate-500 hover:text-white hover:bg-slate-800 transition-colors"
                  title="Hide Chat"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Messages — scrollable, anchored to bottom */}
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 scrollbar-thin">
              {/* Empty state */}
              {history.length === 0 && !sourceCaption && !targetCaption && (
                <div className="flex-1 flex flex-col items-center justify-center text-center my-auto py-12">
                  <div className="h-14 w-14 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center mb-3">
                    <MessageSquare className="h-6 w-6 text-slate-600" />
                  </div>
                  <p className="text-xs text-slate-600 font-medium leading-relaxed max-w-[200px]">
                    Translations will appear here. Press the mic and start speaking.
                  </p>
                </div>
              )}

              {/* Message history — most recent entries at bottom (chat order) */}
              {history.map(msg => (
                <div
                  key={msg.id}
                  className={`flex flex-col max-w-[88%] ${msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'}`}
                >
                  <div className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm ${
                    msg.sender === 'user'
                      ? 'bg-emerald-500/15 border border-emerald-500/25 text-emerald-100 rounded-tr-none'
                      : 'bg-indigo-500/15 border border-indigo-500/25 text-indigo-100 rounded-tl-none'
                  }`}>
                    <p className="font-medium">{msg.text}</p>
                  </div>
                  <span className="text-[9px] text-slate-600 mt-1 font-bold uppercase tracking-wider px-1 flex items-center gap-1.5">
                    {msg.sender === 'user' ? `You (${msg.language})` : `AI (${msg.language})`}
                    <span className="text-slate-700 font-normal normal-case tracking-normal">
                      {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <button onClick={() => handleCopyText(msg.text, msg.id)} className="text-slate-600 hover:text-slate-300 transition-colors p-0.5" title="Copy">
                      {copiedId === msg.id ? <Check className="h-2.5 w-2.5 text-emerald-500" /> : <Copy className="h-2.5 w-2.5" />}
                    </button>
                    <button onClick={() => handleDeleteMessage(msg.id)} className="text-slate-700 hover:text-rose-400 transition-colors p-0.5" title="Delete this entry">
                      <Trash2 className="h-2.5 w-2.5" />
                    </button>
                  </span>
                </div>
              ))}

              {/* Live captions — sourceCaption with copy button */}
              {sourceCaption && (
                <div className="flex flex-col max-w-[88%] self-end items-end">
                  <div className="px-4 py-2.5 rounded-2xl rounded-tr-none bg-emerald-500/10 border border-emerald-500/20 text-emerald-200 text-sm italic shadow-sm animate-pulse">
                    <p>{sourceCaption}</p>
                  </div>
                  <span className="text-[9px] text-emerald-600 mt-1 font-extrabold flex items-center gap-1 uppercase tracking-wider">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
                    Speaking {sourceLang}...
                    <button
                      onClick={() => handleCopyText(sourceCaption, 'live-source')}
                      className="text-emerald-700 hover:text-emerald-400 transition-colors p-0.5 ml-0.5"
                      title="Copy source text"
                    >
                      {copiedId === 'live-source' ? <Check className="h-2.5 w-2.5 text-emerald-400" /> : <Copy className="h-2.5 w-2.5" />}
                    </button>
                  </span>
                </div>
              )}

              {/* Live captions — targetCaption with copy button */}
              {targetCaption && (
                <div className="flex flex-col max-w-[88%] self-start items-start">
                  <div className="px-4 py-2.5 rounded-2xl rounded-tl-none bg-indigo-500/10 border border-indigo-500/20 text-indigo-200 text-sm shadow-sm">
                    <p>{targetCaption}</p>
                  </div>
                  <span className="text-[9px] text-indigo-500 mt-1 font-extrabold flex items-center gap-1 uppercase tracking-wider">
                    <Volume2 className="h-2.5 w-2.5 animate-bounce" />
                    Translating to {targetLang}...
                    <button
                      onClick={() => handleCopyText(targetCaption, 'live-target')}
                      className="text-indigo-700 hover:text-indigo-400 transition-colors p-0.5 ml-0.5"
                      title="Copy translation"
                    >
                      {copiedId === 'live-target' ? <Check className="h-2.5 w-2.5 text-indigo-400" /> : <Copy className="h-2.5 w-2.5" />}
                    </button>
                  </span>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Text input — anchored to bottom of chat */}
            <form onSubmit={handleSendText} className="flex items-center gap-2 p-3 border-t border-slate-800 shrink-0">
              <input
                type="text"
                value={inputText}
                onChange={e => setInputText(e.target.value)}
                placeholder="Type to translate..."
                className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2 text-xs font-medium text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
              <button
                type="submit"
                disabled={!inputText.trim()}
                className={`p-2 rounded-xl border transition-all ${
                  !inputText.trim()
                    ? 'border-slate-700 text-slate-700 bg-slate-800/50 cursor-not-allowed'
                    : 'border-indigo-500/40 bg-indigo-500/15 text-indigo-400 hover:bg-indigo-500/25'
                }`}
              >
                <Send className="h-4 w-4" />
              </button>
            </form>
          </div>
        )}
      </div>

      {/* ── CONFIG OVERLAY ────────────────────────────────────── */}
      {showConfig && (
        <div className="mx-5 mb-3 shrink-0 bg-slate-900 border border-slate-700 rounded-2xl p-4 shadow-xl">
          <h3 className="text-xs font-bold text-slate-300 mb-3 flex items-center gap-2">
            <Settings className="h-3.5 w-3.5 text-indigo-400" />
            Parameter Configuration
          </h3>
          <div className="flex flex-col gap-4">
            {/* Volume */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] text-slate-500 font-semibold flex justify-between">
                <span>TTS Playback Volume</span>
                <span className="text-indigo-400 font-bold">{volume}%</span>
              </label>
              <input type="range" min="0" max="100" value={volume} onChange={e => setVolume(Number(e.target.value))}
                className="w-full accent-indigo-500 h-1.5 rounded-lg appearance-none cursor-pointer bg-slate-700" />
            </div>

            {/* Voice Mode */}
            <div className="flex flex-col gap-1.5">
              <label className="text-[11px] text-slate-500 font-semibold">TTS Voice Mode</label>
              <div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={() => setVoiceMode('auto')}
                  className={`py-1.5 px-3 rounded-lg text-xs font-bold transition-all border ${voiceMode === 'auto' ? 'bg-indigo-500/15 border-indigo-500/40 text-indigo-300' : 'bg-slate-800 border-slate-700 text-slate-500 hover:text-slate-300'}`}>
                  ✨ Auto (Gender)
                </button>
                <button type="button" onClick={() => setVoiceMode('manual')}
                  className={`py-1.5 px-3 rounded-lg text-xs font-bold transition-all border ${voiceMode === 'manual' ? 'bg-indigo-500/15 border-indigo-500/40 text-indigo-300' : 'bg-slate-800 border-slate-700 text-slate-500 hover:text-slate-300'}`}>
                  ⚙️ Manual
                </button>
              </div>
            </div>

            {voiceMode === 'manual' && (
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] text-slate-500 font-semibold">Select Voice</label>
                <select value={ttsVoice} onChange={e => setTtsVoice(e.target.value as any)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs font-bold text-slate-300 focus:outline-none focus:border-indigo-500 cursor-pointer">
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

      {/* ── TERMINAL ─────────────────────────────────────────── */}
      {showLogs && (
        <div className="mx-5 mb-3 shrink-0 bg-slate-900 border border-slate-700 rounded-2xl p-4 shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-bold text-slate-400 flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-indigo-400" />
              Developer Telemetry
            </h4>
            <span className="text-[8px] uppercase tracking-wider font-bold bg-slate-800 border border-slate-700 text-slate-500 px-2 py-0.5 rounded font-mono">Active</span>
          </div>
          <div className="bg-slate-950 border border-slate-800 rounded-xl p-3 h-28 overflow-y-auto font-mono text-[10px] leading-relaxed flex flex-col-reverse gap-1.5 scrollbar-thin shadow-inner">
            {logs.map((log, i) => (
              <div key={i} className="flex items-start gap-1 px-1 py-0.5 rounded hover:bg-slate-900/50 transition-colors">
                <span className="text-slate-700 select-none">&gt;</span>
                <div className="flex-1 whitespace-pre-wrap">{formatLog(log)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
