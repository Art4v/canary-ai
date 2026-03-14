import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import gsap from 'gsap'
import SkyBackground from '../features/sky/SkyBackground.jsx'
import './AuthPages.css'

/**
 * LoginPage — full-page login form rendered over the animated sky background.
 *
 * Features:
 *   - Glassmorphic card with GSAP pop-in animation (scale 0.8→1, opacity 0→1)
 *   - Puffy 3D back button (top-left) navigating to the previous page
 *   - Email + password fields with stub submit (console.log + redirect to dashboard)
 *   - Footer link to the register page
 *
 * @returns {JSX.Element}
 */
function LoginPage() {
  /* Form state for email and password fields */
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  /* Ref to the card element for GSAP entrance animation */
  const cardRef = useRef(null)

  /* React Router navigation hook */
  const navigate = useNavigate()

  /* ── GSAP Card Entrance Animation ──
     Scales the card from 0.8→1 and fades opacity 0→1
     using a back.out ease for a playful overshoot effect. */
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
   * handleSubmit — stub form handler.
   * Logs the email and password to the console and
   * navigates to the dashboard route.
   *
   * @param {React.FormEvent} e  Form submit event
   */
  const handleSubmit = (e) => {
    e.preventDefault()
    console.log('Login submitted:', { email, password })
    navigate('/')
  }

  /**
   * handleBack — navigate back to the previous page.
   * Falls back to the dashboard if there is no history.
   */
  const handleBack = () => {
    navigate(-1)
  }

  return (
    <div className="auth-page">
      {/* Animated sky behind everything */}
      <SkyBackground />

      {/* Top-left back arrow — puffy 3D circle */}
      <button className="auth-back-btn" onClick={handleBack} aria-label="Go back">
        <ArrowLeft size={20} />
      </button>

      {/* Centered glassmorphic login card */}
      <div className="auth-card" ref={cardRef}>
        <h1>Login</h1>

        <form className="auth-form" onSubmit={handleSubmit}>
          {/* Email field */}
          <div className="auth-field">
            <label className="auth-label" htmlFor="login-email">Email</label>
            <input
              id="login-email"
              className="auth-input"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>

          {/* Password field */}
          <div className="auth-field">
            <label className="auth-label" htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="auth-input"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {/* Submit button — puffy 3D accent-colored */}
          <button type="submit" className="auth-submit-btn">Login</button>
        </form>

        {/* Footer link to register page */}
        <p className="auth-footer">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="auth-link">Register</Link>
        </p>
      </div>
    </div>
  )
}

export default LoginPage
