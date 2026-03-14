import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import useSnapDrag from '@/hooks/useSnapDrag'
import useSnapResize from '@/hooks/useSnapResize'
import { useSnap } from '@/contexts/SnapContext'
import './Window.css'

/**
 * MINIMUM window dimensions (px) — prevents the window from being
 * resized to an unusably small area.
 */
const MIN_SIZE = { width: 300, height: 380 }

/**
 * Window — generic draggable, resizable window shell with snap support.
 *
 * Renders a floating panel with:
 *   - A header bar (title label + close button) that acts as the drag handle
 *   - 8 invisible edge/corner resize handles
 *   - A GSAP pop-in animation on mount
 *   - Color theming via CSS custom properties derived from `colorTokenPrefix`
 *   - Snap-aware dragging and resizing via SnapContext
 *
 * On mount, registers with SnapContext so other windows can detect snap
 * candidates against this window. On unmount, unregisters to clean up.
 *
 * @param {string}   windowId           Unique identifier for snap system (e.g. "trades")
 * @param {string}   title              Text shown in the header bar
 * @param {Function} onClose            Called when the X button is clicked
 * @param {React.ReactNode} children    Content rendered in the window body
 * @param {{ x: number, y: number }}  initialPosition  Starting top-left coords
 * @param {{ width: number, height: number }} initialSize  Starting dimensions
 * @param {string}   closeIcon          Image src for the close button PNG (each window has its own colored icon)
 * @param {string}   colorTokenPrefix   Maps to CSS vars, e.g. "trades" → --color-trades-*
 * @param {number}   [zIndex=300]       Inline z-index for multi-window stacking order
 * @param {Function} [onFocus]          Called on mousedown to bring this window to front
 * @returns {JSX.Element}
 */
export default function Window({
  windowId,
  title,
  onClose,
  closeIcon,
  children,
  initialPosition = { x: window.innerWidth / 2 - 220, y: window.innerHeight / 2 - 250 },
  initialSize = { width: 440, height: 500 },
  colorTokenPrefix = 'trades',
  zIndex = 300,
  onFocus,
}) {
  /* Ref for the outer container — used by GSAP for the pop-in animation
     and registered with SnapContext for snap animations */
  const windowRef = useRef(null)

  /* Snap-aware drag hook — tracks position, provides onMouseDown for the header,
     handles group dragging and snap detection */
  const { position, setPosition, onMouseDown } = useSnapDrag(windowId, initialPosition)

  /* Snap-aware resize hook — tracks size, provides handle elements to render,
     handles linked resize propagation on bonded edges */
  const { size, setSize, resizeHandles } = useSnapResize(windowId, initialSize, MIN_SIZE, setPosition)

  /* Snap context — used for window registration/unregistration */
  const snap = useSnap()

  /**
   * Register this window with SnapContext on mount.
   * Provides the initial rect, position/size setters, and DOM element
   * so other windows can detect snaps and the system can animate this window.
   */
  useEffect(() => {
    if (!windowRef.current) return

    snap.registerWindow(
      windowId,
      { ...initialPosition, width: initialSize.width, height: initialSize.height },
      setPosition,
      setSize,
      windowRef.current,
    )

    /* Unregister on unmount to remove from all snap tracking */
    return () => snap.unregisterWindow(windowId)
  }, [windowId]) // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Keep the snap registry in sync whenever position or size changes.
   * This ensures snap detection always uses the latest rect.
   */
  useEffect(() => {
    snap.updateRect(windowId, {
      x: position.x,
      y: position.y,
      width: size.width,
      height: size.height,
    })
  }, [windowId, position.x, position.y, size.width, size.height, snap])

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
      /* Data attribute for snap system identification */
      data-window-id={windowId}
      /* Bring this window to the front of the stack when clicked anywhere */
      onMouseDown={onFocus}
      style={{
        /* Position and size driven by snap-aware drag/resize hooks */
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
        /* Dynamic z-index for multi-window stacking */
        zIndex,
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
