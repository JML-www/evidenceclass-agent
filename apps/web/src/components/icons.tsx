/**
 * 线性图标集
 *
 * 全部为 24×24 viewBox 的内联 SVG，`stroke="currentColor"`，随文字颜色继承。
 * 统一 stroke-width 1.6、圆角端点 —— 旧版的 Unicode 字符图标（▦ ◌ ⌁ ✓ ⌘ ▤ ◈ ⚙ ☰ ♢）
 * 会随字体渲染成不同粗细与字面宽度，这是界面显得廉价的直接原因之一。
 */

import React from 'react'

export type IconProps = {
  size?: number
  className?: string
  'aria-hidden'?: boolean
}

function Svg({
  size = 18,
  className,
  children,
  ...rest
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={rest['aria-hidden'] ?? true}
      focusable="false"
    >
      {children}
    </svg>
  )
}

/* ---------- 导航 ---------- */

export const IconTasks = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2.5" />
    <path d="M3 9.5h18M9 9.5V20" />
  </Svg>
)

export const IconNew = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
)

export const IconRun = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Svg>
)

export const IconEvidence = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 8.5 12 4l8 4.5-8 4.5-8-4.5Z" />
    <path d="m4 13 8 4.5 8-4.5" />
  </Svg>
)

export const IconReview = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 11.5l2 2 4-4.5" />
    <rect x="3.5" y="4" width="17" height="16" rx="2.5" />
  </Svg>
)

export const IconResults = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20.5 12a8.5 8.5 0 0 1-11.9 7.8L4 21l1.2-4.6A8.5 8.5 0 1 1 20.5 12Z" />
  </Svg>
)

export const IconKnowledge = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 4.5h9.5L19 9v10.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-14a1 1 0 0 1 1-1Z" />
    <path d="M14 4.5V9h4.5M8 13h7M8 16.5h4.5" />
  </Svg>
)

export const IconEvaluation = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 19V5M4 19h16" />
    <path d="M8 19v-5.5M12 19V9M16 19v-8" />
  </Svg>
)

export const IconSettings = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 14.6a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7h-.2a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1v-.2a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.8 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.2a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z" />
  </Svg>
)

/* ---------- 通用 UI ---------- */

export const IconMenu = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
)

export const IconBell = (p: IconProps) => (
  <Svg {...p}>
    <path d="M18 8.5a6 6 0 1 0-12 0c0 4.5-1.5 5.5-1.5 5.5h15S18 13 18 8.5Z" />
    <path d="M13.7 18a2 2 0 0 1-3.4 0" />
  </Svg>
)

export const IconSun = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8" />
  </Svg>
)

export const IconMoon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5Z" />
  </Svg>
)

export const IconChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 9.5 6 6 6-6" />
  </Svg>
)

export const IconChevronRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="m9.5 6 6 6-6 6" />
  </Svg>
)

export const IconCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Svg>
)

export const IconCheckCircle = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="m8.5 12.2 2.3 2.3 4.7-4.9" />
  </Svg>
)

export const IconAlert = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 8v4.5M12 16h.01" />
  </Svg>
)

export const IconInfo = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5M12 8h.01" />
  </Svg>
)

export const IconX = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
  </Svg>
)

export const IconUpload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 16V5M8 8.5 12 4.5l4 4" />
    <path d="M4.5 15v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3" />
  </Svg>
)

export const IconSend = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 4 3.5 10.5l6.2 2.3 2.3 6.2L20 4Z" />
    <path d="m9.7 12.8 4.3-4.3" />
  </Svg>
)

export const IconSearch = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4 4" />
  </Svg>
)

export const IconFilter = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 6h16l-6.2 7.3V19l-3.6-2v-3.7L4 6Z" />
  </Svg>
)

export const IconMore = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="5.5" cy="12" r="1.3" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
    <circle cx="18.5" cy="12" r="1.3" fill="currentColor" stroke="none" />
  </Svg>
)

export const IconShield = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3.5 19 6v6c0 4-3 7.2-7 8.5-4-1.3-7-4.5-7-8.5V6l7-2.5Z" />
    <path d="m9.2 12 1.8 1.8 3.8-3.9" />
  </Svg>
)

export const IconLock = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4.5" y="10.5" width="15" height="9.5" rx="2" />
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
  </Svg>
)

export const IconPlay = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4.5 19 12 7 19.5v-15Z" />
  </Svg>
)

export const IconImage = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
    <circle cx="9" cy="10" r="1.6" />
    <path d="m5 17 4.8-4.4a1.5 1.5 0 0 1 2 0L17 17" />
  </Svg>
)

export const IconVideo = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.5" y="6" width="12.5" height="12" rx="2.5" />
    <path d="m16 11 4.5-2.8v7.6L16 13" />
  </Svg>
)

export const IconLayers = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 9 12 5l8 4-8 4-8-4Z" />
    <path d="m4 14 8 4 8-4" />
  </Svg>
)

export const IconFileText = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 3.5h7.5L18.5 8.5V20a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z" />
    <path d="M13.5 3.5v5h5M8.5 13h6M8.5 16.5h4" />
  </Svg>
)

export const IconThumbsUp = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 10.5V19.5" />
    <path d="M4.5 10.5h2.5v9H4.5a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z" />
    <path d="M7 19.5h9.3a1.8 1.8 0 0 0 1.8-1.5l1-6a1.5 1.5 0 0 0-1.5-1.7H13V6a2.5 2.5 0 0 0-2.5-2.5L7 11" />
  </Svg>
)

export const IconThumbsDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 13.5V4.5" />
    <path d="M4.5 13.5h2.5v-9H4.5a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1Z" />
    <path d="M7 4.5h9.3a1.8 1.8 0 0 1 1.8 1.5l1 6a1.5 1.5 0 0 1-1.5 1.7H13V18a2.5 2.5 0 0 1-2.5 2.5L7 13" />
  </Svg>
)

export const IconSort = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4.5v15M7 19.5 4 16.5M7 19.5l3-3" />
    <path d="M17 19.5v-15M17 4.5l-3 3M17 4.5l3 3" />
  </Svg>
)

export const IconDownload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 4v11M8.5 11.5 12 15l3.5-3.5" />
    <path d="M4.5 15v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3" />
  </Svg>
)

export const IconExternal = (p: IconProps) => (
  <Svg {...p}>
    <path d="M13.5 4.5H19v5.5M19 4.5 11 12.5" />
    <path d="M18 14.5V19a1 1 0 0 1-1 1H5.5a1 1 0 0 1-1-1V7.5a1 1 0 0 1 1-1H10" />
  </Svg>
)

export const IconInbox = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 13.5 6 5.5h12l2 8v4a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5v-4Z" />
    <path d="M4 13.5h4l1 2h6l1-2h4" />
  </Svg>
)

export const IconRefresh = (p: IconProps) => (
  <Svg {...p}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" />
    <path d="M19.5 5v4h-4" />
  </Svg>
)
