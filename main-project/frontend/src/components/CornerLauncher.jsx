import { useState, useRef, useCallback, useEffect } from 'react'
import gsap from 'gsap'
import {
  Plus,
  Trash2,
  MessageCircle,
  ArrowLeftRight,
  Briefcase,
  Settings,
  CircleHelp,
} from 'lucide-react'
import './CornerLauncher.css'

/**
 * NAV_ITEMS — the 5 section buttons shown in the launcher menu.
 * Order here is bottom-to-top when expanded (Chat closest to trigger,
 * Help furthest). Each entry mirrors the Dock's navigation set.
 */
const NAV_ITEMS = [
  { key: 'chats',     Icon: MessageCircle,  color: 'chats'     },
  { key: 'trades',    Icon: ArrowLeftRight, color: 'trades'    },
  { key: 'portfolio', Icon: Briefcase,      color: 'portfolio' },
  { key: 'settings',  Icon: Settings,       color: 'settings'  },
  { key: 'help',      Icon: CircleHelp,     color: 'help'      },
]

/**
 * CornerLauncher — expandable quick-access menu anchored to a viewport corner.
 *
 * Renders a 48px puffy trigger button that, when clicked, expands a vertical
 * stack of section toggle buttons plus a "Clear All" action. Items animate in
 * with a staggered GSAP scale+fade entrance.
 *
 * @param {Object}   props
 * @param {"left"|"right"} props.position     — which bottom corner to anchor to
 * @param {Set}            props.openSections — currently open window keys (for outline state)
 * @param {Function}       props.onNavigate   — called with a section key to toggle it
 * @param {Function}       props.onClearAll   — called to close every open window
 * @returns {JSX.Element}
 */
export default function CornerLauncher({ position, openSections, onNavigate, onClearAll }) {
  /* Whether the menu is currently expanded */
  const [expanded, setExpanded] = useState(false)

  /* Whether the cursor is hovering over the corner zone.
     The trigger button is invisible until hovered (or the menu is expanded). */
  const [hovered, setHovered] = useState(false)

  /* Refs for GSAP animation targets */
  const menuRef = useRef(null)
  const itemRefs = useRef([])
  const triggerIconRef = useRef(null)
  const triggerRef = useRef(null)

  /* Derived flag: the trigger (and menu) should be visible when the cursor
     is inside the corner zone OR the menu is currently expanded. */
  const visible = hovered || expanded

  /**
   * toggleMenu — flip expanded state and kick off the GSAP
   * entrance or exit animation for the menu items.
   */
  const toggleMenu = useCallback(() => {
    setExpanded(prev => !prev)
  }, [])

  /**
   * Animate the trigger button in/out when visibility changes.
   * Fades + scales the trigger so it feels like it "pops" into the corner.
   */
  useEffect(() => {
    if (!triggerRef.current) return
    if (visible) {
      gsap.to(triggerRef.current, {
        scale: 1,
        opacity: 1,
        duration: 0.2,
        ease: 'back.out(1.7)',
      })
    } else {
      gsap.to(triggerRef.current, {
        scale: 0,
        opacity: 0,
        duration: 0.15,
        ease: 'power2.in',
      })
    }
  }, [visible])

  /**
   * Animate menu items whenever `expanded` changes.
   * - Expand: items scale from 0 → 1 and fade in with 0.05s stagger (bottom-up)
   * - Collapse: items scale from 1 → 0 and fade out with 0.04s stagger (top-down)
   * - Trigger icon rotates 0 → 45° (so the + becomes ×) or back
   */
  useEffect(() => {
    const items = itemRefs.current.filter(Boolean)
    if (items.length === 0) return

    if (expanded) {
      /* Make all items visible before animating in */
      gsap.set(items, { scale: 0, opacity: 0 })

      /* Staggered scale-up + fade-in, bottom item first */
      gsap.to(items, {
        scale: 1,
        opacity: 1,
        duration: 0.2,
        ease: 'back.out(1.7)',
        stagger: 0.05,
      })

      /* Rotate trigger icon 45° so + becomes × */
      if (triggerIconRef.current) {
        gsap.to(triggerIconRef.current, {
          rotation: 45,
          duration: 0.25,
          ease: 'power2.out',
        })
      }
    } else {
      /* Staggered scale-down + fade-out, top item first (reverse stagger) */
      gsap.to(items, {
        scale: 0,
        opacity: 0,
        duration: 0.15,
        ease: 'power2.in',
        stagger: { each: 0.04, from: 'end' },
      })

      /* Rotate trigger icon back to 0° */
      if (triggerIconRef.current) {
        gsap.to(triggerIconRef.current, {
          rotation: 0,
          duration: 0.25,
          ease: 'power2.out',
        })
      }
    }
  }, [expanded])

  /**
   * handleItemClick — toggle a section and keep the menu open so the
   * user can toggle multiple windows without re-expanding.
   *
   * @param {string} key  Section key to toggle
   */
  const handleItemClick = useCallback((key) => {
    onNavigate(key)
  }, [onNavigate])

  /**
   * handleClearAll — close all windows via the parent callback.
   */
  const handleClearAll = useCallback(() => {
    onClearAll()
  }, [onClearAll])

  return (
    <div
      className={`corner-launcher corner-launcher--${position}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* ── Menu: column of section buttons + Clear All ──
          Uses column-reverse so items stack upward from the trigger.
          Clear All is rendered LAST in DOM so column-reverse places it
          at the top (furthest from the trigger). */}
      {expanded && (
        <div className="corner-launcher__menu" ref={menuRef}>
          {/* Section toggle buttons — in NAV_ITEMS order (bottom-to-top visually
              because the container uses column-reverse) */}
          {NAV_ITEMS.map(({ key, Icon, color }, i) => {
            /* Determine whether this section's window is currently open */
            const isActive = openSections.has(key)
            return (
              <button
                key={key}
                ref={el => { itemRefs.current[i] = el }}
                className={`corner-launcher__item${isActive ? ' corner-launcher__item--active' : ''}`}
                title={key}
                aria-label={key}
                onClick={() => handleItemClick(key)}
                style={{
                  /* Per-section color tokens for fill and outline */
                  '--cl-primary': `var(--color-${color}-primary)`,
                  '--cl-dark': `var(--color-${color}-dark)`,
                }}
              >
                <Icon size={20} />
              </button>
            )
          })}

          {/* Clear All button — last in DOM so column-reverse puts it at the
              very top of the expanded stack, above all window buttons */}
          <button
            ref={el => { itemRefs.current[NAV_ITEMS.length] = el }}
            className="corner-launcher__item corner-launcher__item--clear"
            title="Clear All"
            aria-label="Clear All"
            onClick={handleClearAll}
          >
            <Trash2 size={20} />
          </button>
        </div>
      )}

      {/* ── Trigger button: puffy 48px circle with + icon ──
          Starts scaled to 0 / invisible; GSAP animates it in when
          the corner zone is hovered or the menu is expanded. */}
      <button
        ref={triggerRef}
        className="corner-launcher__trigger"
        title={expanded ? 'Close menu' : 'Open menu'}
        aria-label={expanded ? 'Close menu' : 'Open menu'}
        onClick={toggleMenu}
      >
        <span ref={triggerIconRef} className="corner-launcher__trigger-icon">
          <Plus size={24} />
        </span>
      </button>
    </div>
  )
}
