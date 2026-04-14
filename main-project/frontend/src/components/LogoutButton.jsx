import { useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext.jsx'
import './LogoutButton.css'

/**
 * LogoutButton — puffy 3D circle button fixed to the top-left corner
 * of the /app dashboard. Clicking it calls logout() from AuthContext
 * (which fire-and-forgets POST /database/users/logout) and then
 * navigates back to the landing page.
 *
 * @returns {JSX.Element}
 */
export default function LogoutButton() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  /**
   * handleLogout — clear the session and redirect to the landing page.
   */
  const handleLogout = () => {
    logout()
    navigate('/')
  }

  return (
    <button
      className="logout-btn"
      onClick={handleLogout}
      aria-label="Log out"
      title="Log out"
    >
      <LogOut size={18} />
    </button>
  )
}
