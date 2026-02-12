"""
Settlement Onboarding Engine
==============================
Detects missing banking rails across the deal group and generates
structured onboarding action plans so that entities can establish
SWIFT-capable settlement before closing.

The deal-ready and closing-tracker engines flag missing settlement
banks, but neither tells you HOW to fix it. This engine does.

For each entity with settlement gaps:
  1. Identify what's missing (settlement bank, SWIFT code, ABA, account)
  2. Recommend candidate banks based on jurisdiction + deal requirements
  3. Generate an onboarding checklist with specific steps
  4. Track onboarding status across the deal group

Input:  Entity paths (the deal group)
Output: OnboardingPlan with per-entity action items, candidate banks,
        and overall settlement-readiness determination
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
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "settlement_onboarding"

# Candidate banks by jurisdiction
CANDIDATE_BANKS: dict[str, list[dict[str, Any]]] = {
    "US": [
        {
            "name": "JPMorgan Chase Bank, N.A.",
            "swift": "CHASUS33",
            "services": ["settlement", "custody", "escrow", "correspondent"],
            "tier": "GSIB",
            "notes": "Largest US bank. Full DTC/DWAC capability.",
        },
        {
            "name": "The Bank of New York Mellon Corporation",
            "swift": "IRVTUS3N",
            "services": ["settlement", "custody", "clearing", "correspondent"],
            "tier": "GSIB",
            "notes": "Largest global custodian. Specialist in securities settlement.",
        },
        {
            "name": "Bank of America / Merrill Lynch",
            "swift": "BOFAUS3N",
            "services": ["settlement", "brokerage", "custody"],
            "tier": "GSIB",
            "notes": "Full-service institutional banking.",
        },
    ],
    "BS": [
        {
            "name": "Scotiabank (Bahamas) Limited",
            "swift": "NOSCBSNS",
            "services": ["settlement", "correspondent", "fx"],
            "tier": "INTERNATIONAL",
            "notes": "Leading bank in the Bahamas with international correspondent access.",
        },
        {
            "name": "FirstCaribbean International Bank",
            "swift": "FCIBKYKY",
            "services": ["settlement", "correspondent"],
            "tier": "REGIONAL",
            "notes": "CIBC subsidiary. Caribbean specialist.",
        },
    ],
    "GB": [
        {
            "name": "Barclays Bank PLC",
            "swift": "BARCGB22",
            "services": ["settlement", "custody", "correspondent", "fx"],
            "tier": "GSIB",
            "notes": "Major UK clearing bank.",
        },
    ],
    "VN": [
        {
            "name": "Vietcombank",
            "swift": "BFTVVNVX",
            "services": ["settlement", "fx", "correspondent"],
            "tier": "DOMESTIC_MAJOR",
            "notes": "Largest commercial bank in Vietnam.",
        },
        {
            "name": "Standard Chartered Bank Vietnam",
            "swift": "SCBLVNVX",
            "services": ["settlement", "correspondent", "trade_finance"],
            "tier": "INTERNATIONAL",
            "notes": "International bank with strong cross-border capability.",
        },
    ],
}

# Default candidates if jurisdiction not in the registry
DEFAULT_CANDIDATES = [
    {
        "name": "JPMorgan Chase Bank, N.A.",
        "swift": "CHASUS33",
        "services": ["settlement", "custody", "escrow", "correspondent"],
        "tier": "GSIB",
        "notes": "Global correspondent bank. Covers most jurisdictions.",
    },
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class OnboardingStep:
    """A single step in the onboarding process."""
    step_number: int
    action: str
    responsible: str = "Operations"
    estimated_days: int = 0
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, BLOCKED
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "action": self.action,
            "responsible": self.responsible,
            "estimated_days": self.estimated_days,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class CandidateBank:
    """A recommended banking partner for onboarding."""
    name: str
    swift_code: str
    services: list[str] = field(default_factory=list)
    tier: str = "UNKNOWN"
    fit_score: int = 0  # 0-100, how well it fits the entity's needs
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "swift_code": self.swift_code,
            "services": self.services,
            "tier": self.tier,
            "fit_score": self.fit_score,
            "rationale": self.rationale,
        }


@dataclass
class EntityOnboardingProfile:
    """Onboarding profile for a single entity."""
    entity_name: str
    jurisdiction: str
    entity_type: str = ""
    missing: list[str] = field(default_factory=list)  # What banking data is missing
    has_settlement_bank: bool = False
    has_swift: bool = False
    has_aba: bool = False
    has_account: bool = False
    candidates: list[CandidateBank] = field(default_factory=list)
    steps: list[OnboardingStep] = field(default_factory=list)
    status: str = "NEEDS_ONBOARDING"  # COMPLETE, NEEDS_ONBOARDING, PARTIAL, NOT_APPLICABLE
    notes: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.status == "COMPLETE"

    def to_dict(self) -> dict:
        return {
            "entity_name": self.entity_name,
            "jurisdiction": self.jurisdiction,
            "entity_type": self.entity_type,
            "status": self.status,
            "missing": self.missing,
            "has_settlement_bank": self.has_settlement_bank,
            "has_swift": self.has_swift,
            "has_aba": self.has_aba,
            "has_account": self.has_account,
            "candidates": [c.to_dict() for c in self.candidates],
            "steps": [s.to_dict() for s in self.steps],
            "notes": self.notes,
        }


@dataclass
class OnboardingPlan:
    """Complete settlement onboarding plan for a deal group."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    profiles: list[EntityOnboardingProfile] = field(default_factory=list)

    @property
    def total_entities(self) -> int:
        return len(self.profiles)

    @property
    def needs_onboarding(self) -> int:
        return sum(1 for p in self.profiles if p.status == "NEEDS_ONBOARDING")

    @property
    def partial(self) -> int:
        return sum(1 for p in self.profiles if p.status == "PARTIAL")

    @property
    def complete(self) -> int:
        return sum(1 for p in self.profiles if p.status == "COMPLETE")

    @property
    def settlement_ready(self) -> bool:
        """Are all entities onboarded for settlement?"""
        for p in self.profiles:
            if p.status in ("NEEDS_ONBOARDING", "PARTIAL"):
                return False
        return True

    @property
    def total_steps(self) -> int:
        return sum(len(p.steps) for p in self.profiles)

    @property
    def completed_steps(self) -> int:
        return sum(
            1 for p in self.profiles for s in p.steps if s.status == "COMPLETED"
        )

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "SETTLEMENT ONBOARDING PLAN",
            f"  {self.deal_name}",
            f"  Created: {self.created_at}",
            "=" * 70,
            "",
            f"  SETTLEMENT READY: {'YES' if self.settlement_ready else 'NO'}",
            f"  Entities:         {self.total_entities}",
            f"  Needs Onboarding: {self.needs_onboarding}",
            f"  Partial:          {self.partial}",
            f"  Complete:         {self.complete}",
            f"  Total Steps:      {self.total_steps}",
            "",
        ]

        for profile in self.profiles:
            status_icon = {
                "COMPLETE": "[+]",
                "NEEDS_ONBOARDING": "[X]",
                "PARTIAL": "[~]",
                "NOT_APPLICABLE": "[-]",
            }.get(profile.status, "[ ]")

            lines.append(f"--- {status_icon} {profile.entity_name} ({profile.jurisdiction}) ---")
            lines.append(f"    Type: {profile.entity_type}")
            lines.append(f"    Status: {profile.status}")

            if profile.missing:
                lines.append(f"    Missing: {', '.join(profile.missing)}")

            if profile.candidates:
                lines.append(f"    Recommended Banks:")
                for cb in profile.candidates[:3]:
                    lines.append(
                        f"      - {cb.name} [{cb.swift_code}] "
                        f"(Fit: {cb.fit_score}/100, {cb.tier})"
                    )
                    if cb.rationale:
                        lines.append(f"        {cb.rationale}")

            if profile.steps:
                lines.append(f"    Onboarding Steps ({len(profile.steps)}):")
                for step in profile.steps:
                    step_icon = {"COMPLETED": "+", "IN_PROGRESS": "~",
                                 "BLOCKED": "X"}.get(step.status, " ")
                    days = f" (~{step.estimated_days}d)" if step.estimated_days else ""
                    lines.append(
                        f"      [{step_icon}] {step.step_number}. {step.action}"
                        f"{days} [{step.responsible}]"
                    )
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "settlement_ready": self.settlement_ready,
            "total_entities": self.total_entities,
            "needs_onboarding": self.needs_onboarding,
            "complete": self.complete,
            "profiles": [p.to_dict() for p in self.profiles],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class SettlementOnboardingEngine:
    """
    Detects banking gaps and generates onboarding plans.

    Usage:
        engine = SettlementOnboardingEngine()
        plan = engine.assess(
            deal_name="OPTKAS-TC Deal Group",
            entity_paths=[Path("data/entities/tc_advantage_traders.yaml"), ...],
        )
        print(plan.summary())
    """

    def assess(
        self,
        deal_name: str,
        entity_paths: list[Path] | None = None,
    ) -> OnboardingPlan:
        """Assess banking gaps and build onboarding plan."""
        plan = OnboardingPlan(deal_name=deal_name)

        for ep in (entity_paths or []):
            data = load_entity(ep)
            profile = self._assess_entity(data)
            plan.profiles.append(profile)

        return plan

    def _assess_entity(self, entity: dict) -> EntityOnboardingProfile:
        """Assess a single entity's banking readiness."""
        e = entity.get("entity", entity)
        banking = e.get("banking", {})
        reg = e.get("regulatory_status", {})
        name = e.get("legal_name", "Unknown")
        jur = e.get("jurisdiction", "")
        base_jur = jur.split("-")[0].upper() if jur else ""

        profile = EntityOnboardingProfile(
            entity_name=name,
            jurisdiction=jur,
            entity_type=e.get("entity_type", ""),
        )

        # Check what's present
        profile.has_settlement_bank = bool(banking.get("settlement_bank"))
        profile.has_swift = bool(banking.get("swift_code"))
        profile.has_aba = bool(banking.get("aba_routing"))
        profile.has_account = bool(
            banking.get("account_number") or banking.get("beneficiary_account_number")
        )

        # Banks don't need onboarding
        is_bank = reg.get("is_bank", False)
        if is_bank:
            profile.status = "NOT_APPLICABLE"
            profile.notes.append("Entity is a bank. No partner bank onboarding needed.")
            return profile

        # Identify missing items
        if not profile.has_settlement_bank:
            profile.missing.append("settlement_bank")
        if not profile.has_swift:
            profile.missing.append("swift_code")
        if not profile.has_aba and base_jur == "US":
            profile.missing.append("aba_routing")
        if not profile.has_account:
            profile.missing.append("account_number")

        # Determine status
        if not profile.missing:
            profile.status = "COMPLETE"
            profile.notes.append("All banking data present. Settlement-ready.")
            return profile
        elif profile.has_settlement_bank:
            profile.status = "PARTIAL"
            profile.notes.append("Settlement bank assigned but details incomplete.")
        else:
            profile.status = "NEEDS_ONBOARDING"

        # Recommend candidate banks
        profile.candidates = self._recommend_banks(e, profile)

        # Generate onboarding steps
        profile.steps = self._generate_steps(profile, e)

        return profile

    def _recommend_banks(
        self, entity: dict, profile: EntityOnboardingProfile,
    ) -> list[CandidateBank]:
        """Recommend candidate settlement banks for the entity."""
        jur = profile.jurisdiction
        base_jur = jur.split("-")[0].upper() if jur else ""
        entity_type = profile.entity_type
        banking = entity.get("entity", entity).get("banking", {})

        # Get jurisdiction-specific candidates
        raw_candidates = CANDIDATE_BANKS.get(base_jur, DEFAULT_CANDIDATES)

        candidates: list[CandidateBank] = []
        for rc in raw_candidates:
            fit = 50  # Base fit score
            rationale_parts = []

            # Tier bonus
            if rc["tier"] in ("GSIB", "GLOBAL_SYSTEMICALLY_IMPORTANT"):
                fit += 15
                rationale_parts.append("GSIB institution")

            # Jurisdiction match
            if base_jur == "US" and "US" in rc.get("swift", "")[:2]:
                fit += 10
                rationale_parts.append("US-domiciled")
            elif base_jur in ("BS", "KY", "BM"):
                # Caribbean entities benefit from US correspondent
                if "correspondent" in rc.get("services", []):
                    fit += 10
                    rationale_parts.append("Correspondent capability for Caribbean entities")

            # Settlement service
            if "settlement" in rc.get("services", []):
                fit += 10
                rationale_parts.append("Direct settlement capability")

            # DTC/DWAC compatibility
            mtn = entity.get("entity", entity).get("mtn_program", {})
            if mtn.get("settlement_method", "").upper() in ("DTC/DWAC", "DTC/DWAC FAST"):
                if "clearing" in rc.get("services", []) or "custody" in rc.get("services", []):
                    fit += 10
                    rationale_parts.append("DTC/DWAC clearing capable")

            # SPV-specific
            if entity_type == "special_purpose_vehicle":
                if "custody" in rc.get("services", []):
                    fit += 5
                    rationale_parts.append("Custodial services for SPV")

            # Existing custodian relationship
            custodian = banking.get("custodian", "")
            if custodian and rc["name"].lower() in custodian.lower():
                fit += 15
                rationale_parts.append("Existing custodial relationship")

            candidates.append(CandidateBank(
                name=rc["name"],
                swift_code=rc["swift"],
                services=rc.get("services", []),
                tier=rc["tier"],
                fit_score=min(100, fit),
                rationale=". ".join(rationale_parts) + "." if rationale_parts else "",
            ))

        # Sort by fit score descending
        candidates.sort(key=lambda c: c.fit_score, reverse=True)
        return candidates

    def _generate_steps(
        self, profile: EntityOnboardingProfile, entity: dict,
    ) -> list[OnboardingStep]:
        """Generate onboarding steps for the entity."""
        steps: list[OnboardingStep] = []
        step_num = 1

        # Step 1: Always — select settlement bank
        if "settlement_bank" in profile.missing:
            top_bank = profile.candidates[0].name if profile.candidates else "TBD"
            steps.append(OnboardingStep(
                step_number=step_num,
                action=f"Select settlement bank (recommended: {top_bank})",
                responsible="Treasury / Operations",
                estimated_days=5,
                notes="Evaluate candidates. Consider existing relationships.",
            ))
            step_num += 1

        # Step 2: Open account
        if "settlement_bank" in profile.missing or "account_number" in profile.missing:
            steps.append(OnboardingStep(
                step_number=step_num,
                action="Open settlement account with selected bank",
                responsible="Operations",
                estimated_days=14,
                notes="Requires KYC/AML documentation, corporate resolutions, authorized signatories.",
            ))
            step_num += 1

        # Step 3: Obtain SWIFT/ABA
        if "swift_code" in profile.missing:
            steps.append(OnboardingStep(
                step_number=step_num,
                action="Obtain SWIFT BIC code from settlement bank",
                responsible="Operations",
                estimated_days=3,
                notes="SWIFT code will be the bank's BIC. Record in entity profile.",
            ))
            step_num += 1

        if "aba_routing" in profile.missing:
            steps.append(OnboardingStep(
                step_number=step_num,
                action="Obtain ABA routing number for US wire transfers",
                responsible="Operations",
                estimated_days=1,
                notes="Required for domestic US wire transfers.",
            ))
            step_num += 1

        # Step 4: DTC/DWAC setup
        e = entity.get("entity", entity)
        mtn = e.get("mtn_program", {})
        if mtn.get("settlement_method", "").upper() in ("DTC/DWAC", "DTC/DWAC FAST"):
            steps.append(OnboardingStep(
                step_number=step_num,
                action="Confirm DTC/DWAC FAST eligibility with settlement bank and transfer agent",
                responsible="Operations / Transfer Agent",
                estimated_days=7,
                notes="Coordinate with Securities Transfer Corporation (STC) for DTC/DWAC capability.",
            ))
            step_num += 1

        # Step 5: KYC/AML package
        steps.append(OnboardingStep(
            step_number=step_num,
            action="Submit KYC/AML documentation package to settlement bank",
            responsible="Compliance",
            estimated_days=10,
            notes="Includes: certificate of formation, beneficial ownership, tax ID, authorized signatories.",
        ))
        step_num += 1

        # Step 6: Test wire
        steps.append(OnboardingStep(
            step_number=step_num,
            action="Execute test wire transfer to verify settlement rails",
            responsible="Treasury",
            estimated_days=3,
            notes="Send small test amount. Verify receipt. Confirm ABA/SWIFT routing.",
        ))
        step_num += 1

        # Step 7: Update entity profile
        steps.append(OnboardingStep(
            step_number=step_num,
            action="Update entity YAML with settlement bank details",
            responsible="Operations / Legal Ops",
            estimated_days=1,
            notes="Record: settlement_bank, swift_code, aba_routing, account_number in entity file.",
        ))
        step_num += 1

        return steps

    def save(self, plan: OnboardingPlan) -> Path:
        """Persist onboarding plan to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = plan.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"onboarding_{name}_{ts}.json"
        path.write_text(json.dumps(plan.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
