import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext.jsx'
import Window from './Window'
import closeIcon from '@/assets/trades/close.png'
import './TradesWindow.css'

/**
 * TradesWindow — Portfolio dashboard with deposit/withdraw functionality.
 *
 * Layout (top to bottom):
 *   1. Portfolio metrics card — current value, cash reserve, capital invested
 *   2. Deposit / Withdraw section — dollar input + action buttons
 *   3. Footer strip
 *
 * @param {string}   windowId         Unique identifier for snap system
 * @param {Function} onClose          Called when the window's X button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function TradesWindow({ windowId, onClose, onFocus, zIndex, initialPosition }) {
  /* ── Auth context — get the logged-in user's username and authFetch ── */
  const { user, authFetch } = useAuth()

  /* ── State ── */
  const [portfolio, setPortfolio] = useState(null)         // portfolio summary row
  const [loading, setLoading] = useState(true)              // initial load flag
  const [error, setError] = useState(null)                  // fetch error message
  const [amount, setAmount] = useState('')                   // deposit/withdraw input value
  const [actionError, setActionError] = useState(null)       // inline error for deposit/withdraw
  const [actionLoading, setActionLoading] = useState(false)  // disables buttons during request

  /* ── Fetch portfolio + transactions on mount, then poll every 10 s ── */
  useEffect(() => {
    if (!user?.username) {
      setLoading(false)
      return
    }

    /**
     * fetchAll — fetches portfolio summary from the database.
     * Called immediately on mount and then every 10 seconds via setInterval
     * so that changes made elsewhere (e.g. via chat) appear automatically.
     *
     * @param {boolean} isInitial  True on the first call to show the loading spinner
     */
    async function fetchAll(isInitial = false) {
      try {
        if (isInitial) setLoading(true)
        setError(null)

        /* Fetch portfolio summary (authenticated) */
        const portfolioRes = await authFetch(`/database/portfolios/${user.username}`)

        /* Parse portfolio summary */
        const portfolioJson = await portfolioRes.json()
        if (portfolioJson.success && portfolioJson.data) {
          setPortfolio(portfolioJson.data)
        }
      } catch (err) {
        console.error('TradesWindow fetch error:', err)
        setError('Failed to load trades data.')
      } finally {
        if (isInitial) setLoading(false)
      }
    }

    /* Initial fetch with loading spinner */
    fetchAll(true)

    /* Poll every 10 seconds so new transactions (e.g. from chat) appear automatically */
    const intervalId = setInterval(() => fetchAll(false), 10_000)

    /* Clean up the interval when the component unmounts or username changes */
    return () => clearInterval(intervalId)
  }, [user?.username])

  /**
   * handleDeposit — POST to deposit endpoint, update portfolio state on success.
   */
  async function handleDeposit() {
    const numAmount = parseFloat(amount)
    if (!numAmount || numAmount <= 0) {
      setActionError('Enter a positive dollar amount')
      return
    }

    setActionLoading(true)
    setActionError(null)

    try {
      const res = await authFetch(`/database/portfolios/${user.username}/deposit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: numAmount }),
      })
      const json = await res.json()

      if (json.success && json.data) {
        setPortfolio(json.data)
        setAmount('')
      } else {
        setActionError(json.error || 'Deposit failed')
      }
    } catch (err) {
      console.error('Deposit error:', err)
      setActionError('Network error — try again')
    } finally {
      setActionLoading(false)
    }
  }

  /**
   * handleWithdraw — POST to withdraw endpoint, update portfolio state on success.
   * Shows inline error if insufficient funds.
   */
  async function handleWithdraw() {
    const numAmount = parseFloat(amount)
    if (!numAmount || numAmount <= 0) {
      setActionError('Enter a positive dollar amount')
      return
    }

    setActionLoading(true)
    setActionError(null)

    try {
      const res = await authFetch(`/database/portfolios/${user.username}/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: numAmount }),
      })
      const json = await res.json()

      if (json.success && json.data) {
        setPortfolio(json.data)
        setAmount('')
      } else {
        setActionError(json.error || 'Withdrawal failed')
      }
    } catch (err) {
      console.error('Withdraw error:', err)
      setActionError('Network error — try again')
    } finally {
      setActionLoading(false)
    }
  }

  /**
   * formatDollar — format a number as a USD string with commas.
   *
   * @param {number|string} val  Numeric value
   * @returns {string}           e.g. "$12,345.67"
   */
  function formatDollar(val) {
    const num = Number(val) || 0
    return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  return (
    <Window
      windowId={windowId}
      title="Trades"
      onClose={onClose}
      closeIcon={closeIcon}
      colorTokenPrefix="trades"
      onFocus={onFocus}
      zIndex={zIndex}
      initialPosition={initialPosition}
    >
      {/* ── Loading / Error states ── */}
      {loading && <div className="trades-status">Loading trades data…</div>}
      {error && <div className="trades-status trades-error">{error}</div>}

      {!loading && (
        <>
          {/* ── Portfolio Metrics Card ──
              Shows real portfolio values from the database, or $0 defaults. */}
          <div className="trades-summary">
            <div className="trades-summary-col">
              <span className="trades-label">Total Portfolio Value</span>
              <span className="trades-value">
                {formatDollar(portfolio?.current_portfolio_value ?? 0)}
              </span>
            </div>
            <div className="trades-summary-col">
              <span className="trades-label">Cash Reserve</span>
              <span className="trades-detail">
                {formatDollar(portfolio?.cash_reserve ?? 0)}
              </span>
            </div>
            <div className="trades-summary-col">
              <span className="trades-label">Capital Invested</span>
              <span className="trades-detail">
                {formatDollar(portfolio?.total_capital_invested ?? 0)}
              </span>
            </div>
          </div>

          {/* ── Deposit / Withdraw Section ──
              Dollar input with two action buttons for cash management. */}
          <div className="trades-cash-section">
            <div className="trades-cash-row">
              <input
                type="number"
                className="trades-cash-input"
                placeholder="$ Amount"
                value={amount}
                onChange={(e) => {
                  setAmount(e.target.value)
                  setActionError(null)
                }}
                min="0"
                step="0.01"
              />
              <button
                className="trades-action-btn trades-action-btn--deposit"
                onClick={handleDeposit}
                disabled={actionLoading}
              >
                {actionLoading ? '…' : 'Deposit'}
              </button>
              <button
                className="trades-action-btn trades-action-btn--withdraw"
                onClick={handleWithdraw}
                disabled={actionLoading}
              >
                {actionLoading ? '…' : 'Withdraw'}
              </button>
            </div>
            {/* Inline error message for deposit/withdraw validation */}
            {actionError && (
              <div className="trades-inline-error">{actionError}</div>
            )}
          </div>

          {/* ── Footer Strip ──
              Dark band at the bottom matching the reference design. */}
          <div className="trades-footer" />
        </>
      )}
    </Window>
  )
}
