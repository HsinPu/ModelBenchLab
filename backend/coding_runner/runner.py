"""Supervisor runs one candidate in a disposable, resource-limited container."""
import json
import multiprocessing as mp
import os
import sys


def candidate(payload, pipe):
    sink = os.open(os.devnull, os.O_WRONLY)
    os.dup2(sink, 1)
    os.dup2(sink, 2)
    try:
        code = compile(payload['program'], '<candidate>', 'exec')
    except (SyntaxError, ValueError):
        pipe.send({'passed': False, 'outcome': 'syntax_error'})
        return
    try:
        tests = compile(payload['tests'], '<tests>', 'exec')
        scope = {}
        exec(tests, scope)
        check = scope['check']
    except BaseException:
        pipe.send({'passed': None, 'outcome': 'suite_error'})
        return
    try:
        namespace = {}
        exec(code, namespace)
        check(namespace[payload['entry_point']])
        pipe.send({'passed': True, 'outcome': 'passed'})
    except AssertionError:
        pipe.send({'passed': False, 'outcome': 'wrong_answer'})
    except BaseException:
        pipe.send({'passed': False, 'outcome': 'runtime_error'})


if __name__ == '__main__':
    payload = json.load(sys.stdin)
    ctx = mp.get_context('fork')
    receive, send = ctx.Pipe(duplex=False)
    process = ctx.Process(target=candidate, args=(payload, send))
    process.start()
    send.close()
    process.join(payload['timeout'])
    if process.is_alive():
        process.kill()
        process.join()
        result = {'passed': False, 'outcome': 'time_limit'}
    elif receive.poll():
        try:
            result = receive.recv()
        except EOFError:
            result = {'passed': False, 'outcome': 'runtime_error'}
    else:
        result = {'passed': False, 'outcome': 'runtime_error'}
    print(json.dumps(result), flush=True)
