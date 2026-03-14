import { useState } from 'react'
import Window from './Window'
import closeIcon from '@/assets/trades/close.png'
import './TradesWindow.css'

/**
 * TradesWindow — Trades section content wrapped in the generic Window shell.
 *
 * Layout (top to bottom):
 *   1. Buy / Sell toggle — two equal-width buttons; active gets primary color
 *   2. Content area — empty flex region (placeholder for future order form)
 *   3. "Execute Order" button — puffy 3D style matching dock button aesthetics
 *
 * @param {Function} onClose          Called when the window's X button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function TradesWindow({ onClose, onFocus, zIndex, initialPosition }) {
  /* Track whether the user has selected "buy" or "sell" mode */
  const [side, setSide] = useState('buy')

  return (
    <Window
      title="Trades"
      onClose={onClose}
      closeIcon={closeIcon}
      colorTokenPrefix="trades"
      onFocus={onFocus}
      zIndex={zIndex}
      initialPosition={initialPosition}
    >
      {/* ── Buy / Sell Toggle ──
          Two buttons splitting the width equally. The active side uses
          the trades primary color; the inactive side uses the lighter shade. */}
      <div className="trades-toggle">
        <button
          className={`trades-toggle-btn${side === 'buy' ? ' trades-toggle-btn--active' : ''}`}
          onClick={() => setSide('buy')}
        >
          Buy
        </button>
        <button
          className={`trades-toggle-btn${side === 'sell' ? ' trades-toggle-btn--active' : ''}`}
          onClick={() => setSide('sell')}
        >
          Sell
        </button>
      </div>

      {/* ── Content Area ──
          Empty placeholder — will hold order details, asset picker, etc. */}
      <div className="trades-content" />

      {/* ── Execute Order Button ──
          Puffy 3D button matching the dock button aesthetic.
          Centered at the bottom of the window. */}
      <div className="trades-footer">
        <button className="trades-execute-btn">
          Execute Order
        </button>
      </div>
    </Window>
  )
}
