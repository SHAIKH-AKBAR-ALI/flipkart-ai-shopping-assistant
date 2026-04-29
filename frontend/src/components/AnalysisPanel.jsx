import React from 'react';
import { motion } from 'framer-motion';

const AnalysisPanel = ({ product, onClose }) => {
  if (!product) return null;

  const {
    name,
    loading,
    value_score,
    pros,
    cons,
    who_should_buy,
    who_should_avoid,
    alternatives,
    verdict
  } = product;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
      />
      
      <motion.div 
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
        className="relative w-full max-w-[420px] bg-card-bg border-l border-border h-full flex flex-col shadow-2xl"
      >
        <div className="p-6 border-b border-border flex items-center justify-between">
          <h2 className="font-bold text-xl line-clamp-1">{name}</h2>
          <button onClick={onClose} className="p-2 hover:bg-border rounded-lg text-text-muted">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
          {loading ? (
            <div className="space-y-6 animate-pulse">
              <div className="h-20 bg-border rounded-xl" />
              <div className="h-40 bg-border rounded-xl" />
              <div className="h-40 bg-border rounded-xl" />
            </div>
          ) : (
            <>
              {/* Value Score */}
              <div className="bg-background border border-border rounded-2xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-sm font-medium text-text-muted uppercase tracking-wider">Value Score</span>
                  <span className="text-3xl font-bold text-primary-accent">{value_score}/100</span>
                </div>
                <div className="w-full h-3 bg-border rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${value_score}%` }}
                    className="h-full gradient-bg"
                  />
                </div>
              </div>

              {/* Pros & Cons */}
              <div className="grid grid-cols-1 gap-4">
                <div className="space-y-3">
                  <h3 className="text-xs font-bold text-success uppercase tracking-widest flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-success rounded-full" /> Pros
                  </h3>
                  <ul className="space-y-2">
                    {pros?.map((pro, idx) => (
                      <li key={idx} className="text-sm text-text-primary flex items-start gap-2 bg-success/5 border border-success/10 p-2 rounded-lg">
                        <span className="text-success mt-0.5">✓</span> {pro}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="space-y-3">
                  <h3 className="text-xs font-bold text-danger uppercase tracking-widest flex items-center gap-2">
                    <span className="w-1.5 h-1.5 bg-danger rounded-full" /> Cons
                  </h3>
                  <ul className="space-y-2">
                    {cons?.map((con, idx) => (
                      <li key={idx} className="text-sm text-text-primary flex items-start gap-2 bg-danger/5 border border-danger/10 p-2 rounded-lg">
                        <span className="text-danger mt-0.5">×</span> {con}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Targets */}
              <div className="space-y-4">
                <div className="p-4 bg-success/10 border border-success/20 rounded-xl">
                  <h4 className="text-xs font-bold text-success mb-2 uppercase">Who should buy</h4>
                  <p className="text-sm text-text-primary leading-relaxed">{who_should_buy}</p>
                </div>
                <div className="p-4 bg-danger/10 border border-danger/20 rounded-xl">
                  <h4 className="text-xs font-bold text-danger mb-2 uppercase">Who should avoid</h4>
                  <p className="text-sm text-text-primary leading-relaxed">{who_should_avoid}</p>
                </div>
              </div>

              {/* Verdict */}
              <div className="p-6 bg-primary-accent/10 border border-primary-accent/30 rounded-2xl relative overflow-hidden group">
                <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
                  <svg width="60" height="60" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>
                  </svg>
                </div>
                <h4 className="text-sm font-bold text-primary-accent mb-2 uppercase tracking-widest">Expert Verdict</h4>
                <p className="text-sm text-text-primary font-medium leading-relaxed italic relative z-10">"{verdict}"</p>
              </div>

              {/* Alternatives */}
              {alternatives && alternatives.length > 0 && (
                <div className="space-y-4">
                  <h3 className="text-xs font-bold text-text-muted uppercase tracking-widest">Better Alternatives</h3>
                  <div className="space-y-2">
                    {alternatives.map((alt, idx) => (
                      <div key={idx} className="p-3 bg-background border border-border rounded-lg flex justify-between items-center group hover:border-primary-accent smooth-transition">
                        <span className="text-sm font-medium">{alt.name}</span>
                        <span className="text-xs font-bold text-price group-hover:scale-110 transition-transform">₹{alt.price}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </motion.div>
    </div>
  );
};

export default AnalysisPanel;
