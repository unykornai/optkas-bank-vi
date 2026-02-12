"""
Collateral Verification Engine
================================
Validates the structural integrity and operational readiness of a
collateral / SPV entity and its relationship to the issuer.

Checks:
  1. SPV structure     - entity type, jurisdiction, bankruptcy remoteness
  2. UCC perfection    - filing status, custodial control
  3. Collateral match  - CUSIPs match issuer program
  4. LTV / Haircut     - haircut range, capacity recognition, concentration limits
  5. Reserve system    - XRPL components, oracle, proof-of-reserves
  6. Risk controls     - credit, liquidity, market, operational controls
  7. Eligible facilities - what funding structures the collateral supports

Each check returns PASS / WARN / FAIL with detail text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "collateral_verifications"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class CollateralCheck:
    """Single collateral verification check."""
    category: str
    check: str
    status: str       # PASS, WARN, FAIL
    detail: str = ""
    value: Any = None


@dataclass
class CollateralVerificationReport:
    """Complete collateral verification report."""
    spv_name: str
    issuer_name: str = ""
    verified_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    items: list[CollateralCheck] = field(default_factory=list)
    capacity_summary: dict = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for i in self.items if i.status == "PASS")

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.items if i.status == "WARN")

    @property
    def fail_count(self) -> int:
        return sum(1 for i in self.items if i.status == "FAIL")

    @property
    def score(self) -> float:
        if not self.items:
            return 0.0
        total = sum(
            1.0 if i.status == "PASS" else 0.5 if i.status == "WARN" else 0.0
            for i in self.items
        )
        return round(total / len(self.items) * 100, 1)

    @property
    def verification_status(self) -> str:
        if self.fail_count == 0 and self.warn_count == 0:
            return "VERIFIED"
        elif self.fail_count == 0:
            return "CONDITIONAL"
        else:
            return "UNVERIFIED"

    def summary(self) -> str:
        icon = {"PASS": "[+]", "WARN": "[?]", "FAIL": "[X]"}
        lines = [
            "=" * 65,
            f"COLLATERAL VERIFICATION: {self.spv_name}",
            f"  Backing: {self.issuer_name}" if self.issuer_name else "",
            "=" * 65,
            f"Score: {self.score}% | {self.verification_status}",
            f"Checks: {self.pass_count} PASS, {self.warn_count} WARN, {self.fail_count} FAIL",
            "",
        ]
        lines = [l for l in lines if l or l == ""]

        current_cat = ""
        for item in self.items:
            if item.category != current_cat:
                current_cat = item.category
                lines.append(f"--- {current_cat.upper().replace('_', ' ')} ---")
            lines.append(f"  {icon.get(item.status, '[ ]')} {item.check}")
            if item.detail:
                lines.append(f"      {item.detail}")

        if self.capacity_summary:
            lines.append("")
            lines.append("--- CAPACITY SUMMARY ---")
            for k, v in self.capacity_summary.items():
                lines.append(f"  {k}: {v}")

        if self.recommendations:
            lines.append("")
            lines.append("--- RECOMMENDATIONS ---")
            for r in self.recommendations:
                lines.append(f"  -> {r}")

        lines.append("=" * 65)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "spv_name": self.spv_name,
            "issuer_name": self.issuer_name,
            "verified_at": self.verified_at,
            "score": self.score,
            "verification_status": self.verification_status,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "items": [
                {"category": i.category, "check": i.check,
                 "status": i.status, "detail": i.detail}
                for i in self.items
            ],
            "capacity_summary": self.capacity_summary,
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CollateralVerifier:
    """
    Validates a collateral/SPV entity's structural integrity.

    Usage:
        spv = load_entity("data/entities/optkas1_spv.yaml")
        issuer = load_entity("data/entities/tc_advantage_traders.yaml")
        verifier = CollateralVerifier()
        report = verifier.verify(spv, issuer)
        print(report.summary())
    """

    def verify(
        self,
        spv: dict,
        issuer: dict | None = None,
    ) -> CollateralVerificationReport:
        """Full collateral verification."""
        report = CollateralVerificationReport(
            spv_name=spv.get("legal_name", "Unknown"),
            issuer_name=issuer.get("legal_name", "") if issuer else "",
        )

        self._check_spv_structure(spv, report)
        self._check_ucc_perfection(spv, report)
        self._check_reserve_system(spv, report)
        self._check_ltv_controls(spv, report)
        self._check_risk_controls(spv, report)
        self._check_eligible_facilities(spv, report)

        if issuer:
            self._check_collateral_match(spv, issuer, report)
            self._compute_capacity(spv, issuer, report)

        self._generate_recommendations(report)
        return report

    # ------------------------------------------------------------------

    def _check_spv_structure(self, spv: dict, report: CollateralVerificationReport) -> None:
        etype = spv.get("entity_type", "")
        if "spv" in etype.lower() or "special_purpose" in etype.lower():
            report.items.append(CollateralCheck(
                "spv_structure", "Entity type is SPV", "PASS",
                f"Entity type: {etype}.",
            ))
        else:
            report.items.append(CollateralCheck(
                "spv_structure", "Entity type is SPV", "WARN",
                f"Entity type '{etype}' may not be a proper SPV.",
            ))

        j = spv.get("jurisdiction", "")
        favorable_spv_jurisdictions = {"US-WY", "US-DE", "US-NV", "KY", "BM", "JE", "LU"}
        if j in favorable_spv_jurisdictions:
            report.items.append(CollateralCheck(
                "spv_structure", "SPV jurisdiction favorable", "PASS",
                f"Jurisdiction {j} recognized for SPV-friendly law.",
            ))
        elif j:
            report.items.append(CollateralCheck(
                "spv_structure", "SPV jurisdiction favorable", "WARN",
                f"Jurisdiction {j} — verify SPV legislation quality.",
            ))

        # Bankruptcy remoteness
        reg = spv.get("regulatory_status", {})
        chars = reg.get("spv_characteristics", [])
        bankruptcy_remote = any("bankrupt" in c.lower() for c in chars)
        if bankruptcy_remote:
            report.items.append(CollateralCheck(
                "spv_structure", "Bankruptcy-remote", "PASS",
                "SPV characterized as bankruptcy-remote.",
            ))
        else:
            report.items.append(CollateralCheck(
                "spv_structure", "Bankruptcy-remote", "WARN",
                "No bankruptcy-remoteness characterization found.",
            ))

        # Segregated assets
        segregated = any("segregat" in c.lower() for c in chars)
        if segregated:
            report.items.append(CollateralCheck(
                "spv_structure", "Segregated asset pools", "PASS",
                "Asset pools are segregated.",
            ))

        # Independent trustee
        trustee = any("trustee" in c.lower() for c in chars)
        if trustee:
            report.items.append(CollateralCheck(
                "spv_structure", "Independent trustee oversight", "PASS",
                "Independent trustee oversight confirmed.",
            ))

    def _check_ucc_perfection(self, spv: dict, report: CollateralVerificationReport) -> None:
        coll = spv.get("collateral_holdings", {})
        perfection = coll.get("perfection", "")

        if "UCC" in perfection.upper():
            report.items.append(CollateralCheck(
                "ucc_perfection", "UCC filing referenced", "PASS",
                f"Perfection method: {perfection}.",
            ))
        else:
            report.items.append(CollateralCheck(
                "ucc_perfection", "UCC filing referenced", "FAIL",
                "No UCC filing referenced in collateral holdings.",
            ))

        if "custodial control" in perfection.lower() or "STC" in perfection.upper():
            report.items.append(CollateralCheck(
                "ucc_perfection", "Custodial control at STC", "PASS",
                "Custodial control confirmed at Securities Transfer Corporation.",
            ))

        pledge = coll.get("pledge_mechanism", "")
        if pledge:
            report.items.append(CollateralCheck(
                "ucc_perfection", "Pledge mechanism defined", "PASS",
                f"Pledge mechanism: {pledge}.",
            ))

        evidence = coll.get("ownership_evidence", "")
        if evidence:
            report.items.append(CollateralCheck(
                "ucc_perfection", "Ownership evidence available", "PASS",
                f"Evidence: {evidence}.",
            ))

    def _check_reserve_system(self, spv: dict, report: CollateralVerificationReport) -> None:
        xrpl = spv.get("xrpl_reserve_system")
        if not xrpl:
            report.items.append(CollateralCheck(
                "reserve_system", "Reserve system exists", "WARN",
                "No XRPL reserve system defined.",
            ))
            return

        report.items.append(CollateralCheck(
            "reserve_system", "Reserve system exists", "PASS",
            f"System: {xrpl.get('name', 'Unknown')}.",
        ))

        components = xrpl.get("components", [])
        names = [c.get("name", "") for c in components]

        if any("oracle" in n.lower() for n in names):
            report.items.append(CollateralCheck(
                "reserve_system", "Oracle integration", "PASS",
                "Chainlink or equivalent oracle for on-chain attestation.",
            ))

        if any("proof" in n.lower() or "por" in n.lower() for n in names):
            report.items.append(CollateralCheck(
                "reserve_system", "Proof-of-reserves", "PASS",
                "PoR system for transparent reserve verification.",
            ))

        # Check registry categories
        for comp in components:
            cats = comp.get("categories", [])
            if cats:
                cat_types = [c.get("type", "") for c in cats]
                report.items.append(CollateralCheck(
                    "reserve_system", "Reserve categories defined", "PASS",
                    f"Categories: {', '.join(cat_types)}.",
                ))
                break

    def _check_ltv_controls(self, spv: dict, report: CollateralVerificationReport) -> None:
        xrpl = spv.get("xrpl_reserve_system", {})
        ltv = xrpl.get("ltv_controls", {})
        if not ltv:
            report.items.append(CollateralCheck(
                "ltv_controls", "LTV controls defined", "WARN",
                "No LTV control section found.",
            ))
            return

        haircut = ltv.get("haircut_range", "")
        if haircut:
            report.items.append(CollateralCheck(
                "ltv_controls", "Haircut range defined", "PASS",
                f"Haircut range: {haircut}.",
            ))

        capacity = ltv.get("capacity_recognition", "")
        if capacity:
            report.items.append(CollateralCheck(
                "ltv_controls", "Capacity recognition", "PASS",
                f"Capacity: {capacity} of face value.",
            ))

        if ltv.get("concentration_limits"):
            report.items.append(CollateralCheck(
                "ltv_controls", "Concentration limits", "PASS",
                "Concentration limits enforced.",
            ))

        if ltv.get("daily_mark_to_market"):
            report.items.append(CollateralCheck(
                "ltv_controls", "Daily mark-to-market", "PASS",
                "Daily mark-to-market enabled.",
            ))

        if ltv.get("no_rehypothecation"):
            report.items.append(CollateralCheck(
                "ltv_controls", "No rehypothecation", "PASS",
                "Rehypothecation explicitly prohibited.",
            ))

        if ltv.get("automated_sufficiency_alerts"):
            report.items.append(CollateralCheck(
                "ltv_controls", "Automated alerts", "PASS",
                "Automated collateral sufficiency alerts enabled.",
            ))

    def _check_risk_controls(self, spv: dict, report: CollateralVerificationReport) -> None:
        rc = spv.get("risk_controls", {})
        if not rc:
            report.items.append(CollateralCheck(
                "risk_controls", "Risk controls exist", "WARN",
                "No risk_controls section found.",
            ))
            return

        for category in ("credit_risk", "liquidity_risk", "market_risk", "operational_risk"):
            items = rc.get(category, [])
            label = category.replace("_", " ").title()
            if items:
                report.items.append(CollateralCheck(
                    "risk_controls", f"{label} controls ({len(items)})", "PASS",
                    f"{len(items)} controls defined.",
                ))
            else:
                report.items.append(CollateralCheck(
                    "risk_controls", f"{label} controls", "WARN",
                    f"No {label.lower()} controls defined.",
                ))

    def _check_eligible_facilities(self, spv: dict, report: CollateralVerificationReport) -> None:
        facilities = spv.get("eligible_facilities", [])
        if not facilities:
            report.items.append(CollateralCheck(
                "eligible_facilities", "Eligible facilities defined", "WARN",
                "No eligible_facilities section found.",
            ))
            return

        types = [f.get("type", "") for f in facilities]
        report.items.append(CollateralCheck(
            "eligible_facilities", "Eligible facilities defined", "PASS",
            f"{len(types)} facility type(s): {', '.join(types)}.",
        ))

    def _check_collateral_match(
        self, spv: dict, issuer: dict, report: CollateralVerificationReport,
    ) -> None:
        coll = spv.get("collateral_holdings", {})
        coll_cusips = set(coll.get("cusips_referenced", []))

        mtn = issuer.get("mtn_program", {})
        issuer_cusips = {c["id"] for c in mtn.get("cusips", []) if "id" in c}

        if not coll_cusips:
            report.items.append(CollateralCheck(
                "collateral_match", "CUSIPs referenced", "WARN",
                "No CUSIPs in collateral holdings.",
            ))
            return

        matched = coll_cusips & issuer_cusips
        if matched:
            report.items.append(CollateralCheck(
                "collateral_match", "CUSIPs match issuer", "PASS",
                f"Matched: {', '.join(sorted(matched))}.",
            ))
        else:
            report.items.append(CollateralCheck(
                "collateral_match", "CUSIPs match issuer", "FAIL",
                "No CUSIPs from SPV match the issuer's MTN program.",
            ))

        # Issuer name match
        coll_issuer = coll.get("issuer", "")
        issuer_name = issuer.get("legal_name", "")
        if coll_issuer and issuer_name and coll_issuer in issuer_name:
            report.items.append(CollateralCheck(
                "collateral_match", "Issuer name matches", "PASS",
                f"Collateral references issuer: {coll_issuer}.",
            ))

    def _compute_capacity(
        self, spv: dict, issuer: dict, report: CollateralVerificationReport,
    ) -> None:
        """Compute borrowing capacity from collateral at stated haircuts."""
        mtn = issuer.get("mtn_program", {})
        coll = spv.get("collateral_holdings", {})
        coll_cusips = set(coll.get("cusips_referenced", []))

        # Find matching CUSIPs and sum authorized par
        total_par = 0
        for cusip in mtn.get("cusips", []):
            if cusip.get("id") in coll_cusips:
                par = cusip.get("authorized_par", 0)
                issued = cusip.get("issued") or cusip.get("outstanding") or par
                total_par += issued

        xrpl = spv.get("xrpl_reserve_system", {})
        ltv = xrpl.get("ltv_controls", {})
        haircut_str = ltv.get("haircut_range", "70-90%")
        capacity_str = ltv.get("capacity_recognition", "10-30%")

        # Parse ranges
        try:
            parts = capacity_str.replace("%", "").split("-")
            low_pct = float(parts[0]) / 100
            high_pct = float(parts[1]) / 100 if len(parts) > 1 else low_pct
        except (ValueError, IndexError):
            low_pct, high_pct = 0.10, 0.30

        low_cap = total_par * low_pct
        high_cap = total_par * high_pct

        report.capacity_summary = {
            "collateral_par": f"${total_par:,.0f}",
            "haircut_range": haircut_str,
            "capacity_range": capacity_str,
            "borrowing_capacity_low": f"${low_cap:,.0f}",
            "borrowing_capacity_high": f"${high_cap:,.0f}",
        }

    def _generate_recommendations(self, report: CollateralVerificationReport) -> None:
        for item in report.items:
            if item.status == "FAIL":
                report.recommendations.append(f"CRITICAL: {item.check} - {item.detail}")
            elif item.status == "WARN" and "UCC" in item.check:
                report.recommendations.append(f"ACTION: {item.check} - {item.detail}")

    def save(self, report: CollateralVerificationReport) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = report.spv_name.replace(" ", "_").replace(",", "")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"collateral_{slug}_{ts}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path
