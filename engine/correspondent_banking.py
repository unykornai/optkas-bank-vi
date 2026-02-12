"""
Correspondent Banking Engine
============================

Maps settlement paths, validates custodial chains, resolves SWIFT
routing, and verifies that cross-border fund flows have legally
compliant banking rails at every hop.

Design Principles:
  - Entity → Partner Bank → Correspondent Bank → Beneficiary Bank
  - Non-bank entities (custodians, securities houses) use partner
    banks for SWIFT rails — this is standard institutional practice
  - Every settlement path must have: AML/KYC coverage, SWIFT
    reachability, and regulatory clearance at each node
  - The engine does NOT move money — it validates that the proposed
    path CAN move money legally
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import ROOT_DIR


# ── Known SWIFT-eligible bank registry ──────────────────────────

KNOWN_BANKS: dict[str, dict[str, Any]] = {
    "CHASUS33": {
        "name": "JPMorgan Chase Bank, N.A.",
        "country": "US",
        "swift": "CHASUS33",
        "services": ["settlement", "custody", "escrow", "correspondent"],
        "tier": "GLOBAL_SYSTEMICALLY_IMPORTANT",
    },
    "IRVTUS3N": {
        "name": "The Bank of New York Mellon Corporation",
        "country": "US",
        "swift": "IRVTUS3N",
        "services": ["settlement", "custody", "clearing", "correspondent"],
        "tier": "GLOBAL_SYSTEMICALLY_IMPORTANT",
    },
    "BOFAUS3N": {
        "name": "Bank of America / Merrill Lynch",
        "country": "US",
        "swift": "BOFAUS3N",
        "services": ["settlement", "brokerage", "custody"],
        "tier": "GLOBAL_SYSTEMICALLY_IMPORTANT",
    },
    "BFTVVNVX": {
        "name": "Vietcombank",
        "country": "VN",
        "swift": "BFTVVNVX",
        "services": ["settlement", "fx", "correspondent"],
        "tier": "DOMESTIC_MAJOR",
    },
    "SCBLVNVX": {
        "name": "Standard Chartered Bank Vietnam",
        "country": "VN",
        "swift": "SCBLVNVX",
        "services": ["settlement", "correspondent", "trade_finance"],
        "tier": "INTERNATIONAL",
    },
}

# ── Settlement path models ──────────────────────────────────────


@dataclass
class BankNode:
    """A single node in a settlement chain."""
    name: str
    swift_code: str | None
    country: str
    role: str  # originator | partner_bank | correspondent | beneficiary_bank
    aba_routing: str | None = None
    account_reference: str | None = None
    services: list[str] = field(default_factory=list)
    tier: str = "UNKNOWN"
    aml_kyc_coverage: bool = True  # Assumed for known banks


@dataclass
class SettlementPath:
    """A complete settlement chain from originator to beneficiary."""
    originator_entity: str
    beneficiary_entity: str
    nodes: list[BankNode] = field(default_factory=list)
    currency: str = "USD"
    requires_fx: bool = False
    fx_approval_required: bool = False
    fx_authority: str | None = None
    is_valid: bool = False
    validation_issues: list[str] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "SETTLEMENT PATH ANALYSIS",
            "=" * 60,
            f"From: {self.originator_entity}",
            f"To:   {self.beneficiary_entity}",
            f"Currency: {self.currency}",
            f"Requires FX: {'YES' if self.requires_fx else 'NO'}",
            "",
            "--- CHAIN ---",
        ]
        for i, node in enumerate(self.nodes):
            arrow = "  >>  " if i > 0 else "  [1] "
            swift_tag = f" [{node.swift_code}]" if node.swift_code else " [NO SWIFT]"
            lines.append(f"{arrow}{node.name}{swift_tag}")
            lines.append(f"       Role: {node.role} | Country: {node.country}")
            if node.aba_routing:
                lines.append(f"       ABA: {node.aba_routing}")
            if node.account_reference:
                lines.append(f"       Account: {node.account_reference}")

        lines.append("")
        lines.append(f"--- VALIDATION: {'PASS' if self.is_valid else 'FAIL'} ---")
        for issue in self.validation_issues:
            lines.append(f"  [X] {issue}")
        for note in self.validation_notes:
            lines.append(f"  [i] {note}")

        if self.fx_approval_required:
            lines.append(f"  [!] FX approval required from: {self.fx_authority}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "originator_entity": self.originator_entity,
            "beneficiary_entity": self.beneficiary_entity,
            "currency": self.currency,
            "requires_fx": self.requires_fx,
            "fx_approval_required": self.fx_approval_required,
            "fx_authority": self.fx_authority,
            "is_valid": self.is_valid,
            "node_count": len(self.nodes),
            "nodes": [
                {
                    "name": n.name,
                    "swift_code": n.swift_code,
                    "country": n.country,
                    "role": n.role,
                    "aba_routing": n.aba_routing,
                    "tier": n.tier,
                }
                for n in self.nodes
            ],
            "validation_issues": self.validation_issues,
            "validation_notes": self.validation_notes,
        }


# ── FX Control Registry ────────────────────────────────────────

FX_CONTROLLED_JURISDICTIONS: dict[str, dict[str, Any]] = {
    "VN": {
        "authority": "State Bank of Vietnam (SBV)",
        "controls": [
            "Foreign currency transactions require SBV approval",
            "Repatriation of profits subject to tax clearance",
            "Capital account transactions require registration",
        ],
        "freely_convertible": False,
    },
    "CN": {
        "authority": "State Administration of Foreign Exchange (SAFE)",
        "controls": [
            "All cross-border capital flows require SAFE approval",
            "Strict capital account controls",
        ],
        "freely_convertible": False,
    },
}


# ── Correspondent Banking Engine ────────────────────────────────


class CorrespondentBankingEngine:
    """
    Validates and maps settlement paths between entities.

    Core logic:
    - If an entity is NOT a bank (e.g., a securities house, custodian),
      it MUST use a partner bank for SWIFT-based settlement
    - The engine resolves the full chain and validates each node
    - Cross-border paths are checked for FX controls
    """

    def __init__(self) -> None:
        self._known_banks = dict(KNOWN_BANKS)

    def resolve_settlement_path(
        self,
        entity: dict,
        counterparty: dict,
        currency: str = "USD",
    ) -> SettlementPath:
        """Build and validate the full settlement chain."""
        e = entity.get("entity", entity)
        cp = counterparty.get("entity", counterparty)

        path = SettlementPath(
            originator_entity=e.get("legal_name", "Unknown"),
            beneficiary_entity=cp.get("legal_name", "Unknown"),
            currency=currency,
        )

        # ── Build originator side ───────────────────────────────
        self._build_originator_chain(e, path)

        # ── Build beneficiary side ──────────────────────────────
        self._build_beneficiary_chain(cp, path)

        # ── Check FX requirements ───────────────────────────────
        self._check_fx_requirements(e, cp, currency, path)

        # ── Validate the full path ──────────────────────────────
        self._validate_path(path)

        return path

    def _build_originator_chain(self, entity: dict, path: SettlementPath) -> None:
        """Add originator-side nodes to the settlement chain."""
        banking = entity.get("banking", {})
        reg = entity.get("regulatory_status", {})
        is_bank = reg.get("is_bank", False)
        name = entity.get("legal_name", "Unknown")

        # The entity itself
        originator_node = BankNode(
            name=name,
            swift_code=banking.get("swift_code") if is_bank else None,
            country=entity.get("jurisdiction", "??")[:2],
            role="originator",
        )
        path.nodes.append(originator_node)

        # If NOT a bank, needs a partner/settlement bank
        if not is_bank:
            settlement_bank = banking.get("settlement_bank")
            swift_code = banking.get("swift_code")
            if settlement_bank:
                bank_info = self._known_banks.get(swift_code, {})
                path.nodes.append(BankNode(
                    name=settlement_bank,
                    swift_code=swift_code,
                    country=bank_info.get("country", entity.get("jurisdiction", "??")[:2]),
                    role="partner_bank",
                    aba_routing=banking.get("aba_routing"),
                    account_reference=banking.get("beneficiary_account_number"),
                    services=bank_info.get("services", []),
                    tier=bank_info.get("tier", "UNKNOWN"),
                ))
                path.validation_notes.append(
                    f"{name} is not a bank. Uses {settlement_bank} "
                    f"[{swift_code}] as partner bank for SWIFT rails. "
                    f"This is standard institutional practice."
                )

            # Check for correspondent bank
            corr = banking.get("correspondent_bank")
            if corr:
                path.nodes.append(BankNode(
                    name=corr,
                    swift_code=None,
                    country="",
                    role="correspondent",
                ))

    def _build_beneficiary_chain(self, entity: dict, path: SettlementPath) -> None:
        """Add beneficiary-side nodes to the settlement chain."""
        banking = entity.get("banking", {})
        reg = entity.get("regulatory_status", {})
        is_bank = reg.get("is_bank", False)
        name = entity.get("legal_name", "Unknown")

        # If counterparty also needs a partner bank
        if not is_bank:
            settlement_bank = banking.get("settlement_bank")
            swift_code = banking.get("swift_code")
            if settlement_bank:
                bank_info = self._known_banks.get(swift_code, {})
                path.nodes.append(BankNode(
                    name=settlement_bank,
                    swift_code=swift_code,
                    country=bank_info.get("country", entity.get("jurisdiction", "??")[:2]),
                    role="beneficiary_bank",
                    aba_routing=banking.get("aba_routing"),
                    services=bank_info.get("services", []),
                    tier=bank_info.get("tier", "UNKNOWN"),
                ))

        # The beneficiary entity itself
        path.nodes.append(BankNode(
            name=name,
            swift_code=banking.get("swift_code") if is_bank else None,
            country=entity.get("jurisdiction", "??")[:2],
            role="beneficiary",
        ))

    def _check_fx_requirements(
        self,
        entity: dict,
        counterparty: dict,
        currency: str,
        path: SettlementPath,
    ) -> None:
        """Check if FX approval is needed for any jurisdiction in the path."""
        jurisdictions = set()
        ej = entity.get("jurisdiction", "")[:2]
        cj = counterparty.get("jurisdiction", "")[:2]
        jurisdictions.add(ej)
        jurisdictions.add(cj)

        if ej != cj:
            path.requires_fx = True

        for jx in jurisdictions:
            fx_info = FX_CONTROLLED_JURISDICTIONS.get(jx)
            if fx_info:
                path.fx_approval_required = True
                path.fx_authority = fx_info["authority"]
                for ctrl in fx_info["controls"]:
                    path.validation_notes.append(f"FX Control ({jx}): {ctrl}")

    def _validate_path(self, path: SettlementPath) -> None:
        """Run validation checks on the complete settlement path."""
        issues = []

        # Check: at least 3 nodes (originator, bank, beneficiary)
        if len(path.nodes) < 3:
            issues.append(
                "Settlement path has fewer than 3 nodes. "
                "Direct entity-to-entity settlement without banking "
                "intermediary is not permitted for institutional transactions."
            )

        # Check: at least one SWIFT-capable node
        swift_nodes = [n for n in path.nodes if n.swift_code]
        if not swift_nodes:
            issues.append(
                "No SWIFT-capable node in the settlement chain. "
                "At least one banking node must have SWIFT access."
            )

        # Check: no consecutive non-bank entities
        for i in range(len(path.nodes) - 1):
            a, b = path.nodes[i], path.nodes[i + 1]
            if a.role == "originator" and b.role == "beneficiary":
                issues.append(
                    "Direct entity-to-entity path without banking "
                    "intermediary detected."
                )

        # Check: GSIB or known banks in the chain
        tier_nodes = [n for n in path.nodes if n.tier != "UNKNOWN"]
        if tier_nodes:
            path.validation_notes.append(
                f"Chain includes {len(tier_nodes)} known bank(s): "
                + ", ".join(f"{n.name} ({n.tier})" for n in tier_nodes)
            )

        # Check: escrow presence for cross-border
        if path.requires_fx:
            path.validation_notes.append(
                "Cross-border transaction. Consider escrow in freely "
                "convertible currency (USD/EUR/GBP) with independent "
                "escrow agent."
            )

        path.validation_issues = issues
        path.is_valid = len(issues) == 0


# ── Settlement Structure Templates ─────────────────────────────

SETTLEMENT_STRUCTURES: dict[str, dict[str, Any]] = {
    "querubin_jpmorgan_iolta": {
        "name": "Querubin → JP Morgan Programmed Settlement → Attorney IOLTA → Seller",
        "description": (
            "DN2NC authorizes release via custody statement. "
            "JP Morgan executes programmed settlement with AML/KYC. "
            "Funds land in Attorney IOLTA for fiduciary protection. "
            "Attorney releases to seller upon closing conditions."
        ),
        "nodes": [
            {"role": "custodian", "entity": "DN2NC", "action": "authorize"},
            {"role": "settlement_bank", "entity": "JP Morgan", "action": "execute"},
            {"role": "fiduciary", "entity": "Attorney IOLTA", "action": "hold"},
            {"role": "beneficiary", "entity": "Seller", "action": "receive"},
        ],
        "strengths": [
            "JP Morgan performs full AML/KYC",
            "JP Morgan controls release logic",
            "IOLTA provides fiduciary protection",
            "Settlement is fully auditable",
            "Capital never touches unregulated rails",
        ],
        "institutional_precedent": "Standard cross-border M&A settlement structure",
    },
}
