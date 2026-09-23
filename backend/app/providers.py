import time
import httpx

class ProviderError(Exception):
    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable

def generate(config, messages, settings, key='', client=None):
    start = time.perf_counter()
    if config['provider'] == 'demo':
        text = messages[-1]['content']
        answers = {'2 + 2': '4', '法國': '巴黎', 'JSON': '{"name":"Alice","age":30}', 'Python': 'Python 是一種程式語言。', '翻譯': 'Hello', '水': 'H2O', '排序': '1, 2, 3', '首都': '東京', '布林': 'true', '摘要': '本工具協助比較模型的品質與效能。'}
        answer = next((v for k, v in answers.items() if k in text), '這是示範回答，請接入真實模型進行正式評估。')
        if config['model'] == 'demo-experimental' and any(k in text for k in ['2 + 2', 'JSON', '翻譯']):
            answer = '示範：此模型未符合預期答案。'
        time.sleep(0.12 if config['model'] == 'demo-stable' else 0.06)
        return {'output': answer, 'latency_ms': round((time.perf_counter()-start)*1000), 'input_tokens': None, 'output_tokens': None, 'finish_reason': 'stop', 'demo': True}
    own = client is None
    client = client or httpx.Client(timeout=settings['timeout'], follow_redirects=False)
    try:
        response = client.post(config['endpoint'].rstrip('/') + '/chat/completions', headers={'Authorization': 'Bearer ' + key} if key else {}, json={'model': config['model'], 'messages': messages, 'temperature': settings['temperature'], 'max_tokens': settings['max_tokens'], 'stream': False})
        if response.status_code >= 400:
            # Never persist upstream bodies: they can contain credentials or private headers.
            raise ProviderError('模型服務 HTTP ' + str(response.status_code), response.status_code == 429 or response.status_code >= 500)
        data = response.json()
        choice = data['choices'][0]
        output = choice['message']['content']
        if not isinstance(output, str):
            raise ValueError('Non-text content')
        usage = data.get('usage') or {}
        return {'output': output, 'latency_ms': round((time.perf_counter()-start)*1000), 'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens'), 'finish_reason': choice.get('finish_reason'), 'demo': False}
    except httpx.TimeoutException:
        raise ProviderError('模型請求逾時；上游可能已執行並計費', True)
    except httpx.RequestError:
        raise ProviderError('無法連線到模型服務', True)
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        raise ProviderError('模型回應格式不符合 chat/completions 文字格式')
    finally:
        if own: client.close()
