import type { AnalysisMode, JobStatus } from '../types'

export const statusText: Record<JobStatus, string> = {
  QUEUED: '排队中',
  RUNNING: '运行中',
  NEEDS_REVIEW: '待复核',
  SUCCEEDED: '成功',
  FAILED: '失败',
  CANCELLED: '已取消',
}

export const modeText: Record<AnalysisMode, string> = {
  IMAGE: '单图',
  VIDEO: '短视频',
  STRUCTURED: '结构化',
}

/** 全部 9 个页面的导航项，供侧边栏、面包屑与路由守卫共用。 */
export const navItems = [
  { to: '/jobs', label: '任务中心', icon: '▦' },
  { to: '/new', label: '新建分析', icon: '+' },
  { to: '/runs/job_8f21', label: 'Agent Run', icon: '◌' },
  { to: '/evidence', label: '证据浏览器', icon: '⌁' },
  { to: '/reviews', label: '复核工作台', icon: '✓' },
  { to: '/results', label: '结果与问答', icon: '⌘' },
  { to: '/knowledge', label: '知识库', icon: '▤' },
  { to: '/evaluation', label: '评测中心', icon: '◈' },
  { to: '/settings', label: '设置与模型能力', icon: '⚙' },
] as const

/** 根据路径推断面包屑标题。 */
export function breadcrumbTitle(pathname: string): string {
  if (pathname.startsWith('/new')) return '新建分析'
  if (pathname.startsWith('/runs')) return 'Agent Run 详情'
  if (pathname.startsWith('/evidence')) return '证据浏览器'
  if (pathname.startsWith('/reviews')) return '复核工作台'
  if (pathname.startsWith('/results')) return '结果与问答'
  if (pathname.startsWith('/knowledge')) return '知识库'
  if (pathname.startsWith('/evaluation')) return '评测中心'
  if (pathname.startsWith('/settings')) return '设置与模型能力'
  return '任务中心'
}
