import { useRef } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { api } from '../api'
import { useAsync } from '../lib'
import { ErrorNote, Loading } from '../components/ui'
import Calibration from '../components/Calibration'
import ScatterAgentVsMarket from '../components/ScatterAgentVsMarket'

export default function EvalPage() {
  const { data, loading, error, reload } = useAsync(() => api.evalSummary(), [])
  const f = data?.forecasts
  const rootRef = useRef<HTMLDivElement>(null)

  useGSAP(() => {
    if (!f || f.n === 0) return
    const mm = gsap.matchMedia()
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.grid.cards .card', { opacity: 0, y: 14, stagger: 0.06,
        duration: 0.4, ease: 'power2.out' })
    })
  }, { dependencies: [f?.n ?? 0], scope: rootRef })

  return (
    <div ref={rootRef}>
      <div className="section-title" style={{ marginTop: 0 }}>战绩评估 · Agent 分析质量</div>

      {loading && <Loading />}
      {error && <ErrorNote error={error} onRetry={reload} />}

      {data && f && f.n === 0 && (
        <div className="notice">还没有已揭晓的分析。等盘子揭晓(或用「立即盯市 / 检查揭晓」)后这里会出现 Brier、校准与跑赢市场与否。</div>
      )}

      {data && f && f.n > 0 && (
        <>
          <div className="grid cards" style={{ marginBottom: 16 }}>
            <div className="card stat">
              <div className="label">Agent Brier(越低越好)</div>
              <div className="value">{f.agent_brier?.toFixed(3)}</div>
            </div>
            <div className="card stat">
              <div className="label">市场基准 Brier</div>
              <div className="value">{f.market_brier?.toFixed(3)}</div>
            </div>
            {f.agent_brier_calibrated != null && (
              <div className="card stat">
                <div className="label">校准后 Brier(n={f.n_calibrated})</div>
                <div className={`value ${f.agent_brier != null && f.agent_brier_calibrated <= f.agent_brier ? 'pos' : 'warn'}`}>
                  {f.agent_brier_calibrated.toFixed(3)}
                </div>
              </div>
            )}
            <div className="card stat">
              <div className="label">vs 市场</div>
              <div className={`value small ${f.beats_market ? 'pos' : 'warn'}`}>
                {f.beats_market ? '跑赢市场' : '未跑赢'}
              </div>
            </div>
            <div className="card stat"><div className="label">准确率</div><div className="value small">{((f.accuracy ?? 0) * 100).toFixed(0)}%</div></div>
            <div className="card stat"><div className="label">Log loss</div><div className="value small">{f.log_loss?.toFixed(3)}</div></div>
            <div className="card stat"><div className="label">已揭晓样本</div><div className="value small">{f.n}</div></div>
          </div>

          <div className="grid" style={{ gridTemplateColumns: '280px 1fr', alignItems: 'start' }}>
            <div className="card">
              <div className="section-title" style={{ marginTop: 0 }}>校准曲线</div>
              <Calibration buckets={f.calibration ?? []} />
              {data.points && data.points.length > 0 && (
                <>
                  <div className="section-title">Agent vs 市场(绿=押对方向)</div>
                  <ScatterAgentVsMarket points={data.points} />
                </>
              )}
            </div>
            <div className="card">
              <div className="section-title" style={{ marginTop: 0 }}>说明</div>
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
                <li><b>无未来函数</b>:所有分析都在盘子揭晓前做出,故 Brier 与盈亏诚实可信。</li>
                {f.n < 20 && <li className="warn">样本累计中(n={f.n}),Brier/校准波动大,结论仅作方向性参考。</li>}
                <li>所有分析全留痕(无论是否押注),Agent 战绩无选择偏差。</li>
                <li className="muted">数据源:{data.data_source} · LLM:{data.llm_mode} · 知识库复盘:{data.kb_size} 条</li>
                <li className="muted">LLM 花费:今日 ${(data.cost.today_usd ?? data.cost.total_usd).toFixed(4)} / 日上限 ${data.cost.max_spend_usd} · 累计 ${data.cost.total_usd.toFixed(4)}({data.cost.calls} 次)</li>
                {data.cost.by_kind && Object.keys(data.cost.by_kind).length > 0 && (
                  <li className="muted">成本归因:{Object.entries(data.cost.by_kind).map(([k, v]) => `${k} $${v.toFixed(4)}`).join(' · ')}</li>
                )}
                {f.by_version && (
                  <li className="muted">按 prompt 版本:{Object.entries(f.by_version).map(([v, d]) => `${v}(n=${d.n})Brier ${d.agent_brier.toFixed(3)}`).join(' · ')}</li>
                )}
                {data.cache && (
                  <li className="muted">缓存命中率:{(data.cache.hit_rate * 100).toFixed(0)}%({data.cache.hits} 命中 / {data.cache.misses} 未命中)</li>
                )}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
