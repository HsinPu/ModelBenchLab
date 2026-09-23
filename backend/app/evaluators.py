import json
from jsonschema import validate, ValidationError

def evaluate(text, rule):
    kind = rule['kind']
    if kind == 'manual':
        return {'version': '1', 'kind': kind, 'passed': None, 'reason': '待人工評分'}
    if kind == 'exact':
        passed = text.strip() == rule['expected'].strip()
        reason = '完全符合參考答案' if passed else '與參考答案不一致'
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
