import { createContext, useContext, useState, useCallback } from 'react'

/**
 * AuthContext — provides authentication state and helpers to the entire app.
 *
 * State:
 *   - `user`       — the logged-in user object (from Supabase) or null
 *   - `login(data)` — store user data in state + localStorage
 *   - `logout()`    — clear user data from state + localStorage
 *   - `updateUser(fields)` — merge partial updates into the current user object
 *
 * Persistence:
 *   Uses localStorage under the key "canary_user" so sessions survive
 *   page reloads. On mount, the provider reads from localStorage to
 *   restore the previous session.
 */

/* localStorage key used for persisting the user object */
const STORAGE_KEY = 'canary_user'

/* Create the context with a null default (no user logged in) */
const AuthContext = createContext(null)

/**
 * useAuth — convenience hook to consume AuthContext.
 *
 * @returns {{ user: object|null, login: Function, logout: Function, updateUser: Function }}
 */
export function useAuth() {
  return useContext(AuthContext)
}

/**
 * AuthProvider — wraps the component tree to provide auth state.
 *
 * Reads the initial user from localStorage on first render so that
 * a page refresh doesn't log the user out.
 *
 * @param {{ children: React.ReactNode }} props
 * @returns {JSX.Element}
 */
export function AuthProvider({ children }) {
  /* Initialise user state from localStorage (lazy initialiser runs once) */
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? JSON.parse(stored) : null
    } catch {
      /* Corrupt or missing data — start logged out */
      return null
    }
  })

  /**
   * login — save user data to state and localStorage.
   * Called after a successful POST /database/users/login response.
   *
   * @param {object} data  User row returned by the backend (without password_hash)
   */
  const login = useCallback((data) => {
    setUser(data)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  }, [])

  /**
   * logout — clear the current session.
   * Removes the user from state and localStorage.
   */
  const logout = useCallback(() => {
    setUser(null)
    localStorage.removeItem(STORAGE_KEY)
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
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
      return updated
    })
  }, [])

  return (
    <AuthContext.Provider value={{ user, login, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  )
}
