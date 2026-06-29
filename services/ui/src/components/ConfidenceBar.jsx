import React from 'react'

export default function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100)
  const color = value >= 0.8 ? '#22C55E' : value >= 0.6 ? '#F59E0B' : '#EF4444'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full" style={{ background: '#2D3148' }}>
        <div
          className="h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-sm font-medium font-mono" style={{ color, minWidth: 36 }}>{pct}%</span>
    </div>
  )
}
