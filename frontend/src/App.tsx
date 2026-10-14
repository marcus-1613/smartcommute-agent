import { NavLink, Route, Routes } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import HistoryPage from './pages/HistoryPage'
import PreferencesPage from './pages/PreferencesPage'

export default function App() {
  const navItems = [
    { to: '/', label: '通勤助手', end: true },
    { to: '/history', label: '历史记录' },
    { to: '/preferences', label: '用户偏好' },
  ]

  return (
    <div className="app">
      <header className="topbar">
        <div className="container topbar-inner">
          <span className="logo">🚇 SmartCommute AI</span>
          <nav className="nav">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  isActive ? 'nav-link active' : 'nav-link'
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
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
