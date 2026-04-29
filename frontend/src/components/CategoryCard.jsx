import { motion } from 'framer-motion'

export default function CategoryCard({ category, onClick, active = false }) {
  return (
    <motion.button
      type="button"
      className={`category-card ${active ? 'active' : ''}`}
      whileHover={{ y: -4, scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
    >
      <span className="category-icon">{category.icon || '🛍️'}</span>
      <h3>{category.name}</h3>
      <span className="count-badge">{category.count || 0} products</span>
    </motion.button>
  )
}
