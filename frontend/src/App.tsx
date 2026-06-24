import { useRef, useState } from 'react'
import gsap from 'gsap'
import { useGSAP } from '@gsap/react'
import { api } from './api'
import { useAsync } from './lib'
import MarketsPage from './pages/MarketsPage'
import PositionsPage from './pages/PositionsPage'
import PortfolioPage from './pages/PortfolioPage'
import EvalPage from './pages/EvalPage'
import AuditPage from './pages/AuditPage'

gsap.registerPlugin(useGSAP)

type Tab = 'markets' | 'positions' | 'portfolio' | 'eval' | 'audit'

export default function App() {
  const [tab, setTab] = useState<Tab>('markets')
  const { data: h } = useAsync(() => api.health(), [])
  const appRef = useRef<HTMLDivElement>(null)
  const viewRef = useRef<HTMLElement>(null)

  // mount: header + tabs ease in (skipped under prefers-reduced-motion)
  useGSAP(() => {
    const mm = gsap.matchMedia()
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('header.top', { y: -14, opacity: 0, duration: 0.45, ease: 'power3.out' })
      gsap.from('nav.tabs button', { y: -6, opacity: 0, stagger: 0.05, duration: 0.3,
        delay: 0.1, ease: 'power2.out' })
    })
  }, { scope: appRef })

  // health badges pop in once the /health call resolves
  useGSAP(() => {
    if (!h) return
    const mm = gsap.matchMedia()
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('header.top .badge', { opacity: 0, scale: 0.85, stagger: 0.06,
        duration: 0.3, ease: 'back.out(1.7)' })
    })
  }, { dependencies: [!!h], scope: appRef })

  // smooth page transition on every tab switch
  useGSAP(() => {
    const mm = gsap.matchMedia()
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from(viewRef.current, { opacity: 0, y: 10, duration: 0.32, ease: 'power2.out' })
    })
  }, { dependencies: [tab], scope: viewRef })

  return (
    <div className="app" ref={appRef}>
      <header className="top">
        <div className="brand">
          <svg className="brand-mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="1.25" y="1.25" width="21.5" height="21.5" rx="6.5" stroke="url(#fl-mark)" strokeWidth="1.5" />
            <line x1="6" y1="9" x2="18" y2="9" stroke="var(--iris)" strokeWidth="1.75" strokeLinecap="round" opacity="0.45" />
            <circle cx="15" cy="9" r="2.1" fill="var(--iris)" />
            <line x1="6" y1="15" x2="18" y2="15" stroke="var(--azure)" strokeWidth="1.75" strokeLinecap="round" opacity="0.45" />
            <circle cx="9" cy="15" r="2.1" fill="var(--azure)" />
            <defs>
              <linearGradient id="fl-mark" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
                <stop stopColor="var(--iris-bright)" />
                <stop offset="1" stopColor="var(--azure)" />
              </linearGradient>
            </defs>
          </svg>
          <h1><span className="tag">Forecast</span>Lab</h1>
        </div>
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
        <button className={tab === 'audit' ? 'active' : ''} onClick={() => setTab('audit')}>审计</button>
      </nav>

      <main className="view" ref={viewRef}>
        {tab === 'markets' && <MarketsPage key="m" onAnalyzed={() => setTab('positions')} />}
        {tab === 'positions' && <PositionsPage key="p" />}
        {tab === 'portfolio' && <PortfolioPage key="pf" />}
        {tab === 'eval' && <EvalPage key="e" />}
        {tab === 'audit' && <AuditPage key="a" />}
      </main>

      <footer className="disc">
        仅供研究与分析,非投资建议。Agent 只做分析、不做下注决策;所有押注均为用户手输的虚拟纸面记录,不接支付,不构成任何真实交易。
      </footer>
    </div>
  )
}
