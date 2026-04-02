import os
import requests
import chromadb
import uuid
from dotenv import load_dotenv

load_dotenv()

def chunk_text(text):
    """Splits input text into chunks of 1000 characters with 100 character overlap."""
    chunk_size = 1000
    overlap = 100
    chunks = []
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    return chunks

def generate_embeddings(chunks):
    """Generates embeddings for each chunk using the local Ollama API via env config."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_api_url = f"{base_url}/api/embeddings"
    headers = {'Content-Type': 'application/json'}
    model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    
    embeddings = []
    for chunk in chunks:
        data = {'prompt': chunk, 'model': model}
        try:
            response = requests.post(ollama_api_url, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                embeddings.append(response.json()['embedding'])
            else:
                print(f"Error generating embedding for chunk: {chunk[:50]}... Status: {response.status_code}")
        except Exception as e:
            print(f"Connection error to Ollama at {ollama_api_url}: {e}")
    return embeddings

def store_in_chroma(chunks, embeddings, source_metadata, collection_name):
    """Stores chunks and embeddings in ChromaDB using the configured brain path."""
    chromadb_storage_path = os.getenv("WINTRIP_DB_PATH", "./wintrip_brain")
    os.makedirs(chromadb_storage_path, exist_ok=True)
    
    client = chromadb.PersistentClient(path=chromadb_storage_path)
    collection = client.get_or_create_collection(name=collection_name)
    
    ids = [str(uuid.uuid4()) for _ in range(len(chunks))]
    metadatas = []
    for i in range(len(chunks)):
        meta = source_metadata.copy() if isinstance(source_metadata, dict) else {"source": str(source_metadata)}
        meta['chunk_index'] = i
        metadatas.append(meta)

    if chunks and embeddings:
        collection.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Successfully stored {len(chunks)} chunks in collection '{collection_name}' at {chromadb_storage_path}.")

def digest_text(text, source_metadata, collection_name):
    """Main function to chunk text, generate embeddings, and store them."""
    chunks = chunk_text(text)
    embeddings = generate_embeddings(chunks)
    if chunks and embeddings:
        store_in_chroma(chunks, embeddings, source_metadata, collection_name)
        return True
    else:
        print("Digestion failed: No chunks or embeddings generated.")
        return False

