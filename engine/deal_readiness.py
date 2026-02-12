"""
Deal Readiness Report
======================
The "can we proceed?" engine. Aggregates MTN validation, collateral
verification, insurance, legal opinions, governance, settlement path,
and evidence into a single readiness determination.

Produces three possible verdicts:
  READY           - All critical items pass. Deal can proceed.
  CONDITIONAL     - No critical failures, but warnings need attention.
  NOT_READY       - Critical blockers exist. Cannot proceed.

For each blocker or warning, the report provides a specific action item
with responsible party guidance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.mtn_validator import MTNProgramValidator
from engine.collateral_verifier import CollateralVerifier
from engine.governance_rules import GovernanceBuilder
from engine.correspondent_banking import CorrespondentBankingEngine
from engine.jurisdiction_intel import JurisdictionIntelEngine
from engine.schema_loader import load_entity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "readiness_reports"
EVIDENCE_DIR = ROOT_DIR / "data" / "evidence"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class ReadinessItem:
    """Single readiness check with action guidance."""
    area: str               # mtn, collateral, insurance, opinions, governance, settlement, evidence
    item: str               # Short label
    status: str             # PASS, WARN, FAIL
    detail: str = ""
    action: str = ""        # What to do if not PASS
    responsible: str = ""   # Who should act


@dataclass
class InsuranceSummary:
    """Structured insurance assessment."""
    exists: bool = False
    broker: str = ""
    sum_insured: float = 0
    market: str = ""
    fca_authorized: bool = False
    coverage_ratio: float = 0.0     # vs program size
    status: str = "NOT_VERIFIED"    # VERIFIED, CONDITIONAL, NOT_VERIFIED


@dataclass
class OpinionSummary:
    """Structured legal opinion tracker."""
    total: int = 0
    signed: int = 0
    draft: int = 0
    jurisdictions: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)  # Missing jurisdictions
    scope_issues: list[str] = field(default_factory=list)
    status: str = "NO_OPINIONS"  # COMPLETE, PARTIAL, DRAFT_ONLY, NO_OPINIONS


@dataclass
class DealReadinessReport:
    """Complete deal readiness assessment."""
    deal_name: str
    assessed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    entities: list[str] = field(default_factory=list)
    items: list[ReadinessItem] = field(default_factory=list)
    mtn_score: float = 0.0
    collateral_score: float = 0.0
    insurance: InsuranceSummary = field(default_factory=InsuranceSummary)
    opinions: OpinionSummary = field(default_factory=OpinionSummary)
    governance_compliant: bool = False
    settlement_viable: bool = False
    evidence_count: int = 0
    blockers: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        fails = sum(1 for i in self.items if i.status == "FAIL")
        warns = sum(1 for i in self.items if i.status == "WARN")
        if fails == 0 and warns == 0:
            return "READY"
        elif fails == 0:
            return "CONDITIONAL"
        else:
            return "NOT_READY"

    @property
    def overall_score(self) -> float:
        if not self.items:
            return 0.0
        total = sum(
            1.0 if i.status == "PASS" else 0.5 if i.status == "WARN" else 0.0
            for i in self.items
        )
        return round(total / len(self.items) * 100, 1)

    def summary(self) -> str:
        icon = {"PASS": "[+]", "WARN": "[?]", "FAIL": "[X]"}
        verdict_label = {
            "READY": "READY TO PROCEED",
            "CONDITIONAL": "CONDITIONAL - ACTION ITEMS REMAIN",
            "NOT_READY": "NOT READY - BLOCKERS EXIST",
        }
        lines = [
            "=" * 70,
            "DEAL READINESS REPORT",
            f"  {self.deal_name}",
            f"  Assessed: {self.assessed_at[:19]}Z",
            "=" * 70,
            "",
            f"  VERDICT:  {verdict_label.get(self.verdict, self.verdict)}",
            f"  SCORE:    {self.overall_score}%",
            "",
            f"  Entities:     {len(self.entities)}",
            f"  MTN Score:    {self.mtn_score}%",
            f"  Collateral:   {self.collateral_score}%",
            f"  Insurance:    {self.insurance.status}",
            f"  Opinions:     {self.opinions.status} ({self.opinions.signed} signed, {self.opinions.draft} draft)",
            f"  Governance:   {'COMPLIANT' if self.governance_compliant else 'NON-COMPLIANT'}",
            f"  Settlement:   {'VIABLE' if self.settlement_viable else 'UNRESOLVED'}",
            f"  Evidence:     {self.evidence_count} document(s)",
            "",
        ]

        # Group by area
        current_area = ""
        for item in self.items:
            if item.area != current_area:
                current_area = item.area
                lines.append(f"--- {current_area.upper().replace('_', ' ')} ---")
            lines.append(f"  {icon.get(item.status, '[ ]')} {item.item}")
            if item.detail:
                lines.append(f"      {item.detail}")
            if item.action and item.status != "PASS":
                lines.append(f"      ACTION: {item.action}")

        if self.blockers:
            lines.append("")
            lines.append("=== BLOCKERS (must resolve before proceeding) ===")
            for i, b in enumerate(self.blockers, 1):
                lines.append(f"  {i}. {b}")

        if self.action_items:
            lines.append("")
            lines.append("=== ACTION ITEMS (should resolve) ===")
            for i, a in enumerate(self.action_items, 1):
                lines.append(f"  {i}. {a}")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "assessed_at": self.assessed_at,
            "verdict": self.verdict,
            "overall_score": self.overall_score,
            "entities": self.entities,
            "mtn_score": self.mtn_score,
            "collateral_score": self.collateral_score,
            "insurance": {
                "exists": self.insurance.exists,
                "broker": self.insurance.broker,
                "sum_insured": self.insurance.sum_insured,
                "market": self.insurance.market,
                "fca_authorized": self.insurance.fca_authorized,
                "coverage_ratio": self.insurance.coverage_ratio,
                "status": self.insurance.status,
            },
            "opinions": {
                "total": self.opinions.total,
                "signed": self.opinions.signed,
                "draft": self.opinions.draft,
                "jurisdictions": self.opinions.jurisdictions,
                "gaps": self.opinions.gaps,
                "status": self.opinions.status,
            },
            "governance_compliant": self.governance_compliant,
            "settlement_viable": self.settlement_viable,
            "evidence_count": self.evidence_count,
            "blockers": self.blockers,
            "action_items": self.action_items,
            "items": [
                {
                    "area": i.area,
                    "item": i.item,
                    "status": i.status,
                    "detail": i.detail,
                    "action": i.action,
                    "responsible": i.responsible,
                }
                for i in self.items
            ],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DealReadinessEngine:
    """
    Aggregates all validation engines into one readiness determination.

    Usage:
        engine = DealReadinessEngine()
        report = engine.assess(
            deal_name="OPTKAS-TC Advantage Deal",
            issuer_path=Path("data/entities/tc_advantage_traders.yaml"),
            spv_path=Path("data/entities/optkas1_spv.yaml"),
            additional_entities=[
                Path("data/entities/optkas_platform.yaml"),
                Path("data/entities/querubin_usa.yaml"),
            ],
        )
        print(report.summary())
    """

    def __init__(self) -> None:
        self.mtn_validator = MTNProgramValidator()
        self.collateral_verifier = CollateralVerifier()
        self.governance_builder = GovernanceBuilder()
        self.banking_engine = CorrespondentBankingEngine()
        self.jurisdiction_engine = JurisdictionIntelEngine()

    def assess(
        self,
        deal_name: str,
        issuer_path: Path | None = None,
        spv_path: Path | None = None,
        additional_entities: list[Path] | None = None,
    ) -> DealReadinessReport:
        """Run comprehensive deal readiness assessment."""
        report = DealReadinessReport(deal_name=deal_name)

        # Load entities
        issuer = None
        spv = None
        all_entities: list[dict] = []

        if issuer_path:
            issuer = load_entity(issuer_path)
            all_entities.append(issuer)
            report.entities.append(issuer.get("legal_name", str(issuer_path)))

        if spv_path:
            spv = load_entity(spv_path)
            all_entities.append(spv)
            report.entities.append(spv.get("legal_name", str(spv_path)))

        for ep in (additional_entities or []):
            e = load_entity(ep)
            all_entities.append(e)
            report.entities.append(e.get("legal_name", str(ep)))

        # 1. MTN validation
        if issuer and issuer.get("mtn_program"):
            mtn_report = self.mtn_validator.validate(issuer, spv)
            report.mtn_score = mtn_report.score
            for item in mtn_report.items:
                report.items.append(ReadinessItem(
                    area="mtn_program",
                    item=item.check,
                    status=item.status,
                    detail=item.detail,
                    action=item.detail if item.status != "PASS" else "",
                ))
        else:
            report.items.append(ReadinessItem(
                area="mtn_program", item="MTN program exists", status="WARN",
                detail="No issuer with MTN program provided.",
                action="Provide issuer entity with mtn_program section.",
            ))

        # 2. Collateral verification
        if spv:
            coll_report = self.collateral_verifier.verify(spv, issuer)
            report.collateral_score = coll_report.score
            for item in coll_report.items:
                report.items.append(ReadinessItem(
                    area="collateral",
                    item=item.check,
                    status=item.status,
                    detail=item.detail,
                ))
        else:
            report.items.append(ReadinessItem(
                area="collateral", item="Collateral SPV exists", status="WARN",
                detail="No SPV entity provided for collateral verification.",
                action="Provide collateral SPV entity.",
            ))

        # 3. Insurance assessment
        if issuer:
            self._assess_insurance(issuer, report)
        else:
            report.insurance.status = "NOT_VERIFIED"
            report.items.append(ReadinessItem(
                area="insurance", item="Insurance coverage", status="WARN",
                detail="No issuer provided for insurance check.",
            ))

        # 4. Legal opinions
        if issuer:
            self._assess_opinions(issuer, report)
        else:
            report.opinions.status = "NO_OPINIONS"

        # 5. Governance
        self._assess_governance(all_entities, deal_name, report)

        # 6. Settlement path
        if len(all_entities) >= 2:
            self._assess_settlement(all_entities, report)
        else:
            report.items.append(ReadinessItem(
                area="settlement", item="Settlement path", status="WARN",
                detail="Need 2+ entities to assess settlement path.",
            ))

        # 7. Evidence inventory
        self._assess_evidence(report)

        # Compile blockers and action items
        self._compile_actions(report)

        return report

    # ------------------------------------------------------------------
    # Assessment sub-methods
    # ------------------------------------------------------------------

    def _assess_insurance(self, issuer: dict, report: DealReadinessReport) -> None:
        ins = issuer.get("insurance")
        if not ins:
            report.insurance.status = "NOT_VERIFIED"
            report.items.append(ReadinessItem(
                area="insurance", item="Insurance coverage exists", status="FAIL",
                detail="No insurance section in issuer profile.",
                action="Obtain and document insurance coverage.",
                responsible="Issuer / Broker",
            ))
            return

        coverage = ins.get("coverage", {})
        broker = ins.get("broker", {})

        report.insurance.exists = True
        report.insurance.broker = broker.get("name", "Unknown")
        report.insurance.sum_insured = coverage.get("sum_insured", 0)
        report.insurance.market = coverage.get("market", "")

        # FCA
        fca = broker.get("fca_number")
        report.insurance.fca_authorized = bool(fca)
        if fca:
            report.items.append(ReadinessItem(
                area="insurance", item="Broker FCA authorized", status="PASS",
                detail=f"FCA #{fca}.",
            ))
        else:
            report.items.append(ReadinessItem(
                area="insurance", item="Broker FCA authorized", status="WARN",
                detail="FCA number not documented.",
                action="Verify broker FCA authorization.",
            ))

        # Sum insured
        si = report.insurance.sum_insured
        if si > 0:
            report.items.append(ReadinessItem(
                area="insurance", item="Sum insured", status="PASS",
                detail=f"${si:,.0f} confirmed.",
            ))
        else:
            report.items.append(ReadinessItem(
                area="insurance", item="Sum insured", status="FAIL",
                detail="No sum insured documented.",
                action="Confirm coverage amount with broker.",
            ))

        # Market quality
        market = report.insurance.market
        if "lloyd" in market.lower():
            report.items.append(ReadinessItem(
                area="insurance", item="Market quality", status="PASS",
                detail=f"Lloyd's of London. Gold-standard market.",
            ))
        elif market:
            report.items.append(ReadinessItem(
                area="insurance", item="Market quality", status="WARN",
                detail=f"Market: {market}. Verify A-rated.",
            ))

        # Coverage ratio
        mtn = issuer.get("mtn_program", {})
        max_off = mtn.get("max_offering", 0)
        if max_off > 0 and si > 0:
            ratio = si / max_off * 100
            report.insurance.coverage_ratio = ratio
            status = "PASS" if ratio >= 10 else "WARN"
            report.items.append(ReadinessItem(
                area="insurance", item="Coverage ratio", status=status,
                detail=f"{ratio:.1f}% of max offering (${max_off:,.0f}).",
                action=f"Consider increasing coverage." if status == "WARN" else "",
            ))

        report.insurance.status = "VERIFIED" if si > 0 and fca else "CONDITIONAL"

    def _assess_opinions(self, issuer: dict, report: DealReadinessReport) -> None:
        opinions = issuer.get("legal_opinions", [])
        if not opinions:
            report.opinions.status = "NO_OPINIONS"
            report.items.append(ReadinessItem(
                area="legal_opinions", item="Legal opinions exist", status="FAIL",
                detail="No legal opinions on file.",
                action="Engage counsel to produce opinion letters.",
                responsible="Legal counsel",
            ))
            return

        report.opinions.total = len(opinions)
        for op in opinions:
            status = op.get("status", "SIGNED").upper()
            j = op.get("jurisdiction", "??")
            counsel = op.get("counsel", "Unknown")
            report.opinions.jurisdictions.append(j)

            if status == "DRAFT":
                report.opinions.draft += 1
                report.items.append(ReadinessItem(
                    area="legal_opinions",
                    item=f"Opinion: {counsel} ({j})",
                    status="WARN",
                    detail=f"DRAFT status.",
                    action=f"Finalize opinion with {counsel}.",
                    responsible=counsel,
                ))
            else:
                report.opinions.signed += 1
                report.items.append(ReadinessItem(
                    area="legal_opinions",
                    item=f"Opinion: {counsel} ({j})",
                    status="PASS",
                    detail=f"Signed opinion covering {j} law.",
                ))

            # Scope checks
            scope = op.get("scope", [])
            has_collateral = any("collateral" in s.lower() or "pledge" in s.lower() for s in scope)
            has_xrpl = any("xrpl" in s.lower() or "reserve" in s.lower() for s in scope)
            if has_collateral:
                report.items.append(ReadinessItem(
                    area="legal_opinions",
                    item=f"  Scope: collateral/pledge",
                    status="PASS",
                    detail="Covers collateral use and pledgeability.",
                ))
            if has_xrpl:
                report.items.append(ReadinessItem(
                    area="legal_opinions",
                    item=f"  Scope: XRPL/reserve system",
                    status="PASS",
                    detail="Covers XRPL reserve system integration.",
                ))

        # Jurisdiction gap analysis
        issuer_j = issuer.get("jurisdiction", "")[:2]
        covered = set(report.opinions.jurisdictions)
        if issuer_j and issuer_j not in covered:
            report.opinions.gaps.append(issuer_j)
            report.items.append(ReadinessItem(
                area="legal_opinions",
                item=f"Jurisdiction gap: {issuer_j}",
                status="FAIL",
                detail=f"No opinion covering issuer's home jurisdiction ({issuer_j}).",
                action=f"Obtain {issuer_j} counsel opinion.",
                responsible=f"{issuer_j} legal counsel",
            ))

        # Status
        if report.opinions.signed > 0 and report.opinions.draft == 0 and not report.opinions.gaps:
            report.opinions.status = "COMPLETE"
        elif report.opinions.signed > 0:
            report.opinions.status = "PARTIAL"
        else:
            report.opinions.status = "DRAFT_ONLY"

    def _assess_governance(
        self, entities: list[dict], deal_name: str, report: DealReadinessReport,
    ) -> None:
        # Try to build from entity governance data
        framework = None
        for e in entities:
            if e.get("governance"):
                framework = self.governance_builder.build_from_entity(e, deal_name)
                break

        if not framework:
            framework = self.governance_builder.build_institutional(deal_name)

        issues = framework.validate()
        report.governance_compliant = framework.is_compliant

        if framework.is_compliant:
            report.items.append(ReadinessItem(
                area="governance", item="Governance framework", status="PASS",
                detail=f"{framework.structure} structure, {len(framework.committees)} committees.",
            ))
        else:
            report.items.append(ReadinessItem(
                area="governance", item="Governance framework", status="WARN",
                detail=f"{len(issues)} governance issue(s) detected.",
                action="Complete governance framework definition.",
            ))
            for issue in issues[:3]:
                report.items.append(ReadinessItem(
                    area="governance", item=f"  Issue", status="WARN",
                    detail=issue,
                ))

    def _assess_settlement(
        self, entities: list[dict], report: DealReadinessReport,
    ) -> None:
        try:
            path = self.banking_engine.resolve_settlement_path(
                entities[0], entities[1], "USD",
            )
            report.settlement_viable = path.is_valid
            node_count = len(path.nodes)
            report.items.append(ReadinessItem(
                area="settlement", item="Settlement path resolved",
                status="PASS" if path.is_valid else "WARN",
                detail=f"{node_count} nodes, FX: {'Yes' if path.requires_fx else 'No'}.",
                action="" if path.is_valid else "Resolve settlement path issues.",
            ))
            for note in path.validation_notes[:2]:
                report.items.append(ReadinessItem(
                    area="settlement", item="  Note", status="PASS",
                    detail=note,
                ))
            for issue in path.validation_issues[:2]:
                report.items.append(ReadinessItem(
                    area="settlement", item="  Issue", status="WARN",
                    detail=issue,
                    action=issue,
                ))
        except Exception as ex:
            report.settlement_viable = False
            report.items.append(ReadinessItem(
                area="settlement", item="Settlement path resolved", status="WARN",
                detail=f"Could not resolve: {ex}",
                action="Confirm banking details for all entities.",
            ))

    def _assess_evidence(self, report: DealReadinessReport) -> None:
        if not EVIDENCE_DIR.exists():
            report.evidence_count = 0
            report.items.append(ReadinessItem(
                area="evidence", item="Evidence documents", status="WARN",
                detail="No evidence directory found.",
            ))
            return

        total_files = 0
        for sub in EVIDENCE_DIR.iterdir():
            if sub.is_dir():
                files = list(sub.glob("*"))
                total_files += len(files)

        report.evidence_count = total_files
        if total_files >= 5:
            report.items.append(ReadinessItem(
                area="evidence", item="Evidence inventory", status="PASS",
                detail=f"{total_files} document(s) on file.",
            ))
        elif total_files > 0:
            report.items.append(ReadinessItem(
                area="evidence", item="Evidence inventory", status="WARN",
                detail=f"Only {total_files} document(s). Consider adding more.",
                action="Gather additional supporting documents.",
            ))
        else:
            report.items.append(ReadinessItem(
                area="evidence", item="Evidence inventory", status="WARN",
                detail="No evidence documents found.",
            ))

    def _compile_actions(self, report: DealReadinessReport) -> None:
        for item in report.items:
            if item.status == "FAIL" and item.action:
                report.blockers.append(item.action)
            elif item.status == "WARN" and item.action:
                report.action_items.append(item.action)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, report: DealReadinessReport) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = report.deal_name.replace(" ", "_").replace(",", "").replace(".", "")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"readiness_{slug}_{ts}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path
