# open-classics-api

**An open, dependency-free JSON API over public-domain classical Chinese literature — built for learners, teachers, and educational software.**

[中文说明](README.zh-CN.md) · [API contract](http://localhost:8000/api/openapi.json) · MIT License

---

## Why this exists

Classical Chinese poetry (*shīcí*) is part of the compulsory curriculum for every
student in China, and it is also studied by heritage learners and second-language
learners around the world. Yet the material is scattered: it lives in scanned
textbooks, in PDFs that no program can read, and in a handful of large research
corpora that are built for linguists rather than for learners.

What is missing is the middle layer — a **small, clean, machine-readable corpus
with a free API**, so that anyone building a study app, a recitation trainer, an
Anki deck generator, or a classroom quiz tool does not have to scrape and clean
the text themselves.

This project provides that layer. It is deliberately narrow in scope and
deliberately boring in implementation: one JSON file, one small Python service,
no database, no external dependencies.

### Who it is for

- **Students** who want to search a line they half-remember and get the full text
  with a plain-language note.
- **Teachers** who want to build recitation sheets or quizzes without
  copy-pasting from a dozen websites.
- **Developers of educational tools** who need a stable, documented, CORS-enabled
  JSON endpoint instead of a fragile scraper.
- **Learners of Chinese as a second language** who need the text plus a short
  gloss, not a scholarly apparatus.

### Non-goals

This is not a research corpus, not a full-text archive of all Chinese literature,
and not a competitor to the large academic datasets. It is a **curated learning
corpus** — a small set of the works that people actually study, with the
metadata a learning application needs.

---

## What is in the corpus

| | |
|---|---|
| Works | 47 |
| Authors | 21 |
| Dynasties | Tang, Song, Five Dynasties, Three Kingdoms, Pre-Qin |
| Genres | 五言绝句, 七言绝句, 五言律诗, 七言律诗, 词, 铭, 说, 书, 语录体 |
| Thematic tags | 66 distinct tags (思乡, 边塞, 隐逸, 咏物, …) |

Every work is in the **public domain**. All authors died more than 100 years ago,
and no copyright is claimed over the texts. The editorial policy is recorded in
`data/works.json` under `meta.editorial_policy`: text follows the standard
editions commonly used in Chinese school textbooks, variant readings are
acknowledged, and corrections are accepted by pull request.

Each record carries:

```json
{
  "id": "tang-jingyesi",
  "title": "静夜思",
  "author": "李白",
  "dynasty": "唐",
  "genre": "五言绝句",
  "tags": ["思乡", "月", "夜晚"],
  "content": ["床前明月光，", "疑是地上霜。", "举头望明月，", "低头思故乡。"],
  "note": "以极浅白的语言写羁旅思乡：月光如霜，抬头低头之间，乡愁已满。"
}
```

`content` is an array of lines split at natural reading pauses, so a client can
render a recitation card without guessing where the line breaks go. `note` is a
one-sentence gloss written for a learner, not for a specialist.

---

## Quick start

No installation, no virtualenv, no requirements file. Python 3.10+ and the
standard library are enough.

```bash
git clone https://github.com/Rikka-8964/open-classics-api.git
cd open-classics-api
python app.py
```

```
open-classics-api 0.1.0
  corpus : 47 works / 21 authors / 2541 characters
  listen : http://0.0.0.0:8000
```

Open <http://localhost:8000> for the browse interface, or hit the API directly:

```bash
curl "http://localhost:8000/api/works?q=明月&limit=3"
curl "http://localhost:8000/api/works/tang-jingyesi"
curl "http://localhost:8000/api/random?tag=思乡"
curl "http://localhost:8000/api/stats"
```

To bind a different port:

```bash
PORT=3000 python app.py
```

### Running the tests

```bash
python -m unittest discover -s tests -v
```

24 tests cover the store (ranking, filtering, pagination, determinism) and the
HTTP surface (status codes, CORS, error handling).

---

## API reference

Base URL: `/`. All responses are JSON with UTF-8 encoding and
`Access-Control-Allow-Origin: *`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/stats` | Corpus statistics and service metrics |
| `GET` | `/api/works` | Search, filter, sort and paginate works |
| `GET` | `/api/works/{id}` | Fetch a single work by id |
| `GET` | `/api/random` | One random work, optionally constrained |
| `GET` | `/api/authors` | Author facet counts |
| `GET` | `/api/tags` | Thematic tag facet counts |
| `GET` | `/api/dynasties` | Dynasty facet counts |
| `GET` | `/api/genres` | Genre facet counts |
| `GET` | `/api/facets` | All facet counts in one call |
| `GET` | `/api/openapi.json` | OpenAPI 3.1 description of this API |

### `GET /api/works`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — | Free-text query. Space-separated terms are combined with **AND**. |
| `author` | string | — | Exact match |
| `dynasty` | string | — | Exact match |
| `genre` | string | — | Exact match |
| `tag` | string | — | Exact match against the tag list |
| `page` | integer | `1` | 1-based |
| `limit` | integer | `20` | Clamped to 1–100 |
| `sort` | enum | `relevance` | `relevance` \| `title` \| `author` \| `dynasty` |

```json
{
  "total": 12,
  "page": 1,
  "limit": 20,
  "pages": 1,
  "items": [
    {
      "id": "tang-jingyesi",
      "title": "静夜思",
      "author": "李白",
      "dynasty": "唐",
      "genre": "五言绝句",
      "tags": ["思乡", "月", "夜晚"],
      "excerpt": "床前明月光，疑是地上霜。举头望明月，低头思故乡。"
    }
  ]
}
```

### Relevance ranking

Ranking uses explicit weights rather than an opaque scoring library, so the
behaviour can be reviewed and argued about in a pull request:

| Match | Weight |
|---|---|
| Title, exact | 1000 |
| Title, partial | 300 |
| Author | 200 |
| Tag, exact | 160 |
| Tag, partial | 120 |
| Body text | 100 |
| Genre / dynasty | 60 |
| Note | 40 |

A query term that matches nothing scores 0 and the whole work is dropped. Scores
are summed across terms, then ties break on title. The constants live at the top
of `classics/store.py`.

### Errors

Errors use a consistent envelope and a meaningful HTTP status:

```json
{ "error": { "code": "work_not_found", "message": "No work with that id.", "status": 404 } }
```

| Status | When |
|---|---|
| `404` | Unknown route, unknown work id, or an empty random pool |
| `429` | More than 120 requests per minute from one client |
| `500` | Unexpected server error |

### Rate limiting

Public instances apply a per-client sliding window of **120 requests / 60 s**.
The counter is in-memory and deliberately simple; if the service ever needs to
scale horizontally, the counter should move to shared storage first. This is
noted in the source rather than silently ignored.

---

## Deployment

The service reads `HOST` and `PORT` from the environment and binds `0.0.0.0`, so
it runs unchanged on a VPS, in a container, or behind a reverse proxy:

```bash
PORT=8000 python app.py
```

Because there are no third-party dependencies, deployment needs no build step,
no lockfile, and no package manager. A `systemd` unit is two lines.

### Why this needs a server

A JSON corpus on its own could be served as static files. This project is a
**service**, and the following features genuinely require a running process:

- **Server-side search and ranking.** Relevance is computed per query across the
  whole corpus, including multi-term AND matching. A static host cannot do this.
- **Server-side filtering, sorting and pagination** over 66 tags, 21 authors and
  10 genres, so a client never downloads the entire corpus to run one query.
- **Rate limiting and usage statistics**, which are what make it safe to offer an
  endpoint to the public for free without it being abused.
- **A stable, always-on endpoint** for third-party educational applications that
  cannot depend on a student's laptop being awake.

The service is intentionally light: the entire corpus is a few kilobytes, so a
1 vCPU / 1 GB instance has far more capacity than the project currently needs.
That headroom is the point — it leaves room for the corpus and the traffic to
grow without a rewrite.

---

## Roadmap

The corpus is a **seed**, not a finished archive. Planned work, roughly in order:

- [ ] Expand to ~300 works, covering the full compulsory-education canon
- [ ] Add `pinyin` field for every character, for second-language learners
- [ ] Add a `level` field mapping works to school stages (小学 / 初中 / 高中)
- [ ] Add traditional-character variants of every text
- [ ] Static export mode: generate a fully offline copy for low-bandwidth classrooms
- [ ] Optional SQLite backend for deployments that outgrow the in-memory store

Contributions are welcome on any of these. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Project structure

```
open-classics-api/
├── app.py                 # HTTP entry point: routing, CORS, rate limiting
├── classics/
│   ├── __init__.py
│   └── store.py           # corpus loading, ranking, filtering, facets
├── data/
│   └── works.json         # the corpus itself — the heart of the project
├── static/
│   └── index.html         # dependency-free browse interface
├── tests/
│   └── test_api.py        # 24 tests: store + HTTP surface
├── CONTRIBUTING.md
├── LICENSE                # MIT
└── README.md
```

---

## License

Code: **MIT** — see [LICENSE](LICENSE).

Corpus: **public domain.** All texts are classical works whose authors died more
than a century ago. The `note` fields and the editorial selection are released
under the same MIT terms as the code, so the dataset can be reused freely,
including commercially, with no attribution requirement. Attribution is
appreciated but not required.
