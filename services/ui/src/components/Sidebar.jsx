import React from 'react'
import { NavLink } from 'react-router-dom'
import { Send, Search, CheckSquare, BarChart2, Zap } from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/submit', label: 'Submit', icon: Send },
  { to: '/status', label: 'Status', icon: Search },
  { to: '/approvals', label: 'Approvals', icon: CheckSquare },
  { to: '/dashboard', label: 'Dashboard', icon: BarChart2 },
]

export default function Sidebar({ queueCount, setCurrentPage }) {
  return (
    <div
      className="flex flex-col border-r"
      style={{ width: 240, background: '#1A1D27', borderColor: '#2D3148' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b" style={{ borderColor: '#2D3148' }}>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: '#6366F1' }}>
          <Zap size={16} className="text-white" />
        </div>
        <span className="text-lg font-semibold" style={{ color: '#F8FAFC' }}>ApprovalFlow</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setCurrentPage(label)}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'text-white'
                  : 'hover:bg-white/5'
              )
            }
            style={({ isActive }) => isActive ? { background: '#6366F1', color: '#fff' } : { color: '#94A3B8' }}
          >
            <Icon size={18} />
            <span>{label}</span>
            {label === 'Approvals' && queueCount > 0 && (
              <span
                className="ml-auto text-xs font-bold px-2 py-0.5 rounded-full"
                style={{ background: '#F59E0B', color: '#000' }}
              >
                {queueCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t text-xs" style={{ borderColor: '#2D3148', color: '#94A3B8' }}>
        v1.0.0 · ApprovalFlow
      </div>
    </div>
  )
}
