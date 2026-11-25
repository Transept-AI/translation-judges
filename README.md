# Transept translation judges

AI judges that score translations of fiction the way readers read them, without a reference translation. This is
the benchmark [Transept](https://transept.ai) uses to decide whether a model, a prompt or a preset change makes its
translations better or worse. The method and what it found are written up in
[How human and AI translation differ, and what readers like](https://transept.ai/journal/how-human-and-ai-translation-differ);
more articles are in the [Transept Journal](https://transept.ai/journal).

A translation is scored on three separate questions:

| Axis | The question | How |
| --- | --- | --- |
| Reading quality | Does it read like a book written in the target language? | Five calls to four target-only judges ([`prompts/`](prompts)), combined by [`score.py`](score.py) |
| Copy-editing | How much would a copy-editor fix? | The editor's punctuation and grammar fixes per 100 words, reported apart from reading |
| Hard errors | Does it say something the original does not? | A bilingual judge run twice; an error counts when both runs find it |
| Integrity | Is anything left untranslated, in the wrong language or broken? | [`integrity.py`](integrity.py), code only |
| Information (diagnostic) | What does it keep, compress, change, drop or add of the original's information? | One call per window over all versions at once ([`ledger.py`](ledger.py), [`prompts/unit_ledger.md`](prompts/unit_ledger.md)); not part of the gate |

A system passes the gate with no integrity incident and fewer than 3 agreed hard errors per 1,000 source words;
systems that pass are ranked by reading quality. Every number has a 95% interval from resampling passages.

For diagnosis there is a second layer: a **rubric** (an "element map") built from the original alone, listing the
places in each paragraph where a translation can go wrong, and two judges that grade translations against it.

## How well does it agree with readers?

The reading score was calibrated and checked on the reader study of Ferstler et al. (2026) [1]: 386 passages from
15 novels translated from French, Polish and Japanese into English, each read by two avid readers who chose between
the published human translation and a machine translation.

- It agrees with a single reader at a rank correlation of **+0.22**; two readers of the same book agree at **+0.18**.
- Where both readers clearly preferred one version, it picks the same version in **68%** of passages, including 14
  of the 24 where readers preferred the machine.
- Design choices were made on 9 books; on the 6 held-out books it holds at +0.19 (readers there: +0.07).
- Copy-editing (punctuation, grammar, mechanics) is kept out of the reading score and reported apart. With it
  folded in, agreement was +0.24, within noise of +0.22, but an unedited original scored far below its own polished
  translations: a copy-editor's work, not the writing, decided the score.
- MetricX-QE, GEMBA-MQM and LiTransProQA sit at about 0 on the same passages.

The hard-error judge allows the liberties literary translators take on purpose (an added heading, an explained
cultural item, a rounded hedge) and still counts any misreading. On the study's published translations it keeps
23 of 31 real slips and flags 10 of 33 deliberate liberties; on our own answer key it catches 51 of 61 real errors.

Not validated: faithfulness against readers (the study's readers never saw the original), and any target language
other than English. The judges are Claude Opus; a check with GPT-6 judges agrees on the direction.

## Run it

```bash
pip install anthropic          # for the API backend
export ANTHROPIC_API_KEY=...   # or `ant auth login`

# reading judges and the hard-error judge, one window and one system at a time
for j in editor friction friction_avid mirror meaning; do
  python3 judge.py $j examples/intermezzo/bench.json runs/intermezzo
done
python3 score.py examples/intermezzo/bench.json runs/intermezzo --vs opus,haiku

# rubrics (slow: maximum effort, one call per paragraph), then the two rubric judges
python3 judge.py builder examples/intermezzo/bench.json runs/intermezzo
python3 judge.py checker examples/intermezzo/bench.json runs/intermezzo
python3 judge.py native  examples/intermezzo/bench.json runs/intermezzo
```

`JUDGE_BACKEND=claude-code` runs every judge through the `claude` command line (headless, no tools) instead of the
API, the way the validation runs were made. To judge your own text, write a bench file:

```json
{"source": "Ukrainian", "target": "English", "genre": "a novel", "interference": null,
 "paragraphs": ["<source paragraph 0>", "..."],
 "windows": [{"id": "w0", "paras": [0, 1, 2]}],
 "translations": {"my-system": ["<translation of paragraph 0>", "..."]}}
```

Cut windows of about 300 source words on paragraph boundaries; each window is judged on its own. `translate.py`
adds a plain baseline translation by any Claude model. For a target that a closely related language tends to leak into, set `"interference"` to that
language's name to add an interference category to the editor and the readers.

Each judge's prompt, effort and inputs are listed at the top of [`judge.py`](judge.py). The model is pinned
(`claude-opus-5-5`) and recorded with the effort and the prompt's hash in every output; there is no fallback to
another model, because a judge that changes model is a different benchmark.

## Examples

[`examples/`](examples) holds four texts with their translations, rubrics, judge outputs and scores:

| Text | Pair | Words |
| --- | --- | --- |
| Глава 2, chapter 2 of an unpublished novel by Vitalii Vlasiuk | Ukrainian → English | 806 |
| The prologue of the same novel, Ukrainian version picked and edited by the author (see `examples/prologue/SOURCE.md`) | Ukrainian → English | 877 |
| Mykhailo Kotsiubynsky, "Intermezzo" (1908) | Ukrainian → English | 1,456 |
| Katherine Mansfield, "Miss Brill" (1920) | English → Ukrainian | 1,929 |

Each folder has `bench.json` (source, translations, windows), the judge outputs, the rubric (`maps/`) and
`scores.txt`. The translations are plain baselines made with `translate.py` at low effort, plus, for Глава 2, the
author's existing English ("house"); the prologue has eleven more versions, described below. All judging ran through
`JUDGE_BACKEND=claude-code`. The prologue and Глава 2 also carry unit-ledger calls (`ledger/`).

| Text | System | Reading [95%] | Copy-edit / 100 | Hard errors / 1k | Gate | Rubric checks "no" / 1k | Native |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Глава 2 | house | −0.61 [−0.92, −0.29] | 0.38 | 0.00 | pass | 9.0 | 84% |
| | Opus 5.5 | −1.00 [−1.24, −0.70] | 0.16 | 0.00 | pass | 5.1 | 86% |
| | Sonnet 5.5 | −1.44 [−1.54, −1.25] | 0.11 | 3.85 | fail | 6.4 | 80% |
| | Haiku 5.5 | −2.46 [−3.07, −1.69] | 0.21 | 5.13 | fail | 16.7 | 69% |
| Prologue | Opus 5.5 | +0.01 [−0.93, +0.63] | 0.22 | 1.14 | pass | 5.7 | 87% |
| | Sonnet 5.5 | −0.60 [−0.95, −0.39] | 0.13 | 2.28 | pass | 14.8 | 80% |
| | Haiku 5.5 | −1.68 [−1.94, −1.53] | 0.36 | 6.85 | fail | 17.1 | 76% |
| Intermezzo | Opus 5.5 | +0.30 [−0.14, +0.78] | 0.17 | 0.00 | pass | 6.9 | 85% |
| | Sonnet 5.5 | +0.20 [−0.44, +0.84] | 0.25 | 0.00 | pass | 9.0 | 81% |
| | Haiku 5.5 | +0.01 [−0.51, +0.42] | 0.57 | 2.07 | pass | 11.0 | 75% |
| Miss Brill | Opus 5.5 | +1.40 [+1.03, +1.75] | 0.34 | 0.51 | pass | 4.0 | 90% |
| | Sonnet 5.5 | +0.17 [−0.38, +0.79] | 0.20 | 1.52 | pass | 9.4 | 80% |
| | Haiku 5.5 | −0.55 [−1.53, +0.28] | 0.94 | 1.52 | pass | 12.9 | 76% |

Reading scores from different texts are on one scale but measure different texts; compare systems within a text.
With three to six windows per text the intervals are wide: these are examples of the method, not a ranking of models.

What the gate caught on Глава 2: Sonnet read the novel's coined term "Плани" (the Plans) as "Planes", and turned a
dative ("sent to Agnes") into "Agnes had assigned"; Haiku read "доля" (fate) as "share" and invented a line of
dialogue. Each counted only because both runs of the hard-error judge found it.

### The prologue through the Transept pipeline and Gemini 4

`examples/prologue` holds eleven more versions of the prologue, made on 24 November 2026: Transept Standard and Pro
(the product's presets: Claude Opus 5.5 at low and high effort, through its translation pipeline), and Google's Gemini 4
Neon, Argon and Carbon, each called plainly at low and at high thinking with the same prompt as the baselines above, and
at low thinking through the Transept pipeline. Same judges, same three windows.

| System | Reading [95%] | Copy-edit / 100 | Hard errors / 1k | Gate | Rubric checks "no" / 1k | Native |
| --- | --- | --- | --- | --- | --- | --- |
| Transept Standard | +0.22 [−0.38, +0.64] | 0.22 | 0.00 | pass | 10.3 | 88% |
| Carbon high, plain | +0.19 [−0.01, +0.32] | 0.00 | 0.00 | pass | 8.0 | 88% |
| Argon low, Transept | +0.16 [−0.26, +0.76] | 0.08 | 0.00 | pass | 13.7 | 84% |
| Neon low, Transept | +0.12 [−0.32, +0.63] | 0.11 | 1.14 | pass | 14.8 | 88% |
| Transept Pro | +0.11 [−0.37, +0.56] | 0.17 | 0.00 | pass | 8.0 | 91% |
| Carbon low, Transept | +0.05 [−0.39, +0.49] | 0.04 | 0.00 | pass | 13.7 | 89% |
| Neon high, plain | −0.06 [−0.26, +0.29] | 0.13 | 0.00 | pass | 10.3 | 84% |
| Carbon low, plain | −0.42 [−0.96, +0.29] | 0.00 | 0.00 | pass | 10.3 | 83% |
| Argon high, plain | −0.44 [−0.68, −0.13] | 0.10 | 0.00 | pass | 9.1 | 82% |
| Neon low, plain | −0.56 [−0.79, −0.20] | 0.08 | 0.00 | pass | 9.1 | 90% |
| Argon low, plain | −1.13 [−1.44, −0.76] | 0.07 | 0.00 | pass | 9.1 | 83% |

The intervals overlap; the paired differences, window by window, are firmer. Against the same model called plainly at
low thinking, the pipeline adds +0.68 [+0.47, +0.83] to Neon, +1.30 [+1.18, +1.52] to Argon and +0.46 [+0.19, +1.01]
to Carbon, ahead in all three windows each time. Thinking harder helps every plain Gemini model here (Neon +0.50,
Argon +0.69, Carbon +0.61), but costs far more: Carbon at high thinking spent about 31,000 thinking tokens on this
877-word text, against none at low.

## Unit ledger: what a translation does with the original's information

The reading score never sees the original, so it cannot tell whether a version kept the original's information. The
ledger can. One call per window shows a judge the original and every version, blind and shuffled. The judge splits
the original into typed information units (event, fact, detail, speaker, feeling, image, logic, emphasis, reference),
marks each unit per version as kept, compressed, dropped or changed, and lists what each version adds.

```bash
python3 ledger.py run examples/prologue/bench.json runs/ledger --systems opus,transept-standard,neon-low \
    --backend gemini          # needs GEMINI_API_KEY; --backend claude uses judge.py's model
python3 ledger.py score runs/ledger
```

It is a diagnostic, not a quality score. On the LAIT passages, nothing about units predicted which version readers
preferred within a book, while published translators kept far fewer units than any machine. Checked against 78 of the
author's own verdicts, Gemini 4 Hydrogen at high thinking agreed 79% of the time and Claude Opus 5.5 at low 69%. Every
judge was right on "kept"; all of them over-mark "changed" and "compressed" where a translator used an idiomatic
equivalent, so read those two as upper bounds. The calls in `examples/*/ledger/` were made by Hydrogen at high thinking.

Per 100 units of the original:

| Text | Version | Kept | Compressed | Changed | Dropped | Added |
| --- | --- | --- | --- | --- | --- | --- |
| Глава 2 | house (the author's English) | 80.9 | 6.6 | 11.8 | 0.7 | 2.9 |
| | Opus 5.5 | 96.3 | 2.2 | 1.5 | 0.0 | 2.9 |
| | Sonnet 5.5 | 96.3 | 2.9 | 0.7 | 0.0 | 0.0 |
| | Haiku 5.5 | 85.3 | 4.4 | 10.3 | 0.0 | 2.2 |
| Prologue (six versions per call) | Opus 5.5, plain | 99.1 | 0.3 | 0.6 | 0.0 | 1.2 |
| | Neon high, plain | 97.3 | 1.2 | 0.9 | 0.6 | 2.7 |
| | Transept Pro | 94.6 | 3.3 | 2.1 | 0.0 | 2.1 |
| | Neon low, plain | 94.3 | 2.1 | 2.7 | 0.9 | 2.4 |
| | Transept Standard | 93.2 | 2.7 | 3.6 | 0.6 | 0.6 |
| | Neon low, Transept | 90.5 | 3.3 | 4.8 | 1.5 | 3.9 |
| Prologue (eight versions per call) | Argon high, plain | 97.2 | 2.2 | 0.6 | 0.0 | 1.3 |
| | Argon low, plain | 97.2 | 1.9 | 0.9 | 0.0 | 2.2 |
| | Carbon high, plain | 96.9 | 2.5 | 0.6 | 0.0 | 0.3 |
| | Carbon low, plain | 95.9 | 2.2 | 1.9 | 0.0 | 3.1 |
| | Transept Standard | 94.0 | 2.2 | 3.4 | 0.3 | 0.9 |
| | Carbon low, Transept | 91.8 | 4.1 | 3.8 | 0.3 | 11.0 |
| | Argon low, Transept | 90.3 | 4.4 | 5.3 | 0.0 | 6.6 |
| | Neon low, Transept | 90.0 | 5.6 | 4.1 | 0.3 | 5.6 |

The second prologue call repeats two versions from the first as anchors: Standard moves from 93.2 to 94.0 kept and Neon
through Transept from 90.5 to 90.0, so a call's size shifts the marks by about one unit. Compare versions within a call.

"Changed" counts choices as well as mistakes. On Глава 2, 11 of the 12 "changed" marks on the author's English in the
last window fall on names he set in his own glossary (CISAME, the Ground, the Gathers and others); the twelfth is the
judge itself reading "Плани" (the Plans) as "Planes".

## Licences

- Code: [MIT](LICENSE).
- Prompts and documentation: [CC BY 4.0](prompts/LICENSE.md).
- `reader_mirror.md` and `calibration.json` build on the LAIT study; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- The examples from Vitalii Vlasiuk's novel, and every translation of them, are all rights reserved; see
  [examples/LICENSE.md](examples/LICENSE.md). "Intermezzo" and "Miss Brill" are in the public domain.

No passage, translation or reader judgement from the LAIT study is included. The study's data is available from its
authors.

## Citation

```bibtex
@misc{transept-translation-judges-2026,
  title  = {Transept translation judges: reader-aligned evaluation of literary translation},
  author = {Vlasiuk, Vitalii},
  year   = {2026},
  url    = {https://github.com/Transept-AI/translation-judges}
}
```

[1] Ferstler, Y. et al. (2026). *AI translation of literary texts is "fine", but readers still prefer human
translations*. arXiv:2606.26040. https://github.com/Yves575/lait
