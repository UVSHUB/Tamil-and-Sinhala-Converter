import { useState } from 'react';
import { 
  Mic, MicOff, Sparkles, RefreshCw, 
  Settings, Activity, Wifi, ShieldAlert 
} from 'lucide-react';
import { useAudioStream } from '../hooks/useAudioStream';

type LanguageMode = 'SI_TO_TA' | 'TA_TO_SI';

export default function TranslatorPage() {
  // UI states
  const [langMode, setLangMode] = useState<LanguageMode>('SI_TO_TA');
  const [showConfig, setShowConfig] = useState<boolean>(false);
  const [volume, setVolume] = useState<number>(80);
  const [latency] = useState<number>(45); // Mock latency

  const {
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
  } = useAudioStream(langMode);

  const handleStartSession = () => {
    if (sessionState === 'IDLE' || sessionState === 'ERROR') {
      startStream();
    } else {
      stopStream();
    }
  };

  const toggleLanguageMode = () => {
    if (isRecording) {
      stopStream();
    }
    const nextMode = langMode === 'SI_TO_TA' ? 'TA_TO_SI' : 'SI_TO_TA';
    setLangMode(nextMode);
    setSinhalaCaption('');
    setTamilCaption('');
    addLog(`Language mode switched to: ${nextMode === 'SI_TO_TA' ? 'Sinhala ↔ Tamil' : 'Tamil ↔ Sinhala'}`);
  };

  return (
    <div className="flex-1 w-full max-w-6xl mx-auto px-4 py-8 flex flex-col relative z-10">
      
      {/* ----------------------------------------------------------------------
          HEADER NAVIGATION SECTION
         ---------------------------------------------------------------------- */}
      <header className="flex flex-col sm:flex-row items-center justify-between gap-4 pb-8 border-b border-slate-800 mb-8">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-outfit font-bold tracking-tight text-white flex items-center gap-2">
              Gemini Live <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">Voice Translator</span>
            </h1>
            <p className="text-xs text-slate-400">Bidirectional Sinhala ↔ Tamil Audio Stream Pipeline</p>
          </div>
        </div>

        {/* Live System Stats */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass-panel text-xs text-slate-300">
            <Wifi className={`h-3.5 w-3.5 ${isConnected ? 'text-emerald-400 animate-pulse' : 'text-slate-500'}`} />
            <span>Server:</span>
            <span className={isConnected ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
              {isConnected ? 'Connected' : 'Offline'}
            </span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass-panel text-xs text-slate-300">
            <Activity className="h-3.5 w-3.5 text-indigo-400" />
            <span>RTT Latency:</span>
            <span className="text-indigo-400 font-semibold">{isConnected ? `${latency}ms` : '--'}</span>
          </div>

          <button 
            onClick={() => setShowConfig(!showConfig)}
            className="p-2 rounded-lg glass-panel hover:border-indigo-500/40 text-slate-300 hover:text-white transition-all"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </header>

      <main className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        
        {/* ----------------------------------------------------------------------
            TRANSLATOR CONTROL PANEL (LEFT COLUMN)
           ---------------------------------------------------------------------- */}
        <section className="lg:col-span-1 flex flex-col gap-6">
          <div className="glass-panel rounded-2xl p-6 shadow-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 h-16 w-16 bg-indigo-600/5 rounded-bl-full pointer-events-none"></div>
            
            <h2 className="text-sm font-semibold text-slate-400 tracking-wider uppercase mb-4">Translation Mode</h2>
            
            {/* Language Selector Selector */}
            <div className="flex items-center justify-between p-2 rounded-xl bg-slate-900/80 border border-slate-800 mb-6">
              <div className={`flex-1 text-center py-2.5 rounded-lg text-sm transition-all font-medium ${langMode === 'SI_TO_TA' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-400 hover:text-white cursor-pointer'}`}
                   onClick={() => langMode === 'TA_TO_SI' && toggleLanguageMode()}>
                Sinhala
              </div>
              <button 
                onClick={toggleLanguageMode}
                className="p-2.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
                title="Swap Language Direction"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
              <div className={`flex-1 text-center py-2.5 rounded-lg text-sm transition-all font-medium ${langMode === 'TA_TO_SI' ? 'bg-indigo-600 text-white shadow-lg' : 'text-slate-400 hover:text-white cursor-pointer'}`}
                   onClick={() => langMode === 'SI_TO_TA' && toggleLanguageMode()}>
                Tamil
              </div>
            </div>

            {/* Central Stream Trigger */}
            <div className="flex flex-col items-center justify-center py-6">
              <button
                onClick={handleStartSession}
                className={`h-24 w-24 rounded-full flex items-center justify-center text-white transition-all shadow-2xl relative ${
                  sessionState === 'IDLE' 
                    ? 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-600/30' 
                    : sessionState === 'ERROR'
                      ? 'bg-rose-600 hover:bg-rose-500 shadow-rose-600/30'
                      : sessionState === 'AI_LISTENING'
                        ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/30 ai-listening'
                        : sessionState === 'AI_THINKING'
                          ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-600/30 ai-thinking'
                          : 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-600/30 ai-speaking'
                }`}
              >
                {sessionState === 'IDLE' ? (
                  <Mic className="h-10 w-10" />
                ) : (
                  <MicOff className="h-10 w-10 animate-pulse" />
                )}
              </button>

              <div className="text-center mt-6">
                <p className="text-xs uppercase tracking-widest text-slate-400">Stream Status</p>
                <div className="flex items-center justify-center gap-2 mt-1">
                  <span className={`h-2.5 w-2.5 rounded-full ${
                    sessionState === 'IDLE' ? 'bg-slate-600' :
                    sessionState === 'AI_LISTENING' ? 'bg-emerald-400 animate-ping' :
                    sessionState === 'AI_THINKING' ? 'bg-amber-400 animate-pulse' :
                    sessionState === 'AI_SPEAKING' ? 'bg-indigo-400 animate-pulse' : 'bg-rose-500'
                  }`}></span>
                  <span className="text-sm font-semibold font-outfit text-white">
                    {sessionState === 'IDLE' && 'Awaiting Mic...'}
                    {sessionState === 'AI_LISTENING' && 'AI Listening (Capturing Audio)'}
                    {sessionState === 'AI_THINKING' && 'AI Thinking (Processing)'}
                    {sessionState === 'AI_SPEAKING' && 'AI Speaking (Synthesizing)'}
                    {sessionState === 'ERROR' && 'Stream error'}
                  </span>
                </div>
              </div>
            </div>

            {/* Waveform Micro-indicator */}
            {sessionState !== 'IDLE' && (
              <div className="flex justify-center gap-1.5 h-8 mt-2 items-center">
                {[...Array(9)].map((_, i) => (
                  <span 
                    key={i} 
                    className="w-1 bg-indigo-500 rounded-full transition-all"
                    style={{
                      height: `${Math.random() * 100}%`,
                      animation: 'voice-pulse 1s infinite alternate',
                      animationDelay: `${i * 0.1}s`
                    }}
                  ></span>
                ))}
              </div>
            )}
          </div>

          {/* Configuration drawer */}
          {showConfig && (
            <div className="glass-panel rounded-2xl p-6 shadow-xl animate-fadeIn">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Settings className="h-4 w-4 text-indigo-400" />
                Session Parameter Tuning
              </h3>
              
              <div className="flex flex-col gap-4">
                <label className="text-xs text-slate-400">
                  TTS Volume Settings ({volume}%)
                  <input 
                    type="range" 
                    min="0" 
                    max="100"
                    value={volume}
                    onChange={(e) => setVolume(Number(e.target.value))}
                    className="w-full mt-2 accent-indigo-500" 
                  />
                </label>

                <div>
                  <span className="text-xs text-slate-400 block mb-2">Target Audio Channels</span>
                  <div className="flex gap-2">
                    <button className="flex-1 py-1 text-xs rounded bg-indigo-600 border border-indigo-500">16kHz PCM (Mono)</button>
                    <button className="flex-1 py-1 text-xs rounded border border-slate-700 hover:border-slate-600 text-slate-400">48kHz PCM (Stereo)</button>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-800 text-[10px] text-slate-500">
                  Model configuration currently targets: <code className="text-indigo-400">gemini-2.0-flash-exp</code>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* ----------------------------------------------------------------------
            TRANSCRIPT & CAPTION MODULES (RIGHT COLUMNS)
           ---------------------------------------------------------------------- */}
        <section className="lg:col-span-2 flex flex-col gap-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* Input Caption Card */}
            <div className={`glass-panel rounded-2xl p-6 min-h-[220px] flex flex-col justify-between text-panel-transition ${
              (sessionState === 'AI_LISTENING' && langMode === 'SI_TO_TA') || 
              (sessionState === 'AI_THINKING' && langMode === 'SI_TO_TA') ||
              (sessionState === 'AI_SPEAKING' && langMode === 'TA_TO_SI')
                ? 'text-panel-active' : ''
            }`}>
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">Sinhala Transcript</span>
                    {(sessionState === 'AI_LISTENING' && langMode === 'SI_TO_TA') && (
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    )}
                    {(sessionState === 'AI_THINKING' && langMode === 'SI_TO_TA') && (
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                    )}
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">16kHz Int16</span>
                </div>
                <p className="text-lg font-outfit text-white leading-relaxed">
                  {sinhalaCaption || (
                    <span className="text-slate-600 italic">
                      {sessionState === 'AI_LISTENING' && langMode === 'SI_TO_TA' ? 'Speak Sinhala now...' : 'Awaiting speech input...'}
                    </span>
                  )}
                </p>
              </div>
              <div className="pt-4 border-t border-slate-900 flex justify-between text-xs text-slate-500">
                <span>Recognized source speech</span>
                <span>SINHALA (Sri Lanka)</span>
              </div>
            </div>

            {/* Output Translation Card */}
            <div className={`glass-panel rounded-2xl p-6 min-h-[220px] flex flex-col justify-between text-panel-transition ${
              (sessionState === 'AI_LISTENING' && langMode === 'TA_TO_SI') || 
              (sessionState === 'AI_THINKING' && langMode === 'TA_TO_SI') ||
              (sessionState === 'AI_SPEAKING' && langMode === 'SI_TO_TA')
                ? 'text-panel-active' : ''
            }`}>
              <div>
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Tamil Translation</span>
                    {(sessionState === 'AI_LISTENING' && langMode === 'TA_TO_SI') && (
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    )}
                    {(sessionState === 'AI_THINKING' && langMode === 'TA_TO_SI') && (
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                    )}
                    {(sessionState === 'AI_SPEAKING') && (
                      <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse"></span>
                    )}
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Gemini Live</span>
                </div>
                <p className="text-lg font-outfit text-white leading-relaxed">
                  {tamilCaption || (
                    <span className="text-slate-600 italic">
                      {sessionState === 'AI_LISTENING' && langMode === 'TA_TO_SI' ? 'Speak Tamil now...' : 'Awaiting translation...'}
                    </span>
                  )}
                </p>
              </div>
              <div className="pt-4 border-t border-slate-900 flex justify-between text-xs text-slate-500">
                <span>Synthesized outputs stream</span>
                <span>TAMIL (Sri Lanka / India)</span>
              </div>
            </div>

          </div>

          {/* Real-time Logger Terminal for dev verification */}
          <div className="glass-panel rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-indigo-400" />
              Developer Stream Logs (Real-time Telemetry)
            </h3>
            
            <div className="bg-slate-950/80 border border-slate-900 rounded-xl p-4 h-36 overflow-y-auto font-mono text-[11px] text-slate-400 flex flex-col-reverse gap-1.5 scrollbar-thin">
              {logs.map((log, i) => (
                <div key={i} className="hover:text-white transition-colors">
                  {log}
                </div>
              ))}
            </div>
          </div>
        </section>

      </main>

      {/* Footer */}
      <footer className="mt-12 pt-6 border-t border-slate-900 text-center text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-4">
        <span>© 2026 Translators Project Group. Designed under Clean Architecture patterns.</span>
        <div className="flex gap-4">
          <a href="#docs" className="hover:text-indigo-400 transition-colors">Documentation</a>
          <a href="#help" className="hover:text-indigo-400 transition-colors">Support</a>
        </div>
      </footer>

    </div>
  );
}
