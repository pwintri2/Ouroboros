import os
import uuid
import chromadb
from chromadb.utils import embedding_functions
import PyPDF2
import docx
import hashlib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CHROMA_PERSIST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "wintrip_brain"))
CHROMA_COLLECTION_NAME = "wintrip_knowledge"

class KnowledgeBase:
    def __init__(self, persist_dir: str = None):
        if not persist_dir:
            persist_dir = os.getenv("WINTRIP_DB_PATH", CHROMA_PERSIST_DIR)
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # We vertellen ChromaDB dat we Ollama gebruiken voor de wiskundige vectoren
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=f"{ollama_url}/api/embeddings",
            model_name=embed_model,
        )
        
        # Maak of open de collectie (het vakje in het brein)
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME, 
            embedding_function=self.embedding_function
        )
        print(f"🧠 [Hippocampus]: Vector Database wordt opgestart ({persist_dir})...")
        count = self.collection.count()
        print(f"🧠 [Hippocampus]: Online. Aantal herinneringen in database: {count}")

    def _extract_text(self, file_path):
        """Hulpfunctie om tekst uit een bestand te trekken"""
        ext = file_path.lower().split('.')[-1]
        text = ""
        try:
            if ext in ['txt', 'md', 'csv', 'json']:
                with open(file_path, 'r', encoding='utf-8') as f: text = f.read()
            elif ext == 'pdf':
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            elif ext == 'docx':
                doc = docx.Document(file_path)
                text = "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            print(f"❌ Fout bij lezen van {file_path}: {e}")
        return text

    def _chunk_text(self, text, chunk_size=1000, overlap=200):
        """Hakt enorme teksten in betekenisvolle, overlappende blokken (respecteert paragrafen)."""
        chunks = []
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        for p in paragraphs:
            # Als de paragraaf zelf groter is dan chunk_size, moeten we grof hakken
            if len(p) > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                # Hard chunk the massive paragraph
                start = 0
                while start < len(p):
                    end = start + chunk_size
                    chunks.append(p[start:end])
                    start += (chunk_size - overlap)
            # Als nieuwe paragraaf past bij de huidige chunk
            elif len(current_chunk) + len(p) < chunk_size:
                current_chunk += p + "\n\n"
            # Als de chunk vol is
            else:
                chunks.append(current_chunk.strip())
                # Start new chunk with overlap of previous text logic (or just start fresh)
                current_chunk = p + "\n\n"
                
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
            
        return chunks

    def ingest_file(self, file_path):
        """Leest een bestand, hakt het in stukjes en slaat het voor eeuwig op in ChromaDB"""
        if not os.path.exists(file_path):
            return False
            
        print(f"📥 [Hippocampus]: Bestand aan het leren... ({os.path.basename(file_path)})")
        text = self._extract_text(file_path)
        
        if not text.strip():
            print("⚠️ Bestand was leeg of onleesbaar.")
            return False

        # Check of we dit bestand al kennen (voorkomt dubbele data)
        existing_docs = self.collection.get(where={"source": file_path})
        if existing_docs and len(existing_docs['ids']) > 0:
            print("✅ [Hippocampus]: Ik kende dit bestand al. Overgeslagen.")
            return True

        chunks = self._chunk_text(text)
        
        # Determine doc_type roughly
        doc_type = "user_memory" if "Kennis over" in text else "system_docs"
        interaction_id = str(uuid.uuid4())
        source_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        ingested_at = datetime.utcnow().isoformat()
        
        documents = []
        metadatas = []
        ids = []
        
        for i, chunk in enumerate(chunks):
            documents.append(chunk)
            chunk_hash = hashlib.sha256(chunk.encode("utf-8", errors="ignore")).hexdigest()
            metadatas.append({
                "type": doc_type,
                "source": file_path,
                "source_type": file_path.split('.')[-1] if '.' in file_path else "unknown",
                "persona": "general",
                "importance": 5.0 if doc_type == "user_memory" else 1.0,
                "interaction_id": interaction_id,
                "chunk_index": i,
                "chunk_count": len(chunks),
                "content_hash": chunk_hash,
                "source_hash": source_hash,
                "ingested_at": ingested_at,
                "title": os.path.basename(file_path),
                "tags": "wintrip_ingest",
                "language": "unknown"
            })
            ids.append(f"{os.path.basename(file_path)}_{uuid.uuid5(uuid.NAMESPACE_URL, str(chunk_hash))}")
            
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"✅ [Hippocampus]: Opgeslagen! {len(chunks)} nieuwe herinneringen toegevoegd.")
        return True

    def ingest_reflection(self, text, reflection_type="insight", tags="", interaction_id=None):
        """Slaat interne reflecties (success, failure, insight) direct op in het geheugen."""
        if not text.strip():
            return False
            
        print(f"📥 [Hippocampus]: Reflectie aan het opslaan... ({reflection_type})")
        
        chunks = self._chunk_text(text)
        
        if not interaction_id:
            interaction_id = str(uuid.uuid4())
            
        source_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        ingested_at = datetime.utcnow().isoformat()
        
        documents = []
        metadatas = []
        ids = []
        
        if reflection_type not in ["success", "failure", "insight"]:
            reflection_type = "insight"
            
        importance_score = 4.0 if reflection_type == "insight" else (3.5 if reflection_type == "failure" else 3.0)
            
        for i, chunk in enumerate(chunks):
            documents.append(chunk)
            chunk_hash = hashlib.sha256(chunk.encode("utf-8", errors="ignore")).hexdigest()
            metadatas.append({
                "type": reflection_type,
                "source": "reflector",
                "source_type": "generated",
                "persona": "system",
                "importance": importance_score,
                "interaction_id": interaction_id,
                "chunk_index": i,
                "chunk_count": len(chunks),
                "content_hash": chunk_hash,
                "source_hash": source_hash,
                "ingested_at": ingested_at,
                "title": f"Reflection: {reflection_type.capitalize()}",
                "tags": tags if tags else "wintrip_reflection",
                "language": "unknown"
            })
            ids.append(f"reflector_{uuid.uuid5(uuid.NAMESPACE_URL, chunk_hash)}")
            
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"✅ [Hippocampus]: Reflectie Opgeslagen! ({len(chunks)} chunks)")
        return True

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        results = []
        # Tier 1: personal memories first (type='user_memory', importance=5)
        try:
            r = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"type": "user_memory"}
            )
            if r and r["documents"] and r["documents"][0]:
                for doc, meta in zip(r["documents"][0], r["metadatas"][0]):
                    results.append({"text": doc, "metadata": meta, "tier": "user_memory"})
        except Exception:
            pass

        # Tier 2: if no personal memories, search everything
        if not results:
            try:
                r = self.collection.query(query_texts=[query], n_results=n_results)
                if r and r["documents"] and r["documents"][0]:
                    for doc, meta in zip(r["documents"][0], r["metadatas"][0]):
                        results.append({"text": doc, "metadata": meta, "tier": "general"})
            except Exception:
                pass

        if results:
            print(f"🧠 [Hippocampus]: {len(results)} herinneringen gevonden (tier: {results[0]['tier']})")
        else:
            print("🧠 [Hippocampus]: Geen relevante herinneringen gevonden.")
        return results

    def search_reflections(self, query, n_results=3, max_distance=1.5):
        """Specifieke zoekopdracht gereserveerd voor evaluatie-inzichten."""
        print("🔎 [Hippocampus]: Gekanaliseerde zoekopdracht in reflectie-geheugen...")
        return self.search_detailed(
            query, 
            n_results=n_results, 
            max_distance=max_distance, 
            where_filter={"source": "reflector"}
        )

    def search_detailed(self, query, n_results=3, max_distance=1.2, where_filter=None):
        """Zoekt met DREMPELWAARDEN en S_final (Semantic + Metadata + Importance ranking)."""
        if self.collection.count() == 0:
            return []
            
        print(f"🔎 [Hippocampus]: Zoeken naar: '{query}' (n={n_results})")
        
        # Fetch meer items (pool) om te re-ranken
        fetch_k = max(n_results * 2, 8)
        
        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_k,
            where=where_filter
        )
        
        if not results['documents'] or len(results['documents'][0]) == 0:
            print("⚠️ [Hippocampus]: Geen resultaten gevonden.")
            return []
            
        formatted_results = []
        print(f"💡 [Hippocampus]: S_final Analyse van top {len(results['documents'][0])} fragmenten:")
        
        for i in range(len(results['documents'][0])):
            content = results['documents'][0][i]
            metadata = results['metadatas'][0][i] if (results['metadatas'] and len(results['metadatas'][0]) > i) else {}
            dist = results['distances'][0][i] if 'distances' in results and results['distances'] else 99.0
            
            if dist > max_distance:
                continue
                
            # S_final berekening
            semantic_score = max(0, 1.5 - dist) * 10
            dtype = metadata.get('type') or metadata.get('doc_type', 'unknown_legacy')
            
            # Metadata priority boost
            metadata_priority = 1.0
            if dtype == "user_memory":
                metadata_priority = 2.0
            elif dtype in ["success", "failure", "insight"]:
                metadata_priority = 1.8 # Reflecties zijn ook erg belangrijk
            elif dtype == "system_docs":
                metadata_priority = 0.5
            importance_weight = float(metadata.get('importance', 1.0)) * 0.5
            
            s_final = semantic_score + metadata_priority + importance_weight
            
            formatted_results.append({
                "content": content,
                "metadata": metadata,
                "distance": dist,
                "s_final": s_final,
                "score_log": f"Sem:{semantic_score:.2f} + Meta:{metadata_priority:.2f} + Imp:{importance_weight:.2f}"
            })
            
        # Select best matches
        formatted_results.sort(key=lambda x: x["s_final"], reverse=True)
        top_results = formatted_results[:n_results]
            
        for idx, res in enumerate(top_results):
            m = res["metadata"]
            dtype = m.get('type', m.get('doc_type', 'unknown_legacy'))
            src = m.get('source_path') or m.get('source') or 'unknown'
            snippet = res['content'][:80].replace('\n', ' ') + "..."
            
            print(f"   [{idx+1}] S_final: {res['s_final']:.2f} (Dist: {res['distance']:.2f}) | {dtype} | {src}")
            print(f"       Scores: {res['score_log']}")
            print(f"       Snippet: {snippet}")
            
        if not top_results:
            print("⚠️ [Hippocampus]: Alle ruwe hits faalden de relevantie-check.")
            
        return top_results
