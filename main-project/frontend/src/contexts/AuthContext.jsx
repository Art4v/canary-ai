import { createContext, useContext, useState, useCallback } from 'react'

/**
 * AuthContext — provides authentication state and helpers to the entire app.
 *
 * State:
 *   - `user`       — the logged-in user object (from Supabase) or null
 *   - `token`      — the session token returned by POST /database/users/login
 *   - `login(data)` — expects { user, token }; stores both in state + localStorage
 *   - `logout()`    — fire-and-forget POST /database/users/logout, then clear state + localStorage
 *   - `updateUser(fields)` — merge partial updates into the current user object
 *   - `authFetch(url, options)` — wrapper around fetch() that injects the Bearer token
 *                                  and handles 401 by auto-logging out
 *
 * Persistence:
 *   Uses localStorage under "canary_user" (user object) and "canary_token"
 *   (session token) so sessions survive page reloads.
 */

/* localStorage keys used for persisting auth state */
const USER_KEY = 'canary_user'
const TOKEN_KEY = 'canary_token'

/* Create the context with a null default (no user logged in) */
const AuthContext = createContext(null)

/**
 * useAuth — convenience hook to consume AuthContext.
 *
 * @returns {{ user: object|null, token: string|null, login: Function, logout: Function, updateUser: Function, authFetch: Function }}
 */
export function useAuth() {
  return useContext(AuthContext)
}

/**
 * AuthProvider — wraps the component tree to provide auth state.
 *
 * Reads the initial user and token from localStorage on first render
 * so that a page refresh doesn't log the user out.
 *
 * @param {{ children: React.ReactNode }} props
 * @returns {JSX.Element}
 */
export function AuthProvider({ children }) {
  /* Initialise user state from localStorage (lazy initialiser runs once) */
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem(USER_KEY)
      return stored ? JSON.parse(stored) : null
    } catch {
      /* Corrupt or missing data — start logged out */
      return null
    }
  })

  /* Initialise token state from localStorage */
  const [token, setToken] = useState(() => {
    return localStorage.getItem(TOKEN_KEY) || null
  })

  /**
   * login — save user data and session token to state and localStorage.
   * Called after a successful POST /database/users/login response.
   * Expects the new response shape: { user: <user_data>, token: <session_token> }.
   *
   * @param {object} data  Object with `user` and `token` fields
   */
  const login = useCallback((data) => {
    const { user: userData, token: sessionToken } = data
    setUser(userData)
    setToken(sessionToken)
    localStorage.setItem(USER_KEY, JSON.stringify(userData))
    localStorage.setItem(TOKEN_KEY, sessionToken)
  }, [])

  /**
   * logout — invalidate the session on the backend and clear local state.
   * Fire-and-forget POST /database/users/logout with the Bearer token,
   * then clear state and localStorage regardless of whether the request succeeds.
   */
  const logout = useCallback(() => {
    /* Fire-and-forget: tell the backend to delete the session */
    const currentToken = localStorage.getItem(TOKEN_KEY)
    if (currentToken) {
      fetch('/database/users/logout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${currentToken}`,
        },
      }).catch(() => {
        /* Silently ignore — we're logging out anyway */
      })
    }

    /* Clear local state and storage */
    setUser(null)
    setToken(null)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(TOKEN_KEY)
  }, [])

  /**
   * updateUser — merge partial field updates into the stored user object.
   * Used after a successful PUT /database/users/{username} call so the
   * context stays in sync with the database without re-fetching.
   *
   * @param {object} fields  Key-value pairs to merge (e.g. { email: "new@example.com" })
   */
  const updateUser = useCallback((fields) => {
    setUser(prev => {
      /* Merge the new fields into the existing user object */
      const updated = { ...prev, ...fields }
      localStorage.setItem(USER_KEY, JSON.stringify(updated))
      return updated
    })
  }, [])

  /**
   * authFetch — wrapper around the native fetch() that automatically injects
   * the Authorization: Bearer <token> header. If the backend responds with
   * 401 (invalid/expired token), the user is logged out and redirected to /.
   *
   * @param {string} url       The request URL
   * @param {object} [options] Standard fetch options (method, headers, body, etc.)
   * @returns {Promise<Response>} The fetch Response object
   */
  const authFetch = useCallback(async (url, options = {}) => {
    /* Read the current token from localStorage (more reliable than stale closure) */
    const currentToken = localStorage.getItem(TOKEN_KEY)

    /* Merge the Authorization header into any existing headers */
    const headers = {
      ...options.headers,
      ...(currentToken ? { 'Authorization': `Bearer ${currentToken}` } : {}),
    }

    const response = await fetch(url, { ...options, headers })

    /* If the backend says 401, the token is invalid/expired — auto-logout */
    if (response.status === 401) {
      setUser(null)
      setToken(null)
      localStorage.removeItem(USER_KEY)
      localStorage.removeItem(TOKEN_KEY)
      window.location.href = '/'
    }

    return response
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, login, logout, updateUser, authFetch }}>
      {children}
    </AuthContext.Provider>
  )
}
