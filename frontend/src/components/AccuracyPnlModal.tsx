import { useState } from 'react'
import { api } from '../api'
import { EST_STAKE, estBet, fmtDate, fmtOdds, money, pct, signMoney, useAsync } from '../lib'
import { ErrorNote, Loading } from './ui'

type Filter = 'all' | 'profit' | 'loss'

// Drill-down for the 预估收益 stat: every resolved forecast as a hypothetical
// $100 bet on the analysis's pick at the analysis-time market price. Per-bet
// math (lib.estBet) mirrors the backend aggregate so the total matches the card.
export default function AccuracyPnlModal({ onClose }: { onClose: () => void }) {
  const { data, loading, error, reload } = useAsync(() => api.positions(), [])
  const [filter, setFilter] = useState<Filter>('all')

  const rows = (data ?? [])
    .filter((p) => p.status === 'resolved' && p.outcome != null)
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .map((p) => ({ p, ...estBet(p.agent_prob, p.market_prob_at_analysis, p.outcome as 0 | 1) }))
    .filter((r) => r.valid)

  const total = rows.reduce((s, r) => s + r.pnl, 0)
  const staked = rows.length * EST_STAKE
  const roi = staked > 0 ? total / staked : 0
  const wins = rows.filter((r) => r.pnl > 0).length
  const losses = rows.filter((r) => r.pnl < 0).length
  const shown = rows.filter((r) => (filter === 'all' ? true : filter === 'profit' ? r.pnl > 0 : r.pnl < 0))

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal scrollable" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-head">
          <div className="row spread">
            <h3>预估收益明细 · 每笔 ${EST_STAKE}</h3>
            <button className="btn ghost sm" onClick={onClose}>关闭</button>
          </div>
          <div className="muted" style={{ fontSize: 12.5, margin: '2px 0 12px' }}>
            共 {rows.length} 笔 · 投入 {money(staked)} · 预估收益{' '}
            <b className={total >= 0 ? 'pos' : 'neg'}>{signMoney(total)}</b> · ROI {(roi * 100).toFixed(0)}%
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className={`chip ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>全部 {rows.length}</button>
            <button className={`chip ${filter === 'profit' ? 'active' : ''}`} onClick={() => setFilter('profit')}>盈利 {wins}</button>
            <button className={`chip ${filter === 'loss' ? 'active' : ''}`} onClick={() => setFilter('loss')}>亏损 {losses}</button>
          </div>
        </div>

        <div className="modal-body" style={{ marginTop: 12 }}>
          {loading && <Loading />}
          {error && <ErrorNote error={error} onRetry={reload} />}
          {data && rows.length === 0 && <div className="muted">还没有已揭晓的盘子。</div>}
          {shown.map(({ p, side, entry, pnl }) => (
            <div key={p.id} className="card" style={{ background: 'var(--panel-2)', padding: '10px 12px' }}>
              <div className="row spread" style={{ gap: 10, alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13 }}>
                    {p.question || p.market_id}
                    {p.url && <a className="ext" href={p.url} target="_blank" rel="noreferrer" title="在 Polymarket 查看">↗</a>}
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    分析 <b>{side}</b> · 入场 {entry.toFixed(2)}（赔率 {fmtOdds(entry)}）· 市场 {pct(p.market_prob_at_analysis)} · {fmtDate(p.close_at || p.created_at)}
                  </div>
                </div>
                <div className="row" style={{ gap: 8, flexShrink: 0 }}>
                  <span className="pill mono">揭晓 {p.outcome === 1 ? 'YES' : 'NO'}</span>
                  <span className={`pill ${pnl >= 0 ? 'win' : 'lose'}`}>{signMoney(pnl)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
