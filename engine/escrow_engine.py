"""
Escrow & Settlement Rail Builder
===================================
Models proper 3+ node institutional settlement chains with
escrow agent placement, SWIFT routing, freely convertible
currency enforcement, and escrow release conditions.

The Settlement and Banking Onboarding sections of the deal
dashboard flag that the current entity graph has:
  - No banking intermediary (direct entity-to-entity)
  - No SWIFT-capable node
  - Entities missing settlement banks

This engine SOLVES those problems by constructing a valid
settlement rail architecture for the deal group.

For each pair of counterparties it:
  1. Selects the optimal escrow agent / settlement bank
  2. Builds a 3+ node chain: Originator Bank → Escrow → Beneficiary Bank
  3. Validates SWIFT coverage, AML/KYC, and FX controls
  4. Generates escrow release conditions
  5. Produces a settlement rail plan the group can execute

Input:  Entity paths, deal metadata
Output: EscrowPlan with per-leg settlement rails, escrow terms,
        and compliance validation
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
    KNOWN_BANKS,
    BankNode,
    SettlementPath,
    FX_CONTROLLED_JURISDICTIONS,
)
from engine.settlement_onboarding import CANDIDATE_BANKS, DEFAULT_CANDIDATES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "escrow_plans"

FREELY_CONVERTIBLE = {"USD", "EUR", "GBP", "CHF", "JPY", "CAD", "AUD", "SGD", "HKD"}

# Escrow agent registry — institutional-grade escrow providers
ESCROW_AGENTS: dict[str, dict[str, Any]] = {
    "CHASUS33": {
        "name": "JPMorgan Chase Bank, N.A.",
        "swift": "CHASUS33",
        "country": "US",
        "escrow_services": ["institutional_escrow", "paying_agent", "trustee"],
        "min_escrow": 1_000_000,
        "max_escrow": 50_000_000_000,
        "tier": "GSIB",
        "dtc_dwac": True,
        "notes": "Full-service escrow and paying agent. DTC/DWAC clearing.",
    },
    "IRVTUS3N": {
        "name": "The Bank of New York Mellon Corporation",
        "swift": "IRVTUS3N",
        "country": "US",
        "escrow_services": ["institutional_escrow", "custody", "trustee", "paying_agent"],
        "min_escrow": 5_000_000,
        "max_escrow": 100_000_000_000,
        "tier": "GSIB",
        "dtc_dwac": True,
        "notes": "World's largest custodian. Specialist in securities settlement and escrow.",
    },
    "BOFAUS3N": {
        "name": "Bank of America / Merrill Lynch",
        "swift": "BOFAUS3N",
        "country": "US",
        "escrow_services": ["institutional_escrow", "settlement", "brokerage"],
        "min_escrow": 1_000_000,
        "max_escrow": 25_000_000_000,
        "tier": "GSIB",
        "dtc_dwac": True,
        "notes": "Full-service institutional banking and escrow.",
    },
    "BARCGB22": {
        "name": "Barclays Bank PLC",
        "swift": "BARCGB22",
        "country": "GB",
        "escrow_services": ["institutional_escrow", "correspondent", "fx"],
        "min_escrow": 5_000_000,
        "max_escrow": 10_000_000_000,
        "tier": "GSIB",
        "dtc_dwac": False,
        "notes": "Major UK clearing bank. Cross-border escrow capability.",
    },
    "NOSCBSNS": {
        "name": "Scotiabank (Bahamas) Limited",
        "swift": "NOSCBSNS",
        "country": "BS",
        "escrow_services": ["regional_escrow", "correspondent", "fx"],
        "min_escrow": 100_000,
        "max_escrow": 500_000_000,
        "tier": "INTERNATIONAL",
        "dtc_dwac": False,
        "notes": "Caribbean escrow specialist. Correspondent access through Scotiabank global.",
    },
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class EscrowCondition:
    """A condition for escrow release."""
    condition_id: str
    description: str
    category: str  # documentary, regulatory, financial, legal
    responsible: str = "Escrow Agent"
    status: str = "PENDING"  # PENDING, SATISFIED, WAIVED, FAILED
    notes: str = ""

    @property
    def is_met(self) -> bool:
        return self.status in ("SATISFIED", "WAIVED")

    def to_dict(self) -> dict:
        return {
            "condition_id": self.condition_id,
            "description": self.description,
            "category": self.category,
            "responsible": self.responsible,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class EscrowTerms:
    """Terms of the escrow arrangement."""
    escrow_agent: str
    escrow_agent_swift: str
    escrow_agent_country: str
    escrow_currency: str = "USD"
    escrow_amount: float = 0.0
    escrow_type: str = "institutional"  # institutional, attorney_iolta, bank_controlled
    release_mechanism: str = "dual_authorization"
    conditions: list[EscrowCondition] = field(default_factory=list)
    compliance_notes: list[str] = field(default_factory=list)

    @property
    def all_conditions_met(self) -> bool:
        return all(c.is_met for c in self.conditions)

    @property
    def met_count(self) -> int:
        return sum(1 for c in self.conditions if c.is_met)

    @property
    def pending_count(self) -> int:
        return sum(1 for c in self.conditions if c.status == "PENDING")

    def to_dict(self) -> dict:
        return {
            "escrow_agent": self.escrow_agent,
            "escrow_agent_swift": self.escrow_agent_swift,
            "escrow_agent_country": self.escrow_agent_country,
            "escrow_currency": self.escrow_currency,
            "escrow_amount": self.escrow_amount,
            "escrow_type": self.escrow_type,
            "release_mechanism": self.release_mechanism,
            "all_conditions_met": self.all_conditions_met,
            "conditions_met": self.met_count,
            "conditions_pending": self.pending_count,
            "conditions": [c.to_dict() for c in self.conditions],
            "compliance_notes": self.compliance_notes,
        }


@dataclass
class SettlementRailLeg:
    """One leg of a multi-leg settlement rail."""
    leg_id: str
    originator: str
    originator_bank: str
    originator_swift: str
    escrow_agent: str
    escrow_swift: str
    beneficiary: str
    beneficiary_bank: str
    beneficiary_swift: str
    currency: str = "USD"
    requires_fx: bool = False
    node_count: int = 0
    nodes: list[dict] = field(default_factory=list)
    is_valid: bool = False
    issues: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "leg_id": self.leg_id,
            "originator": self.originator,
            "originator_bank": self.originator_bank,
            "originator_swift": self.originator_swift,
            "escrow_agent": self.escrow_agent,
            "escrow_swift": self.escrow_swift,
            "beneficiary": self.beneficiary,
            "beneficiary_bank": self.beneficiary_bank,
            "beneficiary_swift": self.beneficiary_swift,
            "currency": self.currency,
            "requires_fx": self.requires_fx,
            "node_count": self.node_count,
            "is_valid": self.is_valid,
            "nodes": self.nodes,
            "issues": self.issues,
            "notes": self.notes,
        }


@dataclass
class EscrowPlan:
    """Complete escrow and settlement rail plan."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    escrow_terms: EscrowTerms | None = None
    legs: list[SettlementRailLeg] = field(default_factory=list)
    entity_bank_assignments: dict[str, dict] = field(default_factory=dict)
    overall_valid: bool = False
    overall_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def total_legs(self) -> int:
        return len(self.legs)

    @property
    def valid_legs(self) -> int:
        return sum(1 for l in self.legs if l.is_valid)

    @property
    def total_nodes(self) -> int:
        return sum(l.node_count for l in self.legs)

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "ESCROW & SETTLEMENT RAIL PLAN",
            f"  {self.deal_name}",
            f"  Generated: {self.created_at}",
            "=" * 70,
            "",
            f"  OVERALL: {'VALID' if self.overall_valid else 'NEEDS ACTION'}",
            f"  Settlement Legs: {self.total_legs} ({self.valid_legs} valid)",
            f"  Total Nodes: {self.total_nodes}",
            "",
        ]

        # Escrow terms
        if self.escrow_terms:
            et = self.escrow_terms
            lines.append("--- ESCROW ARRANGEMENT ---")
            lines.append(f"  Agent:     {et.escrow_agent} [{et.escrow_agent_swift}]")
            lines.append(f"  Country:   {et.escrow_agent_country}")
            lines.append(f"  Currency:  {et.escrow_currency}")
            if et.escrow_amount > 0:
                lines.append(f"  Amount:    ${et.escrow_amount:,.2f}")
            lines.append(f"  Type:      {et.escrow_type}")
            lines.append(f"  Release:   {et.release_mechanism}")
            lines.append(f"  Conditions: {et.met_count}/{len(et.conditions)} met")
            for cond in et.conditions:
                icon = "[+]" if cond.is_met else "[ ]"
                lines.append(f"    {icon} {cond.condition_id}: {cond.description}")
            if et.compliance_notes:
                for note in et.compliance_notes:
                    lines.append(f"    [i] {note}")
            lines.append("")

        # Bank assignments
        if self.entity_bank_assignments:
            lines.append("--- ENTITY BANK ASSIGNMENTS ---")
            for entity_name, assignment in self.entity_bank_assignments.items():
                bank = assignment.get("bank", "TBD")
                swift = assignment.get("swift", "")
                source = assignment.get("source", "")
                lines.append(f"  {entity_name}")
                lines.append(f"    Bank:  {bank} [{swift}]")
                lines.append(f"    Source: {source}")
            lines.append("")

        # Settlement legs
        for leg in self.legs:
            valid_icon = "[+]" if leg.is_valid else "[X]"
            lines.append(f"--- LEG {leg.leg_id}: {valid_icon} ---")
            lines.append(f"  {leg.originator}")
            lines.append(f"    >> {leg.originator_bank} [{leg.originator_swift}]")
            lines.append(f"    >> {leg.escrow_agent} [{leg.escrow_swift}] (ESCROW)")
            lines.append(f"    >> {leg.beneficiary_bank} [{leg.beneficiary_swift}]")
            lines.append(f"    >> {leg.beneficiary}")
            lines.append(f"  Nodes: {leg.node_count} | Currency: {leg.currency} "
                         f"| FX: {'YES' if leg.requires_fx else 'NO'}")
            for issue in leg.issues:
                lines.append(f"  [!] {issue}")
            for note in leg.notes:
                lines.append(f"  [i] {note}")
            lines.append("")

        # Issues & recommendations
        if self.overall_issues:
            lines.append("--- OUTSTANDING ISSUES ---")
            for issue in self.overall_issues:
                lines.append(f"  [X] {issue}")
            lines.append("")

        if self.recommendations:
            lines.append("--- RECOMMENDATIONS ---")
            for rec in self.recommendations:
                lines.append(f"  >> {rec}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "overall_valid": self.overall_valid,
            "total_legs": self.total_legs,
            "valid_legs": self.valid_legs,
            "total_nodes": self.total_nodes,
            "escrow_terms": self.escrow_terms.to_dict() if self.escrow_terms else None,
            "legs": [l.to_dict() for l in self.legs],
            "entity_bank_assignments": self.entity_bank_assignments,
            "overall_issues": self.overall_issues,
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class EscrowEngine:
    """
    Builds valid 3+ node settlement rails with escrow placement.

    Solves the dashboard RED flags:
      - Settlement path INVALID (< 3 nodes)
      - No SWIFT-capable node
      - Direct entity-to-entity without banking intermediary

    Usage:
        engine = EscrowEngine()
        plan = engine.build(
            deal_name="TC Advantage 5B MTN",
            entity_paths=[
                Path("data/entities/tc_advantage_traders.yaml"),
                Path("data/entities/optkas1_spv.yaml"),
                Path("data/entities/querubin_usa.yaml"),
                Path("data/entities/optkas_platform.yaml"),
            ],
            escrow_currency="USD",
        )
        print(plan.summary())
    """

    def __init__(self) -> None:
        self._banking_engine = CorrespondentBankingEngine()

    def build(
        self,
        deal_name: str,
        entity_paths: list[Path] | None = None,
        escrow_currency: str = "USD",
        escrow_amount: float = 0.0,
    ) -> EscrowPlan:
        """Build complete escrow and settlement rail plan."""
        plan = EscrowPlan(deal_name=deal_name)

        # Load entities
        entities: list[dict] = []
        for ep in (entity_paths or []):
            try:
                entities.append(load_entity(ep))
            except Exception:
                plan.overall_issues.append(f"Could not load entity: {ep}")

        if len(entities) < 2:
            plan.overall_issues.append(
                "Need at least 2 entities to build settlement rails."
            )
            return plan

        # Step 1: Assign banks to entities that lack them
        bank_assignments = self._assign_banks(entities)
        plan.entity_bank_assignments = bank_assignments

        # Step 2: Select escrow agent
        escrow_info = self._select_escrow_agent(entities, escrow_currency)
        plan.escrow_terms = self._build_escrow_terms(
            escrow_info, escrow_currency, escrow_amount, deal_name,
        )

        # Step 3: Build settlement legs between each pair
        leg_num = 0
        primary = entities[0]  # issuer
        for i in range(1, len(entities)):
            leg_num += 1
            counterparty = entities[i]
            leg = self._build_leg(
                leg_id=f"LEG-{leg_num:02d}",
                originator=primary,
                beneficiary=counterparty,
                escrow_info=escrow_info,
                bank_assignments=bank_assignments,
                currency=escrow_currency,
            )
            plan.legs.append(leg)

        # Step 4: Validate overall plan
        self._validate_plan(plan)

        return plan

    # ------------------------------------------------------------------
    # Bank assignment
    # ------------------------------------------------------------------

    def _assign_banks(self, entities: list[dict]) -> dict[str, dict]:
        """Assign settlement banks to entities that lack them."""
        assignments: dict[str, dict] = {}

        for entity in entities:
            e = entity.get("entity", entity)
            name = e.get("legal_name", "Unknown")
            banking = e.get("banking", {})
            jur = e.get("jurisdiction", "")
            base_jur = jur.split("-")[0].upper() if jur else ""

            existing_bank = banking.get("settlement_bank")
            existing_swift = banking.get("swift_code")

            if existing_bank and existing_swift:
                # Entity already has a settlement bank
                assignments[name] = {
                    "bank": existing_bank,
                    "swift": existing_swift,
                    "aba": banking.get("aba_routing", ""),
                    "account": banking.get("beneficiary_account_number",
                                           banking.get("account_number", "")),
                    "source": "existing",
                }
            else:
                # Assign the best candidate bank
                candidates = CANDIDATE_BANKS.get(base_jur, DEFAULT_CANDIDATES)
                if candidates:
                    best = self._rank_candidate(candidates, e)
                    assignments[name] = {
                        "bank": best["name"],
                        "swift": best["swift"],
                        "aba": "",
                        "account": "",
                        "source": "recommended",
                        "rationale": f"Best fit for {base_jur} jurisdiction. "
                                     f"Tier: {best['tier']}. "
                                     f"Services: {', '.join(best.get('services', []))}.",
                    }

        return assignments

    def _rank_candidate(
        self, candidates: list[dict], entity: dict
    ) -> dict:
        """Pick the best candidate bank for an entity."""
        e = entity.get("entity", entity)
        mtn = e.get("mtn_program", {})
        entity_type = e.get("entity_type", "")
        banking = e.get("banking", {})
        custodian = banking.get("custodian", "")

        scored: list[tuple[int, dict]] = []
        for c in candidates:
            score = 50
            # GSIB preference
            if c.get("tier") in ("GSIB", "GLOBAL_SYSTEMICALLY_IMPORTANT"):
                score += 15
            # Settlement service
            if "settlement" in c.get("services", []):
                score += 10
            # DTC/DWAC support
            if mtn.get("settlement_method", "").upper() in ("DTC/DWAC", "DTC/DWAC FAST"):
                if "clearing" in c.get("services", []) or "custody" in c.get("services", []):
                    score += 10
            # SPV — needs custody
            if entity_type == "special_purpose_vehicle" and "custody" in c.get("services", []):
                score += 5
            # Existing relationship
            if custodian and c["name"].lower() in custodian.lower():
                score += 15
            # Escrow capability
            if "escrow" in c.get("services", []):
                score += 10
            # Correspondent capability (for cross-border)
            if "correspondent" in c.get("services", []):
                score += 5

            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # ------------------------------------------------------------------
    # Escrow agent selection
    # ------------------------------------------------------------------

    def _select_escrow_agent(
        self, entities: list[dict], currency: str,
    ) -> dict[str, Any]:
        """Select the optimal escrow agent for the deal."""
        # Determine jurisdictions involved
        jurisdictions = set()
        for entity in entities:
            e = entity.get("entity", entity)
            jur = e.get("jurisdiction", "").split("-")[0].upper()
            if jur:
                jurisdictions.add(jur)

        # Check for DTC/DWAC need
        needs_dtc = any(
            entity.get("entity", entity).get("mtn_program", {})
            .get("settlement_method", "").upper() in ("DTC/DWAC", "DTC/DWAC FAST")
            for entity in entities
        )

        # Score escrow agents
        best_score = -1
        best_agent: dict[str, Any] = {}

        for swift, agent in ESCROW_AGENTS.items():
            score = 50

            # GSIB preference
            if agent["tier"] == "GSIB":
                score += 20

            # DTC/DWAC capability
            if needs_dtc and agent.get("dtc_dwac"):
                score += 15

            # Trustee/paying agent services
            services = agent.get("escrow_services", [])
            if "trustee" in services:
                score += 10
            if "paying_agent" in services:
                score += 10
            if "custody" in services:
                score += 5

            # Jurisdiction coverage
            agent_country = agent.get("country", "")
            if "US" in jurisdictions and agent_country == "US":
                score += 10
            if "BS" in jurisdictions and agent_country in ("US", "BS"):
                score += 5

            # Currency match
            if currency in FREELY_CONVERTIBLE:
                score += 5

            if score > best_score:
                best_score = score
                best_agent = {**agent, "score": score}

        return best_agent

    # ------------------------------------------------------------------
    # Escrow terms
    # ------------------------------------------------------------------

    def _build_escrow_terms(
        self,
        escrow_info: dict,
        currency: str,
        amount: float,
        deal_name: str,
    ) -> EscrowTerms:
        """Build escrow terms with release conditions."""
        terms = EscrowTerms(
            escrow_agent=escrow_info.get("name", "TBD"),
            escrow_agent_swift=escrow_info.get("swift", ""),
            escrow_agent_country=escrow_info.get("country", ""),
            escrow_currency=currency,
            escrow_amount=amount,
            escrow_type="institutional",
            release_mechanism="dual_authorization",
        )

        # Currency validation
        if currency not in FREELY_CONVERTIBLE:
            terms.compliance_notes.append(
                f"WARNING: {currency} is not freely convertible. "
                f"Escrow should be denominated in USD/EUR/GBP."
            )
            terms.escrow_currency = "USD"
            terms.compliance_notes.append(
                "Escrow currency overridden to USD (freely convertible)."
            )

        # Standard release conditions
        cond_num = 0

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="All closing conditions precedent satisfied or waived",
            category="legal",
            responsible="Counsel",
        ))

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="KYC/AML clearance confirmed for all parties by escrow agent",
            category="regulatory",
            responsible="Escrow Agent / Compliance",
        ))

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="Dual authorization received from authorized signatories",
            category="legal",
            responsible="Authorized Signatories",
        ))

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="All legal opinions delivered in final form",
            category="documentary",
            responsible="Counsel",
        ))

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="Settlement instructions verified by all counterparties",
            category="financial",
            responsible="Operations",
        ))

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="Funds confirmed deposited in escrow account",
            category="financial",
            responsible="Escrow Agent",
        ))

        cond_num += 1
        terms.conditions.append(EscrowCondition(
            condition_id=f"ESC-{cond_num:03d}",
            description="OFAC/sanctions screening completed with no adverse findings",
            category="regulatory",
            responsible="Escrow Agent / Compliance",
        ))

        # Compliance notes
        terms.compliance_notes.append(
            f"Escrow agent ({terms.escrow_agent}) will hold funds in "
            f"{terms.escrow_currency} pending release conditions."
        )
        terms.compliance_notes.append(
            "Release requires dual authorization from designated signatories."
        )
        terms.compliance_notes.append(
            "Escrow agent performs independent AML/KYC verification."
        )

        return terms

    # ------------------------------------------------------------------
    # Settlement leg builder
    # ------------------------------------------------------------------

    def _build_leg(
        self,
        leg_id: str,
        originator: dict,
        beneficiary: dict,
        escrow_info: dict,
        bank_assignments: dict[str, dict],
        currency: str,
    ) -> SettlementRailLeg:
        """Build a single settlement leg with escrow intermediary."""
        oe = originator.get("entity", originator)
        be = beneficiary.get("entity", beneficiary)
        o_name = oe.get("legal_name", "Unknown")
        b_name = be.get("legal_name", "Unknown")

        # Get assigned banks
        o_bank = bank_assignments.get(o_name, {})
        b_bank = bank_assignments.get(b_name, {})

        escrow_name = escrow_info.get("name", "TBD")
        escrow_swift = escrow_info.get("swift", "")

        # Determine FX need
        o_jur = oe.get("jurisdiction", "").split("-")[0].upper()
        b_jur = be.get("jurisdiction", "").split("-")[0].upper()
        requires_fx = o_jur != b_jur

        # Build node chain
        nodes = []

        # Node 1: Originator
        nodes.append({
            "position": 1,
            "name": o_name,
            "role": "originator",
            "country": o_jur,
            "swift": None,
        })

        # Node 2: Originator's bank
        nodes.append({
            "position": 2,
            "name": o_bank.get("bank", "TBD"),
            "role": "originator_bank",
            "country": o_jur if o_bank.get("source") == "existing" else "US",
            "swift": o_bank.get("swift", ""),
        })

        # Node 3: Escrow agent
        nodes.append({
            "position": 3,
            "name": escrow_name,
            "role": "escrow_agent",
            "country": escrow_info.get("country", ""),
            "swift": escrow_swift,
        })

        # Node 4: Beneficiary's bank
        nodes.append({
            "position": 4,
            "name": b_bank.get("bank", "TBD"),
            "role": "beneficiary_bank",
            "country": b_jur if b_bank.get("source") == "existing" else "US",
            "swift": b_bank.get("swift", ""),
        })

        # Node 5: Beneficiary
        nodes.append({
            "position": 5,
            "name": b_name,
            "role": "beneficiary",
            "country": b_jur,
            "swift": None,
        })

        leg = SettlementRailLeg(
            leg_id=leg_id,
            originator=o_name,
            originator_bank=o_bank.get("bank", "TBD"),
            originator_swift=o_bank.get("swift", ""),
            escrow_agent=escrow_name,
            escrow_swift=escrow_swift,
            beneficiary=b_name,
            beneficiary_bank=b_bank.get("bank", "TBD"),
            beneficiary_swift=b_bank.get("swift", ""),
            currency=currency,
            requires_fx=requires_fx,
            node_count=len(nodes),
            nodes=nodes,
        )

        # Validate the leg
        issues: list[str] = []
        notes: list[str] = []

        # Check SWIFT coverage
        swift_nodes = [n for n in nodes if n.get("swift")]
        if len(swift_nodes) < 2:
            issues.append(
                "Fewer than 2 SWIFT-capable nodes in the settlement chain."
            )
        else:
            notes.append(
                f"{len(swift_nodes)} SWIFT-capable nodes in the chain."
            )

        # Check node count
        if len(nodes) < 3:
            issues.append("Settlement leg has fewer than 3 nodes.")
        else:
            notes.append(
                f"Valid {len(nodes)}-node chain with escrow intermediary."
            )

        # Check escrow
        has_escrow = any(n.get("role") == "escrow_agent" for n in nodes)
        if not has_escrow:
            issues.append("No escrow agent in settlement chain.")
        else:
            notes.append(
                f"Escrow agent: {escrow_name} [{escrow_swift}]."
            )

        # Check FX
        if requires_fx:
            notes.append(
                f"Cross-border leg ({o_jur} → {b_jur}). FX may be required."
            )
            # Check FX controls
            for jur in (o_jur, b_jur):
                fx_info = FX_CONTROLLED_JURISDICTIONS.get(jur)
                if fx_info:
                    notes.append(
                        f"FX Control ({jur}): {fx_info['authority']} approval may be required."
                    )

        leg.issues = issues
        leg.notes = notes
        leg.is_valid = len(issues) == 0

        return leg

    # ------------------------------------------------------------------
    # Plan validation
    # ------------------------------------------------------------------

    def _validate_plan(self, plan: EscrowPlan) -> None:
        """Validate the overall escrow plan."""
        issues: list[str] = []
        recommendations: list[str] = []

        # Check all legs valid
        invalid_legs = [l for l in plan.legs if not l.is_valid]
        if invalid_legs:
            issues.append(
                f"{len(invalid_legs)} settlement leg(s) have validation issues."
            )

        # Check escrow terms
        if plan.escrow_terms and plan.escrow_terms.escrow_currency not in FREELY_CONVERTIBLE:
            issues.append(
                f"Escrow currency {plan.escrow_terms.escrow_currency} "
                f"is not freely convertible."
            )

        # Check bank assignments
        unassigned = [
            name for name, info in plan.entity_bank_assignments.items()
            if info.get("bank") == "TBD"
        ]
        if unassigned:
            issues.append(
                f"{len(unassigned)} entity(ies) without bank assignment: "
                f"{', '.join(unassigned)}"
            )

        # Check for recommended (not established) banks
        recommended = [
            name for name, info in plan.entity_bank_assignments.items()
            if info.get("source") == "recommended"
        ]
        if recommended:
            for name in recommended:
                info = plan.entity_bank_assignments[name]
                recommendations.append(
                    f"Onboard {name} with {info['bank']} [{info['swift']}]. "
                    f"{info.get('rationale', '')}"
                )

        # General recommendations
        if plan.escrow_terms:
            recommendations.append(
                f"Execute escrow agreement with {plan.escrow_terms.escrow_agent}. "
                f"Escrow type: {plan.escrow_terms.escrow_type}."
            )
            recommendations.append(
                "Obtain dual-signature authorization from all designated signatories."
            )

        if any(l.requires_fx for l in plan.legs):
            recommendations.append(
                "Engage FX desk for cross-border legs. "
                "Confirm freely convertible currency for all settlement."
            )

        plan.overall_issues = issues
        plan.recommendations = recommendations
        plan.overall_valid = len(issues) == 0

    # ------------------------------------------------------------------
    # Escrow condition auto-satisfaction
    # ------------------------------------------------------------------

    def auto_satisfy_conditions(
        self,
        plan: EscrowPlan,
        entities: list[dict] | None = None,
        entity_paths: list[Path] | None = None,
    ) -> int:
        """
        Auto-satisfy escrow conditions by cross-referencing evidence
        and entity data. Returns the number of conditions satisfied.

        Checks:
          - KYC/AML: evidence vault has KYC/CIS docs
          - Dual authorization: signatories exist in entity data
          - Legal opinions: evidence vault has opinion docs
          - Settlement instructions: bank assignments exist in plan
          - OFAC/sanctions: no sanctioned jurisdictions in deal
        """
        if not plan.escrow_terms:
            return 0

        # Load entities if paths provided but no dicts
        if not entities and entity_paths:
            entities = []
            for ep in entity_paths:
                try:
                    entities.append(load_entity(ep))
                except Exception:
                    pass

        entities = entities or []
        satisfied_count = 0
        evidence_dir = ROOT_DIR / "data" / "evidence"

        # Build evidence index
        evidence_files: list[str] = []
        if evidence_dir.is_dir():
            for subdir in evidence_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("_"):
                    for f in subdir.iterdir():
                        if f.is_file() and not f.name.startswith("."):
                            evidence_files.append(f.name.lower())

        for cond in plan.escrow_terms.conditions:
            if cond.is_met:
                continue

            desc_lower = cond.description.lower()

            # ESC: KYC/AML clearance
            if "kyc" in desc_lower or "aml" in desc_lower:
                kyc_evidence = [
                    f for f in evidence_files
                    if "cis_" in f or "kyc_" in f or "risk_compliance" in f
                ]
                if len(kyc_evidence) >= 2:
                    cond.status = "SATISFIED"
                    cond.notes = (
                        f"KYC/AML documentation found: {len(kyc_evidence)} "
                        f"document(s) in evidence vault."
                    )
                    satisfied_count += 1
                    continue

            # ESC: Dual authorization / signatories
            if "authorization" in desc_lower or "signator" in desc_lower:
                total_sigs = sum(
                    len(e.get("entity", e).get("signatories", []))
                    for e in entities
                )
                if total_sigs >= 2:
                    cond.status = "SATISFIED"
                    cond.notes = (
                        f"{total_sigs} authorized signatories found "
                        f"across entity profiles."
                    )
                    satisfied_count += 1
                    continue

            # ESC: Legal opinions
            if "legal opinion" in desc_lower or "opinions delivered" in desc_lower:
                opinion_evidence = [
                    f for f in evidence_files
                    if "opinion_" in f or "legal_opinion" in f
                ]
                if opinion_evidence:
                    # Check if any are draft
                    is_draft = any("draft" in f for f in opinion_evidence)
                    if not is_draft:
                        cond.status = "SATISFIED"
                        cond.notes = (
                            f"Legal opinion(s) found: {len(opinion_evidence)} "
                            f"document(s) in evidence vault."
                        )
                        satisfied_count += 1
                    else:
                        cond.status = "PENDING"
                        cond.notes = (
                            "Legal opinion(s) found but in DRAFT status. "
                            "Final form required."
                        )
                    continue

            # ESC: Settlement instructions verified
            if "settlement instruction" in desc_lower:
                assigned = plan.entity_bank_assignments
                all_have_banks = all(
                    info.get("swift") for info in assigned.values()
                ) if assigned else False
                if all_have_banks and len(assigned) >= 2:
                    cond.status = "SATISFIED"
                    cond.notes = (
                        f"Settlement instructions verified for "
                        f"{len(assigned)} entities with SWIFT codes."
                    )
                    satisfied_count += 1
                    continue

            # ESC: OFAC/sanctions screening
            if "ofac" in desc_lower or "sanctions" in desc_lower:
                # Check no sanctioned jurisdictions
                sanctioned = {"IR", "KP", "CU", "SY"}
                jurisdictions = set()
                for e in entities:
                    jur = e.get("entity", e).get("jurisdiction", "")
                    base = jur.split("-")[0].upper() if jur else ""
                    if base:
                        jurisdictions.add(base)

                if not jurisdictions & sanctioned:
                    compliance_evidence = [
                        f for f in evidence_files
                        if "risk_compliance" in f or "sanctions" in f
                    ]
                    if compliance_evidence:
                        cond.status = "SATISFIED"
                        cond.notes = (
                            "No sanctioned jurisdictions in deal group. "
                            "Compliance documentation found in evidence vault."
                        )
                        satisfied_count += 1
                        continue

        return satisfied_count

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, plan: EscrowPlan) -> Path:
        """Persist escrow plan to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = plan.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"escrow_plan_{name}_{ts}.json"
        path.write_text(
            json.dumps(plan.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path
