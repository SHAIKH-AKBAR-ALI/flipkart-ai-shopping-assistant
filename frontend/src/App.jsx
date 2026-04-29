import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import ChatPage from './pages/ChatPage'

export default function App() {
  const [darkMode, setDarkMode] = useState(() => {
    const stored = localStorage.getItem('flipkart-dark-mode')
    return stored ? stored === 'true' : false
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
    localStorage.setItem('flipkart-dark-mode', String(darkMode))
  }, [darkMode])

  return (
    <Routes>
      <Route path="/" element={<LandingPage darkMode={darkMode} />} />
      <Route
        path="/chat/:categoryId"
        element={<ChatPage darkMode={darkMode} setDarkMode={setDarkMode} />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
