import { useState } from 'react'
import { api } from './api'
import { useAsync } from './lib'
import MarketsPage from './pages/MarketsPage'
import PositionsPage from './pages/PositionsPage'
import PortfolioPage from './pages/PortfolioPage'
import EvalPage from './pages/EvalPage'

type Tab = 'markets' | 'positions' | 'portfolio' | 'eval'

export default function App() {
  const [tab, setTab] = useState<Tab>('markets')
  const { data: h } = useAsync(() => api.health(), [])

  return (
    <div className="app">
      <header className="top">
        <h1><span className="tag">Forecast</span>Lab</h1>
        <span className="sub">事件预测 Agent · 选盘 → 分析 → 假性押注 → 揭晓 → 复盘进化</span>
        <div className="badges">
          {h && <span className={`badge ${h.llm_ready ? 'live' : 'mock'}`} title={h.llm_ready ? '' : '未配置 API key'}>LLM: {h.llm}{h.llm_ready ? '' : ' ⚠'}</span>}
          {h && <span className={`badge ${h.search_ready ? 'live' : 'mock'}`} title={h.search_ready ? '' : '未配置搜索 key'}>检索: {h.search}{h.search_ready ? '' : ' ⚠'}</span>}
          {h && <span className={`badge ${h.data_source === 'polymarket' ? 'live' : 'mock'}`}>数据: {h.data_source}</span>}
        </div>
      </header>

      <nav className="tabs">
        <button className={tab === 'markets' ? 'active' : ''} onClick={() => setTab('markets')}>盘子浏览</button>
        <button className={tab === 'positions' ? 'active' : ''} onClick={() => setTab('positions')}>分析 / 押注</button>
        <button className={tab === 'portfolio' ? 'active' : ''} onClick={() => setTab('portfolio')}>虚拟组合</button>
        <button className={tab === 'eval' ? 'active' : ''} onClick={() => setTab('eval')}>战绩评估</button>
      </nav>

      {tab === 'markets' && <MarketsPage key="m" onAnalyzed={() => setTab('positions')} />}
      {tab === 'positions' && <PositionsPage key="p" />}
      {tab === 'portfolio' && <PortfolioPage key="pf" />}
      {tab === 'eval' && <EvalPage key="e" />}

      <footer className="disc">
        仅供研究与分析,非投资建议。Agent 只做分析、不做下注决策;所有押注均为用户手输的虚拟纸面记录,不接支付,不构成任何真实交易。
      </footer>
    </div>
  )
}
