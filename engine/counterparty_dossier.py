"""
Counterparty Risk Dossier
==========================
Builds a structured intelligence profile for any entity in the system.

This is not a compliance check. This is a counterparty assessment.
Banks build dossiers before they extend credit.
Institutional counterparties build dossiers before they sign.

A dossier aggregates:
  - Entity profile (jurisdiction, type, formation, directors, owners)
  - Regulatory posture (licenses, regulatory status, claims vs evidence)
  - Signatory authority map
  - Evidence coverage score
  - Red flag profile
  - Deal classification history (if available)
  - Risk rating

Dossiers persist. Each entity gets one. Updated on every interaction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import (
    ROOT_DIR,
    get_jurisdiction_full_name,
)
from engine.validator import ComplianceValidator
from engine.red_flags import RedFlagDetector
from engine.evidence_validator import EvidenceValidator
from engine.regulatory_validator import RegulatoryClaimValidator
from engine._icons import ICON_CHECK, ICON_CROSS, ICON_WARN, ICON_ALERT


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOSSIER_DIR = ROOT_DIR / "output" / "dossiers"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class RiskRating:
    """Quantified counterparty risk assessment."""
    regulatory_score: int = 0   # 0-25
    evidence_score: int = 0     # 0-25
    governance_score: int = 0   # 0-25
    red_flag_score: int = 0     # 0-25

    @property
    def total(self) -> int:
        return self.regulatory_score + self.evidence_score + self.governance_score + self.red_flag_score

    @property
    def grade(self) -> str:
        t = self.total
        if t >= 85:
            return "A"
        if t >= 70:
            return "B"
        if t >= 50:
            return "C"
        if t >= 30:
            return "D"
        return "F"

    def to_dict(self) -> dict[str, Any]:
        return {
            "regulatory": self.regulatory_score,
            "evidence": self.evidence_score,
            "governance": self.governance_score,
            "red_flags": self.red_flag_score,
            "total": self.total,
            "grade": self.grade,
        }


@dataclass
class CounterpartyDossier:
    """Complete counterparty intelligence profile."""
    legal_name: str
    jurisdiction: str
    jurisdiction_full: str
    entity_type: str
    formation_date: str
    generated_at: str = ""

    # Profile sections
    registration: dict[str, Any] = field(default_factory=dict)
    regulatory_posture: dict[str, Any] = field(default_factory=dict)
    signatory_map: list[dict[str, Any]] = field(default_factory=list)
    director_map: list[dict[str, Any]] = field(default_factory=list)
    ownership_structure: list[dict[str, Any]] = field(default_factory=list)
    banking_profile: dict[str, Any] = field(default_factory=dict)
    evidence_coverage: dict[str, Any] = field(default_factory=dict)
    red_flag_profile: list[dict[str, Any]] = field(default_factory=list)
    compliance_summary: dict[str, Any] = field(default_factory=dict)
    risk_rating: RiskRating = field(default_factory=RiskRating)

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def render(self) -> str:
        lines = [
            "=" * 70,
            "COUNTERPARTY RISK DOSSIER -- CONFIDENTIAL",
            "=" * 70,
            "",
            f"Entity:         {self.legal_name}",
            f"Jurisdiction:   {self.jurisdiction} ({self.jurisdiction_full})",
            f"Type:           {self.entity_type}",
            f"Formed:         {self.formation_date}",
            f"Generated:      {self.generated_at}",
            f"Risk Grade:     {self.risk_rating.grade} ({self.risk_rating.total}/100)",
            "",
            "-" * 70,
        ]

        # Registration
        lines.append("")
        lines.append("1. REGISTRATION & IDENTIFICATION")
        lines.append("-" * 40)
        for k, v in self.registration.items():
            lines.append(f"  {k}: {v}")

        # Regulatory posture
        lines.append("")
        lines.append("2. REGULATORY POSTURE")
        lines.append("-" * 40)
        for k, v in self.regulatory_posture.items():
            if isinstance(v, list):
                lines.append(f"  {k}:")
                for item in v:
                    lines.append(f"    - {item}")
            else:
                status_icon = ICON_CHECK if v else ICON_CROSS
                lines.append(f"  {status_icon} {k}: {v}")

        # Signatory authority
        lines.append("")
        lines.append("3. SIGNATORY AUTHORITY MAP")
        lines.append("-" * 40)
        for sig in self.signatory_map:
            powers = []
            if sig.get("can_bind"): powers.append("BIND")
            if sig.get("can_funds"): powers.append("FUNDS")
            if sig.get("can_pledge"): powers.append("PLEDGE")
            lines.append(f"  {sig.get('name', '?')} [{sig.get('title', '?')}]")
            lines.append(f"    Powers: {', '.join(powers) if powers else 'NONE'}")

        # Directors
        lines.append("")
        lines.append("4. DIRECTOR BOARD")
        lines.append("-" * 40)
        for d in self.director_map:
            pep = f" [PEP]" if d.get("pep") else ""
            lines.append(f"  {d.get('name', '?')}{pep}")
            lines.append(f"    Authority: {d.get('authority', '?')} | Nationality: {d.get('nationality', '?')}")

        # Ownership
        lines.append("")
        lines.append("5. BENEFICIAL OWNERSHIP")
        lines.append("-" * 40)
        for o in self.ownership_structure:
            sanctions = f" {ICON_CHECK} screened" if o.get("sanctions_screened") else f" {ICON_ALERT} NOT screened"
            pep = " [PEP]" if o.get("pep") else ""
            lines.append(f"  {o.get('name', '?')} -- {o.get('percentage', '?')}%{pep}{sanctions}")

        # Banking
        lines.append("")
        lines.append("6. BANKING PROFILE")
        lines.append("-" * 40)
        for k, v in self.banking_profile.items():
            lines.append(f"  {k}: {v}")

        # Evidence
        lines.append("")
        lines.append("7. EVIDENCE COVERAGE")
        lines.append("-" * 40)
        lines.append(f"  Files on record: {self.evidence_coverage.get('files_count', 0)}")
        lines.append(f"  Gaps: {self.evidence_coverage.get('gap_count', 0)}")
        lines.append(f"  Critical gaps: {self.evidence_coverage.get('critical_gaps', 0)}")

        # Red flags
        lines.append("")
        lines.append("8. RED FLAG PROFILE")
        lines.append("-" * 40)
        if self.red_flag_profile:
            for rf in self.red_flag_profile:
                lines.append(f"  [{rf.get('severity', '?')}] {rf.get('category', '?')}")
                lines.append(f"    {rf.get('description', '')}")
        else:
            lines.append(f"  {ICON_CHECK} No red flags detected.")

        # Compliance
        lines.append("")
        lines.append("9. COMPLIANCE SUMMARY")
        lines.append("-" * 40)
        lines.append(f"  Compliance Score: {self.compliance_summary.get('score', 'N/A')}/100")
        lines.append(f"  Errors: {self.compliance_summary.get('errors', 0)}")
        lines.append(f"  Warnings: {self.compliance_summary.get('warnings', 0)}")

        # Risk rating
        lines.append("")
        lines.append("10. RISK RATING")
        lines.append("-" * 40)
        lines.append(f"  Regulatory:  {self.risk_rating.regulatory_score}/25")
        lines.append(f"  Evidence:    {self.risk_rating.evidence_score}/25")
        lines.append(f"  Governance:  {self.risk_rating.governance_score}/25")
        lines.append(f"  Red Flags:   {self.risk_rating.red_flag_score}/25")
        lines.append(f"  TOTAL:       {self.risk_rating.total}/100  (Grade: {self.risk_rating.grade})")

        lines.append("")
        lines.append("=" * 70)
        lines.append(f"END OF DOSSIER -- {self.generated_at}")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "legal_name": self.legal_name,
            "jurisdiction": self.jurisdiction,
            "entity_type": self.entity_type,
            "formation_date": self.formation_date,
            "generated_at": self.generated_at,
            "registration": self.registration,
            "regulatory_posture": self.regulatory_posture,
            "signatory_map": self.signatory_map,
            "director_map": self.director_map,
            "ownership_structure": self.ownership_structure,
            "banking_profile": self.banking_profile,
            "evidence_coverage": self.evidence_coverage,
            "red_flag_profile": self.red_flag_profile,
            "compliance_summary": self.compliance_summary,
            "risk_rating": self.risk_rating.to_dict(),
        }

    def save(self, directory: Path | None = None) -> Path:
        """Persist dossier to disk as JSON."""
        out_dir = directory or DOSSIER_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = self.legal_name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        path = out_dir / f"dossier_{slug}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str, ensure_ascii=False)
        return path


# ---------------------------------------------------------------------------
# Dossier Builder
# ---------------------------------------------------------------------------

class DossierBuilder:
    """
    Builds a complete counterparty risk dossier from entity data.
    """

    def __init__(self) -> None:
        self.validator = ComplianceValidator()
        self.red_flag_detector = RedFlagDetector()
        self.evidence_validator = EvidenceValidator()
        self.regulatory_validator = RegulatoryClaimValidator()

    def build(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any] | None = None,
        transaction_type: str | None = None,
    ) -> CounterpartyDossier:
        """Build a complete dossier for the given entity."""

        jur = entity.get("jurisdiction", "")
        base_jur = jur.split("-")[0].upper()

        dossier = CounterpartyDossier(
            legal_name=entity.get("legal_name", "UNKNOWN"),
            jurisdiction=jur,
            jurisdiction_full=get_jurisdiction_full_name(jur) if jur else "Unknown",
            entity_type=entity.get("entity_type", "unknown"),
            formation_date=entity.get("formation_date", "unknown"),
        )

        # 1. Registration
        dossier.registration = {
            "registration_number": entity.get("registration_number", "N/A"),
            "ein": entity.get("ein", "N/A"),
            "lei": entity.get("lei", "N/A"),
            "trade_name": entity.get("trade_name", "N/A"),
        }

        # 2. Regulatory posture
        rs = entity.get("regulatory_status", {})
        licenses = entity.get("licenses", [])
        dossier.regulatory_posture = {
            "is_bank": rs.get("is_bank", False),
            "is_broker_dealer": rs.get("is_broker_dealer", False),
            "is_ria": rs.get("is_ria", False),
            "is_fund": rs.get("is_fund", False),
            "is_insurance_company": rs.get("is_insurance_company", False),
            "is_money_services_business": rs.get("is_money_services_business", False),
            "is_government_entity": rs.get("is_government_entity", False),
            "licenses": [
                f"{lic.get('license_type', '?')} ({lic.get('regulator', '?')}) #{lic.get('license_number', '?')} [{lic.get('status', 'unknown')}]"
                for lic in licenses
            ],
            "license_count": len(licenses),
        }

        # 3. Signatory authority
        for sig in entity.get("signatories", []):
            dossier.signatory_map.append({
                "name": sig.get("name", "?"),
                "title": sig.get("title", "?"),
                "can_bind": sig.get("can_bind_company", False),
                "can_funds": sig.get("can_move_funds", False),
                "can_pledge": sig.get("can_pledge_assets", False),
            })

        # 4. Directors
        for d in entity.get("directors", []):
            dossier.director_map.append({
                "name": d.get("name", "?"),
                "authority": d.get("authority_level", "?"),
                "nationality": d.get("nationality", "?"),
                "pep": d.get("pep_status", False),
            })

        # 5. Ownership
        for o in entity.get("beneficial_owners", []):
            dossier.ownership_structure.append({
                "name": o.get("name", "?"),
                "percentage": o.get("percentage", "?"),
                "nationality": o.get("nationality", "?"),
                "pep": o.get("pep_status", False),
                "sanctions_screened": o.get("sanctions_screened", False),
            })

        # 6. Banking
        banking = entity.get("banking", {})
        dossier.banking_profile = {
            "primary_bank": banking.get("primary_bank", "N/A"),
            "account_currency": banking.get("account_currency", "N/A"),
            "swift": banking.get("swift_bic", "N/A"),
            "custodian": banking.get("custodian", "N/A"),
            "escrow_required": banking.get("escrow_required", False),
            "escrow_agent": banking.get("escrow_agent", "N/A"),
        }

        # 7. Evidence coverage
        ev_report = self.evidence_validator.validate_entity_evidence(entity, counterparty)
        dossier.evidence_coverage = {
            "files_count": ev_report.files_hashed,
            "gap_count": len(ev_report.gaps),
            "critical_gaps": sum(1 for g in ev_report.gaps if g.severity == "ERROR"),
        }

        # 8. Red flags
        rf_report = self.red_flag_detector.scan(entity, counterparty, transaction_type)
        for rf in rf_report.flags:
            dossier.red_flag_profile.append({
                "category": rf.category,
                "severity": rf.severity,
                "description": rf.description,
                "recommendation": rf.recommendation,
            })

        # 9. Compliance summary
        val_report = self.validator.validate_entity(entity, transaction_type, counterparty)
        dossier.compliance_summary = {
            "score": val_report.compliance_score,
            "errors": len(val_report.errors),
            "warnings": len(val_report.warnings),
            "blocked": val_report.is_blocked,
        }

        # 10. Risk rating
        dossier.risk_rating = self._calculate_risk_rating(
            entity, licenses, ev_report, rf_report, val_report
        )

        return dossier

    def _calculate_risk_rating(
        self,
        entity: dict,
        licenses: list,
        ev_report: Any,
        rf_report: Any,
        val_report: Any,
    ) -> RiskRating:
        """Calculate the quantified risk rating (0-100)."""
        rating = RiskRating()

        # Regulatory score (0-25)
        rs = entity.get("regulatory_status", {})
        regulated = any(rs.get(k) for k in (
            "is_bank", "is_broker_dealer", "is_ria", "is_fund",
        ))
        if regulated and licenses:
            active = sum(1 for lic in licenses if lic.get("status") == "active")
            rating.regulatory_score = min(25, 15 + active * 5)
        elif not regulated:
            rating.regulatory_score = 20  # Non-regulated is neutral
        else:
            rating.regulatory_score = 5  # Regulated but no licenses

        # Evidence score (0-25)
        gaps = len(ev_report.gaps)
        critical_gaps = sum(1 for g in ev_report.gaps if g.severity == "ERROR")
        if gaps == 0:
            rating.evidence_score = 25
        elif critical_gaps == 0:
            rating.evidence_score = max(5, 20 - gaps * 2)
        else:
            rating.evidence_score = max(0, 10 - critical_gaps * 3)

        # Governance score (0-25)
        directors = entity.get("directors", [])
        signatories = entity.get("signatories", [])
        owners = entity.get("beneficial_owners", [])
        gov = 10  # Base
        if len(directors) >= 2:
            gov += 5
        if len(signatories) >= 2:
            gov += 5
        if owners:
            screened = sum(1 for o in owners if o.get("sanctions_screened"))
            if screened == len(owners):
                gov += 5
        rating.governance_score = min(25, gov)

        # Red flag score (0-25) — inverted: fewer flags = higher score
        critical = rf_report.critical_count
        high = rf_report.high_count
        others = len(rf_report.flags) - critical - high
        deduction = critical * 12 + high * 6 + others * 2
        rating.red_flag_score = max(0, 25 - deduction)

        return rating
