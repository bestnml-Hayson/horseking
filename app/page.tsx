import { RaceDashboard } from './components/RaceDashboard'

export default function Home() {
  return (
    <main className="app-root">
      <header className="app-header">
        <div className="app-header-left">
          <h1 className="app-title">
            <span className="app-title-icon">&#x1F3C7;</span>
            賽馬 AI Live
          </h1>
          <span className="app-version">QUANT ENGINE v3.0</span>
        </div>
        <div className="app-header-sub">
          Benter 量化分析 Dashboard &mdash; Softmax Multinomial Logit + Market Odds Fusion + 1/4 Kelly Criterion
        </div>
      </header>
      <RaceDashboard />
    </main>
  )
}
