import { useState, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext.jsx'
import Window from './Window'
import closeIcon from '@/assets/settings/settings_close.png'
import './SettingsWindow.css'

/**
 * SettingsWindow — Lavender-themed settings panel rendered inside the
 * generic draggable/resizable Window shell.
 *
 * Layout: 3-column grid (label | control | action) with 6 rows:
 *   1. Username   — text input + Save
 *   2. API Key    — masked password input + Save
 *   3. Email      — text input + Save
 *   4. Password   — current + new password fields + Save
 *   5. Trading Style — dropdown select + Save
 *   6. Notifications — toggle slider (saves on toggle, no button)
 *
 * Each Save button calls PUT /database/users/{username} to persist
 * the change to Supabase. Password changes require verifying the
 * current password via POST /database/users/login before updating.
 *
 * Inline success/error feedback is shown per-row after each save.
 *
 * @param {string}   windowId         Unique identifier for snap system
 * @param {Function} onClose          Called when the window's close button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function SettingsWindow({ windowId, onClose, onFocus, zIndex, initialPosition }) {
  /* Auth context — read current user data, authFetch for authenticated PUT calls,
     and updateUser to sync local state after saves */
  const { user, updateUser, authFetch } = useAuth()

  /* ── Local State ──
     Each setting field has its own piece of state so rows update independently. */
  const [username, setUsername] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [email, setEmail] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')   // verify before changing
  const [newPassword, setNewPassword] = useState('')            // the new password to set
  const [tradingStyle, setTradingStyle] = useState('balanced')
  const [notifications, setNotifications] = useState(true)

  /* Per-row feedback messages — { type: 'success'|'error', text: string } or null */
  const [feedback, setFeedback] = useState({
    username: null,
    apiKey: null,
    email: null,
    password: null,
    tradingStyle: null,
    notifications: null,
  })

  /* ── Pre-fill fields from AuthContext user data ──
     Runs once when the component mounts or when the user object changes. */
  useEffect(() => {
    if (user) {
      setUsername(user.username || '')
      setApiKey(user.api_key || '')
      setEmail(user.email || '')
      setTradingStyle(user.trading_style || 'balanced')
      setNotifications(user.notifications !== undefined ? user.notifications : true)
    }
  }, [user])

  /**
   * setRowFeedback — helper to set feedback for a specific row.
   * Auto-clears the feedback after 3 seconds.
   *
   * @param {string} row     Row key (e.g. 'username', 'email')
   * @param {string} type    'success' or 'error'
   * @param {string} text    Message to display
   */
  const setRowFeedback = (row, type, text) => {
    setFeedback(prev => ({ ...prev, [row]: { type, text } }))
    /* Auto-clear after 3 seconds */
    setTimeout(() => {
      setFeedback(prev => ({ ...prev, [row]: null }))
    }, 3000)
  }

  /**
   * saveField — generic helper that PUTs a partial update to the backend.
   * On success, updates the AuthContext user and shows a success message.
   * On failure, shows an inline error message.
   *
   * @param {string} rowKey      Feedback row key (e.g. 'username')
   * @param {object} payload     Fields to send in the PUT body
   * @param {string} [targetUsername]  Username to update (defaults to current user)
   * @returns {boolean} true if the save succeeded
   */
  const saveField = async (rowKey, payload, targetUsername) => {
    const uname = targetUsername || user?.username
    if (!uname) {
      setRowFeedback(rowKey, 'error', 'Not logged in')
      return false
    }

    try {
      const res = await authFetch(`/database/users/${encodeURIComponent(uname)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await res.json()

      if (result.success) {
        /* Merge the updated fields into the AuthContext user object */
        updateUser(result.data)
        setRowFeedback(rowKey, 'success', 'Saved!')
        return true
      } else {
        setRowFeedback(rowKey, 'error', result.error || 'Save failed')
        return false
      }
    } catch {
      setRowFeedback(rowKey, 'error', 'Unable to connect to server')
      return false
    }
  }

  /* ── Save Handlers ──
     Each row has its own save function that validates locally
     then calls saveField with the appropriate payload. */

  /** Save the username — also updates the lookup key for future PUTs */
  const handleSaveUsername = async () => {
    if (!username.trim()) {
      setRowFeedback('username', 'error', 'Username cannot be empty')
      return
    }
    /* Use the *current* username from context as the URL param,
       since we're changing it to a new value */
    await saveField('username', { username: username.trim() }, user?.username)
  }

  /** Save the API key */
  const handleSaveApiKey = async () => {
    await saveField('apiKey', { api_key: apiKey })
  }

  /** Save the email address */
  const handleSaveEmail = async () => {
    if (!email.trim()) {
      setRowFeedback('email', 'error', 'Email cannot be empty')
      return
    }
    await saveField('email', { email: email.trim() })
  }

  /**
   * Save password — requires verifying the current password first.
   * 1. POST /database/users/login with { email, currentPassword } to verify
   * 2. If valid, PUT the new password via saveField
   */
  const handleSavePassword = async () => {
    if (!currentPassword) {
      setRowFeedback('password', 'error', 'Enter your current password')
      return
    }
    if (!newPassword) {
      setRowFeedback('password', 'error', 'Enter a new password')
      return
    }
    if (newPassword.length < 4) {
      setRowFeedback('password', 'error', 'New password is too short')
      return
    }

    try {
      /* Step 1: verify current password via the login endpoint */
      const verifyRes = await fetch('/database/users/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: user?.email, password: currentPassword }),
      })
      const verifyResult = await verifyRes.json()

      if (!verifyResult.success) {
        setRowFeedback('password', 'error', 'Current password is incorrect')
        return
      }

      /* Step 2: set the new password */
      const ok = await saveField('password', { password: newPassword })
      if (ok) {
        /* Clear both fields on success */
        setCurrentPassword('')
        setNewPassword('')
      }
    } catch {
      setRowFeedback('password', 'error', 'Unable to connect to server')
    }
  }

  /** Save the trading style preference */
  const handleSaveTradingStyle = async () => {
    await saveField('tradingStyle', { trading_style: tradingStyle })
  }

  /**
   * handleToggleNotifications — save immediately when the toggle changes.
   * No separate Save button needed for this row.
   *
   * @param {boolean} checked  New toggle state
   */
  const handleToggleNotifications = async (checked) => {
    setNotifications(checked)
    await saveField('notifications', { notifications: checked })
  }

  /**
   * renderFeedback — render inline success/error text for a given row.
   *
   * @param {string} rowKey  Feedback row key
   * @returns {JSX.Element|null}
   */
  const renderFeedback = (rowKey) => {
    const fb = feedback[rowKey]
    if (!fb) return null
    return (
      <span className={`settings-feedback settings-feedback--${fb.type}`}>
        {fb.text}
      </span>
    )
  }

  return (
    <div className="settings-window-wrapper">
      <Window
        windowId={windowId}
        title="Settings"
        onClose={onClose}
        closeIcon={closeIcon}
        colorTokenPrefix="settings"
        onFocus={onFocus}
        zIndex={zIndex}
        initialPosition={initialPosition}
      >
        {/* ── Settings Grid ──
            3-column layout: label | control | action.
            Each row is a triplet of .settings-cell elements. */}
        <div className="settings-grid">

          {/* ── Row 1: Username ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Username</div>
          {/* Control — text input for changing the display username */}
          <div className="settings-cell">
            <input
              className="settings-input"
              type="text"
              placeholder="Enter new username…"
              value={username}
              onChange={e => setUsername(e.target.value)}
            />
            {renderFeedback('username')}
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveUsername}>
              Save
            </button>
          </div>

          {/* ── Row 2: API Key ── */}
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
            {renderFeedback('apiKey')}
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveApiKey}>
              Save
            </button>
          </div>

          {/* ── Row 3: Email ── */}
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
            {renderFeedback('email')}
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveEmail}>
              Save
            </button>
          </div>

          {/* ── Row 4: Password ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Password</div>
          {/* Control — two password fields: current (for verification) + new */}
          <div className="settings-cell">
            <input
              className="settings-input"
              type="password"
              placeholder="Current password…"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
            />
            <input
              className="settings-input settings-input--second"
              type="password"
              placeholder="New password…"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
            />
            {renderFeedback('password')}
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSavePassword}>
              Save
            </button>
          </div>

          {/* ── Row 5: Trading Style ── */}
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
            {renderFeedback('tradingStyle')}
          </div>
          {/* Action — per-row save button */}
          <div className="settings-cell">
            <button className="settings-save-btn" onClick={handleSaveTradingStyle}>
              Save
            </button>
          </div>

          {/* ── Row 6: Notifications ── */}
          {/* Label */}
          <div className="settings-cell settings-label">Notifications</div>
          {/* Control — CSS-only toggle switch (hidden checkbox + styled slider).
              Saves immediately on toggle via handleToggleNotifications. */}
          <div className="settings-cell">
            <label className="settings-toggle">
              <input
                type="checkbox"
                checked={notifications}
                onChange={e => handleToggleNotifications(e.target.checked)}
              />
              {/* Pill-shaped track with sliding circular knob */}
              <span className="settings-toggle-slider" />
            </label>
            {renderFeedback('notifications')}
          </div>
          {/* Action — empty cell to maintain grid alignment */}
          <div className="settings-cell" />

        </div>
      </Window>
    </div>
  )
}
