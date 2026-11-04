import { useState } from "react";
import { api, brl, type Hunt as HuntData } from "../api";
import Thermometer from "../components/Thermometer";

type Props = { data: HuntData | null; onRefresh: () => void };

export default function Hunt({ data, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [onlyVerified, setOnlyVerified] = useState(false);

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
                className={`card flex flex-wrap items-center gap-x-6 gap-y-2 p-4 ${o.is_deal ? "bg-mint/15" : ""}`}>
              <div className="min-w-0 flex-1 basis-64">
                <div className="mb-1 flex flex-wrap gap-1.5">
                  {o.is_deal && <span className="rounded-full border-2 border-ink bg-mint px-2 text-xs font-bold">OFERTA!</span>}
                  {o.verified ? (
                    <span className="rounded-full border-2 border-ink bg-white px-2 text-xs font-bold" title="Preço lido direto na página da loja">✅ conferida</span>
                  ) : (
                    <span className="rounded-full border-2 border-ink bg-gold/60 px-2 text-xs font-bold" title="Preço vindo do Buscapé/Zoom. A oferta pode já não existir na loja.">⚠️ não verificada</span>
                  )}
                  {o.approximate && (
                    <span className="rounded-full border-2 border-ink bg-gold/60 px-2 text-xs font-bold"
                          title="O AliExpress mostra o preço da opção mais barata do anúncio (outra capacidade ou cor). Confira a opção antes de comprar.">≈ preço aproximado</span>
                  )}
                  {o.in_stock === false && <span className="rounded-full border-2 border-ink bg-pig/40 px-2 text-xs font-bold">⛔ sem estoque</span>}
                  {o.in_stock === true && <span className="rounded-full border-2 border-ink bg-white px-2 text-xs font-bold">📦 em estoque</span>}
                </div>
                <p className="font-bold leading-snug">{o.name}</p>
                <p className="text-sm text-ink/70">🏪 {o.merchant} · busca “{o.query}”</p>
              </div>
              <div className="text-right">
                <p className="font-display text-2xl font-semibold">{brl(o.price)}</p>
                <p className="text-sm font-semibold">{o.price_per_gb ? `${brl(o.price_per_gb)}/GB` : "—"}</p>
              </div>
              <Thermometer quality={o.quality} />
              <a className="btn-ghost" href={o.url} target="_blank" rel="noreferrer noopener">Ver loja ↗</a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
