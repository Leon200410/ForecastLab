// A 270° dial gauge. The value arc fills clockwise from the lower-left; the
// center shows the percentage. An optional baseline tick marks a reference point
// on the arc (here: the market's hit-rate, for comparison).
export default function AccuracyGauge({ value, baseline, label }: {
  value: number             // 0–1, the headline accuracy
  baseline?: number | null  // 0–1, optional reference marker
  label?: string
}) {
  const S = 240, cx = S / 2, cy = S / 2, r = 92, sw = 18
  const C = 2 * Math.PI * r
  const sweep = 0.75                 // the dial spans 270° of the circle
  const arc = C * sweep
  const rot = 135                    // dash starts at lower-left, gap centered at bottom
  const frac = Math.max(0, Math.min(1, value))

  const tick = baseline == null ? null : (() => {
    const a = (rot + Math.max(0, Math.min(1, baseline)) * sweep * 360) * Math.PI / 180
    const r0 = r - sw / 2 - 3, r1 = r + sw / 2 + 3
    return {
      x1: cx + r0 * Math.cos(a), y1: cy + r0 * Math.sin(a),
      x2: cx + r1 * Math.cos(a), y2: cy + r1 * Math.sin(a),
    }
  })()

  return (
    <svg viewBox={`0 0 ${S} ${S}`} width="100%" style={{ maxWidth: 240 }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--border-2)" strokeWidth={sw}
        strokeDasharray={`${arc} ${C}`} strokeLinecap="round"
        transform={`rotate(${rot} ${cx} ${cy})`} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--iris)" strokeWidth={sw}
        strokeDasharray={`${frac * arc} ${C}`} strokeLinecap="round"
        transform={`rotate(${rot} ${cx} ${cy})`} />
      {tick && (
        <line x1={tick.x1} y1={tick.y1} x2={tick.x2} y2={tick.y2}
          stroke="var(--text)" strokeWidth={2.5} strokeLinecap="round" />
      )}
      <text x={cx} y={cy - 2} textAnchor="middle" fill="var(--text)"
        fontFamily="var(--font-mono)" fontSize="46" fontWeight="700">
        {Math.round(value * 100)}%
      </text>
      <text x={cx} y={cy + 26} textAnchor="middle" fill="var(--muted)" fontSize="12">
        {label ?? '命中率'}
      </text>
    </svg>
  )
}
