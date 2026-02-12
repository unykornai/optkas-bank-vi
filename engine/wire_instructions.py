"""
Wire Instruction Generator
=============================
Generates institutional-grade wire instruction packages from entity
banking data and settlement path analysis.

After settlement paths are validated and banking onboarding is complete,
this engine produces the actual wire instructions that counterparties
and settlement banks use to move funds.

Each wire instruction set contains:
  - Originator details (name, account, bank, SWIFT)
  - Beneficiary details (name, account, bank, SWIFT)
  - Intermediary/correspondent bank details
  - Reference numbers and purpose codes
  - FX instructions (if cross-border)
  - Compliance attestations (OFAC, sanctions)

The output is formatted for institutional use — not consumer wire transfers.

Input:  Entity data, settlement path, amount, currency, reference
Output: WireInstructionPackage with originator/beneficiary details,
        compliance notes, and formatted instruction text
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import load_entity
from engine.correspondent_banking import (
    CorrespondentBankingEngine,
    SettlementPath,
    BankNode,
    KNOWN_BANKS,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "wire_instructions"

SANCTIONED_JURISDICTIONS = {"IR", "KP", "CU", "SY", "RU"}

COMPLIANCE_ATTESTATION_TEMPLATE = (
    "The undersigned hereby certifies that: "
    "(1) This wire transfer does not involve any party on the OFAC SDN list; "
    "(2) The funds are not derived from or intended for any prohibited activity; "
    "(3) All parties have been screened in accordance with applicable AML/KYC regulations; "
    "(4) This transfer complies with all applicable sanctions programs."
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class WireParty:
    """Details for one side of a wire transfer."""
    party_type: str  # originator | beneficiary | intermediary
    entity_name: str
    bank_name: str = ""
    swift_code: str = ""
    aba_routing: str = ""
    account_number: str = ""
    account_name: str = ""
    address: str = ""
    country: str = ""
    reference: str = ""

    def to_dict(self) -> dict:
        return {
            "party_type": self.party_type,
            "entity_name": self.entity_name,
            "bank_name": self.bank_name,
            "swift_code": self.swift_code,
            "aba_routing": self.aba_routing,
            "account_number": self.account_number,
            "account_name": self.account_name,
            "address": self.address,
            "country": self.country,
            "reference": self.reference,
        }


@dataclass
class ComplianceNote:
    """A compliance note or flag on the wire instruction."""
    category: str  # sanctions, aml, fx_controls, regulatory
    severity: str  # INFO, WARNING, BLOCK
    description: str

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass
class WireInstruction:
    """A single wire transfer instruction."""
    instruction_id: str
    originator: WireParty = field(default_factory=lambda: WireParty(party_type="originator", entity_name=""))
    beneficiary: WireParty = field(default_factory=lambda: WireParty(party_type="beneficiary", entity_name=""))
    intermediary: WireParty | None = None
    amount: float = 0.0
    currency: str = "USD"
    value_date: str = ""
    purpose: str = ""
    reference: str = ""
    fx_required: bool = False
    fx_rate: float | None = None
    fx_settlement_currency: str = ""
    compliance_notes: list[ComplianceNote] = field(default_factory=list)
    compliance_attestation: str = COMPLIANCE_ATTESTATION_TEMPLATE
    status: str = "DRAFT"  # DRAFT, REVIEWED, APPROVED, EXECUTED, CANCELLED
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def is_blocked(self) -> bool:
        return any(n.severity == "BLOCK" for n in self.compliance_notes)

    @property
    def has_warnings(self) -> bool:
        return any(n.severity == "WARNING" for n in self.compliance_notes)

    def formatted(self) -> str:
        """Generate formatted wire instruction text."""
        lines = [
            "=" * 70,
            "WIRE TRANSFER INSTRUCTION",
            f"  Instruction ID: {self.instruction_id}",
            f"  Status:         {self.status}",
            f"  Created:        {self.created_at}",
            "=" * 70,
            "",
            "--- ORIGINATOR ---",
            f"  Entity:     {self.originator.entity_name}",
            f"  Bank:       {self.originator.bank_name}",
            f"  SWIFT/BIC:  {self.originator.swift_code or 'N/A'}",
            f"  ABA:        {self.originator.aba_routing or 'N/A'}",
            f"  Account:    {self.originator.account_number or 'N/A'}",
            f"  Country:    {self.originator.country}",
            "",
        ]

        if self.intermediary:
            lines.extend([
                "--- INTERMEDIARY BANK ---",
                f"  Bank:       {self.intermediary.bank_name}",
                f"  SWIFT/BIC:  {self.intermediary.swift_code or 'N/A'}",
                f"  Country:    {self.intermediary.country}",
                "",
            ])

        lines.extend([
            "--- BENEFICIARY ---",
            f"  Entity:     {self.beneficiary.entity_name}",
            f"  Bank:       {self.beneficiary.bank_name}",
            f"  SWIFT/BIC:  {self.beneficiary.swift_code or 'N/A'}",
            f"  ABA:        {self.beneficiary.aba_routing or 'N/A'}",
            f"  Account:    {self.beneficiary.account_number or 'N/A'}",
            f"  Country:    {self.beneficiary.country}",
            "",
            "--- AMOUNT ---",
            f"  Amount:     {self.currency} {self.amount:,.2f}",
            f"  Value Date: {self.value_date or 'TBD'}",
            f"  Purpose:    {self.purpose or 'N/A'}",
            f"  Reference:  {self.reference or 'N/A'}",
        ])

        if self.fx_required:
            lines.extend([
                "",
                "--- FX DETAILS ---",
                f"  FX Required:    YES",
                f"  Settlement CCY: {self.fx_settlement_currency or 'TBD'}",
                f"  FX Rate:        {self.fx_rate or 'SPOT'}",
            ])

        if self.compliance_notes:
            lines.extend(["", "--- COMPLIANCE ---"])
            for note in self.compliance_notes:
                icon = {"BLOCK": "[X]", "WARNING": "[!]", "INFO": "[i]"}.get(
                    note.severity, "[?]"
                )
                lines.append(f"  {icon} [{note.category.upper()}] {note.description}")

        if self.is_blocked:
            lines.extend(["", "*** WIRE BLOCKED — COMPLIANCE ISSUE DETECTED ***"])

        lines.extend(["", "=" * 70])
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = {
            "instruction_id": self.instruction_id,
            "originator": self.originator.to_dict(),
            "beneficiary": self.beneficiary.to_dict(),
            "intermediary": self.intermediary.to_dict() if self.intermediary else None,
            "amount": self.amount,
            "currency": self.currency,
            "value_date": self.value_date,
            "purpose": self.purpose,
            "reference": self.reference,
            "fx_required": self.fx_required,
            "fx_rate": self.fx_rate,
            "fx_settlement_currency": self.fx_settlement_currency,
            "compliance_notes": [n.to_dict() for n in self.compliance_notes],
            "status": self.status,
            "created_at": self.created_at,
            "is_blocked": self.is_blocked,
        }
        return d


@dataclass
class WireInstructionPackage:
    """Complete wire instruction package for a deal."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    instructions: list[WireInstruction] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.instructions)

    @property
    def blocked(self) -> int:
        return sum(1 for w in self.instructions if w.is_blocked)

    @property
    def draft(self) -> int:
        return sum(1 for w in self.instructions if w.status == "DRAFT")

    @property
    def approved(self) -> int:
        return sum(1 for w in self.instructions if w.status == "APPROVED")

    @property
    def all_clear(self) -> bool:
        """No blocked wires and at least one instruction."""
        return self.total > 0 and self.blocked == 0

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "WIRE INSTRUCTION PACKAGE",
            f"  {self.deal_name}",
            f"  Created: {self.created_at}",
            "=" * 70,
            "",
            f"  Total Instructions: {self.total}",
            f"  Blocked:            {self.blocked}",
            f"  Draft:              {self.draft}",
            f"  Approved:           {self.approved}",
            f"  All Clear:          {'YES' if self.all_clear else 'NO'}",
            "",
        ]

        for wi in self.instructions:
            blocked_tag = " [BLOCKED]" if wi.is_blocked else ""
            warn_tag = " [WARNINGS]" if wi.has_warnings and not wi.is_blocked else ""
            lines.append(
                f"--- {wi.instruction_id}{blocked_tag}{warn_tag} ---"
            )
            lines.append(
                f"  From: {wi.originator.entity_name} -> To: {wi.beneficiary.entity_name}"
            )
            lines.append(
                f"  Amount: {wi.currency} {wi.amount:,.2f}  |  Status: {wi.status}"
            )
            if wi.compliance_notes:
                for n in wi.compliance_notes:
                    icon = {"BLOCK": "X", "WARNING": "!", "INFO": "i"}.get(
                        n.severity, "?"
                    )
                    lines.append(f"  [{icon}] {n.description}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "total": self.total,
            "blocked": self.blocked,
            "all_clear": self.all_clear,
            "instructions": [i.to_dict() for i in self.instructions],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class WireInstructionEngine:
    """
    Generates wire instruction packages from entity data and settlement paths.

    Usage:
        engine = WireInstructionEngine()
        pkg = engine.generate(
            deal_name="OPTKAS-TC Deal",
            originator_path=Path("data/entities/tc_advantage_traders.yaml"),
            beneficiary_path=Path("data/entities/optkas1_spv.yaml"),
            amount=10_000_000,
            currency="USD",
            purpose="MTN subscription payment",
        )
        print(pkg.summary())
    """

    def __init__(self) -> None:
        self.banking_engine = CorrespondentBankingEngine()

    def generate(
        self,
        deal_name: str,
        originator_path: Path | None = None,
        beneficiary_path: Path | None = None,
        amount: float = 0.0,
        currency: str = "USD",
        purpose: str = "",
        reference: str = "",
        value_date: str = "",
    ) -> WireInstructionPackage:
        """Generate wire instruction package."""
        pkg = WireInstructionPackage(deal_name=deal_name)

        if not originator_path or not beneficiary_path:
            return pkg

        orig_data = load_entity(originator_path)
        bene_data = load_entity(beneficiary_path)

        # Generate a unique instruction ID
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        instr_id = f"WIRE-{ts}-001"

        # Build wire instruction
        instruction = self._build_instruction(
            instr_id=instr_id,
            originator=orig_data,
            beneficiary=bene_data,
            amount=amount,
            currency=currency,
            purpose=purpose,
            reference=reference,
            value_date=value_date,
        )

        pkg.instructions.append(instruction)
        return pkg

    def _build_instruction(
        self,
        instr_id: str,
        originator: dict,
        beneficiary: dict,
        amount: float,
        currency: str,
        purpose: str,
        reference: str,
        value_date: str,
    ) -> WireInstruction:
        """Build a single wire instruction from entity data."""
        o = originator.get("entity", originator)
        b = beneficiary.get("entity", beneficiary)
        o_bank = o.get("banking", {})
        b_bank = b.get("banking", {})

        # Build originator party
        orig_party = WireParty(
            party_type="originator",
            entity_name=o.get("legal_name", "Unknown"),
            bank_name=o_bank.get("settlement_bank", "") or "",
            swift_code=o_bank.get("swift_code", "") or "",
            aba_routing=o_bank.get("aba_routing", "") or "",
            account_number=o_bank.get("account_number", "") or o_bank.get("beneficiary_account_number", "") or "",
            account_name=o_bank.get("ultimate_beneficiary_name", "") or "",
            country=o.get("jurisdiction", "")[:2] if o.get("jurisdiction") else "",
        )

        # Build beneficiary party
        bene_party = WireParty(
            party_type="beneficiary",
            entity_name=b.get("legal_name", "Unknown"),
            bank_name=b_bank.get("settlement_bank", "") or "",
            swift_code=b_bank.get("swift_code", "") or "",
            aba_routing=b_bank.get("aba_routing", "") or "",
            account_number=b_bank.get("account_number", "") or b_bank.get("beneficiary_account_number", "") or "",
            account_name=b_bank.get("ultimate_beneficiary_name", "") or "",
            country=b.get("jurisdiction", "")[:2] if b.get("jurisdiction") else "",
        )

        # Resolve settlement path for FX / intermediary analysis
        path = self.banking_engine.resolve_settlement_path(
            originator, beneficiary, currency
        )

        # Build intermediary if path has a correspondent node
        intermediary = None
        for node in path.nodes:
            if node.role in ("correspondent", "partner_bank"):
                intermediary = WireParty(
                    party_type="intermediary",
                    entity_name=node.name,
                    bank_name=node.name,
                    swift_code=node.swift_code or "",
                    aba_routing=node.aba_routing or "",
                    country=node.country,
                )
                break

        instruction = WireInstruction(
            instruction_id=instr_id,
            originator=orig_party,
            beneficiary=bene_party,
            intermediary=intermediary,
            amount=amount,
            currency=currency,
            value_date=value_date,
            purpose=purpose,
            reference=reference or f"{orig_party.entity_name[:10]}-{bene_party.entity_name[:10]}-{currency}",
            fx_required=path.requires_fx,
            fx_settlement_currency=currency if not path.requires_fx else "",
        )

        # Run compliance checks
        self._check_compliance(instruction, originator, beneficiary, path)

        return instruction

    def _check_compliance(
        self,
        instruction: WireInstruction,
        originator: dict,
        beneficiary: dict,
        path: SettlementPath,
    ) -> None:
        """Run compliance checks on the wire instruction."""
        o = originator.get("entity", originator)
        b = beneficiary.get("entity", beneficiary)

        # Sanctions screening
        for ent, label in [(o, "originator"), (b, "beneficiary")]:
            jur = ent.get("jurisdiction", "")[:2].upper()
            if jur in SANCTIONED_JURISDICTIONS:
                instruction.compliance_notes.append(ComplianceNote(
                    category="sanctions",
                    severity="BLOCK",
                    description=f"{label.title()} jurisdiction ({jur}) is on sanctioned list.",
                ))

        # Missing banking data warnings
        if not instruction.originator.bank_name:
            instruction.compliance_notes.append(ComplianceNote(
                category="regulatory",
                severity="WARNING",
                description="Originator has no settlement bank assigned.",
            ))

        if not instruction.beneficiary.bank_name:
            instruction.compliance_notes.append(ComplianceNote(
                category="regulatory",
                severity="WARNING",
                description="Beneficiary has no settlement bank assigned.",
            ))

        if not instruction.originator.swift_code and not instruction.originator.aba_routing:
            instruction.compliance_notes.append(ComplianceNote(
                category="regulatory",
                severity="WARNING",
                description="Originator has no SWIFT/BIC or ABA routing number.",
            ))

        if not instruction.beneficiary.swift_code and not instruction.beneficiary.aba_routing:
            instruction.compliance_notes.append(ComplianceNote(
                category="regulatory",
                severity="WARNING",
                description="Beneficiary has no SWIFT/BIC or ABA routing number.",
            ))

        # Settlement path issues
        if not path.is_valid:
            for issue in path.validation_issues:
                instruction.compliance_notes.append(ComplianceNote(
                    category="regulatory",
                    severity="WARNING",
                    description=f"Settlement path: {issue}",
                ))

        # FX controls
        if path.fx_approval_required:
            instruction.compliance_notes.append(ComplianceNote(
                category="fx_controls",
                severity="WARNING",
                description=f"FX approval required from {path.fx_authority}.",
            ))

        # Amount validation
        if instruction.amount <= 0:
            instruction.compliance_notes.append(ComplianceNote(
                category="regulatory",
                severity="INFO",
                description="Wire amount is zero or not specified. Update before execution.",
            ))

        # Beneficial owner screening
        for ent, label in [(o, "originator"), (b, "beneficiary")]:
            owners = ent.get("beneficial_owners", [])
            unscreened = [
                bo for bo in owners
                if not bo.get("sanctions_screened", False)
            ]
            if unscreened:
                instruction.compliance_notes.append(ComplianceNote(
                    category="aml",
                    severity="WARNING",
                    description=f"{label.title()} has {len(unscreened)} unscreened beneficial owner(s).",
                ))

    def save(self, package: WireInstructionPackage) -> Path:
        """Persist wire instruction package to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = package.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"wires_{name}_{ts}.json"
        path.write_text(json.dumps(package.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
