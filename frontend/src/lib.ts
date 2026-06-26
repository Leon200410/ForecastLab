import { useCallback, useEffect, useState } from 'react'
import type { Side } from './types'

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)
  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    run()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [run])
  useEffect(() => { reload() }, [reload])
  return { data, error, loading, reload }
}

export const pct = (x?: number | null) => (x == null ? '—' : `${(x * 100).toFixed(0)}%`)
export const pct1 = (x?: number | null) => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
export const money = (x?: number | null) =>
  x == null ? '—' : `$${x.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
export const signMoney = (x?: number | null) =>
  x == null ? '—' : `${x >= 0 ? '+' : ''}$${x.toFixed(2)}`
export const round2 = (x: number) => Math.round(x * 100) / 100
export const pnlClass = (x?: number | null) => (x == null ? '' : x > 0 ? 'pos' : x < 0 ? 'neg' : '')

// Agent's YES/NO call, derived from its probability (P(YES) for the binary
// market). A ±5% band around 0.5 is flagged as a toss-up rather than forced
// onto a side. (Scoring still uses a hard 0.5 split — see ScatterAgentVsMarket.)
export const verdict = (prob?: number | null) => {
  if (prob == null) return { side: '—', word: '', tag: '—', cls: '' }
  if (prob >= 0.45 && prob <= 0.55) return { side: '中性', word: '接近五五开', tag: '≈', cls: 'even' }
  return prob < 0.5
    ? { side: 'NO', word: '不会', tag: 'NO', cls: 'no' }
    : { side: 'YES', word: '会', tag: 'YES', cls: 'yes' }
}

// market timing (Polymarket is UTC -> we display Beijing time, UTC+8) + odds / payout
const _bjDate = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
})
const _bjDateTime = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
})
export const fmtDate = (iso?: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso.slice(0, 10) : _bjDate.format(d)
}
export const fmtDateTime = (iso?: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso.slice(0, 19).replace('T', ' ') : _bjDateTime.format(d)
}
export const fmtOdds = (p?: number | null) => (p && p > 0 ? `${(1 / p).toFixed(2)}x` : '—')
export const winProfit = (stake?: number | null, p?: number | null) =>
  stake && p && p > 0 ? (stake * (1 - p)) / p : 0   // profit if the bet is correct
export const winPayout = (stake?: number | null, p?: number | null) =>
  stake && p && p > 0 ? stake / p : 0               // total returned if correct

// Hypothetical paper bet of EST_STAKE on the analysis's pick (hard 0.5 split),
// entered at the market price when the analysis was made (no future function).
// Mirrors backend metrics.bet_pnl — keep the two in sync.
export const EST_STAKE = 100
export function estBet(agentProb: number, marketProb: number, outcome: 0 | 1) {
  const side: Side = agentProb >= 0.5 ? 'YES' : 'NO'
  const entry = side === 'YES' ? marketProb : 1 - marketProb
  const valid = entry > 0 && entry < 1
  const hit = (side === 'YES' ? 1 : 0) === outcome
  const pnl = !valid ? 0 : hit ? winProfit(EST_STAKE, entry) : -EST_STAKE
  return { side, entry, valid, hit, pnl }
}
