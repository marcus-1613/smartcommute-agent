import { useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import HistoryPage from './pages/HistoryPage'
import PreferencesPage from './pages/PreferencesPage'

const navItems = [
  { to: '/', label: '通勤助手', icon: '💬', end: true },
  { to: '/history', label: '历史记录', icon: '🕘', end: false },
  { to: '/preferences', label: '用户偏好', icon: '⚙️', end: false },
]

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="app">
      <header className="topbar">
        <div className="container topbar-inner">
          <span className="logo">
            <span className="logo-icon">🚇</span>
            <span className="logo-text">SmartCommute AI</span>
          </span>
          <nav className="nav nav-desktop">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  isActive ? 'nav-link active' : 'nav-link'
                }
              >
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
          <button
            className="nav-toggle"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label="切换导航菜单"
            aria-expanded={menuOpen}
          >
            <span className="nav-toggle-bar" />
            <span className="nav-toggle-bar" />
            <span className="nav-toggle-bar" />
          </button>
        </div>
        {menuOpen && (
          <nav className="nav nav-mobile">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  isActive ? 'nav-link active' : 'nav-link'
                }
              >
                <span className="nav-icon">{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="container main">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/preferences" element={<PreferencesPage />} />
        </Routes>
      </main>
    </div>
  )
}
