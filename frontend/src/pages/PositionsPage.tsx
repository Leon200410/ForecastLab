import { useState } from 'react'
import { api } from '../api'
import { fmtDate, fmtDateTime, fmtOdds, pct, pnlClass, signMoney, useAsync, winProfit } from '../lib'
import type { Position } from '../types'
import BetForm from '../components/BetForm'
import ForecastDetail from '../components/ForecastDetail'

export default function PositionsPage() {
  const { data, loading, error, reload } = useAsync(() => api.positions(), [])
  const [onlyBets, setOnlyBets] = useState(false)
  const [betFor, setBetFor] = useState<Position | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)

  const rows = (data ?? []).filter((p) => !onlyBets || p.bet)

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="section-title" style={{ margin: 0 }}>分析 / 押注 · 统一列表</div>
        <label className="row muted" style={{ gap: 6, fontSize: 12.5 }}>
          <input type="checkbox" checked={onlyBets} onChange={(e) => setOnlyBets(e.target.checked)} /> 只看押注的
        </label>
      </div>

      {loading && <div className="empty">加载中…</div>}
      {error && <div className="error">{error}</div>}
      {data && rows.length === 0 && (
        <div className="empty">还没有分析。去「盘子浏览」选一个盘子点「分析」。</div>
      )}

      {rows.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>问题</th><th>Agent vs 市场</th><th>状态</th>
                <th className="right">Brier A/M</th><th>你的押注</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <Row key={p.id} p={p} onBet={() => setBetFor(p)} onDetail={() => setDetailId(p.id)} onChanged={reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {betFor && <BetForm position={betFor} onClose={() => setBetFor(null)} onDone={() => { setBetFor(null); reload() }} />}
      {detailId && (
        <ForecastDetail id={detailId} url={(data ?? []).find((p) => p.id === detailId)?.url}
          onClose={() => setDetailId(null)} onChanged={reload} />
      )}
    </div>
  )
}

function Row({ p, onBet, onDetail, onChanged }: {
  p: Position; onBet: () => void; onDetail: () => void; onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const resolved = p.status === 'resolved'

  async function review() {
    setBusy(true)
    try { await api.review(p.id) } finally { setBusy(false); onChanged() }
  }

  return (
    <tr>
      <td style={{ maxWidth: 320 }}>
        {p.question || p.market_id}
        {p.url && <a className="ext" href={p.url} target="_blank" rel="noreferrer" title="在 Polymarket 查看">↗</a>}
        {resolved && p.outcome != null && (
          <span className={`pill ${p.outcome === 1 ? 'yes' : 'no'}`} style={{ marginLeft: 6 }}>
            结果 {p.outcome === 1 ? 'YES' : 'NO'}
          </span>
        )}
        <div className="muted" style={{ fontSize: 11.5, marginTop: 3 }}>
          {p.bet && p.opened_at && <>开盘 {fmtDate(p.opened_at)} · </>}
          截止 {fmtDateTime(p.close_at)}
          {p.bet && (
            <> · 赔率 {fmtOdds(p.bet.entry_prob)} · 押对赚 +${winProfit(p.bet.stake, p.bet.entry_prob).toFixed(0)}</>
          )}
        </div>
      </td>
      <td><ProbBars agent={p.agent_prob} market={p.market_prob_at_analysis} /></td>
      <td><span className={`pill ${resolved ? 'resolved' : 'open'}`}>{resolved ? '已揭晓' : '进行中'}</span></td>
      <td className="right mono">
        {p.brier != null ? `${p.brier.toFixed(3)} / ${p.market_brier?.toFixed(3)}` : '—'}
      </td>
      <td>
        {p.bet ? (
          <span className="row" style={{ gap: 6 }}>
            <span className={`pill ${p.bet.side === 'YES' ? 'yes' : 'no'}`}>{p.bet.side}</span>
            <span className="mono">${p.bet.stake}</span>
            {p.bet.pnl != null ? (
              <span className={`mono ${pnlClass(p.bet.pnl)}`}>{signMoney(p.bet.pnl)}</span>
            ) : p.bet.unrealized_pnl != null ? (
              <span className={`mono ${pnlClass(p.bet.unrealized_pnl)}`} title="浮动盈亏(盯市)">
                {signMoney(p.bet.unrealized_pnl)}*
              </span>
            ) : null}
          </span>
        ) : <span className="muted">—</span>}
      </td>
      <td className="right">
        <div className="row" style={{ justifyContent: 'flex-end', gap: 6 }}>
          {!p.bet && !resolved && p.market_status === 'open' && (
            <button className="btn sm" onClick={onBet}>押注</button>
          )}
          {resolved && !p.reviewed && (
            <button className="btn sm ghost" disabled={busy} onClick={review}>
              {busy ? '复盘中…' : '分析/复盘'}
            </button>
          )}
          <button className="btn sm ghost" onClick={onDetail}>详情</button>
        </div>
      </td>
    </tr>
  )
}

function ProbBars({ agent, market }: { agent: number; market: number }) {
  return (
    <div style={{ minWidth: 150 }}>
      <div className="row" style={{ gap: 8 }} title="Agent 概率">
        <span className="mono" style={{ width: 34 }}>{pct(agent)}</span>
        <div className="bar"><span style={{ width: `${agent * 100}%` }} /></div>
      </div>
      <div className="row" style={{ gap: 8, marginTop: 4 }} title="分析时市场价">
        <span className="mono muted" style={{ width: 34 }}>{pct(market)}</span>
        <div className="bar market"><span style={{ width: `${market * 100}%` }} /></div>
      </div>
    </div>
  )
}
