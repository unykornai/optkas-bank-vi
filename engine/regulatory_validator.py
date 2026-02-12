"""
Regulatory Claim Validator
===========================
Validates entity regulatory claims against the regulatory matrix.

Checks:
  1. Is the claimed regulator valid for that jurisdiction?
  2. Is the claimed activity legally possible without specific licenses?
  3. Does the entity type match the declared activity?
  4. Does custody require a banking license in that jurisdiction?

This prevents entities from claiming regulatory status that doesn't
exist in their jurisdiction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from engine._icons import SEVERITY_ICONS, ICON_CLEAR


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MATRIX_PATH = Path(__file__).resolve().parent / "regulatory_matrix.yaml"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class RegulatoryFinding:
    code: str
    severity: str  # ERROR, WARNING, INFO
    category: str
    description: str
    recommendation: str

    @property
    def icon(self) -> str:
        return SEVERITY_ICONS.get(self.severity, "[?]")

    def __str__(self) -> str:
        return (
            f"{self.icon} [{self.code}] {self.category}: {self.description}\n"
            f"   → {self.recommendation}"
        )


@dataclass
class RegulatoryValidationReport:
    entity_name: str
    jurisdiction: str
    findings: list[RegulatoryFinding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "ERROR" for f in self.findings)

    def summary(self) -> str:
        if not self.findings:
            return (
                f"{ICON_CLEAR} Regulatory claims for '{self.entity_name}' in {self.jurisdiction} "
                f"validated against matrix."
            )

        lines = [
            f"═══ REGULATORY VALIDATION: {self.entity_name} ({self.jurisdiction}) ═══",
            f"Findings: {len(self.findings)} "
            f"({sum(1 for f in self.findings if f.severity == 'ERROR')} errors)",
            "",
        ]
        for finding in self.findings:
            lines.append(str(finding))
            lines.append("")
        lines.append("═" * 50)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class RegulatoryClaimValidator:
    """
    Validates entity regulatory claims against the jurisdiction regulatory matrix.
    """

    def __init__(self) -> None:
        self.matrix = self._load_matrix()

    def _load_matrix(self) -> dict[str, Any]:
        if MATRIX_PATH.exists():
            with open(MATRIX_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def validate(self, entity: dict[str, Any]) -> RegulatoryValidationReport:
        """
        Validate all regulatory claims for an entity.

        Checks:
          1. Regulator validity per jurisdiction
          2. Activity-license alignment
          3. Custody-banking dependency
          4. Entity type consistency
        """
        entity_name = entity.get("legal_name", "UNKNOWN")
        jur_code = entity.get("jurisdiction", "").split("-")[0].upper()

        report = RegulatoryValidationReport(
            entity_name=entity_name,
            jurisdiction=jur_code,
        )

        jur_matrix = self.matrix.get("jurisdictions", {}).get(jur_code)
        if not jur_matrix:
            report.findings.append(RegulatoryFinding(
                code="REGMX-001",
                severity="WARNING",
                category="MATRIX_COVERAGE",
                description=f"Jurisdiction {jur_code} not found in regulatory matrix.",
                recommendation="Add jurisdiction rules to engine/regulatory_matrix.yaml.",
            ))
            return report

        regulators = jur_matrix.get("regulators", {})
        activity_mapping = self.matrix.get("activity_mapping", {})
        license_activity_mapping = self.matrix.get("license_activity_mapping", {})

        # Check 1: Validate claimed regulatory status against matrix
        self._check_regulatory_status_claims(
            entity, jur_code, regulators, activity_mapping, report
        )

        # Check 2: Validate license regulators
        self._check_license_regulators(
            entity, jur_code, regulators, license_activity_mapping, report
        )

        # Check 3: Custody-banking dependency
        self._check_custody_banking(entity, jur_code, regulators, report)

        # Check 4: Entity type consistency
        self._check_entity_type_consistency(entity, report)

        return report

    def _check_regulatory_status_claims(
        self,
        entity: dict,
        jur_code: str,
        regulators: dict,
        activity_mapping: dict,
        report: RegulatoryValidationReport,
    ) -> None:
        """Check that claimed regulatory status flags are valid for the jurisdiction."""
        rs = entity.get("regulatory_status", {})
        licenses = entity.get("licenses", [])

        for flag, activity in activity_mapping.items():
            if not rs.get(flag):
                continue

            # Check if this activity exists in the jurisdiction matrix
            activity_rules = regulators.get(activity)
            if not activity_rules:
                report.findings.append(RegulatoryFinding(
                    code="REGMX-010",
                    severity="ERROR",
                    category="INVALID_ACTIVITY",
                    description=(
                        f"Entity claims '{flag}' but activity '{activity}' is not "
                        f"defined in the regulatory matrix for {jur_code}."
                    ),
                    recommendation=f"Verify if {activity} is a regulated activity in {jur_code}.",
                ))
                continue

            # Check if license is required and present
            if activity_rules.get("requires_license"):
                valid_regulators = set()
                for key in ("primary", "self_regulatory", "state"):
                    valid_regulators.update(
                        r.upper() for r in activity_rules.get(key, [])
                    )

                # Check if entity has at least one license from valid regulators
                entity_regulators = {
                    lic.get("regulator", "").upper() for lic in licenses
                }
                has_valid = entity_regulators & valid_regulators

                if not has_valid and licenses:
                    report.findings.append(RegulatoryFinding(
                        code="REGMX-011",
                        severity="ERROR",
                        category="REGULATOR_MISMATCH",
                        description=(
                            f"Entity claims '{flag}' in {jur_code} but holds no license "
                            f"from valid regulators: {', '.join(sorted(valid_regulators))}. "
                            f"Entity's regulators: {', '.join(sorted(entity_regulators))}."
                        ),
                        recommendation=(
                            f"Obtain license from {', '.join(sorted(valid_regulators))} "
                            f"for {activity} activities in {jur_code}."
                        ),
                    ))

    def _check_license_regulators(
        self,
        entity: dict,
        jur_code: str,
        regulators: dict,
        license_activity_mapping: dict,
        report: RegulatoryValidationReport,
    ) -> None:
        """Check that each license's regulator is valid for the jurisdiction."""
        licenses = entity.get("licenses", [])

        # Build set of all valid regulators for the jurisdiction
        all_valid_regulators = set()
        for activity, rules in regulators.items():
            for key in ("primary", "self_regulatory", "state"):
                all_valid_regulators.update(
                    r.upper() for r in rules.get(key, [])
                )

        for lic in licenses:
            regulator = lic.get("regulator", "").upper()
            lic_type = lic.get("license_type", "UNKNOWN")

            if regulator and regulator not in all_valid_regulators:
                report.findings.append(RegulatoryFinding(
                    code="REGMX-020",
                    severity="ERROR",
                    category="INVALID_REGULATOR",
                    description=(
                        f"License '{lic_type}' claims regulator '{regulator}' "
                        f"which is NOT a recognized regulator in {jur_code}. "
                        f"Valid regulators: {', '.join(sorted(all_valid_regulators))}."
                    ),
                    recommendation=(
                        f"Verify the regulator '{regulator}' exists in {jur_code}. "
                        f"If correct, add to regulatory matrix."
                    ),
                ))

    def _check_custody_banking(
        self,
        entity: dict,
        jur_code: str,
        regulators: dict,
        report: RegulatoryValidationReport,
    ) -> None:
        """Check if custody requires banking license in this jurisdiction."""
        custody_rules = regulators.get("custody", {})
        if not custody_rules:
            return

        # Check if entity claims custody or has custody license
        licenses = entity.get("licenses", [])
        has_custody = any(
            lic.get("license_type", "").lower() in ("custody", "custodial", "safekeeping")
            for lic in licenses
        )
        rs = entity.get("regulatory_status", {})

        if not has_custody and not rs.get("is_bank"):
            return

        if custody_rules.get("requires_banking_license"):
            if not rs.get("is_bank"):
                report.findings.append(RegulatoryFinding(
                    code="REGMX-030",
                    severity="ERROR",
                    category="CUSTODY_BANKING_REQUIRED",
                    description=(
                        f"Custody services in {jur_code} require a banking license. "
                        f"Entity claims custody capability but is_bank = false."
                    ),
                    recommendation=(
                        f"In {jur_code}, only licensed banks can provide custody. "
                        f"Entity must obtain banking license or use a qualified custodian."
                    ),
                ))

        if custody_rules.get("requires_bd_or_ria"):
            if not (rs.get("is_broker_dealer") or rs.get("is_ria")):
                note = custody_rules.get("note", "")
                report.findings.append(RegulatoryFinding(
                    code="REGMX-031",
                    severity="WARNING",
                    category="CUSTODY_QUALIFICATION",
                    description=(
                        f"Custody in {jur_code} requires broker-dealer or RIA status. "
                        f"Entity has neither. {note}"
                    ),
                    recommendation=(
                        f"Verify entity qualifies as a custodian under {jur_code} regulations."
                    ),
                ))

    def _check_entity_type_consistency(
        self, entity: dict, report: RegulatoryValidationReport,
    ) -> None:
        """Check if entity type is consistent with claimed activities."""
        entity_type = entity.get("entity_type", "").lower()
        rs = entity.get("regulatory_status", {})

        # Natural persons cannot be banks, broker-dealers, etc.
        if entity_type in ("individual", "natural_person", "sole_proprietor"):
            institutional_flags = [
                "is_bank", "is_fund", "is_insurance_company",
            ]
            for flag in institutional_flags:
                if rs.get(flag):
                    report.findings.append(RegulatoryFinding(
                        code="REGMX-040",
                        severity="ERROR",
                        category="ENTITY_TYPE_MISMATCH",
                        description=(
                            f"Entity type '{entity_type}' is incompatible with "
                            f"regulatory status '{flag}'. Only legal entities "
                            f"can hold this status."
                        ),
                        recommendation=(
                            f"Correct entity_type or remove '{flag}' status."
                        ),
                    ))
