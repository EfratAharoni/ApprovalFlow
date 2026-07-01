const BASE = 'http://localhost:8000'

export async function postSubmission(data) {
  const res = await fetch(`${BASE}/submissions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Submission failed')
  }
  return res.json()
}

export async function getStatus(trackingId) {
  const res = await fetch(`${BASE}/submissions/${trackingId}`)
  if (!res.ok) throw new Error('Not found')
  return res.json()
}

export async function getQueue() {
  const res = await fetch(`${BASE}/approvals/queue`)
  if (!res.ok) throw new Error('Failed to load queue')
  return res.json()
}

export async function postDecision(submissionId, action, notes, decidedBy = 'ui-approver', token = null) {
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE}/approvals/${submissionId}/decide`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ action, notes, decided_by: decidedBy }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ? JSON.stringify(err.detail) : 'Decision failed')
  }
  return res.json()
}

export async function getToken(username, password, role) {
  const res = await fetch(`${BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }))
    throw new Error(err.detail || 'Login failed')
  }
  return res.json()
}

export async function getDashboard() {
  const res = await fetch(`${BASE}/audit/dashboard`)
  if (!res.ok) throw new Error('Failed to load dashboard')
  return res.json()
}

export async function proveCeiling() {
  const res = await fetch(`${BASE}/audit/prove-ceiling`)
  if (!res.ok) throw new Error('Failed')
  return res.json()
}
