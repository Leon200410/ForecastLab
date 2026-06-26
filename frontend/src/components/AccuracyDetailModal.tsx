import { useState } from 'react'
import { api } from '../api'
import { fmtDate, pct, useAsync } from '../lib'
import { ErrorNote, Loading } from './ui'

type Filter = 'all' | 'hit' | 'miss'

// Drill-down for the 命中/落空 stat: lists every resolved forecast with its
// analysis call vs the revealed outcome. Hit = direction matched (hard 0.5
// split — same rule as the backend accuracy metric), so counts match the card.
export default function AccuracyDetailModal({ category, onClose }: { category?: string; onClose: () => void }) {
  const { data, loading, error, reload } = useAsync(() => api.positions(), [])
  const [filter, setFilter] = useState<Filter>('all')

  const rows = (data ?? [])
    .filter((p) => p.status === 'resolved' && p.outcome != null)
    .filter((p) => !category || (p.category || '其他') === category)
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .map((p) => {
      const call: 0 | 1 = p.agent_prob >= 0.5 ? 1 : 0
      return { p, call, hit: call === p.outcome }
    })
  const hits = rows.filter((r) => r.hit).length
  const misses = rows.length - hits
  const shown = rows.filter((r) => (filter === 'all' ? true : filter === 'hit' ? r.hit : !r.hit))

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal scrollable" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-head">
          <div className="row spread">
            <h3>命中 / 落空 明细{category ? ` · ${category}` : ''}</h3>
            <button className="btn ghost sm" onClick={onClose}>关闭</button>
          </div>
          <div className="muted" style={{ fontSize: 12.5, margin: '2px 0 12px' }}>
            已揭晓 {rows.length} · <span className="pos">命中 {hits}</span> · <span className="neg">落空 {misses}</span>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className={`chip ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>全部 {rows.length}</button>
            <button className={`chip ${filter === 'hit' ? 'active' : ''}`} onClick={() => setFilter('hit')}>命中 {hits}</button>
            <button className={`chip ${filter === 'miss' ? 'active' : ''}`} onClick={() => setFilter('miss')}>落空 {misses}</button>
          </div>
        </div>

        <div className="modal-body" style={{ marginTop: 12 }}>
          {loading && <Loading />}
          {error && <ErrorNote error={error} onRetry={reload} />}
          {data && rows.length === 0 && <div className="muted">还没有已揭晓的盘子。</div>}
          {shown.map(({ p, call, hit }) => (
            <div key={p.id} className="card" style={{ background: 'var(--panel-2)', padding: '10px 12px' }}>
              <div className="row spread" style={{ gap: 10, alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13 }}>
                    {p.question || p.market_id}
                    {p.url && <a className="ext" href={p.url} target="_blank" rel="noreferrer" title="在 Polymarket 查看">↗</a>}
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                    分析 <b>{call === 1 ? 'YES' : 'NO'}</b> {pct(p.agent_prob)} · 市场 {pct(p.market_prob_at_analysis)} · {fmtDate(p.close_at || p.created_at)}
                  </div>
                </div>
                <div className="row" style={{ gap: 8, flexShrink: 0 }}>
                  <span className="pill mono">揭晓 {p.outcome === 1 ? 'YES' : 'NO'}</span>
                  <span className={`pill ${hit ? 'win' : 'lose'}`}>{hit ? '命中' : '落空'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
