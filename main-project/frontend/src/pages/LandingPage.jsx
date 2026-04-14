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

/* ── Asset imports: Tree trunk (grass is pure CSS, no image needed) ── */
import treeWood from '../assets/landing_page/tree_wood.png'

/* ── Grass blade definitions ──
   Three layers of blades (back/mid/front) with increasing density.
   Each entry: [leftPercent, height, width, rotationDeg, color].
   Blades are rendered as pointed SVG leaf shapes that poke above the
   green section's top edge. */
const GRASS_COLORS = {
  back:  ['#1a4210', '#1b4511', '#1c4812'],
  mid:   ['#1e4a10', '#206010', '#236012'],
  front: ['#266815', '#2a6418', '#2d5a1b'],
}

/**
 * generateBlades — creates a dense array of blade definitions for one layer.
 * @param {number} count       - how many blades to generate
 * @param {number[]} hRange    - [minHeight, maxHeight] in px
 * @param {number[]} wRange    - [minWidth, maxWidth] in px
 * @param {string[]} colors    - palette to pick from
 * @param {number} maxRot      - max absolute rotation in degrees
 * @returns {{ left: number, h: number, w: number, rot: number, fill: string, swayDur: number, swayDelay: number }[]}
 */
function generateBlades(count, hRange, wRange, colors, maxRot) {
  const blades = []
  for (let i = 0; i < count; i++) {
    /* Spread blades evenly with a small random jitter so they don't line up */
    const base = (i / count) * 100
    const jitter = (Math.sin(i * 73.7 + 13) * 0.5 + 0.5) * (100 / count) * 0.6
    const left = base + jitter

    /* Deterministic pseudo-random using sin to avoid Math.random (keeps SSR-safe) */
    const seed1 = Math.sin(i * 127.1 + 7) * 0.5 + 0.5
    const seed2 = Math.sin(i * 269.3 + 31) * 0.5 + 0.5
    const seed3 = Math.sin(i * 419.7 + 53) * 0.5 + 0.5

    const h = hRange[0] + seed1 * (hRange[1] - hRange[0])
    const w = wRange[0] + seed2 * (wRange[1] - wRange[0])
    const rot = (seed3 - 0.5) * 2 * maxRot
    const fill = colors[Math.floor(seed1 * colors.length) % colors.length]
    /* Each blade gets a slightly different sway speed and start offset */
    const swayDur = 2.5 + seed2 * 2.5          // 2.5–5s
    const swayDelay = seed3 * -5                // 0 to -5s (negative = pre-started)

    blades.push({ left, h, w, rot, fill, swayDur, swayDelay })
  }
  return blades
}

/* Pre-compute blade arrays once (outside component to avoid re-creation) */
const BACK_BLADES  = generateBlades(50, [36, 56], [9, 12], GRASS_COLORS.back, 6)
const MID_BLADES   = generateBlades(55, [24, 40], [7, 10], GRASS_COLORS.mid, 5)
const FRONT_BLADES = generateBlades(60, [14, 28], [5, 8],  GRASS_COLORS.front, 4)
const ALL_BLADES   = [...BACK_BLADES, ...MID_BLADES, ...FRONT_BLADES]

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
        <div className="landing-nest-container">
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
              <img src={loginTopcrack} alt="" className="crack-bottom" draggable={false} />
              <img src={loginCanary} alt="" className="crack-canary" draggable={false} />
              <img src={loginBottomcrack} alt="" className="crack-top" draggable={false} />
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
              <img src={loginTopcrack} alt="" className="crack-bottom" draggable={false} />
              <img src={loginCanary} alt="" className="crack-canary" draggable={false} />
              <img src={loginBottomcrack} alt="" className="crack-top" draggable={false} />
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
              <img src={loginTopcrack} alt="" className="crack-bottom" draggable={false} />
              <img src={loginCanary} alt="" className="crack-canary" draggable={false} />
              <img src={loginBottomcrack} alt="" className="crack-top" draggable={false} />
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
          Pure CSS grass — 3-layer SVG bumps tiling horizontally over
          the green section background. No image asset needed. */}
      <section className="landing-base-section">
        {/* ── Grass Blades ──
            165 generated blades (50 back + 55 mid + 60 front) with wind sway
            animation. Each blade gets unique size, rotation, sway speed, and
            delay via CSS custom properties for natural, non-uniform movement. */}
        <div className="landing-grass-blades">
          {ALL_BLADES.map((b, i) => {
            const w = Math.round(b.w)
            const h = Math.round(b.h)
            const cx = w / 2
            return (
              <svg
                key={i}
                className="grass-blade"
                style={{
                  left: `${b.left.toFixed(1)}%`,
                  top: `${-h}px`,
                  '--base-rot': `${b.rot.toFixed(1)}deg`,
                  '--sway-duration': `${b.swayDur.toFixed(2)}s`,
                  '--sway-delay': `${b.swayDelay.toFixed(2)}s`,
                }}
                width={w}
                height={h}
                viewBox={`0 0 ${w} ${h}`}
              >
                <path
                  d={`M${cx},0 Q${cx + w * 0.2},${h * 0.4} ${w - 1},${h} L1,${h} Q${cx - w * 0.2},${h * 0.4} ${cx},0Z`}
                  fill={b.fill}
                />
              </svg>
            )
          })}
        </div>

        <div className="landing-base-grass" />

        {/* ── Ground Decorations ──
            Scattered flowers and rocks between the grass and buttons
            for depth and a cartoony nature-scene feel. */}
        <div className="landing-ground-decor">
          {/* Flower 1 — white petals, yellow center (28px) */}
          <svg className="ground-flower decor-1" width="28" height="28" viewBox="0 0 28 28">
            <ellipse cx="14" cy="7" rx="4" ry="6" fill="#fff" />
            <ellipse cx="14" cy="21" rx="4" ry="6" fill="#fff" />
            <ellipse cx="7" cy="14" rx="6" ry="4" fill="#fff" />
            <ellipse cx="21" cy="14" rx="6" ry="4" fill="#fff" />
            <ellipse cx="8" cy="8" rx="4" ry="5" fill="#fff" transform="rotate(45 8 8)" />
            <circle cx="14" cy="14" r="4" fill="#f5d442" />
          </svg>

          {/* Flower 2 — pink petals, yellow center (24px) */}
          <svg className="ground-flower decor-2" width="24" height="24" viewBox="0 0 28 28">
            <ellipse cx="14" cy="7" rx="4" ry="6" fill="#f5a0b8" />
            <ellipse cx="14" cy="21" rx="4" ry="6" fill="#f5a0b8" />
            <ellipse cx="7" cy="14" rx="6" ry="4" fill="#f5a0b8" />
            <ellipse cx="21" cy="14" rx="6" ry="4" fill="#f5a0b8" />
            <ellipse cx="20" cy="8" rx="4" ry="5" fill="#f5a0b8" transform="rotate(-45 20 8)" />
            <circle cx="14" cy="14" r="4" fill="#f5d442" />
          </svg>

          {/* Flower 3 — white petals, yellow center (20px) */}
          <svg className="ground-flower decor-3" width="20" height="20" viewBox="0 0 28 28">
            <ellipse cx="14" cy="7" rx="4" ry="6" fill="#fff" />
            <ellipse cx="14" cy="21" rx="4" ry="6" fill="#fff" />
            <ellipse cx="7" cy="14" rx="6" ry="4" fill="#fff" />
            <ellipse cx="21" cy="14" rx="6" ry="4" fill="#fff" />
            <ellipse cx="8" cy="20" rx="4" ry="5" fill="#fff" transform="rotate(-45 8 20)" />
            <circle cx="14" cy="14" r="4" fill="#f5d442" />
          </svg>

          {/* Flower 4 — pink petals, yellow center (32px) */}
          <svg className="ground-flower decor-4" width="32" height="32" viewBox="0 0 28 28">
            <ellipse cx="14" cy="7" rx="4" ry="6" fill="#f5a0b8" />
            <ellipse cx="14" cy="21" rx="4" ry="6" fill="#f5a0b8" />
            <ellipse cx="7" cy="14" rx="6" ry="4" fill="#f5a0b8" />
            <ellipse cx="21" cy="14" rx="6" ry="4" fill="#f5a0b8" />
            <ellipse cx="20" cy="20" rx="4" ry="5" fill="#f5a0b8" transform="rotate(45 20 20)" />
            <circle cx="14" cy="14" r="4" fill="#f5d442" />
          </svg>

          {/* Rock 1 — dark gray (22px) */}
          <svg className="ground-rock decor-5" width="22" height="16" viewBox="0 0 22 16">
            <ellipse cx="11" cy="10" rx="10" ry="6" fill="#6b6b6b" />
            <ellipse cx="11" cy="9" rx="9" ry="5" fill="#8a8a8a" />
            <ellipse cx="9" cy="8" rx="5" ry="3" fill="#9e9e9e" opacity="0.5" />
          </svg>

          {/* Rock 2 — brown-gray (28px) */}
          <svg className="ground-rock decor-6" width="28" height="18" viewBox="0 0 28 18">
            <ellipse cx="14" cy="12" rx="13" ry="6" fill="#7a6e5d" />
            <ellipse cx="14" cy="11" rx="11" ry="5" fill="#8f8070" />
            <ellipse cx="12" cy="10" rx="6" ry="3" fill="#a39585" opacity="0.5" />
          </svg>

          {/* Rock 3 — small gray (16px) */}
          <svg className="ground-rock decor-7" width="16" height="12" viewBox="0 0 16 12">
            <ellipse cx="8" cy="7" rx="7" ry="5" fill="#777" />
            <ellipse cx="8" cy="6" rx="6" ry="4" fill="#999" />
            <ellipse cx="7" cy="5" rx="3" ry="2" fill="#aaa" opacity="0.5" />
          </svg>
        </div>

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
