"""
Compliance Validator (Layer 4)
==============================
Pre-generation validation engine that checks entities against
jurisdiction rules and transaction requirements.

This is the gatekeeper. No document is generated without passing
through this validator first.

Outputs:
  - Errors   (🚫) — Block generation. Must be resolved.
  - Warnings (⚠️) — Flagged in output. May proceed with caution.
  - Info     (ℹ️) — Advisory. No action required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from engine.schema_loader import (
    load_jurisdiction_rules,
    load_master_rules,
    load_transaction_type,
    get_jurisdiction_full_name,
)
from engine.regulatory_validator import RegulatoryClaimValidator
from engine.evidence_validator import EvidenceValidator
from engine._icons import SEVERITY_ICONS, ICON_BLOCK
from engine.policy_engine import PolicyEngine


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Finding:
    severity: Severity
    code: str
    message: str
    field: str | None = None

    @property
    def icon(self) -> str:
        return SEVERITY_ICONS.get(self.severity.value, "[?]")

    def __str__(self) -> str:
        loc = f" [{self.field}]" if self.field else ""
        return f"{self.icon} {self.severity.value}{loc}: {self.message}"


@dataclass
class ValidationReport:
    entity_name: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.INFO]

    @property
    def is_blocked(self) -> bool:
        return len(self.errors) > 0

    @property
    def compliance_score(self) -> int:
        """0-100 compliance score. 100 = clean."""
        total_checks = len(self.findings) or 1
        deductions = len(self.errors) * 15 + len(self.warnings) * 5
        return max(0, 100 - deductions)

    def summary(self) -> str:
        lines = [
            f"═══ COMPLIANCE REPORT: {self.entity_name} ═══",
            f"Score: {self.compliance_score}/100",
            f"Errors: {len(self.errors)} | Warnings: {len(self.warnings)} | Info: {len(self.infos)}",
            "",
        ]
        if self.is_blocked:
            lines.append(f"{ICON_BLOCK} GENERATION BLOCKED \u2014 Resolve errors before proceeding.\n")

        for f in self.findings:
            lines.append(str(f))

        lines.append("")
        lines.append("═" * 50)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core Validator
# ---------------------------------------------------------------------------

class ComplianceValidator:
    """
    Validates an entity against jurisdiction rules and transaction requirements.
    """

    def __init__(self) -> None:
        self.master_rules = load_master_rules()
        self.policy = PolicyEngine()

    def validate_entity(
        self,
        entity: dict[str, Any],
        transaction_type: str | None = None,
        counterparty: dict[str, Any] | None = None,
    ) -> ValidationReport:
        """
        Run full validation on an entity.

        Args:
            entity: Loaded entity dict.
            transaction_type: Optional transaction type to validate against.
            counterparty: Optional counterparty entity for cross-border checks.

        Returns:
            ValidationReport with all findings.
        """
        report = ValidationReport(entity_name=entity.get("legal_name", "UNKNOWN"))

        # 1. Core entity checks
        self._check_registration(entity, report)
        self._check_regulatory_status(entity, report)
        self._check_licenses(entity, report)
        self._check_directors(entity, report)
        self._check_signatories(entity, report)
        self._check_beneficial_owners(entity, report)
        self._check_banking(entity, report)

        # 2. Jurisdiction-specific checks
        self._check_jurisdiction_rules(entity, report)

        # 3. Regulatory matrix validation
        self._check_regulatory_matrix(entity, report)

        # 4. Transaction-specific checks
        if transaction_type:
            self._check_transaction_requirements(entity, transaction_type, report)

        # 5. Cross-border checks
        if counterparty:
            self._check_cross_border(entity, counterparty, report)

        # 6. Escrow enforcement for cross-border
        if counterparty and transaction_type:
            self._check_escrow_enforcement(entity, counterparty, transaction_type, report)

        return report

    # --- Registration Checks ---

    def _check_registration(self, entity: dict, report: ValidationReport) -> None:
        if not entity.get("registration_number"):
            report.findings.append(Finding(
                Severity.ERROR, "REG-001",
                "Missing registration number.",
                "registration_number",
            ))

        jur = entity.get("jurisdiction", "")
        if jur.startswith("US") and not entity.get("ein"):
            report.findings.append(Finding(
                Severity.WARNING, "REG-002",
                "US entity missing EIN (Employer Identification Number).",
                "ein",
            ))

        if not entity.get("lei"):
            report.findings.append(Finding(
                Severity.INFO, "REG-003",
                "No LEI (Legal Entity Identifier) provided. Recommended for institutional transactions.",
                "lei",
            ))

    # --- Regulatory Status Checks ---

    def _check_regulatory_status(self, entity: dict, report: ValidationReport) -> None:
        rs = entity.get("regulatory_status", {})
        if not rs:
            report.findings.append(Finding(
                Severity.ERROR, "REGSTAT-001",
                "Missing regulatory status block.",
                "regulatory_status",
            ))
            return

        # Check if entity claims regulated status but has no licenses
        regulated_flags = [
            ("is_bank", "banking"),
            ("is_broker_dealer", "broker-dealer"),
            ("is_ria", "investment adviser"),
            ("is_fund", "fund"),
            ("is_insurance_company", "insurance"),
            ("is_money_services_business", "money services business"),
        ]

        licenses = entity.get("licenses", [])
        for flag, label in regulated_flags:
            if rs.get(flag):
                if not licenses:
                    report.findings.append(Finding(
                        Severity.ERROR, "REGSTAT-002",
                        f"Entity claims {label} status but has NO licenses on file.",
                        f"regulatory_status.{flag}",
                    ))
                    break

    # --- License Checks ---

    def _check_licenses(self, entity: dict, report: ValidationReport) -> None:
        licenses = entity.get("licenses", [])
        if not licenses:
            report.findings.append(Finding(
                Severity.WARNING, "LIC-001",
                "No regulatory licenses on file.",
                "licenses",
            ))
            return

        today = date.today()
        for lic in licenses:
            # Check for missing fields
            if not lic.get("license_number"):
                report.findings.append(Finding(
                    Severity.ERROR, "LIC-002",
                    f"License '{lic.get('license_type', 'UNKNOWN')}' missing license number.",
                    "licenses[].license_number",
                ))

            if not lic.get("regulator"):
                report.findings.append(Finding(
                    Severity.ERROR, "LIC-003",
                    f"License '{lic.get('license_type', 'UNKNOWN')}' missing regulator name.",
                    "licenses[].regulator",
                ))

            # Check expiration
            exp = lic.get("expiration")
            if exp:
                if isinstance(exp, str):
                    try:
                        exp = datetime.strptime(exp, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                if isinstance(exp, date) and exp < today:
                    report.findings.append(Finding(
                        Severity.ERROR, "LIC-004",
                        f"License '{lic.get('license_type')}' from {lic.get('regulator')} "
                        f"EXPIRED on {exp}.",
                        "licenses[].expiration",
                    ))
                elif isinstance(exp, date) and (exp - today).days < 90:
                    report.findings.append(Finding(
                        Severity.WARNING, "LIC-005",
                        f"License '{lic.get('license_type')}' from {lic.get('regulator')} "
                        f"expires within 90 days ({exp}).",
                        "licenses[].expiration",
                    ))

            # Check status
            status = lic.get("status", "").lower()
            if status in ("suspended", "revoked"):
                report.findings.append(Finding(
                    Severity.ERROR, "LIC-006",
                    f"License '{lic.get('license_type')}' status is {status.upper()}.",
                    "licenses[].status",
                ))
            elif status == "expired":
                report.findings.append(Finding(
                    Severity.ERROR, "LIC-007",
                    f"License '{lic.get('license_type')}' status marked as EXPIRED.",
                    "licenses[].status",
                ))

    # --- Director Checks ---

    def _check_directors(self, entity: dict, report: ValidationReport) -> None:
        directors = entity.get("directors", [])
        pep_directors = [d for d in directors if d.get("pep_status")]

        if pep_directors:
            for d in pep_directors:
                report.findings.append(Finding(
                    Severity.WARNING, "DIR-001",
                    f"Director '{d['name']}' flagged as Politically Exposed Person (PEP). "
                    f"Enhanced due diligence required.",
                    "directors[].pep_status",
                ))

        full_auth = [d for d in directors if d.get("authority_scope") == "full"]
        if not full_auth:
            report.findings.append(Finding(
                Severity.WARNING, "DIR-002",
                "No director with full authority scope. Verify authorization chain.",
                "directors[].authority_scope",
            ))

    # --- Signatory Checks ---

    def _check_signatories(self, entity: dict, report: ValidationReport) -> None:
        signatories = entity.get("signatories", [])

        # Check binding authority
        can_bind = [s for s in signatories if s.get("can_bind_company")]
        if not can_bind:
            report.findings.append(Finding(
                Severity.ERROR, "SIG-001",
                "No signatory authorized to bind the company.",
                "signatories[].can_bind_company",
            ))

        for sig in signatories:
            if not sig.get("authorization_document"):
                report.findings.append(Finding(
                    Severity.WARNING, "SIG-002",
                    f"Signatory '{sig.get('name')}' missing authorization document reference "
                    f"(e.g., board resolution, power of attorney).",
                    "signatories[].authorization_document",
                ))

    # --- Beneficial Ownership Checks ---

    def _check_beneficial_owners(self, entity: dict, report: ValidationReport) -> None:
        owners = entity.get("beneficial_owners", [])
        if not owners:
            report.findings.append(Finding(
                Severity.WARNING, "BO-001",
                "No beneficial ownership information provided.",
                "beneficial_owners",
            ))
            return

        total_pct = sum(o.get("ownership_percentage", 0) for o in owners)
        if total_pct > 100:
            report.findings.append(Finding(
                Severity.ERROR, "BO-002",
                f"Beneficial ownership percentages sum to {total_pct}% (exceeds 100%).",
                "beneficial_owners[].ownership_percentage",
            ))

        for owner in owners:
            if owner.get("pep_status"):
                report.findings.append(Finding(
                    Severity.WARNING, "BO-003",
                    f"Beneficial owner '{owner['name']}' is a PEP. Enhanced due diligence required.",
                    "beneficial_owners[].pep_status",
                ))

            if not owner.get("sanctions_screened"):
                report.findings.append(Finding(
                    Severity.WARNING, "BO-004",
                    f"Beneficial owner '{owner['name']}' has NOT been sanctions screened.",
                    "beneficial_owners[].sanctions_screened",
                ))

            screening_date = owner.get("screening_date")
            if screening_date:
                if isinstance(screening_date, str):
                    try:
                        screening_date = datetime.strptime(screening_date, "%Y-%m-%d").date()
                    except ValueError:
                        continue
                if isinstance(screening_date, date):
                    days_since = (date.today() - screening_date).days
                    if days_since > 365:
                        report.findings.append(Finding(
                            Severity.WARNING, "BO-005",
                            f"Beneficial owner '{owner['name']}' screening is {days_since} days old "
                            f"(> 1 year). Re-screening recommended.",
                            "beneficial_owners[].screening_date",
                        ))

    # --- Banking Checks ---

    def _check_banking(self, entity: dict, report: ValidationReport) -> None:
        banking = entity.get("banking")
        if not banking:
            report.findings.append(Finding(
                Severity.INFO, "BANK-001",
                "No banking information provided.",
                "banking",
            ))
            return

        if banking.get("escrow_required") and not banking.get("custodian"):
            report.findings.append(Finding(
                Severity.WARNING, "BANK-002",
                "Escrow required but no custodian specified.",
                "banking.custodian",
            ))

        if not banking.get("swift_code"):
            report.findings.append(Finding(
                Severity.INFO, "BANK-003",
                "No SWIFT/BIC code provided for settlement bank.",
                "banking.swift_code",
            ))

    # --- Jurisdiction Rule Checks ---

    def _check_jurisdiction_rules(self, entity: dict, report: ValidationReport) -> None:
        jur_code = entity.get("jurisdiction", "")
        try:
            rules = load_jurisdiction_rules(jur_code)
        except ValueError:
            report.findings.append(Finding(
                Severity.ERROR, "JUR-001",
                f"Unsupported jurisdiction: {jur_code}",
                "jurisdiction",
            ))
            return

        # Check entity-type-specific rules
        rs = entity.get("regulatory_status", {})
        licenses = entity.get("licenses", [])
        license_regulators = {lic.get("regulator", "").upper() for lic in licenses}

        # Broker-dealer checks
        if rs.get("is_broker_dealer") and "if_broker_dealer" in rules:
            required_from = rules["if_broker_dealer"].get("require_license_from", [])
            for reg in required_from:
                if reg.upper() not in license_regulators:
                    report.findings.append(Finding(
                        Severity.ERROR, "JUR-BD-001",
                        f"Broker-dealer in {jur_code} requires license from {reg}. Not found.",
                        "licenses",
                    ))

        # RIA checks
        if rs.get("is_ria") and "if_ria" in rules:
            required_from = rules["if_ria"].get("require_license_from", [])
            for reg in required_from:
                if reg.upper() not in license_regulators:
                    report.findings.append(Finding(
                        Severity.ERROR, "JUR-RIA-001",
                        f"Investment adviser in {jur_code} requires registration with {reg}. Not found.",
                        "licenses",
                    ))

        # Bank checks
        if rs.get("is_bank") and "if_bank" in rules:
            required_from = rules["if_bank"].get("require_license_from", [])
            for reg in required_from:
                if reg.upper() not in license_regulators:
                    report.findings.append(Finding(
                        Severity.ERROR, "JUR-BANK-001",
                        f"Banking entity in {jur_code} requires license from {reg}. Not found.",
                        "licenses",
                    ))

    # --- Transaction Requirement Checks ---

    def _check_transaction_requirements(
        self, entity: dict, tx_type: str, report: ValidationReport
    ) -> None:
        try:
            tx_def = load_transaction_type(tx_type)
        except ValueError as e:
            report.findings.append(Finding(
                Severity.ERROR, "TX-001", str(e), "transaction_type"
            ))
            return

        # Check signatory authority requirements
        sig_reqs = tx_def.get("requires_signatory_authority", {})
        signatories = entity.get("signatories", [])

        for field_name, required_value in sig_reqs.items():
            if required_value:
                has_authority = any(s.get(field_name) for s in signatories)
                if not has_authority:
                    report.findings.append(Finding(
                        Severity.ERROR, "TX-SIG-001",
                        f"Transaction type '{tx_type}' requires signatory with "
                        f"'{field_name}' = true. No qualifying signatory found.",
                        f"signatories[].{field_name}",
                    ))

    # --- Cross-Border Checks ---

    def _check_cross_border(
        self,
        entity: dict,
        counterparty: dict,
        report: ValidationReport,
    ) -> None:
        jur_a = entity.get("jurisdiction", "").split("-")[0].upper()
        jur_b = counterparty.get("jurisdiction", "").split("-")[0].upper()

        if jur_a == jur_b:
            report.findings.append(Finding(
                Severity.INFO, "XB-001",
                "Same-jurisdiction transaction. Cross-border checks not required.",
            ))
            return

        report.findings.append(Finding(
            Severity.INFO, "XB-002",
            f"Cross-border transaction detected: {jur_a} ↔ {jur_b}. "
            f"Additional compliance modules will be applied.",
        ))

        # Check AML for both jurisdictions
        for jur in [jur_a, jur_b]:
            try:
                rules = load_jurisdiction_rules(jur)
                aml = rules.get("aml_requirements", {})
                if aml.get("require_beneficial_ownership_declaration"):
                    report.findings.append(Finding(
                        Severity.INFO, "XB-AML-001",
                        f"Jurisdiction {jur} requires beneficial ownership declaration.",
                    ))
            except ValueError:
                pass

        # Check escrow
        banking_a = entity.get("banking", {})
        banking_b = counterparty.get("banking", {})
        if banking_a.get("escrow_required") or banking_b.get("escrow_required"):
            report.findings.append(Finding(
                Severity.WARNING, "XB-ESC-001",
                "Cross-border transaction with escrow requirement. "
                "Escrow agent and release conditions must be specified.",
            ))

        # Check if counterparty has no licenses when they should
        cp_licenses = counterparty.get("licenses", [])
        if not cp_licenses:
            report.findings.append(Finding(
                Severity.WARNING, "XB-LIC-001",
                f"Counterparty '{counterparty.get('legal_name')}' has no regulatory "
                f"licenses on file. Verify regulatory status in {jur_b}.",
            ))

    # --- Regulatory Matrix Checks ---

    def _check_regulatory_matrix(self, entity: dict, report: ValidationReport) -> None:
        """Validate entity regulatory claims against the regulatory matrix."""
        try:
            reg_validator = RegulatoryClaimValidator()
            reg_report = reg_validator.validate(entity)

            for finding in reg_report.findings:
                severity = {
                    "ERROR": Severity.ERROR,
                    "WARNING": Severity.WARNING,
                    "INFO": Severity.INFO,
                }.get(finding.severity, Severity.WARNING)

                report.findings.append(Finding(
                    severity,
                    finding.code,
                    f"{finding.category}: {finding.description}",
                    field="regulatory_matrix",
                ))
        except Exception:
            # Regulatory matrix is advisory — don't block on load failure
            pass

    # --- Escrow Enforcement ---

    def _check_escrow_enforcement(
        self,
        entity: dict,
        counterparty: dict,
        transaction_type: str,
        report: ValidationReport,
    ) -> None:
        """Block cross-border fund transactions without escrow."""
        jur_a = entity.get("jurisdiction", "").split("-")[0].upper()
        jur_b = counterparty.get("jurisdiction", "").split("-")[0].upper()

        if jur_a == jur_b:
            return  # Not cross-border

        # Check if transaction involves funds
        try:
            tx_def = load_transaction_type(transaction_type)
        except ValueError:
            return

        category = tx_def.get("category", "").lower()
        requires_escrow = any(kw in category for kw in (
            "lending", "securities", "subscription", "purchase", "bond",
        ))

        # Also check if modules include escrow
        required_modules = tx_def.get("required_modules", [])
        conditional = tx_def.get("conditional_modules", {})
        cb_modules = conditional.get("cross_border", [])

        if "escrow_conditions" in required_modules or "escrow_conditions" in cb_modules:
            requires_escrow = True

        if not requires_escrow:
            return

        banking_a = entity.get("banking", {})
        banking_b = counterparty.get("banking", {})

        escrow_required = (
            banking_a.get("escrow_required")
            or banking_b.get("escrow_required")
        )
        escrow_agent = (
            banking_a.get("escrow_agent")
            or banking_b.get("escrow_agent")
        )

        if not escrow_required:
            escrow_severity = (
                Severity.ERROR
                if self.policy.should_block("escrow_missing_severity", "cross_border_controls")
                else Severity.WARNING
            )
            report.findings.append(Finding(
                escrow_severity, "ESC-001",
                f"Cross-border {transaction_type} between {jur_a} and {jur_b} "
                f"requires escrow. Neither entity has escrow_required = true. "
                f"Set escrow_required in entity banking data.",
                "banking.escrow_required",
            ))

        if escrow_required and not escrow_agent:
            escrow_severity = (
                Severity.ERROR
                if self.policy.should_block("escrow_missing_severity", "cross_border_controls")
                else Severity.WARNING
            )
            report.findings.append(Finding(
                escrow_severity, "ESC-002",
                f"Escrow is required but no escrow agent is defined. "
                f"Specify escrow_agent in entity banking data before generation.",
                "banking.escrow_agent",
            ))
