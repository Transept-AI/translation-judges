#!/usr/bin/env python3
"""Score systems from judge outputs: the gate (integrity, hard errors), then the reading score.

    python3 score.py <bench.json> <out_dir> [--vs systemA,systemB]

Reading score, per window: -(z(E) + z(F1) + z(F2) + z(M)) / 4, z = (x - mean) / sd with calibration.json
  E  = editor error fixes per 100 words, mean of the editor runs, without punctuation and grammar fixes
  F1 = demanding reader: weight of the issues whose quote is in the text, per 100 words, without mechanics
  F2 = avid reader: same
  M  = reader mirror: minus the mean of its four 1-5 ratings
Copy-editing, reported apart: the editor's punctuation and grammar fixes per 100 words. A copy-editor fixes these
cheaply, and folding them into reading made an unedited original score below its own polished translations.
0 is the average passage of the LAIT study (published human and machine translations pooled); higher reads better.
A system's score is its mean over windows, with a 95% interval from resampling windows (2,000 draws).
Hard errors: an error counts when the second meaning run flags the same paragraph with a quote sharing at least
half the words of the shorter quote; reported per 1,000 source words. Integrity: integrity.py.
A system passes the gate with no integrity incident and fewer than 3 agreed hard errors per 1,000 source words.
"""
import argparse, collections, glob, json, os, random, re, statistics as st

import integrity

HERE = os.path.dirname(os.path.abspath(__file__))
CAL = json.load(open(os.path.join(HERE, 'calibration.json')))['judges']
COPYEDIT = {'punctuation', 'grammar'}
READING_KINDS = {'unclear', 'follow', 'structure', 'unnatural', 'literal', 'register', 'wordy', 'flat', 'interference'}
words = lambda t: len(re.findall(r"[\w']+", str(t).replace('’', "'")))
norm = lambda s: re.sub(r'\s+', ' ', str(s).lower().translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '«': '"', '»': '"', '—': '-', '–': '-'}))).strip()
found = lambda q, t: bool(norm(q).strip('"')) and norm(q).strip('"') in norm(t)
toks = lambda s: set(re.findall(r"[\w']+", str(s).lower()))


def load(out, judge):
    """{(window, system): [result, ...]} from out/<judge>/<window>.<system>.r<k>.json"""
    r = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(out, judge, '*.json'))):
        w, system, _ = os.path.basename(f)[:-5].rsplit('.', 2)
        r[(w, system)].append(json.load(open(f, encoding='utf-8'))['result'])
    return r


def reading(b, out):
    text = {(w['id'], s): '\n\n'.join(t[p] for p in w['paras']) for w in b['windows'] for s, t in b['translations'].items()}
    E, F1, F2, M = load(out, 'editor'), load(out, 'friction'), load(out, 'friction_avid'), load(out, 'mirror')
    fr = lambda res, t: 100 * sum(float(i.get('weight') or 1) for i in res.get('issues', []) if found(i.get('quote', ''), t) and i.get('kind') in READING_KINDS) / words(t)
    score, copyedit = {}, {}
    for k, t in text.items():
        if not (E.get(k) and F1.get(k) and F2.get(k) and M.get(k)):
            continue
        e = st.mean(100 * sum(1 for c in r.get('changes', []) if c.get('kind') == 'error' and c.get('category') not in COPYEDIT) / words(t) for r in E[k])
        copyedit[k] = st.mean(100 * sum(1 for c in r.get('changes', []) if c.get('kind') == 'error' and c.get('category') in COPYEDIT) / words(t) for r in E[k])
        rt = M[k][0].get('ratings', {})
        m = -st.mean(float(rt[q]) for q in ('acceptability', 'smoothness', 'immersion', 'continue'))
        z = lambda name, v: (v - CAL[name]['mean']) / CAL[name]['sd']
        score[k] = -(z('editor_style_errors_per100_mean2', e) + z('friction_reading_weighted_per100', fr(F1[k][0], t))
                     + z('friction2_reading_weighted_per100', fr(F2[k][0], t)) + z('mirror_neg_rating', m)) / 4
    return score, copyedit


def boot(windows, f, n=2000, seed=5):
    rnd = random.Random(seed)
    draws = sorted(st.mean(f(rnd.choice(windows)) for _ in windows) for _ in range(n))
    return draws[int(0.025 * n)], draws[int(0.975 * n) - 1]


def hard(b, out):
    """Agreed hard errors per 1,000 source words, per system."""
    runs = load(out, 'meaning'); n, wd = collections.Counter(), collections.Counter()
    for w in b['windows']:
        sw = sum(words(b['paragraphs'][p]) for p in w['paras'])
        for s in b['translations']:
            r = runs.get((w['id'], s), [])
            if len(r) < 2:
                continue
            e1, e2 = r[0].get('errors', []), r[1].get('errors', [])
            same = lambda a, x: a.get('n') == x.get('n') and toks(a.get('quote')) & toks(x.get('quote')) and \
                len(toks(a.get('quote')) & toks(x.get('quote'))) / max(1, min(len(toks(a.get('quote'))), len(toks(x.get('quote'))))) >= 0.5
            n[s] += sum(1 for a in e1 if any(same(a, x) for x in e2)); wd[s] += sw
    return {s: 1000 * n[s] / wd[s] for s in wd}


def rubrics(b, out):
    """The two rubric judges, per system: the checker's share of checks answered yes and its 'no' answers per 1,000
    source words; the native reader's share rated native, and foreign / weak+missing notes per 1,000 target words."""
    res, sw = {}, sum(words(p) for p in b['paragraphs'])
    for s, tr in b['translations'].items():
        r, tw = {}, sum(words(p) for p in tr)
        f = os.path.join(out, 'checker', s + '.json')
        if os.path.exists(f):
            a = collections.Counter(c.get('answer') for p in json.load(open(f, encoding='utf-8'))['result']['paragraphs'] for c in p.get('checks', []))
            if sum(a.values()):
                r.update(yes=f"{100 * a['yes'] / sum(a.values()):.0f}%", no=f"{1000 * a['no'] / sw:.1f}")
        f = os.path.join(out, 'native', s + '.json')
        if os.path.exists(f):
            n = collections.Counter(x.get('rating') for p in json.load(open(f, encoding='utf-8'))['result']['paragraphs'] for x in p.get('notes', []))
            if sum(n.values()):
                r.update(native=f"{100 * n['native'] / sum(n.values()):.0f}%", foreign=f"{1000 * n['foreign'] / tw:.1f}",
                         lost=f"{1000 * (n['weak'] + n['missing']) / tw:.1f}")
        if r:
            res[s] = r
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bench'); ap.add_argument('out'); ap.add_argument('--vs')
    a = ap.parse_args()
    b = json.load(open(a.bench, encoding='utf-8'))
    tgt = {'English': 'en', 'Ukrainian': 'uk'}.get(b['target'])
    (score, copyedit), hd = reading(b, a.out), hard(b, a.out)
    ws = [w['id'] for w in b['windows']]
    rows = []
    for s, tr in b['translations'].items():
        inc = integrity.check(b['paragraphs'], {str(i): t for i, t in enumerate(tr)}, tgt)[0] if tgt else []
        have = [w for w in ws if (w, s) in score]
        r = st.mean(score[(w, s)] for w in have) if have else None
        ci = boot(have, lambda w: score[(w, s)]) if len(have) > 1 else (None, None)
        gate = 'pass' if not inc and hd.get(s, 0) < 3 else 'FAIL'
        ce = st.mean(copyedit[(w, s)] for w in have) if have else None
        rows.append((s, r, ci, hd.get(s), len(inc), gate, ce))
    print(f"{'system':28s} {'reading [95%]':>24s} {'copy-edit/100':>13s} {'hard/1k':>8s} {'integrity':>9s}  gate")
    for s, r, (lo, hi), h, i, g, ce in sorted(rows, key=lambda x: (x[5] != 'pass', -(x[1] if x[1] is not None else -9))):
        rs = f'{r:+.2f} [{lo:+.2f}, {hi:+.2f}]' if lo is not None else (f'{r:+.2f}' if r is not None else '-')
        print(f"{s:28s} {rs:>24s} {(f'{ce:.2f}' if ce is not None else '-'):>13s} {(f'{h:.2f}' if h is not None else '-'):>8s} {i:>9d}  {g}")
    rub = rubrics(b, a.out)
    if rub:
        print(f"\n{'rubric (diagnostic)':28s} {'checks yes':>10s} {'no/1k src':>10s} {'native':>7s} {'foreign/1k':>11s} {'weak+missing/1k':>16s}")
        for s, r in rub.items():
            print(f"{s:28s} {r.get('yes', '-'):>10} {r.get('no', '-'):>10} {r.get('native', '-'):>7} {r.get('foreign', '-'):>11} {r.get('lost', '-'):>16}")
    if a.vs:
        x, y = a.vs.split(',')
        both = [w for w in ws if (w, x) in score and (w, y) in score]
        d = lambda w: score[(w, x)] - score[(w, y)]
        lo, hi = boot(both, d)
        print(f'\n{x} - {y}: {st.mean(d(w) for w in both):+.2f} [{lo:+.2f}, {hi:+.2f}] over {len(both)} windows, ahead in {sum(d(w) > 0 for w in both)}')


if __name__ == '__main__':
    main()
