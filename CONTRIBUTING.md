# Contributing to open-classics-api

Thanks for considering a contribution. This project has two kinds of work: the
**corpus** (the texts and their metadata) and the **code**. Both are welcome.

---

## The one rule that matters

**Accuracy over volume.**

A corpus of 47 correct texts is worth more than a corpus of 500 texts with
silent errors, because a learner has no way to tell which line is wrong. If you
are unsure about a character, leave it out and open an issue instead of guessing.

---

## Contributing a work to the corpus

Add an entry to the `works` array in `data/works.json`. Every field is required
except `note`.

| Field | Type | Notes |
|---|---|---|
| `id` | string | Format: `{dynasty-pinyin}-{title-pinyin}`, e.g. `tang-jingyesi`. Must be unique and stable — clients cache on it. Once merged, an id is never changed. |
| `title` | string | Include the serial number in parentheses when the poem is part of a numbered series, e.g. `出塞（其一）`. |
| `author` | string | Use the conventional Chinese name. For anonymous works, use the received attribution and say so in `note`. |
| `dynasty` | string | One of: `先秦`, `汉`, `三国`, `魏晋`, `南北朝`, `唐`, `五代`, `宋`, `元`, `明`, `清`. |
| `genre` | string | e.g. `五言绝句`, `七言律诗`, `词`, `铭`, `说`, `书`. Reuse an existing value where one fits. |
| `tags` | string[] | 2–4 thematic tags in Simplified Chinese. **Reuse existing tags** where possible — the tag list is a controlled vocabulary and every new synonym splits the facet. |
| `content` | string[] | Lines split at natural reading pauses. Each line keeps its punctuation. |
| `note` | string | One sentence, plain language, written for a learner. Explain the poem, do not paraphrase it line by line. |

### Checklist before you open a pull request

- [ ] The text matches a standard edition used in Chinese school textbooks.
- [ ] You have stated which edition you used, in the pull request description.
- [ ] The `id` is unique (`python -m unittest discover -s tests -v` checks this).
- [ ] Tags are reused from the existing vocabulary wherever possible.
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] The work is genuinely in the public domain (author died over 100 years ago).

### Correcting an existing text

Variant readings are a real feature of the classical tradition, not a bug. If you
are correcting a text, say in the pull request which edition you are following and
why it should be preferred. Do not open a pull request that simply replaces one
reading with another without a stated source.

---

## Contributing code

- **No third-party dependencies.** This is a hard constraint, not a preference.
  The project must keep running with `python app.py` on a bare interpreter. A pull
  request that adds an entry to a requirements file will be declined unless it
  removes a much larger problem than it creates.
- **Keep it boring.** Prefer the obvious implementation over the clever one.
- **Tests.** Any change to `classics/store.py` or the routing in `app.py` should
  come with a test. Run the suite with:

  ```bash
  python -m unittest discover -s tests -v
  ```

- **Ranking changes.** The relevance weights at the top of `classics/store.py` are
  deliberately explicit. If you change them, include in the pull request
  description a query that behaves better afterwards and one that behaves worse.

---

## Style

- Python: standard library style, type hints on public functions, docstrings on
  modules and non-obvious functions.
- Comments explain *why*, not *what*. If a line needs a comment to explain what it
  does, rewrite the line.
- Corpus JSON: keep the existing key order and formatting. Two-space indent.

---

## Reporting a problem with a text

Open an issue with:

1. The work `id`.
2. The line as it currently reads.
3. The line as you believe it should read.
4. Your source.

Textual errors are the highest-priority bugs in this project. They are the one
kind of defect a learner cannot work around.
