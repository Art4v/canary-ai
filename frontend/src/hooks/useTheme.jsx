import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'

const ThemeContext = createContext()

const CYCLE = ['auto', 'night', 'day']

function isAESTDaytime() {
  const now = new Date()
  // AEST = UTC+10 (ignoring daylight saving for simplicity, AEST is +10)
  const aestHour = (now.getUTCHours() + 10) % 24
  return aestHour >= 10 && aestHour < 16
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState('auto')

  const isDark = useMemo(() => {
    if (mode === 'day') return false
    if (mode === 'night') return true
    return !isAESTDaytime()
  }, [mode])

  // Re-evaluate auto mode every 60s
  const [, setTick] = useState(0)
  useEffect(() => {
    if (mode !== 'auto') return
    const id = setInterval(() => setTick(t => t + 1), 60_000)
    return () => clearInterval(id)
  }, [mode])

  // Apply .night class to body
  useEffect(() => {
    document.body.classList.toggle('night', isDark)
  }, [isDark])

  const cycleMode = useCallback(() => {
    setMode(prev => CYCLE[(CYCLE.indexOf(prev) + 1) % CYCLE.length])
  }, [])

  const value = useMemo(() => ({ mode, isDark, cycleMode }), [mode, isDark, cycleMode])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
