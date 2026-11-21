#!/usr/bin/env python3
"""Integrity checks for a translation: code only, no model.

Incidents (a system with any of these fails the gate):
  empty        a source paragraph with words has no translation (dropped, or merged into a neighbour)
  script       the target is in the wrong script (Cyrillic left in English, a mostly Latin paragraph in Ukrainian)
  leak         letters the target alphabet does not use (ы, э, ъ, ё in a Ukrainian target)
Warnings (reported, not gating):
  length       a paragraph's length ratio is under 0.5x or over 2x the translation's own median ratio
  italics      the source paragraph has emphasis (*...*) and the translation has none

Usage:
  integrity.py SOURCE.json TRANSLATION.json --target en|uk
      SOURCE.json: [{"text": ...}, ...] (paragraphs in order); TRANSLATION.json: {"0": text, "1": text, ...}
  integrity.py --bench DIR [--target en|uk]
      DIR holds source.json and entries/<name>.json; prints one line per entry.
"""
import json, os, re, statistics, sys

CYR = re.compile(r'[Ѐ-ӿ]')
LAT = re.compile(r'[A-Za-z]')
LEAK_LETTERS = re.compile(r'[ыэъёЫЭЪЁ]')
words = lambda t: re.findall(r"[\w'’]+", t)


def check(src, tr, target):
    """src: list of source paragraphs; tr: {index: translation}. Returns (incidents, warnings), lists of (n, kind, detail)."""
    inc, warn, ratios = [], [], {}
    for i, s in enumerate(src):
        if not words(s):
            continue
        t = (tr.get(str(i)) or '').strip()
        if not words(t):
            inc.append((i, 'empty', ''))
            continue
        cyr, lat = len(CYR.findall(t)), len(LAT.findall(t))
        if target == 'en' and cyr > 2:
            inc.append((i, 'script', f'{cyr} Cyrillic letters'))
        if target == 'uk' and lat > 0.5 * (cyr + lat):  # mostly Latin: left untranslated (a quoted foreign phrase is fine)
            inc.append((i, 'script', f'{lat} Latin letters of {cyr + lat}'))
        if target == 'uk' and LEAK_LETTERS.search(t):
            inc.append((i, 'leak', ''.join(sorted(set(LEAK_LETTERS.findall(t))))))
        if s.count('*') >= 2 and t.count('*') < 2:
            warn.append((i, 'italics', ''))
        if len(words(s)) >= 15:
            ratios[i] = len(words(t)) / len(words(s))
    if len(ratios) >= 3:
        med = statistics.median(ratios.values())
        for i, r in ratios.items():
            if r < 0.5 * med or r > 2 * med:
                warn.append((i, 'length', f'{r / med:.2f}x the median'))
    return inc, warn


def load_source(path):
    return [(p.get('text') if isinstance(p, dict) else p) or '' for p in json.load(open(path))]


def main(argv):
    target = argv[argv.index('--target') + 1] if '--target' in argv else None
    if '--bench' in argv:
        d = argv[argv.index('--bench') + 1]
        bench = json.load(open(os.path.join(d, 'bench.json'))) if os.path.exists(os.path.join(d, 'bench.json')) else {}
        target = target or {'English': 'en', 'Ukrainian': 'uk'}[bench['target']]
        src = load_source(os.path.join(d, 'source.json'))
        for f in sorted(os.listdir(os.path.join(d, 'entries'))):
            if not f.endswith('.json') or f.endswith('.meta.json'):
                continue
            inc, warn = check(src, json.load(open(os.path.join(d, 'entries', f))), target)
            kinds = lambda xs: ', '.join(f'{k} {sum(1 for x in xs if x[1] == k)}' for k in sorted({x[1] for x in xs})) or '-'
            print(f'{f[:-5]:42s} incidents: {kinds(inc):30s} warnings: {kinds(warn)}')
        return
    src, tr = load_source(argv[1]), json.load(open(argv[2]))
    inc, warn = check(src, tr, target)
    print(json.dumps({'incidents': inc, 'warnings': warn}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv)
