from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from . import core
from . import semantic
from . import llm_config

app = FastAPI(title='产品知识库问答演示', version='1.0')
core.init_db()
STATIC = Path(__file__).parent / 'static'

class ProductInput(BaseModel):
    id: str
    name: str
    aliases: list[str] = []

class AskInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    product_id: Optional[str] = None
    version: Optional[str] = None

class FeedbackInput(BaseModel):
    session_id: str
    message_id: int = Field(gt=0)
    rating: int
    note: str = ''

class GapAnswerInput(BaseModel):
    product_id: str
    version: str
    question: str
    answer: str

class PromptInput(BaseModel):
    prompt: str

class LLMConfigInput(BaseModel):
    provider_id: str
    model: str = Field(default='', max_length=200)
    base_url: str = Field(default='', max_length=1000)
    api_key: Optional[str] = Field(default=None, max_length=4096)
    answer_mode: str = 'llm'

@app.get('/api/llm/config')
def get_llm_config():
    return {'providers': llm_config.PROVIDERS, **llm_config.public_config(core.DB_PATH)}

@app.put('/api/llm/config')
def save_llm_config(data: LLMConfigInput):
    try:
        return llm_config.save(core.DB_PATH, provider_id=data.provider_id, model=data.model,
                               base_url=data.base_url, api_key=data.api_key, answer_mode=data.answer_mode)
    except ValueError as error:
        raise HTTPException(400, str(error))

@app.delete('/api/llm/config')
def reset_llm_config():
    return llm_config.reset(core.DB_PATH)

@app.post('/api/llm/test')
def test_llm_config():
    import urllib.error
    import urllib.request
    if not llm_config.enabled(core.DB_PATH):
        raise HTTPException(400, '请先选择服务商并保存 API Key')
    config = llm_config.effective(core.DB_PATH)
    payload = json.dumps({'model': config['model'], 'temperature': 0, 'max_tokens': 64,
                          'messages': [{'role': 'user', 'content': '请仅回复 OK。'}]}).encode()
    request = urllib.request.Request(config['base_url'] + '/chat/completions', data=payload,
            headers={'Authorization': 'Bearer ' + config['api_key'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.load(response)
        content = result['choices'][0]['message']['content']
        if not isinstance(content, str) or not content.strip():
            raise ValueError('empty response')
        return {'ok': True, 'model': str(result.get('model') or config['model']),
                'message': '连接成功，模型已返回内容。'}
    except Exception as error:
        kind = 'HTTP' + str(error.code) if isinstance(error, urllib.error.HTTPError) else type(error).__name__
        raise HTTPException(503, llm_config.error_message(kind))

@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html', headers={'Cache-Control': 'no-store'})

@app.get('/api/rag/status')
def rag_status():
    import importlib.util
    with core.connect() as db:
        chunks = db.execute('SELECT count(*) FROM chunks').fetchone()[0]
        indexed = db.execute('''SELECT count(*) FROM semantic_vectors s JOIN chunks c ON c.id=s.chunk_id
                              WHERE identity=?''', (semantic.config()[3],)).fetchone()[0]
    return {'retriever': os.getenv('RAG_RETRIEVER', 'hash'),
            'answer_mode': llm_config.effective(core.DB_PATH)['answer_mode'],
            'embedding_provider': semantic.config()[0], 'embedding_model': semantic.config()[1],
            'faiss_available': importlib.util.find_spec('faiss') is not None,
            'local_embedding_available': importlib.util.find_spec('sentence_transformers') is not None,
            'chunks': chunks, 'indexed_chunks': indexed,
            'llm_configured': core.answer_prompt_config()['model_enabled']}

@app.post('/api/rag/reindex')
def reindex():
    try:
        return semantic.index_chunks(core.connect)
    except Exception as error:
        raise HTTPException(503, '语义索引构建失败（' + type(error).__name__ + '），请检查依赖、模型和网络配置')

@app.get('/api/products')
def products():
    with core.connect() as db:
        rows = db.execute('SELECT * FROM products ORDER BY name').fetchall()
        result = []
        for p in rows:
            versions = [r['version'] for r in db.execute(
                'SELECT DISTINCT version FROM documents WHERE product_id=? ORDER BY version DESC', (p['id'],))]
            result.append({'id': p['id'], 'name': p['name'], 'aliases': json.loads(p['aliases']), 'versions': versions})
        return result

@app.get('/api/products/featured')
def featured_products():
    catalog = core.product_catalog()
    return catalog[:6] if any(p['consultation_count'] for p in catalog) else catalog

@app.get('/api/products/catalog')
def indexed_products():
    return core.product_catalog()

@app.get('/api/products/search')
def search_products(q: str):
    if len(q) > 200:
        raise HTTPException(400, '搜索内容不能超过 200 字')
    return core.search_products(q)

@app.post('/api/products')
def create_product(data: ProductInput):
    try:
        core.add_product(data.id, data.name, data.aliases)
        return {'ok': True}
    except ValueError as e:
        raise HTTPException(400, str(e))

async def document_request(product_id, version, category, title, file,
                           remove_page_markers, remove_duplicates, max_chars, overlap,
                           selected_faqs=None, preview=False, review=False):
    try:
        content = await file.read(5 * 1024 * 1024 + 1)
        settings = dict(remove_page_markers=remove_page_markers,
                        remove_duplicates=remove_duplicates, max_chars=max_chars,
                        overlap=overlap, include_training=review or preview)
        if preview:
            result = core.prepare_document(product_id, version, file.filename, content, **settings)
            result.pop('product_name')
            return result
        selection = json.loads(selected_faqs) if selected_faqs is not None else None
        return core.add_document(product_id, version.strip(), category.strip(),
                                 title.strip() or file.filename, file.filename, content,
                                 selected_faqs=selection, **settings)
    except (ValueError, UnicodeError, zipfile.BadZipFile, ImportError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.post('/api/documents/preview')
async def preview_document(product_id: str = Form(...), version: str = Form(...),
                           file: UploadFile = File(...),
                           remove_page_markers: bool = Form(True),
                           remove_duplicates: bool = Form(True),
                           max_chars: int = Form(360), overlap: int = Form(50)):
    return await document_request(product_id, version, '', '', file,
                                  remove_page_markers, remove_duplicates, max_chars, overlap,
                                  preview=True)


@app.post('/api/documents')
async def upload_document(product_id: str = Form(...), version: str = Form(...),
                          category: str = Form('产品说明'), title: str = Form(''),
                          file: UploadFile = File(...),
                          remove_page_markers: bool = Form(True),
                          remove_duplicates: bool = Form(True),
                          max_chars: int = Form(360), overlap: int = Form(50),
                          selected_faqs: Optional[str] = Form(None), review: bool = Form(False)):
    return await document_request(product_id, version, category, title, file,
                                  remove_page_markers, remove_duplicates, max_chars, overlap,
                                  selected_faqs, review=review)

@app.get('/api/documents')
def documents(product_id: Optional[str] = None):
    with core.connect() as db:
        if product_id:
            rows = db.execute('SELECT d.*, count(c.id) chunks, (SELECT count(*) FROM faqs f WHERE f.document_id=d.id) faqs FROM documents d LEFT JOIN chunks c ON c.document_id=d.id WHERE d.product_id=? GROUP BY d.id ORDER BY d.created_at DESC', (product_id,))
        else:
            rows = db.execute('SELECT d.*, count(c.id) chunks, (SELECT count(*) FROM faqs f WHERE f.document_id=d.id) faqs FROM documents d LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.created_at DESC')
        return [{**dict(r), 'cleaning_report': json.loads(r['cleaning_report'])} for r in rows]

@app.get('/api/faqs')
def faqs(product_id: str, version: str, limit: int = 12):
    return core.list_faqs(product_id, version, limit)

@app.post('/api/faqs/train')
def train_faqs(product_id: Optional[str] = None, version: Optional[str] = None):
    return core.bootstrap_faqs(product_id, version)

@app.delete('/api/documents/{document_id}')
def delete_document(document_id: str):
    with core.connect() as db:
        row = db.execute('DELETE FROM documents WHERE id=? RETURNING id', (document_id,)).fetchone()
        if not row:
            raise HTTPException(404, '文档不存在')
    return {'ok': True}

@app.post('/api/ask')
def ask(data: AskInput):
    try:
        return core.ask(data.question, data.session_id, data.product_id, data.version)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as error:
        raise HTTPException(503, '问答服务暂不可用（' + type(error).__name__ + '），请检查检索配置')

@app.post('/api/feedback')
def feedback(data: FeedbackInput):
    if data.rating not in (-1, 1):
        raise HTTPException(400, '请选择有帮助或没帮助')
    with core.connect() as db:
        message = db.execute('SELECT id FROM messages WHERE id=? AND session_id=? AND role=? AND status=?',
                             (data.message_id, data.session_id, 'assistant', 'answered')).fetchone()
        if not message:
            raise HTTPException(404, '对应回答不存在或不可评价')
        db.execute('''INSERT INTO feedback(session_id,message_id,rating,note,created_at)
                      VALUES(?,?,?,?,?) ON CONFLICT(message_id) DO UPDATE SET
                      rating=excluded.rating,note=excluded.note,created_at=excluded.created_at''',
                   (data.session_id, data.message_id, data.rating, data.note[:500], core.now()))
    return {'ok': True, 'message_id': data.message_id, 'rating': data.rating}

@app.post('/api/gaps/{gap_id}/answer')
def answer_gap(gap_id: int, data: GapAnswerInput):
    try:
        return core.supplement_gap(gap_id, data.product_id, data.version,
                                   data.question, data.answer)
    except KeyError as e:
        raise HTTPException(404, e.args[0])
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post('/api/faqs/manual')
def add_manual_faq(data: GapAnswerInput):
    try:
        return core.supplement_gap(None, data.product_id, data.version,
                                   data.question, data.answer)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get('/api/prompt')
def get_prompt():
    return core.answer_prompt_config()

@app.put('/api/prompt')
def update_prompt(data: PromptInput):
    try:
        return core.save_answer_prompt(data.prompt)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.delete('/api/prompt')
def reset_prompt():
    return core.reset_answer_prompt()

@app.get('/api/stats')
def stats():
    with core.connect() as db:
        counts = dict(db.execute('SELECT status,count(*) n FROM messages WHERE role="assistant" GROUP BY status').fetchall())
        total = sum(counts.values())
        return {'questions': total, 'answered': counts.get('answered', 0),
                'handoffs': counts.get('handoff', 0),
                'unanswered': counts.get('no_answer', 0) + counts.get('no_product', 0),
                'auto_faqs': db.execute("SELECT count(*) FROM faqs WHERE kind IN ('auto','rule','trained')").fetchone()[0],
                'open_gap_count': db.execute('SELECT count(*) FROM unanswered WHERE resolved_at IS NULL').fetchone()[0],
                'resolution_rate': round(counts.get('answered', 0) / total, 3) if total else 0,
                'feedback_positive': db.execute('SELECT count(*) FROM feedback WHERE rating=1').fetchone()[0],
                'feedback_negative': db.execute('SELECT count(*) FROM feedback WHERE rating=-1').fetchone()[0],
                'top_unanswered': [dict(r) for r in db.execute('''
                    SELECT min(u.id) id,u.question,u.product_id,u.version,
                           coalesce(p.name,'未确认产品') product_name,count(*) count
                    FROM unanswered u LEFT JOIN products p ON p.id=u.product_id
                    WHERE u.resolved_at IS NULL
                    GROUP BY u.question,u.product_id,u.version
                    ORDER BY count DESC,id LIMIT 10''')]}

@app.get('/api/handoffs')
def handoffs():
    with core.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM handoffs ORDER BY created_at DESC LIMIT 50')]


@app.get('/api/evaluation')
def evaluation():
    """Run fixed evaluation cases against a read-only snapshot of current knowledge."""
    with core.connect() as db:
        history = [dict(row) for row in db.execute('''
            SELECT id,created_at,product_id,version,documents_scanned,faqs_added,total_faqs
            FROM training_runs ORDER BY id''')]
        with tempfile.TemporaryDirectory(prefix='rag-evaluation-') as temp:
            snapshot = Path(temp) / 'snapshot.sqlite3'
            with sqlite3.connect(snapshot) as target:
                db.backup(target)
            environment = os.environ.copy()
            environment['RAG_DB'] = str(snapshot)
            environment['RAG_LLM_DISABLED'] = '1'
            for key in ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL'):
                environment.pop(key, None)
            try:
                process = subprocess.run(
                    [sys.executable, '-m', 'app.evaluation_worker'], cwd=core.ROOT,
                    env=environment, capture_output=True, text=True, timeout=45, check=True)
                result = json.loads(process.stdout)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
                raise HTTPException(500, '评估运行失败，请检查服务日志') from error
    return {'training_history': history, **result}
