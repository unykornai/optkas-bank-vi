"""
Capital Structure Tracker
=========================

Tracks capital commitments, allocation percentages, contribution
types (cash vs. in-kind), and validates that allocations sum
correctly and comply with JV governance rules.

Designed for the OPTKAS/Cuerpo Markets × Bank JV structure where:
  - Capital is committed by multiple parties
  - Each party has a commitment percentage
  - Contributions can be cash or in-kind (infrastructure, IP, etc.)
  - The system tracks commitments vs. actual contributions
  - Waterfall logic determines revenue/distribution priority
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import ROOT_DIR


# ── Models ──────────────────────────────────────────────────────


@dataclass
class CapitalCommitment:
    """A single party's capital commitment to the deal."""
    party_name: str
    party_type: str  # uhnwi | wealth_manager | family_office | gp | partner | entity
    commitment_percentage: float
    commitment_amount: float | None = None
    contribution_type: str = "cash"  # cash | in_kind | mixed
    in_kind_description: str | None = None
    committed_date: str | None = None
    funded_amount: float = 0.0
    funded_date: str | None = None
    status: str = "COMMITTED"  # COMMITTED | PARTIALLY_FUNDED | FULLY_FUNDED | WITHDRAWN

    @property
    def unfunded(self) -> float:
        if self.commitment_amount is None:
            return 0.0
        return max(0.0, self.commitment_amount - self.funded_amount)

    @property
    def funded_percentage(self) -> float:
        if self.commitment_amount is None or self.commitment_amount == 0:
            return 100.0 if self.status == "FULLY_FUNDED" else 0.0
        return round(self.funded_amount / self.commitment_amount * 100, 2)


@dataclass
class RevenueAllocation:
    """Revenue split rule for a party."""
    party_name: str
    revenue_percentage: float
    priority: int = 1  # 1 = first in waterfall
    conditions: list[str] = field(default_factory=list)


@dataclass
class CapitalStructure:
    """Complete capital structure for a deal or JV."""
    deal_name: str
    total_commitment: float | None = None
    currency: str = "USD"
    commitments: list[CapitalCommitment] = field(default_factory=list)
    revenue_splits: list[RevenueAllocation] = field(default_factory=list)
    governance_rules: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def total_committed_pct(self) -> float:
        return sum(c.commitment_percentage for c in self.commitments)

    @property
    def total_funded(self) -> float:
        return sum(c.funded_amount for c in self.commitments)

    @property
    def total_unfunded(self) -> float:
        if self.total_commitment is None:
            return 0.0
        return max(0.0, self.total_commitment - self.total_funded)

    @property
    def is_fully_allocated(self) -> bool:
        return abs(self.total_committed_pct - 100.0) < 0.01

    @property
    def is_fully_funded(self) -> bool:
        return all(c.status == "FULLY_FUNDED" for c in self.commitments)

    def validate(self) -> list[str]:
        """Return list of validation issues."""
        issues = []
        total_pct = self.total_committed_pct
        if abs(total_pct - 100.0) > 0.01:
            issues.append(
                f"Allocation sums to {total_pct}%, not 100%. "
                f"{'Overallocated' if total_pct > 100 else 'Underallocated'} "
                f"by {abs(total_pct - 100.0):.2f}%."
            )

        # Check for duplicate parties
        names = [c.party_name for c in self.commitments]
        if len(names) != len(set(names)):
            issues.append("Duplicate party names in capital structure.")

        # Check revenue split totals
        rev_total = sum(r.revenue_percentage for r in self.revenue_splits)
        if self.revenue_splits and abs(rev_total - 100.0) > 0.01:
            issues.append(
                f"Revenue allocation sums to {rev_total}%, not 100%."
            )

        # Check for in-kind contributions without description
        for c in self.commitments:
            if c.contribution_type in ("in_kind", "mixed") and not c.in_kind_description:
                issues.append(
                    f"{c.party_name}: In-kind contribution declared but "
                    f"no description provided. Must specify assets, IP, "
                    f"or services being contributed."
                )

        # Check for no governance rules
        if not self.governance_rules:
            issues.append(
                "No governance rules defined. JV requires at minimum: "
                "dual-signature authority, oversight committees, "
                "and decision-making thresholds."
            )

        return issues

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "CAPITAL STRUCTURE",
            f"  {self.deal_name}",
            "=" * 60,
            f"Total Commitment: {self._fmt_money(self.total_commitment)} {self.currency}",
            f"Total Funded:     {self._fmt_money(self.total_funded)} {self.currency}",
            f"Allocation:       {self.total_committed_pct}%",
            f"Status:           {'FULLY ALLOCATED' if self.is_fully_allocated else 'INCOMPLETE'}",
            "",
            "--- COMMITMENTS ---",
        ]

        for c in sorted(self.commitments, key=lambda x: -x.commitment_percentage):
            funded_tag = f" [{c.funded_percentage}% funded]" if c.commitment_amount else ""
            contrib_tag = f" ({c.contribution_type})" if c.contribution_type != "cash" else ""
            lines.append(
                f"  {c.commitment_percentage:6.1f}%  {c.party_name} "
                f"[{c.party_type}]{contrib_tag}{funded_tag}"
            )
            if c.in_kind_description:
                lines.append(f"          In-kind: {c.in_kind_description}")

        if self.revenue_splits:
            lines.append("")
            lines.append("--- REVENUE WATERFALL ---")
            for r in sorted(self.revenue_splits, key=lambda x: x.priority):
                lines.append(
                    f"  Priority {r.priority}: {r.revenue_percentage}% -> {r.party_name}"
                )
                for cond in r.conditions:
                    lines.append(f"    Condition: {cond}")

        if self.governance_rules:
            lines.append("")
            lines.append("--- GOVERNANCE ---")
            for rule in self.governance_rules:
                lines.append(f"  * {rule}")

        issues = self.validate()
        if issues:
            lines.append("")
            lines.append("--- ISSUES ---")
            for issue in issues:
                lines.append(f"  [X] {issue}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "total_commitment": self.total_commitment,
            "currency": self.currency,
            "total_committed_pct": self.total_committed_pct,
            "total_funded": self.total_funded,
            "is_fully_allocated": self.is_fully_allocated,
            "is_fully_funded": self.is_fully_funded,
            "commitments": [
                {
                    "party_name": c.party_name,
                    "party_type": c.party_type,
                    "commitment_percentage": c.commitment_percentage,
                    "commitment_amount": c.commitment_amount,
                    "contribution_type": c.contribution_type,
                    "in_kind_description": c.in_kind_description,
                    "funded_amount": c.funded_amount,
                    "funded_percentage": c.funded_percentage,
                    "status": c.status,
                }
                for c in self.commitments
            ],
            "revenue_splits": [
                {
                    "party_name": r.party_name,
                    "revenue_percentage": r.revenue_percentage,
                    "priority": r.priority,
                    "conditions": r.conditions,
                }
                for r in self.revenue_splits
            ],
            "governance_rules": self.governance_rules,
            "validation_issues": self.validate(),
            "created_at": self.created_at,
        }

    @staticmethod
    def _fmt_money(amount: float | None) -> str:
        if amount is None:
            return "TBD"
        if amount >= 1_000_000_000:
            return f"${amount / 1_000_000_000:,.2f}B"
        if amount >= 1_000_000:
            return f"${amount / 1_000_000:,.2f}M"
        return f"${amount:,.2f}"


# ── Capital Structure Builder ───────────────────────────────────


class CapitalStructureBuilder:
    """Builds capital structures from entity data and deal terms."""

    def build_jv_structure(
        self,
        deal_name: str,
        parties: list[dict[str, Any]],
        total_commitment: float | None = None,
        currency: str = "USD",
        revenue_splits: list[dict[str, Any]] | None = None,
        governance_rules: list[str] | None = None,
    ) -> CapitalStructure:
        """
        Build a JV capital structure.

        Each party dict should have:
          - party_name: str
          - party_type: str (uhnwi, wealth_manager, family_office, gp, partner, entity)
          - commitment_percentage: float
          - contribution_type: str (cash, in_kind, mixed)
          - in_kind_description: str (optional)
          - commitment_amount: float (optional)
        """
        structure = CapitalStructure(
            deal_name=deal_name,
            total_commitment=total_commitment,
            currency=currency,
        )

        for p in parties:
            commitment = CapitalCommitment(
                party_name=p["party_name"],
                party_type=p.get("party_type", "partner"),
                commitment_percentage=p["commitment_percentage"],
                commitment_amount=p.get("commitment_amount"),
                contribution_type=p.get("contribution_type", "cash"),
                in_kind_description=p.get("in_kind_description"),
                committed_date=p.get("committed_date"),
                funded_amount=p.get("funded_amount", 0.0),
                status=p.get("status", "COMMITTED"),
            )
            structure.commitments.append(commitment)

        if revenue_splits:
            for r in revenue_splits:
                structure.revenue_splits.append(RevenueAllocation(
                    party_name=r["party_name"],
                    revenue_percentage=r["revenue_percentage"],
                    priority=r.get("priority", 1),
                    conditions=r.get("conditions", []),
                ))

        if governance_rules:
            structure.governance_rules = governance_rules

        return structure

    def save(self, structure: CapitalStructure, directory: Path | None = None) -> Path:
        """Save capital structure to JSON."""
        if directory is None:
            directory = ROOT_DIR / "output" / "capital_structures"
        directory.mkdir(parents=True, exist_ok=True)

        slug = structure.deal_name.replace(" ", "_").replace("/", "_")
        path = directory / f"capital_{slug}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(structure.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        return path
