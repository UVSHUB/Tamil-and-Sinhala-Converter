import TranslatorPage from './pages/TranslatorPage';

function App() {
  return (
    <div className="min-h-screen bg-slate-950 bg-gradient-radial from-slate-900 via-slate-950 to-slate-950 flex flex-col">
      {/* Background glowing gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-900/10 blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-900/10 blur-[120px] pointer-events-none"></div>

      <TranslatorPage />
    </div>
  );
}

export default App;
