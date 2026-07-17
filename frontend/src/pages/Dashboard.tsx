import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { Project } from '../api'

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([])
  const [pathInput, setPathInput] = useState('')

  function load() { api.projects.list().then(setProjects) }
  useEffect(() => { load() }, [])

  async function addProject() {
    if (!pathInput.trim()) return
    await api.projects.create(pathInput.trim())
    setPathInput('')
    load()
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Projects</h2>

      <div className="flex gap-2">
        <input value={pathInput} onChange={e => setPathInput(e.target.value)}
          placeholder="Path to game project..."
          className="flex-1 bg-surface-800 border border-surface-700 rounded px-3 py-1.5 text-sm" />
        <button onClick={addProject} className="bg-teal-700 px-4 py-1.5 rounded text-sm hover:bg-teal-600">
          Add Project
        </button>
      </div>

      <div className="grid gap-3">
        {projects.map(p => (
          <Link key={p.id} to={`/projects/${p.id}`}
            className="bg-surface-800 rounded p-4 flex items-center justify-between hover:bg-gray-750 transition-colors">
            <div>
              <span className="font-semibold text-lg">{p.name}</span>
              <span className="text-surface-400 text-sm ml-3">{p.engine || '?'} | {p.platform || '?'}</span>
              {p.last_build_time && (
                <span className={`ml-3 text-xs ${p.last_build_success ? 'text-green-400' : 'text-red-400'}`}>
                  {p.last_build_success ? 'Last build OK' : 'Last build failed'}
                </span>
              )}
              <div className="text-surface-500 text-xs mt-1">{p.project_path}</div>
            </div>
            <div className="flex gap-2">
              {p.itch_target && <span className="bg-purple-700 px-2 py-0.5 rounded text-xs">Itch</span>}
              {p.steam_app_id && <span className="bg-teal-700 px-2 py-0.5 rounded text-xs">Steam</span>}
            </div>
          </Link>
        ))}
        {projects.length === 0 && (
          <p className="text-surface-400">No projects yet. Add a game project path above.</p>
        )}
      </div>
    </div>
  )
}
