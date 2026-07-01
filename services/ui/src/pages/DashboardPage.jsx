import React, { useState, useEffect } from 'react'
import { RefreshCw, Shield, TrendingUp, Users, XCircle, CheckCircle, AlertTriangle } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { getDashboard, proveCeiling } from '../api'

function KPICard({ label, value, sub, color, icon: Icon }) {
  return (
    <div className="rounded-xl p-5 space-y-3" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: '#94A3B8' }}>{label}</span>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${color}20` }}>
          <Icon size={16} style={{ color }} />
        </div>
      </div>
      <div>
        <p className="text-3xl font-bold font-mono" style={{ color: '#F8FAFC' }}>{value}</p>
        {sub && <p className="text-sm mt-1" style={{ color: '#94A3B8' }}>{sub}</p>}
      </div>
    </div>
  )
}

export default function DashboardPage({ setCurrentPage }) {
  React.useEffect(() => setCurrentPage('Dashboard'), [])
  const [dash, setDash] = useState(null)
  const [ceiling, setCeiling] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  async function fetchData(showSpinner = false) {
    if (showSpinner) setRefreshing(true)
    try {
      const [d, c] = await Promise.all([getDashboard(), proveCeiling()])
      setDash(d); setCeiling(c)
    } catch {}
    finally { setLoading(false); setRefreshing(false) }
  }

  useEffect(() => {
    fetchData()
    const id = setInterval(() => fetchData(), 10000)
    return () => clearInterval(id)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw size={24} className="animate-spin" style={{ color: '#6366F1' }} />
      </div>
    )
  }

  if (!dash) {
    return <div className="text-center py-16 text-sm" style={{ color: '#94A3B8' }}>Failed to load dashboard</div>
  }

  const total = dash.total_submissions || 0
  const pct = n => total > 0 ? `${Math.round((n / total) * 100)}%` : '0%'

  const donutData = [
    { name: 'Auto-Approved', value: dash.auto_approved || 0, color: '#22C55E' },
    { name: 'Human Reviewed', value: dash.human_reviewed || 0, color: '#F59E0B' },
    { name: 'Rejected', value: dash.rejected || 0, color: '#EF4444' },
    { name: 'Duplicate', value: dash.duplicates || 0, color: '#94A3B8' },
  ].filter(d => d.value > 0)

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header with refresh */}
      <div className="flex items-center justify-end">
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:bg-white/5 disabled:opacity-50"
          style={{ border: '1px solid #2D3148', color: '#94A3B8' }}
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4">
        <KPICard label="Total Submissions" value={total} icon={TrendingUp} color="#6366F1" />
        <KPICard label="Auto Approved" value={dash.auto_approved || 0} sub={pct(dash.auto_approved)} icon={CheckCircle} color="#22C55E" />
        <KPICard label="Human Reviewed" value={dash.human_reviewed || 0} sub={pct(dash.human_reviewed)} icon={Users} color="#F59E0B" />
        <KPICard label="Rejected" value={dash.rejected || 0} sub={pct(dash.rejected)} icon={XCircle} color="#EF4444" />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Donut */}
        <div className="rounded-xl p-5" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: '#F8FAFC' }}>Decision Distribution</h3>
          {donutData.length > 0 ? (
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={160} height={160}>
                <PieChart>
                  <Pie data={donutData} cx="50%" cy="50%" innerRadius={45} outerRadius={70} dataKey="value" strokeWidth={0}>
                    {donutData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2">
                {donutData.map((d, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <div className="w-3 h-3 rounded-full" style={{ background: d.color }} />
                    <span style={{ color: '#94A3B8' }}>{d.name}</span>
                    <span className="ml-auto font-mono font-medium" style={{ color: '#F8FAFC' }}>{d.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-40 text-sm" style={{ color: '#94A3B8' }}>No data yet</div>
          )}
        </div>

        {/* Processing time */}
        <div className="rounded-xl p-5" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: '#F8FAFC' }}>Processing Stats</h3>
          <div className="space-y-4">
            <div>
              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: '#94A3B8' }}>Avg. end-to-end time</p>
              <p className="text-2xl font-bold font-mono" style={{ color: '#F8FAFC' }}>
                {dash.avg_processing_time_seconds > 0
                  ? `${dash.avg_processing_time_seconds.toFixed(1)}s`
                  : '—'}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: '#94A3B8' }}>Total auto-approved ($)</p>
              <p className="text-2xl font-bold font-mono" style={{ color: '#22C55E' }}>
                ${(dash.total_amount_auto_approved || 0).toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider mb-1" style={{ color: '#94A3B8' }}>Total human-approved ($)</p>
              <p className="text-2xl font-bold font-mono" style={{ color: '#F59E0B' }}>
                ${(dash.total_amount_human_approved || 0).toFixed(2)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Ceiling proof */}
      {ceiling && (
        <div
          className="rounded-xl p-5 flex items-start gap-4"
          style={{
            background: ceiling.violation_found ? '#EF444415' : '#22C55E15',
            border: `1px solid ${ceiling.violation_found ? '#EF444440' : '#22C55E40'}`,
          }}
        >
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: ceiling.violation_found ? '#EF444420' : '#22C55E20' }}
          >
            {ceiling.violation_found
              ? <AlertTriangle size={20} style={{ color: '#EF4444' }} />
              : <Shield size={20} style={{ color: '#22C55E' }} />
            }
          </div>
          <div>
            <p className="font-semibold" style={{ color: '#F8FAFC' }}>
              {ceiling.violation_found ? 'Ceiling Violation Detected!' : 'No ceiling violations detected'}
            </p>
            <p className="text-sm mt-1" style={{ color: '#94A3B8' }}>
              Ceiling: <span className="font-mono" style={{ color: '#F8FAFC' }}>${ceiling.ceiling}</span>
              {' · '}
              Max auto-approved: <span className="font-mono" style={{ color: '#F8FAFC' }}>${ceiling.max_auto_approved_amount ?? 0}</span>
              {' · '}
              Records checked: <span className="font-mono" style={{ color: '#F8FAFC' }}>{ceiling.records?.length ?? 0}</span>
            </p>
          </div>
        </div>
      )}

      {/* Auto-approval rate */}
      {dash.auto_approval_rate !== undefined && (
        <div className="rounded-xl p-5" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold" style={{ color: '#F8FAFC' }}>Auto-Approval Rate</h3>
            <span className="text-2xl font-bold font-mono" style={{ color: '#22C55E' }}>
              {Math.round((dash.auto_approval_rate || 0) * 100)}%
            </span>
          </div>
          <div className="h-3 rounded-full" style={{ background: '#2D3148' }}>
            <div
              className="h-3 rounded-full transition-all duration-1000"
              style={{ width: `${Math.round((dash.auto_approval_rate || 0) * 100)}%`, background: 'linear-gradient(90deg, #6366F1, #22C55E)' }}
            />
          </div>
          <p className="text-xs mt-2" style={{ color: '#94A3B8' }}>
            Total amount auto-approved: <span className="font-mono" style={{ color: '#F8FAFC' }}>${(dash.total_amount_auto_approved || 0).toFixed(2)}</span>
          </p>
        </div>
      )}
    </div>
  )
}
