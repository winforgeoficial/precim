import type { Mascot as MascotData } from "../api";
import Mascot from "./Mascot";

const HINT: Record<MascotData["mood"], string> = {
  sleep: "Zzz… me dê algo para caçar!",
  sniff: "Farejando… ainda sem ofertas boas.",
  party: "Achei ofertas boas! 🎉",
};

export default function Header({ mascot }: { mascot: MascotData | null }) {
  const mood = mascot?.mood ?? "sleep";
  const pct = Math.round((mascot?.progress ?? 0) * 100);
  return (
    <header className="card flex flex-col items-center gap-4 p-4 sm:flex-row sm:p-6">
      <Mascot mood={mood} />
      <div className="w-full flex-1">
        <h1 className="font-display text-3xl font-semibold">precim</h1>
        <p className="text-lg font-semibold text-pigdark" aria-live="polite">{HINT[mood]}</p>
        {mascot && (
          <div className="mt-3">
            <div className="flex justify-between text-sm font-bold">
              <span>Nível {mascot.level} · {mascot.title}</span>
              <span>{mascot.next_at ? `${mascot.xp}/${mascot.next_at} XP` : `${mascot.xp} XP (máx.)`}</span>
            </div>
            <div className="mt-1 h-4 overflow-hidden rounded-full border-2 border-ink bg-cream"
                 role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full bg-mint transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
