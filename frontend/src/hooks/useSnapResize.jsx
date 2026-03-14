import { useState, useCallback, useEffect, useRef } from 'react'
import { useSnap } from '@/contexts/SnapContext'

/**
 * EDGES — defines all 8 resize handles (4 edges + 4 corners).
 * Each entry specifies the CSS cursor, position styles (as CSS properties),
 * and which axes are affected (dx/dy for origin, dw/dh for size).
 *
 * Convention for direction flags:
 *   dx: -1 means left edge moves (adjusts x + width), 0 means fixed
 *   dy: -1 means top edge moves (adjusts y + height), 0 means fixed
 *   dw:  1 means right edge stretches width, 0 means fixed
 *   dh:  1 means bottom edge stretches height, 0 means fixed
 */
const HANDLE_SIZE = 6 /* px — invisible hit-area thickness for edge handles */

const EDGES = [
  /* ── Straight edges ── */
  { name: 'top',    cursor: 'ns-resize',   style: { top: 0, left: HANDLE_SIZE, right: HANDLE_SIZE, height: HANDLE_SIZE }, dx: 0, dy: -1, dw: 0, dh: 0 },
  { name: 'bottom', cursor: 'ns-resize',   style: { bottom: 0, left: HANDLE_SIZE, right: HANDLE_SIZE, height: HANDLE_SIZE }, dx: 0, dy: 0, dw: 0, dh: 1 },
  { name: 'left',   cursor: 'ew-resize',   style: { left: 0, top: HANDLE_SIZE, bottom: HANDLE_SIZE, width: HANDLE_SIZE }, dx: -1, dy: 0, dw: 0, dh: 0 },
  { name: 'right',  cursor: 'ew-resize',   style: { right: 0, top: HANDLE_SIZE, bottom: HANDLE_SIZE, width: HANDLE_SIZE }, dx: 0, dy: 0, dw: 1, dh: 0 },
  /* ── Corner handles ── */
  { name: 'top-left',     cursor: 'nwse-resize', style: { top: 0, left: 0, width: HANDLE_SIZE, height: HANDLE_SIZE }, dx: -1, dy: -1, dw: 0, dh: 0 },
  { name: 'top-right',    cursor: 'nesw-resize', style: { top: 0, right: 0, width: HANDLE_SIZE, height: HANDLE_SIZE }, dx: 0, dy: -1, dw: 1, dh: 0 },
  { name: 'bottom-left',  cursor: 'nesw-resize', style: { bottom: 0, left: 0, width: HANDLE_SIZE, height: HANDLE_SIZE }, dx: -1, dy: 0, dw: 0, dh: 1 },
  { name: 'bottom-right', cursor: 'nwse-resize', style: { bottom: 0, right: 0, width: HANDLE_SIZE, height: HANDLE_SIZE }, dx: 0, dy: 0, dw: 1, dh: 1 },
]

/**
 * MIN_BONDED_SIZE — minimum dimension (px) for a bonded window during
 * linked resize. Prevents the bonded window from being crushed to zero.
 */
const MIN_BONDED_SIZE = 100

/**
 * mapEdgeName — maps EDGES handle names to the bond edge names used
 * by the snap system. Handles like "top-left" affect both "top" and "left"
 * edges, so we return all applicable bond edge names.
 *
 * @param {object} edge  Edge descriptor from EDGES array
 * @returns {string[]}   Array of bond edge names affected by this resize handle
 */
function getAffectedBondEdges(edge) {
  const edges = []
  if (edge.dw === 1) edges.push('right')   /* right edge grows rightward */
  if (edge.dx === -1) edges.push('left')    /* left edge grows leftward */
  if (edge.dh === 1) edges.push('bottom')   /* bottom edge grows downward */
  if (edge.dy === -1) edges.push('top')     /* top edge grows upward */
  return edges
}

/**
 * useSnapResize — snap-aware resize hook that replaces useResize in Window.jsx.
 *
 * Contains all of useResize's resize logic PLUS linked resize propagation:
 * when a resized edge has a snap bond, the bonded window's position and size
 * are adjusted to maintain the connection. Only propagates one level deep
 * (no cascading through chains).
 *
 * @param {string} windowId                           Unique window identifier
 * @param {{ width: number, height: number }} initialSize  Starting dimensions
 * @param {{ width: number, height: number }} minSize      Minimum allowed dimensions
 * @param {Function} setPosition                       Position setter from useSnapDrag
 * @returns {{ size, setSize, resizeHandles }}
 */
export default function useSnapResize(windowId, initialSize, minSize, setPosition) {
  /* Current width/height of the window */
  const [size, setSize] = useState(initialSize)

  /* Ref tracking active resize state: which edge, starting mouse pos, starting bounds */
  const resizing = useRef(null)

  /* Snap context — provides bond queries and registered setters */
  const snap = useSnap()

  /**
   * handleResizeStart — records starting geometry when user grabs a resize handle.
   * Also captures the starting geometry of any bonded windows for linked resize.
   * stopPropagation prevents the drag hook from also firing.
   */
  const onHandleMouseDown = useCallback((e, edge) => {
    if (e.button !== 0) return
    e.stopPropagation()

    /* Capture the window's current bounding rect at resize start */
    const rect = e.currentTarget.closest('.window').getBoundingClientRect()

    /* Find bonds on edges affected by this resize handle */
    const affectedEdges = getAffectedBondEdges(edge)
    const windowBonds = snap.getBondsForWindow(windowId)

    /* Capture starting state of bonded windows for linked resize */
    const bondedStarts = new Map()
    for (const bond of windowBonds) {
      /* Determine which edge of this window is in the bond */
      const thisEdge = bond.idA === windowId ? bond.edgeA : bond.edgeB
      const otherId = bond.idA === windowId ? bond.idB : bond.idA

      if (affectedEdges.includes(thisEdge)) {
        const otherRect = snap.windowRects.current.get(otherId)
        if (otherRect) {
          bondedStarts.set(otherId, {
            ...otherRect,
            bondEdge: thisEdge,        /* edge of this window */
            otherEdge: bond.idA === windowId ? bond.edgeB : bond.edgeA,
          })
        }
      }
    }

    resizing.current = {
      edge,
      startX: e.clientX,
      startY: e.clientY,
      startW: rect.width,
      startH: rect.height,
      startLeft: rect.left,
      startTop: rect.top,
      bondedStarts,
    }
    document.body.style.userSelect = 'none'
  }, [windowId, snap])

  useEffect(() => {
    /**
     * handleMouseMove — adjusts size and/or position based on which edge is active.
     * For left/top edges the origin also shifts so the opposite side stays anchored.
     * When a bonded window exists on the resized edge, propagates the resize to it.
     */
    const handleMouseMove = (e) => {
      if (!resizing.current) return
      const { edge, startX, startY, startW, startH, startLeft, startTop, bondedStarts } = resizing.current
      const deltaX = e.clientX - startX
      const deltaY = e.clientY - startY

      /* Calculate new width based on edge direction flags */
      let newW = startW
      if (edge.dw === 1) newW = startW + deltaX       /* right edge grows rightward */
      if (edge.dx === -1) newW = startW - deltaX       /* left edge grows leftward */

      /* Calculate new height based on edge direction flags */
      let newH = startH
      if (edge.dh === 1) newH = startH + deltaY        /* bottom edge grows downward */
      if (edge.dy === -1) newH = startH - deltaY       /* top edge grows upward */

      /* Enforce minimum dimensions */
      newW = Math.max(minSize.width, newW)
      newH = Math.max(minSize.height, newH)

      setSize({ width: newW, height: newH })

      /* When resizing from left or top edge, shift position so the opposite side stays put */
      let newX = startLeft
      let newY = startTop
      if (edge.dx === -1) newX = startLeft + (startW - newW)
      if (edge.dy === -1) newY = startTop + (startH - newH)
      setPosition({ x: newX, y: newY })

      /* Update this window's rect in the snap registry */
      snap.updateRect(windowId, { x: newX, y: newY, width: newW, height: newH })

      /* ── Linked Resize ──
         Propagate size/position changes to bonded windows (one level deep only). */
      for (const [otherId, startState] of bondedStarts) {
        const otherSetPos = snap.positionSetters.current.get(otherId)
        const otherSetSize = snap.sizeSetters.current.get(otherId)
        if (!otherSetPos || !otherSetSize) continue

        let otherX = startState.x
        let otherY = startState.y
        let otherW = startState.width
        let otherH = startState.height

        /**
         * Edge mapping for linked resize:
         *   - Resize this window's RIGHT (bonded to other's LEFT):
         *     Other window's x shifts by the width delta, width shrinks
         *   - Resize this window's LEFT (bonded to other's RIGHT):
         *     Other window's width grows (its right edge stays put)
         *   - Same logic for TOP/BOTTOM
         */
        if (startState.bondEdge === 'right') {
          /* This window's right edge moved — shift bonded window's left edge */
          const widthDelta = newW - startW
          otherX = startState.x + widthDelta
          otherW = startState.width - widthDelta
        } else if (startState.bondEdge === 'left') {
          /* This window's left edge moved — shift bonded window's right edge */
          const widthDelta = newW - startW
          otherW = startState.width + widthDelta
        } else if (startState.bondEdge === 'bottom') {
          /* This window's bottom edge moved — shift bonded window's top edge */
          const heightDelta = newH - startH
          otherY = startState.y + heightDelta
          otherH = startState.height - heightDelta
        } else if (startState.bondEdge === 'top') {
          /* This window's top edge moved — shift bonded window's bottom edge */
          const heightDelta = newH - startH
          otherH = startState.height + heightDelta
        }

        /* Enforce minimum bonded window size */
        otherW = Math.max(MIN_BONDED_SIZE, otherW)
        otherH = Math.max(MIN_BONDED_SIZE, otherH)

        /* Apply the computed position and size to the bonded window */
        otherSetPos({ x: otherX, y: otherY })
        otherSetSize({ width: otherW, height: otherH })

        /* Update the bonded window's rect in the snap registry */
        snap.updateRect(otherId, { x: otherX, y: otherY, width: otherW, height: otherH })
      }
    }

    /**
     * handleMouseUp — ends the resize operation and restores text selection.
     */
    const handleMouseUp = () => {
      if (!resizing.current) return
      resizing.current = null
      document.body.style.userSelect = ''
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [windowId, minSize, setPosition, snap])

  /**
   * resizeHandles — array of invisible positioned divs, one per edge/corner.
   * Each div covers a thin strip along its edge with the appropriate resize cursor.
   */
  const resizeHandles = EDGES.map((edge) => (
    <div
      key={edge.name}
      onMouseDown={(e) => onHandleMouseDown(e, edge)}
      style={{
        position: 'absolute',
        ...edge.style,
        cursor: edge.cursor,
        zIndex: 10,
        /* Invisible but clickable */
      }}
    />
  ))

  return { size, setSize, resizeHandles }
}
