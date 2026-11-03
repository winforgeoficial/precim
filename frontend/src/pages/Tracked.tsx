import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, brl, type HistoryPoint, type Tracked as T } from "../api";

function Delta({ now, before }: { now: number | null; before: number | null }) {
  if (now == null || before == null || now === before) return null;
  const down = now < before;
  return <span className={`text-sm font-bold ${down ? "text-mint" : "text-pigdark"}`}>
    {down ? "▼" : "▲"} {Math.abs(((now - before) / before) * 100).toFixed(1)}%
  </span>;
}

function Card({ item, onChange }: { item: T; onChange: () => void }) {
  const [hist, setHist] = useState<HistoryPoint[] | null>(null);
  const [open, setOpen] = useState(false);

  async function toggle() {
    if (!open && !hist) setHist(await api.history(item.id));
    setOpen(!open);
  }
  async function remove() {
    if (confirm(`Parar de acompanhar “${item.name}”?`)) { await api.removeTracked(item.id); onChange(); }
  }
  const chart = (hist ?? []).map((p) => ({ ...p, label: new Date(p.at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) }));

  return (
    <li className="card p-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1 basis-64">
          <p className="font-bold leading-snug">{item.name}</p>
          <p className="text-sm text-ink/70">
            🏪 {item.store} · {item.in_stock == null ? "estoque ?" : item.in_stock ? "📦 em estoque" : "⛔ sem estoque"}
            {item.target_price != null && ` · alvo ${brl(item.target_price)}`}
          </p>
        </div>
        <div className="text-right">
          <p className="font-display text-2xl font-semibold">{brl(item.price)} <Delta now={item.price} before={item.previous_price} /></p>
          <p className="text-sm">
            {item.old_price && <s className="mr-2 text-ink/50">{brl(item.old_price)}</s>}
            {item.price_per_gb ? `${brl(item.price_per_gb)}/GB` : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={toggle} aria-expanded={open}>{open ? "Esconder" : "📈 Histórico"}</button>
          <a className="btn-ghost" href={item.url} target="_blank" rel="noreferrer noopener">Loja ↗</a>
          <button className="btn-ghost" onClick={remove} aria-label={`Remover ${item.name}`}>🗑</button>
        </div>
      </div>
      {open && (
        <div className="mt-4 h-52" role="img" aria-label="Gráfico do histórico de preços">
          {chart.length < 2 ? (
            <p className="py-8 text-center text-sm text-ink/70">Poucos pontos ainda — o gráfico aparece após algumas varreduras.</p>
          ) : (
            <ResponsiveContainer>
              <LineChart data={chart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#3b2a2a22" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12 }} width={64} tickFormatter={(v) => `R$${v}`} />
                <Tooltip formatter={(v: number) => brl(v)} />
                <Line type="monotone" dataKey="price" stroke="#e8738c" strokeWidth={3} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </li>
  );
}

export default function Tracked({ items, onChange }: { items: T[]; onChange: () => void }) {
  return (
    <section aria-labelledby="h-ac" className="space-y-4">
      <h2 id="h-ac" className="font-display text-2xl font-semibold">Produtos acompanhados</h2>
      {items.length === 0 ? (
        <p className="card p-6 text-center">Nenhum produto por URL ainda. Cole o link de um SSD da Kabum na aba <b>Nova caça</b>.</p>
      ) : (
        <ul className="space-y-3">{items.map((i) => <Card key={i.id} item={i} onChange={onChange} />)}</ul>
      )}
    </section>
  );
}
