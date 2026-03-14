import { useState, useCallback, useEffect, useRef } from 'react'

/**
 * useDrag — custom hook for making an element draggable by its header.
 *
 * Tracks `{ x, y }` position state. On `mousedown` over the drag handle,
 * records the pointer offset relative to the element, then follows the cursor
 * on `mousemove` until `mouseup`. Position is clamped so the window can't
 * be dragged outside the viewport.
 *
 * @param {{ x: number, y: number }} initialPosition  Starting top-left coords
 * @param {{ width: number, height: number }} size     Current element dimensions (for clamping)
 * @returns {{ position, onMouseDown }}
 *   - position  `{ x, y }` — current top-left position in px
 *   - onMouseDown  attach to the drag-handle's onMouseDown
 */
export default function useDrag(initialPosition, size) {
  /* Current position of the draggable element */
  const [position, setPosition] = useState(initialPosition)

  /* Whether a drag operation is currently in progress */
  const dragging = useRef(false)

  /* Pointer offset from element top-left recorded at drag start */
  const offset = useRef({ x: 0, y: 0 })

  /* Store latest size in a ref so mousemove always has the current value */
  const sizeRef = useRef(size)
  useEffect(() => { sizeRef.current = size }, [size])

  /**
   * handleMouseDown — initiates the drag.
   * Records the offset between the mouse and the element's top-left corner
   * and disables text selection on the body for a smooth drag experience.
   */
  const onMouseDown = useCallback((e) => {
    /* Only respond to primary (left) mouse button */
    if (e.button !== 0) return
    dragging.current = true
    offset.current = {
      x: e.clientX - e.currentTarget.closest('.window').getBoundingClientRect().left,
      y: e.clientY - e.currentTarget.closest('.window').getBoundingClientRect().top,
    }
    /* Prevent text selection while dragging */
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    /**
     * handleMouseMove — updates position while dragging.
     * Clamps x/y so the window stays fully within the viewport.
     */
    const handleMouseMove = (e) => {
      if (!dragging.current) return
      const { width, height } = sizeRef.current
      const x = Math.min(Math.max(0, e.clientX - offset.current.x), window.innerWidth - width)
      const y = Math.min(Math.max(0, e.clientY - offset.current.y), window.innerHeight - height)
      setPosition({ x, y })
    }

    /**
     * handleMouseUp — ends the drag and restores text selection.
     */
    const handleMouseUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.userSelect = ''
    }

    /* Attach listeners to document so drag continues even if cursor leaves the element */
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  return { position, setPosition, onMouseDown }
}
