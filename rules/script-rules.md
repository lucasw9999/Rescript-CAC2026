# Script rules

The rules the rewrite step follows when it turns a transcript into a clean script.

3. **Write `script.json`.** It is a list of units covering word 0 through the final word, contiguously: unit *n+1* starts at word `last+1`.
   - Each unit is 1–4 sentences of one thought, about 5–20 s spoken.
   - Keep every fact, claim, number, and example. Do not add any.
   - Remove fillers and hedges ("um", "you know", "like", "I think", "basically", "so yeah"), repeats, false starts, and self-corrections.
   - Fix the grammar into short, confident, declarative sentences in the speaker's first person.
   - Write hard-to-say numbers as words ("thirty-five minutes"). Keep version names as digits ("iPhone 17 Pro").
   - Note the unit indices that open a new section; you pass them to render as `--breaks`.
   - Make it sound like the speaker, not like an AI. Check the draft yourself:
     - No em dashes. Use a comma or a full stop, which also reads more naturally aloud.
     - No AI vocabulary: "leverage", "robust", "seamless", "delve", "pivotal", "comprehensive", "game-changer", "unlock".
     - No "it's not X, it's Y" reveals and no stock transitions ("moreover", "let's dive in").
     - Don't pad points into groups of three.
     - Vary sentence length, and keep the speaker's plain words where they were already plain.

   Unit forms:
   - `[w0, w1, "text"]`: words w0..w1 of the source.
   - `{"words": [w0, w1], "end": t, "text": ...}`: the same, but the video span stops at `t` seconds. Use this to cut a broken tail such as an error page or a failed demo.
   - `{"src": "/abs/other.mov", "start": s, "end": e, "text": ...}`: a span from another recording, for example a take where the demo worked. Render scales and pads it to match.

   **Merging two takes:** use the newer video, which usually has the latest slides, and write the script from its transcript plus anything the older take said better.
