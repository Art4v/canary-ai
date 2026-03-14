import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import {
  MessageCircle,
  ArrowLeftRight,
  Briefcase,
  Settings,
  CircleHelp,
} from 'lucide-react'
/* Vite asset import — resolved to a hashed URL at build time */
import logoCanary from '@/assets/logocanary.PNG'
import './Dock.css'

/**
 * NAV_ITEMS — configuration for each navigation button.
 * Order (left to right): Chat, Trades, Portfolio, Settings, Help.
 * Each entry maps a section name to its Lucide icon component
 * and the CSS custom-property prefix used for its color tokens
 * (e.g. "chats" → --color-chats-primary / dark / light).
 */
const NAV_ITEMS = [
  { key: 'chats',     label: 'Chat',      Icon: MessageCircle,  color: 'chats'     },
  { key: 'trades',    label: 'Trades',    Icon: ArrowLeftRight,  color: 'trades'    },
  { key: 'portfolio', label: 'Portfolio', Icon: Briefcase,      color: 'portfolio' },
  { key: 'settings',  label: 'Settings',  Icon: Settings,       color: 'settings'  },
  { key: 'help',      label: 'Help',      Icon: CircleHelp,     color: 'help'      },
]

/**
 * Dock — cloud-shaped navigation dock positioned just below center of the viewport.
 *
 * Renders an inline SVG cloud backdrop (overlapping ellipses) filled with
 * var(--color-cloud) so it adapts to day/night theme automatically.
 * On top of the cloud sit the Canary logo and 5 cartoony, puffy nav buttons
 * styled as rounded squares with a 3D embossed effect, each with a text label.
 *
 * @returns {JSX.Element} The dock component
 */
/**
 * @param {Set<string>} openSections   Set of currently open section keys
 * @param {Function}    onNavigate     Callback to toggle a section open/closed
 */
export default function Dock({ openSections, onNavigate }) {

  /* Ref for the logo element — used by GSAP for the bobbing animation */
  const logoRef = useRef(null)

  /* GSAP bobbing animation on the logo — gentle float up and down.
     Uses yoyo + infinite repeat with a sine ease for a smooth, looping bob.
     Follows the same pattern used in BirdLayer.jsx. */
  useEffect(() => {
    const tween = gsap.to(logoRef.current, {
      y: -4,
      duration: 2,
      yoyo: true,
      repeat: -1,
      ease: 'sine.inOut',
    })
    /* Clean up the tween when the component unmounts */
    return () => tween.kill()
  }, [])

  return (
    <div className="dock">
      {/* ── Cloud SVG Backdrop ──
          Wider cloud shape (540×200) with more puffs to fill the larger dock.
          Center-top puff is tallest (where the logo sits). */}
      <svg
        className="dock-cloud"
        viewBox="0 0 810 300"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
      >
        {/* Cloud ellipses — group uses cloud color token, no drop shadow */}
        <g fill="var(--color-cloud)">
          {/* Wide flat base ellipse spanning the full width */}
          <ellipse cx="405" cy="240" rx="390" ry="75" />
          {/* Far-left puff */}
          <ellipse cx="120" cy="210" rx="105" ry="75" />
          {/* Left puff */}
          <ellipse cx="225" cy="172" rx="97"  ry="82" />
          {/* Center-left puff */}
          <ellipse cx="330" cy="135" rx="90"  ry="82" />
          {/* Center-top puff — tallest, logo sits above this */}
          <ellipse cx="405" cy="97"  rx="105" ry="90" />
          {/* Center-right puff */}
          <ellipse cx="480" cy="135" rx="90"  ry="82" />
          {/* Right puff */}
          <ellipse cx="585" cy="172" rx="97"  ry="82" />
          {/* Far-right puff */}
          <ellipse cx="690" cy="210" rx="105" ry="75" />
        </g>
      </svg>

      {/* ── Content Overlay ──
          Sits above the SVG cloud: logo on top, nav buttons with labels below. */}
      <div className="dock-content">
        {/* Canary logo — imported via Vite for proper asset hashing.
            ref is used by GSAP for the bobbing animation. */}
        <img
          ref={logoRef}
          className="dock-logo"
          src={logoCanary}
          alt="Canary"
        />

        {/* "Canary AI" branding label between logo and nav buttons */}
        <span className="dock-label">Canary AI</span>

        {/* Navigation button row — each button is a rounded puffy square with label */}
        <nav className="dock-nav">
          {NAV_ITEMS.map(({ key, label, Icon, color }) => (
            <button
              key={key}
              className={`dock-nav-btn${openSections.has(key) ? ' dock-nav-btn--active' : ''}`}
              title={label}
              aria-label={label}
              /* Toggle behavior: clicking an open section closes it; clicking a closed one opens it */
              onClick={() => onNavigate(key)}
              /* Per-button section colors via inline CSS custom properties.
                 The CSS file references --btn-primary / --btn-dark / --btn-light
                 for border, fill, and active states. */
              style={{
                '--btn-primary': `var(--color-${color}-primary)`,
                '--btn-dark':    `var(--color-${color}-dark)`,
                '--btn-light':   `var(--color-${color}-light)`,
              }}
            >
              {/* Icon — 28px to fill the larger 64px button */}
              <Icon size={28} />
              {/* Text label below the icon */}
              <span className="dock-nav-label">{label}</span>
            </button>
          ))}
        </nav>
      </div>
    </div>
  )
}
