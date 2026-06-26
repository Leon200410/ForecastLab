import { useEffect, useMemo, useRef, useState } from 'react'
import { api, forecastStreamUrl } from '../api'
import { pct, useAsync, verdict } from '../lib'
import { useToast } from '../components/Toast'
import { ErrorNote, Loading } from '../components/ui'
import type { EventGroup, GroupedItem } from '../types'

const catOf = (i: GroupedItem) => (i.kind === 'event' ? i.category : i.market.category) || '其他'

export default function MarketsPage() {
  const { data, loading, error, reload } = useAsync(() => api.marketsGrouped(), [])
  const toast = useToast()
  // each market analyzes independently → track per-market progress (presence = running)
  const [inflight, setInflight] = useState<Record<string, { label: string; msg: string }>>({})
  const [busyIngest, setBusyIngest] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [category, setCategory] = useState<string | null>(null)
  const esRef = useRef<Map<string, EventSource>>(new Map())

  // close any still-open streams when leaving the page
  useEffect(() => () => { esRef.current.forEach((es) => es.close()); esRef.current.clear() }, [])

  const cats = useMemo(() => {
    const counts = new Map<string, number>()
    for (const i of data ?? []) counts.set(catOf(i), (counts.get(catOf(i)) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [data])

  const shown = (data ?? []).filter((i) => !category || catOf(i) === category)
  const running = new Set(Object.keys(inflight))

  function toggle(id: string) {
    setExpanded((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  function analyze(marketId: string, label: string) {
    if (esRef.current.has(marketId)) return // already running
    const setMsg = (msg: string) => setInflight((p) => ({ ...p, [marketId]: { label, msg } }))
    setMsg('开始分析…')
    const es = new EventSource(forecastStreamUrl(marketId))
    esRef.current.set(marketId, es)
    let finished = false
    const finish = () => {
      if (finished) return
      finished = true
      es.close()
      esRef.current.delete(marketId)
      setInflight((p) => { const n = { ...p }; delete n[marketId]; return n })
    }

    es.addEventListener('evidence', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      setMsg(`已检索 ${d.count} 条证据、${d.lessons} 条历史复盘,集成分析中…`)
    })
    es.addEventListener('run', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      setMsg(`集成成员 #${d.i + 1}:${Math.round(d.probability * 100)}%(${d.confidence})`)
    })
    es.addEventListener('aggregate', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      setMsg(`聚合完成 ${Math.round(d.agent_prob * 100)}%,写入中…`)
    })
    es.addEventListener('done', (e) => {
      const fc = JSON.parse((e as MessageEvent).data)
      finish()
      const v = verdict(fc.agent_prob)
      toast(`已分析「${label}」:判断 ${v.side}(${v.word},${Math.round(fc.agent_prob * 100)}%),见「分析 / 押注」。`, 'success')
    })
    es.addEventListener('failed', (e) => {
      const d = JSON.parse((e as MessageEvent).data)
      finish()
      toast(`「${label}」分析失败:${d.message || '未知错误'}`, 'error')
    })
    es.onerror = () => {
      if (finished) return
      finish()
      toast(`「${label}」分析连接中断,请重试。`, 'error')
    }
  }

  async function ingest() {
    setBusyIngest(true)
    try {
      const r = await api.ingest()
      toast(`已拉取 ${r.ingested} 个开放盘子(来源:${r.source})。`, 'success')
      reload()
    } catch (e) {
      toast('拉取失败:' + (e as Error).message, 'error')
    } finally {
      setBusyIngest(false)
    }
  }

  const runningList = Object.entries(inflight)

  return (
    <div>
      <div className="row spread" style={{ marginBottom: 12 }}>
        <div className="section-title" style={{ margin: 0 }}>开放市场 · Polymarket(已滤掉已揭晓盘)</div>
        <button className="btn ghost sm" onClick={ingest} disabled={busyIngest}>
          {busyIngest ? '拉取中…' : '拉取最新盘子'}
        </button>
      </div>

      {runningList.length > 0 && (
        <div className="notice" style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div className="muted" style={{ fontSize: 12, letterSpacing: '.04em' }}>{runningList.length} 个盘子分析中(可同时进行)</div>
          {runningList.map(([id, { label, msg }]) => (
            <div key={id} className="row" style={{ gap: 8 }}>
              <span className="spinner" />
              <span style={{ fontSize: 12.5 }}><b>{label}</b> · {msg}</span>
            </div>
          ))}
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
                        <button className="btn sm" disabled={running.has(item.market.id)}
                          onClick={() => analyze(item.market.id, item.market.question)}>
                          {running.has(item.market.id) ? '分析中…' : '分析'}
                        </button>
                      </td>
                    </tr>
                  ) : (
                    <EventRows key={item.event_id} ev={item} open={expanded.has(item.event_id)}
                      onToggle={() => toggle(item.event_id)} running={running} onAnalyze={analyze} />
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

function EventRows({ ev, open, onToggle, running, onAnalyze }: {
  ev: EventGroup
  open: boolean
  onToggle: () => void
  running: Set<string>
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
            <button className="btn sm" disabled={running.has(o.market_id)}
              onClick={() => onAnalyze(o.market_id, `${ev.event_title} — ${o.name}`)}>
              {running.has(o.market_id) ? '分析中…' : '分析'}
            </button>
          </td>
        </tr>
      ))}
    </>
  )
}
