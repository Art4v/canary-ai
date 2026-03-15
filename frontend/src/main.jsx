import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './styles/tokens.css'
import './styles/base.css'
import { ThemeProvider } from './hooks/useTheme.jsx'
import { AuthProvider } from './contexts/AuthContext.jsx'
import App from './App.jsx'

/* Wrap the entire app with BrowserRouter so all components
   can use React Router hooks (useNavigate, Link, Routes, etc.).
   AuthProvider sits inside BrowserRouter so auth helpers can
   use navigation, and outside ThemeProvider since auth is independent. */
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter basename="/landing">
      <AuthProvider>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
