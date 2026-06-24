import { Component, type ReactNode } from 'react'

/** Catches render-time crashes so one broken view doesn't blank the whole app. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app">
          <div className="card" style={{ marginTop: 40 }}>
            <h3>页面出错了</h3>
            <div className="error" style={{ margin: '8px 0 14px' }}>{this.state.error.message}</div>
            <button className="btn" onClick={() => location.reload()}>刷新页面</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
