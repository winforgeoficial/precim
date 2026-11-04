import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, brl, type HistoryPoint, type Hunt as HuntData, type Offer, type Source } from "../api";
import Thermometer from "../components/Thermometer";

type Props = { data: HuntData | null; sources: Source[]; onRefresh: () => void };

const STATE_STYLE: Record<Source["state"], string> = {
  ok: "bg-mint/30", falhando: "bg-pig/50", bloqueada: "bg-gold/60", aguardando: "bg-white",
};
const STATE_TEXT: Record<Source["state"], string> = {
  ok: "✓ ok", falhando: "✗ falhando", bloqueada: "⏸ bloqueada (pausa de 12 h)", aguardando: "… aguardando",
};

function SourceChips({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2 text-xs" aria-label="Saúde das fontes">
      {sources.map((s) => (
        <li key={s.source} className={`rounded-full border-2 border-ink px-2.5 py-0.5 font-bold ${STATE_STYLE[s.state]}`}
            title={s.detail ?? (s.last_ok_at ? `Última leitura ok: ${new Date(s.last_ok_at).toLocaleString("pt-BR")}` : "Ainda sem leitura")}>
          {s.label} {STATE_TEXT[s.state]}{s.state === "falhando" ? ` (${s.failures}×)` : ""}
        </li>
      ))}
    </ul>
  );
}

function OfferHistory({ offer }: { offer: Offer }) {
  const [points, setPoints] = useState<HistoryPoint[] | null>(null);
  useEffect(() => {
    let alive = true;
    api.offerHistory(offer.watch_id, offer.key).then((p) => alive && setPoints(p)).catch(() => alive && setPoints([]));
    return () => { alive = false; };
  }, [offer.watch_id, offer.key]);
  const chart = (points ?? []).map((p) => ({
    label: new Date(p.at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }), price: p.price,
  }));
  return (
    <div className="mt-2 h-44 w-full basis-full" role="img" aria-label="Gráfico do histórico de preços da oferta">
      {points === null ? <p className="py-6 text-center text-sm">Carregando…</p> : chart.length < 2 ? (
        <p className="py-6 text-center text-sm text-ink/70">Poucos pontos ainda — o gráfico aparece quando o preço mudar ou nas próximas varreduras.</p>
      ) : (
        <ResponsiveContainer>
          <LineChart data={chart}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3b2a2a22" />
            <XAxis dataKey="label" tick={{ fontSize: 12 }} />
            <YAxis domain={["auto", "auto"]} tick={{ fontSize: 12 }} width={64} tickFormatter={(v) => `R$${v}`} />
            <Tooltip formatter={(v: number) => brl(v)} />
            <Line type="stepAfter" dataKey="price" stroke="#e8738c" strokeWidth={3} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default function Hunt({ data, sources, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [onlyVerified, setOnlyVerified] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.runHunt();
      setMsg(r.alerts_sent ? `🎉 ${r.alerts_sent} oferta(s) avisada(s)!` : "Caçada feita. Nada novo para avisar.");
      onRefresh();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const all = data?.offers ?? [];
  const offers = onlyVerified ? all.filter((o) => o.verified) : all;
  const verifiedCount = all.filter((o) => o.verified).length;
  return (
    <section aria-labelledby="h-caca" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="h-caca" className="font-display text-2xl font-semibold">A caça de hoje</h2>
          <p className="text-sm text-ink/70">
            {data?.last_scan
              ? `Última varredura: ${new Date(data.last_scan).toLocaleString("pt-BR")}`
              : "Ainda sem varredura."}
          </p>
        </div>
        <button className="btn" onClick={run} disabled={busy}>
          {busy ? "Farejando…" : "🔎 Caçar agora"}
        </button>
      </div>
      <SourceChips sources={sources} />
      {msg && <p className="card bg-gold/30 px-4 py-2 font-semibold" role="status">{msg}</p>}

      {all.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <label className="flex cursor-pointer items-center gap-2 font-bold">
            <input type="checkbox" className="h-4 w-4 accent-mint" checked={onlyVerified}
                   onChange={(e) => setOnlyVerified(e.target.checked)} />
            Só conferidas na loja ({verifiedCount} de {all.length})
          </label>
          <span className="text-ink/70">
            <b>✅ conferida</b>: preço lido direto na loja · <b>≈ aproximado</b>: AliExpress mostra o valor da opção mais barata · <b>⚠️ não verificada</b>: vem do Buscapé e pode já não existir.
          </span>
        </div>
      )}

      {offers.length === 0 ? (
        <p className="card p-6 text-center">
          Nada na toca ainda. Crie uma caça na aba <b>Nova caça</b> e o Precinho começa a farejar.
        </p>
      ) : offers.length === 0 ? (
        <p className="card p-6 text-center">
          Nenhuma oferta conferida na loja ainda. A conferência direta da Kabum roda a cada 3 horas — desmarque o filtro para ver as do Buscapé.
        </p>
      ) : (
        <ul className="space-y-3">
          {offers.map((o, i) => (
            <li key={`${o.url}-${i}`}
                className={`card flex flex-wrap items-center gap-x-6 gap-y-2 p-4 ${o.is_deal && o.verified ? "bg-mint/15" : ""}`}>
              <div className="min-w-0 flex-1 basis-64">
                <div className="mb-1 flex flex-wrap gap-1.5">
                  {o.is_deal && (o.verified
                    ? <span className="rounded-full border-2 border-ink bg-mint px-2 text-xs font-bold">OFERTA!</span>
                    : <span className="rounded-full border-2 border-dashed border-ink bg-white px-2 text-xs font-bold" title="Está dentro da sua meta, mas o preço não foi conferido na loja: não gera alerta no grupo.">possível oferta</span>)}
                  {o.verified ? (
                    <span className="rounded-full border-2 border-ink bg-white px-2 text-xs font-bold" title="Preço lido direto na página da loja">✅ conferida</span>
                  ) : (
                    <span className="rounded-full border-2 border-ink bg-gold/60 px-2 text-xs font-bold" title="Preço vindo do Buscapé/Zoom. A oferta pode já não existir na loja.">⚠️ não verificada</span>
                  )}
                  {o.approximate && (
                    <span className="rounded-full border-2 border-ink bg-gold/60 px-2 text-xs font-bold"
                          title="O AliExpress mostra o preço da opção mais barata do anúncio (outra capacidade ou cor). Confira a opção antes de comprar.">≈ preço aproximado</span>
                  )}
                  {o.suspect && (
                    <span className="rounded-full border-2 border-ink bg-pig/50 px-2 text-xs font-bold"
                          title="R$/GB abaixo de metade da mediana das lojas conferidas. Costuma ser capacidade falsificada ou preço de outra opção. Não gera alerta.">⚠️ preço suspeito</span>
                  )}
                  {o.is_lowest && (
                    <span className="rounded-full border-2 border-ink bg-gold/60 px-2 text-xs font-bold" title="Menor preço registrado para esta oferta">🏆 menor preço visto</span>
                  )}
                  {o.fake_discount && (
                    <span className="rounded-full border-2 border-ink bg-pig/40 px-2 text-xs font-bold"
                          title="O “preço antigo” informado pela loja nunca apareceu no histórico do precim.">🤨 desconto duvidoso</span>
                  )}
                  {o.in_stock === false && <span className="rounded-full border-2 border-ink bg-pig/40 px-2 text-xs font-bold">⛔ sem estoque</span>}
                  {o.in_stock === true && <span className="rounded-full border-2 border-ink bg-white px-2 text-xs font-bold">📦 em estoque</span>}
                </div>
                <p className="font-bold leading-snug">{o.name}</p>
                <p className="text-sm text-ink/70">🏪 {o.merchant} · busca “{o.query}”</p>
              </div>
              <div className="text-right">
                <p className="font-display text-2xl font-semibold">{brl(o.price)}</p>
                <p className="text-sm font-semibold">
                  {o.capacity_gb ? `${o.capacity_gb >= 1000 ? `${o.capacity_gb / 1000} TB` : `${o.capacity_gb} GB`} · ` : ""}
                  {o.price_per_gb ? `${brl(o.price_per_gb)}/GB` : "—"}
                </p>
              </div>
              <Thermometer quality={o.quality} />
              <button className="btn-ghost" aria-expanded={openKey === `${o.watch_id}|${o.key}`}
                      onClick={() => setOpenKey(openKey === `${o.watch_id}|${o.key}` ? null : `${o.watch_id}|${o.key}`)}>
                📈 histórico{o.low_price != null && o.high_price != null && o.high_price > o.low_price
                  ? ` (${brl(o.low_price)} – ${brl(o.high_price)})` : ""}
              </button>
              <a className="btn-ghost" href={o.url} target="_blank" rel="noreferrer noopener">Ver loja ↗</a>
              {openKey === `${o.watch_id}|${o.key}` && <OfferHistory offer={o} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
