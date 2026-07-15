"""Unstructured policy/contract corpus with lexical retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

DOCS: list[dict[str, str]] = [
    {
        "doc_id": "MSA-2024",
        "title": "Master Service Agreement — Pricing & Discounts",
        "clause": "4.2",
        "text": (
            "List prices in the price book are authoritative for quoting. Partner or account "
            "discounts may not exceed the entitlement discount recorded for that account without "
            "Deal Desk approval. Quoted unit price must equal list_price * (1 - discount_pct/100)."
        ),
    },
    {
        "doc_id": "MSA-2024",
        "title": "Master Service Agreement — Audit",
        "clause": "7.1",
        "text": (
            "Customer may request an annual pricing audit. Vendor must produce the price_list "
            "effective date and the entitlement discount applied at quote time."
        ),
    },
    {
        "doc_id": "POLICY-RESELL",
        "title": "Reseller Discount Policy",
        "clause": "2.1",
        "text": (
            "Enterprise segment accounts may receive up to 25% discount on Cloud Shield with "
            "an approved annual commit. SMB discounts are capped at 10% unless an exception ticket exists."
        ),
    },
    {
        "doc_id": "POLICY-RESELL",
        "title": "Reseller Discount Policy — Data Fabric",
        "clause": "2.3",
        "text": (
            "Data Fabric Enterprise discounts above 15% require VP approval. Bundling Observability "
            "Suite does not automatically increase Data Fabric discount entitlement."
        ),
    },
    {
        "doc_id": "RUNBOOK-QUOTE",
        "title": "Quote Construction Runbook",
        "clause": "1.4",
        "text": (
            "A compliant quote must cite (a) the SQL price_list row for SKU+tier and (b) the MSA or "
            "reseller policy clause governing the applied discount. Answers without both sources "
            "are non-compliant."
        ),
    },
    {
        "doc_id": "DPA-EMEA",
        "title": "EMEA Data Processing Addendum",
        "clause": "3.2",
        "text": (
            "EMEA customers require a signed DPA before production data processing. Region field "
            "on the account record must be EMEA for this obligation to apply."
        ),
    },
]


@dataclass
class DocHit:
    doc_id: str
    clause: str
    title: str
    text: str
    score: float

    @property
    def citation_id(self) -> str:
        return f"doc:{self.doc_id}:{self.clause}"


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def search_docs(query: str, top_k: int = 3) -> list[DocHit]:
    q = _tokens(query)
    hits: list[DocHit] = []
    for d in DOCS:
        blob = f"{d['title']} {d['text']} {d['doc_id']} clause {d['clause']}"
        score = float(len(q & _tokens(blob)))
        # synonym boosts
        ql = query.lower()
        if "discount" in ql and "discount" in blob.lower():
            score += 2
        if "price" in ql and "price" in blob.lower():
            score += 2
        if "dpa" in ql or "emea" in ql:
            if "emea" in blob.lower() or "dpa" in blob.lower():
                score += 3
        if "quote" in ql and "quote" in blob.lower():
            score += 2
        hits.append(
            DocHit(
                doc_id=d["doc_id"],
                clause=d["clause"],
                title=d["title"],
                text=d["text"],
                score=score,
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return [h for h in hits if h.score > 0][:top_k] or hits[:1]


def get_doc(citation_id: str) -> dict | None:
    # doc:MSA-2024:4.2
    parts = citation_id.split(":")
    if len(parts) != 3 or parts[0] != "doc":
        return None
    _, doc_id, clause = parts
    for d in DOCS:
        if d["doc_id"] == doc_id and d["clause"] == clause:
            return d
    return None
