import React from 'react'
import { Check, Clock, X, MinusCircle, Loader, AlertCircle } from 'lucide-react'

const CONFIG = {
  PAID:           { label: 'Paid',           bg: '#22C55E20', color: '#22C55E', border: '#22C55E40', Icon: Check },
  APPROVED:       { label: 'Approved',       bg: '#22C55E20', color: '#22C55E', border: '#22C55E40', Icon: Check },
  ESCALATED:      { label: 'Escalated',      bg: '#F59E0B20', color: '#F59E0B', border: '#F59E0B40', Icon: Clock },
  PENDING_INFO:   { label: 'Pending Info',   bg: '#F59E0B20', color: '#F59E0B', border: '#F59E0B40', Icon: Clock },
  TIMED_OUT:      { label: 'Timed Out',      bg: '#EF444420', color: '#EF4444', border: '#EF444440', Icon: AlertCircle },
  REJECTED:       { label: 'Rejected',       bg: '#EF444420', color: '#EF4444', border: '#EF444440', Icon: X },
  PAYMENT_FAILED: { label: 'Payment Failed', bg: '#EF444420', color: '#EF4444', border: '#EF444440', Icon: X },
  DUPLICATE:      { label: 'Duplicate',      bg: '#94A3B820', color: '#94A3B8', border: '#94A3B840', Icon: MinusCircle },
  PENDING:        { label: 'Processing',     bg: '#6366F120', color: '#6366F1', border: '#6366F140', Icon: Loader },
}

export default function StatusBadge({ status, large = false }) {
  const cfg = CONFIG[status] || CONFIG.PENDING
  const { label, bg, color, border, Icon } = cfg
  const isSpinning = status === 'PENDING'

  return (
    <span
      className={`inline-flex items-center gap-2 font-medium rounded-full ${large ? 'px-5 py-2 text-base' : 'px-3 py-1 text-xs'}`}
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      <Icon size={large ? 18 : 12} className={isSpinning ? 'animate-spin' : ''} />
      {label}
    </span>
  )
}
