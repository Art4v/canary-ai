import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { useAuth } from '../../contexts/AuthContext.jsx'
import Window from './Window'
import closeIcon from '@/assets/portfolio/portfolio_close.png'
import './PortfolioWindow.css'

/**
 * PortfolioWindow — Live portfolio dashboard with real data from Supabase
 * and interactive stock price charts powered by Recharts.
 *
 * Layout (top to bottom):
 *   1. Summary card — total portfolio value, cash reserve, capital invested
 *   2. Stock charts — one LineChart per tracked ticker showing price history
 *   3. Holdings table — current positions with ticker, qty, avg price, est. value
 *   4. Footer strip — dark band at the bottom
 *
 * @param {string}   windowId         Unique identifier for snap system
 * @param {Function} onClose          Called when the window's X button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function PortfolioWindow({ windowId, onClose, onFocus, zIndex, initialPosition }) {
  /* ── Auth context — get the logged-in user's username and authFetch ── */
  const { user, authFetch } = useAuth()

  /* ── State ── */
  const [portfolio, setPortfolio] = useState(null)       // portfolio summary row
  const [holdings, setHoldings] = useState([])            // array of holding objects
  const [trackedTickers, setTrackedTickers] = useState([]) // currently tracked ticker symbols
  const [chartData, setChartData] = useState({})           // { TICKER: [ { timestamp, current_price } ] }
  const [loading, setLoading] = useState(true)             // initial load flag
  const [error, setError] = useState(null)                 // fetch error message

  /* ── Fetch all data on mount ── */
  useEffect(() => {
    if (!user?.username) {
      setLoading(false)
      return
    }

    /**
     * fetchAll — fetches portfolio summary, holdings, tracked tickers,
     * and price history for each tracked ticker in parallel where possible.
     */
    async function fetchAll() {
      try {
        setLoading(true)
        setError(null)

        /* Fetch portfolio summary, holdings, and tracked tickers in parallel.
           Portfolio and holdings are authenticated; /track is public. */
        const [portfolioRes, holdingsRes, trackedRes] = await Promise.all([
          authFetch(`/database/portfolios/${user.username}`),
          authFetch(`/database/holdings/${user.username}`),
          fetch('/track'),
        ])

        /* Parse portfolio summary — may be empty if user has no portfolio yet */
        const portfolioJson = await portfolioRes.json()
        if (portfolioJson.success && portfolioJson.data) {
          setPortfolio(portfolioJson.data)
        }

        /* Parse holdings list */
        const holdingsJson = await holdingsRes.json()
        if (holdingsJson.success && holdingsJson.data) {
          /* Normalise: backend may return a single object or an array */
          const holdingsArr = Array.isArray(holdingsJson.data)
            ? holdingsJson.data
            : [holdingsJson.data]
          setHoldings(holdingsArr)
        }

        /* Parse tracked tickers and fetch price history for each */
        const trackedJson = await trackedRes.json()
        const tickers = trackedJson.tracked || []
        setTrackedTickers(tickers)

        /* Fetch stock data for every tracked ticker in parallel */
        if (tickers.length > 0) {
          const stockPromises = tickers.map(async (ticker) => {
            const res = await fetch(`/stock-data/${ticker}`)
            const json = await res.json()
            return { ticker, data: json.success ? json.data : [] }
          })

          const results = await Promise.all(stockPromises)
          const dataMap = {}
          for (const { ticker, data } of results) {
            dataMap[ticker] = data
          }
          setChartData(dataMap)
        }
      } catch (err) {
        console.error('PortfolioWindow fetch error:', err)
        setError('Failed to load portfolio data.')
      } finally {
        setLoading(false)
      }
    }

    fetchAll()
  }, [user?.username])

  /**
   * formatTimestamp — shorten an ISO/yfinance timestamp to a readable
   * short date-time string for the chart X-axis.
   *
   * @param {string} ts  Raw timestamp string from the CSV
   * @returns {string}   Formatted time like "3/15 14:30"
   */
  function formatTimestamp(ts) {
    try {
      const d = new Date(ts)
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
    } catch {
      return ts
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
      title="Portfolio"
      onClose={onClose}
      closeIcon={closeIcon}
      colorTokenPrefix="portfolio"
      onFocus={onFocus}
      zIndex={zIndex}
      initialPosition={initialPosition}
    >
      {/* ── Loading / Error states ── */}
      {loading && <div className="portfolio-status">Loading portfolio data…</div>}
      {error && <div className="portfolio-status portfolio-error">{error}</div>}

      {!loading && (
        <>
          {/* ── Summary Card ──
              Shows real portfolio values from the database, or $0 defaults. */}
          <div className="portfolio-summary">
            <div className="portfolio-summary-left">
              <span className="portfolio-label">Total Portfolio Value</span>
              <span className="portfolio-value">
                {formatDollar(portfolio?.current_portfolio_value ?? 0)}
              </span>
              <span className="portfolio-detail">
                Cash Reserve: {formatDollar(portfolio?.cash_reserve ?? 0)}
              </span>
              <span className="portfolio-detail">
                Capital Invested: {formatDollar(portfolio?.total_capital_invested ?? 0)}
              </span>
            </div>
            <div className="portfolio-summary-right">
              <span className="portfolio-market-status">
                {trackedTickers.length > 0
                  ? `Tracking ${trackedTickers.length} stock${trackedTickers.length > 1 ? 's' : ''}`
                  : 'No stocks tracked'}
              </span>
            </div>
          </div>

          {/* ── Stock Charts Section ──
              One Recharts LineChart per tracked ticker, in a scrollable container. */}
          <div className="portfolio-charts-section">
            {trackedTickers.length === 0 ? (
              <div className="portfolio-empty">No stocks being tracked</div>
            ) : (
              trackedTickers.map((ticker) => {
                /* Downsample to at most 200 points for chart performance */
                const raw = chartData[ticker] || []
                const step = Math.max(1, Math.floor(raw.length / 200))
                const sampled = raw.filter((_, i) => i % step === 0)

                return (
                  <div key={ticker} className="portfolio-chart-card">
                    <h3 className="portfolio-chart-title">{ticker}</h3>
                    {sampled.length === 0 ? (
                      <div className="portfolio-empty">Waiting for data…</div>
                    ) : (
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={sampled}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.15)" />
                          <XAxis
                            dataKey="timestamp"
                            tickFormatter={formatTimestamp}
                            tick={{ fontSize: 10, fill: 'var(--color-text)' }}
                            interval="preserveStartEnd"
                          />
                          <YAxis
                            domain={['auto', 'auto']}
                            tick={{ fontSize: 10, fill: 'var(--color-text)' }}
                            tickFormatter={(v) => `$${v.toFixed(0)}`}
                          />
                          <Tooltip
                            formatter={(value) => [`$${Number(value).toFixed(2)}`, 'Price']}
                            labelFormatter={formatTimestamp}
                            contentStyle={{
                              background: 'var(--win-dark)',
                              border: 'none',
                              borderRadius: '8px',
                              color: 'var(--color-text)',
                            }}
                          />
                          <Line
                            type="monotone"
                            dataKey="current_price"
                            stroke="#8e896b"
                            strokeWidth={2}
                            dot={false}
                            activeDot={{ r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                )
              })
            )}
          </div>

          {/* ── Holdings Table ──
              Lists current positions: ticker, quantity, avg buy price, est. value. */}
          <div className="portfolio-holdings-section">
            <h3 className="portfolio-section-title">Holdings</h3>
            {holdings.length === 0 ? (
              <div className="portfolio-empty">No holdings yet</div>
            ) : (
              <table className="portfolio-holdings-table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Quantity</th>
                    <th>Avg Buy Price</th>
                    <th>Est. Value</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h, i) => (
                    <tr key={h.holding_id || i}>
                      <td className="portfolio-holding-ticker">{h.ticker}</td>
                      <td>{Number(h.quantity).toLocaleString()}</td>
                      <td>{formatDollar(h.average_buy_price)}</td>
                      <td>{formatDollar(Number(h.quantity) * Number(h.average_buy_price))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* ── Footer Strip ──
              Dark band at the bottom matching the reference design. */}
          <div className="portfolio-footer" />
        </>
      )}
    </Window>
  )
}
