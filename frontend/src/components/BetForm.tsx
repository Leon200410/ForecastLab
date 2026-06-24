import { useState } from 'react'
import { api } from '../api'
import { round2 } from '../lib'
import { useToast } from './Toast'
import { Spinner } from './ui'
import type { Position, Side } from '../types'

export default function BetForm({ position, onClose, onDone }: {
  position: Position; onClose: () => void; onDone: () => void
}) {
  const toast = useToast()
  const yesPrice = position.market_current_prob ?? position.market_prob_at_analysis
  const [side, setSide] = useState<Side>('YES')
  const [stake, setStake] = useState(100)
  const [entry, setEntry] = useState(round2(yesPrice))
  const [note, setNote] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)

  function pick(s: Side) {
    setSide(s)
    setEntry(round2(s === 'YES' ? yesPrice : 1 - yesPrice))
  }

  const stakeOk = Number.isFinite(stake) && stake > 0
  const entryOk = Number.isFinite(entry) && entry > 0 && entry < 1
  const valid = stakeOk && entryOk
  const potential = entryOk ? (stake * (1 - entry)) / entry : 0

  async function submit() {
    setBusy(true)
    setErr(null)
    try {
      await api.placeBet({ forecast_id: position.id, side, stake, entry_prob: entry, note: note || undefined })
      toast(`已记录押注:${side} $${stake} @ ${entry}`, 'success')
      onDone()
    } catch (e) {
      setErr((e as Error).message)
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>记一笔假性押注</h3>
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          {position.question} · Agent {Math.round(position.agent_prob * 100)}% / 市场 {Math.round(yesPrice * 100)}%
        </div>

        <div className="field">
          <label>方向</label>
          <div className="row" style={{ gap: 8 }}>
            <button className={`btn ${side === 'YES' ? '' : 'ghost'}`} onClick={() => pick('YES')}>YES</button>
            <button className={`btn ${side === 'NO' ? '' : 'ghost'}`} onClick={() => pick('NO')}>NO</button>
          </div>
        </div>

        <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
          <div className="field" style={{ flex: 1 }}>
            <label>注码(虚拟 USD)</label>
            <input type="number" min={1} value={stake} onChange={(e) => setStake(Number(e.target.value))} />
            {!stakeOk && <span className="field-err">注码需大于 0</span>}
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>入场价(该侧,0–1)</label>
            <input type="number" min={0.01} max={0.99} step={0.01} value={entry}
              onChange={(e) => setEntry(Number(e.target.value))} />
            {!entryOk && <span className="field-err">入场价需在 0 与 1 之间</span>}
          </div>
        </div>

        <div className="field">
          <label>备注(可选)</label>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="为什么这样押…" />
        </div>

        <div className="notice" style={{ marginBottom: 14 }}>
          赔率 <b>{entryOk ? (1 / entry).toFixed(2) : '—'}x</b> · 押对总返还 <b>${entryOk ? (stake / entry).toFixed(2) : '0'}</b>(净赚 <b>+${potential.toFixed(2)}</b>),押错亏 <b>−${stakeOk ? stake.toFixed(2) : '0'}</b>。纸面记录,从虚拟余额扣减,不接支付。
        </div>

        {err && <div className="error" style={{ marginBottom: 10 }}>{err}</div>}
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          {confirming ? (
            <>
              <span className="muted" style={{ marginRight: 'auto', fontSize: 12.5 }}>
                确认:{side} ${stake} @ {entry}?
              </span>
              <button className="btn ghost" disabled={busy} onClick={() => setConfirming(false)}>返回</button>
              <button className="btn" disabled={busy} onClick={submit}>
                {busy ? <><Spinner /> 提交中…</> : '确定提交'}
              </button>
            </>
          ) : (
            <>
              <button className="btn ghost" onClick={onClose}>取消</button>
              <button className="btn" disabled={!valid} onClick={() => { setErr(null); setConfirming(true) }}>
                确认押注
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
