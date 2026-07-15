"""Hybrid retrieval + gated answer generation."""

from __future__ import annotations

import re
from typing import Any

from app.db import documents, warehouse
from app.policy.gate import GateDecision, evaluate_gate
from app.settings import get_settings


def _sql_for_question(question: str) -> dict[str, Any]:
    q = question.lower()
    if "northstar" in q:
        return warehouse.run_sql(
            """
            SELECT a.account_id, a.name, a.segment, a.region, a.arr_usd, a.champion,
                   e.sku, e.seats, e.discount_pct, p.tier, p.unit_price_usd
            FROM accounts a
            JOIN entitlements e ON a.account_id = e.account_id
            JOIN price_list p ON p.sku = e.sku AND p.tier = a.segment
            WHERE a.name LIKE '%Northstar%'
            """
        )
    if "helios" in q:
        return warehouse.run_sql(
            "SELECT * FROM accounts WHERE name LIKE '%Helios%'"
        )
    if "orbit" in q:
        return warehouse.run_sql(
            "SELECT * FROM accounts WHERE name LIKE '%Orbit%'"
        )
    if any(w in q for w in ("cloud shield", "cs-ent", "shield")):
        return warehouse.run_sql(
            "SELECT * FROM price_list WHERE sku = 'CS-ENT'"
        )
    if "data fabric" in q or "df-ent" in q:
        return warehouse.run_sql(
            "SELECT * FROM price_list WHERE sku = 'DF-ENT'"
        )
    if "observability" in q or "obs-su" in q:
        return warehouse.run_sql(
            "SELECT * FROM price_list WHERE sku = 'OBS-SU'"
        )
    if any(w in q for w in ("price", "pricing", "list price", "discount")):
        return warehouse.run_sql(
            "SELECT pr.name, pl.sku, pl.tier, pl.unit_price_usd, pl.effective_from "
            "FROM price_list pl JOIN products pr ON pr.sku = pl.sku "
            "ORDER BY pr.name, pl.tier"
        )
    if "emea" in q or "dpa" in q:
        return warehouse.run_sql(
            "SELECT account_id, name, segment, region, champion FROM accounts WHERE region = 'EMEA'"
        )
    return warehouse.run_sql(
        "SELECT account_id, name, segment, region, arr_usd, champion FROM accounts LIMIT 5"
    )


def _compose_answer(
    question: str,
    sql_result: dict[str, Any],
    doc_hits: list[documents.DocHit],
) -> str:
    rows = sql_result.get("rows") or []
    parts = [f"Question: {question}", "", "Structured findings:"]
    if not rows:
        parts.append("- No SQL rows returned.")
    for r in rows[:5]:
        parts.append("- " + ", ".join(f"{k}={v}" for k, v in r.items()))

    parts += ["", "Policy / contract findings:"]
    for h in doc_hits:
        parts.append(f"- ({h.citation_id}) {h.title}: {h.text}")

    # Deterministic commercial conclusion for common paths
    ql = question.lower()
    if rows and ("price" in ql or "discount" in ql or "quote" in ql):
        row = rows[0]
        if "unit_price_usd" in row and "discount_pct" in row:
            list_p = float(row["unit_price_usd"])
            disc = float(row["discount_pct"])
            net = list_p * (1 - disc / 100)
            parts += [
                "",
                (
                    f"Compliant quote math: list ${list_p:.2f} with {disc:.1f}% entitlement "
                    f"discount → net ${net:.2f} per unit."
                ),
            ]
        elif "unit_price_usd" in row:
            parts += ["", f"List unit price from price book: ${float(row['unit_price_usd']):.2f}."]

    sql_cites = sql_result.get("citation_ids") or []
    doc_cites = [h.citation_id for h in doc_hits]
    parts += [
        "",
        "Citations:",
        "SQL: " + (", ".join(sql_cites) if sql_cites else "none"),
        "DOC: " + (", ".join(doc_cites) if doc_cites else "none"),
    ]
    return "\n".join(parts)


def _maybe_llm_polish(question: str, draft: str) -> str:
    settings = get_settings()
    if not settings.USE_LLM or not settings.has_llm_key:
        return draft
    try:
        if settings.LLM_PROVIDER == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=settings.GOOGLE_API_KEY,
                temperature=0,
            )
        else:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=0,
            )
        prompt = (
            "Rewrite the draft into a concise enterprise answer. "
            "KEEP all citation IDs exactly (sql:... and doc:...). "
            "Do not invent numbers.\n\n"
            f"Question: {question}\n\nDraft:\n{draft}"
        )
        out = llm.invoke(prompt).content
        return out if isinstance(out, str) else str(out)
    except Exception:  # noqa: BLE001
        return draft


def ask(
    question: str,
    *,
    enforce_gate: bool | None = None,
    bypass_docs: bool = False,
    bypass_sql: bool = False,
) -> dict[str, Any]:
    """Run hybrid retrieval and apply HybridGate before releasing the answer."""
    settings = get_settings()
    enforce = settings.ENFORCE_HYBRID_GATE if enforce_gate is None else enforce_gate

    sql_result = (
        {"ok": True, "rows": [], "citation_ids": [], "columns": []}
        if bypass_sql
        else _sql_for_question(question)
    )
    doc_hits = [] if bypass_docs else documents.search_docs(question, top_k=3)

    sql_citations = list(sql_result.get("citation_ids") or [])
    # If join query didn't tag entitlements well, add generic sql cite when rows exist
    if sql_result.get("ok") and sql_result.get("rows") and not sql_citations:
        sql_citations = ["sql:query_result"]

    doc_citations = [h.citation_id for h in doc_hits]
    gate = evaluate_gate(
        question,
        sql_citations=sql_citations,
        doc_citations=doc_citations,
        enforce=enforce,
    )

    draft = _compose_answer(question, sql_result, doc_hits)
    polished = _maybe_llm_polish(question, draft)

    blocked = gate.decision == GateDecision.BLOCK
    return {
        "question": question,
        "allowed": not blocked,
        "answer": (
            polished
            if not blocked
            else (
                "BLOCKED by HybridGate: insufficient dual-source evidence.\n"
                + "\n".join(f"- {v}" for v in gate.violations)
                + "\nRetrieve both SQL and policy citations, then retry."
            )
        ),
        "gate": gate.as_dict(),
        "sql": {
            "ok": sql_result.get("ok"),
            "error": sql_result.get("error"),
            "rows": sql_result.get("rows", [])[:10],
            "citations": sql_citations,
        },
        "documents": [
            {
                "citation_id": h.citation_id,
                "title": h.title,
                "clause": h.clause,
                "text": h.text,
                "score": h.score,
            }
            for h in doc_hits
        ],
        "schema": warehouse.schema_text(),
    }


def ask_ungated_sql_only(question: str) -> dict[str, Any]:
    """Contrast mode: SQL-only answer (should fail HybridGate)."""
    return ask(question, enforce_gate=True, bypass_docs=True)


def ask_ungated_docs_only(question: str) -> dict[str, Any]:
    """Contrast mode: docs-only answer (should fail HybridGate)."""
    return ask(question, enforce_gate=True, bypass_sql=True)
