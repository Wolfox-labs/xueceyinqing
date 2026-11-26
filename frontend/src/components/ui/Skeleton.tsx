/**
 * 加载骨架屏。
 *
 * 为什么需要：原先各页加载时要么是一行"正在加载…"文字、要么是一个居中的转圈，
 * 版面高度从 0 突然撑开，观感上像"卡住了"。骨架屏先把版面占住，
 * 数据到位后原位替换，不发生跳动。
 *
 * 注意：骨架只用于**等待内容**的场景。像"提交中"这种等待动作本身的状态，
 * 仍然用文字+转圈更合适（用户需要知道是在等一个动作，而不是在看内容）。
 */

/** 骨架基础块。 */
export function SkeletonBar({
  width = '100%',
  height = 12,
  className = '',
}: {
  width?: string
  height?: number
  className?: string
}) {
  return (
    <span
      className={className ? `skeleton ${className}` : 'skeleton'}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}

/** 面板形状的骨架：标题条 + 若干行。 */
export function SkeletonPanel({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-panel">
      <SkeletonBar width="34%" height={14} />
      <div className="skeleton-panel__lines">
        {Array.from({ length: lines }, (_, index) => (
          <SkeletonBar key={index} width={`${100 - index * 14}%`} />
        ))}
      </div>
    </div>
  )
}

/** 整页骨架：与 core-page 同构，数据到位后原位替换。 */
export default function SkeletonPage({ panels = 3 }: { panels?: number }) {
  return (
    <div className="core-page" aria-busy="true">
      <div className="skeleton-head">
        <SkeletonBar width="180px" height={26} />
        <SkeletonBar width="320px" height={12} />
      </div>
      <div className="skeleton-grid">
        {Array.from({ length: panels }, (_, index) => (
          <SkeletonPanel key={index} />
        ))}
      </div>
      {/* 视觉上是骨架，但读屏用户需要一句话说明正在加载 */}
      <span className="skeleton-sr" role="status">正在加载…</span>
    </div>
  )
}