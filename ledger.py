#!/usr/bin/env python3
"""Unit ledger: what each translation does with the original's information.

One call per window shows the judge the original and every chosen version at once, blind and shuffled (A, B, C...).
The judge splits the original into typed information units and marks each unit per version: K kept, C compressed,
D dropped, X changed; it also lists what each version adds. `score` turns the calls into rates per 100 units.

    python3 ledger.py run <bench.json> <out_dir> --systems a,b,c [--name ledger] [--runs 2] [--backend claude|gemini]
                          [--model gemini-4-hydrogen] [--effort high] [--concurrency 4]
    python3 ledger.py score <out_dir>

The prompt is prompts/unit_ledger.md. Backends: `claude` uses judge.py's single call (JUDGE_BACKEND and its model
apply); `gemini` calls the Gemini API with GEMINI_API_KEY. In a check against 78 of the author's own verdicts, Gemini 4
Hydrogen at high thinking agreed 79% of the time, Claude Opus 5.5 at low 69%; every judge was right on "kept" and
over-marks "changed" and "compressed" where a translator used an idiomatic equivalent, so read those two as upper
bounds. Marks shift a little with the number of versions in a call (about two units of "kept" between a six- and an
eight-version call in examples/prologue), so compare versions judged in the same call, or repeat one or two of them
as anchors in a second call.
"""
import argparse, collections, concurrent.futures as cf, glob, json, os, random, string, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = open(os.path.join(HERE, 'prompts', 'unit_ledger.md'), encoding='utf-8').read().strip()
WORDS = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven',
         12: 'twelve', 13: 'thirteen', 14: 'fourteen'}


def prompt(n, target):
    labels = string.ascii_uppercase[:n]
    marks = ', '.join(f'"{L}": "{"KCDX"[i % 4]}"' for i, L in enumerate(labels))
    return TEMPLATE.format(n=WORDS.get(n, str(n)), target=target, last=labels[-1], marks=marks)


def gemini_single(system, user, model, effort):
    key = os.environ['GEMINI_API_KEY']
    body = {'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'role': 'user', 'parts': [{'text': user}]}],
            'generationConfig': {'temperature': 1, 'maxOutputTokens': 65536, 'responseMimeType': 'application/json',
                                 'thinkingConfig': {'thinkingLevel': effort}}}
    for attempt in range(4):
        req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                                     data=json.dumps(body).encode(), headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
        try:
            j = json.load(urllib.request.urlopen(req, timeout=900))
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(20 * (attempt + 1)); continue
            raise RuntimeError(f'HTTP {e.code}: {e.read()[:200]}')
        except Exception:
            time.sleep(20 * (attempt + 1)); continue
        c = (j.get('candidates') or [{}])[0]
        text = ''.join(p.get('text', '') for p in c.get('content', {}).get('parts', []) if not p.get('thought'))
        try:
            return json.loads(text), {'input_tokens': j.get('usageMetadata', {}).get('promptTokenCount', 0),
                                      'output_tokens': j.get('usageMetadata', {}).get('candidatesTokenCount', 0) + (j.get('usageMetadata', {}).get('thoughtsTokenCount') or 0),
                                      'finish': c.get('finishReason')}
        except ValueError:
            continue
    raise RuntimeError('no parsable reply')


def run(a):
    b = json.load(open(a.bench, encoding='utf-8'))
    systems = a.systems.split(',')
    missing = [s for s in systems if s not in b['translations']]
    if missing: sys.exit(f'not in the bench: {missing}')
    system_prompt = prompt(len(systems), b['target'])
    if a.backend == 'claude':
        sys.path.insert(0, HERE); import judge
        single = lambda s, u: judge.single(s, u, a.effort)
    else:
        single = lambda s, u: gemini_single(s, u, a.model, a.effort)
    os.makedirs(a.out, exist_ok=True)

    def task(w, r):
        out = os.path.join(a.out, f"{a.name}.{w['id']}.r{r}.json")
        if os.path.exists(out): return out, 'exists'
        order = systems[:]; random.Random(f"{a.name}/{w['id']}/{r}").shuffle(order)
        labels = {string.ascii_uppercase[i]: s for i, s in enumerate(order)}
        src = '\n\n'.join(b['paragraphs'][p] for p in w['paras'])
        user = f"Original ({b['source']}):\n\n{src}\n\n" + '\n\n'.join(
            f'Translation {L}:\n\n' + '\n\n'.join(b['translations'][s][p] for p in w['paras']) for L, s in labels.items())
        try:
            result, usage = single(system_prompt, user)
        except Exception as e:
            return out, f'error {str(e)[:120]}'
        json.dump({'window': w['id'], 'run': r, 'labels': labels, 'backend': a.backend, 'model': a.model if a.backend == 'gemini' else 'judge.py',
                   'effort': a.effort, 'usage': usage, 'result': result}, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return out, 'ok'

    with cf.ThreadPoolExecutor(a.concurrency) as p:
        for r in p.map(lambda j: task(*j), [(w, r) for w in b['windows'] for r in range(1, a.runs + 1)]): print(*r, flush=True)


def score(a):
    groups = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for f in sorted(glob.glob(os.path.join(a.out, '*.json'))):
        x = json.load(open(f, encoding='utf-8')); g = os.path.basename(f).split('.')[0]
        r = x['result'] if isinstance(x['result'], dict) else json.loads(x['result'])
        for u in r.get('units', []):
            for L, s in x['labels'].items(): groups[g][s][u.get(L, '?')] += 1
        for add in r.get('added', []):
            s = x['labels'].get(add.get('v'))
            if s: groups[g][s]['+'] += 1
    for g, per in groups.items():
        print(f'{g}: per 100 units of the original')
        print(f"  {'version':22} {'kept':>6} {'compressed':>10} {'changed':>8} {'dropped':>8} {'added':>6}")
        for s, c in sorted(per.items(), key=lambda kv: -kv[1]['K'] / max(1, sum(kv[1][k] for k in 'KCDX'))):
            t = max(1, sum(c[k] for k in 'KCDX'))
            print(f"  {s:22} {100 * c['K'] / t:6.1f} {100 * c['C'] / t:10.1f} {100 * c['X'] / t:8.1f} {100 * c['D'] / t:8.1f} {100 * c['+'] / t:6.1f}")
        print()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run'); r.add_argument('bench'); r.add_argument('out'); r.add_argument('--systems', required=True)
    r.add_argument('--name', default='ledger'); r.add_argument('--runs', type=int, default=2)
    r.add_argument('--backend', choices=['claude', 'gemini'], default='claude'); r.add_argument('--model', default='gemini-4-hydrogen')
    r.add_argument('--effort', default='high'); r.add_argument('--concurrency', type=int, default=4)
    s = sub.add_parser('score'); s.add_argument('out')
    a = ap.parse_args()
    run(a) if a.cmd == 'run' else score(a)
