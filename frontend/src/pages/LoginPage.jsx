import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import gsap from 'gsap'
import { useAuth } from '../contexts/AuthContext.jsx'
import SkyBackground from '../features/sky/SkyBackground.jsx'
import './AuthPages.css'

/**
 * LoginPage — full-page login form rendered over the animated sky background.
 *
 * Features:
 *   - Glassmorphic card with GSAP pop-in animation (scale 0.8→1, opacity 0→1)
 *   - Puffy 3D back button (top-left) navigating to the previous page
 *   - Email + password fields that POST to /database/users/login for verification
 *   - On success, redirects to the dashboard
 *   - Footer link to the register page
 *
 * @returns {JSX.Element}
 */
function LoginPage() {
  /* Form state for email and password fields */
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  /* Validation / server error message shown below the form */
  const [error, setError] = useState('')

  /* Loading state — disables the submit button while the request is in flight */
  const [loading, setLoading] = useState(false)

  /* Ref to the card element for GSAP entrance animation */
  const cardRef = useRef(null)

  /* React Router navigation hook */
  const navigate = useNavigate()

  /* Auth context — login() persists user data to state + localStorage */
  const { login } = useAuth()

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
   * handleSubmit — sends login credentials to the backend for verification.
   *
   * 1. POSTs { email, password } to /database/users/login
   * 2. The backend looks up the user by email and verifies the password
   *    against the stored bcrypt hash
   * 3. On success, navigates to the dashboard
   * 4. On error, displays the server error message in the form
   *
   * @param {React.FormEvent} e  Form submit event
   */
  const handleSubmit = async (e) => {
    e.preventDefault()

    /* Clear any previous error and enter loading state */
    setError('')
    setLoading(true)

    try {
      /* POST login credentials to the backend login endpoint.
         Uses a relative URL — same origin as the SPA. */
      const res = await fetch('/database/users/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      /* Parse the JSON envelope { success, data?, error? } */
      const result = await res.json()

      if (result.success) {
        /* Login succeeded — persist user data in AuthContext and redirect */
        login(result.data)
        navigate('/')
      } else {
        /* Show the server-provided error (e.g. invalid credentials) */
        setError(result.error || 'Login failed. Please try again.')
      }
    } catch (err) {
      /* Network error or server unreachable */
      setError('Unable to connect to the server. Please try again later.')
    } finally {
      /* Always re-enable the submit button */
      setLoading(false)
    }
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

          {/* Error message (e.g. invalid credentials, server error) */}
          {error && <p className="auth-error">{error}</p>}

          {/* Submit button — disabled while request is in flight */}
          <button type="submit" className="auth-submit-btn" disabled={loading}>
            {loading ? 'Logging in…' : 'Login'}
          </button>
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
