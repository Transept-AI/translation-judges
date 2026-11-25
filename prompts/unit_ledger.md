You compare translations of one passage of a novel with its original. You get the original and {n} {target} translations, labelled A to {last}, in no particular order. You don't know who made them and must not guess.

1. Read the original and split it into information units, in order. A unit is one thing a reader of the original learns or is meant to notice. Give each a type:
   - "event": an action or something that happens;
   - "fact": a state of affairs, a time, a place, a number, who someone is;
   - "detail": a descriptive particular (a colour, a gesture, an object, a sensation);
   - "speaker": who speaks, thinks or acts, when the text says it;
   - "feeling": a character's or the narrator's feeling, judgment or attitude;
   - "image": a figure of speech, comparison or metaphor;
   - "logic": a relation the text states (because, but, so, then, although);
   - "emphasis": intensity, repetition or stress (very, again, even, a repeated word);
   - "reference": a name, a quotation or a cultural or literary pointer.
   One unit is one piece: "she slammed the red door" is an event and a detail. Don't split finer than a careful reader would notice.

2. For each unit, say what each translation does with it:
   - "K" kept: a reader gets the same information;
   - "C" compressed: still there, but merged, shortened or left implicit, and a reader can still get it;
   - "D" dropped: not there;
   - "X" changed: there, but it says something else.

3. List what each translation adds that the original does not give: information, not a different wording of what is there. Types: "explain" (spells out what the original implies or explains a cultural item), "detail", "feeling", "speaker", "logic", "emphasis", "other". Quote at most eight words of the translation.

4. Name the passage's main mode: "dialogue", "action", "description" or "introspection"; and the book's likely genre from this passage: "literary", "crime", "fantasy", "sf", "horror", "romance" or "other".

Reply with JSON only, units in the order of the original, each gloss at most six words of English, every unit with a mark for each of A to {last}:
{{"mode": "", "genre": "", "units": [{{"t": "event", "g": "<gloss>", {marks}}}], "added": [{{"v": "A", "t": "explain", "q": "<quote>"}}]}}
