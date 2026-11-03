import { useCallback, useEffect, useState } from "react";
import { api, type Hunt as HuntData, type Mascot, type SearchWatch, type Tracked as T } from "./api";
import Header from "./components/Header";
import Achievements from "./pages/Achievements";
import Hunt from "./pages/Hunt";
import NewHunt from "./pages/NewHunt";
import Tracked from "./pages/Tracked";

const TABS = [
  { id: "caca", label: "🔎 Caça" },
  { id: "produtos", label: "📈 Acompanhados" },
  { id: "nova", label: "➕ Nova caça" },
  { id: "conquistas", label: "🏆 Conquistas" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function App() {
  const [tab, setTab] = useState<TabId>("caca");
  const [hunt, setHunt] = useState<HuntData | null>(null);
  const [mascot, setMascot] = useState<Mascot | null>(null);
  const [tracked, setTracked] = useState<T[]>([]);
  const [searches, setSearches] = useState<SearchWatch[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [h, m, t, s] = await Promise.all([api.hunt(), api.mascot(), api.tracked(), api.searches()]);
      setHunt(h); setMascot(m); setTracked(t); setSearches(s); setError(null);
    } catch (e) {
      setError(`Não consegui falar com o servidor (${(e as Error).message}).`);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 60_000);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6">
      <Header mascot={mascot} />
      {error && <p className="card bg-pig/30 px-4 py-2 font-semibold" role="alert">{error}</p>}
      <nav aria-label="Seções" className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} aria-current={tab === t.id ? "page" : undefined}
                  className={`rounded-xl border-2 border-ink px-4 py-2 font-display font-semibold ${tab === t.id ? "bg-pig shadow-pop" : "bg-white hover:bg-cream"}`}>
            {t.label}
          </button>
        ))}
      </nav>
      <main>
        {tab === "caca" && <Hunt data={hunt} onRefresh={refresh} />}
        {tab === "produtos" && <Tracked items={tracked} onChange={refresh} />}
        {tab === "nova" && <NewHunt searches={searches} onChange={refresh} />}
        {tab === "conquistas" && <Achievements mascot={mascot} />}
      </main>
      <footer className="pt-4 text-center text-xs text-ink/60">
        precim · uso pessoal · preços vêm de Buscapé/Zoom e Kabum e podem estar defasados.
      </footer>
    </div>
  );
}
