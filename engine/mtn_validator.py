"""
Medium Term Note (MTN) Program Validator
==========================================
Validates the structural completeness and operational readiness of a
Medium Term Note program as described in an issuer entity profile.

Checks:
  1. Program structure  - max offering, coupon, maturity, settlement
  2. CUSIP registration - all series present, authorized vs outstanding
  3. Transfer agent     - STC roles validated
  4. Insurance coverage - exists, sum insured, coverage ratio
  5. Legal opinions     - signed vs draft, jurisdiction coverage
  6. Collateral framework - SPV, reserve system, UCC perfection
  7. Cross-references   - CUSIPs in collateral entity match issuer CUSIPs

Each check returns PASS / WARN / FAIL with detail text.
The validator produces an overall readiness score.
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
OUTPUT_DIR = ROOT_DIR / "output" / "mtn_validations"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class ValidationItem:
    """Single validation check result."""
    category: str          # program_structure, cusips, insurance, etc.
    check: str             # Human-readable check name
    status: str            # PASS, WARN, FAIL
    detail: str = ""       # Explanation
    value: Any = None      # Actual value found


@dataclass
class MTNValidationReport:
    """Complete MTN program validation report."""
    issuer_name: str
    program_name: str = ""
    validated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    items: list[ValidationItem] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    # -- Derived --
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
    def total_checks(self) -> int:
        return len(self.items)

    @property
    def score(self) -> float:
        """Weighted score: PASS=1, WARN=0.5, FAIL=0."""
        if not self.items:
            return 0.0
        total = sum(
            1.0 if i.status == "PASS" else 0.5 if i.status == "WARN" else 0.0
            for i in self.items
        )
        return round(total / len(self.items) * 100, 1)

    @property
    def readiness(self) -> str:
        """Overall readiness: READY, CONDITIONAL, NOT_READY."""
        if self.fail_count == 0 and self.warn_count == 0:
            return "READY"
        elif self.fail_count == 0:
            return "CONDITIONAL"
        else:
            return "NOT_READY"

    def summary(self) -> str:
        status_icon = {
            "PASS": "[+]",
            "WARN": "[?]",
            "FAIL": "[X]",
        }
        lines = [
            "=" * 65,
            f"MTN PROGRAM VALIDATION: {self.issuer_name}",
            f"  {self.program_name}",
            "=" * 65,
            f"Score: {self.score}% | {self.readiness}",
            f"Checks: {self.pass_count} PASS, {self.warn_count} WARN, {self.fail_count} FAIL",
            "",
        ]

        current_cat = ""
        for item in self.items:
            if item.category != current_cat:
                current_cat = item.category
                lines.append(f"--- {current_cat.upper().replace('_', ' ')} ---")
            icon = status_icon.get(item.status, "[ ]")
            lines.append(f"  {icon} {item.check}")
            if item.detail:
                lines.append(f"      {item.detail}")

        if self.recommendations:
            lines.append("")
            lines.append("--- RECOMMENDATIONS ---")
            for r in self.recommendations:
                lines.append(f"  -> {r}")

        lines.append("=" * 65)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "issuer_name": self.issuer_name,
            "program_name": self.program_name,
            "validated_at": self.validated_at,
            "score": self.score,
            "readiness": self.readiness,
            "pass_count": self.pass_count,
            "warn_count": self.warn_count,
            "fail_count": self.fail_count,
            "items": [
                {
                    "category": i.category,
                    "check": i.check,
                    "status": i.status,
                    "detail": i.detail,
                }
                for i in self.items
            ],
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class MTNProgramValidator:
    """
    Validates a Medium Term Note program from entity YAML data.

    Usage:
        entity = load_entity("data/entities/tc_advantage_traders.yaml")
        validator = MTNProgramValidator()
        report = validator.validate(entity)
        print(report.summary())
    """

    def validate(
        self,
        issuer: dict,
        collateral_entity: dict | None = None,
    ) -> MTNValidationReport:
        """
        Run full validation on an issuer's MTN program.

        Args:
            issuer: Loaded issuer entity dict (must have mtn_program key).
            collateral_entity: Optional collateral/SPV entity for cross-referencing.
        """
        report = MTNValidationReport(
            issuer_name=issuer.get("legal_name", "Unknown"),
        )

        mtn = issuer.get("mtn_program")
        if not mtn:
            report.items.append(ValidationItem(
                "program_structure", "MTN program exists", "FAIL",
                "No mtn_program section found in entity profile.",
            ))
            report.recommendations.append("Add mtn_program section to entity YAML.")
            return report

        report.program_name = mtn.get("program_name", "")

        # 1. Program structure
        self._check_program_structure(mtn, report)

        # 2. CUSIPs
        self._check_cusips(mtn, report)

        # 3. Transfer agent
        self._check_transfer_agent(mtn, report)

        # 4. Insurance
        self._check_insurance(issuer, mtn, report)

        # 5. Legal opinions
        self._check_legal_opinions(issuer, report)

        # 6. Collateral framework
        self._check_collateral_framework(issuer, report)

        # 7. Cross-references (if collateral entity provided)
        if collateral_entity:
            self._check_cross_references(mtn, collateral_entity, report)

        # Generate recommendations
        self._generate_recommendations(report)

        return report

    # ------------------------------------------------------------------
    # Check methods
    # ------------------------------------------------------------------

    def _check_program_structure(self, mtn: dict, report: MTNValidationReport) -> None:
        """Validate core MTN program structure."""
        # Max offering
        max_off = mtn.get("max_offering")
        if max_off and max_off > 0:
            report.items.append(ValidationItem(
                "program_structure", "Max offering defined", "PASS",
                f"${max_off:,.0f} authorized.", max_off,
            ))
        else:
            report.items.append(ValidationItem(
                "program_structure", "Max offering defined", "FAIL",
                "No max_offering value found.",
            ))

        # Coupon rate
        coupon = mtn.get("coupon_rate")
        if coupon is not None and coupon > 0:
            report.items.append(ValidationItem(
                "program_structure", "Coupon rate defined", "PASS",
                f"{coupon}% fixed coupon.", coupon,
            ))
        else:
            report.items.append(ValidationItem(
                "program_structure", "Coupon rate defined", "FAIL",
                "No coupon rate specified.",
            ))

        # Maturity date
        maturity = mtn.get("maturity_date")
        if maturity:
            try:
                mat_dt = datetime.fromisoformat(str(maturity))
                now = datetime.now(timezone.utc)
                mat_aware = mat_dt.replace(tzinfo=timezone.utc) if mat_dt.tzinfo is None else mat_dt
                if mat_aware > now:
                    days = (mat_aware - now).days
                    report.items.append(ValidationItem(
                        "program_structure", "Maturity date valid", "PASS",
                        f"Matures {maturity} ({days} days remaining).", maturity,
                    ))
                else:
                    report.items.append(ValidationItem(
                        "program_structure", "Maturity date valid", "FAIL",
                        f"Maturity date {maturity} is in the past.", maturity,
                    ))
            except (ValueError, TypeError):
                report.items.append(ValidationItem(
                    "program_structure", "Maturity date valid", "WARN",
                    f"Could not parse maturity date: {maturity}.",
                ))
        else:
            report.items.append(ValidationItem(
                "program_structure", "Maturity date valid", "FAIL",
                "No maturity date specified.",
            ))

        # Settlement method
        settlement = mtn.get("settlement_method")
        if settlement:
            report.items.append(ValidationItem(
                "program_structure", "Settlement method defined", "PASS",
                f"Settlement via {settlement}.", settlement,
            ))
        else:
            report.items.append(ValidationItem(
                "program_structure", "Settlement method defined", "WARN",
                "No settlement method specified.",
            ))

        # Note type
        note_type = mtn.get("note_type")
        if note_type and "secured" in str(note_type).lower():
            report.items.append(ValidationItem(
                "program_structure", "Note type is secured", "PASS",
                f"Note type: {note_type}.", note_type,
            ))
        elif note_type:
            report.items.append(ValidationItem(
                "program_structure", "Note type is secured", "WARN",
                f"Note type '{note_type}' may not be secured.", note_type,
            ))
        else:
            report.items.append(ValidationItem(
                "program_structure", "Note type is secured", "WARN",
                "No note type specified.",
            ))

    def _check_cusips(self, mtn: dict, report: MTNValidationReport) -> None:
        """Validate CUSIP registrations."""
        cusips = mtn.get("cusips", [])
        if not cusips:
            report.items.append(ValidationItem(
                "cusips", "CUSIPs registered", "FAIL",
                "No CUSIPs found in MTN program.",
            ))
            return

        report.items.append(ValidationItem(
            "cusips", "CUSIPs registered", "PASS",
            f"{len(cusips)} CUSIP(s) registered.",
        ))

        # Check for 144A and Reg S coverage
        types = {c.get("type", "").upper() for c in cusips}
        has_144a = any("144A" in t for t in types)
        has_regs = any("REG" in t for t in types)

        if has_144a:
            report.items.append(ValidationItem(
                "cusips", "Rule 144A series exists", "PASS",
                "144A CUSIP(s) registered for institutional resale.",
            ))
        else:
            report.items.append(ValidationItem(
                "cusips", "Rule 144A series exists", "WARN",
                "No 144A CUSIP found. Limits US institutional participation.",
            ))

        if has_regs:
            report.items.append(ValidationItem(
                "cusips", "Regulation S series exists", "PASS",
                "Reg S CUSIP(s) registered for offshore placement.",
            ))
        else:
            report.items.append(ValidationItem(
                "cusips", "Regulation S series exists", "WARN",
                "No Reg S CUSIP found. Limits offshore distribution.",
            ))

        # STC confirmation
        stc = mtn.get("stc_summary")
        if stc:
            total_auth = stc.get("total_authorized", 0)
            as_of = stc.get("as_of", "unknown")
            report.items.append(ValidationItem(
                "cusips", "STC position confirmed", "PASS",
                f"STC confirms ${total_auth:,.0f} total authorized as of {as_of}.",
            ))
        else:
            report.items.append(ValidationItem(
                "cusips", "STC position confirmed", "WARN",
                "No STC position statement data linked.",
            ))

    def _check_transfer_agent(self, mtn: dict, report: MTNValidationReport) -> None:
        """Validate transfer agent setup."""
        ta = mtn.get("transfer_agent")
        if not ta:
            report.items.append(ValidationItem(
                "transfer_agent", "Transfer agent assigned", "FAIL",
                "No transfer agent defined.",
            ))
            return

        report.items.append(ValidationItem(
            "transfer_agent", "Transfer agent assigned", "PASS",
            f"Transfer agent: {ta.get('name', 'Unknown')}.",
        ))

        roles = ta.get("roles", [])
        required_roles = ["Transfer Agent", "Escrow Agent", "Paying Agent"]
        for role in required_roles:
            if role in roles:
                report.items.append(ValidationItem(
                    "transfer_agent", f"STC role: {role}", "PASS",
                    f"{ta.get('name')} serves as {role}.",
                ))
            else:
                report.items.append(ValidationItem(
                    "transfer_agent", f"STC role: {role}", "WARN",
                    f"{role} not confirmed for {ta.get('name')}.",
                ))

    def _check_insurance(
        self, issuer: dict, mtn: dict, report: MTNValidationReport,
    ) -> None:
        """Validate insurance coverage."""
        insurance = issuer.get("insurance")
        if not insurance:
            report.items.append(ValidationItem(
                "insurance", "Insurance coverage exists", "FAIL",
                "No insurance section found.",
            ))
            return

        coverage = insurance.get("coverage", {})
        broker = insurance.get("broker", {})

        # Coverage exists
        sum_insured = coverage.get("sum_insured", 0)
        if sum_insured > 0:
            report.items.append(ValidationItem(
                "insurance", "Insurance coverage exists", "PASS",
                f"${sum_insured:,.0f} coverage confirmed.", sum_insured,
            ))
        else:
            report.items.append(ValidationItem(
                "insurance", "Insurance coverage exists", "FAIL",
                "Sum insured is zero or missing.",
            ))

        # Coverage ratio vs program size
        max_off = mtn.get("max_offering", 0)
        if max_off > 0 and sum_insured > 0:
            ratio = sum_insured / max_off * 100
            if ratio >= 10:
                report.items.append(ValidationItem(
                    "insurance", "Coverage ratio adequate", "PASS",
                    f"Coverage is {ratio:.1f}% of max offering (${max_off:,.0f}).",
                ))
            else:
                report.items.append(ValidationItem(
                    "insurance", "Coverage ratio adequate", "WARN",
                    f"Coverage is only {ratio:.1f}% of max offering. Consider increasing.",
                ))

        # Market quality
        market = coverage.get("market", "")
        if "lloyd's" in market.lower():
            report.items.append(ValidationItem(
                "insurance", "Market quality (Lloyd's)", "PASS",
                f"Coverage placed in {market}.",
            ))
        elif market:
            report.items.append(ValidationItem(
                "insurance", "Market quality", "WARN",
                f"Market: {market}. Verify market rating.",
            ))

        # Broker FCA authorization
        fca = broker.get("fca_number")
        if fca:
            report.items.append(ValidationItem(
                "insurance", "Broker FCA authorized", "PASS",
                f"FCA registration #{fca}.", fca,
            ))
        else:
            report.items.append(ValidationItem(
                "insurance", "Broker FCA authorized", "WARN",
                "Broker FCA number not recorded.",
            ))

        # Lloyd's registration
        lloyds_num = broker.get("lloyds_number")
        if lloyds_num:
            report.items.append(ValidationItem(
                "insurance", "Broker Lloyd's registered", "PASS",
                f"Lloyd's broker #{lloyds_num}.", lloyds_num,
            ))

    def _check_legal_opinions(
        self, issuer: dict, report: MTNValidationReport,
    ) -> None:
        """Validate legal opinions."""
        opinions = issuer.get("legal_opinions", [])
        if not opinions:
            report.items.append(ValidationItem(
                "legal_opinions", "Legal opinions exist", "FAIL",
                "No legal opinions recorded.",
            ))
            return

        report.items.append(ValidationItem(
            "legal_opinions", "Legal opinions exist", "PASS",
            f"{len(opinions)} opinion(s) on file.",
        ))

        signed_count = 0
        draft_count = 0
        jurisdictions_covered = set()

        for op in opinions:
            status = op.get("status", "SIGNED").upper()
            counsel = op.get("counsel", "Unknown")
            j = op.get("jurisdiction", "??")
            jurisdictions_covered.add(j)

            if status == "DRAFT":
                draft_count += 1
                report.items.append(ValidationItem(
                    "legal_opinions", f"Opinion: {counsel}", "WARN",
                    f"DRAFT status. Jurisdiction: {j}. Needs finalization.",
                ))
            else:
                signed_count += 1
                report.items.append(ValidationItem(
                    "legal_opinions", f"Opinion: {counsel}", "PASS",
                    f"Signed opinion. Jurisdiction: {j}.",
                ))

            # Check scope coverage
            scope = op.get("scope", [])
            has_validity = any("valid" in s.lower() for s in scope)
            has_collateral = any("collateral" in s.lower() or "pledge" in s.lower() for s in scope)
            if has_validity and has_collateral:
                report.items.append(ValidationItem(
                    "legal_opinions", f"  Scope: validity + collateral", "PASS",
                    f"Opinion covers program validity and collateral eligibility.",
                ))
            elif has_validity:
                report.items.append(ValidationItem(
                    "legal_opinions", f"  Scope: validity only", "WARN",
                    "Covers validity but not collateral eligibility.",
                ))

        # Jurisdiction coverage
        issuer_j = issuer.get("jurisdiction", "")[:2]
        if issuer_j in jurisdictions_covered:
            report.items.append(ValidationItem(
                "legal_opinions", "Issuer jurisdiction covered", "PASS",
                f"Opinion covering {issuer_j} (issuer's jurisdiction) on file.",
            ))
        else:
            report.items.append(ValidationItem(
                "legal_opinions", "Issuer jurisdiction covered", "FAIL",
                f"No opinion covering {issuer_j}. Must obtain local counsel opinion.",
            ))

        if "US" in jurisdictions_covered:
            report.items.append(ValidationItem(
                "legal_opinions", "US law opinion", "PASS" if signed_count > 0 or "US" in {
                    op.get("jurisdiction") for op in opinions if op.get("status", "SIGNED").upper() != "DRAFT"
                } else "WARN",
                "US law opinion on file." if "US" in jurisdictions_covered else "",
            ))

    def _check_collateral_framework(
        self, issuer: dict, report: MTNValidationReport,
    ) -> None:
        """Validate collateral framework defined in issuer."""
        cf = issuer.get("collateral_framework")
        if not cf:
            report.items.append(ValidationItem(
                "collateral_framework", "Collateral framework defined", "WARN",
                "No collateral_framework section found.",
            ))
            return

        report.items.append(ValidationItem(
            "collateral_framework", "Collateral framework defined", "PASS",
            f"SPV: {cf.get('spv', 'Unknown')} in {cf.get('spv_jurisdiction', '??')}.",
        ))

        # Reserve system
        reserve = cf.get("reserve_system")
        if reserve:
            report.items.append(ValidationItem(
                "collateral_framework", "Reserve system specified", "PASS",
                f"Reserve system: {reserve}.",
            ))

        # Oracle
        oracle = cf.get("oracle_integration")
        if oracle:
            report.items.append(ValidationItem(
                "collateral_framework", "Oracle integration", "PASS",
                f"Oracle: {oracle} for on-chain attestation.",
            ))

        # Proof of reserves
        por = cf.get("proof_of_reserves")
        if por:
            report.items.append(ValidationItem(
                "collateral_framework", "Proof-of-reserves enabled", "PASS",
                "PoR system enabled for transparent verification.",
            ))

        # LTV haircut
        haircut = cf.get("ltv_haircut_range")
        if haircut:
            report.items.append(ValidationItem(
                "collateral_framework", "LTV haircut defined", "PASS",
                f"Haircut range: {haircut}.",
            ))

    def _check_cross_references(
        self,
        mtn: dict,
        collateral_entity: dict,
        report: MTNValidationReport,
    ) -> None:
        """Cross-reference issuer CUSIPs with collateral entity holdings."""
        issuer_cusips = {c["id"] for c in mtn.get("cusips", []) if "id" in c}
        coll_holdings = collateral_entity.get("collateral_holdings", {})
        coll_cusips = set(coll_holdings.get("cusips_referenced", []))

        if not coll_cusips:
            report.items.append(ValidationItem(
                "cross_references", "Collateral CUSIPs linked", "WARN",
                "Collateral entity has no cusips_referenced.",
            ))
            return

        matched = issuer_cusips & coll_cusips
        unmatched = coll_cusips - issuer_cusips

        if matched:
            report.items.append(ValidationItem(
                "cross_references", "Collateral CUSIPs linked", "PASS",
                f"{len(matched)} CUSIP(s) match between issuer and collateral entity: "
                + ", ".join(sorted(matched)),
            ))
        else:
            report.items.append(ValidationItem(
                "cross_references", "Collateral CUSIPs linked", "FAIL",
                "No CUSIPs match between issuer and collateral entity.",
            ))

        if unmatched:
            report.items.append(ValidationItem(
                "cross_references", "Unmatched collateral CUSIPs", "WARN",
                f"CUSIPs in collateral but not in issuer program: {', '.join(sorted(unmatched))}",
            ))

        # Perfection check
        perfection = coll_holdings.get("perfection", "")
        if "UCC" in perfection.upper():
            report.items.append(ValidationItem(
                "cross_references", "UCC perfection referenced", "PASS",
                f"Collateral perfection: {perfection}.",
            ))
        else:
            report.items.append(ValidationItem(
                "cross_references", "UCC perfection referenced", "WARN",
                "No UCC filing referenced in collateral entity.",
            ))

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _generate_recommendations(self, report: MTNValidationReport) -> None:
        """Generate actionable recommendations based on validation results."""
        fails = [i for i in report.items if i.status == "FAIL"]
        warns = [i for i in report.items if i.status == "WARN"]

        for item in fails:
            if "insurance" in item.category:
                report.recommendations.append(
                    f"CRITICAL: {item.check} - {item.detail}"
                )
            elif "legal_opinions" in item.category:
                report.recommendations.append(
                    f"CRITICAL: {item.check} - {item.detail}"
                )
            elif "cusip" in item.category.lower():
                report.recommendations.append(
                    f"CRITICAL: {item.check} - {item.detail}"
                )
            else:
                report.recommendations.append(
                    f"REQUIRED: {item.check} - {item.detail}"
                )

        for item in warns:
            if "DRAFT" in item.detail:
                report.recommendations.append(
                    f"ACTION: Finalize draft opinion from {item.detail.split('.')[0]}."
                )
            elif "coverage ratio" in item.check.lower():
                report.recommendations.append(
                    f"REVIEW: {item.detail}"
                )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, report: MTNValidationReport) -> Path:
        """Save validation report to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = report.issuer_name.replace(" ", "_").replace(",", "").replace(".", "")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"mtn_validation_{slug}_{ts}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path
