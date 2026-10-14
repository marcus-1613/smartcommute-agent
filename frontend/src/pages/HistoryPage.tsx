import { useEffect, useState } from 'react'
import { api } from '../api'
import type { CommuteSummary, SessionSummary } from '../types'

export default function HistoryPage() {
  const [tab, setTab] = useState<'sessions' | 'commutes'>('sessions')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [commutes, setCommutes] = useState<CommuteSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    load()
  }, [tab])

  async function load() {
    setLoading(true)
    setError('')
    try {
      if (tab === 'sessions') {
        setSessions(await api.listSessions())
      } else {
        setCommutes(await api.listCommutes())
      }
    } catch (e: any) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <h1>历史记录</h1>
      <div className="tabs">
        <button
          className={tab === 'sessions' ? 'tab active' : 'tab'}
          onClick={() => setTab('sessions')}
        >
          历史会话
        </button>
        <button
          className={tab === 'commutes' ? 'tab active' : 'tab'}
          onClick={() => setTab('commutes')}
        >
          通勤计划
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {loading && <p className="hint">加载中…</p>}

      {!loading && tab === 'sessions' && (
        <div className="list">
          {sessions.length === 0 && (
            <p className="hint">暂无历史会话，去通勤助手发起一次对话吧。</p>
          )}
          {sessions.map((s) => (
            <div key={s.session_id} className="list-item">
              <div className="list-item-main">
                <strong>{s.title}</strong>
                <span className="muted">
                  {s.message_count} 条消息 · {formatTime(s.updated_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && tab === 'commutes' && (
        <div className="list">
          {commutes.length === 0 && (
            <p className="hint">暂无通勤计划记录。</p>
          )}
          {commutes.map((c) => (
            <div key={c.id} className="list-item">
              <div className="list-item-main">
                <strong>
                  {c.origin} → {c.destination}
                </strong>
                <span className="muted">
                  {c.departure_time || '时间未指定'} · {c.mode} ·{' '}
                  {c.source === 'mock' ? '模拟数据' : '实时数据'} ·{' '}
                  {formatTime(c.created_at)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}
