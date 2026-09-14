import type { ComponentType } from 'react'
import {
  IconEvaluation,
  IconEvidence,
  IconKnowledge,
  IconNew,
  IconResults,
  IconReview,
  IconRun,
  IconSettings,
  IconTasks,
  type IconProps,
} from '../components/icons'
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

export type NavItem = {
  to: string
  label: string
  icon: ComponentType<IconProps>
  group: string
  /** 该前缀下的路由也算作激活（用于带参数的详情页）。 */
  match?: string
}

/** 9 个页面的导航项，按职责分组；侧边栏与面包屑共用。 */
export const navItems: readonly NavItem[] = [
  { to: '/jobs', label: '任务中心', icon: IconTasks, group: '工作台' },
  { to: '/new', label: '新建分析', icon: IconNew, group: '工作台' },
  { to: '/runs/job_8f21', label: 'Agent Run', icon: IconRun, group: '工作台', match: '/runs' },
  { to: '/evidence', label: '证据浏览器', icon: IconEvidence, group: '分析' },
  { to: '/reviews', label: '复核工作台', icon: IconReview, group: '分析' },
  { to: '/results', label: '结果与问答', icon: IconResults, group: '分析' },
  { to: '/knowledge', label: '知识库', icon: IconKnowledge, group: '系统' },
  { to: '/evaluation', label: '评测中心', icon: IconEvaluation, group: '系统' },
  { to: '/settings', label: '设置与模型能力', icon: IconSettings, group: '系统' },
]

/** 侧边栏分组顺序。 */
export const navGroups = ['工作台', '分析', '系统'] as const

/** 根据路径推断当前页面标题。 */
export function breadcrumbTitle(pathname: string): string {
  const match = [...navItems]
    .sort((a, b) => b.to.length - a.to.length)
    .find(item => pathname === item.to || (item.match && pathname.startsWith(item.match)))
  if (match) return match.label
  return '任务中心'
}
