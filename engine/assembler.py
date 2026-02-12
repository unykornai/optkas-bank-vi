"""
Document Assembler
==================
Composes atomic contract modules into full agreements using
Jinja2 template rendering with structured entity data.

This is the core document compiler.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateSyntaxError

from engine.schema_loader import (
    format_address,
    get_jurisdiction_full_name,
    load_contract_module,
    load_master_rules,
    load_transaction_type,
    load_clause_registry,
)
from engine._icons import ICON_WARN
from engine.policy_engine import PolicyEngine


# ---------------------------------------------------------------------------
# Jinja2 Filters
# ---------------------------------------------------------------------------

def alpha_lower(value: int) -> str:
    """Convert 1-based index to lowercase letter (1->a, 2->b, etc.)."""
    return chr(96 + value) if 1 <= value <= 26 else str(value)


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------

class DocumentAssembler:
    """
    Assembles contract modules into a complete agreement document.
    """

    def __init__(self) -> None:
        self.env = Environment(loader=BaseLoader(), autoescape=False)
        self.env.filters["alpha_lower"] = alpha_lower

    def assemble(
        self,
        party_a: dict[str, Any],
        party_b: dict[str, Any],
        transaction_type: str,
        extra_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Assemble a full agreement from entity data and transaction type.

        Args:
            party_a: Primary entity dict.
            party_b: Counterparty entity dict.
            transaction_type: Transaction type key (e.g., 'loan_agreement').
            extra_context: Additional template variables.

        Returns:
            Rendered Markdown agreement.
        """
        tx_def = load_transaction_type(transaction_type)
        master = load_master_rules()

        # Determine jurisdictions
        jur_a = party_a.get("jurisdiction", "").split("-")[0].upper()
        jur_b = party_b.get("jurisdiction", "").split("-")[0].upper()
        jurisdictions = sorted(set([jur_a, jur_b]))
        is_cross_border = jur_a != jur_b

        # Build template context
        context = self._build_context(
            party_a, party_b, tx_def, jurisdictions, is_cross_border, extra_context
        )

        # Determine which modules to include
        modules = self._resolve_modules(tx_def, is_cross_border, context)

        # Validate modules against clause registry
        registry = load_clause_registry()
        registry_warnings = []

        # Render title page
        sections = [self._render_title_page(context)]

        # Render each module
        article_number = 1
        for module_name in modules:
            # Check clause registry
            reg_entry = registry.get(module_name)
            if reg_entry:
                status = reg_entry.get("status", "UNKNOWN")
                if status == "DEPRECATED":
                    registry_warnings.append(
                        f"{ICON_WARN} MODULE DEPRECATED: {module_name} -- "
                        f"v{reg_entry.get('version', '?')} "
                        f"(last reviewed: {reg_entry.get('last_reviewed_date', 'N/A')})"
                    )
                    continue  # Skip deprecated modules
                if status == "UNDER_REVIEW":
                    registry_warnings.append(
                        f"{ICON_WARN} MODULE UNDER REVIEW: {module_name} -- "
                        f"v{reg_entry.get('version', '?')}. "
                        f"Included but may change."
                    )
                # Check jurisdiction validation
                validated_jurs = reg_entry.get("jurisdiction_validated", [])
                for jur in jurisdictions:
                    if jur not in validated_jurs:
                        registry_warnings.append(
                            f"{ICON_WARN} MODULE NOT VALIDATED for {jur}: {module_name} -- "
                            f"validated only for: {', '.join(validated_jurs)}"
                        )
            else:
                registry_warnings.append(
                    f"{ICON_WARN} UNREGISTERED MODULE: {module_name} -- "
                    f"Not found in clause registry. Review required."
                )

            try:
                template_src = load_contract_module(module_name)
                ctx = {**context, "article_number": self._roman(article_number)}
                rendered = self._render_template(template_src, ctx)
                sections.append(rendered)
                article_number += 1
            except FileNotFoundError:
                sections.append(
                    f"\n<!-- {ICON_WARN} MODULE NOT FOUND: {module_name} -->\n"
                )
            except TemplateSyntaxError as e:
                sections.append(
                    f"\n<!-- {ICON_WARN} TEMPLATE ERROR in {module_name}: {e} -->\n"
                )

        result = "\n\n---\n\n".join(sections)

        # Append registry warnings if any
        if registry_warnings:
            result += "\n\n---\n\n"
            result += "# CLAUSE REGISTRY WARNINGS\n\n"
            for warn in registry_warnings:
                result += f"- {warn}\n"

        # Append liability disclaimer per policy
        policy = PolicyEngine()
        if policy.should_append_disclaimer():
            disclaimer = policy.disclaimer_text()
            if disclaimer:
                result += "\n\n---\n\n"
                result += "# LEGAL NOTICE\n\n"
                result += f"> {disclaimer}\n"

        return result

    def _build_context(
        self,
        party_a: dict,
        party_b: dict,
        tx_def: dict,
        jurisdictions: list[str],
        is_cross_border: bool,
        extra: dict | None,
    ) -> dict[str, Any]:
        """Build the full Jinja2 template context."""

        # Find valid signatories
        sig_a = next(
            (s for s in party_a.get("signatories", []) if s.get("can_bind_company")),
            party_a.get("signatories", [{}])[0] if party_a.get("signatories") else {},
        )
        sig_b = next(
            (s for s in party_b.get("signatories", []) if s.get("can_bind_company")),
            party_b.get("signatories", [{}])[0] if party_b.get("signatories") else {},
        )

        context: dict[str, Any] = {
            # Party A
            "party_a": {
                **party_a,
                "short_name": party_a.get("trade_name") or party_a.get("legal_name", "Party A"),
                "jurisdiction_full_name": get_jurisdiction_full_name(party_a.get("jurisdiction", "")),
                "registered_address_full": format_address(party_a.get("registered_address", {})),
                "signatory_name": sig_a.get("name", "[SIGNATORY — REQUIRED]"),
                "signatory_title": sig_a.get("title", "[TITLE — REQUIRED]"),
                "signatory_validated": bool(sig_a.get("authorization_document")),
                "signatory_authorization": sig_a.get("authorization_document", ""),
            },
            # Party B
            "party_b": {
                **party_b,
                "short_name": party_b.get("trade_name") or party_b.get("legal_name", "Party B"),
                "jurisdiction_full_name": get_jurisdiction_full_name(party_b.get("jurisdiction", "")),
                "registered_address_full": format_address(party_b.get("registered_address", {})),
                "signatory_name": sig_b.get("name", "[SIGNATORY — REQUIRED]"),
                "signatory_title": sig_b.get("title", "[TITLE — REQUIRED]"),
                "signatory_validated": bool(sig_b.get("authorization_document")),
                "signatory_authorization": sig_b.get("authorization_document", ""),
            },
            # Parties list (for signatory block iteration)
            "parties": [
                {
                    "legal_name": party_a.get("legal_name", ""),
                    "jurisdiction": party_a.get("jurisdiction", "").split("-")[0],
                    "signatory_name": sig_a.get("name", "[SIGNATORY — REQUIRED]"),
                    "signatory_title": sig_a.get("title", "[TITLE — REQUIRED]"),
                    "signatory_validated": bool(sig_a.get("authorization_document")),
                    "signatory_authorization": sig_a.get("authorization_document", ""),
                },
                {
                    "legal_name": party_b.get("legal_name", ""),
                    "jurisdiction": party_b.get("jurisdiction", "").split("-")[0],
                    "signatory_name": sig_b.get("name", "[SIGNATORY — REQUIRED]"),
                    "signatory_title": sig_b.get("title", "[TITLE — REQUIRED]"),
                    "signatory_validated": bool(sig_b.get("authorization_document")),
                    "signatory_authorization": sig_b.get("authorization_document", ""),
                },
            ],
            # Transaction
            "transaction_type": tx_def,
            "transaction_type_display": tx_def.get("display_name", "Agreement"),
            "transaction_category": tx_def.get("category", ""),
            # Jurisdiction
            "jurisdictions": jurisdictions,
            "is_cross_border": is_cross_border,
            "governing_law_jurisdiction": self._determine_governing_law(jurisdictions),
            "governing_law_text": self._determine_governing_law_text(jurisdictions),
            "governing_law_state": "New York",
            "court_jurisdiction": self._determine_court(jurisdictions),
            "arbitration_body": self._determine_arbitration(jurisdictions),
            # Escrow
            "escrow_required": (
                party_a.get("banking", {}).get("escrow_required")
                or party_b.get("banking", {}).get("escrow_required")
            ),
            # Date
            "effective_date": date.today().isoformat(),
            # Defaults
            "waive_jury_trial": "US" in jurisdictions,
            "conditions_precedent": [],
        }

        if extra:
            context.update(extra)

        return context

    def _resolve_modules(
        self, tx_def: dict, is_cross_border: bool, context: dict
    ) -> list[str]:
        """Determine which contract modules to include."""
        modules = list(tx_def.get("required_modules", []))

        # Add conditional modules
        conditional = tx_def.get("conditional_modules", {})
        if is_cross_border and "cross_border" in conditional:
            for mod in conditional["cross_border"]:
                if mod not in modules:
                    modules.append(mod)

        return modules

    def _render_template(self, template_src: str, context: dict) -> str:
        """Render a Jinja2 template string with context."""
        template = self.env.from_string(template_src)
        return template.render(**context)

    def _render_title_page(self, context: dict) -> str:
        """Generate the title page of the agreement."""
        return (
            f"# {context['transaction_type_display'].upper()}\n\n"
            f"**Effective Date:** {context['effective_date']}\n\n"
            f"**Between:**\n\n"
            f"**{context['party_a']['legal_name']}** "
            f"({context['party_a']['jurisdiction_full_name']})\n\n"
            f"**and**\n\n"
            f"**{context['party_b']['legal_name']}** "
            f"({context['party_b']['jurisdiction_full_name']})\n"
        )

    def _determine_governing_law(self, jurisdictions: list[str]) -> str:
        if "US" in jurisdictions:
            return "New York, New York"
        if "GB" in jurisdictions:
            return "London, England"
        if "SG" in jurisdictions:
            return "Singapore"
        if "CH" in jurisdictions:
            return "Zurich, Switzerland"
        return jurisdictions[0] if jurisdictions else "New York, New York"

    def _determine_governing_law_text(self, jurisdictions: list[str]) -> str:
        if "US" in jurisdictions:
            return "the laws of the State of New York"
        if "GB" in jurisdictions:
            return "the laws of England and Wales"
        if "SG" in jurisdictions:
            return "the laws of the Republic of Singapore"
        if "CH" in jurisdictions:
            return "the laws of Switzerland"
        if "VN" in jurisdictions:
            return "the laws of Vietnam"
        if "KY" in jurisdictions:
            return "the laws of the Cayman Islands"
        return "the laws of the State of New York"

    def _determine_court(self, jurisdictions: list[str]) -> str:
        if "US" in jurisdictions:
            return (
                "the federal and state courts located in the Borough of Manhattan, "
                "City of New York"
            )
        if "GB" in jurisdictions:
            return "the High Court of Justice, Queen's Bench Division (Commercial Court)"
        if "SG" in jurisdictions:
            return "the High Court of the Republic of Singapore"
        return "the courts of the governing law jurisdiction"

    def _determine_arbitration(self, jurisdictions: list[str]) -> str:
        if "US" in jurisdictions:
            return "AAA"
        if "SG" in jurisdictions or "VN" in jurisdictions:
            return "SIAC"
        if "GB" in jurisdictions or "KY" in jurisdictions:
            return "LCIA"
        if "CH" in jurisdictions:
            return "Swiss"
        return "AAA"

    @staticmethod
    def _roman(n: int) -> str:
        """Convert integer to Roman numeral."""
        vals = [
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        ]
        result = ""
        for value, numeral in vals:
            while n >= value:
                result += numeral
                n -= value
        return result
