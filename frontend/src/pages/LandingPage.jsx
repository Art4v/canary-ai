import { useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import gsap from 'gsap'
import SkyBackground from '../features/sky/SkyBackground.jsx'
import './LandingPage.css'

/* ── Asset imports: Single nest composite (all eggs + nest in one image) ── */
import nestComposite from '../assets/landing_page/nest/eggs.png'

/* ── Asset imports: Cracked egg overlays (reused for all 3 eggs) ── */
import loginCanary from '../assets/landing_page/nest/cracked_eggs/login_canary.png'
import loginTopcrack from '../assets/landing_page/nest/cracked_eggs/login_topcrack.png'
import loginBottomcrack from '../assets/landing_page/nest/cracked_eggs/login_bottomcrack.png'

/* ── Asset imports: Tree trunk + base ── */
import treeWood from '../assets/landing_page/tree_wood.png'
import treeBottom from '../assets/landing_page/tree_bottom.png'

/**
 * LandingPage — full-page vertically scrollable tree scene that serves as
 * the app's entry point before login/register.
 *
 * Layout (top to bottom):
 *   A) Sky + Nest  — "Canary AI" title, single nest composite with 3 clickable egg zones
 *   B) Tree trunk  — seamlessly repeating bark texture
 *   C) Tree base   — trunk meeting grass (full-width repeat-x) + Login/Register buttons
 *
 * Each egg zone reveals a cracked canary mascot on hover with a text label.
 * Clicking an egg navigates to /login, /register, or /credits.
 *
 * @returns {JSX.Element}
 */
function LandingPage() {
  const navigate = useNavigate()

  /* Refs for GSAP entrance animations */
  const titleRef = useRef(null)
  const nestRef = useRef(null)
  const bottomBtnsRef = useRef(null)

  /* ── GSAP Entrance Animations ──
     Title drops in from above, nest scales up with a bounce,
     bottom buttons fade in from below. */
  useEffect(() => {
    /* Title drops in */
    if (titleRef.current) {
      gsap.fromTo(
        titleRef.current,
        { y: -60, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.8, ease: 'back.out(1.7)', delay: 0.2 }
      )
    }

    /* Nest pops in with scale bounce */
    if (nestRef.current) {
      gsap.fromTo(
        nestRef.current,
        { scale: 0.7, opacity: 0 },
        { scale: 1, opacity: 1, duration: 0.7, ease: 'back.out(1.7)', delay: 0.5 }
      )
    }

    /* Bottom buttons slide up */
    if (bottomBtnsRef.current) {
      gsap.fromTo(
        bottomBtnsRef.current,
        { y: 40, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.6, ease: 'power2.out', delay: 0.8 }
      )
    }
  }, [])

  return (
    <div className="landing-page">
      {/* Animated sky behind the entire scene */}
      <SkyBackground />

      {/* ═══ Section A: Sky + Nest ═══
          Full viewport height section with the title and nest composite */}
      <section className="landing-nest-section">
        {/* App title */}
        <h1 className="landing-title" ref={titleRef}>Canary AI</h1>

        {/* Nest container — single composite image with invisible egg hover zones.
            The composite image (eggs.png) contains the full nest scene including eggs.
            Egg buttons sit on top as invisible hit areas that show cracked overlays on hover. */}
        <div className="landing-nest-container" ref={nestRef}>
          {/* Single composite nest image — contains nest, leaves, and all eggs */}
          <img
            src={nestComposite}
            alt="Nest with eggs"
            className="nest-composite"
            draggable={false}
          />

          {/* ── Egg Buttons ──
              Each egg is an invisible button zone positioned over the corresponding
              egg in the composite image. On hover, a cracked canary overlay appears. */}

          {/* Login egg — positioned left */}
          <button
            className="egg-btn egg-login"
            onClick={() => navigate('/login')}
            aria-label="Login"
          >
            {/* Cracked overlay — shown on hover */}
            <div className="egg-cracked">
              <img src={loginBottomcrack} alt="" className="crack-bottom" draggable={false} />
              <img src={loginCanary} alt="" className="crack-canary" draggable={false} />
              <img src={loginTopcrack} alt="" className="crack-top" draggable={false} />
              <span className="egg-label">Login</span>
            </div>
          </button>

          {/* Signup egg — positioned center */}
          <button
            className="egg-btn egg-signup"
            onClick={() => navigate('/register')}
            aria-label="Sign Up"
          >
            <div className="egg-cracked">
              <img src={loginBottomcrack} alt="" className="crack-bottom" draggable={false} />
              <img src={loginCanary} alt="" className="crack-canary" draggable={false} />
              <img src={loginTopcrack} alt="" className="crack-top" draggable={false} />
              <span className="egg-label">Sign Up</span>
            </div>
          </button>

          {/* Credits egg — positioned right */}
          <button
            className="egg-btn egg-credits"
            onClick={() => navigate('/credits')}
            aria-label="Credits"
          >
            <div className="egg-cracked">
              <img src={loginBottomcrack} alt="" className="crack-bottom" draggable={false} />
              <img src={loginCanary} alt="" className="crack-canary" draggable={false} />
              <img src={loginTopcrack} alt="" className="crack-top" draggable={false} />
              <span className="egg-label">Credits</span>
            </div>
          </button>
        </div>
      </section>

      {/* ═══ Section B: Tree Trunk ═══
          Fixed-width column with vertically repeating bark texture.
          Creates the illusion of a tall tree between the nest and base. */}
      <section className="landing-trunk-section">
        <div
          className="landing-trunk"
          style={{ backgroundImage: `url(${treeWood})` }}
        />
      </section>

      {/* ═══ Section C: Tree Base + Grass ═══
          Full-width grass using repeat-x tiling of tree_bottom.png over a
          green background, so grass fills to both screen edges. */}
      <section className="landing-base-section">
        <div
          className="landing-base-grass"
          style={{ backgroundImage: `url(${treeBottom})` }}
        />

        {/* Action buttons at the bottom — puffy 3D style matching auth pages */}
        <div className="landing-bottom-buttons" ref={bottomBtnsRef}>
          <button
            className="landing-btn landing-btn-login"
            onClick={() => navigate('/login')}
          >
            Login
          </button>
          <button
            className="landing-btn landing-btn-register"
            onClick={() => navigate('/register')}
          >
            Register
          </button>
        </div>
      </section>
    </div>
  )
}

export default LandingPage
