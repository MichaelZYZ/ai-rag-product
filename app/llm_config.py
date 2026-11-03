"""Provider presets and local credentials, kept outside the tracked database."""
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

PROVIDERS = [
    {'id': 'openrouter', 'name': 'OpenRouter · 免费模型（默认）',
     'base_url': 'https://openrouter.ai/api/v1',
     'models': [{'id': 'openrouter/free', 'name': '免费模型自动路由'}],
     'key_url': 'https://openrouter.ai/keys',
     'docs_url': 'https://openrouter.ai/collections/free-models/',
     'note': '需要自备 API Key；免费模型有配额与限速，自动路由的实际模型可能变化。'},
    {'id': 'groq', 'name': 'Groq · Free Plan',
     'base_url': 'https://api.groq.com/openai/v1',
     'models': [{'id': 'openai/gpt-oss-20b', 'name': 'GPT OSS 20B'},
                {'id': 'openai/gpt-oss-120b', 'name': 'GPT OSS 120B'},
                {'id': 'qwen/qwen3.8-27b', 'name': 'Qwen 3.8 27B'}],
     'key_url': 'https://console.groq.com/keys',
     'docs_url': 'https://console.groq.com/docs/rate-limits',
     'note': '需要自备 API Key；请使用 Free Plan，额度以账户控制台为准。'},
    {'id': 'gemini', 'name': 'Google Gemini · 免费层',
     'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai',
     'models': [{'id': 'gemini-3.8-flash', 'name': 'Gemini 3.8 Flash'}],
     'key_url': 'https://aistudio.google.com/apikey',
     'docs_url': 'https://ai.google.dev/gemini-api/docs/pricing',
     'note': '需要自备 API Key；免费层可用性受地区、账户和配额限制，请核对账户计费。'},
    {'id': 'custom', 'name': '自定义兼容 API / 本机模型', 'base_url': '', 'models': [],
     'key_url': '', 'docs_url': '', 'note': '自行填写 Base URL、模型名和密钥；自定义服务不保证免费。'}
]


def config_path(db_path):
    return Path(db_path).with_suffix('.llm.json')


def read_local(db_path):
    path = config_path(db_path)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise ValueError('本机模型配置无法读取，请重新保存配置') from None


def effective(db_path):
    saved = read_local(db_path)
    if saved:
        provider = next((p for p in PROVIDERS if p['id'] == saved.get('provider_id')), None)
        if provider is None:
            raise ValueError('本机模型服务商配置无效')
        return {'provider_id': provider['id'], 'base_url': saved.get('base_url', ''),
                'model': saved.get('model', ''), 'api_key': saved.get('keys', {}).get(provider['id'], ''),
                'answer_mode': saved.get('answer_mode', 'llm'), 'source': 'local'}
    endpoint, key, model = [os.getenv(k, '').strip() for k in ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL')]
    using_env = bool(endpoint or model or key)
    return {'provider_id': 'custom' if using_env else 'openrouter',
            'base_url': endpoint.rstrip('/') if using_env else PROVIDERS[0]['base_url'],
            'model': model if using_env else 'openrouter/free', 'api_key': key,
            'answer_mode': os.getenv('RAG_ANSWER_MODE', 'auto'), 'source': 'environment' if using_env else 'default'}


def enabled(db_path):
    if os.getenv('RAG_LLM_DISABLED') == '1':
        return False
    config = effective(db_path)
    return all(config[k] for k in ('base_url', 'api_key', 'model'))


def public_config(db_path):
    config = effective(db_path)
    config['has_api_key'] = bool(config.pop('api_key'))
    config['configured'] = enabled(db_path)
    return config


def validate_url(value):
    url = urlsplit(value)
    local = url.hostname in ('localhost', '127.0.0.1', '::1')
    if (not url.hostname or (url.scheme != 'https' and not (url.scheme == 'http' and local))
            or url.username or url.password or url.query or url.fragment):
        raise ValueError('Base URL 必须为 HTTPS 或本机 HTTP 地址，且不能含密钥、查询参数或片段')


def save(db_path, provider_id, model='', base_url='', api_key=None, answer_mode='llm'):
    provider = next((p for p in PROVIDERS if p['id'] == provider_id), None)
    if provider is None:
        raise ValueError('请选择有效服务商')
    if answer_mode not in ('auto', 'extractive', 'llm'):
        raise ValueError('回答模式无效')
    if provider_id != 'custom':
        base_url = provider['base_url']
        model = model.strip() or provider['models'][0]['id']
        if model not in {m['id'] for m in provider['models']}:
            raise ValueError('请选择该服务商支持的预设模型；其他模型请用自定义服务')
    base_url, model = base_url.strip().rstrip('/'), model.strip()
    validate_url(base_url)
    if not model or len(model) > 200 or any(ord(c) < 32 for c in model):
        raise ValueError('请填写有效模型名（最多 200 字）')
    saved = read_local(db_path)
    keys = dict(saved.get('keys', {}))
    if provider_id == 'custom' and saved.get('base_url') != base_url:
        # A custom URL can change destination; never carry its old key to a new host.
        keys.pop('custom', None)
    if api_key:
        api_key = api_key.strip()
        if len(api_key) > 4096 or any(ord(c) < 32 for c in api_key):
            raise ValueError('API Key 格式无效')
        keys[provider_id] = api_key
    # Empty fields only retain this provider's own saved credential, never another provider's.
    config = {'provider_id': provider_id, 'model': model, 'base_url': base_url,
              'answer_mode': answer_mode, 'keys': keys}
    path = config_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.llm-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(config, handle, ensure_ascii=False)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return public_config(db_path)


def reset(db_path):
    path = config_path(db_path)
    if path.exists():
        path.unlink()
    return public_config(db_path)


def error_message(kind):
    return {'HTTP401': 'API Key 无效或已失效，请检查密钥。',
            'HTTP403': '服务拒绝访问，请检查账户权限、地区和模型授权。',
            'HTTP404': '服务地址或模型不可用，请检查配置。',
            'HTTP429': '免费额度或请求频率已达上限，请稍后再试或切换服务商。',
            'TimeoutError': '模型响应超时，请稍后再试。',
            'URLError': '无法连接模型服务，请检查网络和服务地址。',
            'LLMNotConfiguredOrEmpty': '尚未配置可用模型或模型没有返回答案，请在知识配置中检查服务与密钥。'
            }.get(kind, '模型生成服务暂不可用，请检查模型配置或稍后重试。')
