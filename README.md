# Transept translation judges

Source-blind AI judges that score fiction translations by where a reader stumbles, plus judges that check meaning and
track what happens to the original's information. This is the benchmark [Transept](https://transept.ai) uses to
decide whether a model, a prompt or a preset change makes its translations better or worse. The method and what it
found are written up in [How human and AI translation differ, and what makes readers like
both?](https://transept.ai/journal/how-human-and-ai-translation-differ); more articles are in the
[Transept Journal](https://transept.ai/journal).

## What do the judges measure?

*How to read:* one judge per row: what it sees, what it checks, and the number it gives.

| Judge | Sees | Checks | Counts |
| --- | --- | --- | --- |
| Reading score: four reading judges, five calls ([`prompts/`](prompts), [`score.py`](score.py)) | The translation only, one passage at a time | Stumbles: calques, literal phrasing, foreign syntax, unnatural wording, grammar, and the other places a reader's flow breaks | Each number standardized against the 772 LAIT versions and averaged with equal weights; 0 is the average LAIT version, higher reads better |
| Copy-editing | The translation only (the editor's fixes) | Punctuation, grammar and mechanics, counted apart from the reading score | Fixes per 100 words |
| Meaning judge ([`prompts/meaning.md`](prompts/meaning.md)) | The original and the translation | Seven kinds of misreading: reversed meaning, wrong referent, omitted fact, added fact, wrong fact, idiom, word sense. Deliberate liberties (an explained cultural item, an image swapped for one doing the same job) are allowed | Misreadings that both of two independent runs find, per 1,000 source words |
| Integrity ([`integrity.py`](integrity.py)) | The translation, by code | Paragraphs left untranslated, in the wrong language or broken | Incidents |
| Rubric (element maps) | Built from the original alone, before any translation exists | Elements a hurried translator loses: hinge words, logic links, motifs, allusions, double meanings, devices, register, constructions; yes-or-no checks for each | Elements lost per 1,000 words (a bilingual checker); a native reader who sees only the translation says whether each element reads native, foreign, weak or missing |
| Unit tracker ([`tracker.py`](tracker.py), [`prompts/unit_tracker.md`](prompts/unit_tracker.md)) | The original and every version of the passage, blind and shuffled, in one call | Splits the original into units of information (event, fact, detail, speaker, feeling, image, logic, emphasis, reference); marks each version kept, compressed, changed or dropped; lists what each version adds | Per 100 units of the original |

A version passes the gate with no integrity incident and fewer than 3 misreadings per 1,000 source words; versions
that pass are ranked by the reading score. Every number has a 95% interval from resampling passages. The rubric and
the unit tracker are diagnostics: neither predicts readers.

### What do the reading judges check?

*How to read:* fewer flags means smoother reading; for the reader mirror, a higher rating is better.

| Judge (prompt, `judge.py` name) | Runs | What it flags | Number it gives |
| --- | --- | --- | --- |
| Editor at a publisher (`editor.md`, `editor`) | 2 | Must-fix changes against matters of taste; kinds: calque, word choice, grammar, punctuation, clarity, style | Must-fix style changes per 100 words |
| Demanding reader (`friction_demanding.md`, `friction`) | 1 | Places the reading was disturbed: unclear, hard to follow, sentence structure, unnatural, too literal, register, wordy, flat, mechanics | Weighted issues per 100 words |
| Avid reader, who reads fast for pleasure (`friction_avid.md`, `friction_avid`) | 1 | The same minus "too literal": only what stops the story | Weighted issues per 100 words |
| Reader mirror (`reader_mirror.md`, `mirror`) | 1 | LAIT's own questionnaire: acceptability, smoothness, immersion, would you keep reading | Mean rating |

Hiding the source matters most: a source-aware judge forgives clumsy phrasing because it knows what was meant.

## Do the judges agree with readers?

The judges were designed on 9 books and tested once on 6 held-out books of LAIT, the reader study of Ferstler et al.
(2026) [1]: 386 passages from 15 novels translated from French, Polish and Japanese into English, each read by two
avid readers who chose between the published translation and the study's MT.

*How to read:* agreement runs from −1 to +1; higher is closer to real readers. Two readers agree with each other at +0.18.

| Validation on LAIT | Result |
| --- | --- |
| Agreement with a single reader | +0.22 (two readers agree with each other at +0.18) |
| Passages where both readers were sure | 68% right (90 of 116 human wins, 14 of 24 machine wins) |
| The 6 books held out of all design | +0.19 (the readers there agree at +0.07) |
| Ranking whole books | +0.69 |
| GPT-6 instead of Claude as the judges | Same direction; the two families correlate at +0.76 |
| LAIT's own metrics (MetricX-QE, GEMBA-MQM, LiTransProQA) | Chance, 0.48–0.50 |

The agreement comes from the stumbles. Stumbles alone (the editor's style errors and both readers' issues) reach +0.20;
the questionnaire ratings alone +0.18, falling to +0.03 once stumbles and copy-editing are regressed out. Copy-editing
stays out of the score on purpose: folded in, it rewarded polish, and an unedited original scored far below its own
polished translations.

The meaning judge catches 51 of 61 real errors on our answer key while flagging 10 of 33 deliberate liberties in
published translations; on the study's published translations it keeps 23 of 31 real slips.

### What can't the judges measure?

The reading judges are a strong stumble meter and a poor judge of craft. They rank Transept Pro above the published
translations by +0.51 (295 of 386 passages), and the lead collapses to a near coin flip (+0.05) once stumbles and
copy-editing are stripped from the ratings. No reader has compared AI with the published translations; the judges are
validated only on published translations against a weaker MT, and only into English. GPT-6 agrees with Claude, which
rules out self-preference but not a preference all models share. The unit tracker counts units; it can't tell whether a
cut served the scene.

## Run it

```bash
pip install anthropic          # for the API backend
export ANTHROPIC_API_KEY=...   # or `ant auth login`

# reading judges and the meaning judge, one window and one system at a time
for j in editor friction friction_avid mirror meaning; do
  python3 judge.py $j examples/intermezzo/bench.json runs/intermezzo
done
python3 score.py examples/intermezzo/bench.json runs/intermezzo --vs opus,haiku

# rubric (slow: maximum effort, one call per paragraph), then the checker and the native reader
python3 judge.py builder examples/intermezzo/bench.json runs/intermezzo
python3 judge.py checker examples/intermezzo/bench.json runs/intermezzo
python3 judge.py native  examples/intermezzo/bench.json runs/intermezzo

# unit tracker: all versions of a window in one call
python3 tracker.py run examples/prologue/bench.json runs/tracker --systems opus,transept-standard,neon-low \
    --backend gemini          # needs GEMINI_API_KEY; --backend claude uses judge.py's model
python3 tracker.py score runs/tracker
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
adds a plain baseline translation by any Claude model. For a target that a closely related language tends to leak into,
set `"interference"` to that language's name to add an interference category to the editor and the readers.

Each judge's prompt, effort and inputs are listed at the top of [`judge.py`](judge.py). The model is pinned
(`claude-opus-5-5`) and recorded with the effort and the prompt's hash in every output; there is no fallback to
another model, because a judge that changes model is a different benchmark. `score.py` prints misreadings per 1,000
source words as `hard/1k`.

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
author's English ("house"); the prologue has eleven more versions, described below. Глава 2 and the prologue also carry
the unit tracker's calls (`tracker/`). All judging ran through `JUDGE_BACKEND=claude-code`.

*How to read:* reading score, higher reads better; copy-edit fixes and misreadings, lower is better; rubric elements
lost, lower is better; native, the share of rubric elements that read native, higher is better.

| Text | Version | Reading score [95%] | Copy-edit fixes / 100 words | Misreadings / 1,000 words | Gate | Rubric elements lost / 1,000 words | Native |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Глава 2 | The author's English | −0.61 [−0.92, −0.29] | 0.38 | 0.00 | pass | 9.0 | 84% |
| | Opus 5.5, plain | −1.00 [−1.24, −0.70] | 0.16 | 0.00 | pass | 5.1 | 86% |
| | Sonnet 5.5, plain | −1.44 [−1.54, −1.25] | 0.11 | 3.85 | fail | 6.4 | 80% |
| | Haiku 5.5, plain | −2.46 [−3.07, −1.69] | 0.21 | 5.13 | fail | 16.7 | 69% |
| Prologue | Opus 5.5, plain | +0.01 [−0.93, +0.63] | 0.22 | 1.14 | pass | 5.7 | 87% |
| | Sonnet 5.5, plain | −0.60 [−0.95, −0.39] | 0.13 | 2.28 | pass | 14.8 | 80% |
| | Haiku 5.5, plain | −1.68 [−1.94, −1.53] | 0.36 | 6.85 | fail | 17.1 | 76% |
| Intermezzo | Opus 5.5, plain | +0.30 [−0.14, +0.78] | 0.17 | 0.00 | pass | 6.9 | 85% |
| | Sonnet 5.5, plain | +0.20 [−0.44, +0.84] | 0.25 | 0.00 | pass | 9.0 | 81% |
| | Haiku 5.5, plain | +0.01 [−0.51, +0.42] | 0.57 | 2.07 | pass | 11.0 | 75% |
| Miss Brill | Opus 5.5, plain | +1.40 [+1.03, +1.75] | 0.34 | 0.51 | pass | 4.0 | 90% |
| | Sonnet 5.5, plain | +0.17 [−0.38, +0.79] | 0.20 | 1.52 | pass | 9.4 | 80% |
| | Haiku 5.5, plain | −0.55 [−1.53, +0.28] | 0.94 | 1.52 | pass | 12.9 | 76% |

Reading scores from different texts are on one scale but measure different texts; compare versions within a text.
With three to six windows per text the intervals are wide: these are examples of the method, not a ranking of models.

What the gate caught on Глава 2: Sonnet read the novel's coined term "Плани" (the Plans) as "Planes", and turned a
dative ("sent to Agnes") into "Agnes had assigned"; Haiku read "доля" (fate) as "share" and invented a line of
dialogue. Each counted only because both runs of the meaning judge found it.

### How does the prologue read through the Transept pipeline and Gemini 4?

`examples/prologue` holds eleven more versions of the prologue, made on 24 November 2026: Transept Standard and Pro
(Claude Opus 5.5 at low and high effort, through Transept's translation pipeline), and Google's Gemini 4 Neon, Argon and
Carbon, each called plainly at low and at high thinking with the same prompt as the baselines above, and at low
thinking through Transept. Same judges, same three windows.

*How to read:* as above.

| Version | Reading score [95%] | Copy-edit fixes / 100 words | Misreadings / 1,000 words | Gate | Rubric elements lost / 1,000 words | Native |
| --- | --- | --- | --- | --- | --- | --- |
| Transept Standard | +0.22 [−0.38, +0.64] | 0.22 | 0.00 | pass | 10.3 | 88% |
| Carbon high, plain | +0.19 [−0.01, +0.32] | 0.00 | 0.00 | pass | 8.0 | 88% |
| Argon low through Transept | +0.16 [−0.26, +0.76] | 0.08 | 0.00 | pass | 13.7 | 84% |
| Neon low through Transept | +0.12 [−0.32, +0.63] | 0.11 | 1.14 | pass | 14.8 | 88% |
| Transept Pro | +0.11 [−0.37, +0.56] | 0.17 | 0.00 | pass | 8.0 | 91% |
| Carbon low through Transept | +0.05 [−0.39, +0.49] | 0.04 | 0.00 | pass | 13.7 | 89% |
| Neon high, plain | −0.06 [−0.26, +0.29] | 0.13 | 0.00 | pass | 10.3 | 84% |
| Carbon low, plain | −0.42 [−0.96, +0.29] | 0.00 | 0.00 | pass | 10.3 | 83% |
| Argon high, plain | −0.44 [−0.68, −0.13] | 0.10 | 0.00 | pass | 9.1 | 82% |
| Neon low, plain | −0.56 [−0.79, −0.20] | 0.08 | 0.00 | pass | 9.1 | 90% |
| Argon low, plain | −1.13 [−1.44, −0.76] | 0.07 | 0.00 | pass | 9.1 | 83% |

The intervals overlap; the paired differences, window by window, are firmer. Against the same model called plainly at
low thinking, Transept adds +0.68 [+0.47, +0.83] to Neon, +1.30 [+1.18, +1.52] to Argon and +0.46 [+0.19, +1.01] to
Carbon, ahead in all three windows each time. More thinking helps every plain Gemini model here (Neon +0.50, Argon
+0.69, Carbon +0.61) but costs far more: Carbon at high thinking spent about 31,000 thinking tokens on this 877-word
text, against none at low.

### What do the versions do with the original's information?

The unit tracker's calls in `examples/*/tracker/` were made by Gemini 4 Hydrogen at high thinking, the tracker that
agreed most with the author's hand audit (79% of 78 claims, against 69–73% for Opus and Gemini 4 Carbon, Argon and
Neon). "Kept" is solid; "compressed" and "changed" are inflated, because models treat shifts in wording, intensity or
image as changed information where translators see equivalents (in the hand audit of the first tracker run, the author
agreed with 40% of its "compressed" and 33% of its "changed" claims).

*How to read:* units of the original per 100. Higher "kept" means closer to the original, not a better translation.

| Text | Version | Kept | Compressed | Changed | Dropped | Added |
| --- | --- | --- | --- | --- | --- | --- |
| Глава 2 | The author's English | 80.9 | 6.6 | 11.8 | 0.7 | 2.9 |
| | Opus 5.5, plain | 96.3 | 2.2 | 1.5 | 0.0 | 2.9 |
| | Sonnet 5.5, plain | 96.3 | 2.9 | 0.7 | 0.0 | 0.0 |
| | Haiku 5.5, plain | 85.3 | 4.4 | 10.3 | 0.0 | 2.2 |
| Prologue, first call (six versions) | Opus 5.5, plain | 99.1 | 0.3 | 0.6 | 0.0 | 1.2 |
| | Neon high, plain | 97.3 | 1.2 | 0.9 | 0.6 | 2.7 |
| | Transept Pro | 94.6 | 3.3 | 2.1 | 0.0 | 2.1 |
| | Neon low, plain | 94.3 | 2.1 | 2.7 | 0.9 | 2.4 |
| | Transept Standard | 93.2 | 2.7 | 3.6 | 0.6 | 0.6 |
| | Neon low through Transept | 90.5 | 3.3 | 4.8 | 1.5 | 3.9 |
| Prologue, second call (eight versions) | Argon high, plain | 97.2 | 2.2 | 0.6 | 0.0 | 1.3 |
| | Argon low, plain | 97.2 | 1.9 | 0.9 | 0.0 | 2.2 |
| | Carbon high, plain | 96.9 | 2.5 | 0.6 | 0.0 | 0.3 |
| | Carbon low, plain | 95.9 | 2.2 | 1.9 | 0.0 | 3.1 |
| | Transept Standard | 94.0 | 2.2 | 3.4 | 0.3 | 0.9 |
| | Carbon low through Transept | 91.8 | 4.1 | 3.8 | 0.3 | 11.0 |
| | Argon low through Transept | 90.3 | 4.4 | 5.3 | 0.0 | 6.6 |
| | Neon low through Transept | 90.0 | 5.6 | 4.1 | 0.3 | 5.6 |

The second prologue call repeats two versions from the first as anchors: Standard moves from 93.2 to 94.0 kept and Neon
through Transept from 90.5 to 90.0, so a call's size shifts the marks by about one unit. Compare versions within a call.

Creative decisions count as changes. On Глава 2, 11 of the 12 "changed" marks on the author's English in the last
window fall on names he set in his own glossary (CISAME, the Ground, the Gathers and others); the twelfth is the
tracker itself reading "Плани" (the Plans) as "Planes".

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
