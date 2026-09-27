import { useState } from 'react';
import { KeyRound, Shield, AlertTriangle, Check, Copy, Sparkles, Terminal } from 'lucide-react';

export default function ApiKeyGenerator() {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const generateKey = async () => {
    setLoading(true);
    setError(null);
    setApiKey(null);
    setCopied(false);
    
    try {
      // Determine base URL: assume same host in prod or localhost:8000 in dev
      const baseUrl = window.location.port === '5180' || window.location.port === '3000' 
        ? 'http://localhost:8000' 
        : '';
        
      const response = await fetch(`${baseUrl}/api/generate-key`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to generate API Key.');
      }
      
      const data = await response.json();
      setApiKey(data.api_key);
    } catch (err: any) {
      setError(err.message || 'An error occurred.');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (apiKey) {
      navigator.clipboard.writeText(apiKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex-1 w-full flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-white/70 backdrop-blur-xl border border-white/40 rounded-3xl p-8 shadow-2xl relative overflow-hidden">
        {/* Glow effect */}
        <div className="absolute top-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-400/10 blur-[80px] pointer-events-none"></div>
        
        <div className="flex items-center gap-4 mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/30">
            <KeyRound className="w-7 h-7 text-white" />
          </div>
          <div>
            <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-slate-800 to-slate-600">
              API Keys
            </h1>
            <p className="text-slate-500 mt-1">Generate a secure key to access the translator API directly.</p>
          </div>
        </div>

        {!apiKey ? (
          <div className="space-y-6">
            <div className="bg-emerald-50/50 border border-emerald-100 rounded-2xl p-6">
              <h3 className="font-semibold text-emerald-800 flex items-center gap-2 mb-2">
                <Shield className="w-5 h-5 text-emerald-600" />
                Secure Generation
              </h3>
              <p className="text-emerald-700/80 text-sm leading-relaxed mb-4">
                Your API key will only be shown to you once. It provides full programmatic access to Gemini Live translation streams. 
                Keep it secure and do not expose it in public repositories.
              </p>
              
              <button
                onClick={generateKey}
                disabled={loading}
                className="group relative w-full sm:w-auto inline-flex items-center justify-center gap-3 px-8 py-3.5 bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white rounded-xl shadow-lg shadow-emerald-500/25 transition-all active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100 font-medium font-semibold"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <Sparkles className="w-5 h-5 group-hover:rotate-12 transition-transform" />
                    Create New API Key
                  </>
                )}
              </button>
            </div>
            
            {error && (
              <div className="flex items-start gap-3 text-red-600 bg-red-50 p-4 rounded-xl text-sm">
                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                <p>{error}</p>
              </div>
            )}
            
            <div className="border border-slate-200 bg-slate-50/50 rounded-2xl p-6">
               <h4 className="text-slate-700 font-medium mb-3 flex items-center gap-2">
                 <Terminal className="w-4 h-4 text-slate-400" /> API Usage Example
               </h4>
               <div className="bg-slate-800 rounded-xl p-4 overflow-x-auto text-sm text-emerald-400 font-mono">
                 ws://localhost:8000/ws/translate?api_key=sk_your_key_here
               </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 mb-2">
              <div className="flex gap-3 text-amber-800">
                <AlertTriangle className="w-6 h-6 flex-shrink-0 text-amber-500" />
                <div>
                  <h4 className="font-semibold mb-1">Save this key now</h4>
                  <p className="text-sm text-amber-700/90">
                    For your security, we won't be able to show it to you again. If you lose it, you'll need to generate a new one.
                  </p>
                </div>
              </div>
            </div>

            <div className="relative group">
              <div className="absolute inset-0 bg-gradient-to-r from-emerald-500 to-teal-500 rounded-2xl blur-lg opacity-25 group-hover:opacity-40 transition-opacity"></div>
              <div className="relative flex items-center bg-white border-2 border-emerald-100 rounded-2xl p-1 shadow-sm">
                <div className="flex-1 px-4 py-3 bg-slate-50 rounded-xl font-mono text-lg text-slate-800 overflow-hidden text-ellipsis whitespace-nowrap border border-slate-100">
                  {apiKey}
                </div>
                <button
                  onClick={copyToClipboard}
                  className={`ml-2 mr-1 px-5 py-3 rounded-xl font-medium flex items-center gap-2 transition-all ${
                    copied 
                      ? 'bg-emerald-100 text-emerald-700' 
                      : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-shadow min-w-[120px] justify-center'
                  }`}
                >
                  {copied ? (
                    <>
                      <Check className="w-5 h-5" /> Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-5 h-5" /> Copy Key
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                onClick={() => setApiKey(null)}
                className="px-6 py-2.5 text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-xl font-medium transition-colors"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
