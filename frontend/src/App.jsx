import { useState, useRef, useCallback } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './contexts/AuthContext.jsx'
import SkyBackground from './features/sky/SkyBackground.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import Dock from './features/dock/Dock.jsx'
import TradesWindow from './features/window/TradesWindow.jsx'
import ChatWindow from './features/window/ChatWindow.jsx'
import PortfolioWindow from './features/window/PortfolioWindow.jsx'
import SettingsWindow from './features/window/SettingsWindow.jsx'
import CornerLauncher from './components/CornerLauncher.jsx'
import { SnapProvider } from './contexts/SnapContext.jsx'
import SnapPreview from './components/SnapPreview.jsx'
import SnapSeams from './components/SnapSeams.jsx'
import SnapLayoutBar from './components/SnapLayoutBar.jsx'
import LoginPage from './pages/LoginPage.jsx'
import RegisterPage from './pages/RegisterPage.jsx'
import LandingPage from './pages/LandingPage.jsx'
import CreditsPage from './pages/CreditsPage.jsx'

/** Cascade offset (px) — each newly opened window shifts by this amount */
const CASCADE_OFFSET = 30

/**
 * App — root component that orchestrates the sky background, theme toggle,
 * navigation dock, and any open section windows.
 *
 * Supports multiple simultaneous windows with:
 *   - Independent open/close via Dock toggle or window X button
 *   - Cascaded initial positioning so windows don't stack directly on top of each other
 *   - Bring-to-front on click (managed via a z-order array)
 *   - Lego-style window snapping: edge detection, ghost preview, group drag,
 *     linked resize, and double-click seam unmerge (via SnapProvider)
 *
 * @returns {JSX.Element}
 */
function App() {
  /* Auth context — used to guard the dashboard route */
  const { user } = useAuth()

  /* Set of currently open section keys (e.g. "trades", "chats") */
  const [openSections, setOpenSections] = useState(new Set())

  /* Ordered array of open keys — last element is the topmost window */
  const [zOrder, setZOrder] = useState([])

  /* Stores the cascade position assigned to each key when it was opened.
     Keyed by section key, value is { x, y }. Cleaned up on close. */
  const cascadeRef = useRef({})

  /**
   * handleNavigate — toggle a section open or closed.
   * Called from the Dock when a nav button is clicked.
   *
   * If the section is already open it is closed (removed from openSections,
   * zOrder, and cascadeRef). If closed it is opened with a cascaded position
   * offset based on how many windows are currently open.
   *
   * @param {string} key  Section key to toggle
   */
  const handleNavigate = useCallback((key) => {
    setOpenSections(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        /* Close: remove from all tracking structures */
        next.delete(key)
        delete cascadeRef.current[key]
        setZOrder(z => z.filter(k => k !== key))
      } else {
        /* Open: compute cascade offset and add to tracking */
        const count = next.size
        const baseX = window.innerWidth / 2 - 220
        const baseY = window.innerHeight / 2 - 250
        cascadeRef.current[key] = {
          x: baseX + count * CASCADE_OFFSET,
          y: baseY + count * CASCADE_OFFSET,
        }
        next.add(key)
        setZOrder(z => [...z, key])
      }
      return next
    })
  }, [])

  /**
   * clearAll — close every open window at once.
   * Resets openSections to empty, clears the z-order stack,
   * and wipes all stored cascade positions.
   */
  const clearAll = useCallback(() => {
    setOpenSections(new Set())
    setZOrder([])
    cascadeRef.current = {}
  }, [])

  /**
   * closeSection — close a single section window (used by window X buttons).
   * Removes the key from openSections, zOrder, and cascadeRef.
   *
   * @param {string} key  Section key to close
   */
  const closeSection = useCallback((key) => {
    setOpenSections(prev => {
      const next = new Set(prev)
      next.delete(key)
      return next
    })
    delete cascadeRef.current[key]
    setZOrder(z => z.filter(k => k !== key))
  }, [])

  /**
   * bringToFront — move a window to the top of the z-order stack.
   * Called on mousedown anywhere on the window.
   * No-ops if the key is already the topmost window.
   *
   * @param {string} key  Section key to bring to front
   */
  const bringToFront = useCallback((key) => {
    setZOrder(prev => {
      if (prev[prev.length - 1] === key) return prev
      return [...prev.filter(k => k !== key), key]
    })
  }, [])

  /**
   * getZIndex — compute the inline z-index for a given section key.
   * Base z-index is 300 (above the Dock at 200); position in zOrder
   * array adds an offset so the topmost window has the highest z-index.
   *
   * @param {string} key  Section key
   * @returns {number}    z-index value
   */
  const getZIndex = useCallback((key) => {
    return 300 + zOrder.indexOf(key)
  }, [zOrder])

  return (
    <Routes>
      {/* ── Landing Page (default route) ──
          Entry point with the tree scene, nest, and clickable eggs */}
      <Route path="/" element={<LandingPage />} />

      {/* ── Auth Routes ── */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* ── Credits Route ── */}
      <Route path="/credits" element={<CreditsPage />} />

      {/* ── Dashboard App Route ──
          Guarded: redirects to / (landing) if the user is not authenticated.
          Contains the full desktop environment: sky, dock, windows, etc. */}
      <Route path="/app" element={
        !user ? <Navigate to="/" replace /> :
        <>
          <SkyBackground />
          <ThemeToggle />
          {/* Cloud-shaped navigation dock — fixed to bottom center of viewport */}
          <Dock openSections={openSections} onNavigate={handleNavigate} />

          {/* ── Corner Launchers ──
              Two expandable quick-access menus in the bottom-left and bottom-right
              corners. They mirror the Dock's 5 nav buttons plus a "Clear All" action
              for faster access without moving the cursor to the central Dock. */}
          <CornerLauncher
            position="left"
            openSections={openSections}
            onNavigate={handleNavigate}
            onClearAll={clearAll}
          />
          <CornerLauncher
            position="right"
            openSections={openSections}
            onNavigate={handleNavigate}
            onClearAll={clearAll}
          />

          {/* SnapProvider wraps all windows and overlay components so they
              share the same snap state (bonds, snap preview, window registry) */}
          <SnapProvider>
            {/* ── Section Windows ──
                Conditionally render each open window. Each receives windowId,
                onClose, onFocus (bring-to-front), zIndex, and a cascaded initialPosition. */}
            {openSections.has('trades') && (
              <TradesWindow
                windowId="trades"
                onClose={() => closeSection('trades')}
                onFocus={() => bringToFront('trades')}
                zIndex={getZIndex('trades')}
                initialPosition={cascadeRef.current['trades']}
              />
            )}

            {/* Chat window — purple-themed AI chat interface */}
            {openSections.has('chats') && (
              <ChatWindow
                windowId="chats"
                onClose={() => closeSection('chats')}
                onFocus={() => bringToFront('chats')}
                zIndex={getZIndex('chats')}
                initialPosition={cascadeRef.current['chats']}
              />
            )}

            {/* Portfolio window — yellow/cream-themed portfolio overview */}
            {openSections.has('portfolio') && (
              <PortfolioWindow
                windowId="portfolio"
                onClose={() => closeSection('portfolio')}
                onFocus={() => bringToFront('portfolio')}
                zIndex={getZIndex('portfolio')}
                initialPosition={cascadeRef.current['portfolio']}
              />
            )}

            {/* Settings window — lavender-themed settings panel */}
            {openSections.has('settings') && (
              <SettingsWindow
                windowId="settings"
                onClose={() => closeSection('settings')}
                onFocus={() => bringToFront('settings')}
                zIndex={getZIndex('settings')}
                initialPosition={cascadeRef.current['settings']}
              />
            )}

            {/* ── Snap Overlays ──
                Preview ghost rectangle appears during drag when near another window's edge.
                Seams render along bonded edges with double-click-to-unmerge.
                Layout bar slides down from top when dragging a window near the top edge. */}
            <SnapPreview />
            <SnapSeams />
            <SnapLayoutBar />
          </SnapProvider>
        </>
      } />
    </Routes>
  )
}

export default App
