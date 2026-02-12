"""
Execution Checklist Generator
==============================
Converts all compliance findings, deal classification tags,
evidence gaps, conflict findings, and opinion conditions into
a single structured pre-closing checklist.

This is the bridge between analysis and action.
Without a checklist, analysis is informational.
With a checklist, analysis becomes executable.

Each item has:
  - Category (regulatory, evidence, escrow, signatory, etc.)
  - Priority (CRITICAL, HIGH, MEDIUM, LOW)
  - Description
  - Responsible party hint
  - Status (OPEN / IN_PROGRESS / CLEARED / WAIVED)
  - Gate (PRE_GENERATION / PRE_SIGNATURE / PRE_CLOSING / POST_CLOSING)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from engine._icons import ICON_CHECK, ICON_CROSS, ICON_WARN, ICON_BLOCK


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

GATE_ORDER = {
    "PRE_GENERATION": 0,
    "PRE_SIGNATURE": 1,
    "PRE_CLOSING": 2,
    "POST_CLOSING": 3,
}

PRIORITY_ORDER = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFO": 4,
}


@dataclass
class ChecklistItem:
    """A single pre-closing checklist entry."""
    item_id: str
    category: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    gate: str  # PRE_GENERATION, PRE_SIGNATURE, PRE_CLOSING, POST_CLOSING
    responsible: str = "Counsel"  # Counsel, Compliance, Operations, Client
    status: str = "OPEN"
    notes: str = ""

    @property
    def status_icon(self) -> str:
        icons = {
            "OPEN": ICON_CROSS,
            "IN_PROGRESS": ICON_WARN,
            "CLEARED": ICON_CHECK,
            "WAIVED": "~",
        }
        return icons.get(self.status, "?")

    def __str__(self) -> str:
        return (
            f"  {self.status_icon} [{self.item_id}] {self.description}\n"
            f"    Priority: {self.priority} | Gate: {self.gate} | "
            f"Owner: {self.responsible} | Status: {self.status}"
        )


@dataclass
class ExecutionChecklist:
    """Complete pre-closing execution checklist."""
    transaction_type: str
    entity_name: str
    counterparty_name: str
    generated_at: str = ""
    items: list[ChecklistItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def open_count(self) -> int:
        return sum(1 for i in self.items if i.status == "OPEN")

    @property
    def cleared_count(self) -> int:
        return sum(1 for i in self.items if i.status == "CLEARED")

    @property
    def critical_open(self) -> int:
        return sum(
            1 for i in self.items
            if i.status == "OPEN" and i.priority == "CRITICAL"
        )

    @property
    def is_clear_to_close(self) -> bool:
        """True only if every PRE_CLOSING or earlier item is CLEARED or WAIVED."""
        for item in self.items:
            if item.gate in ("PRE_GENERATION", "PRE_SIGNATURE", "PRE_CLOSING"):
                if item.status not in ("CLEARED", "WAIVED"):
                    return False
        return True

    def items_by_gate(self) -> dict[str, list[ChecklistItem]]:
        """Group items by execution gate."""
        result: dict[str, list[ChecklistItem]] = {}
        for item in sorted(
            self.items,
            key=lambda i: (GATE_ORDER.get(i.gate, 9), PRIORITY_ORDER.get(i.priority, 9)),
        ):
            result.setdefault(item.gate, []).append(item)
        return result

    def summary(self) -> str:
        lines = [
            f"EXECUTION CHECKLIST -- {self.transaction_type}",
            f"Entity:        {self.entity_name}",
            f"Counterparty:  {self.counterparty_name}",
            f"Generated:     {self.generated_at}",
            f"Total Items:   {len(self.items)}",
            f"Open:          {self.open_count}  |  Cleared: {self.cleared_count}",
            f"Critical Open: {self.critical_open}",
            f"Clear to Close: {'YES' if self.is_clear_to_close else 'NO'}",
            "",
        ]

        for gate, items in self.items_by_gate().items():
            lines.append(f"--- {gate} ---")
            for item in items:
                lines.append(str(item))
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_type": self.transaction_type,
            "entity_name": self.entity_name,
            "counterparty_name": self.counterparty_name,
            "generated_at": self.generated_at,
            "total_items": len(self.items),
            "open_count": self.open_count,
            "cleared_count": self.cleared_count,
            "critical_open": self.critical_open,
            "clear_to_close": self.is_clear_to_close,
            "items": [
                {
                    "item_id": i.item_id,
                    "category": i.category,
                    "priority": i.priority,
                    "description": i.description,
                    "gate": i.gate,
                    "responsible": i.responsible,
                    "status": i.status,
                }
                for i in self.items
            ],
        }


# ---------------------------------------------------------------------------
# Checklist Builder
# ---------------------------------------------------------------------------

class ChecklistBuilder:
    """
    Builds a unified pre-closing checklist from all engine outputs.
    """

    def __init__(self) -> None:
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:03d}"

    def build(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any],
        transaction_type: str,
        *,
        validation_findings: list | None = None,
        cp_validation_findings: list | None = None,
        red_flags: list | None = None,
        evidence_gaps: list | None = None,
        cp_evidence_gaps: list | None = None,
        conflict_findings: list | None = None,
        classification_tags: list | None = None,
        opinion_conditions: list[str] | None = None,
        opinion_grade: str | None = None,
        signature_blocked: bool = False,
    ) -> ExecutionChecklist:
        """
        Build a complete execution checklist from all analysis outputs.
        """
        self._counter = 0

        checklist = ExecutionChecklist(
            transaction_type=transaction_type,
            entity_name=entity.get("legal_name", "UNKNOWN"),
            counterparty_name=counterparty.get("legal_name", "UNKNOWN"),
        )

        # 1. Compliance validation findings → checklist items
        self._ingest_validation_findings(
            checklist, validation_findings or [], "Entity"
        )
        self._ingest_validation_findings(
            checklist, cp_validation_findings or [], "Counterparty"
        )

        # 2. Red flags → checklist items
        self._ingest_red_flags(checklist, red_flags or [])

        # 3. Evidence gaps → checklist items
        self._ingest_evidence_gaps(
            checklist, evidence_gaps or [], "Entity"
        )
        self._ingest_evidence_gaps(
            checklist, cp_evidence_gaps or [], "Counterparty"
        )

        # 4. Conflict matrix findings → checklist items
        self._ingest_conflict_findings(checklist, conflict_findings or [])

        # 5. Deal classification tags → checklist items
        self._ingest_classification_tags(checklist, classification_tags or [])

        # 6. Opinion conditions → checklist items
        self._ingest_opinion_conditions(
            checklist, opinion_conditions or [], opinion_grade
        )

        # 7. Signature gate
        if signature_blocked:
            checklist.items.append(ChecklistItem(
                item_id=self._next_id("SIG"),
                category="SIGNATURE",
                priority="CRITICAL",
                description="Signature blocked by policy. Resolve ADVERSE conditions before proceeding.",
                gate="PRE_SIGNATURE",
                responsible="Counsel",
            ))

        return checklist

    # --- Ingestion methods ---

    def _ingest_validation_findings(
        self, cl: ExecutionChecklist, findings: list, party_label: str,
    ) -> None:
        for f in findings:
            sev = getattr(f, "severity", None)
            if sev is None:
                continue
            sev_str = sev.value if hasattr(sev, "value") else str(sev)

            if sev_str == "INFO":
                continue  # Don't checklist info items

            priority = "HIGH" if sev_str == "ERROR" else "MEDIUM"
            gate = "PRE_GENERATION" if sev_str == "ERROR" else "PRE_SIGNATURE"
            code = getattr(f, "code", "VAL")
            msg = getattr(f, "message", str(f))

            cl.items.append(ChecklistItem(
                item_id=self._next_id("VAL"),
                category=f"COMPLIANCE ({party_label})",
                priority=priority,
                description=f"[{code}] {msg}",
                gate=gate,
                responsible="Compliance",
            ))

    def _ingest_red_flags(self, cl: ExecutionChecklist, flags: list) -> None:
        for rf in flags:
            category = getattr(rf, "category", "RED FLAG")
            severity = getattr(rf, "severity", "MEDIUM")
            desc = getattr(rf, "description", str(rf))
            rec = getattr(rf, "recommendation", "")

            gate = "PRE_GENERATION" if severity == "CRITICAL" else "PRE_SIGNATURE"

            cl.items.append(ChecklistItem(
                item_id=self._next_id("RF"),
                category=f"RED FLAG: {category}",
                priority=severity,
                description=f"{desc}  ->  {rec}" if rec else desc,
                gate=gate,
                responsible="Compliance",
            ))

    def _ingest_evidence_gaps(
        self, cl: ExecutionChecklist, gaps: list, party_label: str,
    ) -> None:
        for gap in gaps:
            sev = getattr(gap, "severity", "WARNING")
            desc = getattr(gap, "description", str(gap))
            cat = getattr(gap, "category", "EVIDENCE")

            priority = "HIGH" if sev == "ERROR" else "MEDIUM"

            cl.items.append(ChecklistItem(
                item_id=self._next_id("EV"),
                category=f"EVIDENCE ({party_label}): {cat}",
                priority=priority,
                description=desc,
                gate="PRE_SIGNATURE",
                responsible="Operations",
            ))

    def _ingest_conflict_findings(
        self, cl: ExecutionChecklist, conflicts: list,
    ) -> None:
        for c in conflicts:
            severity = getattr(c, "severity", "MEDIUM")
            code = getattr(c, "code", "CON")
            desc = getattr(c, "description", str(c))
            rec = getattr(c, "recommendation", "")

            gate = "PRE_GENERATION" if severity == "CRITICAL" else "PRE_SIGNATURE"

            cl.items.append(ChecklistItem(
                item_id=self._next_id("CON"),
                category=f"CONFLICT: {code}",
                priority=severity if severity in PRIORITY_ORDER else "MEDIUM",
                description=f"{desc}  ->  {rec}" if rec else desc,
                gate=gate,
                responsible="Counsel",
            ))

    def _ingest_classification_tags(
        self, cl: ExecutionChecklist, tags: list,
    ) -> None:
        for tag in tags:
            tag_name = getattr(tag, "tag", str(tag))
            risk_level = getattr(tag, "risk_level", "MEDIUM")
            actions = getattr(tag, "required_actions", [])

            for action in actions:
                gate = (
                    "PRE_GENERATION" if risk_level == "CRITICAL"
                    else "PRE_SIGNATURE" if risk_level == "HIGH"
                    else "PRE_CLOSING"
                )

                cl.items.append(ChecklistItem(
                    item_id=self._next_id("CLS"),
                    category=f"CLASSIFICATION: {tag_name}",
                    priority=risk_level if risk_level in PRIORITY_ORDER else "MEDIUM",
                    description=action,
                    gate=gate,
                    responsible="Compliance" if risk_level in ("CRITICAL", "HIGH") else "Operations",
                ))

    def _ingest_opinion_conditions(
        self, cl: ExecutionChecklist, conditions: list[str], grade: str | None,
    ) -> None:
        for cond in conditions:
            cl.items.append(ChecklistItem(
                item_id=self._next_id("OPN"),
                category="OPINION CONDITION",
                priority="HIGH" if grade in ("ADVERSE", "UNABLE_TO_OPINE") else "MEDIUM",
                description=cond,
                gate="PRE_SIGNATURE",
                responsible="Counsel",
            ))
