#!/usr/bin/env python3
"""Run one judge over a bench file and save one JSON per call.

    python3 judge.py <judge> <bench.json> <out_dir> [--runs N] [--concurrency 6] [--systems a,b]

Judges (prompt file, effort, what the judge sees):
  editor          prompts/editor.md              low     one window of the translation, never the original
  friction        prompts/friction_demanding.md  medium  same
  friction_avid   prompts/friction_avid.md       medium  same
  mirror          prompts/reader_mirror.md       low     same
  meaning         prompts/meaning.md             medium  the window's original and translation, paragraph-numbered
  builder         prompts/element_map_builder.md max     one paragraph of the original plus the whole original (no translation)
  checker         prompts/map_checker.md         medium  original + translation, then the map paragraph by paragraph
  native          prompts/map_native_reader.md   medium  translation only, then the map without the original's words

The bench file (see examples/):
  {"source": "Ukrainian", "target": "English", "genre": "a novel", "interference": null,
   "paragraphs": ["<source paragraph 0>", ...],
   "windows": [{"id": "w0", "paras": [0, 1, 2]}, ...],
   "translations": {"<system>": ["<translation of paragraph 0>", ...], ...}}

Every output records the model, the effort, the prompt file's SHA-256 and the token usage. The model is pinned:
a judge that silently changed model would change the benchmark, so a refusal is recorded as a failed call and
nothing falls back to another model. Needs `pip install anthropic` and an API key (ANTHROPIC_API_KEY or `ant auth login`).
"""
import argparse, concurrent.futures as cf, hashlib, json, os, re, subprocess, sys, threading

try:
    import anthropic
except ImportError:  # only the API backend needs it
    anthropic = None

MODEL = 'claude-opus-5-5'
HERE = os.path.dirname(os.path.abspath(__file__))
JUDGES = {
    'editor': ('editor.md', 'low', 2), 'friction': ('friction_demanding.md', 'medium', 1),
    'friction_avid': ('friction_avid.md', 'medium', 1), 'mirror': ('reader_mirror.md', 'low', 1),
    'meaning': ('meaning.md', 'medium', 2), 'builder': ('element_map_builder.md', 'max', 1),
    'checker': ('map_checker.md', 'medium', 1), 'native': ('map_native_reader.md', 'medium', 1),
}
NEUTRAL_FRAMING = [
    ("You are reading one passage of a novel translated from another language. You don't know who translated it or how, and you must not guess. You read English only and never see the original.",
     "You are reading one passage of a novel. You don't know who wrote it, or whether it was written in English or translated, and you must not guess. You read English only."),
    ("You get one passage of a novel translated into English. You don't know who translated it or how, and you don't see the original.",
     "You get one passage of a novel in English. You don't know who wrote it, or whether it was written in English or translated."),
]
USAGE = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens')
NO_GLOSSARY = ('\n\nThe translations will be made from the original alone, with no glossary and no style guide.',
               '\n\nThe translator had only the original: no glossary and no style guide. Any clear name used consistently on the page counts.')
client = None  # created on first call, so the module imports without a key
# Ukrainian targets follow the current orthography; the reading judges count a departure as a mechanics error.
ORTHOGRAPHY = {'Ukrainian': ('Ukrainian spelling follows the current orthography, Український правопис 2019: the English h in '
                             'loanwords is г (гейтер, not хейтер), є after a vowel in borrowed words (проєкт), and пів is written '
                             'apart from a noun in the genitive (пів години).')}


def prompt(judge, b):
    """The judge's system prompt for this bench. The reading judges were validated in English on novels; for another
    target, genre or a close source language the same substitutions are made as in the validated runs."""
    text = open(os.path.join(HERE, 'prompts', JUDGES[judge][0]), encoding='utf-8').read().rstrip('\n')
    t, g, i = b['target'], b.get('genre') or 'a novel', b.get('interference')
    if judge in ('editor', 'friction', 'friction_avid', 'mirror'):
        text = text.replace('English', t).replace('of a novel', f'of {g}')
        if i and judge == 'editor':
            text = text.replace('its category: "calque"', f'its category: "interference" if it removes {i} carried into {t} (a word, form, case or preposition government where {t} has its own); "calque"').replace('"category": "calque|', '"category": "interference|calque|')
        elif i:
            text = text.replace('- "mechanics":', f'- "interference": a {i} word, form, case or preposition government carried into {t} where {t} has its own;\n- "mechanics":').replace('|mechanics"', '|interference|mechanics"')
    if judge in ('editor', 'friction', 'friction_avid', 'mirror') and t in ORTHOGRAPHY:
        kind = 'a grammar error' if judge == 'editor' else 'mechanics'
        text = text.replace('\n\nReply with JSON only', f'\n\n{ORTHOGRAPHY[t]} Treat a departure from it as {kind}.\n\nReply with JSON only', 1)
    if judge in ('editor', 'friction', 'friction_avid', 'mirror') and os.environ.get('JUDGE_FRAMING') == 'neutral':
        # experiment (2026-11-11): don't tell the reading judges the text is a translation
        for old, new in NEUTRAL_FRAMING:
            text = text.replace(old.replace('English', t).replace('of a novel', f'of {g}'), new.replace('English', t).replace('of a novel', f'of {g}'))
    return (text.replace('{SOURCE}', b['source']).replace('{TARGET}', t).replace('{GENRE}', g)
            .replace('{NO_GLOSSARY_RULE}', NO_GLOSSARY[0]).replace('{NO_GLOSSARY_NOTE}', NO_GLOSSARY[1])
            .replace('{INTERFERENCE_NOTE}', f' (a {i} word, form, case or preposition government where {t} has its own counts here)' if i else ''))


def parse(text):
    return json.loads(text[text.index('{'):text.rindex('}') + 1])


def call(system, messages, effort):
    """One API request. Returns (reply text, usage dict) or raises."""
    global client
    client = client or anthropic.Anthropic()
    with client.messages.stream(model=MODEL, max_tokens=64000, system=system, messages=messages,
                                output_config={'effort': effort}) as s:
        m = s.get_final_message()
    if m.stop_reason == 'refusal':
        raise RuntimeError(f'refused: {m.stop_details}')
    usage = {k: getattr(m.usage, k, 0) or 0 for k in USAGE}
    return ''.join(b.text for b in m.content if b.type == 'text'), usage


def single(system, user, effort):
    """A one-call judge: up to two attempts until the reply parses."""
    for _ in range(2):
        s = Session(system, effort)
        try:
            return parse(s.send(user)), s.usage
        except (ValueError, RuntimeError) as e:
            err = e
        finally:
            s.close()
    raise RuntimeError(f'no parsable reply: {err}')


class Session:
    """A conversation with the judge. JUDGE_BACKEND=api (default) calls the Messages API; JUDGE_BACKEND=claude-code
    runs one headless Claude Code session (`claude` CLI, safe mode, no tools) over stream-json, as the validated runs
    did, so a Claude subscription can do the judging."""
    def __init__(self, system, effort):
        self.system, self.effort, self.messages, self.usage = system, effort, [], dict.fromkeys(USAGE, 0)
        self.proc = None
        if os.environ.get('JUDGE_BACKEND') == 'claude-code':
            self.proc = subprocess.Popen(
                ['claude', '-p', '--safe-mode', '--model', MODEL, '--effort', effort, '--system-prompt', system, '--tools', '',
                 '--strict-mcp-config', '--no-session-persistence', '--input-format', 'stream-json',
                 '--output-format', 'stream-json', '--verbose'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8')

    def send(self, text):
        if not self.proc:
            self.messages.append({'role': 'user', 'content': text})
            reply, u = call(self.system, self.messages, self.effort)
            self.messages.append({'role': 'assistant', 'content': reply})
            for k in u: self.usage[k] += u[k]
            return reply
        self.proc.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': text}}) + '\n')
        self.proc.stdin.flush()
        for line in self.proc.stdout:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get('type') == 'result':
                for k in self.usage: self.usage[k] += (e.get('usage') or {}).get(k, 0)
                if e.get('is_error'):
                    raise RuntimeError(str(e.get('result'))[:300])
                return str(e.get('result') or '')
        raise RuntimeError('claude exited before replying')

    def close(self):
        if self.proc:
            self.proc.stdin.close(); self.proc.wait()

    def ask(self, text):
        try:
            return parse(self.send(text))
        except ValueError:
            try:
                return parse(self.send('That reply did not parse as JSON. Send the same answer again as one JSON object and nothing else.'))
            except ValueError:
                return None


numbered = lambda paras, idx=None: '\n\n'.join(f'[{n}] {p}' for n, p in zip(idx or range(len(paras)), paras))
CYRILLIC = re.compile(r'[Ѐ-ӿ]')


def element_text(el, with_source, cyrillic_source):
    def strip(s):  # the target-only reader never sees the original's words (by script, so only for Cyrillic sources)
        s = str(s or '')
        if with_source or not cyrillic_source: return s
        s = re.sub(r'\s*\([^()]*[Ѐ-ӿ][^()]*\)', '', s)
        s = re.sub(r'["“«\'‘][^"”»\'’]*[Ѐ-ӿ][^"”»\'’]*["”»\'’]', '[…]', s)
        return re.sub(r"[Ѐ-ӿ][Ѐ-ӿ'’\s,.\-–—…]*[Ѐ-ӿ]|[Ѐ-ӿ]", '[…]', s)
    head = f"{el['id']} ({el['type']}{', recurs in blocks ' + ', '.join(map(str, el['recurs_in'])) if el.get('recurs_in') else ''})"
    src = f"\n  Original words: {el['source']}" if with_source and el.get('source') else ''
    checks = '\n'.join(f"  - {c['id']}: {strip(c['ask'])}" + (f" (No if: {strip(c['fail'])})" if c.get('fail') else '') for c in el['checks'])
    return f"{head}{src}\n  Where: {strip(el['where'])}\n  What: {strip(el['what'])}\n  Checks:\n{checks}"


def jobs(judge, b, runs, systems):
    """(output name, function returning the result) for every call this judge makes."""
    system, effort = prompt(judge, b), JUDGES[judge][1]
    P, T = b['paragraphs'], {k: v for k, v in b['translations'].items() if not systems or k in systems}
    if judge == 'builder':
        for n in range(len(P)):
            user = f'# Block {n}\n\n## Target paragraph (block {n})\n\n[{n}] {P[n]}\n\n## The whole text (blocks 0–{len(P) - 1})\n\n{numbered(P)}'
            yield f'maps/p{n:02d}', lambda user=user: single(system, user, effort)
        return
    if judge in ('checker', 'native'):
        maps = [json.load(open(os.path.join(b['_dir'], 'maps', f'p{n:02d}.json'), encoding='utf-8'))['result'] for n in range(len(P))]
        cyr = bool(CYRILLIC.search(''.join(P)))
        for name, tr in T.items():
            def run(tr=tr):
                s = Session(system, effort)
                if judge == 'checker':
                    s.send(f"The original ({b['source']}):\n\n{numbered(P)}\n\nThe translation ({b['target']}):\n\n{numbered(tr)}\n\nRead both in full now and reply OK.")
                else:
                    s.send(f'Here is the whole page. Read it in full now and reply OK.\n\n{numbered(tr)}')
                out = []
                for n, m in enumerate(maps):
                    els = [e for e in m['elements'] if judge == 'native' or e['type'] != 'construction']
                    if not els:
                        out.append({'n': n}); continue
                    body = '\n\n'.join(element_text(e, judge == 'checker', cyr) for e in els)
                    ask = f'Paragraph [{n}]. Elements:\n\n{body}' if judge == 'checker' else f'Paragraph [{n}].\n\n[{n}] {tr[n]}\n\nNotes:\n\n{body}'
                    out.append({**(s.ask(ask) or {'error': 'unparsed'}), 'n': n})
                s.close()
                return {'paragraphs': out}, s.usage
            yield f'{judge}/{name}', run
        return
    for w in b['windows']:
        for name, tr in T.items():
            for r in range(1, runs + 1):
                if judge == 'meaning':
                    user = f"Original ({b['source']}):\n\n{numbered([P[p] for p in w['paras']], w['paras'])}\n\nTranslation ({b['target']}):\n\n{numbered([tr[p] for p in w['paras']], w['paras'])}"
                else:
                    user = 'The passage:\n\n' + '\n\n'.join(tr[p] for p in w['paras'])
                yield f"{judge}/{w['id']}.{name}.r{r}", lambda user=user: single(system, user, effort)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('judge', choices=JUDGES); ap.add_argument('bench'); ap.add_argument('out')
    ap.add_argument('--runs', type=int); ap.add_argument('--concurrency', type=int, default=6); ap.add_argument('--systems')
    a = ap.parse_args()
    b = json.load(open(a.bench, encoding='utf-8')); b['_dir'] = a.out
    sha = hashlib.sha256(open(os.path.join(HERE, 'prompts', JUDGES[a.judge][0]), 'rb').read()).hexdigest()[:12]
    todo = [(n, f) for n, f in jobs(a.judge, b, a.runs or JUDGES[a.judge][2], set(a.systems.split(',')) if a.systems else None)
            if not os.path.exists(os.path.join(a.out, n + '.json'))]
    lock, done = threading.Lock(), [0]

    def work(item):
        name, f = item
        try:
            result, usage = f()
        except Exception as e:  # a failed call is reported and skipped; rerun to retry it
            print(f'{name}: failed ({e})', file=sys.stderr); return
        path = os.path.join(a.out, name + '.json'); os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump({'judge': a.judge, 'model': MODEL, 'effort': JUDGES[a.judge][1], 'prompt_sha256': sha,
                   'usage': usage, 'result': result}, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        with lock:
            done[0] += 1; print(f'{done[0]}/{len(todo)} {name}', file=sys.stderr)

    with cf.ThreadPoolExecutor(a.concurrency) as ex:
        list(ex.map(work, todo))


if __name__ == '__main__':
    main()
