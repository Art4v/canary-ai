import SkyBackground from './features/sky/SkyBackground.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'

function App() {
  return (
    <>
      <SkyBackground />
      <ThemeToggle />
      <div style={{ position: 'relative', zIndex: 1 }}>
        Canary AI
      </div>
    </>
  )
}

export default App
