import { useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import gsap from 'gsap'
import SkyBackground from '../features/sky/SkyBackground.jsx'
import './AuthPages.css'

/**
 * CreditsPage — simple credits/attribution page rendered over the animated
 * sky background. Uses the same glassmorphic card pattern as Login/Register.
 *
 * Features:
 *   - SkyBackground behind everything
 *   - Puffy 3D back button (top-left) to return to the landing page
 *   - Glassmorphic card listing team members and attributions
 *   - GSAP pop-in card animation
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

      {/* Centered glassmorphic credits card */}
      <div className="auth-card" ref={cardRef}>
        <h1>Credits</h1>

        {/* Team members list */}
        <div className="credits-list">
          <div className="credits-item">
            <span className="credits-name">Ken Nguyen</span>
            <span className="credits-role">Frontend & Backend</span>
          </div>
          <div className="credits-item">
            <span className="credits-name">Arthur Vasilev</span>
            <span className="credits-role">Frontend & Design</span>
          </div>
          <div className="credits-item">
            <span className="credits-name">Sean Yang</span>
            <span className="credits-role">Backend & C++ Prediction</span>
          </div>
        </div>

        {/* Attribution section */}
        <div className="credits-attribution">
          <p className="credits-built">Built for UNIHACK 2026</p>
          <p className="credits-powered">Powered by Claude AI, React, FastAPI & Supabase</p>
        </div>
      </div>
    </div>
  )
}

export default CreditsPage
