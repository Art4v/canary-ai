import { useState, useRef, useEffect } from 'react'
import Window from './Window'
import closeIcon from '@/assets/chat/chat_close.png'
import plusIcon from '@/assets/chat/chat_plus.png'
import './ChatWindow.css'

/**
 * Initial mock messages to populate the chat on first render and
 * when the user resets the conversation via the "+" button.
 * Alternates between bot and user to demonstrate both alignments.
 */
const INITIAL_MESSAGES = [
  { id: 1, sender: 'bot',  text: 'Hey there! I\'m Canary AI, your stock market assistant. How can I help you today?', timestamp: Date.now() - 30000 },
  { id: 2, sender: 'user', text: 'What stocks should I look into right now?',                                        timestamp: Date.now() - 20000 },
  { id: 3, sender: 'bot',  text: 'Based on current market trends, tech and energy sectors are showing strong momentum. Want me to analyze a specific ticker?', timestamp: Date.now() - 10000 },
  { id: 4, sender: 'user', text: 'Sure, tell me more about AAPL.',                                                   timestamp: Date.now() },
]

/**
 * ChatWindow — Chat section content wrapped in the generic Window shell.
 *
 * Layout (top to bottom):
 *   1. Scrollable message area — alternating bot/user speech bubbles with avatars
 *   2. Input bar — text field, new-conversation "+" button, and send "Enter" button
 *
 * @param {string}   windowId         Unique identifier for snap system
 * @param {Function} onClose          Called when the window's X button is clicked
 * @param {Function} [onFocus]        Called on mousedown to bring window to front
 * @param {number}   [zIndex]         Inline z-index for stacking order
 * @param {{ x: number, y: number }} [initialPosition]  Starting top-left coords
 * @returns {JSX.Element}
 */
export default function ChatWindow({ windowId, onClose, onFocus, zIndex, initialPosition }) {
  /* Chat message history — initialized with mock data */
  const [messages, setMessages] = useState(INITIAL_MESSAGES)

  /* Controlled text input value */
  const [inputValue, setInputValue] = useState('')

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
   * handleSend — appends the current input as a new user message.
   * Clears the input field after sending.
   * No-ops if the input is empty or whitespace-only.
   */
  const handleSend = () => {
    const trimmed = inputValue.trim()
    if (!trimmed) return

    setMessages(prev => [
      ...prev,
      {
        id: Date.now(),
        sender: 'user',
        text: trimmed,
        timestamp: Date.now(),
      },
    ])
    setInputValue('')
  }

  /**
   * handleNewConversation — resets the chat back to the initial mock messages.
   * Triggered by the "+" button in the input bar.
   */
  const handleNewConversation = () => {
    setMessages(INITIAL_MESSAGES)
    setInputValue('')
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
          Each message row contains an avatar circle and a speech bubble. */}
      <div className="chat-messages">
        {messages.map(msg => (
          <div
            key={msg.id}
            className={`chat-message${msg.sender === 'user' ? ' chat-message--user' : ''}`}
          >
            {/* Circular avatar placeholder */}
            <div className="chat-avatar" />

            {/* Speech bubble containing the message text */}
            <div className="chat-bubble">{msg.text}</div>
          </div>
        ))}

        {/* Invisible anchor element — scrollIntoView target for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>

      {/* ── Input Bar ──
          Pinned to the bottom: text input + new conversation button + send button. */}
      <div className="chat-input-bar">
        {/* Text input field */}
        <input
          className="chat-input"
          type="text"
          placeholder="Type a message…"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        {/* New conversation button — resets chat to initial mock messages */}
        <button
          className="chat-new-btn"
          onClick={handleNewConversation}
          aria-label="New conversation"
          title="New conversation"
        >
          <img src={plusIcon} alt="New conversation" />
        </button>

        {/* Send button — submits the current input as a user message */}
        <button
          className="chat-send-btn"
          onClick={handleSend}
          aria-label="Send message"
          title="Send"
        >
          Enter
        </button>
      </div>
    </Window>
    </div>
  )
}
