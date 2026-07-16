import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { Project } from '../api'

export default function ProjectDetail() {
  const { id: paramId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const id = paramId!
  const [proj, setProj] = useState<Project | null>(null)
  const [detected, setDetected] = useState<{ engine: string; presets: string[]; version: string } | null>(null)
  const [buildLog, setBuildLog] = useState<string[]>([])
  const [itchLog, setItchLog] = useState<string[]>([])
  const [steamLog, setSteamLog] = useState<string[]>([])
  const [buildStatus, setBuildStatus] = useState('idle')
  const [itchStatus, setItchStatus] = useState('idle')
  const [steamStatus, setSteamStatus] = useState('idle')
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.projects.get(id).then(setProj)
    api.projects.detect(id).then(setDetected)
  }, [id])

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight })

  if (!id || !proj) return <p className="text-gray-400">Loading...</p>

  async function handleDetect() {
    const d = await api.projects.detect(id)
    setDetected(d)
  }

  function saveField(key: string, value: string | boolean) {
    const updated = { ...proj, [key]: value } as Project
    setProj(updated)
    api.projects.update(id, { [key]: value } as any)
  }

  function pollBuild() {
    const iv = setInterval(async () => {
      const s = await api.build.status(id)
      setBuildStatus(s.status)
      setBuildLog(s.logs)
      if (s.status !== 'running') clearInterval(iv)
    }, 1000)
    return () => clearInterval(iv)
  }

  function pollItch() {
    const iv = setInterval(async () => {
      const s = await api.upload.itch.status(id)
      setItchStatus(s.status)
      setItchLog(s.logs)
      if (s.status !== 'running') clearInterval(iv)
    }, 1000)
    return () => clearInterval(iv)
  }

  function pollSteam() {
    const iv = setInterval(async () => {
      const s = await api.upload.steam.status(id)
      setSteamStatus(s.status)
      setSteamLog(s.logs)
      if (s.status !== 'running') clearInterval(iv)
    }, 1000)
    return () => clearInterval(iv)
  }

  async function startBuild() {
    setBuildLog([]); setBuildStatus('running')
    await api.build.start(id)
    pollBuild()
  }

  async function startItch() {
    setItchLog([]); setItchStatus('running')
    await api.upload.itch.start(id)
    pollItch()
  }

  async function startSteam() {
    setSteamLog([]); setSteamStatus('running')
    await api.upload.steam.start(id)
    pollSteam()
  }

  async function handleZip() {
    const r = await api.zip.create(id)
    alert(`Zip created: ${r.path}`)
  }

  async function handleDelete() {
    if (!confirm('Delete this project?')) return
    await api.projects.delete(id)
    navigate('/projects')
  }

  const configFields: { label: string; key: string }[] = [
    { label: 'Name', key: 'name' },
    { label: 'Project Path', key: 'project_path' },
    { label: 'Build Path', key: 'build_path' },
    { label: 'Engine', key: 'engine' },
    { label: 'Platform', key: 'platform' },
    { label: 'Godot Preset', key: 'godot_preset' },
  ]

  const itchFields: { label: string; key: string }[] = [
    { label: 'Itch Target', key: 'itch_target' },
    { label: 'Itch URL', key: 'itch_url' },
  ]

  const steamFields: { label: string; key: string }[] = [
    { label: 'Steam App ID', key: 'steam_app_id' },
    { label: 'Steam Demo App ID', key: 'steam_demo_app_id' },
    { label: 'Steam URL', key: 'steam_url' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">{proj.name}</h2>
        <div className="flex gap-2">
          <button onClick={handleDetect} className="bg-gray-700 px-3 py-1 rounded text-sm hover:bg-gray-600">
            Detect
          </button>
          <button onClick={handleDelete} className="bg-red-800 px-3 py-1 rounded text-sm hover:bg-red-700">
            Delete
          </button>
        </div>
      </div>

      {detected && (
        <div className="bg-gray-800 rounded p-3 text-sm flex gap-4">
          <span>Engine: <strong className="text-teal-400">{detected.engine || '-'}</strong></span>
          <span>Version: <strong>{detected.version || '-'}</strong></span>
          {detected.presets.length > 0 && (
            <span>Presets: <strong>{detected.presets.join(', ')}</strong></span>
          )}
        </div>
      )}

      <div className="bg-gray-800 rounded p-4">
        <h3 className="font-semibold mb-3">Project Config</h3>
        <div className="grid grid-cols-2 gap-3">
          {configFields.map(f => (
            <div key={f.key}>
              <label className="text-xs text-gray-400 block">{f.label}</label>
              <input value={(proj as any)[f.key] || ''} onChange={e => saveField(f.key, e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm" />
            </div>
          ))}
        </div>
      </div>

      <div className="bg-gray-800 rounded p-4">
        <h3 className="font-semibold mb-3 text-purple-400">itch.io</h3>
        <div className="grid grid-cols-2 gap-3 mb-3">
          {itchFields.map(f => (
            <div key={f.key}>
              <label className="text-xs text-gray-400 block">{f.label}</label>
              <input value={(proj as any)[f.key] || ''} onChange={e => saveField(f.key, e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm" />
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400">Demo Build</label>
          <input type="checkbox" checked={proj.demo_build} onChange={e => saveField('demo_build', e.target.checked)}
            className="accent-purple-500" />
        </div>
      </div>

      <div className="bg-gray-800 rounded p-4">
        <h3 className="font-semibold mb-3 text-teal-400">Steam</h3>
        <div className="grid grid-cols-2 gap-3">
          {steamFields.map(f => (
            <div key={f.key}>
              <label className="text-xs text-gray-400 block">{f.label}</label>
              <input value={(proj as any)[f.key] || ''} onChange={e => saveField(f.key, e.target.value)}
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm" />
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button onClick={startBuild} disabled={buildStatus === 'running'}
          className="bg-blue-700 px-4 py-2 rounded text-sm hover:bg-blue-600 disabled:opacity-50">
          Build {buildStatus === 'running' ? '...' : ''}
        </button>
        <button onClick={startItch} disabled={itchStatus === 'running'}
          className="bg-purple-700 px-4 py-2 rounded text-sm hover:bg-purple-600 disabled:opacity-50">
          Upload Itch.io {itchStatus === 'running' ? '...' : ''}
        </button>
        <button onClick={startSteam} disabled={steamStatus === 'running'}
          className="bg-teal-700 px-4 py-2 rounded text-sm hover:bg-teal-600 disabled:opacity-50">
          Upload Steam {steamStatus === 'running' ? '...' : ''}
        </button>
        <button onClick={handleZip} className="bg-gray-700 px-4 py-2 rounded text-sm hover:bg-gray-600">
          Create Zip
        </button>
      </div>

      {buildStatus !== 'idle' && (
        <div className="bg-gray-800 rounded p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${buildStatus === 'running' ? 'bg-yellow-400 animate-pulse' : buildStatus === 'completed' ? 'bg-green-400' : 'bg-red-400'}`} />
            <span className="font-semibold text-sm">Build: {buildStatus}</span>
          </div>
          <div ref={logRef} className="bg-black rounded p-3 h-48 overflow-auto font-mono text-xs text-green-400">
            {buildLog.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}

      {itchStatus !== 'idle' && (
        <div className="bg-gray-800 rounded p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${itchStatus === 'running' ? 'bg-yellow-400 animate-pulse' : itchStatus === 'completed' ? 'bg-green-400' : 'bg-red-400'}`} />
            <span className="font-semibold text-sm">Itch.io: {itchStatus}</span>
          </div>
          <div className="bg-black rounded p-3 h-32 overflow-auto font-mono text-xs text-green-400">
            {itchLog.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}

      {steamStatus !== 'idle' && (
        <div className="bg-gray-800 rounded p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className={`w-2 h-2 rounded-full ${steamStatus === 'running' ? 'bg-yellow-400 animate-pulse' : steamStatus === 'completed' ? 'bg-green-400' : 'bg-red-400'}`} />
            <span className="font-semibold text-sm">Steam: {steamStatus}</span>
          </div>
          <div className="bg-black rounded p-3 h-32 overflow-auto font-mono text-xs text-green-400">
            {steamLog.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}
    </div>
  )
}
