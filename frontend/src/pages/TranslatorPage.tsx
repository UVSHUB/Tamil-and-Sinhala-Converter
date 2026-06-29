import { useState, useEffect, useRef } from 'react';
import { 
  Mic, MicOff, Sparkles, RefreshCw, 
  Settings, Wifi, ShieldAlert,
  MessageSquare, Volume2, VolumeX, Trash2, Terminal,
  Copy, Check, Send
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
  const [volume, setVolume] = useState<number>(80);
  
  // Persistent chat history from LocalStorage
  const [history, setHistory] = useState<ChatMessage[]>(() => {
    const saved = localStorage.getItem('sintam_history');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        return parsed.map((m: any) => ({
          ...m,
          timestamp: new Date(m.timestamp)
        }));
      } catch (e) {
        return [];
      }
    }
    return [];
  });
  
  const [inputText, setInputText] = useState<string>('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Bind the generalized audio hook
  const {
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
  } = useAudioStream(sourceLang, targetLang);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const prevSessionState = useRef<string>('IDLE');

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [history, sourceCaption, targetCaption]);

  // Save history to LocalStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('sintam_history', JSON.stringify(history));
  }, [history]);

  // Canvas Drawing Loop for Siri-like Layered Sine Wave Audio Visualizer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    
    // Configure canvas size based on its display size for high DPI
    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    resizeCanvas();
    
    const bufferLength = 128;
    const dataArray = new Uint8Array(bufferLength);
    let phase = 0;

    const draw = () => {
      animationFrameId = requestAnimationFrame(draw);
      
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      ctx.clearRect(0, 0, width, height);

      let activeAnalyser = null;
      let waveColor = 'rgba(99, 102, 241, 0.8)'; // Indigo (AI)

      if (sessionState === 'AI_LISTENING') {
        activeAnalyser = micAnalyserRef.current;
        waveColor = 'rgba(16, 185, 129, 0.8)'; // Emerald (User)
      } else if (sessionState === 'AI_SPEAKING') {
        activeAnalyser = aiAnalyserRef.current;
      }

      // Get real-time audio amplitude
      let amplitude = 0;
      if (activeAnalyser) {
        activeAnalyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          sum += Math.abs(dataArray[i] - 128);
        }
        amplitude = (sum / bufferLength) / 64.0; // Normalized amplitude [0, 1]
      }

      // Zero out amplitude for idle states
      if (sessionState === 'IDLE' || sessionState === 'ERROR' || sessionState === 'AI_THINKING') {
        amplitude = 0;
      }

      // Draw a subtle idle wave if connected but silent, otherwise flatline
      const finalAmplitude = amplitude > 0.02 ? amplitude : (isConnected ? 0.04 : 0);

      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      // Layered sine waves for Siri-like organic voice wave effect
      const waveCount = finalAmplitude > 0 ? 3 : 1;
      
      for (let w = 0; w < waveCount; w++) {
        ctx.beginPath();
        
        // Different speed, frequency, and phase offset per wave layer
        const wavePhase = phase + w * Math.PI / 2.5;
        const waveFreq = 1.6 + w * 0.4;
        const waveAmp = finalAmplitude * (height / 2.5) * (1 - w * 0.3);
        
        ctx.strokeStyle = w === 0 ? waveColor : waveColor.replace('0.8', (0.4 - w * 0.12).toString());
        ctx.lineWidth = w === 0 ? 2.5 : 1.5;

        for (let x = 0; x <= width; x++) {
          const normalizedX = x / width;
          // Sinusoidal envelope to taper wave ends to 0
          const envelope = Math.sin(normalizedX * Math.PI);
          const angle = normalizedX * Math.PI * 2 * waveFreq - wavePhase;
          const y = (height / 2) + Math.sin(angle) * waveAmp * envelope;

          if (x === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
      }

      phase += 0.1 + finalAmplitude * 0.08;
    };

    draw();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [sessionState, isConnected, micAnalyserRef, aiAnalyserRef]);

  // Archive complete transcripts into chat history when a translation turn completes
  useEffect(() => {
    const isStateTransition = prevSessionState.current !== sessionState;
    if (isStateTransition && (sessionState === 'AI_LISTENING' || sessionState === 'IDLE')) {
      if (prevSessionState.current === 'AI_SPEAKING' || prevSessionState.current === 'AI_LISTENING') {
        const userText = sourceCaption.trim();
        const aiText = targetCaption.trim();

        if (userText || aiText) {
          const timestamp = new Date();
          const newMessages: ChatMessage[] = [];

          if (userText) {
            newMessages.push({
              id: `user-${Date.now()}`,
              sender: 'user',
              text: userText,
              timestamp,
              language: sourceLang,
            });
          }

          if (aiText) {
            newMessages.push({
              id: `ai-${Date.now() + 1}`,
              sender: 'ai',
              text: aiText,
              timestamp,
              language: targetLang,
            });
          }

          setHistory((prev) => [...prev, ...newMessages]);
          setSourceCaption('');
          setTargetCaption('');
        }
      }
    }
    prevSessionState.current = sessionState;
  }, [sessionState, sourceCaption, targetCaption, sourceLang, targetLang, setSourceCaption, setTargetCaption]);

  const handleStartSession = () => {
    if (sessionState === 'IDLE' || sessionState === 'ERROR') {
      startStream();
    } else {
      stopStream();
    }
  };

  const handleSwapLanguages = () => {
    if (isRecording) {
      stopStream();
    }
    const temp = sourceLang;
    setSourceLang(targetLang);
    setTargetLang(temp);
    setSourceCaption('');
    setTargetCaption('');
    addLog(`Swapped languages: ${targetLang} ↔ ${temp}`);
  };

  const handleClearChat = () => {
    setHistory([]);
    setSourceCaption('');
    setTargetCaption('');
    localStorage.removeItem('sintam_history');
    addLog('Chat history cleared.');
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

    // Send text over WebSocket
    sendText(inputText.trim());

    // Add to local history as a user message
    const timestamp = new Date();
    setHistory((prev) => [
      ...prev,
      {
        id: `user-text-${Date.now()}`,
        sender: 'user',
        text: inputText.trim(),
        timestamp,
        language: sourceLang,
      }
    ]);

    // Clear input
    setInputText('');
  };

  const formatLog = (log: string) => {
    if (log.toLowerCase().includes('error') || log.toLowerCase().includes('failed') || log.toLowerCase().includes('terminated')) {
      return <span className="text-rose-400 font-medium">{log}</span>;
    }
    if (log.includes('[Server]')) {
      return <span className="text-indigo-400">{log}</span>;
    }
    if (log.toLowerCase().includes('established') || log.toLowerCase().includes('granted') || log.toLowerCase().includes('success') || log.toLowerCase().includes('reconnected')) {
      return <span className="text-emerald-400 font-medium">{log}</span>;
    }
    return <span className="text-slate-400">{log}</span>;
  };

  return (
    <div className="flex-1 w-full max-w-4xl mx-auto px-4 py-6 flex flex-col relative z-10 font-outfit h-screen max-h-[850px]">
      
      {/* HEADER SECTION */}
      <header className="flex items-center justify-between gap-4 pb-4 border-b border-slate-200 mb-6 shrink-0 font-sans">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center shadow-md shadow-indigo-500/10 relative overflow-hidden">
            <Sparkles className="h-5 w-5 text-white animate-pulse" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-slate-800 flex items-center gap-2">
              SinTam <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600 border border-indigo-100/60 font-semibold uppercase tracking-wider">Live</span>
            </h1>
            <p className="text-[10px] text-slate-500">Sinhala ↔ Tamil Real-Time Voice Translator</p>
          </div>
        </div>

        {/* Status indicators */}
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all duration-300 ${isConnected ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-slate-100 border border-slate-200 text-slate-500'} text-[10px]`}>
            <Wifi className={`h-3 w-3 ${isConnected ? 'text-emerald-500 animate-pulse' : 'text-slate-400'}`} />
            <span className={isConnected ? 'font-bold' : ''}>
              {isConnected ? 'Active' : 'Offline'}
            </span>
          </div>

          {/* Mute Button */}
          <button 
            onClick={toggleMute}
            className={`p-1.5 rounded-lg border transition-all duration-300 ${isMuted ? 'bg-rose-50 border-rose-200 text-rose-600 font-bold' : 'bg-white border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
            title={isMuted ? "Unmute Voice" : "Mute Voice"}
          >
            {isMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
          </button>

          <button 
            onClick={() => setShowConfig(!showConfig)}
            className={`p-1.5 rounded-lg border transition-all duration-300 ${showConfig ? 'bg-indigo-50 border-indigo-200 text-indigo-600 font-bold' : 'bg-white border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-50'}`}
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* LANGUAGE SELECTORS (TOP DECK) */}
      <section className="glass-panel p-3.5 mb-6 flex items-center justify-between gap-4 shrink-0 shadow-sm bg-white/40">
        <div className="flex-1 relative">
          <label className="absolute -top-2 left-3 px-1.5 bg-slate-50 text-[9px] font-bold uppercase tracking-wider text-indigo-600">From</label>
          <select
            value={sourceLang}
            onChange={(e) => {
              if (isRecording) stopStream();
              setSourceLang(e.target.value);
            }}
            className="w-full bg-white border border-slate-200 rounded-xl pl-3 pr-8 py-2.5 text-xs font-bold text-slate-800 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all duration-300 appearance-none cursor-pointer hover:bg-slate-50 text-center shadow-sm"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="bg-white text-slate-800">{l.name}</option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-indigo-500">
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
              <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/>
            </svg>
          </div>
        </div>

        <button 
          onClick={handleSwapLanguages}
          className="p-2.5 rounded-xl bg-white border border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition-all hover:scale-105 active:scale-95 shadow-sm flex items-center justify-center"
          title="Swap Languages"
        >
          <RefreshCw className="h-4 w-4" />
        </button>

        <div className="flex-1 relative">
          <label className="absolute -top-2 left-3 px-1.5 bg-slate-50 text-[9px] font-bold uppercase tracking-wider text-emerald-600">To</label>
          <select
            value={targetLang}
            onChange={(e) => {
              if (isRecording) stopStream();
              setTargetLang(e.target.value);
            }}
            className="w-full bg-white border border-slate-200 rounded-xl pl-3 pr-8 py-2.5 text-xs font-bold text-slate-800 focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 transition-all duration-300 appearance-none cursor-pointer hover:bg-slate-50 text-center shadow-sm"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="bg-white text-slate-800">{l.name}</option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-emerald-500">
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
              <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/>
            </svg>
          </div>
        </div>
      </section>

      {/* CONVERSATION HISTORY PANEL (MAIN CHAT BODY) */}
      <section className="glass-panel flex-1 min-h-0 overflow-y-auto p-4 mb-4 shadow-inner flex flex-col gap-4 scrollbar-thin bg-white/30">
        {/* Empty State */}
        {history.length === 0 && !sourceCaption && !targetCaption && (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 my-auto">
            <div className="h-16 w-16 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center mb-4 relative shadow-sm">
               <MessageSquare className="h-8 w-8 text-indigo-500" />
               <Sparkles className="h-4 w-4 text-emerald-500 absolute top-1.5 right-1.5 animate-bounce" />
            </div>
            <h3 className="text-base font-bold text-slate-800 mb-2">Ready to Translate</h3>
            <p className="text-xs text-slate-500 max-w-sm leading-relaxed">
              Select your languages above, type a message, or press the microphone button below and start speaking. SinTam will translate in real time.
            </p>
          </div>
        )}

        {/* Message Stream */}
        {history.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex flex-col max-w-[85%] ${msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'}`}
          >
            <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm ${
              msg.sender === 'user'
                ? 'bg-emerald-50 border border-emerald-100/80 text-emerald-950 rounded-tr-none'
                : 'bg-indigo-50 border border-indigo-100/80 text-indigo-950 rounded-tl-none'
            }`}>
              <p className="font-medium">{msg.text}</p>
            </div>
            <span className="text-[9px] text-slate-400 mt-1 font-bold uppercase tracking-wider px-1 flex items-center gap-1.5">
              {msg.sender === 'user' ? `You (${msg.language})` : `AI (${msg.language})`}
              <button 
                onClick={() => handleCopyText(msg.text, msg.id)}
                className="text-slate-400 hover:text-slate-600 transition-colors p-0.5"
                title="Copy translation"
              >
                {copiedId === msg.id ? <Check className="h-2.5 w-2.5 text-emerald-600" /> : <Copy className="h-2.5 w-2.5" />}
              </button>
            </span>
          </div>
        ))}

        {/* Active streaming captions (typing indicators) */}
        {sourceCaption && (
          <div className="flex flex-col max-w-[85%] self-end items-end animate-pulse">
            <div className="px-4 py-3 rounded-2xl rounded-tr-none bg-emerald-50/75 border border-emerald-200 text-emerald-900 text-sm italic shadow-sm">
              <p>{sourceCaption}</p>
            </div>
            <span className="text-[9px] text-emerald-600 mt-1 font-extrabold flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
              Speaking {sourceLang}...
            </span>
          </div>
        )}

        {targetCaption && (
          <div className="flex flex-col max-w-[85%] self-start items-start">
            <div className="px-4 py-3 rounded-2xl rounded-tl-none bg-indigo-50/75 border border-indigo-200 text-indigo-900 text-sm shadow-sm">
              <p>{targetCaption}</p>
            </div>
            <span className="text-[9px] text-indigo-600 mt-1 font-extrabold flex items-center gap-1">
              <Volume2 className="h-3 w-3 text-indigo-500 animate-bounce" />
              Translating to {targetLang}...
            </span>
          </div>
        )}

        {/* Anchor point to scroll to */}
        <div ref={messagesEndRef} />
      </section>

      {/* TEXT INPUT FALLBACK */}
      <form 
        onSubmit={handleSendText}
        className="flex items-center gap-2 mb-4 shrink-0"
      >
        <input 
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type a message to translate..."
          className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all duration-300 shadow-sm"
        />
        <button
          type="submit"
          disabled={!inputText.trim()}
          className={`p-2.5 rounded-xl border transition-all shadow-sm flex items-center justify-center ${
            !inputText.trim()
              ? 'border-slate-200/50 text-slate-300 bg-slate-50/50 cursor-not-allowed'
              : 'border-indigo-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100/50 hover:border-indigo-300'
          }`}
          title="Send text to translate"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>

      {/* PARAMETER CONFIG OVERLAY */}
      {showConfig && (
        <section className="glass-panel p-4 mb-4 shadow-md animate-fadeIn shrink-0 bg-white/50">
          <h3 className="text-xs font-bold text-slate-800 mb-3 flex items-center gap-2">
            <Settings className="h-3.5 w-3.5 text-indigo-500" />
            Parameter Configurations
          </h3>
          <div className="flex flex-col gap-3">
            <label className="text-[11px] text-slate-500 font-semibold flex justify-between">
              <span>TTS Playback Volume</span>
              <span className="text-indigo-600 font-bold">{volume}%</span>
            </label>
            <input 
              type="range" 
              min="0" 
              max="100"
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              className="w-full accent-indigo-600 bg-slate-200 h-1.5 rounded-lg appearance-none cursor-pointer" 
            />
          </div>
        </section>
      )}

      {/* BOTTOM CONTROL DECK */}
      <section className="flex flex-col items-center gap-4 shrink-0">
        
        {/* Controls and Actions */}
        <div className="w-full flex items-center justify-between px-2">
          {/* Left: Clear button */}
          <button 
            onClick={handleClearChat}
            disabled={history.length === 0}
            className={`p-2.5 rounded-xl border transition-all ${
              history.length === 0 
                ? 'border-slate-200/50 text-slate-300 bg-slate-50/50 cursor-not-allowed' 
                : 'border-slate-200 bg-white text-slate-500 hover:text-rose-500 hover:border-rose-200 hover:bg-rose-50/50 shadow-sm'
            }`}
            title="Clear Chat History"
          >
            <Trash2 className="h-4 w-4" />
          </button>

          {/* Center: Mic button */}
          <div className="relative">
            {sessionState === 'AI_LISTENING' && (
              <>
                <div className="mic-ripple bg-emerald-500/10" />
                <div className="mic-ripple bg-emerald-500/5 animate-pulse" style={{ animationDelay: '0.6s' }} />
              </>
            )}
            {sessionState === 'AI_SPEAKING' && (
              <>
                <div className="mic-ripple bg-indigo-500/10" />
                <div className="mic-ripple bg-indigo-500/5 animate-pulse" style={{ animationDelay: '0.6s' }} />
              </>
            )}
            {sessionState === 'AI_THINKING' && (
              <>
                <div className="mic-ripple bg-amber-500/10 animate-pulse" />
              </>
            )}

            <button
              onClick={handleStartSession}
              className={`h-20 w-20 rounded-full flex items-center justify-center text-white transition-all duration-300 shadow-lg relative z-10 hover:scale-105 active:scale-95 ${
                sessionState === 'IDLE' 
                  ? 'bg-gradient-to-tr from-indigo-600 to-indigo-500 hover:from-indigo-550 hover:to-indigo-450 neon-glow-indigo' 
                  : sessionState === 'ERROR'
                    ? 'bg-gradient-to-tr from-rose-600 to-rose-500'
                    : sessionState === 'AI_LISTENING'
                      ? 'bg-gradient-to-tr from-emerald-500 to-emerald-500 neon-glow-emerald'
                      : sessionState === 'AI_THINKING'
                        ? 'bg-gradient-to-tr from-amber-500 to-amber-500 neon-glow-amber'
                        : 'bg-gradient-to-tr from-indigo-500 to-indigo-500 neon-glow-indigo'
              }`}
            >
              {sessionState === 'IDLE' ? (
                <Mic className="h-8 w-8 text-white" />
              ) : (
                <MicOff className="h-8 w-8 text-white animate-pulse" />
              )}
            </button>
          </div>

          {/* Right: Logger toggle */}
          <button 
            onClick={() => setShowLogs(!showLogs)}
            className={`p-2.5 rounded-xl border transition-all shadow-sm ${
              showLogs 
                ? 'bg-indigo-50 border-indigo-200 text-indigo-600 font-bold' 
                : 'border-slate-200 bg-white text-slate-500 hover:text-slate-800 hover:bg-slate-50'
            }`}
            title="Toggle Debug Console"
          >
            <Terminal className="h-4 w-4" />
          </button>
        </div>

        {/* Real-Time Siri-like Audio Visualizer Canvas */}
        <div className={`w-full h-12 mt-1 max-w-md mx-auto transition-all duration-500 overflow-hidden flex items-center justify-center ${sessionState === 'IDLE' ? 'opacity-0 h-0' : 'opacity-100 h-12'}`}>
          <canvas 
            ref={canvasRef} 
            className="w-full h-full"
          />
        </div>

        {/* Pipeline Status Indicator */}
        <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-500">
          <span className={`h-2 w-2 rounded-full ${
            sessionState === 'IDLE' ? 'bg-slate-400' :
            sessionState === 'AI_LISTENING' ? 'bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)]' :
            sessionState === 'AI_THINKING' ? 'bg-amber-500 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.5)]' :
            sessionState === 'AI_SPEAKING' ? 'bg-indigo-500 animate-pulse shadow-[0_0_8px_rgba(99,102,241,0.5)]' : 'bg-rose-500'
          }`} />
          <span>
            {sessionState === 'IDLE' && 'Ready to Translate'}
            {sessionState === 'AI_LISTENING' && 'Listening (Voice Capture Active)'}
            {sessionState === 'AI_THINKING' && 'AI Interpreting...'}
            {sessionState === 'AI_SPEAKING' && 'AI Responding...'}
            {sessionState === 'ERROR' && 'Interpreter Connection Error'}
          </span>
        </div>
      </section>

      {/* COLLAPSIBLE DEV TERMINAL */}
      {showLogs && (
        <section className="glass-panel p-4 mt-6 shadow-md animate-fadeIn shrink-0 bg-white/50">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-bold text-slate-700 flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-indigo-500" />
              Developer Telemetry Logs
            </h4>
            <span className="text-[8px] uppercase tracking-wider font-bold bg-slate-100 border border-slate-200 text-slate-500 px-2 py-0.5 rounded font-mono">Telemetry Active</span>
          </div>
          
          <div className="bg-slate-900 border border-slate-950 rounded-xl p-3 h-28 overflow-y-auto font-mono text-[10px] leading-relaxed flex flex-col-reverse gap-1.5 scrollbar-thin shadow-inner">
            {logs.map((log, i) => (
              <div key={i} className="hover:bg-slate-850 px-1 py-0.5 rounded transition-colors flex items-start gap-1">
                <span className="text-slate-600 select-none">&gt;</span>
                <div className="flex-1 whitespace-pre-wrap">{formatLog(log)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

    </div>
  );
}
