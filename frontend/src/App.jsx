import SkyBackground from './features/sky/SkyBackground.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import Dock from './features/dock/Dock.jsx'

function App() {
  return (
    <>
      <SkyBackground />
      <ThemeToggle />
      <div style={{ position: 'relative', zIndex: 1 }}>
        Canary AI
      </div>
      {/* Cloud-shaped navigation dock — fixed to bottom center of viewport */}
      <Dock />
    </>
  )
}

export default App
