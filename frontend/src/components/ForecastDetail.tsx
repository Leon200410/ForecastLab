import { useState } from 'react'
import { api } from '../api'
import { fmtDateTime, fmtOdds, pct, signMoney, useAsync, verdict, winProfit } from '../lib'
import { Loading } from './ui'

export default function ForecastDetail({ id, url, onClose, onChanged }: {
  id: string; url?: string | null; onClose: () => void; onChanged: () => void
}) {
  const { data: fc, loading, reload } = useAsync(() => api.getForecast(id), [id])
  const [busy, setBusy] = useState(false)

  async function review() {
    setBusy(true)
    try { await api.review(id); reload(); onChanged() } finally { setBusy(false) }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        {loading && <Loading />}
        {fc && (
          <>
            <div className="row spread">
              <h3 style={{ maxWidth: 560 }}>
                {fc.review?.question || fc.market_id}
                {url && <a className="ext" href={url} target="_blank" rel="noreferrer" title="在 Polymarket 查看">↗</a>}
              </h3>
              <button className="btn ghost sm" onClick={onClose}>关闭</button>
            </div>
            {(() => {
              const v = verdict(fc.agent_prob)
              return (
                <div className={`verdict ${v.cls}`}>
                  <span className="verdict-k">Agent 判断</span>
                  <span className="verdict-v">{v.side}<em>{v.word}</em></span>
                  <span className="verdict-meta">概率 {pct(fc.agent_prob)}</span>
                </div>
              )
            })()}
            <div className="row" style={{ gap: 16, margin: '8px 0 14px', flexWrap: 'wrap' }}>
              <span>Agent <b>{pct(fc.agent_prob)}</b></span>
              {fc.agent_prob_calibrated != null && (
                <span className="muted" title="按历史已揭晓样本校准后的概率">校准 <b>{pct(fc.agent_prob_calibrated)}</b></span>
              )}
              <span className="muted">市场 {pct(fc.market_prob_at_analysis)}</span>
              <span className="muted">置信 {fc.confidence}</span>
              <span className={`pill ${fc.status === 'resolved' ? 'resolved' : 'open'}`}>
                {fc.status === 'resolved' ? '已揭晓' : '进行中'}
              </span>
              {fc.prompt_version && <span className="muted" style={{ fontSize: 11 }}>prompt {fc.prompt_version}</span>}
              {fc.status === 'resolved' && fc.brier != null && (
                <span className="muted">Brier {fc.brier.toFixed(3)} / 市场 {fc.market_brier?.toFixed(3)}</span>
              )}
            </div>

            <div className="row" style={{ gap: 16, margin: '0 0 14px', fontSize: 12.5 }}>
              {fc.opened_at && <span className="muted">开盘 {fmtDateTime(fc.opened_at)}</span>}
              {fc.close_at && <span className="muted">截止 {fmtDateTime(fc.close_at)}</span>}
              <span className="muted" style={{ fontSize: 11 }}>北京时间</span>
              {fc.bet && (
                <span>赔率 <b>{fmtOdds(fc.bet.entry_prob)}</b> · 押对赚{' '}
                  <b className="pos">+${winProfit(fc.bet.stake, fc.bet.entry_prob).toFixed(2)}</b></span>
              )}
            </div>

            <div className="section-title">理由</div>
            <div>{fc.rationale || '—'}</div>

            {fc.key_factors.length > 0 && (
              <>
                <div className="section-title">关键因素</div>
                <div className="kf">{fc.key_factors.map((k, i) => <span key={i}>{k}</span>)}</div>
              </>
            )}

            <div className="section-title">N 次集成预测</div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {fc.runs.map((r, i) => (
                <span key={i} className="pill mono" title={r.rationale}>{pct(r.probability)} · {r.confidence}</span>
              ))}
            </div>

            {fc.retrieved_lessons.length > 0 && (
              <>
                <div className="section-title">注入的过往复盘(RAG)</div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {fc.retrieved_lessons.map((l, i) => <li key={i} className="muted">{l}</li>)}
                </ul>
              </>
            )}

            <div className="section-title">证据({fc.evidence.length})</div>
            {fc.evidence.length === 0 && <div className="muted">(无)</div>}
            {fc.evidence.map((e, i) => (
              <div key={i} style={{ marginBottom: 8 }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className="pill mono">{e.relevance.toFixed(2)}</span>
                  <a href={e.url} target="_blank" rel="noreferrer">{e.title || e.url}</a>
                </div>
                <div className="muted" style={{ fontSize: 12.5 }}>{e.summary}</div>
              </div>
            ))}

            {fc.review ? (
              <>
                <div className="section-title">复盘</div>
                <div className="card" style={{ background: 'var(--panel-2)' }}>
                  <div><b>结果:</b>{fc.review.outcome === 1 ? 'YES' : 'NO'}
                    {fc.review.bet_pnl != null && <> · 押注盈亏 {signMoney(fc.review.bet_pnl)}</>}</div>
                  <div style={{ marginTop: 6 }}><b>发生了什么:</b>{fc.review.what_happened}</div>
                  <div style={{ marginTop: 6 }}><b>为什么:</b>{fc.review.why}</div>
                  <div style={{ marginTop: 6 }}><b>教训:</b>{fc.review.lesson}</div>
                </div>
              </>
            ) : fc.status === 'resolved' ? (
              <div style={{ marginTop: 16 }}>
                <button className="btn" disabled={busy} onClick={review}>
                  {busy ? '复盘中…' : '生成复盘 → 写入知识库'}
                </button>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
