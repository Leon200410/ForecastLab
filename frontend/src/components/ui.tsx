/** Small shared feedback primitives: spinner, loading placeholder, error+retry. */

export function Spinner({ size = 14 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden />
}

export function Loading({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="empty">
      <Spinner /> <span style={{ marginLeft: 8 }}>{label}</span>
    </div>
  )
}

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="error-note">
      <span className="error">{error}</span>
      {onRetry && <button className="btn ghost sm" onClick={onRetry}>重试</button>}
    </div>
  )
}
