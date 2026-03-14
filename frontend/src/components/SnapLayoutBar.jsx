import { useRef, useEffect, useState } from 'react'
import gsap from 'gsap'
import { useSnap } from '@/contexts/SnapContext'
import { SNAP_LAYOUTS, computeZoneRect } from '@/contexts/SnapContext'
import './SnapLayoutBar.css'

/**
 * SnapLayoutBar — Windows 11-style snap layout toolbar.
 *
 * Slides down from the top center of the viewport when the user drags
 * a window near the top edge (clientY < 10). Shows 6 layout options as
 * miniature tile grids. Hovering a zone within a tile shows a full-size
 * translucent blue preview on the viewport (via SnapPreview). Releasing
 * the mouse while a zone is hovered snaps the window to that zone.
 *
 * No props — reads all state from SnapContext via useSnap().
 *
 * @returns {JSX.Element|null}  Layout bar UI, or null when fully hidden
 */
export default function SnapLayoutBar() {
  const { layoutBarVisible, setLayoutZoneHover } = useSnap()

  /** Ref to the bar container for GSAP slide animation */
  const barRef = useRef(null)

  /** Track whether bar was previously visible (for exit animation) */
  const [wasVisible, setWasVisible] = useState(false)

  /**
   * Animate the bar in/out when layoutBarVisible changes.
   * Slide down from y:-100 with fade on show; reverse on hide.
   */
  useEffect(() => {
    if (!barRef.current) return

    if (layoutBarVisible && !wasVisible) {
      /* Bar just appeared — slide in from above */
      setWasVisible(true)
      gsap.fromTo(barRef.current,
        { y: -100, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.25, ease: 'power2.out' }
      )
    } else if (!layoutBarVisible && wasVisible) {
      /* Bar just hidden — slide out upward, then mark as gone */
      gsap.to(barRef.current, {
        y: -100,
        opacity: 0,
        duration: 0.18,
        ease: 'power2.in',
        onComplete: () => setWasVisible(false),
      })
    }
  }, [layoutBarVisible, wasVisible])

  /* Don't render anything if bar isn't visible and exit animation is done */
  if (!layoutBarVisible && !wasVisible) return null

  /**
   * handleZoneEnter — called when the cursor enters a zone within a tile.
   * Computes the pixel rect for that zone and passes it to the context
   * so the SnapPreview overlay can display the full-size preview.
   *
   * @param {number} layoutIndex  Index into SNAP_LAYOUTS
   * @param {number} zoneIndex    Index into the layout's zones array
   * @param {object} zone         Fractional zone { x, y, w, h }
   */
  const handleZoneEnter = (layoutIndex, zoneIndex, zone) => {
    const rect = computeZoneRect(zone)
    setLayoutZoneHover({ layoutIndex, zoneIndex, rect })
  }

  /**
   * handleBarLeave — called when the cursor leaves the entire bar.
   * Clears the hovered zone so the preview disappears.
   */
  const handleBarLeave = () => {
    setLayoutZoneHover(null)
  }

  return (
    <div
      ref={barRef}
      className="snap-layout-bar"
      onMouseLeave={handleBarLeave}
    >
      <div className="snap-layout-bar__layouts">
        {SNAP_LAYOUTS.map((layout, layoutIndex) => (
          <div
            key={layout.name}
            className="snap-layout-bar__tile"
            title={layout.name}
          >
            {layout.zones.map((zone, zoneIndex) => (
              <div
                key={zoneIndex}
                className="snap-layout-bar__zone"
                style={{
                  /* Position each zone within the tile using percentage values
                     that match the fractional coordinates from SNAP_LAYOUTS */
                  left: `${zone.x * 100}%`,
                  top: `${zone.y * 100}%`,
                  width: `${zone.w * 100}%`,
                  height: `${zone.h * 100}%`,
                }}
                onMouseEnter={() => handleZoneEnter(layoutIndex, zoneIndex, zone)}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
