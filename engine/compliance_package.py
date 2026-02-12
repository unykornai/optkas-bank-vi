"""
Compliance Package Generator
=============================
One-command generation of a complete deal compliance report.

Aggregates:
  - Entity profiles
  - Settlement path analysis
  - Capital structure
  - Governance framework
  - Fund flow status
  - Jurisdiction intelligence
  - Evidence inventory
  - Risk assessment
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.schema_loader import load_entity
from engine.correspondent_banking import CorrespondentBankingEngine
from engine.capital_structure import CapitalStructureBuilder
from engine.governance_rules import GovernanceBuilder
from engine.fund_flow import FundFlowBuilder
from engine.jurisdiction_intel import JurisdictionIntelEngine


@dataclass
class EvidenceItem:
    """A document in the evidence directory."""
    filename: str
    path: str
    entity: str
    file_type: str
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "path": self.path,
            "entity": self.entity,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
        }


@dataclass
class CompliancePackage:
    """Complete compliance package for a deal."""
    deal_name: str
    generated_at: str
    entities: list[dict] = field(default_factory=list)
    settlement_path: Optional[dict] = None
    capital_structure: Optional[dict] = None
    governance: Optional[dict] = None
    fund_flow: Optional[dict] = None
    jurisdictions: list[dict] = field(default_factory=list)
    evidence_inventory: list[EvidenceItem] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    compliance_status: str = "PENDING"

    def assess_status(self) -> str:
        """Determine overall compliance status."""
        critical = 0
        warnings = 0

        # Check governance
        if self.governance:
            issues = self.governance.get("issues", [])
            critical += len(issues)

        # Check settlement
        if self.settlement_path:
            if not self.settlement_path.get("is_valid", False):
                critical += 1
            fx_reqs = self.settlement_path.get("fx_requirements", [])
            warnings += len(fx_reqs)

        # Check capital
        if self.capital_structure:
            cap_issues = self.capital_structure.get("issues", [])
            critical += len([i for i in cap_issues if "governance" in i.lower()])
            warnings += len(cap_issues)

        # Check fund flow
        if self.fund_flow:
            ff_issues = self.fund_flow.get("issues", [])
            critical += len([i for i in ff_issues if "BLOCKED" in i])
            warnings += len(ff_issues)

        # Check evidence
        if not self.evidence_inventory:
            warnings += 1
            self.risk_flags.append("No supporting documents in evidence directory")

        if critical > 0:
            self.compliance_status = "REQUIRES_ACTION"
        elif warnings > 0:
            self.compliance_status = "CONDITIONAL"
        else:
            self.compliance_status = "CLEAR"

        return self.compliance_status

    def summary(self) -> str:
        self.assess_status()

        lines = [
            "=" * 60,
            "COMPLIANCE PACKAGE",
            f"  {self.deal_name}",
            f"  Generated: {self.generated_at}",
            "=" * 60,
        ]

        # Status banner
        status_icon = {
            "CLEAR": "[CLEAR]",
            "CONDITIONAL": "[CONDITIONAL]",
            "REQUIRES_ACTION": "[ACTION REQUIRED]",
            "PENDING": "[PENDING]",
        }.get(self.compliance_status, "[?]")
        lines.append(f"\nSTATUS: {status_icon} {self.compliance_status}")

        # Entities
        lines.append(f"\n--- ENTITIES ({len(self.entities)}) ---")
        for e in self.entities:
            j = e.get("jurisdiction", "??")
            etype = e.get("entity_type", "unknown")
            lines.append(f"  {e.get('legal_name', '?')} [{j}] ({etype})")

        # Settlement
        if self.settlement_path:
            sp = self.settlement_path
            valid = "PASS" if sp.get("is_valid") else "FAIL"
            lines.append(f"\n--- SETTLEMENT PATH [{valid}] ---")
            lines.append(f"  {sp.get('originator', '?')} -> {sp.get('beneficiary', '?')}")
            lines.append(f"  Nodes: {sp.get('node_count', 0)} | FX: {'YES' if sp.get('fx_requirements') else 'NO'}")
            for note in sp.get("validation_notes", [])[:5]:
                lines.append(f"  * {note}")

        # Capital Structure
        if self.capital_structure:
            cs = self.capital_structure
            lines.append(f"\n--- CAPITAL STRUCTURE ---")
            pct = cs.get("total_committed_pct", 0)
            lines.append(f"  Allocation: {pct:.0f}% | Fully allocated: {cs.get('is_fully_allocated', False)}")
            for c in cs.get("commitments", []):
                lines.append(f"    {c['commitment_percentage']:.0f}%  {c['party_name']} ({c.get('party_type', '?')})")

        # Governance
        if self.governance:
            gov = self.governance
            lines.append(f"\n--- GOVERNANCE ---")
            lines.append(f"  Structure: {gov.get('structure', '?')}")
            lines.append(f"  Committees: {len(gov.get('committees', []))}")
            lines.append(f"  Compliant: {gov.get('is_compliant', False)}")
            for issue in gov.get("issues", []):
                lines.append(f"  [X] {issue}")

        # Fund Flow
        if self.fund_flow:
            ff = self.fund_flow
            lines.append(f"\n--- FUND FLOW ---")
            lines.append(f"  Funded: ${ff.get('total_funded', 0):,.0f} / ${ff.get('total_commitment', 0):,.0f}")
            lines.append(f"  Deployed: ${ff.get('total_deployed', 0):,.0f}")
            lines.append(f"  Outstanding: ${ff.get('total_outstanding', 0):,.0f}")

        # Jurisdictions
        if self.jurisdictions:
            lines.append(f"\n--- JURISDICTIONS ({len(self.jurisdictions)}) ---")
            for jp in self.jurisdictions:
                code = jp.get("code", "??")
                name = jp.get("name", "?")
                fatf = jp.get("fatf_status", "?")
                lines.append(f"  [{code}] {name} (FATF: {fatf})")

        # Evidence
        lines.append(f"\n--- EVIDENCE ({len(self.evidence_inventory)}) ---")
        for ev in self.evidence_inventory:
            size_kb = ev.size_bytes / 1024
            lines.append(f"  [{ev.entity}] {ev.filename} ({size_kb:.0f} KB)")

        # Risk Flags
        if self.risk_flags:
            lines.append(f"\n--- RISK FLAGS ({len(self.risk_flags)}) ---")
            for rf in self.risk_flags:
                lines.append(f"  [!] {rf}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "generated_at": self.generated_at,
            "compliance_status": self.compliance_status,
            "entities": self.entities,
            "settlement_path": self.settlement_path,
            "capital_structure": self.capital_structure,
            "governance": self.governance,
            "fund_flow": self.fund_flow,
            "jurisdictions": self.jurisdictions,
            "evidence_inventory": [e.to_dict() for e in self.evidence_inventory],
            "risk_flags": self.risk_flags,
        }


# ── Generator ───────────────────────────────────────────────────────

class CompliancePackageGenerator:
    """Generates a complete compliance package from deal data."""

    def __init__(self):
        self.banking_engine = CorrespondentBankingEngine()
        self.jurisdiction_engine = JurisdictionIntelEngine()

    def generate(
        self,
        deal_name: str,
        entity_paths: list[Path],
        cap_structure_path: Optional[Path] = None,
    ) -> CompliancePackage:
        """Generate a full compliance package."""
        package = CompliancePackage(
            deal_name=deal_name,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        # Load entities
        entities = []
        for ep in entity_paths:
            e = load_entity(ep)
            entities.append(e)
            package.entities.append({
                "legal_name": e.get("legal_name", "Unknown"),
                "jurisdiction": e.get("jurisdiction", "??"),
                "entity_type": e.get("entity_type", "unknown"),
                "swift_eligible": e.get("regulatory_status", {}).get("swift_eligible", None),
            })

        # Settlement path (if 2+ entities)
        if len(entities) >= 2:
            try:
                path = self.banking_engine.resolve_settlement_path(
                    entities[0], entities[1], "USD"
                )
                package.settlement_path = path.to_dict()
            except Exception:
                package.risk_flags.append("Settlement path could not be resolved")

        # Jurisdiction intelligence
        for e in entities:
            j_code = e.get("jurisdiction", "")[:2]
            self.jurisdiction_engine.learn_from_entity(e)
            profile = self.jurisdiction_engine.get_profile(j_code)
            if profile:
                package.jurisdictions.append({
                    "code": profile.jurisdiction_code,
                    "name": profile.jurisdiction_name,
                    "fatf_status": profile.fatf_status,
                    "region": profile.region,
                    "legal_system": profile.legal_system,
                    "deal_count": profile.deal_count,
                })

        # Capital structure
        if cap_structure_path and cap_structure_path.exists():
            cs_data = json.loads(cap_structure_path.read_text(encoding="utf-8"))
            package.capital_structure = cs_data

            # Fund flow from capital structure
            builder = FundFlowBuilder()
            ledger = builder.build_from_capital_structure(cs_data)
            package.fund_flow = ledger.to_dict()

        # Governance (build from first entity that has governance data)
        gov_builder = GovernanceBuilder()
        for e in entities:
            if e.get("governance"):
                framework = gov_builder.build_from_entity(e, deal_name)
                package.governance = framework.to_dict()
                break
        if not package.governance:
            # Build institutional template
            framework = gov_builder.build_institutional(deal_name)
            package.governance = framework.to_dict()

        # Evidence inventory
        evidence_base = Path("data/evidence")
        if evidence_base.exists():
            for entity_dir in evidence_base.iterdir():
                if entity_dir.is_dir() and not entity_dir.name.startswith("_"):
                    for doc in entity_dir.iterdir():
                        if doc.is_file() and not doc.name.startswith("."):
                            package.evidence_inventory.append(
                                EvidenceItem(
                                    filename=doc.name,
                                    path=str(doc),
                                    entity=entity_dir.name,
                                    file_type=doc.suffix.lower(),
                                    size_bytes=doc.stat().st_size,
                                )
                            )

        # Assess overall status
        package.assess_status()
        return package

    def save(self, package: CompliancePackage) -> Path:
        """Save compliance package to JSON."""
        out_dir = Path("output/compliance_packages")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = package.deal_name.replace(" ", "_").replace("/", "-")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = out_dir / f"compliance_{safe_name}_{ts}.json"
        path.write_text(json.dumps(package.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
