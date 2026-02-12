"""
Governing Law Conflict Matrix
==============================
Detects cross-border legal conflicts including:

  - Governing law vs. collateral jurisdiction mismatches
  - Arbitration seat compatibility
  - Currency controls compatibility
  - New York Convention enforcement gaps
  - Local counsel requirements
  - Regulatory extraterritoriality issues

Institutional cross-border transactions fail silently without this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.schema_loader import load_jurisdiction_rules, load_master_rules
from engine._icons import SEVERITY_ICONS, ICON_CLEAR


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class Conflict:
    category: str
    severity: str  # CRITICAL, HIGH, MEDIUM, INFO
    jurisdiction_a: str
    jurisdiction_b: str
    description: str
    recommendation: str

    def __str__(self) -> str:
        icon = SEVERITY_ICONS.get(self.severity, "[?]")
        return (
            f"{icon} [{self.severity}] {self.category}: "
            f"{self.jurisdiction_a} <-> {self.jurisdiction_b}\n"
            f"   {self.description}\n"
            f"   -> {self.recommendation}"
        )


@dataclass
class ConflictReport:
    jurisdiction_a: str
    jurisdiction_b: str
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(c.severity == "CRITICAL" for c in self.conflicts)

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "INFO": 0}
        for c in self.conflicts:
            counts[c.severity] = counts.get(c.severity, 0) + 1
        return counts

    def summary(self) -> str:
        if not self.conflicts:
            return f"{ICON_CLEAR} No conflicts detected between {self.jurisdiction_a} and {self.jurisdiction_b}."

        lines = [
            f"═══ CONFLICT MATRIX: {self.jurisdiction_a} ↔ {self.jurisdiction_b} ═══",
            f"Conflicts: {len(self.conflicts)}",
        ]
        sc = self.severity_counts
        lines.append(f"Critical: {sc['CRITICAL']} | High: {sc['HIGH']} | "
                      f"Medium: {sc['MEDIUM']} | Info: {sc['INFO']}")
        lines.append("")

        for conflict in sorted(
            self.conflicts,
            key=lambda c: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}[c.severity],
        ):
            lines.append(str(conflict))
            lines.append("")

        lines.append("═" * 50)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# New York Convention members (non-exhaustive core list)
# ---------------------------------------------------------------------------

NYC_MEMBERS = {
    "US", "GB", "SG", "CH", "VN", "DE", "FR", "JP", "KR", "AU",
    "CA", "IN", "BR", "MX", "HK", "NL", "SE", "NO", "DK", "FI",
    "AT", "BE", "ES", "IT", "PT", "IE", "NZ", "ZA", "AE", "SA",
    "TH", "MY", "PH", "ID", "CL", "CO", "PE", "AR", "EG", "KE",
    "NG", "GH", "TZ", "KY", "BM", "VG", "JE", "GG", "IM",
}

# Jurisdictions with significant currency controls
CURRENCY_CONTROL_JURISDICTIONS = {
    "VN": {
        "authority": "State Bank of Vietnam (SBV)",
        "controls": [
            "Foreign currency transactions require SBV approval",
            "Repatriation of profits subject to tax clearance",
            "Capital account transactions require registration",
        ],
    },
    "CN": {
        "authority": "State Administration of Foreign Exchange (SAFE)",
        "controls": [
            "All FX transactions require SAFE approval",
            "Capital account strictly controlled",
            "Outbound investment requires multiple approvals",
        ],
    },
    "IN": {
        "authority": "Reserve Bank of India (RBI)",
        "controls": [
            "FEMA compliance required for all cross-border transactions",
            "External commercial borrowings subject to limits",
        ],
    },
    "BR": {
        "authority": "Banco Central do Brasil",
        "controls": [
            "IOF tax on foreign exchange transactions",
            "Registration required for foreign investments",
        ],
    },
}

# Arbitration compatibility matrix
ARBITRATION_COMPATIBILITY = {
    # (seat_jurisdiction, enforcement_jurisdiction) -> compatibility notes
    ("SG", "US"): {
        "compatible": True,
        "notes": "Both NYC members. SIAC awards enforceable in US federal courts.",
    },
    ("SG", "VN"): {
        "compatible": True,
        "notes": "Both NYC members. SIAC commonly used for SEA cross-border.",
    },
    ("GB", "US"): {
        "compatible": True,
        "notes": "Both NYC members. LCIA awards enforceable in US federal courts.",
    },
    ("CH", "US"): {
        "compatible": True,
        "notes": "Both NYC members. Swiss arbitration awards enforceable.",
    },
    ("US", "VN"): {
        "compatible": True,
        "notes": "Both NYC members. Enforcement via VIAC framework.",
        "caution": "Local counsel required for enforcement in Vietnam.",
    },
    ("KY", "US"): {
        "compatible": True,
        "notes": "Cayman Islands is NYC member. Awards enforceable.",
    },
}


# ---------------------------------------------------------------------------
# Conflict Matrix Engine
# ---------------------------------------------------------------------------

class ConflictMatrix:
    """
    Analyzes governing law, arbitration, currency, and enforcement
    conflicts between two jurisdictions.
    """

    def analyze(
        self,
        jur_a: str,
        jur_b: str,
        transaction_type: str = "",
        entity_a: dict[str, Any] | None = None,
        entity_b: dict[str, Any] | None = None,
    ) -> ConflictReport:
        """Run full conflict analysis between two jurisdictions."""
        jur_a = jur_a.upper()
        jur_b = jur_b.upper()
        report = ConflictReport(jurisdiction_a=jur_a, jurisdiction_b=jur_b)

        if jur_a == jur_b:
            return report  # No cross-border conflicts

        self._check_governing_law_collateral(jur_a, jur_b, entity_a, entity_b, report)
        self._check_arbitration_compatibility(jur_a, jur_b, report)
        self._check_new_york_convention(jur_a, jur_b, report)
        self._check_currency_controls(jur_a, jur_b, report)
        self._check_regulatory_extraterritoriality(jur_a, jur_b, entity_a, entity_b, report)
        self._check_local_counsel_requirement(jur_a, jur_b, report)
        self._check_data_protection(jur_a, jur_b, report)

        return report

    # --- Governing Law vs Collateral Jurisdiction ---

    def _check_governing_law_collateral(
        self, jur_a: str, jur_b: str,
        entity_a: dict | None, entity_b: dict | None,
        report: ConflictReport,
    ) -> None:
        """
        If Party A's governing law is US but collateral is in Vietnam,
        local counsel must validate perfection of security interest.
        """
        # Determine likely governing law (US takes precedence)
        governing = "US" if "US" in (jur_a, jur_b) else jur_a
        collateral_jur = jur_b if governing == jur_a else jur_a

        if governing != collateral_jur:
            report.conflicts.append(Conflict(
                category="GOVERNING_LAW_COLLATERAL_MISMATCH",
                severity="HIGH",
                jurisdiction_a=jur_a,
                jurisdiction_b=jur_b,
                description=(
                    f"Governing law ({governing}) differs from potential collateral "
                    f"jurisdiction ({collateral_jur}). Security interests created under "
                    f"{governing} law may not be perfected in {collateral_jur} without "
                    f"local filings."
                ),
                recommendation=(
                    f"Engage local counsel in {collateral_jur} to confirm perfection "
                    f"requirements. Consider dual governing law for collateral provisions."
                ),
            ))

        # Check if security interest laws differ
        try:
            rules_gov = load_jurisdiction_rules(governing)
            if_secured = rules_gov.get("if_secured", {})
            if if_secured:
                framework = if_secured.get("security_framework", "")
                report.conflicts.append(Conflict(
                    category="SECURITY_INTEREST_FRAMEWORK",
                    severity="MEDIUM",
                    jurisdiction_a=governing,
                    jurisdiction_b=collateral_jur,
                    description=(
                        f"Governing jurisdiction uses {framework}. "
                        f"Collateral in {collateral_jur} may follow different perfection rules."
                    ),
                    recommendation=(
                        f"Confirm {collateral_jur} recognizes {framework} "
                        f"security interest framework. Local registration may be required."
                    ),
                ))
        except ValueError:
            pass

    # --- Arbitration Compatibility ---

    def _check_arbitration_compatibility(
        self, jur_a: str, jur_b: str, report: ConflictReport,
    ) -> None:
        """Check if arbitration seats are compatible across jurisdictions."""
        pair = (jur_a, jur_b)
        reverse_pair = (jur_b, jur_a)

        compat = ARBITRATION_COMPATIBILITY.get(pair) or ARBITRATION_COMPATIBILITY.get(reverse_pair)

        if compat:
            if not compat.get("compatible", True):
                report.conflicts.append(Conflict(
                    category="ARBITRATION_INCOMPATIBLE",
                    severity="CRITICAL",
                    jurisdiction_a=jur_a,
                    jurisdiction_b=jur_b,
                    description=compat.get("notes", "Arbitration award enforcement uncertain."),
                    recommendation="Select alternative arbitration seat acceptable to both parties.",
                ))
            elif compat.get("caution"):
                report.conflicts.append(Conflict(
                    category="ARBITRATION_CAUTION",
                    severity="MEDIUM",
                    jurisdiction_a=jur_a,
                    jurisdiction_b=jur_b,
                    description=compat["caution"],
                    recommendation=compat.get("notes", "Confirm enforcement pathway."),
                ))
        else:
            # Unknown pair — flag for review
            report.conflicts.append(Conflict(
                category="ARBITRATION_UNKNOWN",
                severity="MEDIUM",
                jurisdiction_a=jur_a,
                jurisdiction_b=jur_b,
                description=(
                    f"No pre-analyzed arbitration compatibility data for "
                    f"{jur_a} ↔ {jur_b}. Manual review required."
                ),
                recommendation="Verify arbitral award enforceability between jurisdictions.",
            ))

    # --- New York Convention ---

    def _check_new_york_convention(
        self, jur_a: str, jur_b: str, report: ConflictReport,
    ) -> None:
        """Check NYC membership for both jurisdictions."""
        a_member = jur_a in NYC_MEMBERS
        b_member = jur_b in NYC_MEMBERS

        if not a_member or not b_member:
            non_member = jur_a if not a_member else jur_b
            report.conflicts.append(Conflict(
                category="NEW_YORK_CONVENTION_GAP",
                severity="CRITICAL",
                jurisdiction_a=jur_a,
                jurisdiction_b=jur_b,
                description=(
                    f"{non_member} is NOT a signatory to the New York Convention "
                    f"on the Recognition and Enforcement of Foreign Arbitral Awards. "
                    f"Arbitral awards may not be enforceable."
                ),
                recommendation=(
                    f"Consider court litigation instead of arbitration, or select an "
                    f"arbitration seat in a NYC member state acceptable to both parties."
                ),
            ))

    # --- Currency Controls ---

    def _check_currency_controls(
        self, jur_a: str, jur_b: str, report: ConflictReport,
    ) -> None:
        """Check if either jurisdiction has significant currency controls."""
        for jur_code in (jur_a, jur_b):
            if jur_code in CURRENCY_CONTROL_JURISDICTIONS:
                cc = CURRENCY_CONTROL_JURISDICTIONS[jur_code]
                controls_text = "; ".join(cc["controls"])
                report.conflicts.append(Conflict(
                    category="CURRENCY_CONTROLS",
                    severity="HIGH",
                    jurisdiction_a=jur_a,
                    jurisdiction_b=jur_b,
                    description=(
                        f"{jur_code} has active currency controls enforced by "
                        f"{cc['authority']}. Controls: {controls_text}"
                    ),
                    recommendation=(
                        f"Include currency control compliance clause. "
                        f"Verify all FX transactions are pre-approved by {cc['authority']}. "
                        f"Consider escrow in convertible currency."
                    ),
                ))

        # Check if jurisdictions use different base currencies
        try:
            rules_a = load_jurisdiction_rules(jur_a)
            rules_b = load_jurisdiction_rules(jur_b)
            cb_a = rules_a.get("if_cross_border", {})
            cb_b = rules_b.get("if_cross_border", {})

            fx_a = cb_a.get("require_fx_controls")
            fx_b = cb_b.get("require_fx_controls")

            if fx_a or fx_b:
                report.conflicts.append(Conflict(
                    category="FX_CONTROLS_REQUIRED",
                    severity="MEDIUM",
                    jurisdiction_a=jur_a,
                    jurisdiction_b=jur_b,
                    description=(
                        "One or both jurisdictions require foreign exchange control "
                        "compliance in cross-border transactions."
                    ),
                    recommendation=(
                        "Include currency controls module. Specify settlement currency "
                        "and FX conversion mechanics in agreement."
                    ),
                ))
        except ValueError:
            pass

    # --- Regulatory Extraterritoriality ---

    def _check_regulatory_extraterritoriality(
        self, jur_a: str, jur_b: str,
        entity_a: dict | None, entity_b: dict | None,
        report: ConflictReport,
    ) -> None:
        """Check if US/EU regulations have extraterritorial reach."""
        if "US" in (jur_a, jur_b):
            report.conflicts.append(Conflict(
                category="US_EXTRATERRITORIAL_REACH",
                severity="MEDIUM",
                jurisdiction_a=jur_a,
                jurisdiction_b=jur_b,
                description=(
                    "US party involvement triggers potential extraterritorial application "
                    "of US laws including: OFAC sanctions, FCPA (anti-bribery), "
                    "Dodd-Frank (if financial instruments), and US tax reporting (FATCA)."
                ),
                recommendation=(
                    "Include OFAC/FCPA representations. Add FATCA compliance clause. "
                    "Screen all parties against US sanctions lists."
                ),
            ))

        if "GB" in (jur_a, jur_b):
            other = jur_b if jur_a == "GB" else jur_a
            report.conflicts.append(Conflict(
                category="UK_REGULATORY_REACH",
                severity="MEDIUM",
                jurisdiction_a=jur_a,
                jurisdiction_b=jur_b,
                description=(
                    "UK party involvement triggers UK Bribery Act 2010 (extraterritorial), "
                    "UK GDPR data protection requirements, and HMRC tax reporting."
                ),
                recommendation=(
                    "Include anti-bribery representations. Add data protection clause. "
                    "Verify UK GDPR compliance for any personal data transfers."
                ),
            ))

    # --- Local Counsel Requirement ---

    def _check_local_counsel_requirement(
        self, jur_a: str, jur_b: str, report: ConflictReport,
    ) -> None:
        """Always require local counsel for cross-border."""
        report.conflicts.append(Conflict(
            category="LOCAL_COUNSEL_REQUIRED",
            severity="INFO",
            jurisdiction_a=jur_a,
            jurisdiction_b=jur_b,
            description=(
                f"Cross-border transaction between {jur_a} and {jur_b} "
                f"requires local counsel review in both jurisdictions."
            ),
            recommendation=(
                f"Retain qualified counsel in both {jur_a} and {jur_b} "
                f"to opine on enforceability, regulatory compliance, and "
                f"local law requirements before closing."
            ),
        ))

    # --- Data Protection ---

    def _check_data_protection(
        self, jur_a: str, jur_b: str, report: ConflictReport,
    ) -> None:
        """Check for cross-border data transfer restrictions."""
        gdpr_jurisdictions = {"GB", "DE", "FR", "NL", "IE", "SE", "NO", "DK", "FI",
                              "AT", "BE", "ES", "IT", "PT", "CH"}

        if any(j in gdpr_jurisdictions for j in (jur_a, jur_b)):
            other = jur_b if jur_a in gdpr_jurisdictions else jur_a
            if other not in gdpr_jurisdictions:
                report.conflicts.append(Conflict(
                    category="DATA_PROTECTION_TRANSFER",
                    severity="MEDIUM",
                    jurisdiction_a=jur_a,
                    jurisdiction_b=jur_b,
                    description=(
                        "Transaction involves a GDPR/UK GDPR jurisdiction transferring "
                        "data to a non-adequate jurisdiction. Standard contractual clauses "
                        "or equivalent safeguards required."
                    ),
                    recommendation=(
                        "Include data processing agreement and standard contractual "
                        "clauses (SCCs). Conduct transfer impact assessment."
                    ),
                ))
