/** Termômetro da oferta: 100 = mais barato (R$/GB) entre tudo que foi caçado. */
export default function Thermometer({ quality }: { quality: number | null }) {
  if (quality == null) return <span className="text-xs text-ink/60">sem R$/GB</span>;
  const color = quality >= 75 ? "bg-mint" : quality >= 40 ? "bg-gold" : "bg-pig";
  const label = quality >= 75 ? "Ótima" : quality >= 40 ? "Razoável" : "Cara";
  return (
    <div className="w-28" title={`${label} (${quality}/100 vs. o que foi caçado)`}>
      <div className="h-2.5 overflow-hidden rounded-full border-2 border-ink bg-cream">
        <div className={`h-full ${color}`} style={{ width: `${Math.max(quality, 6)}%` }} />
      </div>
      <span className="text-xs font-bold">{label}</span>
    </div>
  );
}
