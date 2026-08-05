import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Preferences } from '../types'

const DEFAULTS: Preferences = {
  default_mode: 'transit',
  prefer_fewer_transfers: 0.5,
  prefer_less_walking: 0.5,
  prefer_lower_cost: 0.5,
  prefer_shorter_time: 0.5,
  max_walk_m: 800,
  max_transfers: 2,
}

export default function PreferencesPage() {
  const [prefs, setPrefs] = useState<Preferences>(DEFAULTS)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      setPrefs(await api.getPreferences())
    } catch (e: any) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  async function save() {
    setSaving(true)
    setMsg('')
    setError('')
    try {
      const updated = await api.updatePreferences(prefs)
      setPrefs(updated)
      setMsg('已保存 ✓')
    } catch (e: any) {
      setError(e.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  function update<K extends keyof Preferences>(key: K, value: Preferences[K]) {
    setPrefs((p) => ({ ...p, [key]: value }))
  }

  if (loading) return <p className="hint">加载中…</p>

  return (
    <div className="page">
      <h1>用户偏好</h1>
      <div className="pref-card">
        <div className="pref-group">
          <label>默认交通方式</label>
          <select
            value={prefs.default_mode}
            onChange={(e) => update('default_mode', e.target.value)}
          >
            <option value="transit">公共交通</option>
            <option value="driving">驾车</option>
          </select>
        </div>

        <div className="pref-group">
          <label>换乘倾向（越大越偏好少换乘）</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={prefs.prefer_fewer_transfers}
            onChange={(e) =>
              update('prefer_fewer_transfers', Number(e.target.value))
            }
          />
          <span className="range-val">{prefs.prefer_fewer_transfers.toFixed(1)}</span>
        </div>

        <div className="pref-group">
          <label>步行倾向（越大越偏好少走路）</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={prefs.prefer_less_walking}
            onChange={(e) =>
              update('prefer_less_walking', Number(e.target.value))
            }
          />
          <span className="range-val">{prefs.prefer_less_walking.toFixed(1)}</span>
        </div>

        <div className="pref-group">
          <label>费用倾向（越大越偏好低费用）</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={prefs.prefer_lower_cost}
            onChange={(e) =>
              update('prefer_lower_cost', Number(e.target.value))
            }
          />
          <span className="range-val">{prefs.prefer_lower_cost.toFixed(1)}</span>
        </div>

        <div className="pref-group">
          <label>耗时倾向（越大越偏好短耗时）</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={prefs.prefer_shorter_time}
            onChange={(e) =>
              update('prefer_shorter_time', Number(e.target.value))
            }
          />
          <span className="range-val">{prefs.prefer_shorter_time.toFixed(1)}</span>
        </div>

        <div className="pref-group">
          <label>最大步行距离（米）</label>
          <input
            type="number"
            min={0}
            value={prefs.max_walk_m}
            onChange={(e) => update('max_walk_m', Number(e.target.value))}
          />
        </div>

        <div className="pref-group">
          <label>最大换乘次数</label>
          <input
            type="number"
            min={0}
            value={prefs.max_transfers}
            onChange={(e) => update('max_transfers', Number(e.target.value))}
          />
        </div>

        {msg && <div className="success-banner">{msg}</div>}
        {error && <div className="error-banner">{error}</div>}

        <button className="save-btn" onClick={save} disabled={saving}>
          {saving ? '保存中…' : '保存偏好'}
        </button>
      </div>
    </div>
  )
}
