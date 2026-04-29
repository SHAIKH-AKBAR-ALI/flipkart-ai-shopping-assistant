import React from 'react';
import { motion } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ProductCard from './ProductCard';
import FollowUpChips from './FollowUpChips';

const MessageBubble = ({ message, onAnalyze }) => {
  const isUser = message.role === 'user';

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div className={`max-w-[85%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-2`}>
        <div 
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-lg ${
            isUser 
              ? 'gradient-bg text-white rounded-tr-none' 
              : 'bg-card-bg border border-border text-text-primary rounded-tl-none'
          }`}
        >
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.text}
            </ReactMarkdown>
          </div>
        </div>

        {!isUser && message.responseTime && (
          <span className="text-[10px] text-text-muted px-2">
            Responded in {message.responseTime}s
          </span>
        )}

        {!isUser && message.products && message.products.length > 0 && (
          <div className="flex gap-4 overflow-x-auto pb-4 pt-2 no-scrollbar w-full max-w-full">
            {message.products.map((product, idx) => (
              <ProductCard 
                key={idx} 
                product={product} 
                onAnalyze={onAnalyze} 
              />
            ))}
          </div>
        )}

        {!isUser && message.followUps && message.followUps.length > 0 && (
          <FollowUpChips chips={message.followUps} />
        )}
      </div>
    </motion.div>
  );
};

export default MessageBubble;
