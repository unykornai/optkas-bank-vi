"""
Deal Governance Framework Engine
==================================
Assembles a complete, actionable governance framework for a deal group
by merging entity-level governance data with institutional templates.

Phase 7 surfaced this gap: the GovernanceBuilder (governance_rules.py)
can validate and template, but there was no engine to:
  1. Merge governance from multiple entities into one deal-level framework
  2. Detect authority gaps and conflict-of-interest patterns
  3. Produce a signable governance package with all rules, thresholds,
     and reporting schedules in one document

This engine does all three.

Input:  Issuer entity, SPV entity, additional entities, deal name
Output: DealGovernanceReport with framework, gap analysis, authority map

Design rules:
  - Every deal must have at least dual-signature authority
  - Every deal must have oversight committees (Risk, Compliance, Audit)
  - Decision thresholds must be defined or defaulted from template
  - Reporting requirements must be defined or defaulted
  - Authority conflicts (same person holding incompatible roles) are flagged
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.governance_rules import (
    GovernanceBuilder,
    GovernanceFramework,
    Committee,
    DecisionThreshold,
    SignatureRule,
    ReportingRequirement,
)
from engine.schema_loader import load_entity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "governance"

# Roles that create conflict if held by same person
CONFLICTING_ROLES = [
    ({"president", "director"}, {"compliance_officer", "auditor"}),
    ({"authorized_signatory"}, {"auditor", "independent_trustee"}),
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class AuthorityEntry:
    """A person/role in the authority map."""
    name: str
    entity: str
    title: str
    roles: list[str] = field(default_factory=list)
    can_bind: bool = False
    can_move_funds: bool = False
    can_pledge_assets: bool = False


@dataclass
class AuthorityConflict:
    """Detected conflict of interest in authority assignments."""
    person: str
    entity: str
    conflicting_roles: list[str] = field(default_factory=list)
    description: str = ""
    severity: str = "HIGH"  # HIGH, MEDIUM

    def to_dict(self) -> dict:
        return {
            "person": self.person,
            "entity": self.entity,
            "conflicting_roles": self.conflicting_roles,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class GovernanceGap:
    """Missing governance element."""
    area: str           # committees, signature_rules, thresholds, reporting, controls
    description: str
    recommendation: str
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM

    def to_dict(self) -> dict:
        return {
            "area": self.area,
            "description": self.description,
            "recommendation": self.recommendation,
            "severity": self.severity,
        }


@dataclass
class DealGovernanceReport:
    """Complete deal-level governance assessment."""
    deal_name: str
    assessed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    entities: list[str] = field(default_factory=list)
    framework: GovernanceFramework | None = None
    authority_map: list[AuthorityEntry] = field(default_factory=list)
    conflicts: list[AuthorityConflict] = field(default_factory=list)
    gaps: list[GovernanceGap] = field(default_factory=list)
    merged_from_entities: int = 0
    template_applied: bool = False

    @property
    def is_compliant(self) -> bool:
        if not self.framework:
            return False
        return self.framework.is_compliant and len(self.conflicts) == 0

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def gap_count(self) -> int:
        return len(self.gaps)

    @property
    def grade(self) -> str:
        """A-F governance grade."""
        if not self.framework:
            return "F"
        issues = self.framework.validate()
        deductions = len(issues) * 10 + len(self.conflicts) * 15 + len(self.gaps) * 5
        score = max(0, 100 - deductions)
        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 50:
            return "C"
        if score >= 30:
            return "D"
        return "F"

    @property
    def score(self) -> float:
        if not self.framework:
            return 0.0
        issues = self.framework.validate()
        deductions = len(issues) * 10 + len(self.conflicts) * 15 + len(self.gaps) * 5
        return max(0.0, min(100.0, 100.0 - deductions))

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "DEAL GOVERNANCE REPORT",
            f"  {self.deal_name}",
            f"  Assessed: {self.assessed_at}",
            "=" * 70,
            "",
            f"  Grade:        {self.grade}",
            f"  Score:        {self.score:.0f}%",
            f"  Compliant:    {'YES' if self.is_compliant else 'NO'}",
            f"  Entities:     {len(self.entities)}",
            f"  Conflicts:    {self.conflict_count}",
            f"  Gaps:         {self.gap_count}",
            "",
        ]

        if self.framework:
            lines.append(f"--- STRUCTURE ---")
            lines.append(f"  Type: {self.framework.structure}")
            lines.append(f"  Committees: {len(self.framework.committees)}")
            lines.append(f"  Signature rules: {len(self.framework.signature_rules)}")
            lines.append(f"  Decision thresholds: {len(self.framework.decision_thresholds)}")
            lines.append(f"  Reporting requirements: {len(self.framework.reporting)}")
            lines.append(f"  Controls: {len(self.framework.controls)}")
            lines.append("")

        if self.authority_map:
            lines.append("--- AUTHORITY MAP ---")
            for a in self.authority_map:
                powers = []
                if a.can_bind:
                    powers.append("BIND")
                if a.can_move_funds:
                    powers.append("FUNDS")
                if a.can_pledge_assets:
                    powers.append("PLEDGE")
                lines.append(f"  {a.name} [{a.title}] @ {a.entity}")
                lines.append(f"    Powers: {', '.join(powers) if powers else 'NONE'}")
            lines.append("")

        if self.conflicts:
            lines.append("--- AUTHORITY CONFLICTS ---")
            for c in self.conflicts:
                lines.append(f"  [{c.severity}] {c.person} @ {c.entity}")
                lines.append(f"    Roles: {', '.join(c.conflicting_roles)}")
                lines.append(f"    {c.description}")
            lines.append("")

        if self.gaps:
            lines.append("--- GOVERNANCE GAPS ---")
            for g in self.gaps:
                lines.append(f"  [{g.severity}] {g.area}: {g.description}")
                lines.append(f"    Recommendation: {g.recommendation}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "assessed_at": self.assessed_at,
            "grade": self.grade,
            "score": self.score,
            "is_compliant": self.is_compliant,
            "entities": self.entities,
            "merged_from_entities": self.merged_from_entities,
            "template_applied": self.template_applied,
            "framework": self.framework.to_dict() if self.framework else None,
            "authority_map": [
                {
                    "name": a.name,
                    "entity": a.entity,
                    "title": a.title,
                    "roles": a.roles,
                    "can_bind": a.can_bind,
                    "can_move_funds": a.can_move_funds,
                    "can_pledge_assets": a.can_pledge_assets,
                }
                for a in self.authority_map
            ],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "gaps": [g.to_dict() for g in self.gaps],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DealGovernanceEngine:
    """
    Assembles deal-level governance from entity data + institutional templates.

    Usage:
        engine = DealGovernanceEngine()
        report = engine.assess(
            deal_name="OPTKAS-TC Advantage",
            entity_paths=[
                Path("data/entities/tc_advantage_traders.yaml"),
                Path("data/entities/optkas1_spv.yaml"),
                Path("data/entities/optkas_platform.yaml"),
            ],
        )
        print(report.summary())
    """

    def __init__(self) -> None:
        self.builder = GovernanceBuilder()

    def assess(
        self,
        deal_name: str,
        entity_paths: list[Path] | None = None,
    ) -> DealGovernanceReport:
        """Assess deal-level governance across all entities."""
        report = DealGovernanceReport(deal_name=deal_name)
        entities: list[dict] = []

        for ep in (entity_paths or []):
            e = load_entity(ep)
            entities.append(e)
            report.entities.append(e.get("legal_name", str(ep)))

        # 1. Try to merge entity governance data
        framework = self._merge_entity_governance(entities, deal_name, report)

        # 2. If incomplete, fill from institutional template
        framework = self._apply_template_defaults(framework, deal_name, report)
        report.framework = framework

        # 3. Build authority map from all entities
        self._build_authority_map(entities, report)

        # 4. Detect authority conflicts
        self._detect_conflicts(report)

        # 5. Gap analysis
        self._analyze_gaps(framework, report)

        return report

    def _merge_entity_governance(
        self,
        entities: list[dict],
        deal_name: str,
        report: DealGovernanceReport,
    ) -> GovernanceFramework:
        """Merge governance sections from all entities into one framework."""
        framework = GovernanceFramework(deal_name=deal_name)
        seen_committees: set[str] = set()
        merged_count = 0

        for e in entities:
            gov = e.get("governance", {})
            if not gov:
                continue
            merged_count += 1

            framework.structure = gov.get("structure", framework.structure)

            for c in gov.get("committees", []):
                name = c.get("name", "")
                if name.lower() not in seen_committees:
                    seen_committees.add(name.lower())
                    framework.committees.append(Committee(
                        name=name,
                        scope=c.get("scope", ""),
                        chair=c.get("chair"),
                        members_required=c.get("members_required", 2),
                        quorum=c.get("quorum", 2),
                        meeting_frequency=c.get("meeting_frequency", "quarterly"),
                    ))

            for ctrl in gov.get("controls", []):
                if ctrl not in framework.controls:
                    framework.controls.append(ctrl)

            # JV structure
            jv = e.get("jv_structure", {})
            if jv and not framework.ownership_split:
                framework.ownership_split = jv.get("ownership_split", "")

        report.merged_from_entities = merged_count
        return framework

    def _apply_template_defaults(
        self,
        framework: GovernanceFramework,
        deal_name: str,
        report: DealGovernanceReport,
    ) -> GovernanceFramework:
        """Fill missing governance elements from institutional template."""
        tpl = GovernanceBuilder.INSTITUTIONAL_TEMPLATE
        applied = False

        # Signature rules
        if not framework.signature_rules:
            framework.signature_rules = list(tpl["signature_rules"])
            applied = True

        # Decision thresholds
        if not framework.decision_thresholds:
            framework.decision_thresholds = list(tpl["decision_thresholds"])
            applied = True

        # Reporting
        if not framework.reporting:
            framework.reporting = list(tpl["reporting"])
            applied = True

        # Committees - add missing required ones
        existing_names = {c.name.lower() for c in framework.committees}
        for tpl_committee in tpl["committees"]:
            if tpl_committee.name.lower() not in existing_names:
                framework.committees.append(tpl_committee)
                applied = True

        # Controls
        if not framework.controls:
            framework.controls = list(tpl["controls"])
            applied = True

        report.template_applied = applied
        return framework

    def _build_authority_map(
        self, entities: list[dict], report: DealGovernanceReport,
    ) -> None:
        """Build a consolidated authority map from all entity signatories/directors."""
        for e in entities:
            entity_name = e.get("legal_name", "Unknown")

            for sig in e.get("signatories", []):
                name = sig.get("name", "Unknown")
                title = sig.get("title", "Unknown")
                roles = []
                if title:
                    roles.append(title.lower().replace(" ", "_"))
                if sig.get("can_bind_company"):
                    roles.append("authorized_signatory")

                report.authority_map.append(AuthorityEntry(
                    name=name,
                    entity=entity_name,
                    title=title,
                    roles=roles,
                    can_bind=sig.get("can_bind_company", False),
                    can_move_funds=sig.get("can_move_funds", False),
                    can_pledge_assets=sig.get("can_pledge_assets", False),
                ))

            for d in e.get("directors", []):
                name = d.get("name", "Unknown")
                already = any(a.name == name and a.entity == entity_name for a in report.authority_map)
                if not already:
                    report.authority_map.append(AuthorityEntry(
                        name=name,
                        entity=entity_name,
                        title=d.get("authority_level", "Director"),
                        roles=["director"],
                        can_bind=d.get("authority_level", "").lower() == "full",
                        can_move_funds=False,
                        can_pledge_assets=False,
                    ))

    def _detect_conflicts(self, report: DealGovernanceReport) -> None:
        """Detect authority conflicts (same person holding incompatible roles)."""
        # Cross-entity: same person with authority at multiple entities
        people: dict[str, list[AuthorityEntry]] = {}
        for a in report.authority_map:
            key = a.name.lower().strip()
            people.setdefault(key, []).append(a)

        for name, entries in people.items():
            if len(entries) <= 1:
                continue

            # Same person across multiple entities with fund/pledge authority
            entities_with_funds = [
                e for e in entries if e.can_move_funds or e.can_pledge_assets
            ]
            if len(entities_with_funds) >= 2:
                entity_names = [e.entity for e in entities_with_funds]
                report.conflicts.append(AuthorityConflict(
                    person=entries[0].name,
                    entity=", ".join(entity_names),
                    conflicting_roles=[
                        f"{e.title}@{e.entity}" for e in entities_with_funds
                    ],
                    description=(
                        f"{entries[0].name} has fund movement or pledge authority "
                        f"at {len(entity_names)} entities in the deal group. "
                        f"This creates a potential conflict of interest requiring "
                        f"independent oversight."
                    ),
                    severity="HIGH",
                ))

        # Within-entity: incompatible role combinations
        for a in report.authority_map:
            role_set = set(r.lower() for r in a.roles)
            for set_a, set_b in CONFLICTING_ROLES:
                if role_set & set_a and role_set & set_b:
                    report.conflicts.append(AuthorityConflict(
                        person=a.name,
                        entity=a.entity,
                        conflicting_roles=list(role_set & set_a | role_set & set_b),
                        description=(
                            f"{a.name} holds roles that create segregation of duties "
                            f"concern: {', '.join(role_set & set_a)} and "
                            f"{', '.join(role_set & set_b)}."
                        ),
                        severity="MEDIUM",
                    ))

    def _analyze_gaps(
        self, framework: GovernanceFramework, report: DealGovernanceReport,
    ) -> None:
        """Identify remaining governance gaps after template application."""
        # Check if framework validates
        issues = framework.validate()
        for issue in issues:
            area = "general"
            if "committee" in issue.lower():
                area = "committees"
            elif "signature" in issue.lower():
                area = "signature_rules"
            elif "threshold" in issue.lower():
                area = "thresholds"
            elif "reporting" in issue.lower():
                area = "reporting"
            elif "control" in issue.lower():
                area = "controls"

            report.gaps.append(GovernanceGap(
                area=area,
                description=issue,
                recommendation=f"Define or update {area} in entity governance YAML.",
                severity="HIGH",
            ))

        # Check authority map adequacy
        if not report.authority_map:
            report.gaps.append(GovernanceGap(
                area="authority",
                description="No signatories or directors found across deal entities.",
                recommendation="Define signatories with explicit authority in entity YAMLs.",
                severity="CRITICAL",
            ))

        # Check for dual-sig capability
        binders = [a for a in report.authority_map if a.can_bind]
        if len(binders) < 2:
            report.gaps.append(GovernanceGap(
                area="signature_rules",
                description=(
                    f"Only {len(binders)} signatory with binding authority. "
                    f"Dual-signature requires at least 2."
                ),
                recommendation="Designate at least 2 signatories with can_bind_company: true.",
                severity="HIGH",
            ))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, report: DealGovernanceReport) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = report.deal_name.replace(" ", "_").replace(",", "").replace(".", "")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"deal_governance_{slug}_{ts}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path
