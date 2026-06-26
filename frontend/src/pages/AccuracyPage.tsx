import { useRef, useState } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { api } from '../api'
import { signMoney, useAsync } from '../lib'
import { ErrorNote, Loading } from '../components/ui'
import AccuracyGauge from '../components/AccuracyGauge'
import AccuracyDetailModal from '../components/AccuracyDetailModal'
import AccuracyPnlModal from '../components/AccuracyPnlModal'

export default function AccuracyPage() {
  const { data, loading, error, reload } = useAsync(() => api.evalSummary(), [])
  const f = data?.forecasts
  const rootRef = useRef<HTMLDivElement>(null)
  const [showDetail, setShowDetail] = useState(false)
  const [showPnl, setShowPnl] = useState(false)
  const [catDetail, setCatDetail] = useState<string | null>(null)

  useGSAP(() => {
    if (!f || f.n === 0) return
    const mm = gsap.matchMedia()
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.grid.cards .card', { opacity: 0, y: 14, stagger: 0.06,
        duration: 0.4, ease: 'power2.out', clearProps: 'transform,opacity' })
    })
  }, { dependencies: [f?.n ?? 0], scope: rootRef })

  const acc = f?.accuracy ?? 0
  const macc = f?.market_accuracy ?? null
  const n = f?.n ?? 0
  const correct = Math.round(acc * n)
  const wrong = n - correct
  const edge = macc == null ? null : acc - macc
  const estPnl = f?.est_pnl_100 ?? null
  const estRoi = f?.est_roi ?? null

  return (
    <div ref={rootRef}>
      <div className="section-title" style={{ marginTop: 0 }}>准确率 · 分析判断 vs 实际揭晓</div>

      {loading && <Loading />}
      {error && <ErrorNote error={error} onRetry={reload} />}

      {data && f && f.n === 0 && (
        <div className="notice">还没有已揭晓的分析。等盘子揭晓(或用「立即盯市 / 检查揭晓」)后,这里会出现分析判断与实际结果的命中率。</div>
      )}

      {data && f && f.n > 0 && (
        <>
        <div className="grid" style={{ gridTemplateColumns: '300px 1fr', alignItems: 'start' }}>
          <div className="card" style={{ textAlign: 'center' }}>
            <AccuracyGauge value={acc} baseline={macc} label="分析命中率" />
            <div className="muted" style={{ fontSize: 12.5, marginTop: 8 }}>
              已揭晓 {n} 个盘子 · 命中 {correct} / 落空 {wrong}
            </div>
            {macc != null && (
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                刻度线 ＝ 市场基准 {(macc * 100).toFixed(0)}%
              </div>
            )}
          </div>

          <div>
            <div className="grid cards" style={{ marginBottom: 16, alignItems: 'stretch' }}>
              <div className="card stat" role="button" tabIndex={0} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', height: '100%' }}
                title="点击查看命中/落空明细"
                onClick={() => setShowDetail(true)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setShowDetail(true) } }}>
                <div className="label">命中 / 落空</div>
                <div className="value small"><span className="pos">{correct}</span> / <span className="neg">{wrong}</span></div>
                <div className="muted" style={{ fontSize: 11, marginTop: 'auto', paddingTop: 6 }}>点击查看明细 ›</div>
              </div>
              <div className="card stat" role="button" tabIndex={0} style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', height: '100%' }}
                title="点击查看每笔预估收益明细"
                onClick={() => setShowPnl(true)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setShowPnl(true) } }}>
                <div className="label">预估收益 · 每笔 $100</div>
                <div className={`value small ${estPnl != null ? (estPnl >= 0 ? 'pos' : 'neg') : ''}`}>
                  {estPnl != null ? signMoney(estPnl) : '—'}
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 'auto', paddingTop: 6 }}>
                  ROI {estRoi != null ? `${(estRoi * 100).toFixed(0)}%` : '—'} · 点击明细 ›
                </div>
              </div>
              {macc != null && (
                <div className="card stat" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                  <div className="label">市场基准命中率</div>
                  <div className="value small">{(macc * 100).toFixed(0)}%</div>
                </div>
              )}
              {edge != null && (
                <div className="card stat" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                  <div className="label">相对市场</div>
                  <div className={`value small ${edge >= 0 ? 'pos' : 'neg'}`}>
                    {edge >= 0 ? '+' : ''}{(edge * 100).toFixed(0)} pts
                  </div>
                </div>
              )}
            </div>

            <div className="card">
              <div className="section-title" style={{ marginTop: 0 }}>说明</div>
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
                <li><b>命中</b>＝分析判断的方向(概率 ≥ 50% 记为 YES,否则 NO)与盘子实际揭晓结果一致。</li>
                <li>仅统计<b>已揭晓</b>的盘子(n={n});进行中的盘子不计入。</li>
                {macc != null && <li>市场基准 ＝ 用盘子当时的市场概率按同样规则判断的命中率,作为对照。</li>}
                <li><b>预估收益</b>＝若每笔都按 $100 押在分析判断的一侧、以分析时的市场价入场:押对赚 100×(1−入场价)/入场价,押错亏 $100。非真实下注。</li>
                {n < 20 && <li className="warn">样本较少(n={n}),命中率波动大,仅作方向性参考。</li>}
                <li className="muted">与「战绩评估」同源:所有分析均在揭晓前做出,无未来函数。</li>
              </ul>
            </div>
          </div>
        </div>

        {f.by_category && Object.keys(f.by_category).length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="section-title">分品类命中率 · 各品类用专属 agent,点行看该品类明细</div>
            <div className="card" style={{ padding: 0 }}>
              <table>
                <thead>
                  <tr>
                    <th>品类</th><th className="right">样本</th><th className="right">命中率</th>
                    <th className="right">市场基准</th><th className="right">相对市场</th><th className="right">Brier A/M</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(f.by_category).map(([cat, s]) => {
                    const e = s.accuracy - s.market_accuracy
                    return (
                      <tr key={cat} style={{ cursor: 'pointer' }} title="点击查看该品类命中/落空明细"
                        onClick={() => setCatDetail(cat)}>
                        <td>{cat}</td>
                        <td className="right mono">{s.n}</td>
                        <td className="right mono">{(s.accuracy * 100).toFixed(0)}%</td>
                        <td className="right mono muted">{(s.market_accuracy * 100).toFixed(0)}%</td>
                        <td className={`right mono ${e >= 0 ? 'pos' : 'neg'}`}>
                          {e >= 0 ? '+' : ''}{(e * 100).toFixed(0)} pts
                        </td>
                        <td className="right mono">{s.agent_brier.toFixed(3)} / {s.market_brier.toFixed(3)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
        </>
      )}

      {showDetail && <AccuracyDetailModal onClose={() => setShowDetail(false)} />}
      {showPnl && <AccuracyPnlModal onClose={() => setShowPnl(false)} />}
      {catDetail && <AccuracyDetailModal category={catDetail} onClose={() => setCatDetail(null)} />}
    </div>
  )
}
