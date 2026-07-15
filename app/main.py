"""HybridGate FastAPI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent.pipeline import ask, ask_ungated_docs_only, ask_ungated_sql_only
from app.db.warehouse import init_db, run_sql, schema_text
from app.db import documents
from app.settings import get_settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("Warehouse ready at %s", get_settings().db_path)
    yield


app = FastAPI(
    title="HybridGate",
    description=(
        "Structured SQL + unstructured policy evidence with dual-citation "
        "gates before answers are released."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    enforce_gate: bool | None = None
    mode: str = Field(
        default="hybrid",
        description="hybrid | sql_only | docs_only",
    )


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "service": "hybrid-gate",
        "enforce_gate": s.ENFORCE_HYBRID_GATE,
        "use_llm": s.USE_LLM,
        "has_llm_key": s.has_llm_key,
    }


@app.get("/api/schema")
def api_schema() -> dict:
    return {"schema": schema_text()}


@app.get("/api/docs")
def api_docs() -> dict:
    return {"documents": documents.DOCS}


@app.get("/api/examples")
def api_examples() -> dict:
    return {
        "examples": [
            "What is the compliant Cloud Shield Enterprise quote for Northstar after entitlement discount?",
            "Does Helios Energy need an EMEA DPA before production processing?",
            "What is Cloud Shield SMB list price and what policy caps SMB discounts?",
            "Explain Data Fabric discount limits for Enterprise deals.",
        ]
    }


@app.post("/api/ask")
def api_ask(body: AskRequest) -> dict:
    mode = body.mode.lower().strip()
    try:
        if mode == "sql_only":
            return ask_ungated_sql_only(body.question.strip())
        if mode == "docs_only":
            return ask_ungated_docs_only(body.question.strip())
        return ask(body.question.strip(), enforce_gate=body.enforce_gate)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ask failed")
        raise HTTPException(500, str(exc)) from exc


@app.post("/api/sql")
def api_sql(query: str) -> dict:
    return run_sql(query)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
