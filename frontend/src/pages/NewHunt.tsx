import { useState, type FormEvent } from "react";
import { api, brl, type SearchWatch } from "../api";

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="font-bold">{label}</span>
      {children}
      {hint && <span className="text-xs text-ink/60">{hint}</span>}
    </label>
  );
}

function SearchItem({ s, onChange }: { s: SearchWatch; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const get = (k: string) => String(f.get(k) ?? "");
    setErr(null); setNote(null);
    try {
      const r = await api.updateSearch(s.id, {
        query: get("query"), min_capacity_gb: num(get("cap")),
        target_price: num(get("target")), max_price_per_gb: num(get("ppg")),
      });
      setNote(r.history_reset ? "Busca trocada: o histórico de avisos foi zerado." : "Salvo!");
      setEditing(false);
      onChange();
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  async function toggle() {
    await api.updateSearch(s.id, { active: !s.active });
    onChange();
  }

  return (
    <li className={`card px-4 py-2 ${s.active ? "" : "opacity-60"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-bold">
          <span className="mr-2 text-xs text-ink/60">c{s.id}</span>“{s.query}”{!s.active && " ⏸"}
        </span>
        <span className="text-sm">
          {s.min_capacity_gb ? `≥ ${s.min_capacity_gb} GB · ` : ""}
          {s.target_price != null ? `até ${brl(s.target_price)} ` : ""}
          {s.max_price_per_gb != null ? `· ${brl(s.max_price_per_gb)}/GB` : ""}
        </span>
        <span className="flex gap-2">
          <button className="btn-ghost" onClick={() => setEditing(!editing)} aria-expanded={editing}
                  aria-label={`Editar caça ${s.query}`}>✏️</button>
          <button className="btn-ghost" onClick={toggle}
                  aria-label={`${s.active ? "Pausar" : "Retomar"} caça ${s.query}`}>{s.active ? "⏸" : "▶️"}</button>
          <button className="btn-ghost" aria-label={`Remover caça ${s.query}`}
                  onClick={async () => { if (confirm(`Apagar a caça “${s.query}”?`)) { await api.removeSearch(s.id); onChange(); } }}>🗑</button>
        </span>
      </div>
      {note && <p className="mt-1 text-sm font-semibold text-mint" role="status">{note}</p>}
      {editing && (
        <form className="mt-3 space-y-3 border-t-2 border-ink/10 pt-3" onSubmit={save}>
          {err && <p className="card bg-pig/30 px-3 py-1 text-sm font-semibold" role="alert">{err}</p>}
          <Field label="Busca" hint="Use | para buscar mais de um termo (até 4). Trocar a busca zera o histórico de avisos.">
            <input name="query" required className="input" defaultValue={s.query} />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Mín. GB"><input name="cap" inputMode="numeric" className="input" defaultValue={s.min_capacity_gb ?? ""} /></Field>
            <Field label="Preço-alvo"><input name="target" inputMode="decimal" className="input" defaultValue={s.target_price ?? ""} /></Field>
            <Field label="Máx. R$/GB"><input name="ppg" inputMode="decimal" className="input" defaultValue={s.max_price_per_gb ?? ""} /></Field>
          </div>
          <p className="text-xs text-ink/60">Deixe um campo vazio para remover a meta. Precisa sobrar ao menos preço-alvo ou R$/GB.</p>
          <div className="flex gap-2">
            <button className="btn" type="submit">Salvar</button>
            <button className="btn-ghost" type="button" onClick={() => setEditing(false)}>Cancelar</button>
          </div>
        </form>
      )}
    </li>
  );
}

export default function NewHunt({ searches, onChange }: { searches: SearchWatch[]; onChange: () => void }) {
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>, kind: "search" | "url") {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const get = (k: string) => String(f.get(k) ?? "");
    setErr(null); setMsg(null);
    try {
      if (kind === "search") {
        await api.addSearch({
          query: get("query"), min_capacity_gb: num(get("cap")),
          target_price: num(get("target")), max_price_per_gb: num(get("ppg")),
        });
        setMsg("Caça criada! O Precinho já está de olho. 🐷");
      } else {
        const r = await api.addTracked({
          url: get("url"), name: get("name"), capacity_gb: num(get("cap")),
          target_price: num(get("target")), max_price_per_gb: num(get("ppg")),
        });
        setMsg(`Acompanhando! Preço agora: ${brl(r.price)} 🐷`);
      }
      form.reset();
      onChange();
    } catch (ex) {
      setErr((ex as Error).message);
    }
  }

  return (
    <section aria-labelledby="h-nova" className="space-y-6">
      <h2 id="h-nova" className="font-display text-2xl font-semibold">Nova caça</h2>
      {msg && <p className="card bg-mint/20 px-4 py-2 font-semibold" role="status">{msg}</p>}
      {err && <p className="card bg-pig/30 px-4 py-2 font-semibold" role="alert">{err}</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        <form className="card space-y-3 p-4" onSubmit={(e) => submit(e, "search")}>
          <h3 className="font-display text-xl font-semibold">🔎 Caçar por busca</h3>
          <p className="text-sm text-ink/70">Varre Buscapé/Zoom (Amazon, Kabum, Magalu). Avisa quando bater uma das metas.</p>
          <Field label="O que caçar?" hint="Dica: use | para várias buscas, ex.: ssd nvme 1tb | ssd nvme 1000gb"><input name="query" required className="input" placeholder="ssd nvme 1tb" /></Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Mín. GB"><input name="cap" inputMode="numeric" className="input" placeholder="960" /></Field>
            <Field label="Preço-alvo"><input name="target" inputMode="decimal" className="input" placeholder="600" /></Field>
            <Field label="Máx. R$/GB"><input name="ppg" inputMode="decimal" className="input" placeholder="0,60" /></Field>
          </div>
          <p className="text-xs text-ink/60">Preencha ao menos uma meta (preço-alvo ou R$/GB).</p>
          <button className="btn" type="submit">Criar caça</button>
        </form>

        <form className="card space-y-3 p-4" onSubmit={(e) => submit(e, "url")}>
          <h3 className="font-display text-xl font-semibold">🔗 Acompanhar um produto (Kabum)</h3>
          <p className="text-sm text-ink/70">Cole o link da página do produto para guardar o histórico de preço.</p>
          <Field label="Link do produto"><input name="url" type="url" required className="input" placeholder="https://www.kabum.com.br/produto/…" /></Field>
          <Field label="Nome"><input name="name" required className="input" placeholder="Kingston A400 480GB" /></Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="GB"><input name="cap" inputMode="numeric" className="input" placeholder="480" /></Field>
            <Field label="Preço-alvo"><input name="target" inputMode="decimal" className="input" placeholder="450" /></Field>
            <Field label="Máx. R$/GB"><input name="ppg" inputMode="decimal" className="input" placeholder="0,60" /></Field>
          </div>
          <button className="btn" type="submit">Acompanhar</button>
        </form>
      </div>

      <div>
        <h3 className="mb-2 font-display text-xl font-semibold">Minhas caças</h3>
        {searches.length === 0 ? (
          <p className="text-sm text-ink/70">Nenhuma ainda.</p>
        ) : (
          <ul className="space-y-2">
            {searches.map((s) => <SearchItem key={s.id} s={s} onChange={onChange} />)}
          </ul>
        )}
      </div>
    </section>
  );
}
