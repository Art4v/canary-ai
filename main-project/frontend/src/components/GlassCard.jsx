export default function GlassCard({ children, className, style, padding = '20px' }) {
  return (
    <div
      className={`glass-card${className ? ` ${className}` : ''}`}
      style={{ padding, ...style }}
    >
      {children}
    </div>
  )
}
