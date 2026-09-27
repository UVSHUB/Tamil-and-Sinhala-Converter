import { useState } from 'react';
import TranslatorPage from './pages/TranslatorPage';
import ApiKeyGenerator from './components/ApiKeyGenerator';
import { KeyRound, Mic } from 'lucide-react';

function App() {
  const [view, setView] = useState<'translator' | 'api-keys'>('translator');

  return (
    <div className="h-screen bg-slate-50 bg-gradient-to-tr from-indigo-50/30 via-slate-50 to-emerald-50/30 flex flex-col relative overflow-hidden">
      {/* Background glowing gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-200/15 blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-200/15 blur-[120px] pointer-events-none"></div>

      {view === 'translator' ? <TranslatorPage /> : <ApiKeyGenerator />}

      {/* Floating Navigation */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex items-center bg-white/70 backdrop-blur-xl border border-white/60 p-1.5 rounded-full shadow-2xl z-50">
        <button
          onClick={() => setView('translator')}
          className={`flex items-center gap-2.5 px-6 py-2.5 rounded-full transition-all duration-300 font-medium ${
            view === 'translator' 
              ? 'bg-indigo-600 text-white shadow-md' 
              : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
          }`}
        >
          <Mic className="w-5 h-5" />
          Translator
        </button>
        
        <button
          onClick={() => setView('api-keys')}
          className={`flex items-center gap-2.5 px-6 py-2.5 rounded-full transition-all duration-300 font-medium ${
            view === 'api-keys' 
              ? 'bg-emerald-600 text-white shadow-md' 
              : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
          }`}
        >
          <KeyRound className="w-5 h-5" />
          API Keys
        </button>
      </div>
    </div>
  );
}

export default App;
