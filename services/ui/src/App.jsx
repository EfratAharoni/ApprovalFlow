import React, { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Header from './components/Header'
import SubmitPage from './pages/SubmitPage'
import StatusPage from './pages/StatusPage'
import ApprovalsPage from './pages/ApprovalsPage'
import DashboardPage from './pages/DashboardPage'
import { getQueue } from './api'

export default function App() {
  const [queueCount, setQueueCount] = useState(0)
  const [currentPage, setCurrentPage] = useState('Submit')

  useEffect(() => {
    const fetchCount = () =>
      getQueue().then(q => setQueueCount(Array.isArray(q) ? q.length : (q.items?.length ?? 0))).catch(() => {})
    fetchCount()
    const id = setInterval(fetchCount, 5000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#0F1117' }}>
      <Sidebar queueCount={queueCount} setCurrentPage={setCurrentPage} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header currentPage={currentPage} queueCount={queueCount} />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/submit" replace />} />
            <Route path="/submit" element={<SubmitPage setCurrentPage={setCurrentPage} />} />
            <Route path="/status" element={<StatusPage setCurrentPage={setCurrentPage} />} />
            <Route path="/approvals" element={<ApprovalsPage setCurrentPage={setCurrentPage} />} />
            <Route path="/dashboard" element={<DashboardPage setCurrentPage={setCurrentPage} />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
