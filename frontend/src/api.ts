const BASE = 'http://127.0.0.1:8700'

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
  })
  if (!r.ok) {
    const body = await r.text()
    throw new Error(`${r.status}: ${body}`)
  }
  return r.json()
}

export interface Project {
  id: string
  name: string
  project_path: string
  build_path: string
  engine: string
  platform: string
  itch_target: string
  itch_url: string
  steam_app_id: string
  steam_demo_app_id: string
  steam_url: string
  steam_depots: Record<string, string>
  demo_build: boolean
  last_build_time: string
  last_build_success: boolean
  godot_preset?: string
}

export const api = {
  projects: {
    list: () => req<Project[]>('/api/projects'),
    get: (id: string) => req<Project>(`/api/projects/${id}`),
    create: (projectPath: string) => req<{ id: string }>(`/api/projects?project_path=${encodeURIComponent(projectPath)}`, { method: 'POST' }),
    update: (id: string, data: Partial<Project>) => req<{ ok: boolean }>(`/api/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id: string) => req<{ ok: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),
    detect: (id: string) => req<{ engine: string; presets: string[]; version: string }>(`/api/projects/${id}/detect`),
  },
  build: {
    start: (id: string) => req<{ ok: boolean; status: string }>(`/api/projects/${id}/build`, { method: 'POST' }),
    status: (id: string) => req<{ status: string; logs: string[] }>(`/api/projects/${id}/build/status`),
  },
  upload: {
    itch: {
      start: (id: string) => req<{ ok: boolean; status: string }>(`/api/projects/${id}/upload/itch`, { method: 'POST' }),
      status: (id: string) => req<{ status: string; logs: string[] }>(`/api/projects/${id}/upload/itch/status`),
    },
    steam: {
      start: (id: string) => req<{ ok: boolean; status: string }>(`/api/projects/${id}/upload/steam`, { method: 'POST' }),
      status: (id: string) => req<{ status: string; logs: string[] }>(`/api/projects/${id}/upload/steam/status`),
    },
  },
  zip: {
    create: (id: string) => req<{ ok: boolean; path: string }>(`/api/projects/${id}/zip`, { method: 'POST' }),
  },
  settings: {
    get: () => req<Record<string, string>>('/api/settings'),
    update: (data: Record<string, string>) => req<{ ok: boolean }>('/api/settings', { method: 'PUT', body: JSON.stringify(data) }),
  },
}
