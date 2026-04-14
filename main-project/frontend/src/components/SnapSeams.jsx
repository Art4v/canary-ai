import { useCallback } from 'react'
import gsap from 'gsap'
import { useSnap } from '@/contexts/SnapContext'

/**
 * SEAM_WIDTH — total width (px) of the invisible clickable seam overlay.
 * The seam is centered on the shared edge between two bonded windows.
 */
const SEAM_WIDTH = 12

/**
 * UNSNAP_DISTANCE — how far (px) windows are pushed apart on double-click unsnap.
 */
const UNSNAP_DISTANCE = 20

/**
 * SnapSeams — renders invisible clickable overlays along the seam between
 * each pair of bonded windows.
 *
 * Behavior:
 *   - On hover: shows a 2px colored line at the exact seam position
 *   - On double-click: breaks the bond and animates the windows apart
 *     with a playful bounce (GSAP back.out ease)
 *   - Hidden during active drag (seams aren't useful mid-drag)
 *
 * @returns {JSX.Element}  Array of absolutely-positioned seam overlays
 */
export default function SnapSeams() {
  const {
    bonds,
    breakBond,
    windowRects,
    positionSetters,
    elementRefs,
    updateRect,
  } = useSnap()

  /**
   * handleDoubleClick — breaks the bond at the given index and animates
   * the two windows 20px apart with a bounce effect.
   *
   * @param {number} bondIndex  Index into the bonds array
   * @param {object} bond       Bond descriptor { idA, edgeA, idB, edgeB, axis }
   */
  const handleDoubleClick = useCallback((bondIndex, bond) => {
    const elA = elementRefs.current.get(bond.idA)
    const elB = elementRefs.current.get(bond.idB)
    const rectA = windowRects.current.get(bond.idA)
    const rectB = windowRects.current.get(bond.idB)
    const setPosA = positionSetters.current.get(bond.idA)
    const setPosB = positionSetters.current.get(bond.idB)

    /* Break the bond immediately to remove from state */
    breakBond(bondIndex)

    if (!elA || !elB || !rectA || !rectB) return

    /**
     * Compute push direction based on which edges were bonded:
     *   - A's right was bonded to B's left → push A left, B right
     *   - A's left was bonded to B's right → push A right, B left
     *   - A's bottom was bonded to B's top → push A up, B down
     *   - A's top was bonded to B's bottom → push A down, B up
     */
    let propA = {}
    let propB = {}
    let newRectA = { ...rectA }
    let newRectB = { ...rectB }

    if (bond.axis === 'x') {
      /* Horizontal bond — push apart on x-axis */
      const dirA = bond.edgeA === 'right' ? -1 : 1
      const dirB = -dirA
      propA = { left: rectA.x + dirA * UNSNAP_DISTANCE }
      propB = { left: rectB.x + dirB * UNSNAP_DISTANCE }
      newRectA.x += dirA * UNSNAP_DISTANCE
      newRectB.x += dirB * UNSNAP_DISTANCE
    } else {
      /* Vertical bond — push apart on y-axis */
      const dirA = bond.edgeA === 'bottom' ? -1 : 1
      const dirB = -dirA
      propA = { top: rectA.y + dirA * UNSNAP_DISTANCE }
      propB = { top: rectB.y + dirB * UNSNAP_DISTANCE }
      newRectA.y += dirA * UNSNAP_DISTANCE
      newRectB.y += dirB * UNSNAP_DISTANCE
    }

    /* Animate window A apart with a playful bounce */
    gsap.to(elA, {
      ...propA,
      duration: 0.2,
      ease: 'back.out(1.4)',
      onComplete: () => {
        /* Sync React state with the GSAP-animated position */
        if (setPosA) setPosA({ x: newRectA.x, y: newRectA.y })
        updateRect(bond.idA, newRectA)
      },
    })

    /* Animate window B apart with the same bounce */
    gsap.to(elB, {
      ...propB,
      duration: 0.2,
      ease: 'back.out(1.4)',
      onComplete: () => {
        /* Sync React state with the GSAP-animated position */
        if (setPosB) setPosB({ x: newRectB.x, y: newRectB.y })
        updateRect(bond.idB, newRectB)
      },
    })
  }, [breakBond, elementRefs, windowRects, positionSetters, updateRect])

  /* Don't render anything if there are no bonds */
  if (bonds.length === 0) return null

  return (
    <>
      {bonds.map((bond, index) => {
        /* Look up the current rects for both bonded windows */
        const rectA = windowRects.current.get(bond.idA)
        const rectB = windowRects.current.get(bond.idB)
        if (!rectA || !rectB) return null

        /* Compute the seam position and dimensions based on bond axis */
        let style = {}

        if (bond.axis === 'x') {
          /* Vertical seam along a left/right edge */
          const seamX = bond.edgeA === 'right'
            ? rectA.x + rectA.width  /* A's right edge */
            : rectA.x                /* A's left edge */
          const top = Math.max(rectA.y, rectB.y)
          const bottom = Math.min(rectA.y + rectA.height, rectB.y + rectB.height)
          const height = bottom - top

          if (height <= 0) return null

          style = {
            position: 'fixed',
            left: seamX - SEAM_WIDTH / 2,
            top: top,
            width: SEAM_WIDTH,
            height: height,
            cursor: 'col-resize',
            zIndex: 9999,
          }
        } else {
          /* Horizontal seam along a top/bottom edge */
          const seamY = bond.edgeA === 'bottom'
            ? rectA.y + rectA.height  /* A's bottom edge */
            : rectA.y                  /* A's top edge */
          const left = Math.max(rectA.x, rectB.x)
          const right = Math.min(rectA.x + rectA.width, rectB.x + rectB.width)
          const width = right - left

          if (width <= 0) return null

          style = {
            position: 'fixed',
            left: left,
            top: seamY - SEAM_WIDTH / 2,
            width: width,
            height: SEAM_WIDTH,
            cursor: 'row-resize',
            zIndex: 9999,
          }
        }

        return (
          <div
            key={`${bond.idA}-${bond.edgeA}-${bond.idB}-${bond.edgeB}`}
            style={style}
            /* Double-click to break the bond and push windows apart */
            onDoubleClick={() => handleDoubleClick(index, bond)}
            /* Show a thin colored line on hover via inline hover styles */
            onMouseEnter={(e) => {
              /* Create a 2px highlight line inside the seam overlay */
              const highlight = document.createElement('div')
              highlight.className = 'snap-seam-highlight'
              highlight.style.position = 'absolute'
              highlight.style.background = 'var(--color-accent, #4a9eff)'
              highlight.style.borderRadius = '1px'
              if (bond.axis === 'x') {
                /* Vertical highlight line centered in the seam */
                highlight.style.left = `${SEAM_WIDTH / 2 - 1}px`
                highlight.style.top = '0'
                highlight.style.width = '2px'
                highlight.style.height = '100%'
              } else {
                /* Horizontal highlight line centered in the seam */
                highlight.style.left = '0'
                highlight.style.top = `${SEAM_WIDTH / 2 - 1}px`
                highlight.style.width = '100%'
                highlight.style.height = '2px'
              }
              e.currentTarget.appendChild(highlight)
            }}
            onMouseLeave={(e) => {
              /* Remove the highlight line when the mouse leaves */
              const highlight = e.currentTarget.querySelector('.snap-seam-highlight')
              if (highlight) highlight.remove()
            }}
          />
        )
      })}
    </>
  )
}
