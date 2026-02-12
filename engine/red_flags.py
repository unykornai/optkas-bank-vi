"""
Red Flag Detection Layer
========================
Identifies high-risk indicators across entities, transactions,
and jurisdictional contexts. Generates a Red Flag Summary
appended to every output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine._icons import RED_FLAG_ICONS, ICON_CLEAR


@dataclass
class RedFlag:
    category: str
    severity: str  # CRITICAL, HIGH, MEDIUM
    description: str
    recommendation: str

    @property
    def icon(self) -> str:
        return RED_FLAG_ICONS.get(self.severity, "[?]")

    def __str__(self) -> str:
        return (
            f"{self.icon} [{self.severity}] {self.category}\n"
            f"   {self.description}\n"
            f"   → {self.recommendation}"
        )


@dataclass
class RedFlagReport:
    flags: list[RedFlag] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "HIGH")

    def summary(self) -> str:
        if not self.flags:
            return f"{ICON_CLEAR} NO RED FLAGS DETECTED"

        lines = [
            "═══ RED FLAG SUMMARY ═══",
            f"Critical: {self.critical_count} | High: {self.high_count} | "
            f"Medium: {len(self.flags) - self.critical_count - self.high_count}",
            "",
        ]
        for flag in sorted(self.flags, key=lambda f: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}[f.severity]):
            lines.append(str(flag))
            lines.append("")

        lines.append("═" * 30)
        return "\n".join(lines)


class RedFlagDetector:
    """Scans entity data and transaction context for red flags."""

    def scan(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any] | None = None,
        transaction_type: str | None = None,
    ) -> RedFlagReport:
        report = RedFlagReport()

        self._scan_no_licenses(entity, report)
        self._scan_pep_exposure(entity, report)
        self._scan_sanctions_screening(entity, report)
        self._scan_signatory_concentration(entity, report)
        self._scan_missing_custodian(entity, report)
        self._scan_shell_indicators(entity, report)

        if counterparty:
            self._scan_counterparty_risks(entity, counterparty, report)

        return report

    def _scan_no_licenses(self, entity: dict, report: RedFlagReport) -> None:
        rs = entity.get("regulatory_status", {})
        licenses = entity.get("licenses", [])
        regulated = any(rs.get(k) for k in [
            "is_bank", "is_broker_dealer", "is_ria", "is_fund",
            "is_insurance_company", "is_money_services_business",
        ])

        if regulated and not licenses:
            report.flags.append(RedFlag(
                category="REGULATORY MISMATCH",
                severity="CRITICAL",
                description=(
                    f"'{entity.get('legal_name')}' claims regulated status "
                    f"but has ZERO licenses on file."
                ),
                recommendation=(
                    "Obtain and verify all regulatory licenses before proceeding. "
                    "Do NOT generate documents referencing regulatory authority."
                ),
            ))

    def _scan_pep_exposure(self, entity: dict, report: RedFlagReport) -> None:
        pep_directors = [
            d["name"] for d in entity.get("directors", []) if d.get("pep_status")
        ]
        pep_owners = [
            o["name"] for o in entity.get("beneficial_owners", []) if o.get("pep_status")
        ]
        all_peps = pep_directors + pep_owners

        if all_peps:
            report.flags.append(RedFlag(
                category="PEP EXPOSURE",
                severity="HIGH",
                description=f"Politically Exposed Persons detected: {', '.join(all_peps)}",
                recommendation=(
                    "Conduct enhanced due diligence (EDD). Obtain source-of-wealth "
                    "documentation. Senior management approval required."
                ),
            ))

    def _scan_sanctions_screening(self, entity: dict, report: RedFlagReport) -> None:
        owners = entity.get("beneficial_owners", [])
        unscreened = [
            o["name"] for o in owners
            if not o.get("sanctions_screened")
        ]
        if unscreened:
            report.flags.append(RedFlag(
                category="SANCTIONS SCREENING GAP",
                severity="HIGH",
                description=f"Beneficial owners NOT screened: {', '.join(unscreened)}",
                recommendation=(
                    "Run OFAC/SDN/UN/EU sanctions screening before proceeding. "
                    "Document screening results with timestamp."
                ),
            ))

    def _scan_signatory_concentration(self, entity: dict, report: RedFlagReport) -> None:
        signatories = entity.get("signatories", [])
        full_power = [
            s for s in signatories
            if s.get("can_bind_company") and s.get("can_move_funds") and s.get("can_pledge_assets")
        ]

        if len(full_power) == 1 and len(signatories) == 1:
            report.flags.append(RedFlag(
                category="SIGNATORY CONCENTRATION",
                severity="MEDIUM",
                description=(
                    f"Single signatory '{full_power[0].get('name')}' holds ALL authority "
                    f"(bind, funds, pledge). No secondary authorization."
                ),
                recommendation=(
                    "Consider requiring dual signatures for transactions above a threshold. "
                    "Verify board resolution explicitly grants sole authority."
                ),
            ))

    def _scan_missing_custodian(self, entity: dict, report: RedFlagReport) -> None:
        banking = entity.get("banking", {})
        rs = entity.get("regulatory_status", {})

        if rs.get("is_fund") or rs.get("is_ria"):
            if not banking.get("custodian"):
                report.flags.append(RedFlag(
                    category="CUSTODY GAP",
                    severity="HIGH",
                    description=(
                        f"'{entity.get('legal_name')}' is a fund/RIA but has no "
                        f"custodian identified."
                    ),
                    recommendation=(
                        "Identify and verify qualified custodian. Required by SEC Rule 206(4)-2 "
                        "(Custody Rule) for US-registered advisers."
                    ),
                ))

    def _scan_shell_indicators(self, entity: dict, report: RedFlagReport) -> None:
        directors = entity.get("directors", [])
        owners = entity.get("beneficial_owners", [])

        # Single director, no employees, no beneficial owner info
        if len(directors) == 1 and not owners:
            report.flags.append(RedFlag(
                category="SHELL ENTITY INDICATORS",
                severity="MEDIUM",
                description=(
                    f"'{entity.get('legal_name')}' has a single director and no "
                    f"beneficial ownership disclosure. Potential shell entity indicators."
                ),
                recommendation=(
                    "Request full organizational chart, beneficial ownership declaration, "
                    "and proof of business operations."
                ),
            ))

    def _scan_counterparty_risks(
        self, entity: dict, counterparty: dict, report: RedFlagReport
    ) -> None:
        cp_licenses = counterparty.get("licenses", [])
        cp_name = counterparty.get("legal_name", "COUNTERPARTY")

        if not cp_licenses:
            report.flags.append(RedFlag(
                category="COUNTERPARTY REGULATORY RISK",
                severity="HIGH",
                description=f"Counterparty '{cp_name}' has no regulatory licenses on file.",
                recommendation=(
                    "Request copies of all applicable regulatory licenses and verify "
                    "with the issuing regulator before executing any agreements."
                ),
            ))

        # Check if counterparty in high-risk jurisdiction
        cp_jur = counterparty.get("jurisdiction", "")
        # Add more high-risk jurisdictions as needed
        if cp_jur in ("KY", "VG", "BZ", "PA"):
            report.flags.append(RedFlag(
                category="HIGH-RISK JURISDICTION",
                severity="MEDIUM",
                description=(
                    f"Counterparty '{cp_name}' is domiciled in {cp_jur}, "
                    f"which may be considered a high-risk jurisdiction by certain regulators."
                ),
                recommendation=(
                    "Apply enhanced due diligence procedures. Verify economic substance "
                    "and legitimate business purpose."
                ),
            ))
