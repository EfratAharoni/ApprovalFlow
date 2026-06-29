import React, { useState } from 'react'
import { PlusCircle, Trash2, Copy, CheckCircle, Loader } from 'lucide-react'
import { postSubmission } from '../api'

const CATEGORIES = [
  { value: 'meals', label: 'Meals', emoji: '🍽️' },
  { value: 'travel', label: 'Travel', emoji: '✈️' },
  { value: 'saas', label: 'SaaS', emoji: '💻' },
  { value: 'hardware', label: 'Hardware', emoji: '🖥️' },
  { value: 'other', label: 'Other', emoji: '📦' },
]
const CURRENCIES = [
  { value: 'USD', flag: '🇺🇸' },
  { value: 'EUR', flag: '🇪🇺' },
  { value: 'GBP', flag: '🇬🇧' },
]
const DEPARTMENTS = ['Engineering', 'Sales', 'Marketing', 'Finance', 'HR', 'Operations']

function Toggle({ checked, onChange, label }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="flex items-center gap-3 cursor-pointer"
    >
      <div
        className="relative w-11 h-6 rounded-full transition-all duration-200"
        style={{ background: checked ? '#6366F1' : '#2D3148' }}
      >
        <div
          className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-200"
          style={{ left: checked ? '26px' : '4px' }}
        />
      </div>
      <span className="text-sm" style={{ color: '#94A3B8' }}>{label}</span>
    </button>
  )
}

export default function SubmitPage({ setCurrentPage }) {
  React.useEffect(() => setCurrentPage('Submit'), [])

  const [form, setForm] = useState({
    vendor: '',
    vendorKnown: true,
    invoiceNumber: '',
    date: new Date().toISOString().split('T')[0],
    currency: 'USD',
    category: 'meals',
    department: 'Engineering',
    submittedBy: '',
    receiptPresent: false,
    attendees: '',
    notes: '',
    taxAmount: '0',
  })
  const [lineItems, setLineItems] = useState([{ description: '', quantity: 1, unitPrice: '' }])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const subtotal = lineItems.reduce((s, i) => s + (parseFloat(i.unitPrice) || 0) * (parseFloat(i.quantity) || 0), 0)
  const taxAmt = subtotal * (parseFloat(form.taxAmount) / 100 || 0)
  const total = subtotal + taxAmt
  const perPerson = form.category === 'meals' && form.attendees > 0 ? total / parseFloat(form.attendees) : null

  function setField(k, v) { setForm(f => ({ ...f, [k]: v })) }
  function updateItem(i, k, v) { setLineItems(items => items.map((item, idx) => idx === i ? { ...item, [k]: v } : item)) }
  function addItem() { setLineItems(items => [...items, { description: '', quantity: 1, unitPrice: '' }]) }
  function removeItem(i) { setLineItems(items => items.filter((_, idx) => idx !== i)) }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const payload = {
        vendor: form.vendor,
        vendorKnown: form.vendorKnown,
        invoiceNumber: form.invoiceNumber,
        date: form.date,
        currency: form.currency,
        category: form.category,
        department: form.department,
        submitter: form.submittedBy,
        receiptPresent: form.receiptPresent,
        attendees: form.category === 'meals' && form.attendees ? parseInt(form.attendees) : undefined,
        notes: form.notes || undefined,
        taxAmount: taxAmt.toFixed(2),
        total: total.toFixed(2),
        lineItems: lineItems.map(i => ({
          description: i.description,
          quantity: parseFloat(i.quantity),
          unitPrice: parseFloat(i.unitPrice),
        })),
      }
      const data = await postSubmission(payload)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function copyId() {
    navigator.clipboard.writeText(result.tracking_id)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const inputCls = 'w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-all duration-200 focus:ring-2'
  const inputStyle = { background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }
  const labelCls = 'block text-xs font-medium mb-1.5'
  const labelStyle = { color: '#94A3B8' }

  if (result) {
    return (
      <div className="max-w-lg mx-auto mt-12">
        <div className="rounded-xl p-8 text-center space-y-5" style={{ background: '#1A1D27', border: '1px solid #22C55E40' }}>
          <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto" style={{ background: '#22C55E20' }}>
            <CheckCircle size={32} style={{ color: '#22C55E' }} />
          </div>
          <div>
            <h2 className="text-xl font-semibold mb-1" style={{ color: '#F8FAFC' }}>Submission Accepted</h2>
            <p className="text-sm" style={{ color: '#94A3B8' }}>Processing asynchronously — use the tracking ID below to check status.</p>
          </div>
          <div className="flex items-center gap-2 px-4 py-3 rounded-lg" style={{ background: '#0F1117', border: '1px solid #2D3148' }}>
            <span className="flex-1 font-mono text-sm" style={{ color: '#6366F1' }}>{result.tracking_id}</span>
            <button onClick={copyId} className="p-1.5 rounded hover:bg-white/10 transition-colors">
              {copied ? <CheckCircle size={16} style={{ color: '#22C55E' }} /> : <Copy size={16} style={{ color: '#94A3B8' }} />}
            </button>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setResult(null)}
              className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 hover:bg-white/10"
              style={{ border: '1px solid #2D3148', color: '#94A3B8' }}
            >
              Submit Another
            </button>
            <a
              href={`/status?id=${result.tracking_id}`}
              className="flex-1 py-2.5 rounded-lg text-sm font-medium text-center transition-all duration-200"
              style={{ background: '#6366F1', color: '#fff' }}
            >
              Track Status →
            </a>
          </div>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-5xl mx-auto space-y-6">
      <div className="grid grid-cols-2 gap-6">
        {/* Left column */}
        <div className="rounded-xl p-6 space-y-4" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          <h3 className="text-sm font-semibold mb-2" style={{ color: '#F8FAFC' }}>Invoice Details</h3>

          <div>
            <label className={labelCls} style={labelStyle}>Vendor Name</label>
            <input className={inputCls} style={inputStyle} value={form.vendor} onChange={e => setField('vendor', e.target.value)} placeholder="e.g. Bistro 19" required />
            <div className="mt-2">
              <Toggle checked={form.vendorKnown} onChange={v => setField('vendorKnown', v)} label="Known Vendor" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls} style={labelStyle}>Invoice Number</label>
              <input className={inputCls} style={inputStyle} value={form.invoiceNumber} onChange={e => setField('invoiceNumber', e.target.value)} placeholder="INV-1001" required />
            </div>
            <div>
              <label className={labelCls} style={labelStyle}>Date</label>
              <input type="date" className={inputCls} style={inputStyle} value={form.date} onChange={e => setField('date', e.target.value)} required />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls} style={labelStyle}>Currency</label>
              <select className={inputCls} style={inputStyle} value={form.currency} onChange={e => setField('currency', e.target.value)}>
                {CURRENCIES.map(c => <option key={c.value} value={c.value}>{c.flag} {c.value}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls} style={labelStyle}>Category</label>
              <select className={inputCls} style={inputStyle} value={form.category} onChange={e => setField('category', e.target.value)}>
                {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.emoji} {c.label}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className={labelCls} style={labelStyle}>Department</label>
            <select className={inputCls} style={inputStyle} value={form.department} onChange={e => setField('department', e.target.value)}>
              {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>

          <div>
            <label className={labelCls} style={labelStyle}>Submitter Email</label>
            <input type="email" className={inputCls} style={inputStyle} value={form.submittedBy} onChange={e => setField('submittedBy', e.target.value)} placeholder="you@company.com" required />
          </div>

          <div className="flex items-center justify-between">
            <Toggle checked={form.receiptPresent} onChange={v => setField('receiptPresent', v)} label="Receipt Present" />
          </div>

          {form.category === 'meals' && (
            <div>
              <label className={labelCls} style={labelStyle}>👥 Attendees</label>
              <input type="number" min="1" className={inputCls} style={inputStyle} value={form.attendees} onChange={e => setField('attendees', e.target.value)} placeholder="Number of attendees" />
              {perPerson !== null && (
                <p className="mt-1 text-xs" style={{ color: '#94A3B8' }}>
                  Per person: <span className="font-mono font-medium" style={{ color: '#6366F1' }}>${perPerson.toFixed(2)}</span>
                  {perPerson > 75 && <span className="ml-2" style={{ color: '#F59E0B' }}>⚠️ Exceeds $75/person limit</span>}
                </p>
              )}
            </div>
          )}

          <div>
            <label className={labelCls} style={labelStyle}>Notes (optional)</label>
            <textarea className={`${inputCls} resize-none`} style={inputStyle} rows={2} value={form.notes} onChange={e => setField('notes', e.target.value)} placeholder="Any additional context..." />
          </div>
        </div>

        {/* Right column */}
        <div className="rounded-xl p-6 space-y-4" style={{ background: '#1A1D27', border: '1px solid #2D3148' }}>
          <h3 className="text-sm font-semibold mb-2" style={{ color: '#F8FAFC' }}>Line Items</h3>

          <div className="space-y-2">
            <div className="grid grid-cols-12 gap-2 text-xs font-medium px-1" style={{ color: '#94A3B8' }}>
              <span className="col-span-5">Description</span>
              <span className="col-span-2">Qty</span>
              <span className="col-span-3">Unit Price</span>
              <span className="col-span-2 text-right">Total</span>
            </div>
            {lineItems.map((item, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-center">
                <input
                  className="col-span-5 px-2 py-2 rounded-lg text-xs outline-none"
                  style={{ background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }}
                  value={item.description}
                  onChange={e => updateItem(i, 'description', e.target.value)}
                  placeholder="Item description"
                  required
                />
                <input
                  type="number" min="1"
                  className="col-span-2 px-2 py-2 rounded-lg text-xs outline-none"
                  style={{ background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }}
                  value={item.quantity}
                  onChange={e => updateItem(i, 'quantity', e.target.value)}
                />
                <input
                  type="number" min="0" step="0.01"
                  className="col-span-3 px-2 py-2 rounded-lg text-xs outline-none"
                  style={{ background: '#0F1117', border: '1px solid #2D3148', color: '#F8FAFC' }}
                  value={item.unitPrice}
                  onChange={e => updateItem(i, 'unitPrice', e.target.value)}
                  placeholder="0.00"
                  required
                />
                <div className="col-span-2 flex items-center justify-end gap-1">
                  <span className="text-xs font-mono" style={{ color: '#F8FAFC' }}>
                    ${((parseFloat(item.unitPrice) || 0) * (parseFloat(item.quantity) || 0)).toFixed(2)}
                  </span>
                  {lineItems.length > 1 && (
                    <button type="button" onClick={() => removeItem(i)} className="p-1 rounded hover:bg-white/10">
                      <Trash2 size={12} style={{ color: '#EF4444' }} />
                    </button>
                  )}
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={addItem}
              className="flex items-center gap-2 text-xs font-medium mt-2 px-3 py-1.5 rounded-lg transition-all duration-200 hover:bg-white/5"
              style={{ color: '#6366F1' }}
            >
              <PlusCircle size={14} />
              Add Line Item
            </button>
          </div>

          {/* Totals */}
          <div className="rounded-lg p-4 space-y-2 mt-4" style={{ background: '#0F1117', border: '1px solid #2D3148' }}>
            <div className="flex justify-between text-sm" style={{ color: '#94A3B8' }}>
              <span>Subtotal</span>
              <span className="font-mono">${subtotal.toFixed(2)}</span>
            </div>
            <div className="flex justify-between items-center text-sm" style={{ color: '#94A3B8' }}>
              <div className="flex items-center gap-2">
                <span>Tax</span>
                <input
                  type="number" min="0" max="100" step="0.5"
                  className="w-14 px-2 py-0.5 rounded text-xs outline-none"
                  style={{ background: '#1A1D27', border: '1px solid #2D3148', color: '#F8FAFC' }}
                  value={form.taxAmount}
                  onChange={e => setField('taxAmount', e.target.value)}
                />
                <span className="text-xs">%</span>
              </div>
              <span className="font-mono">${taxAmt.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-base font-semibold pt-2 border-t" style={{ borderColor: '#2D3148', color: '#F8FAFC' }}>
              <span>Total</span>
              <span className="font-mono">${total.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 rounded-lg text-sm" style={{ background: '#EF444420', color: '#EF4444', border: '1px solid #EF444440' }}>
          {error}
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={loading || total <= 0}
          className="flex items-center gap-2 px-8 py-3 rounded-lg font-semibold text-sm text-white transition-all duration-200 disabled:opacity-50"
          style={{ background: loading ? '#6366F1' : 'linear-gradient(135deg, #6366F1, #8B5CF6)' }}
        >
          {loading && <Loader size={16} className="animate-spin" />}
          {loading ? 'Submitting...' : 'Submit Invoice'}
        </button>
      </div>
    </form>
  )
}
