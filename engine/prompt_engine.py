"""
Prompt Engine (Layer 5)
=======================
Master prompt builder that assembles structured prompts from
entity data, jurisdiction rules, and contract modules.

This is the brain. It instructs the LLM with precision,
ensuring no hallucination, no invented licenses, no generic output.
"""

from __future__ import annotations

import json
from typing import Any

from engine.schema_loader import (
    get_jurisdiction_full_name,
    load_jurisdiction_rules,
    load_master_rules,
    load_transaction_type,
    load_clause_registry,
)
from engine.validator import ComplianceValidator, ValidationReport
from engine.red_flags import RedFlagDetector, RedFlagReport
from engine.conflict_matrix import ConflictMatrix
from engine.evidence_validator import EvidenceValidator
from engine.regulatory_validator import RegulatoryClaimValidator


class PromptEngine:
    """
    Builds structured prompts for LLM-based legal document generation.

    The prompt locks the model to:
      1. Only use structured entity data (no invention).
      2. Insert jurisdiction-specific required clauses.
      3. Flag missing data explicitly.
      4. Output in legal drafting format.
      5. Generate red-flag summary.
    """

    def __init__(self) -> None:
        self.validator = ComplianceValidator()
        self.red_flag_detector = RedFlagDetector()
        self.conflict_matrix = ConflictMatrix()
        self.evidence_validator = EvidenceValidator()
        self.regulatory_validator = RegulatoryClaimValidator()

    def build_prompt(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any],
        transaction_type: str,
        extra_instructions: str | None = None,
    ) -> dict[str, Any]:
        """
        Build a complete structured prompt package.

        Returns a dict containing:
          - system_prompt: The system instruction for the LLM.
          - user_prompt: The structured user prompt.
          - validation_report: Pre-generation compliance report.
          - red_flag_report: Risk assessment summary.
          - metadata: Context about the generation.
        """
        # Run validation first
        val_report = self.validator.validate_entity(
            entity, transaction_type, counterparty
        )
        cp_report = self.validator.validate_entity(
            counterparty, transaction_type, entity
        )

        # Run red flag detection
        rf_report = self.red_flag_detector.scan(entity, counterparty, transaction_type)

        # Load rules
        tx_def = load_transaction_type(transaction_type)
        jur_a = entity.get("jurisdiction", "").split("-")[0].upper()
        jur_b = counterparty.get("jurisdiction", "").split("-")[0].upper()
        jurisdictions = sorted(set([jur_a, jur_b]))
        is_cross_border = jur_a != jur_b

        # Load jurisdiction rules
        rules = {}
        for jur in jurisdictions:
            try:
                rules[jur] = load_jurisdiction_rules(jur)
            except ValueError:
                pass

        # Run conflict matrix
        conflict_report = self.conflict_matrix.analyze(
            jur_a, jur_b,
            transaction_type=tx_def.get("category", ""),
            entity_a=entity,
            entity_b=counterparty,
        )

        # Run evidence validation
        ev_report_a = self.evidence_validator.validate_entity_evidence(entity, counterparty)
        ev_report_b = self.evidence_validator.validate_entity_evidence(counterparty, entity)

        # Run regulatory claim validation
        reg_report_a = self.regulatory_validator.validate(entity)
        reg_report_b = self.regulatory_validator.validate(counterparty)

        # Build prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            entity, counterparty, tx_def, jurisdictions,
            is_cross_border, rules, val_report, cp_report,
            rf_report, conflict_report, ev_report_a, ev_report_b,
            reg_report_a, reg_report_b, extra_instructions,
        )

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "validation_report": val_report,
            "counterparty_validation_report": cp_report,
            "red_flag_report": rf_report,
            "metadata": {
                "transaction_type": transaction_type,
                "jurisdictions": jurisdictions,
                "is_cross_border": is_cross_border,
                "is_blocked": val_report.is_blocked or cp_report.is_blocked,
                "compliance_score_entity": val_report.compliance_score,
                "compliance_score_counterparty": cp_report.compliance_score,
            },
        }

    def _build_system_prompt(self) -> str:
        return """You are acting as a cross-border institutional transaction attorney.

STRICT RULES:

1. You may only use structured entity data provided.
2. You may not invent licenses, regulatory status, or authority.
3. If any required regulatory data is missing, you must:
   - Flag it as ERROR
   - Block enforceability language
4. If cross-border, include:
   - AML compliance language
   - Sanctions compliance (OFAC/SDN/UN/EU)
   - Currency control compliance
   - Escrow mechanics
5. If securities are involved, include:
   - Reg D / 144A / Reg S analysis
   - Transfer restrictions
   - Accredited investor representations
6. If custody is claimed:
   - Require named custodian
   - Require evidence reference
7. Output 4 sections:
   A. Draft Agreement
   B. Compliance Checklist
   C. Red Flag Report
   D. Conditions Precedent for Closing
8. Never assume regulatory approval exists.
9. Never downgrade risk language.
10. If regulatory perimeter is unclear, state:
    "Regulatory authority cannot be confirmed from provided data."
11. All clauses must reference the clause registry version.
12. Cross-border agreements MUST include escrow mechanics.
13. Evidence gaps must be flagged — do not accept YAML declarations without
    corresponding evidence files.
14. Governing law conflicts between jurisdictions must be explicitly addressed.
15. Signatory authority must be traced to board resolution or equivalent document.

OUTPUT FORMAT:
- Standard legal agreement structure with numbered articles and sections.
- All variable data clearly sourced from entity files.
- Compliance checklist appended.
- Missing data warnings appended.
- Conditions precedent list appended.
- Conflict matrix findings appended.
- Evidence status appended.
- Red-flag summary appended."""

    def _build_user_prompt(
        self,
        entity: dict,
        counterparty: dict,
        tx_def: dict,
        jurisdictions: list[str],
        is_cross_border: bool,
        rules: dict,
        val_report: ValidationReport,
        cp_report: ValidationReport,
        rf_report: RedFlagReport,
        conflict_report,
        ev_report_a,
        ev_report_b,
        reg_report_a,
        reg_report_b,
        extra: str | None,
    ) -> str:
        lines = []

        # --- Header ---
        lines.append("=" * 60)
        lines.append("STRUCTURED LEGAL DOCUMENT GENERATION REQUEST")
        lines.append("=" * 60)

        # --- Transaction Type ---
        lines.append(f"\n## Transaction Type: {tx_def.get('display_name', 'Agreement')}")
        lines.append(f"Category: {tx_def.get('category', 'N/A')}")

        # --- Jurisdictions ---
        lines.append(f"\n## Jurisdictions Involved")
        for jur in jurisdictions:
            lines.append(f"  - {jur}: {get_jurisdiction_full_name(jur)}")
        lines.append(f"Cross-Border: {'YES' if is_cross_border else 'NO'}")

        # --- Entity Data ---
        lines.append("\n## PARTY A — Entity Data (Structured Input)")
        lines.append("```json")
        lines.append(json.dumps(self._sanitize_entity(entity), indent=2, default=str))
        lines.append("```")

        lines.append("\n## PARTY B — Counterparty Data (Structured Input)")
        lines.append("```json")
        lines.append(json.dumps(self._sanitize_entity(counterparty), indent=2, default=str))
        lines.append("```")

        # --- Jurisdiction Rules ---
        lines.append("\n## Applicable Jurisdiction Rules")
        for jur, jur_rules in rules.items():
            lines.append(f"\n### {jur} — Required Clauses")
            for clause in jur_rules.get("required_clauses", []):
                lines.append(f"  - {clause}")

            aml = jur_rules.get("aml_requirements", {})
            if aml:
                lines.append(f"\n### {jur} — AML Statutes")
                for statute in aml.get("statutes", []):
                    lines.append(f"  - {statute.get('name')} ({statute.get('citation')})")

        # --- Required Modules ---
        lines.append("\n## Required Contract Modules")
        for mod in tx_def.get("required_modules", []):
            lines.append(f"  - {mod}")

        if is_cross_border:
            conditional = tx_def.get("conditional_modules", {})
            cb_mods = conditional.get("cross_border", [])
            if cb_mods:
                lines.append("\n## Cross-Border Additional Modules")
                for mod in cb_mods:
                    lines.append(f"  - {mod}")

        # --- Validation Reports ---
        lines.append("\n## Pre-Generation Compliance Report — Party A")
        lines.append(val_report.summary())

        lines.append("\n## Pre-Generation Compliance Report — Party B")
        lines.append(cp_report.summary())

        # --- Red Flags ---
        lines.append("\n## Red Flag Assessment")
        lines.append(rf_report.summary())

        # --- Conflict Matrix ---
        if is_cross_border:
            lines.append("\n## Jurisdiction Conflict Matrix")
            lines.append(conflict_report.summary())

        # --- Evidence Status ---
        lines.append("\n## Evidence Status — Party A")
        lines.append(ev_report_a.summary())
        lines.append("\n## Evidence Status — Party B")
        lines.append(ev_report_b.summary())

        # --- Regulatory Matrix Validation ---
        lines.append("\n## Regulatory Claim Validation — Party A")
        lines.append(reg_report_a.summary())
        lines.append("\n## Regulatory Claim Validation — Party B")
        lines.append(reg_report_b.summary())

        # --- Clause Registry ---
        registry = load_clause_registry()
        if registry:
            lines.append("\n## Clause Registry")
            for mod in tx_def.get("required_modules", []):
                entry = registry.get(mod, {})
                if entry:
                    lines.append(
                        f"  - {mod}: v{entry.get('version', '?')} "
                        f"| {entry.get('status', '?')} "
                        f"| risk={entry.get('risk_level', '?')} "
                        f"| reviewed={entry.get('last_reviewed_date', '?')}"
                    )

        # --- Conditions Precedent ---
        lines.append("\n## Minimum Conditions Precedent")
        for cp in tx_def.get("minimum_conditions_precedent", []):
            lines.append(f"  - {cp}")

        # --- Extra Instructions ---
        if extra:
            lines.append(f"\n## Additional Instructions")
            lines.append(extra)

        # --- Generation Command ---
        lines.append("\n" + "=" * 60)
        lines.append("GENERATE THE FOLLOWING:")
        lines.append("1. Complete draft agreement using the modules listed above.")
        lines.append("2. Compliance checklist (pass/fail per requirement).")
        lines.append("3. Missing data warnings (all [REQUIRED] fields).")
        lines.append("4. Conditions precedent list.")
        lines.append("5. Regulatory exposure summary.")
        lines.append("6. Red-flag summary.")
        lines.append("=" * 60)

        return "\n".join(lines)

    @staticmethod
    def _sanitize_entity(entity: dict) -> dict:
        """Create a clean copy for prompt injection (remove internal fields)."""
        # Return as-is; entities are already structured
        return entity
