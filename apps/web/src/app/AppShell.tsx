import React from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { isMockApi } from '../api/client'
import { breadcrumbTitle, navItems } from '../lib/constants'

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const [notificationsOpen, setNotificationsOpen] = React.useState(false)
  const [profileOpen, setProfileOpen] = React.useState(false)
  const [navOpen, setNavOpen] = React.useState(false)
  const [theme, setTheme] = React.useState<'dark' | 'light' | null>(() => {
    const stored = window.localStorage.getItem('evidenceclass.theme')
    return stored === 'dark' || stored === 'light' ? stored : null
  })

  React.useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
    else document.documentElement.removeAttribute('data-theme')
  }, [theme])

  React.useEffect(() => {
    const onResize = () => {
      if (window.innerWidth > 1024) setNavOpen(false)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const toggleTheme = () => {
    const isDark = theme
      ? theme === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches
    const next: 'dark' | 'light' = isDark ? 'light' : 'dark'
    window.localStorage.setItem('evidenceclass.theme', next)
    setTheme(next)
  }

  // 路由守卫：真实 API 模式下未登录则跳转到登录页。
  const token = window.localStorage.getItem('evidenceclass.access_token')
  if (!isMockApi && !token) return <Navigate to="/login" replace />

  const logout = () => {
    window.localStorage.removeItem('evidenceclass.access_token')
    window.localStorage.removeItem('evidenceclass.workspace_id')
    setProfileOpen(false)
    if (!isMockApi) navigate('/login')
  }

  const title = breadcrumbTitle(location.pathname)
  const isDark = theme
    ? theme === 'dark'
    : typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches

  return (
    <div className={`app-shell${navOpen ? ' nav-open' : ''}`}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">L</span>
          <span>
            <b>灵眸智课</b>
            <small>EvidenceClass Agent</small>
          </span>
        </div>
        <div className="workspace-switcher">
          <span className="avatar">王</span>
          <span>
            <b>王子豪的工作区</b>
            <small>个人项目</small>
          </span>
          <span className="chevron">⌄</span>
        </div>
        <nav aria-label="主导航">
          {navItems.map(item => {
            const active =
              location.pathname === item.to ||
              (item.to.startsWith('/runs') &&
                location.pathname.startsWith('/runs'))
            return (
              <Link
                key={item.to}
                to={item.to}
                aria-current={active ? 'page' : undefined}
                className={active ? 'nav-item active' : 'nav-item'}
                onClick={() => setNavOpen(false)}
              >
                <span className="nav-icon" aria-hidden="true">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="system-status">
            <span className="status-dot" /> API 与 Worker{' '}
            <span className="status-ok">正常</span>
          </div>
          <a
            href="https://github.com/JML-www/evidenceclass-agent"
            target="_blank"
            rel="noreferrer"
            className="help-link"
          >
            文档与帮助 ↗
          </a>
        </div>
      </aside>
      {navOpen && (
        <div
          className="sidebar-overlay"
          aria-hidden="true"
          onClick={() => setNavOpen(false)}
        />
      )}
      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="menu-button"
              aria-label="切换导航"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(value => !value)}
            >
              ☰
            </button>
            灵眸智课 <span>/</span> {title}
          </div>
          <div className="top-actions">
            <button
              className="theme-toggle"
              aria-label={isDark ? '切换到浅色主题' : '切换到深色主题'}
              onClick={toggleTheme}
            >
              {isDark ? '☀' : '☾'}
            </button>
            <div className="top-action-wrap">
              <button
                className="icon-button"
                aria-label="通知"
                onClick={() => setNotificationsOpen(value => !value)}
              >
                ♢<span className="notification-dot" />
              </button>
              {notificationsOpen && (
                <div className="popover">
                  <b>通知</b>
                  <p className="muted">暂无未读通知</p>
                </div>
              )}
            </div>
            <div className="top-action-wrap">
              <button
                className="profile-button"
                onClick={() => setProfileOpen(value => !value)}
              >
                <span className="avatar small">王</span>
                <span>王子豪</span>
                <span className="chevron">⌄</span>
              </button>
              {profileOpen && (
                <div className="popover profile-popover">
                  <span>个人项目</span>
                  <button className="text-button" onClick={logout}>
                    退出登录
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  )
}
