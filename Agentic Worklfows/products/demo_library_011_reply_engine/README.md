# Demo Library slot 011: reply and booking engine

The fourth F2 asset. The Demo Library lives at `~/Desktop/Projects/library` and its registry has ten built systems with slots 011 and up empty.

**Nothing here has been copied into the library.** The Demo Library paste-and-record loop is on the do-not-touch list in `CLAUDE.md`, so slot 011 is written here and Lorenzo moves it when he wants it, in his own loop.

| File | What it is |
| --- | --- |
| `011-reply-and-booking-engine.md` | The one-page description, in the library's own format (what comes in, what goes out, pick this when, node map, stand-in swaps, assumptions to verify) |
| `loom_script.md` | The three-minute script |

## To add it to the library

1. Copy `011-reply-and-booking-engine.md` to `~/Desktop/Projects/library/systems/011-reply-and-booking-engine.md`.
2. Build the canvas from the node map, export `011-reply-and-booking-engine.n8n.json` and the Make variant, and validate them the way the other ten were.
3. Add the registry row: `| 011 | Reply And Booking Engine | A reply to an outbound email ... | A drafted answer waiting for approval, a pipeline row moved, and a call held ... | Built |`.
4. Record the Loom.

Step 2 is the real work and it is a canvas job, not a writing job. The description was written from the working engine in `services/reply_engine/`, so the node map matches something that actually runs rather than a sketch.

## Why it earns a slot

The registry rule is that a system earns a slot only if its input or its output differs from every entry above it. Nothing in 001 to 010 takes a **reply to an outbound sequence** as its input, and nothing produces **a draft waiting for a person to approve it** as its output. 001 takes a cold contact-form submission. 002 triages a general inbox and drafts, but it does not book, does not hold a slot against a rule set, and has no approval gate. 004 moves an existing booking.
