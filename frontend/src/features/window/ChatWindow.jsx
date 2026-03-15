import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../../contexts/AuthContext.jsx'
import Window from './Window'
import closeIcon from '@/assets/chat/chat_close.png'
import plusIcon from '@/assets/chat/chat_plus.png'
import { Send } from 'lucide-react'
import './ChatWindow.css'

/**
 * Greeting message shown when a new conversation starts.
 * This is the only pre-populated message — all subsequent messages
 * come from the backend chat API.
 */
const GREETING_MESSAGE = {
  id: 1,
  sender: 'bot',
  text: "hey! i'm canary ai, your investment preference assistant. let's get your portfolio set up — what stocks are you looking to hold onto?",
  timestamp: Date.now(),
}

/**
 * ChatWindow — AI chat interface wired to the backend POST /chat endpoint.
 *
 * Layout (top to bottom):
 *   1. Scrollable message area — alternating bot/user speech bubbles with avatars
 *   2. Input bar — text field, new-conversation "+" button, and send star-icon button
 *
 * On mount, shows a single greeting message from the bot.
 * User messages are sent to POST /chat with the logged-in username,
 * and the bot's reply is displayed when it arrives.
 * A typing indicator ("...") is shown while waiting for the API response.
 * Preference updates from the bot are shown as [check] system messages.
 *
 * @param {string}   windowId         Unique identifier for snap system
 * @param {Function} onClose          Called when the window's X button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function ChatWindow({ windowId, onClose, onFocus, zIndex, initialPosition }) {
  /* Auth context — need the username to send with chat messages */
  const { user } = useAuth()

  /* Chat message history — starts with a single bot greeting */
  const [messages, setMessages] = useState([GREETING_MESSAGE])

  /* Controlled text input value */
  const [inputValue, setInputValue] = useState('')

  /* Whether we're waiting for the backend to respond */
  const [isLoading, setIsLoading] = useState(false)

  /* Ref anchored at the bottom of the messages list for auto-scrolling */
  const messagesEndRef = useRef(null)

  /**
   * Auto-scroll to the newest message whenever the messages array changes.
   * Uses smooth scrolling for a polished feel.
   */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  /**
   * handleSend — sends the user's message to the backend chat API.
   *
   * 1. Appends the user message to the local messages array
   * 2. Shows a typing indicator
   * 3. POSTs to /chat with { message, username }
   * 4. On success, appends the bot's reply and any preference update messages
   * 5. On failure, appends an error message from the bot
   */
  const handleSend = async () => {
    const trimmed = inputValue.trim()
    if (!trimmed || isLoading) return

    /* Get the username from AuthContext */
    const username = user?.username
    if (!username) {
      /* Not logged in — show an error message */
      setMessages(prev => [
        ...prev,
        {
          id: Date.now(),
          sender: 'bot',
          text: 'please log in first so i can save your preferences!',
          timestamp: Date.now(),
        },
      ])
      return
    }

    /* Append the user message immediately */
    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: trimmed,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setInputValue('')
    setIsLoading(true)

    try {
      /* POST the message to the backend chat endpoint */
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, username }),
      })
      const result = await res.json()

      if (result.success) {
        const { reply, preferences_updated } = result.data

        /* Build an array of new messages to append */
        const newMessages = []

        /* Add system messages for any preference updates */
        if (preferences_updated && Object.keys(preferences_updated).length > 0) {
          for (const [field, value] of Object.entries(preferences_updated)) {
            const displayValue = Array.isArray(value) ? value.join(', ') : String(value)
            newMessages.push({
              id: Date.now() + Math.random(),
              sender: 'system',
              text: `\u2713 ${field}: ${displayValue}`,
              timestamp: Date.now(),
            })
          }
        }

        /* Add the bot's reply */
        newMessages.push({
          id: Date.now() + 1,
          sender: 'bot',
          text: reply,
          timestamp: Date.now(),
        })

        setMessages(prev => [...prev, ...newMessages])
      } else {
        /* Backend returned an error — show it as a bot message */
        setMessages(prev => [
          ...prev,
          {
            id: Date.now() + 1,
            sender: 'bot',
            text: `oops, something went wrong: ${result.error || 'unknown error'}`,
            timestamp: Date.now(),
          },
        ])
      }
    } catch {
      /* Network error — show a connection failure message */
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + 1,
          sender: 'bot',
          text: "can't reach the server right now — try again in a sec",
          timestamp: Date.now(),
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  /**
   * handleNewConversation — resets the chat to a fresh greeting and
   * clears the server-side session via POST /chat/reset.
   *
   * Triggered by the "+" button in the input bar.
   */
  const handleNewConversation = async () => {
    /* Reset local state immediately for responsiveness */
    setMessages([{ ...GREETING_MESSAGE, id: Date.now(), timestamp: Date.now() }])
    setInputValue('')

    /* Clear the server-side session if we have a username */
    const username = user?.username
    if (username) {
      try {
        await fetch('/chat/reset', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username }),
        })
      } catch {
        /* Non-critical — if the reset fails, the next /chat call will still work */
      }
    }
  }

  /**
   * handleKeyDown — sends the message when Enter is pressed without Shift.
   * Shift+Enter allows multi-line input (default textarea behavior if swapped later).
   *
   * @param {React.KeyboardEvent} e  Keyboard event from the input field
   */
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-window-wrapper">
    <Window
      windowId={windowId}
      title="Chat"
      onClose={onClose}
      closeIcon={closeIcon}
      colorTokenPrefix="chats"
      onFocus={onFocus}
      zIndex={zIndex}
      initialPosition={initialPosition}
    >
      {/* ── Messages Area ──
          Scrollable container for all chat messages.
          Each message row contains an avatar circle and a speech bubble.
          System messages (preference updates) use a special centered style. */}
      <div className="chat-messages">
        {messages.map(msg => (
          msg.sender === 'system' ? (
            /* System message — centered, muted text for preference updates */
            <div key={msg.id} className="chat-message chat-message--system">
              <div className="chat-system-text">{msg.text}</div>
            </div>
          ) : (
            <div
              key={msg.id}
              className={`chat-message${msg.sender === 'user' ? ' chat-message--user' : ''}`}
            >
              {/* Circular avatar placeholder */}
              <div className="chat-avatar" />

              {/* Speech bubble containing the message text */}
              <div className="chat-bubble">{msg.text}</div>
            </div>
          )
        ))}

        {/* Typing indicator — shown while waiting for the backend response */}
        {isLoading && (
          <div className="chat-message">
            <div className="chat-avatar" />
            <div className="chat-bubble chat-bubble--typing">...</div>
          </div>
        )}

        {/* Invisible anchor element — scrollIntoView target for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>

      {/* ── Input Bar ──
          Pinned to the bottom: text input + new conversation button + send button. */}
      <div className="chat-input-bar">
        {/* Text input field — disabled while loading */}
        <input
          className="chat-input"
          type="text"
          placeholder="Type a message…"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
        />

        {/* New conversation button — clears chat and resets server session */}
        <button
          className="chat-new-btn"
          onClick={handleNewConversation}
          aria-label="New conversation"
          title="New conversation"
        >
          <img src={plusIcon} alt="New conversation" />
        </button>

        {/* Send button — submits the current input; disabled while loading */}
        <button
          className="chat-send-btn"
          onClick={handleSend}
          aria-label="Send message"
          title="Send"
          disabled={isLoading}
        >
          <Send size={18} color="white" />
        </button>
      </div>
    </Window>
    </div>
  )
}
