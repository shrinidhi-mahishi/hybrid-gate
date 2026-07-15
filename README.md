# HybridGate

**Structured SQL + unstructured policy evidence, with dual-citation gates.**

Pure RAG can invent prices. Pure SQL ignores contract language. HybridGate requires **both** before an answer is released.

```
Question
  → SQL warehouse (price_list, entitlements, accounts)
  → Policy/MSA document retrieval
  → HybridGate policy check
       ALLOW  → release answer + citations
       BLOCK  → refuse until both evidence types exist
```

## Why it boosts a Principal GenAI profile

| Weak demo | HybridGate |
|---|---|
| Chat over PDFs | SQL facts + contract clauses |
| Hope the model cites sources | Hard gate on citation types |
| One retrieval path | Hybrid commercial decisioning |

## Quick start

```bash
cd hybrid-gate
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000

Try modes:
- **Hybrid** — SQL + docs (should ALLOW for well-formed pricing/compliance questions)
- **SQL only** — expect **BLOCK**
- **Docs only** — expect **BLOCK**

No API key required for the default deterministic composer. Optional LLM polish: `USE_LLM=true` + `OPENAI_API_KEY`.

## Example questions

- What is the compliant Cloud Shield Enterprise quote for Northstar after entitlement discount?
- Does Helios Energy need an EMEA DPA before production processing?
- What is Cloud Shield SMB list price and what policy caps SMB discounts?

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/api/schema` | SQL schema |
| GET | `/api/docs` | Policy corpus |
| GET | `/api/examples` | Sample questions |
| POST | `/api/ask` | `{question, mode: hybrid\|sql_only\|docs_only}` |
| POST | `/api/sql?query=` | Read-only SQL probe |

## Deploy (Render)

Blueprint via `render.yaml` or Docker web service. Set `ENFORCE_HYBRID_GATE=true`.

## Resume one-liner

> Built HybridGate: a dual-source decision agent that blocks commercial answers unless both SQL warehouse rows and policy/MSA clauses are cited.
