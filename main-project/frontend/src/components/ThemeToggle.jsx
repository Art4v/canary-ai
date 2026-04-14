import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme } from '../hooks/useTheme.jsx'
import './ThemeToggle.css'

const ICONS = {
  day: { Icon: Sun, label: 'Day' },
  night: { Icon: Moon, label: 'Night' },
  auto: { Icon: Monitor, label: 'Auto' },
}

export default function ThemeToggle() {
  const { mode, cycleMode } = useTheme()
  const { Icon, label } = ICONS[mode]

  return (
    <button className="glass-card theme-toggle" onClick={cycleMode}>
      <span className="theme-toggle-icon" key={mode}>
        <Icon size={16} />
      </span>
      {label}
    </button>
  )
}
