import React, { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Check, X, HelpCircle, LogIn, LogOut } from 'lucide-react'
import { Dialog, Transition } from '@headlessui/react'
import { getQueue, postDecision, getToken } from '../api'
import ConfidenceBar from '../components/ConfidenceBar'

const TOKEN_KEY = 'approvalflow_token'
const ROLE_KEY  = 'approvalflow_role'
const USER_KEY  = 'approvalflow_user'

function LoginForm({ onLogin }) {
  const [username, setUsername] = useState('lena')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await getToken(username, password, 'approver')
      onLogin(data.access_token, username)
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="rounded-2xl p-8 space-y-6" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
        <div className="text-center">
          <LogIn size={32} className="mx-auto mb-3" style={{ color: '#6366F1' }} />
          <h2 className="text-lg font-semibold" style={{ color: '#F8FAFC' }}>Approver Login</h2>
          <p className="text-xs mt-1" style={{ color: '#94A3B8' }}>JWT required to access approval queue</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#94A3B8' }}>Username</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
              style={{ background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1.5" style={{ color: '#94A3B8' }}>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
              style={{ background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }}
              required
            />
          </div>
          {error && (
            <p className="text-xs px-3 py-2 rounded-lg" style={{ background: '#EF444420', color: '#EF4444' }}>
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all duration-200 disabled:opacity-50"
            style={{ background: '#6366F1' }}
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p className="text-xs text-center" style={{ color: '#94A3B8' }}>
          Hint: <span className="font-mono" style={{ color: '#6366F1' }}>lena / pass123</span>
        </p>
      </div>
    </div>
  )
}

const CATEGORY_COLORS = {
  meals: { bg: '#F59E0B20', color: '#F59E0B' },
  travel: { bg: '#6366F120', color: '#6366F1' },
  saas: { bg: '#22C55E20', color: '#22C55E' },
  hardware: { bg: '#EF444420', color: '#EF4444' },
  other: { bg: '#94A3B820', color: '#94A3B8' },
}
const CATEGORY_EMOJI = { meals: '🍽️', travel: '✈️', saas: '💻', hardware: '🖥️', other: '📦' }

function DecisionModal({ item, action, onClose, onConfirm }) {
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const requiresNotes = action === 'REJECT' || action === 'REQUEST_INFO'
  const colors = { APPROVE: '#22C55E', REJECT: '#EF4444', REQUEST_INFO: '#94A3B8' }
  const labels = { APPROVE: 'Approve', REJECT: 'Reject', REQUEST_INFO: 'Request Info' }

  async function confirm() {
    setLoading(true)
    try {
      await onConfirm(item.submission_id, action, notes)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <Transition show as={React.Fragment}>
      <Dialog onClose={onClose} className="relative z-50">
        <Transition.Child
          enter="ease-out duration-200" enterFrom="opacity-0" enterTo="opacity-100"
          leave="ease-in duration-150" leaveFrom="opacity-100" leaveTo="opacity-0"
        >
          <div className="fixed inset-0" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }} />
        </Transition.Child>
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <Transition.Child
            enter="ease-out duration-200" enterFrom="opacity-0 scale-95" enterTo="opacity-100 scale-100"
            leave="ease-in duration-150" leaveFrom="opacity-100 scale-100" leaveTo="opacity-0 scale-95"
          >
            <Dialog.Panel className="w-full max-w-md rounded-2xl p-6 space-y-4" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
              <Dialog.Title className="text-lg font-semibold" style={{ color: '#F8FAFC' }}>
                {labels[action]} — {item.vendor_name}
              </Dialog.Title>
              <div className="rounded-lg p-4 space-y-1" style={{ background: '#0F1117' }}>
                <div className="flex justify-between text-sm">
                  <span style={{ color: '#94A3B8' }}>Amount</span>
                  <span className="font-mono font-semibold" style={{ color: '#F8FAFC' }}>${parseFloat(item.amount_usd || 0).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span style={{ color: '#94A3B8' }}>Category</span>
                  <span style={{ color: '#F8FAFC' }}>{item.category}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span style={{ color: '#94A3B8' }}>Department</span>
                  <span style={{ color: '#F8FAFC' }}>{item.department || '—'}</span>
                </div>
              </div>
              {(requiresNotes || true) && (
                <div>
                  <label className="block text-xs font-medium mb-1.5" style={{ color: '#94A3B8' }}>
                    Notes {requiresNotes ? '(required)' : '(optional)'}
                  </label>
                  <textarea
                    className="w-full px-3 py-2.5 rounded-lg text-sm outline-none resize-none"
                    style={{ background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }}
                    rows={3}
                    value={notes}
                    onChange={e => setNotes(e.target.value)}
                    placeholder="Add a note..."
                    required={requiresNotes}
                  />
                </div>
              )}
              <div className="flex gap-3 pt-2">
                <button onClick={onClose} className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 hover:bg-white/5" style={{ border: '1px solid #2D3148', color: '#94A3B8' }}>
                  Cancel
                </button>
                <button
                  onClick={confirm}
                  disabled={loading || (requiresNotes && !notes.trim())}
                  className="flex-1 py-2.5 rounded-lg text-sm font-semibold text-white transition-all duration-200 disabled:opacity-50"
                  style={{ background: colors[action] }}
                >
                  {loading ? 'Processing...' : `Confirm ${labels[action]}`}
                </button>
              </div>
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  )
}

export default function ApprovalsPage({ setCurrentPage }) {
  React.useEffect(() => setCurrentPage('Approvals'), [])
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [loggedInUser, setLoggedInUser] = useState(() => localStorage.getItem(USER_KEY) || '')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [modal, setModal] = useState(null)
  const [dismissed, setDismissed] = useState(new Set())

  function handleLogin(accessToken, username) {
    localStorage.setItem(TOKEN_KEY, accessToken)
    localStorage.setItem(USER_KEY, username)
    localStorage.setItem(ROLE_KEY, 'approver')
    setToken(accessToken)
    setLoggedInUser(username)
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(ROLE_KEY)
    setToken('')
    setLoggedInUser('')
    setItems([])
  }

  const load = useCallback(async () => {
    try {
      const data = await getQueue()
      const list = Array.isArray(data) ? data : (data.items || [])
      setItems(list)
      setLastUpdated(new Date())
    } catch {}
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    if (!token) return
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [load, token])

  async function handleDecision(submissionId, action, notes) {
    await postDecision(submissionId, action, notes, 'ui-approver', token)
    setDismissed(d => new Set([...d, submissionId]))
    setTimeout(() => setItems(prev => prev.filter(i => i.submission_id !== submissionId)), 500)
  }

  if (!token) {
    return <LoginForm onLogin={handleLogin} />
  }

  const visible = items.filter(i => !dismissed.has(i.submission_id))
  const recColor = { approve: '#22C55E', escalate: '#F59E0B', reject: '#EF4444' }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold" style={{ color: '#F8FAFC' }}>
          {visible.length} item{visible.length !== 1 ? 's' : ''} awaiting review
        </h2>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs" style={{ color: '#94A3B8' }}>
            <RefreshCw size={12} />
            {lastUpdated ? `Last updated: ${lastUpdated.toLocaleTimeString()}` : 'Loading...'}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium px-2 py-1 rounded-full" style={{ background: '#22C55E20', color: '#22C55E' }}>
              {loggedInUser}
            </span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:opacity-80"
              style={{ background: '#EF444420', color: '#EF4444', border: '1px solid #EF444440' }}
            >
              <LogOut size={12} /> Logout
            </button>
          </div>
        </div>
      </div>

      {loading && (
        <div className="text-center py-16">
          <RefreshCw size={24} className="animate-spin mx-auto mb-3" style={{ color: '#6366F1' }} />
          <p className="text-sm" style={{ color: '#94A3B8' }}>Loading queue...</p>
        </div>
      )}

      {!loading && visible.length === 0 && (
        <div className="text-center py-16 rounded-xl" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          <Check size={32} className="mx-auto mb-3" style={{ color: '#22C55E' }} />
          <p className="font-semibold" style={{ color: '#F8FAFC' }}>All caught up!</p>
          <p className="text-sm mt-1" style={{ color: '#94A3B8' }}>No items awaiting review.</p>
        </div>
      )}

      {visible.map(item => {
        const catStyle = CATEGORY_COLORS[item.category] || CATEGORY_COLORS.other
        const rec = (item.agent_recommendation?.recommendation || '').toLowerCase()
        const isDismissed = dismissed.has(item.submission_id)
        return (
          <div
            key={item.submission_id}
            className="rounded-xl p-5 space-y-4 transition-all duration-500"
            style={{
              background: '#1A1D27',
              border: '1px solid #2D3148',
              opacity: isDismissed ? 0 : 1,
              transform: isDismissed ? 'translateY(-8px)' : 'translateY(0)',
            }}
          >
            {/* Top row */}
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg font-semibold" style={{ color: '#F8FAFC' }}>{item.vendor_name}</span>
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium" style={{ background: catStyle.bg, color: catStyle.color }}>
                    {CATEGORY_EMOJI[item.category]} {item.category}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: '#2D3148', color: '#94A3B8' }}>{item.department || 'Unknown Dept'}</span>
                  <span className="text-xs font-mono" style={{ color: '#94A3B8' }}>#{item.submission_id?.slice(0, 8)}</span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold font-mono" style={{ color: '#F8FAFC' }}>${parseFloat(item.amount_usd || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}</p>
              </div>
            </div>

            {/* AI recommendation */}
            {item.agent_recommendation && (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-medium px-2 py-1 rounded-full" style={{ background: `${recColor[rec]}20`, color: recColor[rec] }}>
                    AI: {rec.toUpperCase()}
                  </span>
                  <div className="flex-1">
                    <ConfidenceBar value={item.agent_recommendation.confidence} />
                  </div>
                </div>
                {item.agent_recommendation.policy_violations?.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {item.agent_recommendation.policy_violations.map((v, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 rounded-full font-mono" style={{ background: '#EF444420', color: '#EF4444' }}>
                        {v.rule_id}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {item.plain_language_reason && (
              <p className="text-xs" style={{ color: '#94A3B8' }}>{item.plain_language_reason}</p>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => setModal({ item, action: 'APPROVE' })}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:opacity-80"
                style={{ background: '#22C55E20', color: '#22C55E', border: '1px solid #22C55E40' }}
              >
                <Check size={14} /> Approve
              </button>
              <button
                onClick={() => setModal({ item, action: 'REJECT' })}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:opacity-80"
                style={{ background: '#EF444420', color: '#EF4444', border: '1px solid #EF444440' }}
              >
                <X size={14} /> Reject
              </button>
              <button
                onClick={() => setModal({ item, action: 'REQUEST_INFO' })}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 hover:opacity-80"
                style={{ background: '#94A3B820', color: '#94A3B8', border: '1px solid #94A3B840' }}
              >
                <HelpCircle size={14} /> Request Info
              </button>
            </div>
          </div>
        )
      })}

      {modal && (
        <DecisionModal
          item={modal.item}
          action={modal.action}
          onClose={() => setModal(null)}
          onConfirm={handleDecision}
        />
      )}
    </div>
  )
}
