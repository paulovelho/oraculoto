"""The live crawler (docs/crawler.md), split across two machines because Caixa blocks data centers.

- `protocol`: the plan and the JSON lines the two sides exchange, and how a response is classified
- `fetch`: home machine; the only part that talks to Caixa (needs the `fetch` extra, no database)
- `plan`, `ingest`: server; read the database, parse responses and write through `save_draw()`
- `caixa`: Caixa's JSON → `DrawData` (docs/crawler.md §4)
"""
