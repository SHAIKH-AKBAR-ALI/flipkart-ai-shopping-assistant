import React, { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import MessageBubble from './MessageBubble';

const ChatWindow = ({ messages, loading, categoryId, onAnalyze }) => {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const welcomeMessages = {
    smartphones: "Welcome! I can help you find the perfect smartphone. Looking for better camera, battery life, or gaming performance?",
    laptops: "Ready to find your next laptop? Tell me about your workflow—coding, design, or casual use?",
    television: "Upgrade your home cinema experience. What screen size or display tech are you interested in?",
    cameras: "Capture your moments with the best gear. Are you a pro or just starting out?",
    audio: "Experience pure sound. Looking for noise-canceling headphones or party speakers?",
    wearables: "Track your health and stay connected. What features do you need in a smartwatch?",
  };

  const welcome = welcomeMessages[categoryId] || "How can I help you today?";

  return (
    <div 
      ref={scrollRef}
      className="flex-1 overflow-y-auto p-4 space-y-6 scroll-smooth"
    >
      <div className="max-w-4xl mx-auto w-full">
        {messages.length === 0 && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center py-20 text-center"
          >
            <div className="w-16 h-16 bg-card-bg border border-border rounded-2xl flex items-center justify-center text-3xl mb-4 shadow-xl">
              ✨
            </div>
            <h2 className="text-xl font-bold mb-2">AI Assistant Ready</h2>
            <p className="text-text-muted max-w-sm">
              {welcome}
            </p>
          </motion.div>
        )}

        <div className="space-y-8">
          {messages.map((msg, idx) => (
            <MessageBubble 
              key={msg.id || idx} 
              message={msg} 
              onAnalyze={onAnalyze}
            />
          ))}

          {loading && (
            <motion.div 
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3"
            >
              <div className="w-8 h-8 rounded-full bg-card-bg border border-border flex items-center justify-center text-xs">
                AI
              </div>
              <div className="bg-card-bg border border-border p-4 rounded-2xl rounded-tl-none">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.div
                      key={i}
                      animate={{ scale: [1, 1.5, 1], opacity: [0.5, 1, 0.5] }}
                      transition={{ repeat: Infinity, duration: 1, delay: i * 0.2 }}
                      className="w-1.5 h-1.5 bg-primary-accent rounded-full"
                    />
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
