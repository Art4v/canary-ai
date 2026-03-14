import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './styles/tokens.css'
import './styles/base.css'
import { ThemeProvider } from './hooks/useTheme.jsx'
import App from './App.jsx'

/* Wrap the entire app with BrowserRouter so all components
   can use React Router hooks (useNavigate, Link, Routes, etc.) */
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </BrowserRouter>
  </StrictMode>,
)
