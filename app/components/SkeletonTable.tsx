'use client'

const shimmer: React.CSSProperties = {
  background: 'linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%)',
  backgroundSize: '200% 100%',
  animation: 'shimmer 1.5s infinite',
  borderRadius: 6,
  height: 16,
}

export function SkeletonTable() {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th style={{ width: 48 }}>No.</th>
          <th>Horse</th>
          <th>Jockey</th>
          <th>Trainer</th>
          <th style={{ textAlign: 'right', width: 56 }}>Wt</th>
          <th style={{ textAlign: 'right', width: 56 }}>Draw</th>
          <th style={{ textAlign: 'right', width: 72 }}>Odds</th>
          <th style={{ textAlign: 'right', width: 80 }}>P_final</th>
          <th style={{ textAlign: 'right', width: 80 }}>EV</th>
          <th style={{ textAlign: 'right', width: 80 }}>Kelly%</th>
          <th style={{ width: 140 }}>Tag</th>
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: 8 }).map((_, i) => (
          <tr key={i}>
            {Array.from({ length: 11 }).map((_, j) => (
              <td key={j} style={{ padding: '12px 16px' }}>
                <div style={{ ...shimmer, width: j === 1 ? '80%' : '50%' }} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
