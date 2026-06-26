import type {
  AccountSummary, AuditEntry, Bet, EvalSummary, Forecast, GroupedItem, Holding, Market, Position,
  Review,
} from './types'

// Empty base => relative URLs proxied by Vite to the backend in dev.
const BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
// Optional bearer token for an API_TOKENS-gated backend (internal team auth).
const TOKEN = import.meta.env.VITE_API_TOKEN ?? ''

// SSE stream URL for a live forecast (EventSource can't set headers → token via query).
// fresh=true forces a re-analysis that bypasses the agent-run cache.
export function forecastStreamUrl(marketId: string, opts?: { fresh?: boolean }): string {
  const qs = new URLSearchParams({ market_id: marketId })
  if (opts?.fresh) qs.set('fresh', '1')
  if (TOKEN) qs.set('token', TOKEN)
  return `${BASE}/api/forecasts/stream?${qs.toString()}`
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
    },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<{ ok: boolean; llm: string; llm_ready: boolean; search: string; search_ready: boolean; data_source: string }>('/api/health'),
  markets: (status?: string) => req<Market[]>(`/api/markets${status ? `?status=${status}` : ''}`),
  marketsGrouped: () => req<GroupedItem[]>('/api/markets/grouped'),
  ingest: () => req<{ ingested: number; source: string }>('/api/markets/ingest', { method: 'POST' }),
  positions: () => req<Position[]>('/api/positions'),
  forecast: (market_id: string) =>
    req<Forecast>('/api/forecasts', { method: 'POST', body: JSON.stringify({ market_id }) }),
  getForecast: (id: string) => req<Forecast>(`/api/forecasts/${id}`),
  forecastsByMarket: (marketId: string) =>
    req<Forecast[]>(`/api/forecasts?market_id=${encodeURIComponent(marketId)}`),
  placeBet: (b: { forecast_id: string; side: string; stake: number; entry_prob: number; note?: string }) =>
    req<Bet>('/api/bets', { method: 'POST', body: JSON.stringify(b) }),
  account: () => req<AccountSummary>('/api/account'),
  holdings: () => req<Holding[]>('/api/holdings'),
  review: (id: string) => req<Review>(`/api/forecasts/${id}/review`, { method: 'POST' }),
  evalSummary: () => req<EvalSummary>('/api/eval/summary'),
  audit: () => req<AuditEntry[]>('/api/audit'),
  poll: () => req<Record<string, number>>('/api/poll', { method: 'POST' }),
  devResolve: (market_id: string, outcome: number) =>
    req<unknown>('/api/dev/resolve', { method: 'POST', body: JSON.stringify({ market_id, outcome }) }),
}
