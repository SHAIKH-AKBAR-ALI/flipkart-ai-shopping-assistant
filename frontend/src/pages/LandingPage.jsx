import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_URL || 'https://flipkart-ai-shopping-assistant-production.up.railway.app';

const LandingPage = () => {
  const [categories, setCategories] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const response = await fetch(`${API_BASE}/categories`);
        const data = await response.json();
        setCategories(data.categories || []);
      } catch (error) {
        console.error('Error fetching categories:', error);
      }
    };
    fetchCategories();
  }, []);

  const totalProducts = categories.reduce((acc, cat) => acc + (cat.count || 0), 0);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center pt-20 pb-10 px-4">
      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="text-center max-w-4xl"
      >
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6">
          Your AI <span className="gradient-text">Shopping Assistant</span>
        </h1>
        <p className="text-text-muted text-xl mb-10 max-w-2xl mx-auto">
          Hyper-personalized product discovery powered by Hybrid RAG and LangGraph.
        </p>

        <motion.div 
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          className="flex flex-wrap justify-center gap-3 mb-16"
        >
          {['Hybrid RAG', 'LangGraph', 'Groq LPU', 'AstraDB'].map((tech) => (
            <motion.span 
              key={tech} 
              variants={itemVariants}
              className="px-3 py-1 bg-card-bg border border-border rounded-full text-xs font-medium text-text-muted"
            >
              {tech}
            </motion.span>
          ))}
        </motion.div>
      </motion.div>

      <motion.div 
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 w-full max-w-6xl mb-20"
      >
        {categories.map((cat) => (
          <motion.div
            key={cat.id}
            variants={itemVariants}
            whileHover={{ 
              scale: 1.02, 
              y: -5,
              borderColor: 'var(--primary-accent)',
              boxShadow: '0 0 20px rgba(124, 58, 237, 0.2)'
            }}
            onClick={() => navigate(`/chat/${cat.id}`)}
            className="glass-card p-8 rounded-2xl cursor-pointer glow-hover smooth-transition group border border-transparent"
          >
            <div className="text-4xl mb-4 grayscale group-hover:grayscale-0 transition-all duration-300">
              {cat.icon}
            </div>
            <h3 className="text-xl font-bold text-text-primary mb-1">
              {cat.name}
            </h3>
            <p className="text-text-muted text-sm">
              {cat.count} items
            </p>
          </motion.div>
        ))}
      </motion.div>

      <footer className="mt-auto text-text-muted text-sm border-t border-border pt-8 w-full text-center space-y-4">
        <p>{totalProducts} products indexed across {categories.length} categories • Built for Performance</p>
        <div className="flex flex-col items-center gap-2">
          <a 
            href="https://github.com/SHAIKH-AKBAR-ALI" 
            target="_blank" 
            rel="noopener noreferrer"
            className="group flex items-center gap-2 text-xs font-medium transition-all duration-300"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
            </svg>
            <span>Developed by <span className="group-hover:text-primary-accent group-hover:drop-shadow-[0_0_8px_rgba(99,102,241,0.6)] smooth-transition">SHAIKH AKBAR ALI</span></span>
          </a>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
