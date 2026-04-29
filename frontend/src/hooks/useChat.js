import { useMemo, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || 'https://flipkart-ai-shopping-assistant-production.up.railway.app'

const getSessionId = () => {
  const key = 'flipkart-session-id'
  const existing = sessionStorage.getItem(key)
  if (existing) return existing
  const next = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
  sessionStorage.setItem(key, next)
  return next
}

export function useChat(categoryId) {
  const sessionId = useMemo(() => getSessionId(), [])
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [ragTrace, setRagTrace] = useState(null)

  const sendMessage = async (query, category, filters) => {
    const userMessage = { id: crypto.randomUUID(), role: 'user', text: query }
    setMessages((prev) => [...prev, userMessage])
    
    const startedAt = performance.now()
    setLoading(true)
    
    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          session_id: sessionId,
          category,
          filters,
        }),
      })
      
      const data = await response.json()
      const endedAt = performance.now()
      const responseTime = ((endedAt - startedAt) / 1000).toFixed(2)
      
      const botMessage = {
        id: crypto.randomUUID(),
        role: 'bot',
        text: data.response || data.answer || 'I found a few options.',
        products: data.products || [],
        followUps: data.follow_up_questions || data.followUps || [],
        responseTime,
      }
      
      setMessages((prev) => [...prev, botMessage])
      setRagTrace(data.trace || data.rag_trace || null)
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: 'bot', text: 'Something went wrong. Please check your connection and retry.' },
      ])
      console.error(error)
    } finally {
      setLoading(false)
    }
  }

  const analyzeProduct = async (product_name, category) => {
    const response = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_name,
        category,
        session_id: sessionId,
      }),
    })
    return response.json()
  }

  const clearChat = async () => {
    setMessages([])
    setRagTrace(null)
    try {
      await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' })
    } catch (error) {
      console.error(error)
    }
  }

  return {
    sessionId,
    categoryId,
    messages,
    loading,
    ragTrace,
    sendMessage,
    analyzeProduct,
    clearChat,
  }
}
