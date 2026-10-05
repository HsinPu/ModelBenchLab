import json
import re
from jsonschema import validate, ValidationError

def evaluate(text, rule, settings=None, cancelled=lambda: False):
    kind = rule['kind']
    if kind == 'code':
        from .coding import evaluate_code
        return evaluate_code(text, rule['coding'], settings or {}, cancelled)
    if kind == 'manual':
        return {'version': '1', 'kind': kind, 'passed': None, 'reason': '待人工評分'}
    if kind == 'exact':
        passed = text.strip() == rule['expected'].strip()
        reason = '完全符合參考答案' if passed else '與參考答案不一致'
    elif kind == 'choice':
        match = re.fullmatch(
            r'\s*(?:(?:答案|選項)\s*(?:是|為)?\s*[:：]?\s*|Answer\s*[:：]\s*)?'
            r'[（(]?([A-D])[）)]?[.。]?\s*',
            text,
            flags=re.IGNORECASE,
        )
        passed = bool(match and match.group(1).upper() == rule['expected'].strip().upper())
        reason = '選項符合參考答案' if passed else '選項與參考答案不一致或回答格式無法辨識'
    elif kind == 'contains':
        passed = rule['expected'].casefold() in text.casefold()
        reason = '包含指定文字' if passed else '未包含指定文字'
    else:
        try:
            validate(json.loads(text), rule.get('schema', {}))
            passed, reason = True, '符合 JSON Schema'
        except (ValueError, ValidationError) as e:
            passed, reason = False, ('無法解析 JSON' if isinstance(e, ValueError) else e.message[:300])
    return {'version': '1', 'kind': kind, 'passed': passed, 'reason': reason}
