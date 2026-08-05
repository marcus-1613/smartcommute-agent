import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DataSources, RouteScore } from '../types'

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
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
        <h1>通勤助手</h1>
        <p className="subtitle">
          用自然语言描述你的通勤需求，例如：我明天早上 8 点从裕廊东去滨海湾，尽量少换乘
        </p>
      </div>

      <div className="chat-window">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>👋 你好，我是你的智慧通勤助手</p>
            <p>告诉我你的出发地、目的地和出发时间，我会为你规划最优路线。</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg-row ${m.role}`}>
            <div className="bubble">
              {m.loading ? (
                <span className="loading-dots">正在查询路线</span>
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

function RouteComparison({ scores }: { scores: RouteScore[] }) {  const [selected, setSelected] = useState<RouteScore>(scores[0])

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
              <span className="route-summary">{s.route.summary}</span>
              <span className="route-score">{s.score.toFixed(2)} 分</span>
            </div>
            <div className="route-metrics">
              <span>⏱ {s.route.duration_min ?? '—'} 分钟</span>
              <span>💰 S${s.route.fare_sgd ?? '—'}</span>
              <span>🚶 {s.route.walk_distance_m ?? '—'} m</span>
              <span>🔄 {s.route.transfers ?? '—'} 次换乘</span>
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
          {selected.route.steps?.map((st, i) => (
            <div key={i} className="step">
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
              <span>{st.description}</span>
              {st.line && <span className="step-line">{st.line}</span>}
            </div>
          ))}
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
