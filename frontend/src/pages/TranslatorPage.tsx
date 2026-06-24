import { useState, useEffect, useRef } from 'react';
import { 
  Mic, MicOff, Sparkles, RefreshCw, 
  Settings, Wifi, ShieldAlert,
  MessageSquare, Volume2, Trash2, Terminal
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
  const [history, setHistory] = useState<ChatMessage[]>([]);

  // Bind the generalized audio hook
  const {
    isConnected,
    isRecording,
    sessionState,
    sourceCaption,
    targetCaption,
    logs,
    startStream,
    stopStream,
    setSourceCaption,
    setTargetCaption,
    addLog,
  } = useAudioStream(sourceLang, targetLang);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevSessionState = useRef<string>('IDLE');

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [history, sourceCaption, targetCaption]);

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
    addLog('Chat history cleared.');
  };

  const formatLog = (log: string) => {
    if (log.toLowerCase().includes('error') || log.toLowerCase().includes('failed') || log.toLowerCase().includes('terminated')) {
      return <span className="text-rose-400 font-medium">{log}</span>;
    }
    if (log.includes('[Server]')) {
      return <span className="text-indigo-400">{log}</span>;
    }
    if (log.toLowerCase().includes('established') || log.toLowerCase().includes('granted') || log.toLowerCase().includes('success')) {
      return <span className="text-emerald-400 font-medium">{log}</span>;
    }
    return <span className="text-slate-400">{log}</span>;
  };

  return (
    <div className="flex-1 w-full max-w-4xl mx-auto px-4 py-6 flex flex-col relative z-10 font-outfit h-screen max-h-[850px]">
      
      {/* HEADER SECTION */}
      <header className="flex items-center justify-between gap-4 pb-4 border-b border-slate-900 mb-6 shrink-0 font-sans">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center shadow-lg shadow-indigo-500/20 relative overflow-hidden">
            <Sparkles className="h-5 w-5 text-white animate-pulse" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              Gemini Live <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-semibold uppercase tracking-wider">Interpreter</span>
            </h1>
            <p className="text-[10px] text-slate-500">Real-time speech-to-speech multi-language translation</p>
          </div>
        </div>

        {/* Status indicators */}
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg transition-all duration-300 ${isConnected ? 'bg-emerald-500/5 border border-emerald-500/20' : 'bg-slate-900/40 border border-slate-900'} text-[10px] text-slate-300`}>
            <Wifi className={`h-3 w-3 ${isConnected ? 'text-emerald-400 animate-pulse' : 'text-slate-500'}`} />
            <span className={isConnected ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
              {isConnected ? 'Active' : 'Offline'}
            </span>
          </div>

          <button 
            onClick={() => setShowConfig(!showConfig)}
            className={`p-1.5 rounded-lg border transition-all duration-300 ${showConfig ? 'bg-indigo-600/10 border-indigo-500/40 text-white' : 'bg-slate-900/40 border-slate-900 text-slate-400 hover:text-white'}`}
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* LANGUAGE SELECTORS (TOP DECK) */}
      <section className="glass-panel p-3 mb-6 flex items-center justify-between gap-4 shrink-0 shadow-lg bg-slate-900/10">
        <div className="flex-1 relative">
          <select
            value={sourceLang}
            onChange={(e) => {
              if (isRecording) stopStream();
              setSourceLang(e.target.value);
            }}
            className="w-full bg-slate-950/60 border border-slate-800 rounded-lg pl-3 pr-8 py-2 text-xs font-semibold text-white focus:outline-none focus:border-indigo-500/80 transition-all duration-300 appearance-none cursor-pointer hover:bg-slate-900/40 text-center"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="bg-slate-950 text-white">{l.name}</option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-indigo-400">
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
              <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/>
            </svg>
          </div>
        </div>

        <button 
          onClick={handleSwapLanguages}
          className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-400 hover:text-white transition-all hover:scale-105 active:scale-95 shadow-md flex items-center justify-center"
          title="Swap Languages"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>

        <div className="flex-1 relative">
          <select
            value={targetLang}
            onChange={(e) => {
              if (isRecording) stopStream();
              setTargetLang(e.target.value);
            }}
            className="w-full bg-slate-950/60 border border-slate-800 rounded-lg pl-3 pr-8 py-2 text-xs font-semibold text-white focus:outline-none focus:border-emerald-500/80 transition-all duration-300 appearance-none cursor-pointer hover:bg-slate-900/40 text-center"
          >
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code} className="bg-slate-950 text-white">{l.name}</option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-emerald-400">
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
              <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"/>
            </svg>
          </div>
        </div>
      </section>

      {/* CONVERSATION HISTORY PANEL (MAIN CHAT BODY) */}
      <section className="glass-panel flex-1 overflow-y-auto p-4 mb-6 shadow-inner flex flex-col gap-4 scrollbar-thin bg-slate-900/20 max-h-[460px]">
        {/* Empty State */}
        {history.length === 0 && !sourceCaption && !targetCaption && (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
            <div className="h-16 w-16 rounded-full bg-indigo-500/5 border border-indigo-500/10 flex items-center justify-center mb-4 relative neon-glow-indigo/5">
              <MessageSquare className="h-8 w-8 text-indigo-400" />
              <Sparkles className="h-4 w-4 text-emerald-400 absolute top-2 right-2 animate-bounce" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">Ready to Interpret</h3>
            <p className="text-xs text-slate-400 max-w-sm leading-relaxed">
              Select your languages above, press the microphone button below, and begin speaking. The system will translate your voice in real time.
            </p>
          </div>
        )}

        {/* Message Stream */}
        {history.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex flex-col max-w-[80%] ${msg.sender === 'user' ? 'self-end items-end' : 'self-start items-start'}`}
          >
            <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
              msg.sender === 'user'
                ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-100 rounded-tr-none'
                : 'bg-indigo-500/10 border border-indigo-500/20 text-indigo-100 rounded-tl-none'
            }`}>
              <p>{msg.text}</p>
            </div>
            <span className="text-[9px] text-slate-500 mt-1 font-semibold uppercase tracking-wider px-1">
              {msg.sender === 'user' ? `You (${msg.language})` : `AI (${msg.language})`}
            </span>
          </div>
        ))}

        {/* Active streaming captions (typing indicators) */}
        {sourceCaption && (
          <div className="flex flex-col max-w-[80%] self-end items-end animate-pulse">
            <div className="px-4 py-3 rounded-2xl rounded-tr-none bg-emerald-500/10 border border-emerald-500/30 text-emerald-100 text-sm italic">
              <p>{sourceCaption}</p>
            </div>
            <span className="text-[9px] text-emerald-400 mt-1 font-bold flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
              Speaking {sourceLang}...
            </span>
          </div>
        )}

        {targetCaption && (
          <div className="flex flex-col max-w-[80%] self-start items-start">
            <div className="px-4 py-3 rounded-2xl rounded-tl-none bg-indigo-500/10 border border-indigo-500/30 text-indigo-100 text-sm">
              <p>{targetCaption}</p>
            </div>
            <span className="text-[9px] text-indigo-400 mt-1 font-bold flex items-center gap-1">
              <Volume2 className="h-3 w-3 text-indigo-400 animate-bounce" />
              Translating to {targetLang}...
            </span>
          </div>
        )}

        {/* Anchor point to scroll to */}
        <div ref={messagesEndRef} />
      </section>

      {/* PARAMETER CONFIG OVERLAY */}
      {showConfig && (
        <section className="glass-panel p-4 mb-6 shadow-xl animate-fadeIn shrink-0">
          <h3 className="text-xs font-bold text-white mb-3 flex items-center gap-2">
            <Settings className="h-3.5 w-3.5 text-indigo-400" />
            Parameter Configurations
          </h3>
          <div className="flex flex-col gap-3">
            <label className="text-[11px] text-slate-400 font-semibold flex justify-between">
              <span>TTS Playback Volume</span>
              <span className="text-indigo-400">{volume}%</span>
            </label>
            <input 
              type="range" 
              min="0" 
              max="100"
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              className="w-full accent-indigo-500 bg-slate-950 h-1.5 rounded-lg appearance-none cursor-pointer" 
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
            className={`p-2 rounded-xl border transition-all ${
              history.length === 0 
                ? 'border-slate-900/40 text-slate-700 cursor-not-allowed' 
                : 'border-slate-800 text-slate-400 hover:text-rose-400 hover:border-rose-500/20'
            }`}
            title="Clear Chat History"
          >
            <Trash2 className="h-4 w-4" />
          </button>

          {/* Center: Mic button */}
          <div className="relative">
            {sessionState === 'AI_LISTENING' && (
              <>
                <div className="mic-ripple bg-emerald-500/20" />
                <div className="mic-ripple bg-emerald-500/10 animate-pulse" style={{ animationDelay: '0.6s' }} />
              </>
            )}
            {sessionState === 'AI_SPEAKING' && (
              <>
                <div className="mic-ripple bg-indigo-500/20" />
                <div className="mic-ripple bg-indigo-500/10 animate-pulse" style={{ animationDelay: '0.6s' }} />
              </>
            )}
            {sessionState === 'AI_THINKING' && (
              <>
                <div className="mic-ripple bg-amber-500/20 animate-pulse" />
              </>
            )}

            <button
              onClick={handleStartSession}
              className={`h-20 w-20 rounded-full flex items-center justify-center text-white transition-all duration-300 shadow-2xl relative z-10 hover:scale-105 active:scale-95 ${
                sessionState === 'IDLE' 
                  ? 'bg-gradient-to-tr from-indigo-700 to-indigo-500 hover:from-indigo-600 hover:to-indigo-400 neon-glow-indigo' 
                  : sessionState === 'ERROR'
                    ? 'bg-gradient-to-tr from-rose-700 to-rose-500'
                    : sessionState === 'AI_LISTENING'
                      ? 'bg-gradient-to-tr from-emerald-600 to-emerald-500 neon-glow-emerald'
                      : sessionState === 'AI_THINKING'
                        ? 'bg-gradient-to-tr from-amber-600 to-amber-500 neon-glow-amber'
                        : 'bg-gradient-to-tr from-indigo-600 to-indigo-500 neon-glow-indigo'
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
            className={`p-2 rounded-xl border transition-all ${
              showLogs 
                ? 'bg-indigo-600/10 border-indigo-500/40 text-white' 
                : 'border-slate-800 text-slate-400 hover:text-white'
            }`}
            title="Toggle Debug Console"
          >
            <Terminal className="h-4 w-4" />
          </button>
        </div>

        {/* Visualizer Waves */}
        {(sessionState === 'AI_LISTENING' || sessionState === 'AI_SPEAKING') && (
          <div className="flex items-center gap-1 h-6 mt-1">
            {[...Array(12)].map((_, i) => {
              const delay = (i % 4) * 0.15;
              const duration = 0.6 + (i % 3) * 0.2;
              return (
                <div
                  key={i}
                  className={`w-1 rounded-full origin-center ${
                    sessionState === 'AI_LISTENING' 
                      ? 'bg-emerald-400/80 shadow-[0_0_10px_rgba(16,185,129,0.5)]' 
                      : 'bg-indigo-400/80 shadow-[0_0_10px_rgba(99,102,241,0.5)]'
                  }`}
                  style={{
                    height: '24px',
                    animation: `voice-pulse ${duration}s ease-in-out infinite alternate`,
                    animationDelay: `${delay}s`,
                  }}
                />
              );
            })}
          </div>
        )}

        {/* Pipeline Status Indicator */}
        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
          <span className={`h-2 w-2 rounded-full ${
            sessionState === 'IDLE' ? 'bg-slate-600' :
            sessionState === 'AI_LISTENING' ? 'bg-emerald-400 animate-pulse' :
            sessionState === 'AI_THINKING' ? 'bg-amber-400 animate-pulse' :
            sessionState === 'AI_SPEAKING' ? 'bg-indigo-400 animate-pulse' : 'bg-rose-500'
          }`} />
          <span>
            {sessionState === 'IDLE' && 'Ready to Interpret'}
            {sessionState === 'AI_LISTENING' && 'Listening (Voice Capture Active)'}
            {sessionState === 'AI_THINKING' && 'AI Interpreting...'}
            {sessionState === 'AI_SPEAKING' && 'AI Responding...'}
            {sessionState === 'ERROR' && 'Interpreter connection error'}
          </span>
        </div>
      </section>

      {/* COLLAPSIBLE DEV TERMINAL */}
      {showLogs && (
        <section className="glass-panel p-4 mt-6 shadow-2xl animate-fadeIn shrink-0">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-bold text-slate-300 flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-indigo-400" />
              Developer Telemetry Logs
            </h4>
            <span className="text-[8px] uppercase tracking-wider font-semibold bg-slate-950 border border-slate-900 text-slate-500 px-2 py-0.5 rounded font-mono">Telemetry Active</span>
          </div>
          
          <div className="bg-slate-950/90 border border-slate-900 rounded-xl p-3 h-28 overflow-y-auto font-mono text-[10px] leading-relaxed flex flex-col-reverse gap-1.5 scrollbar-thin">
            {logs.map((log, i) => (
              <div key={i} className="hover:bg-slate-900/20 px-1 py-0.5 rounded transition-colors flex items-start gap-1">
                <span className="text-slate-700 select-none">&gt;</span>
                <div className="flex-1 whitespace-pre-wrap">{formatLog(log)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

    </div>
  );
}
