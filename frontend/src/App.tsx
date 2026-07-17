import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import ProjectDetail from './pages/ProjectDetail'
import Settings from './pages/Settings'

const nav = [
  { to: '/projects', label: 'Projects' },
  { to: '/settings', label: 'Settings' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-surface-900 text-surface-100">
        <nav className="w-48 bg-surface-800 border-r border-surface-700 p-4 space-y-1 shrink-0">
          <h1 className="text-lg font-bold mb-4 text-teal-400">Deploy Flow</h1>
          {nav.map(n => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) =>
              `block px-3 py-2 rounded text-sm ${isActive ? 'bg-teal-700 text-white' : 'text-surface-300 hover:bg-surface-700'}`
            }>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <main className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/projects" />} />
            <Route path="/projects" element={<Dashboard />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
