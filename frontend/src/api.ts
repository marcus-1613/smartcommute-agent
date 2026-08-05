// API 客户端封装
import type {
  ChatResponse,
  CommuteDetail,
  CommuteSummary,
  Preferences,
  SessionDetail,
  SessionSummary,
} from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`请求失败 (${res.status}): ${body}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; mock_mode: boolean }>('/health'),

  chat: (message: string, sessionId?: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId || null }),
    }),

  listSessions: () => request<SessionSummary[]>('/sessions'),
  getSession: (id: string) => request<SessionDetail>(`/sessions/${id}`),

  listCommutes: () => request<CommuteSummary[]>('/commutes'),
  getCommute: (id: number) => request<CommuteDetail>(`/commutes/${id}`),

  getPreferences: () => request<Preferences>('/preferences'),
  updatePreferences: (prefs: Partial<Preferences>) =>
    request<Preferences>('/preferences', {
      method: 'PUT',
      body: JSON.stringify(prefs),
    }),
}
