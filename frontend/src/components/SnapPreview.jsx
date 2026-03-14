import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import { useSnap } from '@/contexts/SnapContext'

/**
 * SnapPreview — renders a semi-transparent "ghost rectangle" overlay showing
 * where the dragged window will land after snapping.
 *
 * Reads `snapPreview` from SnapContext. When a preview rect is set, renders
 * a fixed-position div with accent-colored background at low opacity,
 * matching the window's border radius. Fades in/out with GSAP.
 *
 * @returns {JSX.Element|null}  Ghost rectangle overlay, or null if no preview
 */
export default function SnapPreview() {
  const { snapPreview } = useSnap()

  /** Ref to the preview div for GSAP opacity animations */
  const previewRef = useRef(null)

  /** Track whether the preview was visible on the previous render */
  const prevVisibleRef = useRef(false)

  /**
   * Animate the preview in/out when it appears or disappears.
   * Fade in with 0.1s duration, fade out with 0.08s.
   */
  useEffect(() => {
    if (!previewRef.current) return

    if (snapPreview && !prevVisibleRef.current) {
      /* Preview just appeared — fade in */
      gsap.fromTo(previewRef.current,
        { opacity: 0 },
        { opacity: 1, duration: 0.1 }
      )
    } else if (!snapPreview && prevVisibleRef.current) {
      /* Preview just disappeared — fade out */
      gsap.to(previewRef.current, { opacity: 0, duration: 0.08 })
    }

    prevVisibleRef.current = !!snapPreview
  }, [snapPreview])

  /* Don't render anything if there is no preview and wasn't one before */
  if (!snapPreview && !prevVisibleRef.current) return null

  return (
    <div
      ref={previewRef}
      style={{
        /* Fixed overlay positioned exactly where the window will snap */
        position: 'fixed',
        left: snapPreview ? snapPreview.x : 0,
        top: snapPreview ? snapPreview.y : 0,
        width: snapPreview ? snapPreview.width : 0,
        height: snapPreview ? snapPreview.height : 0,
        /* Semi-transparent accent fill — ~20% opacity via rgba fallback */
        background: 'rgba(74, 158, 255, 0.2)',
        /* Slightly more opaque accent border — ~40% opacity */
        border: '2px solid rgba(74, 158, 255, 0.4)',
        /* Match the window border radius for a cohesive look */
        borderRadius: '12px',
        /* Below guide lines (9998) but above normal windows */
        zIndex: 9997,
        /* Non-interactive — clicks pass through to windows below */
        pointerEvents: 'none',
      }}
    />
  )
}
