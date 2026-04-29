import React, { useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useChat } from '../hooks/useChat';
import Header from '../components/Header';
import ChatWindow from '../components/ChatWindow';
import InputBar from '../components/InputBar';
import FilterPanel from '../components/FilterPanel';
import RAGTracePanel from '../components/RAGTracePanel';
import AnalysisPanel from '../components/AnalysisPanel';

const ChatPage = () => {
  const { categoryId } = useParams();
  const { 
    messages, 
    loading, 
    ragTrace, 
    sendMessage, 
    analyzeProduct, 
    clearChat 
  } = useChat(categoryId);

  const [filters, setFilters] = useState({ budget: [0, 200000], rating: 0 });
  const [isFilterOpen, setIsFilterOpen] = useState(true);
  const [isTraceOpen, setIsTraceOpen] = useState(false);
  const [analysisProduct, setAnalysisProduct] = useState(null);

  const handleSendMessage = useCallback((query) => {
    sendMessage(query, categoryId, filters);
  }, [sendMessage, categoryId, filters]);

  const handleAnalyze = useCallback(async (product) => {
    setAnalysisProduct({ ...product, loading: true });
    try {
      const data = await analyzeProduct(product.name, categoryId);
      setAnalysisProduct({ ...product, ...data, loading: false });
    } catch (error) {
      console.error(error);
      setAnalysisProduct(null);
    }
  }, [analyzeProduct, categoryId]);

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Left Sidebar: Filters */}
      <AnimatePresence mode="wait">
        {isFilterOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="border-r border-border bg-card-bg flex-shrink-0"
          >
            <FilterPanel 
              filters={filters} 
              setFilters={setFilters} 
              onClose={() => setIsFilterOpen(false)} 
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        <Header 
          categoryId={categoryId} 
          onClear={clearChat} 
          toggleFilter={() => setIsFilterOpen(!isFilterOpen)}
          toggleTrace={() => setIsTraceOpen(!isTraceOpen)}
          isFilterOpen={isFilterOpen}
          isTraceOpen={isTraceOpen}
        />
        
        <div className="flex-1 overflow-hidden flex flex-col">
          <ChatWindow 
            messages={messages} 
            loading={loading} 
            categoryId={categoryId}
            onAnalyze={handleAnalyze}
          />
          <InputBar 
            onSend={handleSendMessage} 
            loading={loading} 
            categoryId={categoryId} 
          />
        </div>
      </div>

      {/* Right Sidebar: RAG Trace */}
      <AnimatePresence mode="wait">
        {isTraceOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="border-l border-border bg-card-bg flex-shrink-0"
          >
            <RAGTracePanel 
              trace={ragTrace} 
              onClose={() => setIsTraceOpen(false)} 
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Overlay Analysis Panel */}
      <AnimatePresence>
        {analysisProduct && (
          <AnalysisPanel 
            product={analysisProduct} 
            onClose={() => setAnalysisProduct(null)} 
          />
        )}
      </AnimatePresence>
    </div>
  );
};

export default ChatPage;
