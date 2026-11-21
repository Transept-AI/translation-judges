#!/usr/bin/env python3
"""Make a plain baseline translation of a bench's source text and add it to the bench file.

    python3 translate.py <bench.json> <name> --model claude-opus-5-5 [--effort low]

One call translates the whole text with a short, plain prompt and returns the paragraphs in order, so the result
lines up with the source paragraph by paragraph. Uses the same backends as judge.py (JUDGE_BACKEND=claude-code for
the `claude` CLI, otherwise the Messages API).
"""
import argparse, json

import judge

SYSTEM = """You are a literary translator, {SOURCE} into {TARGET}. You get {GENRE}, split into numbered paragraphs. Translate it for a reader of {TARGET} who will never see the original: keep what it says and how it says it, and let it read as if it were written in {TARGET}.

Keep the paragraphs: return exactly one translated paragraph for each numbered paragraph, in the same order. Reply with JSON only: {{"paragraphs": ["<paragraph 0>", "<paragraph 1>", ...]}}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bench'); ap.add_argument('name'); ap.add_argument('--model', default=judge.MODEL); ap.add_argument('--effort', default='low')
    a = ap.parse_args()
    b = json.load(open(a.bench, encoding='utf-8'))
    judge.MODEL = a.model
    system = SYSTEM.format(SOURCE=b['source'], TARGET=b['target'], GENRE=b.get('genre') or 'a novel')
    if b['target'] in judge.ORTHOGRAPHY:
        system += '\n\n' + judge.ORTHOGRAPHY[b['target']]
    user = '\n\n'.join(f'[{n}] {p}' for n, p in enumerate(b['paragraphs']))
    result, usage = judge.single(system, user, a.effort)
    paras = result['paragraphs']
    if len(paras) != len(b['paragraphs']):
        raise SystemExit(f"{a.name}: {len(paras)} paragraphs for {len(b['paragraphs'])}; not saved")
    b['translations'][a.name] = [str(p) for p in paras]
    b.setdefault('systems', {})[a.name] = f'{a.model}, effort {a.effort}, translate.py baseline prompt'
    json.dump(b, open(a.bench, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{a.name}: {len(paras)} paragraphs, {usage}')


if __name__ == '__main__':
    main()
