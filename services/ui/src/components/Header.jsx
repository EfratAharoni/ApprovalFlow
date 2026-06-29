import React from 'react'

export default function Header({ currentPage, queueCount }) {
  return (
    <div
      className="flex items-center justify-between px-6 py-4 border-b"
      style={{ background: '#1A1D27', borderColor: '#2D3148' }}
    >
      <h1 className="text-xl font-semibold" style={{ color: '#F8FAFC' }}>{currentPage}</h1>
      {queueCount > 0 && (
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium"
          style={{ background: '#F59E0B20', color: '#F59E0B', border: '1px solid #F59E0B40' }}
        >
          <span className="w-2 h-2 rounded-full" style={{ background: '#F59E0B' }} />
          {queueCount} awaiting review
        </div>
      )}
    </div>
  )
}
