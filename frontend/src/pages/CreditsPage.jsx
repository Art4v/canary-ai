import { useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import gsap from 'gsap'
import SkyBackground from '../features/sky/SkyBackground.jsx'
import './AuthPages.css'

/**
 * CreditsPage — credits/attribution page rendered over the animated sky
 * background. Uses the same glassmorphic card pattern as Login/Register.
 *
 * Sections:
 *   1. Team credits grouped by role (Frontend, Backend, Artwork)
 *   2. Tech stack listing all major technologies used
 *   3. Back button (top-left arrow) to return to the landing page
 *
 * @returns {JSX.Element}
 */
function CreditsPage() {
  const navigate = useNavigate()

  /* Ref for GSAP entrance animation on the card */
  const cardRef = useRef(null)

  /* ── GSAP Card Entrance Animation ──
     Scales from 0.8→1 and fades in with a bounce overshoot. */
  useEffect(() => {
    if (cardRef.current) {
      gsap.fromTo(
        cardRef.current,
        { scale: 0.8, opacity: 0 },
        { scale: 1, opacity: 1, duration: 0.5, ease: 'back.out(1.7)' }
      )
    }
  }, [])

  /**
   * handleBack — navigate back to the landing page.
   */
  const handleBack = () => {
    navigate('/')
  }

  return (
    <div className="auth-page">
      {/* Animated sky behind everything */}
      <SkyBackground />

      {/* Top-left back arrow — puffy 3D circle */}
      <button className="auth-back-btn" onClick={handleBack} aria-label="Go back">
        <ArrowLeft size={20} />
      </button>

      {/* Centered glassmorphic credits card — wider to fit tech stack table */}
      <div className="auth-card credits-card" ref={cardRef}>
        <h1>Credits</h1>

        {/* ── Team credits grouped by role ── */}
        <div className="credits-list">
          {/* Frontend section header */}
          <h2 className="credits-section-heading">Frontend</h2>
          <div className="credits-item">
            <span className="credits-name">Ken Nguyen</span>
          </div>
          <div className="credits-item">
            <span className="credits-name">Sai Prakhya</span>
          </div>

          {/* Backend section header */}
          <h2 className="credits-section-heading">Backend</h2>
          <div className="credits-item">
            <span className="credits-name">Aarav Bhatt</span>
          </div>
          <div className="credits-item">
            <span className="credits-name">Advik Sakhare</span>
          </div>

          {/* Artwork section header */}
          <h2 className="credits-section-heading">Artwork</h2>
          <div className="credits-item">
            <span className="credits-name">Helena Han</span>
          </div>
        </div>

        {/* ── Tech Stack ── */}
        <h2 className="credits-section-heading">Tech Stack</h2>
        <div className="credits-tech-stack">
          <div className="credits-tech-row">
            <span className="credits-tech-label">Frontend</span>
            <span className="credits-tech-value">React 19 + Vite 8</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Routing</span>
            <span className="credits-tech-value">React Router DOM</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Backend</span>
            <span className="credits-tech-value">FastAPI + Uvicorn</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Prediction</span>
            <span className="credits-tech-value">C++17</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Database</span>
            <span className="credits-tech-value">Supabase</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Data</span>
            <span className="credits-tech-value">yfinance, Finnhub API</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Animation</span>
            <span className="credits-tech-value">GSAP</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">Charts</span>
            <span className="credits-tech-value">Recharts</span>
          </div>
          <div className="credits-tech-row">
            <span className="credits-tech-label">AI</span>
            <span className="credits-tech-value">Anthropic SDK (Claude)</span>
          </div>
        </div>

        {/* ── Attribution footer ── */}
        <div className="credits-attribution">
          <p className="credits-built">Built for UNIHACK 2026</p>
        </div>
      </div>
    </div>
  )
}

export default CreditsPage
