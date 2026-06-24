import { api } from '../api'
import { useAsync } from '../lib'
import Calibration from '../components/Calibration'

export default function EvalPage() {
  const { data, loading, error } = useAsync(() => api.evalSummary(), [])
  const f = data?.forecasts

  return (
    <div>
      <div className="section-title" style={{ marginTop: 0 }}>战绩评估 · Agent 分析质量</div>

      {loading && <div className="empty">加载中…</div>}
      {error && <div className="error">{error}</div>}

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
            </div>
            <div className="card">
              <div className="section-title" style={{ marginTop: 0 }}>说明</div>
              <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
                <li><b>无未来函数</b>:所有分析都在盘子揭晓前做出,故 Brier 与盈亏诚实可信。</li>
                {f.n < 20 && <li className="warn">样本累计中(n={f.n}),Brier/校准波动大,结论仅作方向性参考。</li>}
                <li>所有分析全留痕(无论是否押注),Agent 战绩无选择偏差。</li>
                <li className="muted">数据源:{data.data_source} · LLM:{data.llm_mode} · 知识库复盘:{data.kb_size} 条</li>
                <li className="muted">LLM 花费:${data.cost.total_usd.toFixed(4)} / 上限 ${data.cost.max_spend_usd}({data.cost.calls} 次调用)</li>
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
