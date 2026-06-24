import { api } from '../api'
import { fmtDateTime, useAsync } from '../lib'
import { ErrorNote, Loading } from '../components/ui'

const LABELS: Record<string, string> = { forecast: '分析', bet: '押注', review: '复盘' }

export default function AuditPage() {
  const { data, loading, error, reload } = useAsync(() => api.audit(), [])

  return (
    <div>
      <div className="section-title" style={{ marginTop: 0 }}>审计 · 团队操作留痕(最近 100 条,最新在前)</div>

      {loading && <Loading />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <div className="empty">暂无操作记录。分析、押注、复盘都会被记录在此(含操作人)。</div>
      )}

      {data && data.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>时间</th><th>用户</th><th>动作</th><th>目标</th></tr></thead>
            <tbody>
              {data.map((e, i) => (
                <tr key={i}>
                  <td className="muted mono" style={{ fontSize: 12 }}>{fmtDateTime(e.t)}</td>
                  <td>{e.user}</td>
                  <td><span className="pill">{LABELS[e.action] ?? e.action}</span></td>
                  <td className="muted mono" style={{ fontSize: 12 }}>{e.target || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
