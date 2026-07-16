import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({})

  useEffect(() => { api.settings.get().then(setSettings) }, [])

  function update(key: string, value: string) {
    const updated = { ...settings, [key]: value }
    setSettings(updated)
    api.settings.update({ [key]: value })
  }

  const fields = [
    { key: 'godot_executable', label: 'Godot Executable' },
    { key: 'unity_executable', label: 'Unity Executable' },
    { key: 'steam_username', label: 'Steam Username' },
    { key: 'steam_script_path', label: 'Steam Script Path' },
    { key: 'itch_api_key', label: 'itch.io API Key', sensitive: true },
    { key: 'steam_token', label: 'Steam Token', sensitive: true },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Settings</h2>
      <div className="bg-gray-800 rounded p-4 space-y-3">
        {fields.map(f => (
          <div key={f.key}>
            <label className="text-xs text-gray-400 block">{f.label}</label>
            <input
              type={f.sensitive ? 'password' : 'text'}
              value={settings[f.key] || ''}
              onChange={e => update(f.key, e.target.value)}
              className="w-full max-w-lg bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm"
            />
          </div>
        ))}
        <p className="text-xs text-gray-500">Sensitive fields are stored in your OS keychain.</p>
      </div>
    </div>
  )
}
