import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import type { DataSources, RouteScore } from '../types'

const SESSION_KEY = 'smartcommute.sessionId'

const QUICK_TASKS = [
  { icon: '🚇', label: '规划通勤路线', prompt: '我明天早上 8 点从裕廊东去滨海湾，尽量少换乘' },
  { icon: '☀️', label: '查询天气影响', prompt: '今天天气会不会影响我的通勤？' },
  { icon: '🚧', label: '查看交通路况', prompt: '现在有没有影响我出行的交通事故？' },
  { icon: '💡', label: '了解交通方式', prompt: '新加坡有哪些公共交通方式？' },
]

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  scores?: RouteScore[]
  source?: string
  dataSources?: DataSources
  loading?: boolean
}

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [restoring, setRestoring] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 进入页面时：从 localStorage 读取 sessionId，向后端拉取历史消息恢复
  useEffect(() => {
    const saved = localStorage.getItem(SESSION_KEY)
    if (saved) {
      restoreSession(saved)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function restoreSession(id: string) {
    setRestoring(true)
    setError('')
    try {
      const detail = await api.getSession(id)
      setSessionId(detail.session_id)
      setMessages(
        detail.messages.map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          scores: m.meta?.route_scores,
          source: m.meta?.source,
          dataSources: m.meta?.data_sources,
        }))
      )
    } catch (e: any) {
      // 会话可能已被删除或后端不可用，静默回退为全新会话
      localStorage.removeItem(SESSION_KEY)
      setSessionId(null)
      setMessages([])
    } finally {
      setRestoring(false)
    }
  }

  function newSession() {
    setSessionId(null)
    setMessages([])
    setInput('')
    setError('')
    localStorage.removeItem(SESSION_KEY)
  }

  async function send() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setError('')
    setSending(true)

    setMessages((prev) => [...prev, { role: 'user', content: text }])
    // 占位 loading 消息
    setMessages((prev) => [...prev, { role: 'assistant', content: '', loading: true }])

    try {
      const res = await api.chat(text, sessionId || undefined)
      setSessionId(res.session_id)
      localStorage.setItem(SESSION_KEY, res.session_id)
      // 替换 loading 消息
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = {
          role: 'assistant',
          content: res.reply,
          scores: res.route_scores,
          source: res.source,
          dataSources: res.data_sources,
        }
        return next
      })
    } catch (e: any) {
      setError(e.message || '请求失败，请确认后端已启动')
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = {
          role: 'assistant',
          content: '出错了，请稍后重试。',
        }
        return next
      })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-header">
        <div className="chat-header-top">
          <h1>通勤助手</h1>
          {(sessionId || messages.length > 0) && (
            <button className="new-session-btn" onClick={newSession}>
              ＋ 新对话
            </button>
          )}
        </div>
        <p className="subtitle">
          用自然语言描述你的通勤需求，例如：我明天早上 8 点从裕廊东去滨海湾，尽量少换乘
        </p>
      </div>

      <div className="chat-window">
        {restoring && (
          <div className="chat-empty">
            <p>正在恢复上次会话…</p>
          </div>
        )}
        {!restoring && messages.length === 0 && (
          <div className="chat-empty">
            <span className="empty-emoji">🚇</span>
            <p>👋 你好，我是你的智慧通勤助手</p>
            <p>告诉我你的出发地、目的地和出发时间，我会为你规划最优路线。</p>
            <div className="quick-tasks">
              {QUICK_TASKS.map((t) => (
                <button
                  key={t.label}
                  className="quick-task"
                  onClick={() => setInput(t.prompt)}
                >
                  <span className="quick-task-icon">{t.icon}</span>
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg-row ${m.role}`}>
            <div className="avatar">{m.role === 'assistant' ? '🚇' : '👤'}</div>
            <div className="bubble">
              {m.loading ? (
                <div className="loading-skeleton">
                  <span className="skeleton-line skeleton-line-1" />
                  <span className="skeleton-line skeleton-line-2" />
                  <span className="skeleton-line skeleton-line-3" />
                </div>
              ) : m.role === 'assistant' ? (
                // 助手回复可能包含 Markdown（加粗、列表、代码块），按富文本渲染；
                // 用户输入保持纯文本，避免把用户打的 * 号误当 Markdown 解析。
                // remarkBreaks：单个换行也渲染为换行，与模型输出的分行习惯一致。
                <div className="msg-text msg-markdown">
                  <Markdown remarkPlugins={[remarkGfm, remarkBreaks]}>{m.content}</Markdown>
                </div>
              ) : (
                <pre className="msg-text">{m.content}</pre>
              )}
              {m.dataSources && <SourceTags sources={m.dataSources} />}
              {!m.dataSources && m.source === 'mock' && (
                <div className="mock-tag">模拟数据演示模式</div>
              )}
              {!m.dataSources && m.source && m.source !== 'mock' && m.source !== 'error' && (
                <div className="live-tag">实时数据 · {m.source}</div>
              )}
              {!m.dataSources && m.source === 'error' && (
                <div className="error-tag">路线数据暂不可用</div>
              )}
              {m.scores && m.scores.length > 0 && (
                <RouteComparison scores={m.scores} />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="chat-input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="例如：我明天早上 8 点从 Jurong East 去 Marina Bay，少换乘"
          rows={2}
        />
        <button onClick={send} disabled={sending || !input.trim()}>
          {sending ? '查询中…' : '发送'}
        </button>
      </div>
    </div>
  )
}

function SourceTags({ sources }: { sources: DataSources }) {
  const labels: { key: string; name: string; entry?: { source: string; status: string } }[] = [
    { key: 'routes', name: '路线', entry: sources.routes },
    { key: 'weather', name: '天气', entry: sources.weather },
    { key: 'traffic', name: '交通事件', entry: sources.traffic },
  ]

  const present = labels.filter((l) => l.entry)

  const overallLabel =
    sources.overall === 'mock'
      ? '模拟数据演示模式'
      : sources.overall === 'live'
      ? '实时数据'
      : sources.overall === 'degraded'
      ? '部分数据可用'
      : sources.overall === 'error'
      ? '数据不可用'
      : sources.overall

  return (
    <div className="source-tags">
      <div className={`overall-tag tag-${sources.overall}`}>{overallLabel}</div>
      <div className="source-detail">
        {present.map((l) => {
          const isMock = l.entry!.source === 'mock'
          const isError = l.entry!.status === 'error'
          const cls = isError ? 'tag-error' : isMock ? 'tag-mock' : 'tag-live'
          const text = isError
            ? '不可用'
            : isMock
            ? '模拟'
            : l.entry!.source
          return (
            <span key={l.key} className={`source-chip ${cls}`}>
              {l.name} · {text}
            </span>
          )
        })}
      </div>
    </div>
  )
}

function RouteComparison({ scores }: { scores: RouteScore[] }) {
  const [selected, setSelected] = useState<RouteScore>(scores[0])
  const bestId = scores[0]?.route.id

  return (
    <div className="route-compare">
      <div className="route-cards">
        {scores.map((s) => (
          <div
            key={s.route.id}
            className={`route-card ${selected?.route.id === s.route.id ? 'selected' : ''} ${
              !s.feasible ? 'infeasible' : ''
            }`}
            onClick={() => setSelected(s)}
          >
            <div className="route-card-head">
              <span className="route-summary">
                {s.route.id === bestId && s.feasible && (
                  <span className="route-best-badge">推荐</span>
                )}
                {s.route.summary}
              </span>
              <span className="route-score">{s.score.toFixed(2)} 分</span>
            </div>
            <div className="route-metrics">
              <span className="metric"><span className="metric-icon">⏱</span><span className="metric-label">耗时</span><strong>{s.route.duration_min ?? '—'} 分钟</strong></span>
              <span className="metric"><span className="metric-icon">💰</span><span className="metric-label">费用</span><strong>S${s.route.fare_sgd ?? '—'}</strong></span>
              <span className="metric"><span className="metric-icon">🚶</span><span className="metric-label">步行</span><strong>{s.route.walk_distance_m ?? '—'} m</strong></span>
              <span className="metric"><span className="metric-icon">🔄</span><span className="metric-label">换乘</span><strong>{s.route.transfers ?? '—'} 次</strong></span>
            </div>
            {!s.feasible && (
              <div className="violation">
                {s.constraint_violations.join('；')}
              </div>
            )}
          </div>
        ))}
      </div>

      {selected && (
        <div className="route-detail">
          <h4>路线详情</h4>
          <div className="step-timeline">
            {selected.route.steps?.map((st, i) => (
              <div key={i} className="step">
                <span className={`step-dot ${st.type}`} />
                <div className="step-content">
                  <span className={`step-badge ${st.type}`}>
                    {st.type === 'transit'
                      ? '地铁'
                      : st.type === 'walk'
                      ? '步行'
                      : st.type === 'transfer'
                      ? '换乘'
                      : st.type === 'drive'
                      ? '驾车'
                      : st.type}
                  </span>
                  <span className="step-desc">{st.description}</span>
                  {st.line && <span className="step-line">{st.line}</span>}
                </div>
              </div>
            ))}
          </div>
          <div className="score-breakdown">
            <span>耗时 {selected.score_detail.duration.toFixed(2)}</span>
            <span>费用 {selected.score_detail.fare.toFixed(2)}</span>
            <span>步行 {selected.score_detail.walking.toFixed(2)}</span>
            <span>换乘 {selected.score_detail.transfers.toFixed(2)}</span>
          </div>
        </div>
      )}
    </div>
  )
}
