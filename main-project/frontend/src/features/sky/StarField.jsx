import { useMemo } from 'react'
import { useTheme } from '../../hooks/useTheme.jsx'
import './StarField.css'

function seededRandom(seed) {
  let s = seed
  return () => {
    s = (s * 16807 + 0) % 2147483647
    return s / 2147483647
  }
}

export default function StarField() {
  const { isDark } = useTheme()

  const stars = useMemo(() => {
    const rand = seededRandom(42)
    return Array.from({ length: 60 }, (_, i) => ({
      id: i,
      left: rand() * 100,
      top: rand() * 70,
      size: 1 + rand() * 2.5,
      delay: rand() * 5,
      duration: 2 + rand() * 3,
    }))
  }, [])

  return (
    <div className="star-field" style={{ opacity: isDark ? 1 : 0 }}>
      {stars.map(s => (
        <div
          key={s.id}
          className="star"
          style={{
            left: `${s.left}%`,
            top: `${s.top}%`,
            width: `${s.size}px`,
            height: `${s.size}px`,
            '--delay': `${s.delay}s`,
            '--duration': `${s.duration}s`,
          }}
        />
      ))}
    </div>
  )
}
