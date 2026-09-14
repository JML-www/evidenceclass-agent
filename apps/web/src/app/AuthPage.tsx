import React from 'react'
import { useNavigate } from 'react-router-dom'
import { isMockApi, login, register } from '../api/client'
import { IconLock, IconShield } from '../components/icons'

export function AuthPage() {
  const navigate = useNavigate()
  const [registerMode, setRegisterMode] = React.useState(false)
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [workspace, setWorkspace] = React.useState('灵眸智课工作区')
  const [error, setError] = React.useState('')
  const [pending, setPending] = React.useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setPending(true)
    setError('')
    try {
      const result = registerMode
        ? await register(email, password, workspace)
        : await login(email, password)
      window.localStorage.setItem('evidenceclass.access_token', result.access_token)
      if (result.workspace_id) {
        window.localStorage.setItem('evidenceclass.workspace_id', result.workspace_id)
      }
      navigate('/jobs')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '认证失败')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-panel" onSubmit={submit}>
        <div className="auth-brand">
          <span className="brand-mark">灵</span>
          <span>
            <b>灵眸智课</b>
            <small>EvidenceClass Agent</small>
          </span>
        </div>

        <h1>{registerMode ? '创建工作区' : '登录'}</h1>
        <p>
          {registerMode
            ? '创建一个新的工作区，开始课堂学习行为分析。'
            : '登录后进入证据优先的课堂学习行为分析工作台。'}
        </p>

        <label className="field-label" htmlFor="auth-email">
          邮箱
        </label>
        <input
          id="auth-email"
          type="email"
          required
          value={email}
          onChange={event => setEmail(event.target.value)}
          autoComplete="email"
        />

        <label className="field-label" htmlFor="auth-password">
          密码
        </label>
        <input
          id="auth-password"
          type="password"
          required
          minLength={registerMode ? 8 : 1}
          value={password}
          onChange={event => setPassword(event.target.value)}
          autoComplete={registerMode ? 'new-password' : 'current-password'}
        />

        {registerMode && (
          <>
            <label className="field-label" htmlFor="auth-workspace">
              工作区名称
            </label>
            <input
              id="auth-workspace"
              required
              value={workspace}
              onChange={event => setWorkspace(event.target.value)}
            />
          </>
        )}

        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}

        <button className="primary-button submit-button" disabled={pending}>
          {pending ? '提交中…' : registerMode ? '注册并进入' : '登录'}
        </button>

        <button
          type="button"
          className="text-button auth-switch"
          onClick={() => {
            setRegisterMode(value => !value)
            setError('')
          }}
        >
          {registerMode ? '已有账号，返回登录' : '首次使用？创建工作区'}
        </button>

        <div className="auth-foot">
          <span className="inline">
            {isMockApi ? <IconShield size={14} /> : <IconLock size={14} />}
            {isMockApi ? '当前为 Mock 模式，可直接进入' : '真实 API 模式需要工作区身份'}
          </span>
        </div>
      </form>
    </div>
  )
}
