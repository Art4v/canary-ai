import { useState } from 'react'
import SkyBackground from './features/sky/SkyBackground.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import Dock from './features/dock/Dock.jsx'
import TradesWindow from './features/window/TradesWindow.jsx'
import ChatWindow from './features/window/ChatWindow.jsx'
import PortfolioWindow from './features/window/PortfolioWindow.jsx'

/**
 * App — root component that orchestrates the sky background, theme toggle,
 * navigation dock, and any active section windows.
 *
 * Lifts `activeSection` state here so the Dock and windows stay in sync:
 * clicking a dock button opens the matching window; clicking again (or the
 * window's X) closes it.
 *
 * @returns {JSX.Element}
 */
function App() {
  /* Which section window is currently open (null = none) */
  const [activeSection, setActiveSection] = useState(null)

  return (
    <>
      <SkyBackground />
      <ThemeToggle />
      <div style={{ position: 'relative', zIndex: 1 }}>
        Canary AI
      </div>
      {/* Cloud-shaped navigation dock — fixed to bottom center of viewport */}
      <Dock activeSection={activeSection} onNavigate={setActiveSection} />

      {/* ── Section Windows ──
          Conditionally render the window for the active section.
          Each window receives an onClose that clears the active section. */}
      {activeSection === 'trades' && (
        <TradesWindow onClose={() => setActiveSection(null)} />
      )}

      {/* Chat window — purple-themed AI chat interface */}
      {activeSection === 'chats' && (
        <ChatWindow onClose={() => setActiveSection(null)} />
      )}

      {/* Portfolio window — yellow/cream-themed portfolio overview */}
      {activeSection === 'portfolio' && (
        <PortfolioWindow onClose={() => setActiveSection(null)} />
      )}
    </>
  )
}

export default App
