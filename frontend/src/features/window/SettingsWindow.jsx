import { useState } from 'react'
import Window from './Window'
import closeIcon from '@/assets/settings/settings_close.png'
import './SettingsWindow.css'

/**
 * SettingsWindow — Lavender-themed settings panel rendered inside the
 * generic draggable/resizable Window shell.
 *
 * Layout: 3-column grid (label | control | action) with 5 rows:
 *   1. API Key    — masked password input + Save
 *   2. Email      — text input + Save
 *   3. Password   — password input + Save
 *   4. Trading Style — dropdown select + Save
 *   5. Notifications — toggle slider (no action cell)
 *
 * Save handlers are stubs (console.log only) — database integration
 * will be added in a later phase.
 *
 * @param {Function} onClose  Called when the window's close button is clicked
 * @returns {JSX.Element}
 */
export default function SettingsWindow({ onClose }) {
  /* ── Local State ──
     Each setting field has its own piece of state so rows update independently. */
  const [apiKey, setApiKey] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tradingStyle, setTradingStyle] = useState('balanced')
  const [notifications, setNotifications] = useState(true)

  /* ── Stub Save Handlers ──
     Each row has its own save function. Currently they just log to the console;
     real persistence will be wired up when the backend is ready. */

  /** Save the API key (stub) */
  const handleSaveApiKey = () => {
    console.log('Save API Key:', apiKey)
  }

  /** Save the email address (stub) */
  const handleSaveEmail = () => {
    console.log('Save Email:', email)
  }

  /** Save the password (stub) */
  const handleSavePassword = () => {
    console.log('Save Password:', password)
  }

  /** Save the trading style preference (stub) */
  const handleSaveTradingStyle = () => {
    console.log('Save Trading Style:', tradingStyle)
  }

  return (
    <div className="settings-window-wrapper">
      <Window
        title="Settings"
        onClose={onClose}
        closeIcon={closeIcon}
        colorTokenPrefix="settings"
      >
        {/* ── Settings Grid ──
            3-column layout: label | control | action.
            Each row is a triplet of .settings-cell elements. */}
        <div className="settings-grid">

          {/* ── Row 1: API Key ── */}
          {/* Label */}
          <div className="settings-cell settings-label">API Key</div>
          {/* Control — masked password input so the key is hidden */}
          <div className="settings-cell">
            <input
              className="settings-input"
              type="password"
              placeholder="Enter API key…"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
            />
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveApiKey}>
              Save
            </button>
          </div>

          {/* ── Row 2: Email ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Email</div>
          {/* Control — standard text input */}
          <div className="settings-cell">
            <input
              className="settings-input"
              type="text"
              placeholder="Enter email…"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveEmail}>
              Save
            </button>
          </div>

          {/* ── Row 3: Password ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Password</div>
          {/* Control — password input for hidden entry */}
          <div className="settings-cell">
            <input
              className="settings-input"
              type="password"
              placeholder="Enter password…"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSavePassword}>
              Save
            </button>
          </div>

          {/* ── Row 4: Trading Style ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Trading Style</div>
          {/* Control — dropdown select with three strategy options */}
          <div className="settings-cell">
            <select
              className="settings-select"
              value={tradingStyle}
              onChange={e => setTradingStyle(e.target.value)}
            >
              <option value="balanced">Balanced</option>
              <option value="risk-averse">Risk-Averse</option>
              <option value="risk-aggressive">Risk-Aggressive</option>
            </select>
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveTradingStyle}>
              Save
            </button>
          </div>

          {/* ── Row 5: Notifications ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Notifications</div>
          {/* Control — CSS-only toggle switch (hidden checkbox + styled slider) */}
          <div className="settings-cell">
            <label className="settings-toggle">
              <input
                type="checkbox"
                checked={notifications}
                onChange={e => setNotifications(e.target.checked)}
              />
              {/* Pill-shaped track with sliding circular knob */}
              <span className="settings-toggle-slider" />
            </label>
          </div>
          {/* Action — empty cell to maintain grid alignment */}
          <div className="settings-cell" />

        </div>
      </Window>
    </div>
  )
}
