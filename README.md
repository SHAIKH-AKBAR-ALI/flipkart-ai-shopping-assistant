# Flipkart AI Shopping Assistant 🛍️

![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)
![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain)
![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white)
![AstraDB](https://img.shields.io/badge/DataStax_AstraDB-315A5A?style=for-the-badge)
![Vite](https://img.shields.io/badge/Vite-B73BFE?style=for-the-badge&logo=vite&logoColor=FFD62E)
![TailwindCSS](https://img.shields.io/badge/Tailwind_4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-232B2B?style=for-the-badge)

## Overview
An intelligent AI-powered shopping assistant built with a production-grade RAG (Retrieval-Augmented Generation) architecture. Users can have natural conversations to get personalized product recommendations across 6 categories with context-aware responses.

## ✨ Features
- 🤖 **Multi-agent routing with LangGraph** — dedicated specialist agent per category
- 🔍 **Hybrid search pipeline** combining AstraDB vector search + BM25 keyword search + cross-encoder reranking
- 💬 **Context-aware conversations** with persistent session management (SQLAlchemy)
- ⚡ **Ultra-fast LLM inference** via Groq (llama-3.3-70b)
- 📊 **Built-in RAG evaluation pipeline** using Ragas
- 🎨 **Modern React 19 UI** with Framer Motion animations and dark mode
- 📦 **Structured JSON output** for clean product card rendering

## 🏗️ Architecture
The system employs a sophisticated Agentic RAG flow:
1. **User Query**: The user asks a question via the React UI.
2. **FastAPI**: Receives the request and initiates the LangGraph workflow.
3. **LangGraph Router**: Analyzes the query intent and routes it to the appropriate domain expert (e.g., Laptop, Mobile).
4. **Hybrid Retriever**: The chosen agent queries the knowledge base using a mix of AstraDB (semantic search) and BM25 (keyword matching), refined by a cross-encoder reranker for maximum relevance.
5. **Category Specialist Agent**: Synthesizes the retrieved context and formulates a response tailored to the category's unique specifications.
6. **Structured JSON**: The output is strictly formatted as JSON containing the answer text, product metadata, and suggested follow-ups.
7. **React UI**: Parses the JSON to display interactive message bubbles and rich product cards.

## 🛠️ Tech Stack

| Category | Technologies |
| :--- | :--- |
| **Frontend** | React 19, Vite, TailwindCSS 4, Framer Motion, React Router v7, Axios |
| **Backend** | FastAPI, LangChain, LangGraph, Groq (llama-3.3-70b), OpenAI |
| **Database** | DataStax AstraDB (vector), SQLite/PostgreSQL (sessions) |
| **Search** | Rank-BM25, Sentence Transformers, Cross-encoder reranking |
| **Evaluation** | Ragas |
| **Deployment** | Railway (backend), Vercel (frontend) |

## 📁 Project Structure
```text
flipkart-rag-v2/
├── backend/
│   ├── app.py                # FastAPI entry point
│   ├── requirements.txt      # Python dependencies
│   ├── data/                 # Raw datasets (CSVs)
│   └── flipkart/             # Core AI package
│       ├── agent.py          # LangGraph routing & agents
│       ├── retriever.py      # Hybrid RAG search
│       ├── session_store.py  # SQLAlchemy chat history
│       ├── evaluator.py      # Ragas evaluation
│       └── data_ingestion.py # Embedding generation
└── frontend/
    ├── package.json          # Node dependencies
    ├── vite.config.js        # Build configuration
    └── src/
        ├── App.jsx           # Root layout & routing
        ├── pages/            # LandingPage, ChatPage
        ├── components/       # Reusable UI widgets
        └── hooks/            # Custom React hooks
```

## ⚙️ Environment Variables
Create a `.env` file in the `backend/` directory:
```env
GROQ_API_KEY=your_groq_api_key
ASTRA_DB_API_ENDPOINT=your_astra_db_endpoint
ASTRA_DB_APPLICATION_TOKEN=your_astra_db_token
ASTRA_DB_KEYSPACE=your_keyspace
ASTRA_DB_COLLECTION=your_collection
OPENAI_API_KEY=your_openai_api_key
```

## 🚀 Local Setup

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## 🌐 Live Demo
- **Frontend**: https://flipkart-ai-shopping-assistant.vercel.app
- **Backend API**: _[Deploy to Railway to get URL]_

## 📄 License
MIT
