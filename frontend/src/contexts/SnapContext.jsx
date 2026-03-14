import { createContext, useContext, useState, useRef, useCallback } from 'react'

/**
 * SnapContext — central state manager for the lego-style window snapping system.
 *
 * Provides:
 *   - A mutable registry of window rects, position/size setters, and DOM elements
 *     (stored in refs to avoid 60fps re-renders during drag)
 *   - A `bonds` state array describing edge connections between snapped windows
 *   - Functions for snap detection, bond management, and group queries
 *
 * @see useSnapDrag — consumes this context for drag-time snap detection
 * @see useSnapResize — consumes this context for linked resize propagation
 * @see SnapSeams — reads bonds state for seam overlays
 */
const SnapContext = createContext(null)

/**
 * SNAP_THRESHOLD — maximum pixel distance between two edges for a snap
 * candidate to be considered. Within this range the ghost preview appears;
 * releasing the mouse while a candidate exists commits the snap.
 */
const SNAP_THRESHOLD = 30

/**
 * MIN_OVERLAP — minimum perpendicular overlap (px) required between two
 * window edges for them to be considered snap candidates. Prevents snapping
 * when windows are barely touching at a corner.
 */
const MIN_OVERLAP = 30

/**
 * SnapProvider — wraps the application tree and manages all snap state.
 *
 * Mutable refs (no re-render on update):
 *   - windowRects: Map<id, { x, y, width, height }>
 *   - positionSetters: Map<id, setPosition function>
 *   - sizeSetters: Map<id, setSize function>
 *   - elementRefs: Map<id, HTMLElement>
 *
 * React state (triggers re-render):
 *   - bonds: Bond[] — array of edge connections
 *
 * @param {React.ReactNode} children  Child components to wrap
 * @returns {JSX.Element}
 */
export function SnapProvider({ children }) {
  /* ── Mutable Refs ──
     These are updated on every drag frame but never trigger re-renders. */

  /** Map of window IDs to their current bounding rects */
  const windowRects = useRef(new Map())

  /** Map of window IDs to their React position setter functions */
  const positionSetters = useRef(new Map())

  /** Map of window IDs to their React size setter functions */
  const sizeSetters = useRef(new Map())

  /** Map of window IDs to their DOM elements (used for GSAP animations) */
  const elementRefs = useRef(new Map())

  /* ── React State ──
     Changes here trigger re-renders for overlay components. */

  /** Array of snap bonds connecting window edges */
  const [bonds, setBonds] = useState([])

  /** Snap preview rect — shows a ghost rectangle where the window will land */
  const [snapPreview, setSnapPreview] = useState(null)

  /**
   * registerWindow — called by each Window on mount.
   * Stores the window's rect, setters, and DOM element in the mutable registries.
   *
   * @param {string} id         Unique window identifier (e.g. "trades", "chats")
   * @param {object} rect       Initial { x, y, width, height }
   * @param {Function} setPos   React state setter for position
   * @param {Function} setSize  React state setter for size
   * @param {HTMLElement} el    The window's root DOM element
   */
  const registerWindow = useCallback((id, rect, setPos, setSize, el) => {
    windowRects.current.set(id, { ...rect })
    positionSetters.current.set(id, setPos)
    sizeSetters.current.set(id, setSize)
    elementRefs.current.set(id, el)
  }, [])

  /**
   * unregisterWindow — called by each Window on unmount.
   * Removes the window from all registries and breaks any bonds involving it.
   *
   * @param {string} id  Window ID to remove
   */
  const unregisterWindow = useCallback((id) => {
    windowRects.current.delete(id)
    positionSetters.current.delete(id)
    sizeSetters.current.delete(id)
    elementRefs.current.delete(id)
    /* Remove any bonds that reference this window */
    setBonds(prev => prev.filter(b => b.idA !== id && b.idB !== id))
  }, [])

  /**
   * updateRect — hot-path function called on every drag/resize frame.
   * Writes directly to the mutable ref map — no state update, no re-render.
   *
   * @param {string} id    Window ID
   * @param {object} rect  Updated { x, y, width, height }
   */
  const updateRect = useCallback((id, rect) => {
    windowRects.current.set(id, { ...rect })
  }, [])

  /**
   * getGroup — finds all windows connected to the given window via BFS
   * over the bonds graph. Returns the full connected component.
   *
   * @param {string} id  Starting window ID
   * @returns {Set<string>}  Set of all connected window IDs (including the start)
   */
  const getGroup = useCallback((id) => {
    const visited = new Set()
    const queue = [id]
    visited.add(id)

    /* BFS traversal over the bonds adjacency graph */
    while (queue.length > 0) {
      const current = queue.shift()
      /* Check current bonds state via the setter's callback form to read latest */
      for (const bond of bonds) {
        if (bond.idA === current && !visited.has(bond.idB)) {
          visited.add(bond.idB)
          queue.push(bond.idB)
        }
        if (bond.idB === current && !visited.has(bond.idA)) {
          visited.add(bond.idA)
          queue.push(bond.idA)
        }
      }
    }

    return visited
  }, [bonds])

  /**
   * getBondsForWindow — returns all bonds that involve the given window.
   *
   * @param {string} id  Window ID
   * @returns {Bond[]}   Array of bonds where idA or idB matches the ID
   */
  const getBondsForWindow = useCallback((id) => {
    return bonds.filter(b => b.idA === id || b.idB === id)
  }, [bonds])

  /**
   * getEdgeValue — computes the pixel position of a specific edge of a window rect.
   *
   * @param {object} rect  { x, y, width, height }
   * @param {string} edge  One of "left", "right", "top", "bottom"
   * @returns {number}     Pixel position of that edge
   */
  const getEdgeValue = useCallback((rect, edge) => {
    switch (edge) {
      case 'left':   return rect.x
      case 'right':  return rect.x + rect.width
      case 'top':    return rect.y
      case 'bottom': return rect.y + rect.height
      default:       return 0
    }
  }, [])

  /**
   * getPerpendicularOverlap — computes how much two windows overlap along
   * the axis perpendicular to the snap edge. For horizontal snaps (left/right),
   * this measures vertical overlap. For vertical snaps (top/bottom), horizontal overlap.
   *
   * @param {object} rectA  First window rect
   * @param {object} rectB  Second window rect
   * @param {string} axis   "x" for left/right edges, "y" for top/bottom edges
   * @returns {number}      Overlap in pixels (0 if no overlap)
   */
  const getPerpendicularOverlap = useCallback((rectA, rectB, axis) => {
    if (axis === 'x') {
      /* For left/right snaps, compute vertical overlap */
      const overlapStart = Math.max(rectA.y, rectB.y)
      const overlapEnd = Math.min(rectA.y + rectA.height, rectB.y + rectB.height)
      return Math.max(0, overlapEnd - overlapStart)
    } else {
      /* For top/bottom snaps, compute horizontal overlap */
      const overlapStart = Math.max(rectA.x, rectB.x)
      const overlapEnd = Math.min(rectA.x + rectA.width, rectB.x + rectB.width)
      return Math.max(0, overlapEnd - overlapStart)
    }
  }, [])

  /**
   * getSnapTarget — core snap detection algorithm.
   *
   * Checks the dragged window's proposed rect against all other windows
   * (excluding those in the same snap group). For each candidate, tests
   * 4 edge pairs (right↔left, left↔right, bottom↔top, top↔bottom).
   * Returns the closest candidate within SNAP_THRESHOLD that has sufficient
   * perpendicular overlap.
   *
   * @param {string} draggedId     ID of the window being dragged
   * @param {object} proposedRect  Proposed { x, y, width, height } after drag delta
   * @returns {object|null}        { snappedRect, bond, distance } or null if no snap
   */
  const getSnapTarget = useCallback((draggedId, proposedRect) => {
    /* Get all windows in the drag group so we skip them */
    const group = getGroup(draggedId)

    /**
     * Edge pair definitions — each describes a potential snap connection:
     *   dragEdge: edge of the dragged window
     *   targetEdge: complementary edge of the target window
     *   axis: "x" for horizontal adjacency, "y" for vertical adjacency
     */
    const edgePairs = [
      { dragEdge: 'right',  targetEdge: 'left',   axis: 'x' },
      { dragEdge: 'left',   targetEdge: 'right',  axis: 'x' },
      { dragEdge: 'bottom', targetEdge: 'top',    axis: 'y' },
      { dragEdge: 'top',    targetEdge: 'bottom', axis: 'y' },
    ]

    let bestCandidate = null
    let bestDistance = Infinity

    /* Iterate all registered windows that aren't in the current drag group */
    for (const [targetId, targetRect] of windowRects.current) {
      if (group.has(targetId)) continue

      for (const pair of edgePairs) {
        /* Compute pixel distance between the two edges */
        const dragEdgeVal = getEdgeValue(proposedRect, pair.dragEdge)
        const targetEdgeVal = getEdgeValue(targetRect, pair.targetEdge)
        const distance = Math.abs(dragEdgeVal - targetEdgeVal)

        /* Skip if too far away or not enough perpendicular overlap */
        if (distance >= SNAP_THRESHOLD) continue
        const overlap = getPerpendicularOverlap(proposedRect, targetRect, pair.axis)
        if (overlap < MIN_OVERLAP) continue

        /* Track the closest candidate */
        if (distance < bestDistance) {
          bestDistance = distance

          /* Compute the snapped rect — shift the dragged window to exact alignment */
          const snappedRect = { ...proposedRect }
          if (pair.axis === 'x') {
            /* Horizontal snap — adjust x position */
            if (pair.dragEdge === 'right') {
              snappedRect.x = targetEdgeVal - proposedRect.width
            } else {
              snappedRect.x = targetEdgeVal
            }
          } else {
            /* Vertical snap — adjust y position */
            if (pair.dragEdge === 'bottom') {
              snappedRect.y = targetEdgeVal - proposedRect.height
            } else {
              snappedRect.y = targetEdgeVal
            }
          }

          /* Build the bond descriptor */
          const bond = {
            idA: draggedId,
            edgeA: pair.dragEdge,
            idB: targetId,
            edgeB: pair.targetEdge,
            axis: pair.axis,
          }

          bestCandidate = { snappedRect, bond, distance }
        }
      }
    }

    return bestCandidate
  }, [getGroup, getEdgeValue, getPerpendicularOverlap])

  /**
   * commitSnap — adds a new bond to the bonds state array.
   * Checks for duplicate bonds before adding.
   *
   * @param {object} bond  Bond descriptor { idA, edgeA, idB, edgeB, axis }
   */
  const commitSnap = useCallback((bond) => {
    setBonds(prev => {
      /* Prevent duplicate bonds between the same two windows on the same edges */
      const exists = prev.some(b =>
        (b.idA === bond.idA && b.edgeA === bond.edgeA && b.idB === bond.idB && b.edgeB === bond.edgeB) ||
        (b.idA === bond.idB && b.edgeA === bond.edgeB && b.idB === bond.idA && b.edgeB === bond.edgeA)
      )
      if (exists) return prev
      return [...prev, bond]
    })
  }, [])

  /**
   * breakBond — removes a bond at the given index from the bonds array.
   *
   * @param {number} bondIndex  Index into the bonds array to remove
   */
  const breakBond = useCallback((bondIndex) => {
    setBonds(prev => prev.filter((_, i) => i !== bondIndex))
  }, [])

  /**
   * showSnapPreview — displays a ghost rectangle preview at the given rect.
   * Shows where the dragged window will land after snapping.
   *
   * @param {object} rect  { x, y, width, height } of the snapped position
   */
  const showSnapPreview = useCallback((rect) => {
    setSnapPreview({ x: rect.x, y: rect.y, width: rect.width, height: rect.height })
  }, [])

  /**
   * clearSnapPreview — hides the snap preview ghost rectangle.
   * Called when drag ends or when no snap candidate is found.
   */
  const clearSnapPreview = useCallback(() => {
    setSnapPreview(null)
  }, [])

  /* Bundle all values and functions into the context value */
  const value = {
    /* Refs */
    windowRects,
    positionSetters,
    sizeSetters,
    elementRefs,
    /* State */
    bonds,
    /* Registration */
    registerWindow,
    unregisterWindow,
    updateRect,
    /* Snap detection */
    getSnapTarget,
    /* Bond management */
    commitSnap,
    breakBond,
    /* Group queries */
    getGroup,
    getBondsForWindow,
    /* Snap preview */
    snapPreview,
    showSnapPreview,
    clearSnapPreview,
  }

  return (
    <SnapContext.Provider value={value}>
      {children}
    </SnapContext.Provider>
  )
}

/**
 * useSnap — convenience hook to consume the SnapContext.
 * Throws if used outside a SnapProvider.
 *
 * @returns {object}  All SnapContext values and functions
 */
export function useSnap() {
  const ctx = useContext(SnapContext)
  if (!ctx) throw new Error('useSnap must be used within a SnapProvider')
  return ctx
}
