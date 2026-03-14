import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import useDrag from '@/hooks/useDrag'
import useResize from '@/hooks/useResize'
import './Window.css'

/**
 * MINIMUM window dimensions (px) — prevents the window from being
 * resized to an unusably small area.
 */
const MIN_SIZE = { width: 300, height: 380 }

/**
 * Window — generic draggable, resizable window shell.
 *
 * Renders a floating panel with:
 *   - A header bar (title label + close button) that acts as the drag handle
 *   - 8 invisible edge/corner resize handles
 *   - A GSAP pop-in animation on mount
 *   - Color theming via CSS custom properties derived from `colorTokenPrefix`
 *
 * @param {string}   title              Text shown in the header bar
 * @param {Function} onClose            Called when the X button is clicked
 * @param {React.ReactNode} children    Content rendered in the window body
 * @param {{ x: number, y: number }}  initialPosition  Starting top-left coords
 * @param {{ width: number, height: number }} initialSize  Starting dimensions
 * @param {string}   closeIcon          Image src for the close button PNG (each window has its own colored icon)
 * @param {string}   colorTokenPrefix   Maps to CSS vars, e.g. "trades" → --color-trades-*
 * @returns {JSX.Element}
 */
export default function Window({
  title,
  onClose,
  closeIcon,
  children,
  initialPosition = { x: window.innerWidth / 2 - 220, y: window.innerHeight / 2 - 250 },
  initialSize = { width: 440, height: 500 },
  colorTokenPrefix = 'trades',
}) {
  /* Ref for the outer container — used by GSAP for the pop-in animation */
  const windowRef = useRef(null)

  /* Drag hook — tracks position, provides onMouseDown for the header */
  const { position, setPosition, onMouseDown } = useDrag(initialPosition, initialSize)

  /* Resize hook — tracks size, provides handle elements to render */
  const { size, resizeHandles } = useResize(initialSize, MIN_SIZE, setPosition)

  /**
   * Pop-in animation on mount — scales from 0.8 → 1 and fades in.
   * Uses GSAP.fromTo for a snappy, playful entrance matching the app's style.
   */
  useEffect(() => {
    if (!windowRef.current) return
    gsap.fromTo(
      windowRef.current,
      { scale: 0.8, opacity: 0 },
      { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' },
    )
  }, [])

  return (
    <div
      ref={windowRef}
      className="window"
      style={{
        /* Position and size driven by drag/resize hooks */
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
        /* Color tokens — consumed by Window.css as --win-primary / dark / light */
        '--win-primary': `var(--color-${colorTokenPrefix}-primary)`,
        '--win-dark':    `var(--color-${colorTokenPrefix}-dark)`,
        '--win-light':   `var(--color-${colorTokenPrefix}-light)`,
      }}
    >
      {/* Invisible resize handles positioned along all 8 edges/corners */}
      {resizeHandles}

      {/* ── Header Bar ──
          Acts as the drag handle. Contains the title and a close (X) button. */}
      <div className="window-header" onMouseDown={onMouseDown}>
        <span className="window-title">{title}</span>
        <button
          className="window-close"
          onClick={onClose}
          aria-label="Close window"
        >
          {/* Custom close icon — each window section provides its own colored PNG */}
          <img src={closeIcon} alt="Close" />
        </button>
      </div>

      {/* ── Body ──
          Scrollable content area filled by the children prop. */}
      <div className="window-body">
        {children}
      </div>
    </div>
  )
}
