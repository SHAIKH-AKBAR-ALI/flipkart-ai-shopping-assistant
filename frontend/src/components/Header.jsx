import React from 'react';
import { useNavigate } from 'react-router-dom';

const Header = ({ 
  categoryId, 
  onClear, 
  toggleFilter, 
  toggleTrace, 
  isFilterOpen, 
  isTraceOpen 
}) => {
  const navigate = useNavigate();

  const categories = {
    mobile: { name: 'Mobiles', emoji: '📱' },
    laptop: { name: 'Laptops', emoji: '💻' },
    tv: { name: 'Televisions', emoji: '📺' },
    refrigerator: { name: 'Refrigerators', emoji: '🧊' },
    smart_watch: { name: 'Smart Watches', emoji: '⌚' },
    washing_machine: { name: 'Washing Machines', emoji: '🫧' },
  };

  const current = categories[categoryId] || { name: 'Shopping', emoji: '🛍️' };

  return (
    <header className="h-16 bg-card-bg border-b border-border px-4 flex items-center justify-between z-10">
      <div className="flex items-center gap-4">
        <button 
          onClick={() => navigate('/')}
          className="p-2 hover:bg-border rounded-lg smooth-transition text-text-muted hover:text-text-primary"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="flex items-center gap-2">
          <span className="text-xl">{current.emoji}</span>
          <span className="font-bold text-text-primary">{current.name}</span>
        </div>
      </div>

      <div className="hidden md:flex items-center gap-3">
        {['Groq LPU', 'LangGraph', 'RAG'].map((tech) => (
          <span key={tech} className="px-2 py-0.5 bg-background border border-border rounded text-[10px] font-bold text-text-muted tracking-wider uppercase">
            {tech}
          </span>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <button 
          onClick={toggleFilter}
          className={`p-2 rounded-lg smooth-transition ${isFilterOpen ? 'bg-primary-accent/10 text-primary-accent' : 'text-text-muted hover:bg-border'}`}
          title="Toggle Filters"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
          </svg>
        </button>
        
        <button 
          onClick={toggleTrace}
          className={`p-2 rounded-lg smooth-transition ${isTraceOpen ? 'bg-primary-accent/10 text-primary-accent' : 'text-text-muted hover:bg-border'}`}
          title="Toggle RAG Trace"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
        </button>

        <div className="w-[1px] h-6 bg-border mx-1" />

        <button 
          onClick={onClear}
          className="px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger/10 rounded-lg smooth-transition"
        >
          Clear Chat
        </button>
      </div>
    </header>
  );
};

export default Header;
