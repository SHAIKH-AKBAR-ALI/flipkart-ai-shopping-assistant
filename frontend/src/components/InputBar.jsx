import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';

const InputBar = ({ onSend, loading, categoryId }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !loading) {
      onSend(query.trim());
      setQuery('');
    }
  };

  // Listen for follow-up chip clicks
  useEffect(() => {
    const handleQuery = (e) => {
      setQuery(e.detail);
      onSend(e.detail);
    };
    window.addEventListener('send-query', handleQuery);
    return () => window.removeEventListener('send-query', handleQuery);
  }, [onSend]);

  return (
    <div className="p-4 border-t border-border bg-background/50 backdrop-blur-md">
      <form 
        onSubmit={handleSubmit}
        className="max-w-4xl mx-auto relative group"
      >
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Ask about ${categoryId}...`}
          disabled={loading}
          className="w-full bg-card-bg border border-border rounded-2xl py-4 pl-6 pr-16 text-text-primary focus:outline-none focus:border-primary-accent smooth-transition shadow-xl disabled:opacity-50"
        />
        
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className={`absolute right-2 top-2 bottom-2 px-4 rounded-xl gradient-bg text-white font-bold flex items-center justify-center smooth-transition ${
            !query.trim() || loading ? 'opacity-50 grayscale' : 'hover:shadow-lg hover:shadow-primary-accent/40 active:scale-95'
          }`}
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          )}
        </button>
      </form>
      <div className="max-w-4xl mx-auto mt-2 px-2 flex justify-between items-center">
        <p className="text-[10px] text-text-muted font-medium uppercase tracking-widest">
          Powered by LangGraph & Groq LPU
        </p>
        <p className="text-[10px] text-text-muted">
          Press Enter to send
        </p>
      </div>
    </div>
  );
};

export default InputBar;
