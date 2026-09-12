import React from 'react'

/** 单行骨架（数字与中文之间留空隙的观感由容器控制）。 */
export function Skeleton({
  variant = 'line',
  width,
  height,
  className = '',
}: {
  variant?: 'line' | 'circle' | 'block'
  width?: number | string
  height?: number | string
  className?: string
}) {
  const style: React.CSSProperties = {}
  if (width) style.width = width
  if (height) style.height = height
  return (
    <span
      className={`skeleton ${variant} ${className}`}
      style={style}
      aria-hidden="true"
    />
  )
}

/** 文本段落骨架（2–4 行）。 */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-text" aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          width={index === lines - 1 ? '60%' : '100%'}
        />
      ))}
    </div>
  )
}

/** 卡片骨架，用于列表/表格加载态。 */
export function SkeletonCard({ height = 120 }: { height?: number }) {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <Skeleton width="40%" height={16} />
      <Skeleton width="100%" height={height} />
      <Skeleton width="70%" />
    </div>
  )
}
