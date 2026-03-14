import Window from './Window'
import closeIcon from '@/assets/portfolio/portfolio_close.png'
import './PortfolioWindow.css'

/**
 * PortfolioWindow — Portfolio section content wrapped in the generic Window shell.
 *
 * Layout (top to bottom):
 *   1. Summary card — full-width cream card showing total portfolio value,
 *      percentage change, and market status
 *   2. Graph cards — two equal-width placeholder cards for future chart widgets
 *   3. Footer strip — darker band at the very bottom of the window
 *
 * All values are hardcoded placeholders for now.
 *
 * @param {Function} onClose  Called when the window's X button is clicked
 * @returns {JSX.Element}
 */
export default function PortfolioWindow({ onClose }) {
  return (
    <Window
      title="Portfolio"
      onClose={onClose}
      closeIcon={closeIcon}
      colorTokenPrefix="portfolio"
    >
      {/* ── Summary Card ──
          Full-width card split into left (value info) and right (market status).
          Sits at the top of the window body. */}
      <div className="portfolio-summary">
        {/* Left side: label, large dollar value, and percent change */}
        <div className="portfolio-summary-left">
          <span className="portfolio-label">Total portfolio value</span>
          <span className="portfolio-value">$100,000</span>
          <span className="portfolio-change">+2.5%</span>
        </div>
        {/* Right side: current market status indicator */}
        <div className="portfolio-summary-right">
          <span className="portfolio-market-status">Market Open</span>
        </div>
      </div>

      {/* ── Graph Cards ──
          Two equal-width placeholder cards for future chart/graph widgets.
          Displayed side by side with a gap between them. */}
      <div className="portfolio-graphs">
        <div className="portfolio-graph-card">example graph</div>
        <div className="portfolio-graph-card">example graph</div>
      </div>

      {/* ── Footer Strip ──
          Darker band at the bottom matching the reference design. */}
      <div className="portfolio-footer" />
    </Window>
  )
}
