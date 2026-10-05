"""Native single-turn BFCL tools, with pinned official Python AST comparison."""
import copy
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from .bfcl_checker_source import ast_checker, Language

REPO = 'gorilla-llm/Berkeley-Function-Calling-Leaderboard'
FIXED_REVISION = '61fc0608cfd831fcfbbaa676ebdfef0ed963eeda'
CATEGORIES = {'simple': '單一工具', 'multiple': '多工具選擇', 'parallel': '多個調用',
              'parallel_multiple': '混合多工具', 'irrelevance': '不相關工具'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def runtime():
    root = Path(__file__).parent
    return {'mode': 'native-tools', 'version': 'bfcl-v3-python-ast-v1',
            'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'checker_revision': json.loads((root / 'bfcl_checker_provenance.json').read_text())['revision'],
            'checker_sha256': hashlib.sha256((root / 'bfcl_checker_source.py').read_bytes()).hexdigest()}


def run_settings(cases, settings, models):
    if not any(case['rule']['kind'] == 'tool_call' for case in cases):
        return settings
    if not all(case['rule']['kind'] == 'tool_call' for case in cases):
        raise HTTPException(422, 'BFCL 不可與其他評分類型混合測試')
    if settings['repeats'] != 1:
        raise HTTPException(422, 'BFCL 第一版每題一次，請將重複次數設為 1')
    for model in models:
        supported = (model.get('catalog') or {}).get('supported_parameters')
        if model['provider'] == 'openrouter' and isinstance(supported, list) and 'tools' not in supported:
            raise HTTPException(422, f"{model['name']} 目錄未宣告 tools 能力，請選支援工具調用的模型")
    return {**settings, 'bfcl_runtime': runtime()}


def tools_for(spec):
    def schema(value):
        if isinstance(value, list):
            return [schema(v) for v in value]
        if not isinstance(value, dict):
            return value
        # Only schema-valued keywords recurse. enum/const/default/examples and
        # extension data are literals, even when they contain a key named type.
        out = copy.deepcopy(value)
        maps = {'properties', 'patternProperties', '$defs', 'definitions', 'dependentSchemas'}
        singles = {'items', 'additionalItems', 'additionalProperties', 'contains',
                   'propertyNames', 'not', 'if', 'then', 'else',
                   'unevaluatedItems', 'unevaluatedProperties', 'contentSchema'}
        arrays = {'allOf', 'anyOf', 'oneOf', 'prefixItems'}
        for key, child in value.items():
            if key in maps and isinstance(child, dict):
                out[key] = {name: schema(definition) for name, definition in child.items()}
            elif key in singles or key in arrays:
                out[key] = schema(child)
            elif key == 'dependencies' and isinstance(child, dict):
                out[key] = {name: schema(definition) if isinstance(definition, dict)
                            else copy.deepcopy(definition) for name, definition in child.items()}
        if isinstance(out.get('type'), str):
            out['type'] = {'dict': 'object', 'float': 'number', 'tuple': 'array'}.get(out['type'], out['type'])
            if out['type'] == 'any':
                out.pop('type')
        return out
    # Every name has a stable, collision-free alias, including dotted/long names.
    return [{'type': 'function', 'function': {'name': f'bfcl_{i}',
             'description': f"{function['name']}: {function.get('description', '')}",
             'parameters': schema(function['parameters'])}}
            for i, function in enumerate(spec['functions'])]


def evaluate_tools(result, spec, settings):
    base = {'kind': 'tool_call', 'version': 'bfcl-v3-python-ast-v1',
            'category': spec['category'], 'passed': None}
    if settings.get('bfcl_runtime') != runtime():
        return {**base, 'error': True, 'reason': 'BFCL 評分版本已變更，無法使用原版本重新評分'}
    calls = result.get('tool_calls', [])
    if spec['category'] == 'irrelevance':
        passed = not calls
        return {**base, 'passed': passed, 'reason': '正確避免工具調用' if passed else '不應調用工具'}
    parsed = []
    try:
        for call in calls:
            name = call['name']
            aliases = {f'bfcl_{i}': f['name'] for i, f in enumerate(spec['functions'])}
            if name not in aliases:
                return {**base, 'passed': False, 'reason': '調用了未提供的工具', 'error_type': 'unknown_tool'}
            arguments = json.loads(call['arguments'])
            if not isinstance(arguments, dict):
                raise ValueError('arguments must be an object')
            json.dumps(arguments, allow_nan=False)
            parsed.append({aliases[name]: arguments})
    except (ValueError, TypeError, KeyError, RecursionError):
        return {**base, 'passed': False, 'reason': '工具參數不是有效 JSON 物件', 'error_type': 'invalid_arguments'}
    if not parsed:
        return {**base, 'passed': False, 'reason': '缺少必要的工具調用', 'error_type': 'missing_call'}
    try:
        checked = ast_checker(copy.deepcopy(spec['functions']), parsed,
                              copy.deepcopy(spec['answers']), Language.PYTHON, spec['category'], 'native')
        # Do not expose arbitrary nested checker diagnostics or expected answers in polling.
        return {**base, 'passed': checked['valid'], 'reason': '工具與參數符合參考答案' if checked['valid'] else '工具選擇、調用數量或參數不符合參考答案',
                'error_type': checked.get('error_type'), 'calls': parsed}
    except OverflowError:
        # The official checker coerces integer arguments to float. A candidate
        # value outside the float range is an incorrect answer, not a broken runner.
        return {**base, 'passed': False, 'error': False,
                'reason': '工具數值參數超出可比較範圍', 'error_type': 'numeric_range', 'calls': parsed}
    except Exception:
        return {**base, 'error': True, 'reason': 'BFCL 評分器失敗；可重新評分，不重新生成'}
