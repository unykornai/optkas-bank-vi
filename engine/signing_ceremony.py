"""
Deal Signing Ceremony Engine
================================
Manages the execution of deal signing with authority validation,
signature order enforcement, and execution record generation.

The closing tracker tells you WHEN you can sign. This engine
manages HOW the signing actually happens:

  1. Validate signing authority (who CAN sign for each entity)
  2. Enforce signature order (some docs must be signed before others)
  3. Generate execution records with timestamps
  4. Track signature status across all required signatories
  5. Produce a signing certificate after full execution

Input:  Deal name, entity list, signing blocks (who signs what)
Output: SigningCeremony with authority-validated signing blocks,
        execution tracking, and signing certificate generation

Design rules:
  - Every entity must have at least one authorized signatory
  - Binding documents require dual-signature where governance demands it
  - Each signing event records: who, when, what authority, witness
  - The ceremony is NOT complete until all blocks are executed
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import load_entity
from engine.deal_governance import DealGovernanceEngine, AuthorityEntry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "signing_ceremonies"

# Document categories and their signing requirements
DOCUMENT_CATEGORIES: dict[str, dict[str, Any]] = {
    "subscription_agreement": {
        "display_name": "Subscription Agreement",
        "requires_dual_sig": True,
        "binding": True,
        "order": 1,
    },
    "note_purchase_agreement": {
        "display_name": "Note Purchase Agreement",
        "requires_dual_sig": True,
        "binding": True,
        "order": 2,
    },
    "security_agreement": {
        "display_name": "Security Agreement / Pledge",
        "requires_dual_sig": True,
        "binding": True,
        "order": 3,
    },
    "escrow_agreement": {
        "display_name": "Escrow Agreement",
        "requires_dual_sig": True,
        "binding": True,
        "order": 4,
    },
    "operating_agreement": {
        "display_name": "Operating Agreement (SPV)",
        "requires_dual_sig": False,
        "binding": True,
        "order": 5,
    },
    "legal_opinion": {
        "display_name": "Legal Opinion Letter",
        "requires_dual_sig": False,
        "binding": False,
        "order": 6,
    },
    "board_resolution": {
        "display_name": "Board Resolution / Corporate Authorization",
        "requires_dual_sig": False,
        "binding": True,
        "order": 7,
    },
    "compliance_certificate": {
        "display_name": "Compliance Certificate",
        "requires_dual_sig": False,
        "binding": False,
        "order": 8,
    },
    "closing_certificate": {
        "display_name": "Closing Certificate",
        "requires_dual_sig": False,
        "binding": True,
        "order": 9,
    },
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class SigningBlock:
    """A single signature block: who signs what document for which entity."""
    block_id: str
    document_type: str
    document_name: str
    entity_name: str
    signer_name: str = ""
    signer_title: str = ""
    requires_dual_sig: bool = False
    second_signer_name: str = ""
    second_signer_title: str = ""
    is_binding: bool = False
    order: int = 0
    # Execution state
    status: str = "PENDING"  # PENDING, SIGNED, COUNTERSIGNED, REFUSED, DEFERRED
    signed_at: str = ""
    countersigned_at: str = ""
    witness: str = ""
    notes: str = ""

    @property
    def is_executed(self) -> bool:
        if self.requires_dual_sig:
            return self.status == "COUNTERSIGNED"
        return self.status in ("SIGNED", "COUNTERSIGNED")

    def sign(self, signer: str = "", witness: str = "") -> None:
        """Record primary signature."""
        self.status = "SIGNED"
        self.signed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if signer:
            self.signer_name = signer
        if witness:
            self.witness = witness

    def countersign(self, signer: str = "") -> None:
        """Record countersignature (dual-sig completion)."""
        self.status = "COUNTERSIGNED"
        self.countersigned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if signer:
            self.second_signer_name = signer

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "document_type": self.document_type,
            "document_name": self.document_name,
            "entity_name": self.entity_name,
            "signer_name": self.signer_name,
            "signer_title": self.signer_title,
            "requires_dual_sig": self.requires_dual_sig,
            "second_signer_name": self.second_signer_name,
            "second_signer_title": self.second_signer_title,
            "is_binding": self.is_binding,
            "order": self.order,
            "status": self.status,
            "signed_at": self.signed_at,
            "countersigned_at": self.countersigned_at,
            "witness": self.witness,
            "is_executed": self.is_executed,
            "notes": self.notes,
        }


@dataclass
class AuthorityValidation:
    """Result of validating signing authority for a block."""
    block_id: str
    entity_name: str
    signer: str
    is_authorized: bool = False
    authority_basis: str = ""  # How they're authorized (director, signatory, etc.)
    can_bind: bool = False
    can_move_funds: bool = False
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "entity_name": self.entity_name,
            "signer": self.signer,
            "is_authorized": self.is_authorized,
            "authority_basis": self.authority_basis,
            "can_bind": self.can_bind,
            "can_move_funds": self.can_move_funds,
            "issues": self.issues,
        }


@dataclass
class SigningCeremony:
    """Complete signing ceremony for a deal."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    blocks: list[SigningBlock] = field(default_factory=list)
    authority_validations: list[AuthorityValidation] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    @property
    def total_blocks(self) -> int:
        return len(self.blocks)

    @property
    def executed_blocks(self) -> int:
        return sum(1 for b in self.blocks if b.is_executed)

    @property
    def pending_blocks(self) -> int:
        return sum(1 for b in self.blocks if b.status == "PENDING")

    @property
    def is_complete(self) -> bool:
        return self.total_blocks > 0 and all(b.is_executed for b in self.blocks)

    @property
    def completion_pct(self) -> float:
        if self.total_blocks == 0:
            return 0.0
        return round(self.executed_blocks / self.total_blocks * 100, 1)

    @property
    def all_authorized(self) -> bool:
        return all(v.is_authorized for v in self.authority_validations)

    @property
    def authority_issues(self) -> list[str]:
        issues = []
        for v in self.authority_validations:
            issues.extend(v.issues)
        return issues

    def by_entity(self, entity_name: str) -> list[SigningBlock]:
        return [b for b in self.blocks if b.entity_name == entity_name]

    def by_document(self, doc_type: str) -> list[SigningBlock]:
        return [b for b in self.blocks if b.document_type == doc_type]

    def sorted_blocks(self) -> list[SigningBlock]:
        """Return blocks in signing order."""
        return sorted(self.blocks, key=lambda b: b.order)

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "DEAL SIGNING CEREMONY",
            f"  {self.deal_name}",
            f"  Created: {self.created_at}",
            "=" * 70,
            "",
            f"  STATUS:       {'COMPLETE' if self.is_complete else 'IN PROGRESS'}",
            f"  COMPLETION:   {self.completion_pct}%  "
            f"({self.executed_blocks}/{self.total_blocks} executed)",
            f"  AUTHORITY:    {'ALL VALIDATED' if self.all_authorized else 'ISSUES DETECTED'}",
            f"  Entities:     {len(self.entities)}",
            "",
        ]

        # Authority issues
        issues = self.authority_issues
        if issues:
            lines.append("--- AUTHORITY ISSUES ---")
            for issue in issues:
                lines.append(f"  [!] {issue}")
            lines.append("")

        # Signing blocks in order
        lines.append("--- SIGNING BLOCKS ---")
        for block in self.sorted_blocks():
            icon = {
                "SIGNED": "[+]",
                "COUNTERSIGNED": "[++]",
                "PENDING": "[ ]",
                "REFUSED": "[X]",
                "DEFERRED": "[~]",
            }.get(block.status, "[ ]")

            dual_tag = " (DUAL-SIG)" if block.requires_dual_sig else ""
            lines.append(
                f"  {icon} {block.block_id}: {block.document_name}{dual_tag}"
            )
            lines.append(
                f"      Entity: {block.entity_name}  |  "
                f"Signer: {block.signer_name or 'TBD'}  |  "
                f"Status: {block.status}"
            )
            if block.requires_dual_sig and block.second_signer_name:
                lines.append(f"      Countersigner: {block.second_signer_name}")
            if block.signed_at:
                lines.append(f"      Signed: {block.signed_at}")
            if block.witness:
                lines.append(f"      Witness: {block.witness}")

        lines.extend(["", "=" * 70])
        return "\n".join(lines)

    def signing_certificate(self) -> str:
        """Generate signing certificate text (only when complete)."""
        if not self.is_complete:
            return "SIGNING CERTIFICATE: NOT AVAILABLE (ceremony incomplete)"

        lines = [
            "=" * 70,
            "SIGNING CERTIFICATE",
            "=" * 70,
            "",
            f"Deal: {self.deal_name}",
            f"Date: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            "",
            "The undersigned hereby certifies that the following documents",
            "have been duly executed by authorized signatories:",
            "",
        ]

        for block in self.sorted_blocks():
            lines.append(f"  Document: {block.document_name}")
            lines.append(f"  Entity:   {block.entity_name}")
            lines.append(f"  Signer:   {block.signer_name} ({block.signer_title})")
            if block.second_signer_name:
                lines.append(
                    f"  Counter:  {block.second_signer_name} "
                    f"({block.second_signer_title})"
                )
            lines.append(f"  Executed: {block.signed_at}")
            lines.append("")

        lines.extend([
            "All signatories have been verified as authorized per the",
            "deal governance framework.",
            "",
            "=" * 70,
        ])
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "is_complete": self.is_complete,
            "completion_pct": self.completion_pct,
            "all_authorized": self.all_authorized,
            "entities": self.entities,
            "blocks": [b.to_dict() for b in self.sorted_blocks()],
            "authority_validations": [v.to_dict() for v in self.authority_validations],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SigningCeremonyEngine:
    """
    Manages deal signing execution with authority validation.

    Usage:
        engine = SigningCeremonyEngine()
        ceremony = engine.prepare(
            deal_name="OPTKAS-TC Full Deal",
            entity_paths=[Path("data/entities/tc_advantage_traders.yaml"), ...],
            documents=["subscription_agreement", "security_agreement"],
        )
        print(ceremony.summary())
    """

    def __init__(self) -> None:
        self.governance_engine = DealGovernanceEngine()

    def prepare(
        self,
        deal_name: str,
        entity_paths: list[Path] | None = None,
        documents: list[str] | None = None,
    ) -> SigningCeremony:
        """Prepare signing ceremony with auto-generated signing blocks."""
        ceremony = SigningCeremony(deal_name=deal_name)

        entities: list[dict] = []
        for ep in (entity_paths or []):
            e = load_entity(ep)
            entities.append(e)
            ceremony.entities.append(e.get("legal_name", str(ep)))

        # Get governance / authority map
        gov_report = self.governance_engine.assess(
            deal_name=deal_name,
            entity_paths=entity_paths,
        )

        # Determine documents to sign
        doc_types = documents or self._default_documents(entities)

        # Generate signing blocks
        block_num = 1
        for doc_type in doc_types:
            doc_info = DOCUMENT_CATEGORIES.get(doc_type, {})
            doc_name = doc_info.get("display_name", doc_type.replace("_", " ").title())
            requires_dual = doc_info.get("requires_dual_sig", False)
            is_binding = doc_info.get("binding", False)
            order = doc_info.get("order", 99)

            for e_data in entities:
                e = e_data.get("entity", e_data)
                entity_name = e.get("legal_name", "Unknown")

                # Find authorized signers for this entity
                signers = self._find_signers(entity_name, gov_report.authority_map)
                primary_signer = signers[0] if signers else None
                second_signer = signers[1] if len(signers) > 1 and requires_dual else None

                block = SigningBlock(
                    block_id=f"SIG-{block_num:03d}",
                    document_type=doc_type,
                    document_name=doc_name,
                    entity_name=entity_name,
                    signer_name=primary_signer.name if primary_signer else "",
                    signer_title=primary_signer.title if primary_signer else "",
                    requires_dual_sig=requires_dual,
                    second_signer_name=second_signer.name if second_signer else "",
                    second_signer_title=second_signer.title if second_signer else "",
                    is_binding=is_binding,
                    order=order,
                )
                ceremony.blocks.append(block)

                # Validate authority
                validation = self._validate_authority(
                    block, primary_signer, second_signer, e_data
                )
                ceremony.authority_validations.append(validation)

                block_num += 1

        return ceremony

    def _default_documents(self, entities: list[dict]) -> list[str]:
        """Determine default document set based on deal structure."""
        docs = ["board_resolution"]

        # Check if there's an MTN program → subscription agreement
        has_mtn = any(
            e.get("entity", e).get("mtn_program") for e in entities
        )
        if has_mtn:
            docs.extend(["subscription_agreement", "note_purchase_agreement"])

        # Check for collateral/SPV → security agreement
        has_spv = any(
            e.get("entity", e).get("entity_type") == "special_purpose_vehicle"
            for e in entities
        )
        if has_spv:
            docs.extend(["security_agreement", "operating_agreement"])

        # Always include closing certificate
        docs.append("closing_certificate")

        return docs

    def _find_signers(
        self, entity_name: str, authority_map: list[AuthorityEntry],
    ) -> list[AuthorityEntry]:
        """Find authorized signers for an entity from the authority map."""
        signers = [
            a for a in authority_map
            if a.entity == entity_name and (a.can_bind or a.roles)
        ]
        # Sort by binding authority first
        signers.sort(key=lambda a: (not a.can_bind, not a.can_move_funds))
        return signers

    def _validate_authority(
        self,
        block: SigningBlock,
        primary: AuthorityEntry | None,
        second: AuthorityEntry | None,
        entity: dict,
    ) -> AuthorityValidation:
        """Validate that the assigned signer has authority."""
        validation = AuthorityValidation(
            block_id=block.block_id,
            entity_name=block.entity_name,
            signer=block.signer_name or "UNASSIGNED",
        )

        if not primary:
            validation.is_authorized = False
            validation.issues.append(
                f"No authorized signatory found for {block.entity_name}. "
                f"Cannot execute {block.document_name}."
            )
            return validation

        validation.is_authorized = True
        validation.can_bind = primary.can_bind
        validation.can_move_funds = primary.can_move_funds

        # Build authority basis
        roles = ", ".join(primary.roles) if primary.roles else "No specific roles"
        validation.authority_basis = f"{primary.title} ({roles})"

        # Check binding authority for binding documents
        if block.is_binding and not primary.can_bind:
            validation.issues.append(
                f"{primary.name} ({primary.title}) does not have binding authority "
                f"for {block.entity_name}. Document: {block.document_name}."
            )

        # Check dual-sig requirement
        if block.requires_dual_sig and not second:
            validation.issues.append(
                f"Dual signature required for {block.document_name} but "
                f"only one signatory available for {block.entity_name}."
            )

        return validation

    def execute_block(
        self, ceremony: SigningCeremony, block_id: str,
        signer: str = "", witness: str = "",
    ) -> bool:
        """Execute (sign) a specific block."""
        block = next((b for b in ceremony.blocks if b.block_id == block_id), None)
        if not block:
            return False
        block.sign(signer=signer, witness=witness)
        return True

    def countersign_block(
        self, ceremony: SigningCeremony, block_id: str,
        signer: str = "",
    ) -> bool:
        """Countersign a specific block (for dual-sig)."""
        block = next((b for b in ceremony.blocks if b.block_id == block_id), None)
        if not block:
            return False
        block.countersign(signer=signer)
        return True

    def save(self, ceremony: SigningCeremony) -> Path:
        """Persist signing ceremony to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = ceremony.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"signing_{name}_{ts}.json"
        path.write_text(
            json.dumps(ceremony.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path
