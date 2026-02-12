"""
Governance Rules Engine
=======================
Models and validates institutional governance structures for JV deals.
Sourced from the OPTKAS Risk & Compliance Package (9 sections).

Enforces: dual-signature authority, oversight committees,
decision thresholds, quorum rules, and reporting requirements.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional


# ── Models ──────────────────────────────────────────────────────────

@dataclass
class Committee:
    """Oversight committee definition."""
    name: str
    scope: str
    chair: Optional[str] = None
    members_required: int = 2
    quorum: int = 2
    meeting_frequency: str = "quarterly"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scope": self.scope,
            "chair": self.chair,
            "members_required": self.members_required,
            "quorum": self.quorum,
            "meeting_frequency": self.meeting_frequency,
        }


@dataclass
class DecisionThreshold:
    """Decision authority threshold."""
    category: str           # e.g. "capital_deployment", "new_counterparty"
    threshold_usd: float    # amount above which dual-sig required
    authority: str           # "single" | "dual" | "committee" | "board"
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "threshold_usd": self.threshold_usd,
            "authority": self.authority,
            "description": self.description,
        }


@dataclass
class SignatureRule:
    """Signature authority rule."""
    action: str              # "execute_trade", "pledge_collateral", etc.
    required_signers: int    # 1 = single-sig, 2 = dual-sig
    eligible_roles: list     # roles that can sign
    escalation: Optional[str] = None  # committee/board for override

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "required_signers": self.required_signers,
            "eligible_roles": self.eligible_roles,
            "escalation": self.escalation,
        }


@dataclass
class ReportingRequirement:
    """Compliance reporting requirement."""
    report_type: str        # e.g. "compliance_report", "risk_audit"
    frequency: str          # "monthly", "quarterly", "annual", "on_demand"
    audience: str           # "internal", "regulator", "lender", "investor"
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "report_type": self.report_type,
            "frequency": self.frequency,
            "audience": self.audience,
            "description": self.description,
        }


@dataclass
class GovernanceFramework:
    """Complete governance framework for a deal or JV."""
    deal_name: str
    structure: str = "dual_signature"  # "single_signature" | "dual_signature" | "committee"
    ownership_split: str = ""
    committees: list[Committee] = field(default_factory=list)
    decision_thresholds: list[DecisionThreshold] = field(default_factory=list)
    signature_rules: list[SignatureRule] = field(default_factory=list)
    reporting: list[ReportingRequirement] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Validate the governance framework. Returns list of issues."""
        issues = []

        # Must have at least 1 committee
        if not self.committees:
            issues.append(
                "No oversight committees defined. "
                "Institutional JVs require at minimum: Risk, Compliance, and Audit committees."
            )

        # Must have dual-sig for major decisions
        if self.structure != "dual_signature":
            issues.append(
                f"Governance structure is '{self.structure}'. "
                "Institutional standard requires dual-signature authority for major decisions."
            )

        # Must have signature rules
        if not self.signature_rules:
            issues.append(
                "No signature rules defined. "
                "Define which actions require single vs dual authorization."
            )

        # Must have decision thresholds
        if not self.decision_thresholds:
            issues.append(
                "No decision thresholds defined. "
                "Define monetary thresholds for escalation from single to dual/committee authority."
            )

        # Must have reporting requirements
        if not self.reporting:
            issues.append(
                "No reporting requirements defined. "
                "Institutional standard: monthly compliance, quarterly risk audits, "
                "on-chain verification logs."
            )

        # Must have controls
        if not self.controls:
            issues.append(
                "No operational controls defined. "
                "Require: dual-control approvals, segregation of duties, independent audit trails."
            )

        # Check for required committee types
        committee_names_lower = {c.name.lower() for c in self.committees}
        required = ["risk", "compliance", "audit"]
        for req in required:
            if not any(req in cn for cn in committee_names_lower):
                issues.append(
                    f"Missing '{req}' committee. "
                    "Institutional governance requires Risk, Compliance, and Audit oversight."
                )

        return issues

    @property
    def is_compliant(self) -> bool:
        return len(self.validate()) == 0

    def summary(self) -> str:
        lines = [
            "=" * 50,
            f"GOVERNANCE FRAMEWORK",
            f"  {self.deal_name}",
            "=" * 50,
            f"Structure:     {self.structure.replace('_', '-').upper()}",
        ]
        if self.ownership_split:
            lines.append(f"Ownership:     {self.ownership_split}")

        # Committees
        lines.append(f"\n--- COMMITTEES ({len(self.committees)}) ---")
        for c in self.committees:
            lines.append(f"  {c.name}")
            lines.append(f"    Scope: {c.scope}")
            lines.append(f"    Quorum: {c.quorum} | Meets: {c.meeting_frequency}")

        # Signature Rules
        lines.append(f"\n--- SIGNATURE AUTHORITY ({len(self.signature_rules)}) ---")
        for sr in self.signature_rules:
            sig_type = "DUAL-SIG" if sr.required_signers >= 2 else "SINGLE-SIG"
            lines.append(f"  [{sig_type}] {sr.action}")
            lines.append(f"    Eligible: {', '.join(sr.eligible_roles)}")
            if sr.escalation:
                lines.append(f"    Escalation: {sr.escalation}")

        # Decision Thresholds
        lines.append(f"\n--- DECISION THRESHOLDS ({len(self.decision_thresholds)}) ---")
        for dt in self.decision_thresholds:
            lines.append(f"  {dt.category}: ${dt.threshold_usd:,.0f} -> {dt.authority.upper()}")
            if dt.description:
                lines.append(f"    {dt.description}")

        # Reporting
        lines.append(f"\n--- REPORTING ({len(self.reporting)}) ---")
        for r in self.reporting:
            lines.append(f"  [{r.frequency.upper()}] {r.report_type} -> {r.audience}")

        # Controls
        if self.controls:
            lines.append(f"\n--- CONTROLS ({len(self.controls)}) ---")
            for ctrl in self.controls:
                lines.append(f"  + {ctrl}")

        # Validation
        issues = self.validate()
        if issues:
            lines.append(f"\n--- ISSUES ({len(issues)}) ---")
            for issue in issues:
                lines.append(f"  [X] {issue}")
        else:
            lines.append(f"\n--- STATUS: COMPLIANT ---")

        lines.append("=" * 50)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "structure": self.structure,
            "ownership_split": self.ownership_split,
            "is_compliant": self.is_compliant,
            "committees": [c.to_dict() for c in self.committees],
            "decision_thresholds": [dt.to_dict() for dt in self.decision_thresholds],
            "signature_rules": [sr.to_dict() for sr in self.signature_rules],
            "reporting": [r.to_dict() for r in self.reporting],
            "controls": self.controls,
            "issues": self.validate(),
        }


# ── Builder ─────────────────────────────────────────────────────────

class GovernanceBuilder:
    """Builds governance frameworks from entity data and templates."""

    # Institutional template sourced from OPTKAS Risk & Compliance Package
    INSTITUTIONAL_TEMPLATE = {
        "committees": [
            Committee("Risk Committee", "credit_risk, market_risk, liquidity_risk", meeting_frequency="quarterly"),
            Committee("Compliance Committee", "kyc_aml, sanctions, regulatory_reporting", meeting_frequency="quarterly"),
            Committee("Audit & Controls Committee", "internal_audit, independent_audit, exception_reporting", meeting_frequency="quarterly"),
            Committee("Technology & Security Committee", "cybersecurity, data_protection, infrastructure", meeting_frequency="quarterly"),
        ],
        "signature_rules": [
            SignatureRule("execute_trade", 2, ["president", "director", "authorized_signatory"]),
            SignatureRule("pledge_collateral", 2, ["president", "director"], escalation="Risk Committee"),
            SignatureRule("new_counterparty_onboard", 2, ["president", "compliance_officer"], escalation="Compliance Committee"),
            SignatureRule("capital_call", 2, ["president", "director", "cfo"]),
            SignatureRule("fund_deployment", 2, ["president", "director"], escalation="Risk Committee"),
            SignatureRule("regulatory_filing", 1, ["compliance_officer", "president"]),
            SignatureRule("routine_operations", 1, ["authorized_signatory", "president"]),
        ],
        "decision_thresholds": [
            DecisionThreshold("routine_operations", 100_000, "single", "Day-to-day operational spending"),
            DecisionThreshold("capital_deployment", 1_000_000, "dual", "Capital deployment above $1M requires dual-sig"),
            DecisionThreshold("new_facility", 10_000_000, "committee", "New credit facilities above $10M require Risk Committee"),
            DecisionThreshold("strategic_decision", 50_000_000, "board", "Strategic decisions above $50M require full board"),
            DecisionThreshold("collateral_pledge", 0, "dual", "All collateral pledges require dual-sig regardless of amount"),
        ],
        "reporting": [
            ReportingRequirement("compliance_report", "monthly", "internal", "Monthly compliance status"),
            ReportingRequirement("risk_audit", "quarterly", "internal", "Quarterly risk assessment"),
            ReportingRequirement("on_chain_verification", "monthly", "lender", "On-chain verification logs"),
            ReportingRequirement("asset_audit_trail", "monthly", "lender", "Asset-level audit trails"),
            ReportingRequirement("borrowing_base_certificate", "monthly", "lender", "Borrowing base certificates"),
            ReportingRequirement("collateral_sufficiency", "monthly", "lender", "Collateral sufficiency reports"),
            ReportingRequirement("independent_audit", "annual", "regulator", "Independent third-party audits"),
            ReportingRequirement("aml_sar", "on_demand", "regulator", "Suspicious activity reporting"),
        ],
        "controls": [
            "Dual-control approvals for all material transactions",
            "Segregation of duties between origination and compliance",
            "Independent audit trails for all asset movements",
            "Quarterly compliance reviews",
            "Redundant infrastructure and disaster recovery",
            "Daily backups of all records",
            "Conservative advance rates with haircuts by asset class",
            "Concentration limits enforced",
            "Daily mark-to-market capability",
            "Automated collateral sufficiency alerts",
            "Geo-fencing for restricted jurisdictions",
            "No rehypothecation of pledged assets",
        ],
    }

    def build_from_entity(self, entity: dict, deal_name: str = "") -> GovernanceFramework:
        """Build governance framework from entity YAML data."""
        name = deal_name or entity.get("legal_name", "Unknown Deal")
        gov_data = entity.get("governance", {})

        framework = GovernanceFramework(
            deal_name=name,
            structure=gov_data.get("structure", "dual_signature"),
            ownership_split=entity.get("jv_structure", {}).get("ownership_split", ""),
        )

        # Load committees from entity
        for c in gov_data.get("committees", []):
            framework.committees.append(
                Committee(
                    name=c.get("name", ""),
                    scope=c.get("scope", ""),
                )
            )

        # Load controls from entity
        framework.controls = gov_data.get("controls", [])
        return framework

    def build_institutional(self, deal_name: str, ownership_split: str = "50/50") -> GovernanceFramework:
        """Build a full institutional-grade governance framework from template."""
        tpl = self.INSTITUTIONAL_TEMPLATE
        return GovernanceFramework(
            deal_name=deal_name,
            structure="dual_signature",
            ownership_split=ownership_split,
            committees=list(tpl["committees"]),
            decision_thresholds=list(tpl["decision_thresholds"]),
            signature_rules=list(tpl["signature_rules"]),
            reporting=list(tpl["reporting"]),
            controls=list(tpl["controls"]),
        )

    def save(self, framework: GovernanceFramework) -> Path:
        """Persist governance framework to JSON."""
        out_dir = Path("output/governance")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = framework.deal_name.replace(" ", "_").replace("/", "-")
        path = out_dir / f"governance_{safe_name}.json"
        path.write_text(json.dumps(framework.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
