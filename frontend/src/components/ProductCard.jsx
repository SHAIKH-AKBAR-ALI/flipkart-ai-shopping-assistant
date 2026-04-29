import React from 'react';
import { motion } from 'framer-motion';

const ProductCard = ({ product, onAnalyze }) => {
  const {
    name,
    brand,
    price,
    mrp,
    discount,
    rating,
    review_count,
    image_url
  } = product;

  const displayBrand = (!brand || brand.toLowerCase() === 'generic') 
    ? (name ? name.split(' ')[0] : 'Generic') 
    : brand;

  return (
    <motion.div 
      whileHover={{ y: -5 }}
      className="flex-shrink-0 w-64 glass-card rounded-xl overflow-hidden smooth-transition glow-hover group"
    >
      <div className="h-40 bg-white/5 relative overflow-hidden">
        {image_url ? (
          <img src={image_url} alt={name} className="w-full h-full object-contain p-4 group-hover:scale-110 transition-transform duration-500" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-border">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
          </div>
        )}
        {discount && (
          <div className="absolute top-2 right-2 bg-success text-[10px] font-bold px-2 py-0.5 rounded text-white">
            {discount}
          </div>
        )}
      </div>

      <div className="p-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] font-bold text-primary-accent uppercase tracking-wider">{displayBrand}</span>
        </div>
        <h3 className="font-bold text-text-primary text-sm line-clamp-2 min-h-[2.5rem] mb-3">
          {name}
        </h3>

        <div className="flex items-center gap-1 mb-3">
          <span className="text-star">★</span>
          <span className="text-xs font-bold text-text-primary">{rating || '4.2'}</span>
          <span className="text-[10px] text-text-muted">({review_count || '120'})</span>
        </div>

        <div className="flex items-baseline gap-2 mb-4">
          <span className="text-lg font-bold text-price">
            ₹{price ? Number(price).toLocaleString() : 'N/A'}
          </span>
          {mrp && (
            <span className="text-[10px] text-text-muted line-through">
              ₹{Number(mrp).toLocaleString()}
            </span>
          )}
        </div>

        <button 
          onClick={() => onAnalyze(product)}
          className="w-full py-2 rounded-lg gradient-bg text-white text-xs font-bold shadow-lg shadow-primary-accent/20 hover:shadow-primary-accent/40 smooth-transition active:scale-95"
        >
          Analyze
        </button>
      </div>
    </motion.div>
  );
};

export default ProductCard;
