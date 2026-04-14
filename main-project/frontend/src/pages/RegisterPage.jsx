import { useState, useRef, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import gsap from 'gsap'
import SkyBackground from '../features/sky/SkyBackground.jsx'
import './AuthPages.css'

/**
 * RegisterPage — full-page registration form rendered over the animated sky background.
 *
 * Features:
 *   - Glassmorphic card with GSAP pop-in animation (scale 0.8→1, opacity 0→1)
 *   - Puffy 3D back button (top-left) navigating to the previous page
 *   - Username, email, password, and confirm password fields
 *   - Basic validation: passwords must match before submit
 *   - Sends POST /database/users to create the user in Supabase
 *   - On success, redirects to the login page
 *   - Footer link to the login page
 *
 * @returns {JSX.Element}
 */
function RegisterPage() {
  /* Form state for all registration fields */
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  /* Validation error message shown below the form */
  const [error, setError] = useState('')

  /* Loading state — disables the submit button while the request is in flight */
  const [loading, setLoading] = useState(false)

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
   * handleSubmit — sends registration data to the backend.
   *
   * 1. Validates that password and confirm password match
   * 2. POSTs { username, email, password } to /database/users
   * 3. The backend hashes the password with bcrypt before storing
   * 4. On success, navigates to /login so the user can sign in
   * 5. On error, displays the server error message in the form
   *
   * @param {React.FormEvent} e  Form submit event
   */
  const handleSubmit = async (e) => {
    e.preventDefault()

    /* Validate that password and confirm password fields match */
    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    /* Clear any previous error and enter loading state */
    setError('')
    setLoading(true)

    try {
      /* POST the registration payload to the backend users endpoint.
         Uses a relative URL because the React SPA is served from the
         same FastAPI origin — no CORS needed. */
      const res = await fetch('/database/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      })

      /* Parse the JSON envelope { success, data?, error? } */
      const result = await res.json()

      if (result.success) {
        /* Registration succeeded — redirect to login page */
        navigate('/login')
      } else {
        /* Show the server-provided error (e.g. duplicate username) */
        setError(result.error || 'Registration failed. Please try again.')
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

      {/* Centered glassmorphic register card */}
      <div className="auth-card" ref={cardRef}>
        <h1>Register</h1>

        <form className="auth-form" onSubmit={handleSubmit}>
          {/* Username field */}
          <div className="auth-field">
            <label className="auth-label" htmlFor="register-username">Username</label>
            <input
              id="register-username"
              className="auth-input"
              type="text"
              placeholder="Choose a username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>

          {/* Email field */}
          <div className="auth-field">
            <label className="auth-label" htmlFor="register-email">Email</label>
            <input
              id="register-email"
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
            <label className="auth-label" htmlFor="register-password">Password</label>
            <input
              id="register-password"
              className="auth-input"
              type="password"
              placeholder="Create a password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {/* Confirm password field */}
          <div className="auth-field">
            <label className="auth-label" htmlFor="register-confirm">Confirm Password</label>
            <input
              id="register-confirm"
              className="auth-input"
              type="password"
              placeholder="Confirm your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>

          {/* Validation error message (e.g. password mismatch) */}
          {error && <p className="auth-error">{error}</p>}

          {/* Submit button — disabled while request is in flight */}
          <button type="submit" className="auth-submit-btn" disabled={loading}>
            {loading ? 'Registering…' : 'Register'}
          </button>
        </form>

        {/* Footer link to login page */}
        <p className="auth-footer">
          Already have an account?{' '}
          <Link to="/login" className="auth-link">Login</Link>
        </p>
      </div>
    </div>
  )
}

export default RegisterPage
