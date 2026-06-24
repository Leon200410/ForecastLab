import { useMemo, useState } from 'react'
import { api, forecastStreamUrl } from '../api'
import { pct, useAsync } from '../lib'
import { useToast } from '../components/Toast'
import { ErrorNote, Loading } from '../components/ui'
import type { EventGroup, GroupedItem } from '../types'

const catOf = (i: GroupedItem) => (i.kind === 'event' ? i.category : i.market.category) || '其他'

export default function MarketsPage({ onAnalyzed }: { onAnalyzed: () => void }) {
  const { data, loading, error, reload } = useAsync(() => api.marketsGrouped(), [])
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [category, setCategory] = useState<string | null>(null)

  const cats = useMemo(() => {
    const counts = new Map<string, number>()
    for (const i of data ?? []) counts.set(catOf(i), (counts.get(catOf(i)) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  const shown = (data ?? []).filter((i) => !category || catOf(i) === category)

  function toggle(id: string) {
    setExpanded((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  function analyze(marketId: string, label: string) {
    setBusy(marketId)
    setProgress('开始分析…')
    const es = new EventSource(forecastStreamUrl(marketId))
    let finished = false
    const finish = () => { finished = true; es.close(); setBusy(null); setProgress(null) }

    es.addEventListener('evidence', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      setProgress(`已检索 ${d.count} 条证据、${d.lessons} 条历史复盘,集成分析中…`)
    })
    es.addEventListener('run', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      setProgress(`集成成员 #${d.i + 1}:${Math.round(d.probability * 100)}%(${d.confidence})`)
    })
    es.addEventListener('aggregate', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      setProgress(`聚合完成 ${Math.round(d.agent_prob * 100)}%,写入中…`)
    })
    es.addEventListener('done', (e) => {
      const fc = JSON.parse((e as MessageEvent).data)
      finish()
      toast(`已分析「${label}」(Agent ${Math.round(fc.agent_prob * 100)}%),见「分析 / 押注」。`, 'success')
      onAnalyzed()
    })
    es.addEventListener('failed', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      finish()
      toast(d.message || '分析失败', 'error')
    })
    es.onerror = () => {
      if (finished) return
      finish()
      toast('分析连接中断,请重试。', 'error')
    }
  }

  async function ingest() {
    setBusy('ingest')
    try {
      const r = await api.ingest()
      toast(`已拉取 ${r.ingested} 个开放盘子(来源:${r.source})。`, 'success')
      reload()
    } catch (e) {
      toast('拉取失败:' + (e as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="section-title" style={{ margin: 0 }}>开放市场 · Polymarket(已滤掉已揭晓盘)</div>
        <button className="btn ghost sm" onClick={ingest} disabled={busy === 'ingest'}>
          {busy === 'ingest' ? '拉取中…' : '拉取最新盘子'}
        </button>
      </div>

      {progress && (
        <div className="notice" style={{ marginBottom: 12 }}>
          <span className="spinner" style={{ marginRight: 8 }} />{progress}
        </div>
      )}
      {loading && <Loading />}
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && data.length === 0 && <div className="empty">暂无开放盘子,点「拉取最新盘子」。</div>}

      {data && data.length > 0 && (
        <>
          <div className="chips" style={{ marginBottom: 14 }}>
            <button className={`chip ${!category ? 'active' : ''}`} onClick={() => setCategory(null)}>
              全部<span className="n">{data.length}</span>
            </button>
            {cats.map(([c, n]) => (
              <button key={c} className={`chip ${category === c ? 'active' : ''}`} onClick={() => setCategory(c)}>
                {c}<span className="n">{n}</span>
              </button>
            ))}
          </div>

          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr><th>问题 / 事件</th><th>类别</th><th className="right">市场 YES</th><th></th></tr>
              </thead>
              <tbody>
                {shown.map((item) =>
                  item.kind === 'single' ? (
                    <tr key={item.market.id}>
                      <td>
                        {item.market.question}
                        {item.market.url && (
                          <a className="ext" href={item.market.url} target="_blank" rel="noreferrer">↗ Polymarket</a>
                        )}
                      </td>
                      <td className="muted">{item.market.category || '—'}</td>
                      <td className="right mono">{pct(item.market.current_prob)}</td>
                      <td className="right">
                        <button className="btn sm" disabled={busy === item.market.id}
                          onClick={() => analyze(item.market.id, item.market.question)}>
                          {busy === item.market.id ? '分析中…' : '分析'}
                        </button>
                      </td>
                    </tr>
                  ) : (
                    <EventRows key={item.event_id} ev={item} open={expanded.has(item.event_id)}
                      onToggle={() => toggle(item.event_id)} busy={busy} onAnalyze={analyze} />
                  ),
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function EventRows({ ev, open, onToggle, busy, onAnalyze }: {
  ev: EventGroup
  open: boolean
  onToggle: () => void
  busy: string | null
  onAnalyze: (marketId: string, label: string) => void
}) {
  return (
    <>
      <tr style={{ cursor: 'pointer' }} onClick={onToggle}>
        <td>
          <span className="mono" style={{ marginRight: 6 }}>{open ? '▾' : '▸'}</span>
          <b>{ev.event_title}</b>
          {ev.url && (
            <a className="ext" href={ev.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>↗ Polymarket</a>
          )}
        </td>
        <td className="muted">{ev.category || '—'}</td>
        <td className="right muted">{ev.outcomes.length} 个结果</td>
        <td className="right muted" style={{ fontSize: 12 }}>{open ? '收起' : '展开选择'}</td>
      </tr>
      {open && ev.outcomes.map((o) => (
        <tr key={o.market_id} style={{ background: 'var(--panel-2)' }}>
          <td style={{ paddingLeft: 30 }}>{o.name}</td>
          <td></td>
          <td className="right mono">{pct(o.prob)}</td>
          <td className="right">
            <button className="btn sm" disabled={busy === o.market_id}
              onClick={() => onAnalyze(o.market_id, `${ev.event_title} — ${o.name}`)}>
              {busy === o.market_id ? '分析中…' : '分析'}
            </button>
          </td>
        </tr>
      ))}
    </>
  )
}
