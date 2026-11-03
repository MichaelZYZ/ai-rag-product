"""Semantic embeddings with durable vectors and a scope-filtered FAISS index.

Hash vectors remain a separate baseline. Models/configurations never share vectors.
"""
import hashlib
import json
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

os.environ.setdefault('HF_HOME', str(Path(__file__).resolve().parents[1] / '.cache/huggingface'))


def config():
    provider = os.getenv('EMBEDDING_PROVIDER', 'local')
    if provider not in ('local', 'api'):
        raise ValueError('EMBEDDING_PROVIDER 必须为 local 或 api')
    model = os.getenv('EMBEDDING_MODEL', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    endpoint = os.getenv('EMBEDDING_BASE_URL', '').rstrip('/') if provider == 'api' else ''
    identity = hashlib.sha256(json.dumps([provider, model, endpoint]).encode()).hexdigest()
    return provider, model, endpoint, identity


@lru_cache(maxsize=2)
def local_model(name):
    import torch
    # Keep torch/FAISS OpenMP pools bounded on small classroom machines.
    torch.set_num_threads(int(os.getenv('RAG_EMBEDDING_THREADS', '1')))
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(name)


def normalize(values):
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or not matrix.shape[1] or not np.isfinite(matrix).all():
        raise ValueError('Embedding 必须为有限数值的二维矩阵')
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError('Embedding 不能为零向量')
    return np.ascontiguousarray(matrix / norms)


def embed(texts):
    provider, model, endpoint, _ = config()
    if provider == 'local':
        return normalize(local_model(model).encode(texts, show_progress_bar=False))
    key = os.getenv('EMBEDDING_API_KEY', '')
    if not endpoint or not key:
        raise ValueError('API Embedding 需要 EMBEDDING_BASE_URL 和 EMBEDDING_API_KEY')
    request = urllib.request.Request(endpoint + '/embeddings',
        data=json.dumps({'model': model, 'input': texts, 'encoding_format': 'float'}).encode(),
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)['data']
    data.sort(key=lambda item: item['index'])
    if [item['index'] for item in data] != list(range(len(texts))):
        raise ValueError('Embedding 响应数量或序号不匹配')
    return normalize([item['embedding'] for item in data])


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS semantic_vectors(
        chunk_id TEXT NOT NULL, identity TEXT NOT NULL, content_hash TEXT NOT NULL,
        vector BLOB NOT NULL, dimension INTEGER NOT NULL,
        PRIMARY KEY(chunk_id,identity),
        FOREIGN KEY(chunk_id) REFERENCES chunks(id) ON DELETE CASCADE)''')


def index_chunks(connect, product_id=None, version=None):
    """Embed missing/changed chunks in batches, outside the write transaction."""
    _, _, _, identity = config()
    with connect() as db:
        ensure_schema(db)
        rows = db.execute('''SELECT c.*,s.content_hash FROM chunks c
            LEFT JOIN semantic_vectors s ON s.chunk_id=c.id AND s.identity=?
            WHERE (? IS NULL OR c.product_id=?) AND (? IS NULL OR c.version=?)
            ORDER BY c.id''', (identity, product_id, product_id, version, version)).fetchall()
    pending = []
    for row in rows:
        digest = hashlib.sha256(row['text'].encode()).hexdigest()
        if row['content_hash'] != digest:
            pending.append((row, digest))
    for start in range(0, len(pending), 32):
        batch = pending[start:start + 32]
        vectors = embed([row['text'] for row, _ in batch])
        if len(vectors) != len(batch):
            raise ValueError('Embedding 数量不匹配')
        with connect() as db:
            for (row, digest), vector in zip(batch, vectors):
                # A document may have been deleted while the model was running.
                if db.execute('SELECT 1 FROM chunks WHERE id=?', (row['id'],)).fetchone():
                    db.execute('INSERT OR REPLACE INTO semantic_vectors VALUES(?,?,?,?,?)',
                               (row['id'], identity, digest, vector.tobytes(), len(vector)))
    return {'chunks': len(rows), 'embedded': len(pending), 'identity': identity,
            'model': config()[1]}


def retrieve(connect, question, product_id, version, top_k):
    if top_k < 1:
        return []
    import faiss
    faiss.omp_set_num_threads(int(os.getenv('RAG_EMBEDDING_THREADS', '1')))
    index_chunks(connect, product_id, version)
    with connect() as db:
        rows = db.execute('''SELECT c.*,s.vector AS semantic_vector,s.dimension
            FROM chunks c JOIN semantic_vectors s ON s.chunk_id=c.id
            WHERE c.product_id=? AND c.version=? AND s.identity=? ORDER BY c.id''',
            (product_id, version, config()[3])).fetchall()
    if not rows:
        return []
    dimensions = {row['dimension'] for row in rows}
    query = embed([question])
    if dimensions != {query.shape[1]}:
        raise ValueError('Embedding 维度改变，请更换 EMBEDDING_MODEL 标识并重新建索引')
    matrix = np.stack([np.frombuffer(row['semantic_vector'], dtype=np.float32) for row in rows])
    index = faiss.IndexFlatIP(query.shape[1])
    index.add(matrix)
    scores, ids = index.search(query, min(top_k, len(rows)))
    return [{'chunk_id': rows[i]['id'], 'source': rows[i]['source'],
             'category': rows[i]['category'], 'text': rows[i]['text'],
             'score': round(float(score), 4)} for score, i in zip(scores[0], ids[0])]
