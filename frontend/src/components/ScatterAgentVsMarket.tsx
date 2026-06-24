// Agent vs market scatter: market prob (x) vs agent prob (y) for resolved
// forecasts. Points off the dashed diagonal = the agent disagreed with the
// market; green = the agent's direction was right, red = wrong.
export default function ScatterAgentVsMarket({ points }: {
  points: { a: number; m: number; o: 0 | 1 }[]
}) {
  const S = 240
  const pad = 26
  const x = (v: number) => pad + v * (S - 2 * pad)
  const y = (v: number) => S - pad - v * (S - 2 * pad)

  return (
    <svg viewBox={`0 0 ${S} ${S}`} width="100%" style={{ maxWidth: 280 }}>
      <rect x={pad} y={pad} width={S - 2 * pad} height={S - 2 * pad} fill="none" stroke="var(--border-2)" />
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--muted)" strokeDasharray="4 4" />
      {points.map((p, i) => {
        const correct = (p.a >= 0.5 ? 1 : 0) === p.o
        return (
          <circle key={i} cx={x(p.m)} cy={y(p.a)} r={3.5}
            fill={correct ? 'var(--mint)' : 'var(--coral)'} fillOpacity={0.8}
            stroke="var(--bg)" strokeWidth={0.5} />
        )
      })}
      <text x={x(0.5)} y={S - 6} fill="var(--muted)" fontSize="9" textAnchor="middle">市场概率</text>
      <text x={10} y={y(0.5)} fill="var(--muted)" fontSize="9" textAnchor="middle"
        transform={`rotate(-90 10 ${y(0.5)})`}>Agent 概率</text>
    </svg>
  )
}
