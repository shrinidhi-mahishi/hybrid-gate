"""HybridGate policy — answers must cite structured + unstructured evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class GateDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"


@dataclass
class GateResult:
    decision: GateDecision
    required: list[str]
    sql_citations: list[str] = field(default_factory=list)
    doc_citations: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    rule_id: str = "default"

    def as_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "rule_id": self.rule_id,
            "required": self.required,
            "sql_citations": self.sql_citations,
            "doc_citations": self.doc_citations,
            "violations": self.violations,
        }


def classify_intent(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("price", "pricing", "discount", "quote", "list price")):
        return "pricing_quote"
    if any(w in q for w in ("dpa", "emea", "residency", "processing")):
        return "compliance"
    if any(w in q for w in ("account", "champion", "arr", "entitlement", "northstar", "helios", "orbit")):
        return "account_commercial"
    return "general"


RULES = {
    "pricing_quote": {
        "rule_id": "RULE-PRICE-DUAL",
        "required": ["sql_price_or_entitlement", "doc_pricing_policy"],
        "description": "Pricing/discount answers need SQL price/entitlement + MSA/policy clause",
    },
    "compliance": {
        "rule_id": "RULE-COMPLIANCE-DUAL",
        "required": ["sql_account_region", "doc_compliance"],
        "description": "Compliance answers need account region from SQL + DPA/policy doc",
    },
    "account_commercial": {
        "rule_id": "RULE-ACCOUNT-DUAL",
        "required": ["sql_account", "doc_any_policy"],
        "description": "Account commercial answers need account SQL row + governing policy doc",
    },
    "general": {
        "rule_id": "RULE-GENERAL-SOFT",
        "required": ["any_sql_or_doc"],
        "description": "General questions need at least one grounded citation",
    },
}


def _has_sql_price(cites: list[str]) -> bool:
    return any(c.startswith("sql:price_list:") or c.startswith("sql:products:") for c in cites)


def _has_sql_entitlement(cites: list[str]) -> bool:
    return any("entitlement" in c or c.startswith("sql:query_result") for c in cites) or any(
        c.startswith("sql:accounts:") for c in cites
    )


def _has_sql_account(cites: list[str]) -> bool:
    return any(c.startswith("sql:accounts:") for c in cites) or any(
        "account" in c for c in cites
    )


def evaluate_gate(
    question: str,
    *,
    sql_citations: list[str],
    doc_citations: list[str],
    enforce: bool = True,
) -> GateResult:
    intent = classify_intent(question)
    rule = RULES[intent]
    sql_citations = list(dict.fromkeys(sql_citations))
    doc_citations = list(dict.fromkeys(doc_citations))
    violations: list[str] = []

    def need(label: str, ok: bool, msg: str) -> None:
        if not ok:
            violations.append(msg)

    if intent == "pricing_quote":
        need(
            "sql",
            _has_sql_price(sql_citations) or _has_sql_entitlement(sql_citations),
            "Missing SQL citation from price_list / entitlements",
        )
        need(
            "doc",
            any(c.startswith("doc:MSA-2024") or c.startswith("doc:POLICY-RESELL") or c.startswith("doc:RUNBOOK-QUOTE") for c in doc_citations),
            "Missing policy/MSA document citation for pricing",
        )
    elif intent == "compliance":
        need("sql", _has_sql_account(sql_citations), "Missing SQL account/region citation")
        need(
            "doc",
            any(c.startswith("doc:DPA-EMEA") for c in doc_citations),
            "Missing DPA/compliance document citation",
        )
    elif intent == "account_commercial":
        need("sql", _has_sql_account(sql_citations) or _has_sql_entitlement(sql_citations), "Missing SQL account citation")
        need("doc", len(doc_citations) > 0, "Missing unstructured policy citation")
    else:
        need(
            "any",
            bool(sql_citations or doc_citations),
            "Missing any grounded citation",
        )

    if not enforce:
        decision = GateDecision.ALLOW
    elif violations:
        decision = GateDecision.BLOCK
    else:
        decision = GateDecision.ALLOW

    return GateResult(
        decision=decision,
        required=rule["required"],
        sql_citations=sql_citations,
        doc_citations=doc_citations,
        violations=violations,
        rule_id=rule["rule_id"],
    )


def extract_citations_from_text(text: str) -> tuple[list[str], list[str]]:
    sql = re.findall(r"sql:[a-zA-Z0-9_:\-]+", text)
    docs = re.findall(r"doc:[a-zA-Z0-9_\-]+:[0-9.]+", text)
    return sql, docs
