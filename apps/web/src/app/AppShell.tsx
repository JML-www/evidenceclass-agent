import React from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { isMockApi } from '../api/client'
import {
  IconBell,
  IconChevronDown,
  IconExternal,
  IconMenu,
  IconMoon,
  IconSun,
} from '../components/icons'
import { breadcrumbTitle, navGroups, navItems } from '../lib/constants'

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = React.useState<'notifications' | 'profile' | null>(null)
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

  // 点击空白处关闭顶栏下拉。
  React.useEffect(() => {
    if (!menuOpen) return
    const close = () => setMenuOpen(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [menuOpen])

  const isDark = theme
    ? theme === 'dark'
    : typeof window !== 'undefined' &&
      window.matchMedia('(prefers-color-scheme: dark)').matches

  const toggleTheme = () => {
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
    setMenuOpen(null)
    if (!isMockApi) navigate('/login')
  }

  const currentTitle = breadcrumbTitle(location.pathname)

  const isActive = (to: string, match?: string) =>
    location.pathname === to || (match ? location.pathname.startsWith(match) : false)

  return (
    <div className={navOpen ? 'app-shell nav-open' : 'app-shell'}>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">灵</span>
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
          <IconChevronDown size={14} className="chevron" />
        </div>

        <nav aria-label="主导航">
          {navGroups.map(group => (
            <React.Fragment key={group}>
              <div className="nav-group-label">{group}</div>
              {navItems
                .filter(item => item.group === group)
                .map(item => {
                  const Icon = item.icon
                  const active = isActive(item.to, item.match)
                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      aria-current={active ? 'page' : undefined}
                      className={active ? 'nav-item active' : 'nav-item'}
                      onClick={() => setNavOpen(false)}
                    >
                      <span className="nav-icon">
                        <Icon size={17} />
                      </span>
                      {item.label}
                    </Link>
                  )
                })}
            </React.Fragment>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="system-status">
            <span className="status-dot" /> API 与 Worker <span className="status-ok">正常</span>
          </div>
          <a
            href="https://github.com/JML-www/evidenceclass-agent"
            target="_blank"
            rel="noreferrer"
            className="help-link"
          >
            <span className="inline">
              文档与帮助 <IconExternal size={13} />
            </span>
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
          <div className="inline">
            <button
              className="menu-button"
              aria-label="切换导航"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(value => !value)}
            >
              <IconMenu />
            </button>
            <span className="topbar-title">{currentTitle}</span>
          </div>

          <div className="top-actions">
            <button
              className="icon-button"
              aria-label={isDark ? '切换到浅色主题' : '切换到深色主题'}
              onClick={toggleTheme}
            >
              {isDark ? <IconSun size={17} /> : <IconMoon size={17} />}
            </button>

            <div className="top-action-wrap">
              <button
                className="icon-button"
                aria-label="通知"
                aria-expanded={menuOpen === 'notifications'}
                onClick={event => {
                  event.stopPropagation()
                  setMenuOpen(value => (value === 'notifications' ? null : 'notifications'))
                }}
              >
                <IconBell size={17} />
                <span className="notification-dot" />
              </button>
              {menuOpen === 'notifications' && (
                <div className="popover" onClick={event => event.stopPropagation()}>
                  <b>通知</b>
                  <p>暂无未读通知</p>
                </div>
              )}
            </div>

            <div className="top-action-wrap">
              <button
                className="profile-button"
                aria-expanded={menuOpen === 'profile'}
                onClick={event => {
                  event.stopPropagation()
                  setMenuOpen(value => (value === 'profile' ? null : 'profile'))
                }}
              >
                <span className="avatar small">王</span>
                <span>王子豪</span>
                <IconChevronDown size={14} className="chevron" />
              </button>
              {menuOpen === 'profile' && (
                <div
                  className="popover profile-popover"
                  onClick={event => event.stopPropagation()}
                >
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
