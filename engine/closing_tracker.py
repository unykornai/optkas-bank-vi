"""
Closing Conditions Tracker
============================
Tracks conditions precedent (CPs) for deal closing. Each CP has:
  - Category (documentary, regulatory, financial, legal, operational)
  - Description and acceptance criteria
  - Responsible party
  - Deadline
  - Status (OPEN, IN_PROGRESS, SATISFIED, WAIVED, BLOCKED)
  - Gate (PRE_SIGNING, SIGNING, PRE_CLOSING, CLOSING, POST_CLOSING)

The engine:
  1. Auto-generates CPs from deal readiness report (blockers + action items)
  2. Auto-generates CPs from MTN validation (warnings/failures)
  3. Auto-generates CPs from collateral verification
  4. Allows manual addition of custom CPs
  5. Tracks satisfaction and computes closing readiness percentage
  6. Produces a closing-ready / not-ready determination

This is the last mile: after analysis → validation → readiness,
this engine tracks what must happen before signatures go on paper.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any

from engine.mtn_validator import MTNProgramValidator
from engine.collateral_verifier import CollateralVerifier
from engine.deal_readiness import DealReadinessEngine
from engine.schema_loader import load_entity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "closing_trackers"

GATE_ORDER = {
    "PRE_SIGNING": 0,
    "SIGNING": 1,
    "PRE_CLOSING": 2,
    "CLOSING": 3,
    "POST_CLOSING": 4,
}

CP_STATUSES = {"OPEN", "IN_PROGRESS", "SATISFIED", "WAIVED", "BLOCKED"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class ConditionPrecedent:
    """A single closing condition."""
    cp_id: str
    category: str           # documentary, regulatory, financial, legal, operational
    description: str
    gate: str               # PRE_SIGNING, SIGNING, PRE_CLOSING, CLOSING, POST_CLOSING
    responsible: str = "Counsel"
    deadline: str = ""      # ISO date or empty
    status: str = "OPEN"    # OPEN, IN_PROGRESS, SATISFIED, WAIVED, BLOCKED
    acceptance_criteria: str = ""
    notes: str = ""
    source: str = ""        # Where this CP was generated from (e.g., "mtn_validation", "manual")
    satisfied_at: str = ""
    satisfied_by: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status in ("SATISFIED", "WAIVED")

    @property
    def is_blocking(self) -> bool:
        return self.status == "BLOCKED"

    @property
    def is_overdue(self) -> bool:
        if not self.deadline or self.is_resolved:
            return False
        try:
            d = date.fromisoformat(self.deadline)
            return d < date.today()
        except (ValueError, TypeError):
            return False

    def satisfy(self, by: str = "System") -> None:
        self.status = "SATISFIED"
        self.satisfied_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.satisfied_by = by

    def waive(self, reason: str = "", by: str = "Authorized") -> None:
        self.status = "WAIVED"
        self.satisfied_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.satisfied_by = by
        if reason:
            self.notes = f"WAIVED: {reason}"

    def to_dict(self) -> dict:
        return {
            "cp_id": self.cp_id,
            "category": self.category,
            "description": self.description,
            "gate": self.gate,
            "responsible": self.responsible,
            "deadline": self.deadline,
            "status": self.status,
            "acceptance_criteria": self.acceptance_criteria,
            "notes": self.notes,
            "source": self.source,
            "is_resolved": self.is_resolved,
            "is_overdue": self.is_overdue,
            "satisfied_at": self.satisfied_at,
            "satisfied_by": self.satisfied_by,
        }


@dataclass
class ClosingTracker:
    """Complete closing conditions tracker for a deal."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    updated_at: str = ""
    conditions: list[ConditionPrecedent] = field(default_factory=list)
    target_closing_date: str = ""

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = self.created_at

    # -- Counters --

    @property
    def total(self) -> int:
        return len(self.conditions)

    @property
    def satisfied(self) -> int:
        return sum(1 for c in self.conditions if c.status == "SATISFIED")

    @property
    def waived(self) -> int:
        return sum(1 for c in self.conditions if c.status == "WAIVED")

    @property
    def open(self) -> int:
        return sum(1 for c in self.conditions if c.status == "OPEN")

    @property
    def in_progress(self) -> int:
        return sum(1 for c in self.conditions if c.status == "IN_PROGRESS")

    @property
    def blocked(self) -> int:
        return sum(1 for c in self.conditions if c.status == "BLOCKED")

    @property
    def resolved(self) -> int:
        return sum(1 for c in self.conditions if c.is_resolved)

    @property
    def overdue(self) -> int:
        return sum(1 for c in self.conditions if c.is_overdue)

    @property
    def completion_pct(self) -> float:
        if self.total == 0:
            return 100.0
        return round(self.resolved / self.total * 100, 1)

    @property
    def closing_ready(self) -> bool:
        """Can we close? All pre-closing CPs must be resolved."""
        for cp in self.conditions:
            if cp.gate in ("PRE_SIGNING", "SIGNING", "PRE_CLOSING", "CLOSING"):
                if not cp.is_resolved:
                    return False
        return True

    @property
    def signing_ready(self) -> bool:
        """Can we sign? All pre-signing CPs must be resolved."""
        for cp in self.conditions:
            if cp.gate == "PRE_SIGNING" and not cp.is_resolved:
                return False
        return True

    def by_gate(self, gate: str) -> list[ConditionPrecedent]:
        return [c for c in self.conditions if c.gate == gate]

    def by_category(self, category: str) -> list[ConditionPrecedent]:
        return [c for c in self.conditions if c.category == category]

    def by_responsible(self, responsible: str) -> list[ConditionPrecedent]:
        return [
            c for c in self.conditions
            if responsible.lower() in c.responsible.lower()
        ]

    def add(self, cp: ConditionPrecedent) -> None:
        self.conditions.append(cp)
        self.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def get(self, cp_id: str) -> ConditionPrecedent | None:
        return next((c for c in self.conditions if c.cp_id == cp_id), None)

    def summary(self) -> str:
        icon = {
            "OPEN": "[ ]",
            "IN_PROGRESS": "[~]",
            "SATISFIED": "[+]",
            "WAIVED": "[W]",
            "BLOCKED": "[X]",
        }
        lines = [
            "=" * 70,
            "CLOSING CONDITIONS TRACKER",
            f"  {self.deal_name}",
            f"  Created: {self.created_at}",
            "=" * 70,
            "",
            f"  COMPLETION:  {self.completion_pct}%  "
            f"({self.resolved}/{self.total} resolved)",
            f"  SIGNING:     {'READY' if self.signing_ready else 'NOT READY'}",
            f"  CLOSING:     {'READY' if self.closing_ready else 'NOT READY'}",
            "",
            f"  Satisfied: {self.satisfied}  |  Waived: {self.waived}  |  "
            f"Open: {self.open}  |  In Progress: {self.in_progress}  |  "
            f"Blocked: {self.blocked}",
        ]

        if self.overdue:
            lines.append(f"  OVERDUE:   {self.overdue} condition(s)")
        lines.append("")

        # Group by gate
        for gate in GATE_ORDER:
            gate_cps = self.by_gate(gate)
            if not gate_cps:
                continue
            resolved_count = sum(1 for c in gate_cps if c.is_resolved)
            lines.append(
                f"--- {gate.replace('_', ' ')} "
                f"({resolved_count}/{len(gate_cps)} resolved) ---"
            )
            for cp in gate_cps:
                overdue_tag = " [OVERDUE]" if cp.is_overdue else ""
                lines.append(
                    f"  {icon.get(cp.status, '[ ]')} {cp.cp_id}: {cp.description}"
                    f"{overdue_tag}"
                )
                lines.append(
                    f"      Owner: {cp.responsible}  |  "
                    f"Deadline: {cp.deadline or 'TBD'}  |  "
                    f"Category: {cp.category}"
                )
                if cp.notes:
                    lines.append(f"      Note: {cp.notes}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "target_closing_date": self.target_closing_date,
            "total": self.total,
            "resolved": self.resolved,
            "completion_pct": self.completion_pct,
            "signing_ready": self.signing_ready,
            "closing_ready": self.closing_ready,
            "conditions": [c.to_dict() for c in self.conditions],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ClosingTrackerEngine:
    """
    Generates and manages closing conditions from deal analysis.

    Usage:
        engine = ClosingTrackerEngine()
        tracker = engine.generate(
            deal_name="OPTKAS-TC Advantage",
            issuer_path=Path("data/entities/tc_advantage_traders.yaml"),
            spv_path=Path("data/entities/optkas1_spv.yaml"),
            additional_entities=[Path("data/entities/optkas_platform.yaml")],
            target_closing_date="2026-06-30",
        )
        print(tracker.summary())
    """

    def __init__(self) -> None:
        self.mtn_validator = MTNProgramValidator()
        self.collateral_verifier = CollateralVerifier()
        self._cp_counter = 0

    def _next_id(self) -> str:
        self._cp_counter += 1
        return f"CP-{self._cp_counter:03d}"

    def generate(
        self,
        deal_name: str,
        issuer_path: Path | None = None,
        spv_path: Path | None = None,
        additional_entities: list[Path] | None = None,
        target_closing_date: str = "",
    ) -> ClosingTracker:
        """Generate closing tracker from deal analysis."""
        self._cp_counter = 0
        tracker = ClosingTracker(
            deal_name=deal_name,
            target_closing_date=target_closing_date,
        )

        issuer = load_entity(issuer_path) if issuer_path else None
        spv = load_entity(spv_path) if spv_path else None
        extras = [load_entity(p) for p in (additional_entities or [])]

        # Standard documentary CPs
        self._add_standard_cps(tracker)

        # MTN-derived CPs
        if issuer and issuer.get("mtn_program"):
            self._add_mtn_cps(tracker, issuer, spv)

        # Collateral-derived CPs
        if spv:
            self._add_collateral_cps(tracker, spv, issuer)

        # Insurance CPs
        if issuer:
            self._add_insurance_cps(tracker, issuer)

        # Opinion CPs
        if issuer:
            self._add_opinion_cps(tracker, issuer)

        # Governance CPs
        all_entities = [e for e in [issuer, spv] + extras if e]
        self._add_governance_cps(tracker, all_entities)

        # Settlement CPs
        if len(all_entities) >= 2:
            self._add_settlement_cps(tracker, all_entities)

        return tracker

    # ------------------------------------------------------------------
    # CP generators
    # ------------------------------------------------------------------

    def _add_standard_cps(self, tracker: ClosingTracker) -> None:
        """Add standard pre-closing conditions."""
        tracker.add(ConditionPrecedent(
            cp_id=self._next_id(),
            category="documentary",
            description="All transaction documents in final form",
            gate="PRE_SIGNING",
            responsible="Counsel",
            acceptance_criteria="All documents reviewed and approved by all parties.",
            source="standard",
        ))
        tracker.add(ConditionPrecedent(
            cp_id=self._next_id(),
            category="regulatory",
            description="KYC/AML clearance for all counterparties",
            gate="PRE_SIGNING",
            responsible="Compliance",
            acceptance_criteria="KYC packages accepted by all banking counterparties.",
            source="standard",
        ))
        tracker.add(ConditionPrecedent(
            cp_id=self._next_id(),
            category="financial",
            description="Funds confirmed in escrow or settlement account",
            gate="PRE_CLOSING",
            responsible="Operations",
            acceptance_criteria="Settlement bank confirms fund availability.",
            source="standard",
        ))
        tracker.add(ConditionPrecedent(
            cp_id=self._next_id(),
            category="legal",
            description="All legal opinions delivered in final form",
            gate="PRE_SIGNING",
            responsible="Counsel",
            acceptance_criteria="All opinions signed, not draft.",
            source="standard",
        ))

    def _add_mtn_cps(
        self, tracker: ClosingTracker, issuer: dict, spv: dict | None,
    ) -> None:
        """Generate CPs from MTN program validation."""
        report = self.mtn_validator.validate(issuer, spv)

        for item in report.items:
            if item.status == "FAIL":
                tracker.add(ConditionPrecedent(
                    cp_id=self._next_id(),
                    category="documentary",
                    description=f"MTN: {item.check} - {item.detail}",
                    gate="PRE_SIGNING",
                    responsible="Issuer",
                    acceptance_criteria=f"Resolve: {item.detail}",
                    source="mtn_validation",
                ))
            elif item.status == "WARN":
                tracker.add(ConditionPrecedent(
                    cp_id=self._next_id(),
                    category="documentary",
                    description=f"MTN: {item.check} - {item.detail}",
                    gate="PRE_CLOSING",
                    responsible="Issuer / Counsel",
                    acceptance_criteria=f"Resolve or waive: {item.detail}",
                    source="mtn_validation",
                ))

    def _add_collateral_cps(
        self, tracker: ClosingTracker, spv: dict, issuer: dict | None,
    ) -> None:
        """Generate CPs from collateral verification."""
        report = self.collateral_verifier.verify(spv, issuer)

        for item in report.items:
            if item.status == "FAIL":
                tracker.add(ConditionPrecedent(
                    cp_id=self._next_id(),
                    category="financial",
                    description=f"Collateral: {item.check} - {item.detail}",
                    gate="PRE_SIGNING",
                    responsible="SPV Manager",
                    acceptance_criteria=f"Resolve: {item.detail}",
                    source="collateral_verification",
                ))
            elif item.status == "WARN":
                tracker.add(ConditionPrecedent(
                    cp_id=self._next_id(),
                    category="financial",
                    description=f"Collateral: {item.check} - {item.detail}",
                    gate="PRE_CLOSING",
                    responsible="SPV Manager",
                    acceptance_criteria=f"Resolve or waive: {item.detail}",
                    source="collateral_verification",
                ))

    def _add_insurance_cps(self, tracker: ClosingTracker, issuer: dict) -> None:
        """Generate CPs from insurance assessment."""
        ins = issuer.get("insurance")
        if not ins:
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="financial",
                description="Insurance coverage must be obtained and documented",
                gate="PRE_SIGNING",
                responsible="Broker / Issuer",
                acceptance_criteria="Insurance binder or policy with adequate coverage.",
                source="insurance_assessment",
            ))
            return

        broker = ins.get("broker", {})
        if not broker.get("fca_number"):
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="regulatory",
                description="Verify insurance broker FCA authorization",
                gate="PRE_SIGNING",
                responsible="Compliance",
                acceptance_criteria="FCA registration number confirmed.",
                source="insurance_assessment",
            ))

        coverage = ins.get("coverage", {})
        if not coverage.get("sum_insured"):
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="financial",
                description="Confirm insurance coverage amount (sum insured)",
                gate="PRE_SIGNING",
                responsible="Broker",
                acceptance_criteria="Sum insured documented and adequate for program size.",
                source="insurance_assessment",
            ))

    def _add_opinion_cps(self, tracker: ClosingTracker, issuer: dict) -> None:
        """Generate CPs from legal opinion status."""
        opinions = issuer.get("legal_opinions", [])
        if not opinions:
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="legal",
                description="Obtain legal opinions covering program validity",
                gate="PRE_SIGNING",
                responsible="Counsel",
                acceptance_criteria="At least one signed opinion from qualified counsel.",
                source="opinion_assessment",
            ))
            return

        for op in opinions:
            status = op.get("status", "signed").upper()
            counsel = op.get("counsel", "Unknown")
            jur = op.get("jurisdiction", "??")

            if status == "DRAFT":
                tracker.add(ConditionPrecedent(
                    cp_id=self._next_id(),
                    category="legal",
                    description=f"Finalize draft opinion from {counsel} ({jur} law)",
                    gate="PRE_SIGNING",
                    responsible=counsel,
                    acceptance_criteria=f"Opinion signed and dated by {counsel}.",
                    source="opinion_assessment",
                ))

    def _add_governance_cps(
        self, tracker: ClosingTracker, entities: list[dict],
    ) -> None:
        """Generate governance-related CPs."""
        has_governance = any(e.get("governance") for e in entities)
        if not has_governance:
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="operational",
                description="Establish governance framework (committees, authority, reporting)",
                gate="PRE_SIGNING",
                responsible="Legal / Compliance",
                acceptance_criteria="Governance framework document executed by all parties.",
                source="governance_assessment",
            ))

        # Check signatory adequacy
        total_signatories = sum(len(e.get("signatories", [])) for e in entities)
        if total_signatories < 2:
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="operational",
                description="Designate at least 2 authorized signatories for dual-sig authority",
                gate="PRE_SIGNING",
                responsible="Board / Directors",
                acceptance_criteria="Board resolution designating authorized signatories.",
                source="governance_assessment",
            ))

    def _add_settlement_cps(
        self, tracker: ClosingTracker, entities: list[dict],
    ) -> None:
        """Generate settlement-related CPs."""
        has_banking = all(e.get("banking") for e in entities[:2])
        if not has_banking:
            tracker.add(ConditionPrecedent(
                cp_id=self._next_id(),
                category="financial",
                description="Confirm banking details for all settlement counterparties",
                gate="PRE_CLOSING",
                responsible="Operations",
                acceptance_criteria="Settlement instructions confirmed by all banks.",
                source="settlement_assessment",
            ))

        # Check for settlement bank
        for e in entities[:2]:
            banking = e.get("banking", {})
            name = e.get("legal_name", "?")
            if not banking.get("settlement_bank") and not banking.get("primary_bank"):
                tracker.add(ConditionPrecedent(
                    cp_id=self._next_id(),
                    category="financial",
                    description=f"Establish settlement banking for {name}",
                    gate="PRE_CLOSING",
                    responsible="Operations",
                    acceptance_criteria=f"{name} settlement bank confirmed with SWIFT capability.",
                    source="settlement_assessment",
                ))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, tracker: ClosingTracker) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = tracker.deal_name.replace(" ", "_").replace(",", "").replace(".", "")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"closing_{slug}_{ts}.json"
        path.write_text(
            json.dumps(tracker.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def load(self, path: Path) -> ClosingTracker:
        """Load a tracker from disk."""
        data = json.loads(path.read_text(encoding="utf-8"))
        tracker = ClosingTracker(
            deal_name=data["deal_name"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            target_closing_date=data.get("target_closing_date", ""),
        )
        for cp_data in data.get("conditions", []):
            tracker.conditions.append(ConditionPrecedent(
                cp_id=cp_data["cp_id"],
                category=cp_data["category"],
                description=cp_data["description"],
                gate=cp_data["gate"],
                responsible=cp_data.get("responsible", ""),
                deadline=cp_data.get("deadline", ""),
                status=cp_data.get("status", "OPEN"),
                acceptance_criteria=cp_data.get("acceptance_criteria", ""),
                notes=cp_data.get("notes", ""),
                source=cp_data.get("source", ""),
                satisfied_at=cp_data.get("satisfied_at", ""),
                satisfied_by=cp_data.get("satisfied_by", ""),
            ))
        return tracker
