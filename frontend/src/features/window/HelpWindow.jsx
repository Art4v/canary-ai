import Window from './Window'
import closeIcon from '@/assets/settings/settings_close.png'
import './HelpWindow.css'

/**
 * HelpWindow — Purple-themed help panel rendered inside the generic
 * draggable/resizable Window shell.
 *
 * Displays a step-by-step user guide for the Canary AI application,
 * covering 8 major sections from Getting Started through Theme switching.
 *
 * @param {string}   windowId         Unique identifier for snap system
 * @param {Function} onClose          Called when the window's close button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function HelpWindow({ windowId, onClose, onFocus, zIndex, initialPosition }) {
  return (
    <div className="help-window-wrapper">
      <Window
        windowId={windowId}
        title="Help"
        onClose={onClose}
        closeIcon={closeIcon}
        colorTokenPrefix="help"
        onFocus={onFocus}
        zIndex={zIndex}
        initialPosition={initialPosition}
      >
        {/* ── Help Content ──
            Scrollable body containing all 8 guide sections. */}
        <div className="help-content">

          {/* Welcome intro line */}
          <p className="help-intro">
            Welcome to Canary AI — your AI-powered investment assistant. Follow the guide below to get started.
          </p>

          {/* ── Section 1: Getting Started ── */}
          <div className="help-section">
            <h3>1. Getting Started</h3>
            <ol className="help-steps">
              <li className="help-step">
                Navigate to the landing page (the tree scene with a nest).
              </li>
              <li className="help-step">
                Click one of the glowing eggs in the nest to go to the Register page and create a new account (username, email, and password).
              </li>
              <li className="help-step">
                After registering, click the other egg or follow the link to the Login page and sign in with your credentials.
              </li>
              <li className="help-step">
                Once authenticated you are taken to the dashboard — the full Canary AI desktop environment.
              </li>
            </ol>
          </div>

          {/* ── Section 2: Navigating the Desktop ── */}
          <div className="help-section">
            <h3>2. Navigating the Desktop</h3>
            <ol className="help-steps">
              <li className="help-step">
                The <strong>Dock</strong> is the cloud-shaped bar at the bottom centre of the screen. It contains five icons for each main window.
              </li>
              <li className="help-step">
                Click any dock icon to open its window. Click the same icon again to close it. Multiple windows can be open at once.
              </li>
              <li className="help-step">
                The two <strong>Corner Launchers</strong> (bottom-left and bottom-right) give quick access to all five windows without moving your cursor to the central dock.
              </li>
              <li className="help-step">
                Use the <strong>Clear All</strong> button (available in the corner launchers) to close every open window at once.
              </li>
            </ol>
          </div>

          {/* ── Section 3: Chat with Canary AI ── */}
          <div className="help-section">
            <h3>3. Chat with Canary AI</h3>
            <ol className="help-steps">
              <li className="help-step">
                Open the <strong>Chat</strong> window (speech-bubble icon). The AI assistant greets you and can answer investment questions.
              </li>
              <li className="help-step">
                Type your message in the input box at the bottom and press <kbd>Enter</kbd> or click the send arrow.
              </li>
              <li className="help-step">
                Canary AI remembers your conversation across sessions using its persistent memory — it will tailor responses to your stated preferences and portfolio context.
              </li>
              <li className="help-step">
                Click the <strong>"+"</strong> button at the top of the chat to start a fresh conversation and clear the current session memory.
              </li>
              <li className="help-step">
                Set your <strong>trading style</strong> in Settings (balanced / risk-averse / risk-aggressive) to influence how the AI frames its advice.
              </li>
            </ol>
          </div>

          {/* ── Section 4: Portfolio Window ── */}
          <div className="help-section">
            <h3>4. Portfolio Window</h3>
            <ol className="help-steps">
              <li className="help-step">
                Open the <strong>Portfolio</strong> window (chart icon). The summary card at the top shows your <em>Total Value</em>, <em>Cash Reserve</em>, and <em>Capital Invested</em>.
              </li>
              <li className="help-step">
                Below the summary, interactive stock charts display price history for each holding. Hover over a chart to see the exact price at any point in time.
              </li>
              <li className="help-step">
                The <strong>Holdings table</strong> lists every position: ticker symbol, quantity held, average buy price, and current market value.
              </li>
              <li className="help-step">
                Data refreshes automatically each time the window is opened.
              </li>
            </ol>
          </div>

          {/* ── Section 5: Trades Window ── */}
          <div className="help-section">
            <h3>5. Trades Window</h3>
            <ol className="help-steps">
              <li className="help-step">
                Open the <strong>Trades</strong> window (arrow icon). Use the <strong>Buy / Sell</strong> toggle at the top to switch between order types.
              </li>
              <li className="help-step">
                Enter the ticker symbol and the number of shares you wish to trade in the order form.
              </li>
              <li className="help-step">
                Click <strong>Execute Order</strong> to submit the trade. The portfolio and holdings are updated immediately on success.
              </li>
              <li className="help-step">
                Trades are logged in the transaction history and reflected in your portfolio summary.
              </li>
            </ol>
          </div>

          {/* ── Section 6: Settings Window ── */}
          <div className="help-section">
            <h3>6. Settings Window</h3>
            <ol className="help-steps">
              <li className="help-step">
                Open the <strong>Settings</strong> window (gear icon) to manage your account details.
              </li>
              <li className="help-step">
                Update your <strong>Username</strong>, <strong>Email</strong>, or <strong>Password</strong> by filling in the relevant row and clicking <em>Save</em>. Password changes require entering your current password first.
              </li>
              <li className="help-step">
                Enter your <strong>API Key</strong> (used by Canary AI to access market data on your behalf) and save it. The key is stored securely as a bcrypt hash.
              </li>
              <li className="help-step">
                Choose your <strong>Trading Style</strong> from the dropdown: <em>Balanced</em>, <em>Risk-Averse</em>, or <em>Risk-Aggressive</em>. This tells the AI how to frame recommendations.
              </li>
              <li className="help-step">
                Toggle <strong>Notifications</strong> on or off — changes are saved instantly without needing a Save button.
              </li>
            </ol>
          </div>

          {/* ── Section 7: Window Management ── */}
          <div className="help-section">
            <h3>7. Window Management</h3>
            <ol className="help-steps">
              <li className="help-step">
                <strong>Drag</strong> any window by clicking and holding its coloured header bar, then moving the mouse.
              </li>
              <li className="help-step">
                <strong>Resize</strong> a window by dragging any of its edges or corners.
              </li>
              <li className="help-step">
                <strong>Snap</strong> windows together by dragging one close to the edge of another — a ghost preview appears to show where it will snap. Release to attach the windows.
              </li>
              <li className="help-step">
                Snapped windows move as a <strong>group</strong>: dragging one snapped window moves the entire cluster together.
              </li>
              <li className="help-step">
                <strong>Double-click</strong> the seam between two snapped windows to unsnap them and make them independent again.
              </li>
              <li className="help-step">
                Click any window to bring it to the front (raise its z-index above the others).
              </li>
            </ol>
          </div>

          {/* ── Section 8: Theme ── */}
          <div className="help-section">
            <h3>8. Theme</h3>
            <ol className="help-steps">
              <li className="help-step">
                A <strong>Dark / Light</strong> mode toggle is located in one of the screen corners.
              </li>
              <li className="help-step">
                Click it to switch between dark and light colour themes. Your preference is applied instantly across the entire UI.
              </li>
            </ol>
          </div>

        </div>
      </Window>
    </div>
  )
}
