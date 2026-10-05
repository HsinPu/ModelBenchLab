"""Download pinned BFCL data and check reference calls; no model inference or DB writes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.bfcl import FIXED_REVISION, CATEGORIES, evaluate_tools, runtime
from app.bfcl_benchmarks import PreviewInput, build_preview


def candidate(value, definition):
    if definition['type'] == 'dict' and isinstance(value, dict):
        return {key: next(v for v in variants if v != '') for key, variants in value.items() if any(v != '' for v in variants)}
    if definition['type'] in ('array', 'tuple') and definition.get('items', {}).get('type') == 'dict':
        return [candidate(v, {'type': 'dict'}) for v in value]
    return value


if __name__ == '__main__':
    import json
    data = build_preview(PreviewInput(revision=FIXED_REVISION, categories=list(CATEGORIES), limit=None))
    failures = []
    settings = {'bfcl_runtime': runtime()}
    for case in data['cases']:
        spec = case['rule']['bfcl']
        calls = []
        for answer in spec['answers']:
            name, parameters = next(iter(answer.items()))
            # The official simple checker compares the only function's parameters;
            # simple_363's answer uses an unqualified name. Preserve original data.
            index = 0 if spec['category'] == 'simple' else next(i for i, f in enumerate(spec['functions']) if f['name'] == name)
            definitions = spec['functions'][index]['parameters']['properties']
            required = spec['functions'][index]['parameters']['required']
            arguments = {key: candidate(next((v for v in variants if v != ''), ''), definitions.get(key, {'type': 'any'}))
                         for key, variants in parameters.items() if key in required or '' not in variants}
            calls.append({'name': f'bfcl_{index}', 'arguments': json.dumps(arguments)})
        result = evaluate_tools({'tool_calls': calls}, spec, settings)
        if not result['passed']:
            failures.append((spec['task_id'], result.get('error_type'), result.get('error')))
    print('counts:', data['counts'])
    print('reference calls passed:', len(data['cases']) - len(failures), '/', len(data['cases']))
    if failures:
        print('failures:', failures[:20])
        raise SystemExit(1)
