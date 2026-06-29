import React, { useState, useEffect, useRef } from 'react'
import { Search, RefreshCw, Copy, Check } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { getStatus } from '../api'
import StatusBadge from '../components/StatusBadge'

const PROCESSING_STATUSES = ['PENDING', 'PROCESSING']

function TimelineStep({ label, value, done, active }) {
  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <div
          className="w-3 h-3 rounded-full mt-1 flex-shrink-0"
          style={{ background: done ? '#22C55E' : active ? '#6366F1' : '#2D3148' }}
        />
        <div className="flex-1 w-px mt-1" style={{ background: '#2D3148', minHeight: 24 }} />
      </div>
      <div className="pb-6">
        <p className="text-sm font-medium" style={{ color: done || active ? '#F8FAFC' : '#94A3B8' }}>{label}</p>
        {value && <p className="text-xs mt-0.5 font-mono" style={{ color: '#94A3B8' }}>{value}</p>}
      </div>
    </div>
  )
}

export default function StatusPage({ setCurrentPage }) {
  React.useEffect(() => setCurrentPage('Status'), [])
  const [searchParams] = useSearchParams()
  const [trackingId, setTrackingId] = useState(searchParams.get('id') || '')
  const [input, setInput] = useState(searchParams.get('id') || '')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const intervalRef = useRef(null)

  async function fetchStatus(id) {
    try {
      const result = await getStatus(id)
      setData(result)
      if (!PROCESSING_STATUSES.includes(result.status)) {
        clearInterval(intervalRef.current)
      }
    } catch {
      setError('Tracking ID not found')
      clearInterval(intervalRef.current)
    }
  }

  useEffect(() => {
    if (trackingId) {
      setLoading(true)
      setError('')
      fetchStatus(trackingId).finally(() => setLoading(false))
    }
  }, [trackingId])

  useEffect(() => {
    if (data && PROCESSING_STATUSES.includes(data.status)) {
      intervalRef.current = setInterval(() => fetchStatus(trackingId), 3000)
    }
    return () => clearInterval(intervalRef.current)
  }, [data?.status, trackingId])

  function handleSearch(e) {
    e.preventDefault()
    if (!input.trim()) return
    setData(null)
    setError('')
    setTrackingId(input.trim())
  }

  function copyId() {
    navigator.clipboard.writeText(trackingId)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const steps = data ? [
    { label: 'Submitted', value: data.submitted_at ? new Date(data.submitted_at).toLocaleString() : '—', done: true },
    { label: `AI Decision${data.plain_language_reason ? '' : ''}`, value: data.plain_language_reason || 'Processing...', done: !PROCESSING_STATUSES.includes(data.status), active: data.status === 'PENDING' },
    { label: 'Human Review', value: data.status === 'ESCALATED' ? 'Awaiting approver' : data.status === 'TIMED_OUT' ? 'Timed out' : undefined, done: ['APPROVED', 'REJECTED', 'PAID', 'PAYMENT_FAILED'].includes(data.status), active: data.status === 'ESCALATED' },
    { label: 'Payment', value: data.external_payment_ref ? `Ref: ${data.external_payment_ref}` : undefined, done: data.status === 'PAID', active: data.status === 'APPROVED' },
  ] : []

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Search */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <div className="flex-1 relative">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2" style={{ color: '#94A3B8' }} />
          <input
            className="w-full pl-11 pr-4 py-3.5 rounded-xl text-sm outline-none transition-all duration-200 focus:ring-2"
            style={{ background: '#1A1D27', border: '1px solid #2D3148', color: '#F8FAFC' }}
            placeholder="Enter tracking ID or paste it here..."
            value={input}
            onChange={e => setInput(e.target.value)}
          />
        </div>
        <button
          type="submit"
          className="px-6 py-3.5 rounded-xl text-sm font-medium text-white transition-all duration-200"
          style={{ background: 'linear-gradient(135deg, #6366F1, #8B5CF6)' }}
        >
          Track
        </button>
      </form>

      {loading && (
        <div className="text-center py-12">
          <RefreshCw size={24} className="animate-spin mx-auto mb-3" style={{ color: '#6366F1' }} />
          <p className="text-sm" style={{ color: '#94A3B8' }}>Looking up tracking ID...</p>
        </div>
      )}

      {error && (
        <div className="px-4 py-3 rounded-xl text-sm" style={{ background: '#EF444420', color: '#EF4444', border: '1px solid #EF444440' }}>
          {error}
        </div>
      )}

      {data && (
        <div className="rounded-xl overflow-hidden" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          {/* Header */}
          <div className="px-6 py-5 border-b flex items-start justify-between" style={{ borderColor: '#2D3148' }}>
            <div>
              <div className="flex items-center gap-3 mb-1">
                <span className="font-mono text-sm" style={{ color: '#94A3B8' }}>{data.tracking_id}</span>
                <button onClick={copyId} className="p-1 rounded hover:bg-white/10">
                  {copied ? <Check size={14} style={{ color: '#22C55E' }} /> : <Copy size={14} style={{ color: '#94A3B8' }} />}
                </button>
              </div>
              <p className="text-lg font-semibold" style={{ color: '#F8FAFC' }}>{data.vendor}</p>
              <p className="text-sm mt-0.5" style={{ color: '#94A3B8' }}>{data.category} · {data.submitted_by}</p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold font-mono" style={{ color: '#F8FAFC' }}>${parseFloat(data.amount_usd).toFixed(2)}</p>
              <div className="mt-2">
                <StatusBadge status={data.status} large />
              </div>
            </div>
          </div>

          {/* Timeline */}
          <div className="px-6 py-5">
            <h4 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: '#94A3B8' }}>Timeline</h4>
            <div>
              {steps.filter(s => s.done || s.active || s.value).map((step, i) => (
                <TimelineStep key={i} {...step} />
              ))}
            </div>
          </div>

          {PROCESSING_STATUSES.includes(data.status) && (
            <div className="px-6 pb-4 flex items-center gap-2 text-xs" style={{ color: '#6366F1' }}>
              <RefreshCw size={12} className="animate-spin" />
              Auto-refreshing every 3 seconds...
            </div>
          )}
        </div>
      )}
    </div>
  )
}
