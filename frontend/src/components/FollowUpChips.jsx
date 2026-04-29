import React from 'react';
import { motion } from 'framer-motion';

const FollowUpChips = ({ chips }) => {
  return (
    <div className="flex flex-wrap gap-2 pt-2">
      {chips.map((chip, idx) => (
        <motion.button
          key={idx}
          whileHover={{ scale: 1.05, borderColor: '#6366F1' }}
          whileTap={{ scale: 0.95 }}
          className="px-3 py-1.5 bg-card-bg/50 border border-border rounded-full text-xs text-primary-accent font-medium smooth-transition hover:bg-primary-accent/5"
          onClick={() => {
            // This would normally trigger a message send, 
            // but the onClick needs to be passed down or handled via event bus
            const event = new CustomEvent('send-query', { detail: chip });
            window.dispatchEvent(event);
          }}
        >
          {chip}
        </motion.button>
      ))}
    </div>
  );
};

export default FollowUpChips;
