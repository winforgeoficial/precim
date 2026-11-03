import type { Mascot } from "../api";

export default function Achievements({ mascot }: { mascot: Mascot | null }) {
  const list = mascot?.achievements ?? [];
  return (
    <section aria-labelledby="h-conq" className="space-y-4">
      <h2 id="h-conq" className="font-display text-2xl font-semibold">Conquistas</h2>
      {mascot && (
        <p className="text-sm text-ink/70">
          {mascot.stats.tracked} caça(s)/produto(s) · {mascot.stats.scans} coletas · {mascot.stats.alerts_sent} alerta(s) enviados
        </p>
      )}
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((a) => (
          <li key={a.id} className={`card p-4 ${a.unlocked ? "bg-gold/30" : "opacity-60"}`}>
            <p className="text-3xl" aria-hidden="true">{a.unlocked ? "🏆" : "🔒"}</p>
            <p className="font-display text-lg font-semibold">{a.title}</p>
            <p className="text-sm">{a.description}</p>
            <p className="mt-1 text-xs font-bold">{a.unlocked ? "Desbloqueada!" : "Bloqueada"}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
