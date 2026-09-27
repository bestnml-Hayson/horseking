import { RaceDashboard } from './components/RaceDashboard'

export default function Home() {
  return (
    <main style={{ maxWidth: 1280, margin: '0 auto', padding: '24px 20px 48px' }}>
      <header style={{ marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>
            Benter 量化分析 Dashboard
          </h1>
          <span style={{
            padding: '3px 10px',
            borderRadius: 9999,
            background: 'rgba(59, 130, 246, 0.12)',
            color: '#93c5fd',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.03em',
          }}>
            QUANT ENGINE v2.2
          </span>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
          Softmax Multinomial Logit + Market Odds Fusion + 1/4 Kelly Criterion
        </p>
      </header>
      <RaceDashboard />
    </main>
  )
}
