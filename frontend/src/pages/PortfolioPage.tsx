import { useRef, useState } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { api } from '../api'
import { fmtDateTime, fmtOdds, money, pct, pnlClass, signMoney, useAsync, winProfit } from '../lib'
import { useToast } from '../components/Toast'
import { ErrorNote, Loading } from '../components/ui'

export default function PortfolioPage() {
  const acc = useAsync(() => api.account(), [])
  const holds = useAsync(() => api.holdings(), [])
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useGSAP(() => {
    if (!acc.data) return
    const mm = gsap.matchMedia()
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.grid.cards .card', { opacity: 0, y: 14, stagger: 0.06,
        duration: 0.4, ease: 'power2.out' })
    })
  }, { dependencies: [!!acc.data], scope: rootRef })

  async function poll() {
    setBusy(true)
    try {
      await api.poll()
      toast('已盯市并检查揭晓。', 'success')
    } catch (e) {
      toast('盯市失败:' + (e as Error).message, 'error')
    } finally {
      setBusy(false)
      acc.reload()
      holds.reload()
    }
  }

  const a = acc.data
  return (
    <div ref={rootRef}>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="section-title" style={{ margin: 0 }}>虚拟组合 · 纸面账户</div>
        <button className="btn ghost sm" onClick={poll} disabled={busy}>{busy ? '盯市中…' : '立即盯市 / 检查揭晓'}</button>
      </div>

      {acc.loading && <Loading />}
      {acc.error && <ErrorNote error={acc.error} onRetry={acc.reload} />}

      {a && (
        <div className="grid cards" style={{ marginBottom: 16 }}>
          <div className="card stat">
            <div className="label">总权益</div>
            <div className="value">{money(a.equity)}</div>
            <div className={`mono ${pnlClass(a.return_pct)}`}>{a.return_pct >= 0 ? '+' : ''}{a.return_pct}%</div>
          </div>
          <div className="card stat"><div className="label">可用现金</div><div className="value small">{money(a.cash_balance)}</div></div>
          <div className="card stat"><div className="label">持仓现值</div><div className="value small">{money(a.open_positions_value)}</div></div>
          <div className="card stat"><div className="label">已实现盈亏</div><div className={`value small ${pnlClass(a.realized_pnl)}`}>{signMoney(a.realized_pnl)}</div></div>
          <div className="card stat"><div className="label">浮动盈亏</div><div className={`value small ${pnlClass(a.unrealized_pnl)}`}>{signMoney(a.unrealized_pnl)}</div></div>
          <div className="card stat"><div className="label">本金 / 持仓数</div><div className="value small">{money(a.starting_balance)} · {a.open_count}</div></div>
        </div>
      )}

      <div className="section-title">当前持仓(盯市为参考,不可兑现)</div>
      {holds.error && <ErrorNote error={holds.error} onRetry={holds.reload} />}
      {holds.data && holds.data.length === 0 && <div className="empty">暂无开放持仓。</div>}
      {holds.data && holds.data.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr>
                <th>市场</th><th>方向</th><th className="right">注码</th><th className="right">入场价(赔率)</th>
                <th className="right">押对赚</th><th className="right">当前价</th>
                <th className="right">浮动盈亏</th><th className="right">截止</th>
              </tr>
            </thead>
            <tbody>
              {holds.data.map((h) => (
                <tr key={h.id}>
                  <td>{h.question || h.market_id}
                    {h.url && <a className="ext" href={h.url} target="_blank" rel="noreferrer">↗</a>}</td>
                  <td><span className={`pill ${h.side === 'YES' ? 'yes' : 'no'}`}>{h.side}</span></td>
                  <td className="right mono">${h.stake}</td>
                  <td className="right mono">{pct(h.entry_prob)} <span className="muted">({fmtOdds(h.entry_prob)})</span></td>
                  <td className="right mono pos">+${winProfit(h.stake, h.entry_prob).toFixed(2)}</td>
                  <td className="right mono">{pct(h.current_price)}</td>
                  <td className={`right mono ${pnlClass(h.unrealized_pnl)}`}>{signMoney(h.unrealized_pnl)}</td>
                  <td className="right muted" style={{ fontSize: 12 }}>{fmtDateTime(h.close_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
