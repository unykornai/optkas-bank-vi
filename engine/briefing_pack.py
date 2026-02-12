"""
Executive Briefing Pack Engine
================================
Generates the complete deliverable package that OPTKAS sends to a
prospective bank partner / funding group.

This is the "tell them everything" engine. It answers:
  1.  WHO is OPTKAS?  What do they do?
  2.  WHO are the entities in the deal group?
  3.  WHERE does each entity stand right now?
  4.  WHAT is the deal structure?
  5.  HOW does the group move forward?

Output: A structured BriefingPack with multiple sections,
        each renderable as Markdown / JSON / rich console text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import (
    ROOT_DIR,
    EVIDENCE_DIR,
    load_entity,
)
from engine.deal_dashboard import DealDashboardEngine, DealDashboard
from engine.mtn_validator import MTNProgramValidator
from engine.collateral_verifier import CollateralVerifier
from engine.deal_readiness import DealReadinessEngine
from engine.deal_governance import DealGovernanceEngine
from engine.risk_scorer import CounterpartyRiskEngine
from engine.banking_resolver import BankingResolverEngine
from engine.escrow_engine import EscrowEngine
from engine.cp_resolution import CPResolutionEngine
from engine.evidence_validator import EvidenceValidator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = ROOT_DIR / "output" / "briefing_packs"

SANCTIONED_JURISDICTIONS = {"IR", "KP", "CU", "SY", "RU"}

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class EntityStanding:
    """Compliance / readiness snapshot for a single entity."""
    legal_name: str
    trade_name: str
    entity_type: str
    jurisdiction: str
    jurisdiction_risk: str          # LOW, MODERATE, HIGH, SANCTIONED
    formation_date: str | None
    directors: list[dict]
    signatories: list[dict]
    beneficial_owners: list[dict]
    banking_status: str             # COMPLETE, PARTIAL, NONE
    banking_summary: str
    swift_code: str | None
    settlement_bank: str | None
    custodian: str | None
    evidence_files: list[str]
    evidence_score: str             # STRONG, ADEQUATE, WEAK
    regulatory_notes: list[str]
    gaps: list[str]
    strengths: list[str]
    role_in_deal: str               # ISSUER, SPV, PLATFORM, INVESTOR, OTHER


@dataclass
class DealStructure:
    """Summary of the deal mechanics."""
    deal_name: str
    program_name: str
    program_size: float
    currency: str
    coupon: float | None
    maturity: str | None
    issuer: str
    spv: str
    platform: str
    investor: str
    transfer_agent: str
    escrow_agent: str
    insurance_broker: str
    insurance_amount: float | None
    cusips: list[dict]
    collateral_method: str
    settlement_method: str
    eligible_facilities: list[str]
    securities_exemptions: list[str]
    legal_opinions: list[dict]


@dataclass
class ForwardAction:
    """A single action in the forward path."""
    action_id: str
    phase: int                       # 1=Immediate, 2=Near-term, 3=Execution
    category: str                    # BANKING, LEGAL, COMPLIANCE, etc.
    description: str
    responsible: str                 # Entity or role responsible
    dependency: str | None           # What it depends on
    priority: str                    # CRITICAL, HIGH, MEDIUM
    status: str                      # NOT_STARTED, IN_PROGRESS, COMPLETE
    estimated_days: int | None


@dataclass
class ForwardPath:
    """Complete roadmap for moving the deal forward."""
    phases: list[dict]
    actions: list[ForwardAction]
    phase_1_target: str
    phase_2_target: str
    phase_3_target: str

    @property
    def total_actions(self) -> int:
        return len(self.actions)

    @property
    def completed(self) -> int:
        return sum(1 for a in self.actions if a.status == "COMPLETE")

    @property
    def critical_actions(self) -> list[ForwardAction]:
        return [a for a in self.actions if a.priority == "CRITICAL"]

    @property
    def by_phase(self) -> dict[int, list[ForwardAction]]:
        result: dict[int, list[ForwardAction]] = {}
        for a in self.actions:
            result.setdefault(a.phase, []).append(a)
        return result


@dataclass
class BriefingPack:
    """Complete executive deliverable for the funding group."""
    deal_name: str
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    # Section 1: Platform overview
    platform_overview: dict = field(default_factory=dict)
    # Section 2: Entity standings
    entity_standings: list[EntityStanding] = field(default_factory=list)
    # Section 3: Deal structure
    deal_structure: DealStructure | None = None
    # Section 4: Current dashboard
    dashboard: DealDashboard | None = None
    # Section 5: Forward path
    forward_path: ForwardPath | None = None

    def render_markdown(self) -> str:
        """Render the full briefing pack as institutional-grade Markdown."""
        lines: list[str] = []

        # ────── HEADER ──────
        lines.append("=" * 78)
        lines.append("OPTKAS SOVEREIGN CAPITAL MARKETS")
        lines.append("EXECUTIVE BRIEFING PACK")
        lines.append(f"Deal: {self.deal_name}")
        lines.append(f"Generated: {self.generated_at}")
        lines.append("=" * 78)
        lines.append("")

        # ────── 1. PLATFORM OVERVIEW ──────
        lines.append("─" * 78)
        lines.append("1. PLATFORM OVERVIEW — WHAT IS OPTKAS?")
        lines.append("─" * 78)
        po = self.platform_overview
        lines.append("")
        lines.append(f"  Legal Name:     {po.get('legal_name', 'N/A')}")
        lines.append(f"  Entity Type:    {po.get('entity_type', 'N/A')}")
        lines.append(f"  Jurisdiction:   {po.get('jurisdiction', 'N/A')}")
        lines.append(f"  Structure:      {po.get('structure', 'N/A')}")
        lines.append("")
        lines.append("  WHAT OPTKAS DOES:")
        for item in po.get("what_we_do", []):
            lines.append(f"    • {item}")
        lines.append("")
        lines.append("  WHAT OPTKAS BRINGS TO A JV:")
        for item in po.get("optkas_contributions", []):
            lines.append(f"    • {item}")
        lines.append("")
        lines.append("  WHAT THE BANK PARTNER PROVIDES:")
        for item in po.get("bank_contributions", []):
            lines.append(f"    • {item}")
        lines.append("")
        lines.append("  REVENUE MODEL:")
        for item in po.get("revenue_sources", []):
            lines.append(f"    • {item}")
        lines.append("")
        lines.append("  TECHNOLOGY STACK:")
        for item in po.get("technology", []):
            lines.append(f"    • {item}")
        lines.append("")
        lines.append("  GOVERNANCE FRAMEWORK:")
        for item in po.get("governance", []):
            lines.append(f"    • {item}")
        lines.append("")

        # ────── 2. ENTITY STANDINGS ──────
        lines.append("─" * 78)
        lines.append("2. ENTITY STANDINGS — WHERE EVERYONE STANDS")
        lines.append("─" * 78)
        lines.append("")

        for i, es in enumerate(self.entity_standings, 1):
            lines.append(f"  2.{i}  {es.legal_name}")
            lines.append(f"        Role: {es.role_in_deal}  |  Type: {es.entity_type}  |  Jurisdiction: {es.jurisdiction}")
            lines.append(f"        Jurisdiction Risk: {es.jurisdiction_risk}")
            if es.formation_date:
                lines.append(f"        Formed: {es.formation_date}")
            lines.append("")

            # Directors
            lines.append(f"        DIRECTORS ({len(es.directors)}):")
            for d in es.directors:
                lines.append(f"          • {d.get('name', 'N/A')} — {d.get('title', 'N/A')}")

            # Signatories
            lines.append(f"        SIGNATORIES ({len(es.signatories)}):")
            for s in es.signatories:
                lines.append(f"          • {s.get('name', 'N/A')} — {s.get('title', 'N/A')} (authority: {s.get('authority', s.get('can_bind_company', 'N/A'))})")

            # Beneficial Owners
            if es.beneficial_owners:
                lines.append(f"        BENEFICIAL OWNERS ({len(es.beneficial_owners)}):")
                for bo in es.beneficial_owners:
                    screened = "✓ SCREENED" if bo.get("sanctions_screened") else "✗ NOT SCREENED"
                    lines.append(f"          • {bo.get('name', 'N/A')} — {bo.get('ownership_percentage', '?')}% [{screened}]")
            lines.append("")

            # Banking
            lines.append(f"        BANKING STATUS: {es.banking_status}")
            lines.append(f"        {es.banking_summary}")
            if es.swift_code:
                lines.append(f"          SWIFT: {es.swift_code}")
            if es.settlement_bank:
                lines.append(f"          Settlement Bank: {es.settlement_bank}")
            if es.custodian:
                lines.append(f"          Custodian: {es.custodian}")
            lines.append("")

            # Evidence
            lines.append(f"        DOCUMENTARY EVIDENCE: {es.evidence_score} ({len(es.evidence_files)} file(s))")
            for ef in es.evidence_files:
                lines.append(f"          • {ef}")
            lines.append("")

            # Strengths
            if es.strengths:
                lines.append(f"        STRENGTHS:")
                for s in es.strengths:
                    lines.append(f"          [+] {s}")

            # Gaps
            if es.gaps:
                lines.append(f"        GAPS / ACTION REQUIRED:")
                for g in es.gaps:
                    lines.append(f"          [!] {g}")

            lines.append("")
            lines.append("  " + "·" * 70)
            lines.append("")

        # ────── 3. DEAL STRUCTURE ──────
        lines.append("─" * 78)
        lines.append("3. DEAL STRUCTURE — HOW IT WORKS")
        lines.append("─" * 78)
        lines.append("")
        if self.deal_structure:
            ds = self.deal_structure
            lines.append(f"  Program:           {ds.program_name}")
            lines.append(f"  Maximum Offering:  ${ds.program_size:,.0f} {ds.currency}")
            if ds.coupon is not None:
                lines.append(f"  Coupon Rate:       {ds.coupon}%")
            if ds.maturity:
                lines.append(f"  Maturity:          {ds.maturity}")
            lines.append("")
            lines.append(f"  Issuer:            {ds.issuer}")
            lines.append(f"  SPV:               {ds.spv}")
            lines.append(f"  Platform:          {ds.platform}")
            lines.append(f"  Investor:          {ds.investor}")
            lines.append(f"  Transfer Agent:    {ds.transfer_agent}")
            lines.append(f"  Escrow Agent:      {ds.escrow_agent}")
            lines.append(f"  Insurance Broker:  {ds.insurance_broker}")
            if ds.insurance_amount:
                lines.append(f"  Insurance Cover:   ${ds.insurance_amount:,.0f}")
            lines.append("")

            lines.append("  CUSIP SCHEDULE:")
            for c in ds.cusips:
                status = "OUTSTANDING" if not c.get("unissued") else "UNISSUED"
                lines.append(f"    • {c.get('id', 'N/A')} [{c.get('type', '')}] — {c.get('description', '')} ({status})")
            lines.append("")

            lines.append(f"  Collateral:        {ds.collateral_method}")
            lines.append(f"  Settlement:        {ds.settlement_method}")
            lines.append("")

            lines.append("  SECURITIES EXEMPTIONS:")
            for ex in ds.securities_exemptions:
                lines.append(f"    • {ex}")
            lines.append("")

            lines.append("  ELIGIBLE FACILITY TYPES:")
            for ef in ds.eligible_facilities:
                lines.append(f"    • {ef}")
            lines.append("")

            lines.append("  LEGAL OPINIONS:")
            for lo in ds.legal_opinions:
                status_tag = f" [{lo.get('status', 'FINAL')}]" if lo.get("status") else ""
                lines.append(f"    • {lo.get('title', 'N/A')} — {lo.get('counsel', 'N/A')}{status_tag}")
                if lo.get("key_opinions"):
                    for ko in lo["key_opinions"][:3]:
                        lines.append(f"        → {ko}")
            lines.append("")

        # ────── 4. CURRENT DASHBOARD ──────
        lines.append("─" * 78)
        lines.append("4. CURRENT STATUS — DEAL DASHBOARD")
        lines.append("─" * 78)
        lines.append("")
        if self.dashboard:
            lines.append(self.dashboard.summary())
        lines.append("")

        # ────── 5. FORWARD PATH ──────
        lines.append("─" * 78)
        lines.append("5. FORWARD PATH — HOW THE GROUP MOVES FORWARD")
        lines.append("─" * 78)
        lines.append("")
        if self.forward_path:
            fp = self.forward_path
            lines.append(f"  Total Actions:     {fp.total_actions}")
            lines.append(f"  Completed:         {fp.completed}")
            lines.append(f"  Critical Actions:  {len(fp.critical_actions)}")
            lines.append("")

            for phase_num in sorted(fp.by_phase.keys()):
                phase_actions = fp.by_phase[phase_num]
                phase_info = fp.phases[phase_num - 1] if phase_num <= len(fp.phases) else {}
                lines.append(f"  ═══ PHASE {phase_num}: {phase_info.get('name', '')} ═══")
                lines.append(f"      Target: {phase_info.get('target', '')}")
                lines.append(f"      Timeline: {phase_info.get('timeline', '')}")
                lines.append("")

                for a in phase_actions:
                    status_icon = {"COMPLETE": "[✓]", "IN_PROGRESS": "[~]", "NOT_STARTED": "[ ]"}.get(a.status, "[ ]")
                    lines.append(f"      {status_icon} [{a.priority}] {a.description}")
                    lines.append(f"            Category: {a.category}  |  Responsible: {a.responsible}")
                    if a.dependency:
                        lines.append(f"            Depends on: {a.dependency}")
                    if a.estimated_days:
                        lines.append(f"            Est. time: {a.estimated_days} business days")
                    lines.append("")

                lines.append("")

        lines.append("=" * 78)
        lines.append("END OF BRIEFING PACK")
        lines.append("=" * 78)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "generated_at": self.generated_at,
            "platform_overview": self.platform_overview,
            "entity_standings": [
                {
                    "legal_name": es.legal_name,
                    "trade_name": es.trade_name,
                    "entity_type": es.entity_type,
                    "jurisdiction": es.jurisdiction,
                    "jurisdiction_risk": es.jurisdiction_risk,
                    "formation_date": es.formation_date,
                    "directors": es.directors,
                    "signatories": es.signatories,
                    "beneficial_owners": es.beneficial_owners,
                    "banking_status": es.banking_status,
                    "banking_summary": es.banking_summary,
                    "swift_code": es.swift_code,
                    "settlement_bank": es.settlement_bank,
                    "custodian": es.custodian,
                    "evidence_files": es.evidence_files,
                    "evidence_score": es.evidence_score,
                    "regulatory_notes": es.regulatory_notes,
                    "gaps": es.gaps,
                    "strengths": es.strengths,
                    "role_in_deal": es.role_in_deal,
                }
                for es in self.entity_standings
            ],
            "deal_structure": {
                "deal_name": self.deal_structure.deal_name,
                "program_name": self.deal_structure.program_name,
                "program_size": self.deal_structure.program_size,
                "currency": self.deal_structure.currency,
                "coupon": self.deal_structure.coupon,
                "maturity": self.deal_structure.maturity,
                "issuer": self.deal_structure.issuer,
                "spv": self.deal_structure.spv,
                "platform": self.deal_structure.platform,
                "investor": self.deal_structure.investor,
                "cusips": self.deal_structure.cusips,
                "eligible_facilities": self.deal_structure.eligible_facilities,
                "legal_opinions": self.deal_structure.legal_opinions,
            } if self.deal_structure else None,
            "dashboard": self.dashboard.to_dict() if self.dashboard else None,
            "forward_path": {
                "phases": self.forward_path.phases,
                "total_actions": self.forward_path.total_actions,
                "completed": self.forward_path.completed,
                "critical_actions": len(self.forward_path.critical_actions),
                "actions": [
                    {
                        "action_id": a.action_id,
                        "phase": a.phase,
                        "category": a.category,
                        "description": a.description,
                        "responsible": a.responsible,
                        "dependency": a.dependency,
                        "priority": a.priority,
                        "status": a.status,
                        "estimated_days": a.estimated_days,
                    }
                    for a in self.forward_path.actions
                ],
            } if self.forward_path else None,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BriefingPackEngine:
    """
    Builds the complete executive briefing pack.

    Usage:
        engine = BriefingPackEngine()
        pack = engine.build(
            deal_name="OPTKAS-TC Full Deal",
            issuer_path=Path("data/entities/tc_advantage_traders.yaml"),
            spv_path=Path("data/entities/optkas1_spv.yaml"),
            platform_path=Path("data/entities/optkas_platform.yaml"),
            investor_path=Path("data/entities/querubin_usa.yaml"),
        )
        print(pack.render_markdown())
    """

    def build(
        self,
        deal_name: str,
        issuer_path: Path | None = None,
        spv_path: Path | None = None,
        platform_path: Path | None = None,
        investor_path: Path | None = None,
        additional_entities: list[Path] | None = None,
    ) -> BriefingPack:
        """Build the complete briefing pack."""
        pack = BriefingPack(deal_name=deal_name)

        # Collect all paths
        all_paths: list[Path] = []
        role_map: dict[str, str] = {}
        if issuer_path:
            all_paths.append(issuer_path)
            role_map[str(issuer_path)] = "ISSUER"
        if spv_path:
            all_paths.append(spv_path)
            role_map[str(spv_path)] = "SPV"
        if platform_path:
            all_paths.append(platform_path)
            role_map[str(platform_path)] = "PLATFORM"
        if investor_path:
            all_paths.append(investor_path)
            role_map[str(investor_path)] = "INVESTOR"
        for ep in (additional_entities or []):
            if ep not in all_paths:
                all_paths.append(ep)
                role_map.setdefault(str(ep), "PARTICIPANT")

        # 1. Platform overview
        pack.platform_overview = self._build_platform_overview(platform_path)

        # 2. Entity standings
        for ep in all_paths:
            role = role_map.get(str(ep), "PARTICIPANT")
            standing = self._build_entity_standing(ep, role)
            pack.entity_standings.append(standing)

        # 3. Deal structure
        pack.deal_structure = self._build_deal_structure(
            deal_name, issuer_path, spv_path, platform_path, investor_path
        )

        # 4. Live dashboard
        extra = [p for p in all_paths if p not in [issuer_path, spv_path]]
        dashboard_engine = DealDashboardEngine()
        pack.dashboard = dashboard_engine.generate(
            deal_name=deal_name,
            issuer_path=issuer_path,
            spv_path=spv_path,
            additional_entities=extra if extra else None,
        )

        # 5. Forward path
        pack.forward_path = self._build_forward_path(pack)

        return pack

    # ------------------------------------------------------------------
    # 1. Platform overview
    # ------------------------------------------------------------------

    def _build_platform_overview(self, platform_path: Path | None) -> dict:
        """Build the 'What is OPTKAS' section."""
        if not platform_path:
            return {"legal_name": "OPTKAS Sovereign Platform", "note": "No entity file provided"}

        try:
            entity = load_entity(platform_path)
        except Exception:
            return {"legal_name": "OPTKAS Sovereign Platform", "note": "Could not load entity"}

        jv = entity.get("jv_structure", {})
        bond = entity.get("bond_program", {})
        tech = entity.get("technology", {})
        gov = entity.get("governance", {})
        reg = entity.get("regulatory_status", {})

        return {
            "legal_name": entity.get("legal_name", "OPTKAS"),
            "trade_name": entity.get("trade_name", "OPTKAS"),
            "entity_type": entity.get("entity_type", "sovereign_platform"),
            "jurisdiction": entity.get("jurisdiction", "US"),
            "structure": "Sovereign-grade capital markets infrastructure platform with bank JV model",
            "what_we_do": [
                f"${bond.get('size', 0) / 1e6:.0f}M bond-backed lending program",
                "Sovereign SPV + trust structure for institutional collateral",
                "Tokenization, attestation, and issuance infrastructure",
                "Reserve Vault + Borrowing Base analytics (XRPL-based)",
                "Automated compliance, risk, and deal execution engines",
                "Institutional-grade reporting and audit trails",
                "Escrow-based settlement with GSIB-grade banking partners",
            ] + (reg.get("notes", [])[:2]),
            "optkas_contributions": jv.get("optkas_contributions", []),
            "bank_contributions": jv.get("bank_contributions", []),
            "revenue_sources": jv.get("revenue_model", {}).get("sources", []),
            "revenue_split": jv.get("revenue_model", {}).get("split", "50/50"),
            "bond_program_size": bond.get("size", 0),
            "bond_currency": bond.get("currency", "USD"),
            "securities_compliance": bond.get("securities_compliance", []),
            "asset_classes": entity.get("asset_classes", []),
            "technology": [
                f"Blockchain: {', '.join(tech.get('blockchain_layer', []))} (evidence only — non-custodial)",
                f"Security: {', '.join(tech.get('security', [])[:3])}",
                f"Data protection: {', '.join(tech.get('data_protection', [])[:2])}",
            ],
            "governance": [
                f"Structure: {gov.get('structure', 'dual_signature')}",
            ] + [
                f"Committee: {c.get('name', '')} — {c.get('scope', '')}"
                for c in gov.get("committees", [])
            ] + gov.get("controls", [])[:3],
        }

    # ------------------------------------------------------------------
    # 2. Entity standing
    # ------------------------------------------------------------------

    def _build_entity_standing(
        self, entity_path: Path, role: str,
    ) -> EntityStanding:
        """Build standing report for one entity."""
        try:
            entity = load_entity(entity_path)
        except Exception as exc:
            return EntityStanding(
                legal_name=str(entity_path),
                trade_name="",
                entity_type="unknown",
                jurisdiction="unknown",
                jurisdiction_risk="UNKNOWN",
                formation_date=None,
                directors=[],
                signatories=[],
                beneficial_owners=[],
                banking_status="UNKNOWN",
                banking_summary=f"Error loading entity: {exc}",
                swift_code=None,
                settlement_bank=None,
                custodian=None,
                evidence_files=[],
                evidence_score="UNKNOWN",
                regulatory_notes=[],
                gaps=[f"Cannot load entity: {exc}"],
                strengths=[],
                role_in_deal=role,
            )

        legal_name = entity.get("legal_name", "Unknown")
        trade_name = entity.get("trade_name", legal_name)
        jurisdiction = entity.get("jurisdiction", "")

        # Jurisdiction risk
        if jurisdiction.split("-")[0] in SANCTIONED_JURISDICTIONS:
            jur_risk = "SANCTIONED"
        elif jurisdiction.split("-")[0] in {"BS", "KY", "VG", "PA", "BZ"}:
            jur_risk = "MODERATE"
        else:
            jur_risk = "LOW"

        # Banking assessment
        banking = entity.get("banking", {})
        swift = banking.get("swift_code")
        settlement_bank = banking.get("settlement_bank")
        custodian = banking.get("custodian")
        has_swift = bool(swift)
        has_bank = bool(settlement_bank)
        has_custodian = bool(custodian)

        if has_swift and has_bank:
            banking_status = "COMPLETE"
            banking_summary = f"Full banking: {settlement_bank} [{swift}]"
        elif has_custodian or has_bank:
            banking_status = "PARTIAL"
            parts = []
            if has_bank:
                parts.append(f"Bank: {settlement_bank}")
            if has_custodian:
                parts.append(f"Custodian: {custodian}")
            if not has_swift:
                parts.append("Missing SWIFT — uses partner bank")
            banking_summary = "; ".join(parts)
        else:
            banking_status = "NONE"
            notes = banking.get("notes", [])
            banking_summary = notes[0] if notes else "No banking information on file"

        # Evidence
        evidence_files = self._find_evidence(trade_name, legal_name)
        if len(evidence_files) >= 3:
            evidence_score = "STRONG"
        elif len(evidence_files) >= 1:
            evidence_score = "ADEQUATE"
        else:
            evidence_score = "WEAK"

        # Regulatory
        reg = entity.get("regulatory_status", {})
        reg_notes = reg.get("notes", [])

        # Strengths & gaps
        strengths = []
        gaps = []

        # Directors/signatories analysis
        directors = entity.get("directors", [])
        signatories = entity.get("signatories", [])
        bos = entity.get("beneficial_owners", [])

        if len(signatories) >= 2:
            strengths.append(f"Dual signatory authority ({len(signatories)} signatories)")
        elif len(signatories) == 1:
            strengths.append("Single authorized signatory on file")
        else:
            gaps.append("No signatories documented")

        if len(directors) >= 1:
            strengths.append(f"{len(directors)} director(s) documented")
        else:
            gaps.append("No directors documented")

        # BO screening
        unscreened = [bo for bo in bos if not bo.get("sanctions_screened")]
        if bos and not unscreened:
            strengths.append("All beneficial owners sanctions-screened")
        elif unscreened:
            for bo in unscreened:
                gaps.append(f"BO {bo.get('name', 'N/A')} not sanctions-screened")

        # Banking gaps
        if banking_status == "NONE":
            gaps.append("No banking rails established — requires JV bank partner or direct onboarding")
        elif banking_status == "PARTIAL" and not has_swift:
            gaps.append("No SWIFT code — settlement requires partner bank relay")

        # Evidence gaps
        if evidence_score == "WEAK":
            gaps.append("Insufficient documentary evidence on file")

        # MTN / collateral strengths
        mtn = entity.get("mtn_program")
        if mtn:
            strengths.append(
                f"MTN Program: {mtn.get('program_name', '')} "
                f"(${mtn.get('max_offering', 0) / 1e9:.0f}B max)"
            )
        collateral = entity.get("collateral_holdings")
        if collateral:
            strengths.append(f"Collateral: {collateral.get('instrument', '')} via {collateral.get('perfection', 'N/A')}")

        # Insurance
        insurance = entity.get("insurance", {})
        if insurance.get("coverage"):
            cov = insurance["coverage"]
            strengths.append(f"Insurance: ${cov.get('sum_insured', 0) / 1e6:.0f}M at Lloyd's of London")

        # Legal opinions
        opinions = entity.get("legal_opinions", [])
        for op in opinions:
            status = op.get("status", "FINAL")
            if status == "DRAFT":
                gaps.append(f"Legal opinion from {op.get('counsel', 'N/A')} still in DRAFT")
            else:
                strengths.append(f"Legal opinion: {op.get('counsel', 'N/A')} [{op.get('jurisdiction', '')}]")

        # SPV features
        spv_chars = reg.get("spv_characteristics", [])
        if spv_chars:
            strengths.append(f"SPV characteristics: {', '.join(spv_chars[:3])}")

        # XRPL
        xrpl = entity.get("xrpl_reserve_system")
        if xrpl:
            strengths.append(f"Reserve system: {xrpl.get('name', 'XRPL')} with proof-of-reserves")

        # JV structure
        jv = entity.get("jv_structure")
        if jv:
            strengths.append(f"JV model: {jv.get('ownership_split', '')} with bank partner")

        return EntityStanding(
            legal_name=legal_name,
            trade_name=trade_name,
            entity_type=entity.get("entity_type", "unknown"),
            jurisdiction=jurisdiction,
            jurisdiction_risk=jur_risk,
            formation_date=entity.get("formation_date"),
            directors=directors,
            signatories=signatories,
            beneficial_owners=bos,
            banking_status=banking_status,
            banking_summary=banking_summary,
            swift_code=swift,
            settlement_bank=settlement_bank,
            custodian=custodian,
            evidence_files=evidence_files,
            evidence_score=evidence_score,
            regulatory_notes=reg_notes,
            gaps=gaps,
            strengths=strengths,
            role_in_deal=role,
        )

    def _find_evidence(self, trade_name: str, legal_name: str) -> list[str]:
        """Find evidence files for an entity in the vault."""
        evidence_files: list[str] = []
        # Guess directory names from entity names
        candidates = [
            trade_name.lower().replace(" ", "_").replace(",", "").replace(".", ""),
            legal_name.lower().replace(" ", "_").replace(",", "").replace(".", ""),
        ]
        # Also try short forms
        for name in [trade_name, legal_name]:
            parts = name.lower().split()
            if parts:
                candidates.append(parts[0])
                if len(parts) >= 2:
                    candidates.append("_".join(parts[:2]))

        for candidate in candidates:
            edir = EVIDENCE_DIR / candidate
            if edir.exists() and edir.is_dir():
                for f in edir.iterdir():
                    if f.is_file() and f.name != ".gitkeep":
                        evidence_files.append(f.name)
                if evidence_files:
                    break

        return evidence_files

    # ------------------------------------------------------------------
    # 3. Deal structure
    # ------------------------------------------------------------------

    def _build_deal_structure(
        self,
        deal_name: str,
        issuer_path: Path | None,
        spv_path: Path | None,
        platform_path: Path | None,
        investor_path: Path | None,
    ) -> DealStructure | None:
        """Build the deal structure from entity data."""
        issuer = load_entity(issuer_path) if issuer_path else {}
        spv = load_entity(spv_path) if spv_path else {}
        platform = load_entity(platform_path) if platform_path else {}
        investor = load_entity(investor_path) if investor_path else {}

        mtn = issuer.get("mtn_program", {})
        insurance = issuer.get("insurance", {})
        opinions = issuer.get("legal_opinions", [])
        collateral = spv.get("collateral_holdings", {})
        stc = mtn.get("transfer_agent", {})

        return DealStructure(
            deal_name=deal_name,
            program_name=mtn.get("program_name", "N/A"),
            program_size=mtn.get("max_offering", 0),
            currency=mtn.get("currency", "USD"),
            coupon=mtn.get("coupon_rate"),
            maturity=mtn.get("maturity_date"),
            issuer=issuer.get("legal_name", "N/A"),
            spv=spv.get("legal_name", "N/A"),
            platform=platform.get("legal_name", "N/A"),
            investor=investor.get("legal_name", "N/A"),
            transfer_agent=stc.get("name", "Securities Transfer Corporation"),
            escrow_agent="Securities Transfer Corporation",
            insurance_broker=insurance.get("broker", {}).get("name", "N/A"),
            insurance_amount=insurance.get("coverage", {}).get("sum_insured"),
            cusips=mtn.get("cusips", []),
            collateral_method=collateral.get("perfection", "UCC filing + custodial control"),
            settlement_method=mtn.get("settlement_method", "DTC/DWAC FAST"),
            eligible_facilities=[
                f.get("type", "") for f in spv.get("eligible_facilities", [])
            ],
            securities_exemptions=issuer.get("regulatory_status", {}).get(
                "securities_exemptions", []
            ),
            legal_opinions=[
                {
                    "title": op.get("title", ""),
                    "counsel": op.get("counsel", ""),
                    "jurisdiction": op.get("jurisdiction", ""),
                    "status": op.get("status"),
                    "key_opinions": op.get("key_opinions", []),
                }
                for op in opinions
            ],
        )

    # ------------------------------------------------------------------
    # 5. Forward path
    # ------------------------------------------------------------------

    def _build_forward_path(self, pack: BriefingPack) -> ForwardPath:
        """Build actionable forward path from current state."""
        actions: list[ForwardAction] = []
        action_id = 0

        # Phase definitions
        phases = [
            {
                "name": "IMMEDIATE — Documentation & Compliance",
                "target": "Close all documentation gaps and achieve full compliance readiness",
                "timeline": "1-2 weeks",
            },
            {
                "name": "NEAR-TERM — Banking & Legal",
                "target": "Establish all banking rails and finalize legal opinions",
                "timeline": "2-4 weeks",
            },
            {
                "name": "EXECUTION — Deal Close",
                "target": "Execute signing, fund escrow, and close deal",
                "timeline": "4-8 weeks",
            },
        ]

        # Analyze entity standings for gaps
        for es in pack.entity_standings:
            # BO screening gaps
            for bo in es.beneficial_owners:
                if not bo.get("sanctions_screened"):
                    action_id += 1
                    actions.append(ForwardAction(
                        action_id=f"FP-{action_id:03d}",
                        phase=1,
                        category="COMPLIANCE",
                        description=f"Complete sanctions screening for {bo.get('name', 'N/A')} ({es.legal_name})",
                        responsible=es.legal_name,
                        dependency=None,
                        priority="CRITICAL",
                        status="NOT_STARTED",
                        estimated_days=3,
                    ))

            # Banking gaps
            if es.banking_status == "NONE":
                action_id += 1
                actions.append(ForwardAction(
                    action_id=f"FP-{action_id:03d}",
                    phase=2,
                    category="BANKING",
                    description=f"Establish banking relationship for {es.legal_name}",
                    responsible=es.legal_name,
                    dependency="JV bank partner selection",
                    priority="CRITICAL",
                    status="NOT_STARTED",
                    estimated_days=15,
                ))
            elif es.banking_status == "PARTIAL" and not es.swift_code:
                action_id += 1
                actions.append(ForwardAction(
                    action_id=f"FP-{action_id:03d}",
                    phase=2,
                    category="BANKING",
                    description=f"Obtain SWIFT-capable settlement account for {es.legal_name}",
                    responsible=es.legal_name,
                    dependency=None,
                    priority="HIGH",
                    status="NOT_STARTED",
                    estimated_days=10,
                ))

            # Evidence gaps
            if es.evidence_score == "WEAK":
                action_id += 1
                actions.append(ForwardAction(
                    action_id=f"FP-{action_id:03d}",
                    phase=1,
                    category="DOCUMENTATION",
                    description=f"Collect and file documentary evidence for {es.legal_name}",
                    responsible=es.legal_name,
                    dependency=None,
                    priority="HIGH",
                    status="NOT_STARTED",
                    estimated_days=5,
                ))

            # Legal opinion gaps
            for gap in es.gaps:
                if "DRAFT" in gap and "opinion" in gap.lower():
                    action_id += 1
                    actions.append(ForwardAction(
                        action_id=f"FP-{action_id:03d}",
                        phase=2,
                        category="LEGAL",
                        description=f"Finalize draft legal opinion: {gap}",
                        responsible="Legal Counsel",
                        dependency=None,
                        priority="HIGH",
                        status="IN_PROGRESS",
                        estimated_days=10,
                    ))

        # Dashboard-driven actions
        if pack.dashboard:
            for section in pack.dashboard.sections:
                if section.rag == "AMBER":
                    for ai in section.action_items[:2]:
                        action_id += 1
                        # Determine phase based on category
                        cat = section.name.upper()
                        if cat in ("RISK SCORE", "DEAL READINESS"):
                            phase = 1
                        elif cat in ("CLOSING CONDITIONS", "CP RESOLUTION", "ESCROW"):
                            phase = 3
                        else:
                            phase = 2
                        actions.append(ForwardAction(
                            action_id=f"FP-{action_id:03d}",
                            phase=phase,
                            category=cat,
                            description=ai,
                            responsible="Deal Team",
                            dependency=None,
                            priority="MEDIUM",
                            status="NOT_STARTED",
                            estimated_days=7,
                        ))

        # Standard phase 3 actions (always present)
        phase_3_standard = [
            ("EXECUTION", "Execute signing ceremony with dual-signature authority validation", "Deal Team", "CRITICAL"),
            ("ESCROW", "Fund escrow account with confirmed bank partner", "Investor / Bank Partner", "CRITICAL"),
            ("SETTLEMENT", "Complete settlement via DTC/DWAC FAST system", "Transfer Agent (STC)", "CRITICAL"),
            ("CLOSING", "Satisfy all remaining conditions precedent and close", "Legal Counsel", "HIGH"),
        ]
        for cat, desc, resp, pri in phase_3_standard:
            action_id += 1
            actions.append(ForwardAction(
                action_id=f"FP-{action_id:03d}",
                phase=3,
                category=cat,
                description=desc,
                responsible=resp,
                dependency="Phase 1 & 2 completion",
                priority=pri,
                status="NOT_STARTED",
                estimated_days=5,
            ))

        # Mark completed actions from dashboard
        if pack.dashboard:
            green_sections = {
                s.name.lower() for s in pack.dashboard.sections if s.rag == "GREEN"
            }
            for a in actions:
                if a.category.lower() in green_sections:
                    a.status = "COMPLETE"
                elif a.category == "COMPLIANCE" and "collateral" in green_sections:
                    pass  # Don't auto-complete compliance based on collateral

        return ForwardPath(
            phases=phases,
            actions=actions,
            phase_1_target="Full compliance readiness — all BOs screened, all evidence filed, all entity data complete",
            phase_2_target="Banking rails live — SWIFT accounts open, escrow agent engaged, legal opinions final",
            phase_3_target="Deal execution — signing, funding, settlement, and closing",
        )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, pack: BriefingPack) -> Path:
        """Save briefing pack to JSON + Markdown."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = pack.deal_name.replace(" ", "_").replace("/", "-")

        # JSON
        json_path = OUTPUT_DIR / f"briefing_{name}_{ts}.json"
        json_path.write_text(
            json.dumps(pack.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        # Markdown
        md_path = OUTPUT_DIR / f"briefing_{name}_{ts}.md"
        md_path.write_text(pack.render_markdown(), encoding="utf-8")

        return json_path
