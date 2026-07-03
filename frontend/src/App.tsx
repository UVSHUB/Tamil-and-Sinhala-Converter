import TranslatorPage from './pages/TranslatorPage';

function App() {
  return (
    <div className="h-screen bg-slate-50 bg-gradient-to-tr from-indigo-50/30 via-slate-50 to-emerald-50/30 flex flex-col relative overflow-hidden">
      {/* Background glowing gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-200/15 blur-[120px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-emerald-200/15 blur-[120px] pointer-events-none"></div>

      <TranslatorPage />
    </div>
  );
}

export default App;
