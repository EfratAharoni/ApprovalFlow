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

export async function postDecision(submissionId, action, notes) {
  const res = await fetch(`${BASE}/approvals/${submissionId}/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, notes }),
  })
  if (!res.ok) throw new Error('Decision failed')
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
