import type { CalibrationBucket } from '../types'

// Reliability diagram: predicted prob (x) vs observed frequency (y). Points on
// the dashed diagonal = well calibrated. Point size ~ bucket count.
export default function Calibration({ buckets }: { buckets: CalibrationBucket[] }) {
  const S = 240
  const pad = 26
  const x = (v: number) => pad + v * (S - 2 * pad)
  const y = (v: number) => S - pad - v * (S - 2 * pad)

  return (
    <svg viewBox={`0 0 ${S} ${S}`} width="100%" style={{ maxWidth: 280 }}>
      <rect x={pad} y={pad} width={S - 2 * pad} height={S - 2 * pad} fill="none" stroke="#2a3340" />
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#8b98a8" strokeDasharray="4 4" />
      {buckets.map((b, i) => (
        <circle key={i} cx={x(b.mean_pred)} cy={y(b.freq)} r={Math.min(11, 3 + b.count)}
          fill="#2dd4bf" fillOpacity={0.8} stroke="#0d1117" />
      ))}
      <text x={x(0.5)} y={S - 6} fill="#8b98a8" fontSize="9" textAnchor="middle">预测概率</text>
      <text x={10} y={y(0.5)} fill="#8b98a8" fontSize="9" textAnchor="middle"
        transform={`rotate(-90 10 ${y(0.5)})`}>实际频率</text>
    </svg>
  )
}
