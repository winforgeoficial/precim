export type Offer = {
  name: string; merchant: string; price: number; capacity_gb: number | null;
  price_per_gb: number | null; lowering_pct: number; url: string; query: string;
  seen_at: string; is_deal: boolean; quality: number | null;
  source: string; verified: boolean; in_stock: boolean | null; approximate: boolean;
};
export type Hunt = { offers: Offer[]; last_scan: string | null };
export type Tracked = {
  id: number; name: string; store: string; url: string; capacity_gb: number | null;
  price: number | null; old_price: number | null; previous_price: number | null;
  price_per_gb: number | null; in_stock: boolean | null; target_price: number | null;
  updated_at: string | null;
};
export type SearchWatch = {
  id: number; query: string; min_capacity_gb: number | null;
  target_price: number | null; max_price_per_gb: number | null; active: boolean;
};
export type Source = {
  source: string; label: string; state: "ok" | "falhando" | "bloqueada" | "aguardando";
  last_ok_at: string | null; failures: number; detail: string | null;
};
export type Achievement = { id: string; title: string; description: string; unlocked: boolean };
export type Mascot = {
  level: number; title: string; xp: number; next_at: number | null; progress: number;
  mood: "sleep" | "sniff" | "party"; achievements: Achievement[];
  stats: { scans: number; alerts_sent: number; tracked: number };
};
export type HistoryPoint = { at: string; price: number; old_price: number | null };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `Erro ${res.status}`;
    try { const j = await res.json(); if (typeof j.detail === "string") detail = j.detail; } catch { /* sem corpo */ }
    throw new Error(detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  hunt: () => call<Hunt>("/api/hunt"),
  runHunt: () => call<{ alerts_sent: number }>("/api/hunt/run", { method: "POST" }),
  sources: () => call<Source[]>("/api/sources"),
  mascot: () => call<Mascot>("/api/mascot"),
  tracked: () => call<Tracked[]>("/api/watch"),
  history: (id: number) => call<HistoryPoint[]>(`/api/watch/${id}/history`),
  addTracked: (body: Record<string, unknown>) =>
    call<{ listing_id: number; price: number | null }>("/api/watch", { method: "POST", body: JSON.stringify(body) }),
  removeTracked: (id: number) => call<void>(`/api/watch/${id}`, { method: "DELETE" }),
  searches: () => call<SearchWatch[]>("/api/search-watch"),
  addSearch: (body: Record<string, unknown>) =>
    call<{ id: number }>("/api/search-watch", { method: "POST", body: JSON.stringify(body) }),
  updateSearch: (id: number, body: Record<string, unknown>) =>
    call<SearchWatch & { history_reset: boolean }>(`/api/search-watch/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  removeSearch: (id: number) => call<void>(`/api/search-watch/${id}`, { method: "DELETE" }),
};

export const brl = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
