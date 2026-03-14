import { useState, useCallback, useEffect, useRef } from 'react'

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
 * useResize — custom hook for resizable windows with 8 edge/corner handles.
 *
 * Returns the current `size` state and a `resizeHandles` JSX array to render
 * inside the window container. On mousedown on any handle, the hook tracks
 * mouse movement and adjusts size (and position for top/left edges) accordingly.
 *
 * @param {{ width: number, height: number }} initialSize  Starting dimensions
 * @param {{ width: number, height: number }} minSize      Minimum allowed dimensions
 * @param {Function} setPosition  Setter from useDrag — called when top/left edges move
 * @returns {{ size, resizeHandles }}
 */
export default function useResize(initialSize, minSize, setPosition) {
  /* Current width/height of the window */
  const [size, setSize] = useState(initialSize)

  /* Ref tracking active resize state: which edge, starting mouse pos, starting bounds */
  const resizing = useRef(null)

  /**
   * handleResizeStart — records starting geometry when user grabs a resize handle.
   * stopPropagation prevents the drag hook from also firing.
   */
  const onHandleMouseDown = useCallback((e, edge) => {
    if (e.button !== 0) return
    e.stopPropagation()

    /* Capture the window's current bounding rect at resize start */
    const rect = e.currentTarget.closest('.window').getBoundingClientRect()
    resizing.current = {
      edge,
      startX: e.clientX,
      startY: e.clientY,
      startW: rect.width,
      startH: rect.height,
      startLeft: rect.left,
      startTop: rect.top,
    }
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    /**
     * handleMouseMove — adjusts size and/or position based on which edge is active.
     * For left/top edges the origin also shifts so the opposite side stays anchored.
     */
    const handleMouseMove = (e) => {
      if (!resizing.current) return
      const { edge, startX, startY, startW, startH, startLeft, startTop } = resizing.current
      const deltaX = e.clientX - startX
      const deltaY = e.clientY - startY

      /* Calculate new width based on edge direction flags */
      let newW = startW
      if (edge.dw === 1) newW = startW + deltaX       /* right edge grows rightward */
      if (edge.dx === -1) newW = startW - deltaX       /* left edge grows leftward */

      /* Calculate new height based on edge direction flags */
      let newH = startH
      if (edge.dh === 1) newH = startH + deltaY        /* bottom edge grows downward */
      if (edge.dy === -1) newH = startH - deltaY        /* top edge grows upward */

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
  }, [minSize, setPosition])

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

  return { size, resizeHandles }
}
