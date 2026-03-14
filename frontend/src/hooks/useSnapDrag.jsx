import { useState, useCallback, useEffect, useRef } from 'react'
import gsap from 'gsap'
import { useSnap } from '@/contexts/SnapContext'

/**
 * useSnapDrag — snap-aware drag hook that replaces useDrag in Window.jsx.
 *
 * Contains all of useDrag's position-tracking logic PLUS:
 *   - Group dragging: all bonded windows move together as a unit
 *   - Snap detection: shows a ghost preview when near another window's edge;
 *     releasing while the preview is visible snaps the window into place
 *   - GSAP snap animation on mouseup with pending bond
 *
 * @param {string} windowId                       Unique window identifier
 * @param {{ x: number, y: number }} initialPosition  Starting top-left coords
 * @returns {{ position, setPosition, onMouseDown, dragging }}
 *   - position    `{ x, y }` — current top-left position in px
 *   - setPosition setter function for external position updates
 *   - onMouseDown attach to the drag-handle's onMouseDown
 *   - dragging    ref indicating whether a drag is active
 */
export default function useSnapDrag(windowId, initialPosition) {
  /* Current position of the draggable element */
  const [position, setPosition] = useState(initialPosition)

  /* Whether a drag operation is currently in progress */
  const dragging = useRef(false)

  /* Pointer offset from element top-left recorded at drag start */
  const offset = useRef({ x: 0, y: 0 })

  /* Store latest position in a ref for delta calculations during drag */
  const positionRef = useRef(initialPosition)
  useEffect(() => { positionRef.current = position }, [position])

  /* Snap context — provides group queries, snap detection, bond management */
  const snap = useSnap()

  /* The set of window IDs in the current drag group (computed on mousedown) */
  const dragGroup = useRef(new Set())

  /* Starting positions of all group members at drag start (for delta calc) */
  const groupStartPositions = useRef(new Map())

  /* Pending bond to commit on mouseup (set during drag when snap candidate exists) */
  const pendingBond = useRef(null)

  /* Pending snapped rect — the target position for the mouseup GSAP animation.
     Stored separately so the window follows the cursor freely during drag
     while still knowing where to animate on release. */
  const pendingSnappedRect = useRef(null)

  /* Previous mouse position for computing per-frame deltas */
  const prevMouse = useRef({ x: 0, y: 0 })

  /**
   * handleMouseDown — initiates the drag.
   * Records the pointer offset, identifies the snap group via BFS,
   * stores starting positions of all group members, and disables text selection.
   */
  const onMouseDown = useCallback((e) => {
    /* Only respond to primary (left) mouse button */
    if (e.button !== 0) return
    dragging.current = true
    pendingBond.current = null
    pendingSnappedRect.current = null

    /* Record pointer offset from element's top-left corner */
    const rect = e.currentTarget.closest('.window').getBoundingClientRect()
    offset.current = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    }

    /* Store initial mouse position for delta calculations */
    prevMouse.current = { x: e.clientX, y: e.clientY }

    /* Identify the full snap group connected to this window */
    const group = snap.getGroup(windowId)
    dragGroup.current = group

    /* Record starting positions for all group members */
    groupStartPositions.current = new Map()
    for (const id of group) {
      const r = snap.windowRects.current.get(id)
      if (r) groupStartPositions.current.set(id, { x: r.x, y: r.y })
    }

    /* Prevent text selection while dragging */
    document.body.style.userSelect = 'none'
  }, [windowId, snap])

  useEffect(() => {
    /**
     * handleMouseMove — updates position while dragging.
     * Moves the entire snap group by the same delta, then runs snap
     * detection against non-group windows.
     */
    const handleMouseMove = (e) => {
      if (!dragging.current) return

      /* Read current size from the snap registry — always up-to-date after resize */
      const currentRect = snap.windowRects.current.get(windowId)
      const width = currentRect ? currentRect.width : 0
      const height = currentRect ? currentRect.height : 0

      /* Compute the raw new position for the dragged window */
      let newX = Math.min(Math.max(0, e.clientX - offset.current.x), window.innerWidth - width)
      let newY = Math.min(Math.max(0, e.clientY - offset.current.y), window.innerHeight - height)

      /* Compute the delta from the previous position */
      const deltaX = newX - positionRef.current.x
      const deltaY = newY - positionRef.current.y

      /* Update the dragged window's position */
      setPosition({ x: newX, y: newY })

      /* Update the dragged window's rect in the snap registry */
      snap.updateRect(windowId, { x: newX, y: newY, width, height })

      /* Move all other windows in the snap group by the same delta */
      for (const memberId of dragGroup.current) {
        if (memberId === windowId) continue

        const memberRect = snap.windowRects.current.get(memberId)
        if (!memberRect) continue

        const memberNewX = memberRect.x + deltaX
        const memberNewY = memberRect.y + deltaY

        /* Update the member's position via its registered setter */
        const memberSetPos = snap.positionSetters.current.get(memberId)
        if (memberSetPos) memberSetPos({ x: memberNewX, y: memberNewY })

        /* Update the member's rect in the snap registry */
        snap.updateRect(memberId, {
          x: memberNewX,
          y: memberNewY,
          width: memberRect.width,
          height: memberRect.height,
        })
      }

      /* Run snap detection against non-group windows */
      const proposedRect = { x: newX, y: newY, width, height }
      const candidate = snap.getSnapTarget(windowId, proposedRect)

      if (candidate) {
        /* Candidate within SNAP_THRESHOLD — show preview and store pending snap.
           The window follows the cursor freely; the ghost preview shows where
           it will land on release. No auto-jump during drag. */
        snap.showSnapPreview(candidate.snappedRect)
        pendingBond.current = candidate.bond
        pendingSnappedRect.current = candidate.snappedRect
      } else {
        /* No snap candidate — clear preview and pending state */
        snap.clearSnapPreview()
        pendingBond.current = null
        pendingSnappedRect.current = null
      }
    }

    /**
     * handleMouseUp — ends the drag.
     * If there's a pending bond, animates the snap with GSAP then commits.
     * Clears snap preview in all cases.
     */
    const handleMouseUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.userSelect = ''

      if (pendingBond.current && pendingSnappedRect.current) {
        /* Animate the window from its current position to the snapped position */
        const el = snap.elementRefs.current.get(windowId)
        const bond = pendingBond.current
        const snappedRect = pendingSnappedRect.current

        /* Update the snap registry rect before animation so other systems
           see the final position immediately */
        snap.updateRect(windowId, snappedRect)
        setPosition({ x: snappedRect.x, y: snappedRect.y })

        if (el) {
          gsap.to(el, {
            left: snappedRect.x,
            top: snappedRect.y,
            duration: 0.12,
            ease: 'power2.out',
            onComplete: () => {
              snap.commitSnap(bond)
            },
          })
        } else {
          /* Fallback: commit immediately if element not found */
          snap.commitSnap(bond)
        }

        pendingBond.current = null
        pendingSnappedRect.current = null
      }

      /* Clear snap preview after drag ends */
      snap.clearSnapPreview()
    }

    /* Attach listeners to document so drag continues even if cursor leaves the element */
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [windowId, snap])

  return { position, setPosition, onMouseDown, dragging }
}
