import React from 'react';

const FilterPanel = ({ filters, setFilters, onClose }) => {
  const handleBudgetChange = (e) => {
    setFilters({ ...filters, budget: [0, parseInt(e.target.value)] });
  };

  const handleRatingChange = (rating) => {
    setFilters({ ...filters, rating: rating === filters.rating ? 0 : rating });
  };

  const StarRating = ({ rating, active }) => (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((s) => (
        <svg 
          key={s} 
          width="12" 
          height="12" 
          viewBox="0 0 24 24" 
          fill={s <= rating ? (active ? "currentColor" : "currentColor") : "none"}
          stroke="currentColor"
          strokeWidth="2"
          className={s <= rating ? (active ? "text-primary-accent" : "text-primary-accent/40") : "text-border"}
        >
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
      ))}
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-card-bg">
      {/* Header */}
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-text-primary leading-none mb-1">Filters</h2>
          <p className="text-[10px] text-text-muted uppercase tracking-widest font-semibold">Refine your search</p>
        </div>
        <button onClick={onClose} className="md:hidden p-2 hover:bg-border rounded-lg text-text-muted smooth-transition">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-10 custom-scrollbar">
        {/* Budget Slider */}
        <div className="space-y-5">
          <div className="flex justify-between items-end">
            <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Budget Range</label>
            <div className="text-right">
              <span className="text-xs text-text-muted block leading-none mb-1">Up to</span>
              <span className="text-lg font-bold text-primary-accent tabular-nums">₹{filters.budget[1].toLocaleString()}</span>
            </div>
          </div>
          
          <div className="relative pt-2">
            <input 
              type="range" 
              min="0" 
              max="200000" 
              step="5000"
              value={filters.budget[1]} 
              onChange={handleBudgetChange}
              className="filter-range w-full h-1.5 bg-border rounded-full appearance-none cursor-pointer"
            />
            <div className="flex justify-between mt-3 text-[10px] text-text-muted font-bold tracking-tighter">
              <span>₹0</span>
              <span>₹200,000+</span>
            </div>
          </div>
        </div>

        {/* Rating Filter */}
        <div className="space-y-4">
          <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Minimum Rating</label>
          <div className="grid grid-cols-1 gap-2">
            {[4, 3, 2, 1].map((rating) => (
              <button
                key={rating}
                onClick={() => handleRatingChange(rating)}
                className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border text-sm font-medium smooth-transition group ${
                  filters.rating === rating 
                    ? 'bg-primary-accent/10 border-primary-accent text-primary-accent shadow-sm shadow-primary-accent/10' 
                    : 'border-border text-text-muted hover:border-text-muted hover:bg-background/50'
                }`}
              >
                <div className="flex items-center gap-3">
                  <StarRating rating={rating} active={filters.rating === rating} />
                  <span>{rating}+ Stars</span>
                </div>
                {filters.rating === rating && (
                  <div className="w-1.5 h-1.5 rounded-full bg-primary-accent shadow-[0_0_8px_rgba(124,58,237,0.5)]" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Brands Section */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Brands</label>
            <span className="text-[10px] font-bold text-primary-accent/50 italic px-2 py-0.5 rounded-full bg-primary-accent/5">Auto-detected</span>
          </div>
          <div className="p-4 rounded-xl border border-dashed border-border bg-background/30 text-center">
            <p className="text-[11px] text-text-muted leading-relaxed">
              Brands will appear here after your first search query.
            </p>
          </div>
        </div>
      </div>

      {/* Footer Actions */}
      <div className="p-6 border-t border-border bg-background/50 backdrop-blur-sm">
        <button 
          onClick={onClose}
          className="w-full py-4 rounded-xl gradient-bg text-white text-sm font-bold shadow-lg shadow-primary-accent/20 hover:shadow-primary-accent/40 smooth-transition active:scale-[0.98] flex items-center justify-center gap-2"
        >
          <span>Apply Changes</span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
      </div>
    </div>
  );
};

export default FilterPanel;