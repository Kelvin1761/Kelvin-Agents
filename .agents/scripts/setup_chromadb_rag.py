#!/usr/bin/env python3
"""
setup_chromadb_rag.py
(Phase 3.4: RAG Semantic Back-testing Framework)

Sets up a local ChromaDB instance to ingest past racing Analysis.md reports, 
enabling the Wong Choi agents to perform semantic back-testing:
"Have we seen a Type A horse with a fast L400 fail from barrier 14 at Happy Valley before?"
"""

import os
import argparse
try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

def init_chroma():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "databases", "chroma_db")
    os.makedirs(db_path, exist_ok=True)
    
    if not HAS_CHROMA:
        print("⚠️ ChromaDB is not installed. Please run: pip install chromadb")
        print(f"🗂️ RAG Database path established at: {db_path}")
        return None
        
    client = chromadb.PersistentClient(path=db_path)
    
    # Use default sentence-transformers model
    ef = embedding_functions.DefaultEmbeddingFunction()
    
    collection = client.get_or_create_collection(name="racing_analysis_history", embedding_function=ef)
    print(f"✅ ChromaDB initialized at {db_path} with collection 'racing_analysis_history'.")
    return collection

def semantic_search(collection, query_text, n_results=3):
    if not collection:
        return
        
    print(f"🔍 Searching RAG Database for: '{query_text}'...")
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    if results and 'documents' in results and len(results['documents'][0]) > 0:
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i] if 'metadatas' in results and results['metadatas'][0] else {}
            print(f"\n--- Match {i+1} (Distance: {results['distances'][0][i]:.4f}) ---")
            print(f"Metadata: {metadata}")
            print(f"Excerpt: {doc[:200]}...")
    else:
        print("No matching historical races found.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', type=str, help="Semantic query to run against past analyses.")
    args = parser.parse_args()
    
    collection = init_chroma()
    
    if args.query and collection:
        semantic_search(collection, args.query)
