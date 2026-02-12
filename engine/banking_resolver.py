"""
Banking Resolver Engine
=========================
Resolves banking gaps across the deal group by:
  1. Analyzing each entity's banking profile
  2. Cross-referencing with correspondent banking data
  3. Recommending optimal bank assignments
  4. Generating updated banking configurations
  5. Producing an actionable resolution plan

This engine works alongside the Escrow Engine:
  - Escrow Engine builds the settlement RAILS
  - Banking Resolver fills the banking DATA GAPS

The output is a BankingResolutionPlan that maps each entity
to its resolved banking profile — either from existing data
or from recommended assignments.

Input:  Entity paths
Output: BankingResolutionPlan with per-entity resolved banking,
        gap analysis, and implementation steps
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import load_entity
from engine.correspondent_banking import KNOWN_BANKS
from engine.settlement_onboarding import CANDIDATE_BANKS, DEFAULT_CANDIDATES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "banking_resolution"

# Extended bank directory — maps SWIFT codes to complete banking details
BANK_DIRECTORY: dict[str, dict[str, Any]] = {
    "CHASUS33": {
        "name": "JPMorgan Chase Bank, N.A.",
        "swift": "CHASUS33",
        "aba": "021000021",
        "country": "US",
        "address": "383 Madison Avenue, New York, NY 10179",
        "services": ["settlement", "custody", "escrow", "correspondent",
                      "fx", "clearing", "paying_agent"],
        "tier": "GSIB",
        "dtc_participant": True,
        "fedwire": True,
        "chips_uid": "0002",
    },
    "IRVTUS3N": {
        "name": "The Bank of New York Mellon Corporation",
        "swift": "IRVTUS3N",
        "aba": "021000018",
        "country": "US",
        "address": "240 Greenwich Street, New York, NY 10286",
        "services": ["settlement", "custody", "clearing", "correspondent",
                      "trustee", "paying_agent"],
        "tier": "GSIB",
        "dtc_participant": True,
        "fedwire": True,
        "chips_uid": "0001",
    },
    "BOFAUS3N": {
        "name": "Bank of America / Merrill Lynch",
        "swift": "BOFAUS3N",
        "aba": "026009593",
        "country": "US",
        "address": "100 North Tryon Street, Charlotte, NC 28255",
        "services": ["settlement", "brokerage", "custody", "correspondent"],
        "tier": "GSIB",
        "dtc_participant": True,
        "fedwire": True,
        "chips_uid": "0959",
    },
    "BARCGB22": {
        "name": "Barclays Bank PLC",
        "swift": "BARCGB22",
        "aba": None,
        "country": "GB",
        "address": "1 Churchill Place, London E14 5HP",
        "services": ["settlement", "custody", "correspondent", "fx"],
        "tier": "GSIB",
        "dtc_participant": False,
        "fedwire": False,
    },
    "BFTVVNVX": {
        "name": "Vietcombank",
        "swift": "BFTVVNVX",
        "aba": None,
        "country": "VN",
        "address": "198 Tran Quang Khai, Hanoi, Vietnam",
        "services": ["settlement", "fx", "correspondent"],
        "tier": "DOMESTIC_MAJOR",
        "dtc_participant": False,
        "fedwire": False,
    },
    "SCBLVNVX": {
        "name": "Standard Chartered Bank Vietnam",
        "swift": "SCBLVNVX",
        "aba": None,
        "country": "VN",
        "address": "235 Dong Khoi Street, District 1, Ho Chi Minh City",
        "services": ["settlement", "correspondent", "trade_finance", "fx"],
        "tier": "INTERNATIONAL",
        "dtc_participant": False,
        "fedwire": False,
    },
    "NOSCBSNS": {
        "name": "Scotiabank (Bahamas) Limited",
        "swift": "NOSCBSNS",
        "aba": None,
        "country": "BS",
        "address": "Scotia Centre, Bay Street, Nassau, Bahamas",
        "services": ["settlement", "correspondent", "fx"],
        "tier": "INTERNATIONAL",
        "dtc_participant": False,
        "fedwire": False,
    },
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class BankingGap:
    """A specific banking data gap for an entity."""
    field_name: str  # settlement_bank, swift_code, aba_routing, account_number
    severity: str    # CRITICAL, HIGH, MEDIUM
    description: str
    resolution: str = ""

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "severity": self.severity,
            "description": self.description,
            "resolution": self.resolution,
        }


@dataclass
class ResolvedBanking:
    """Complete resolved banking profile for an entity."""
    entity_name: str
    jurisdiction: str
    entity_type: str = ""
    # Current state
    current_bank: str = ""
    current_swift: str = ""
    current_aba: str = ""
    current_account: str = ""
    current_custodian: str = ""
    # Resolved state
    resolved_bank: str = ""
    resolved_swift: str = ""
    resolved_aba: str = ""
    resolved_country: str = ""
    resolved_services: list[str] = field(default_factory=list)
    resolved_tier: str = ""
    # Gap analysis
    gaps: list[BankingGap] = field(default_factory=list)
    # Resolution metadata
    source: str = ""  # existing, recommended, inherited
    confidence: int = 0  # 0-100
    implementation_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return bool(self.resolved_bank and self.resolved_swift)

    @property
    def critical_gaps(self) -> int:
        return sum(1 for g in self.gaps if g.severity == "CRITICAL")

    @property
    def status(self) -> str:
        if not self.gaps:
            return "RESOLVED"
        if self.critical_gaps > 0:
            return "CRITICAL_GAPS"
        return "MINOR_GAPS"

    def to_dict(self) -> dict:
        return {
            "entity_name": self.entity_name,
            "jurisdiction": self.jurisdiction,
            "entity_type": self.entity_type,
            "status": self.status,
            "is_complete": self.is_complete,
            "current": {
                "bank": self.current_bank,
                "swift": self.current_swift,
                "aba": self.current_aba,
                "account": self.current_account,
                "custodian": self.current_custodian,
            },
            "resolved": {
                "bank": self.resolved_bank,
                "swift": self.resolved_swift,
                "aba": self.resolved_aba,
                "country": self.resolved_country,
                "services": self.resolved_services,
                "tier": self.resolved_tier,
            },
            "gaps": [g.to_dict() for g in self.gaps],
            "source": self.source,
            "confidence": self.confidence,
            "implementation_steps": self.implementation_steps,
            "notes": self.notes,
        }


@dataclass
class BankingResolutionPlan:
    """Complete banking resolution plan for a deal group."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    profiles: list[ResolvedBanking] = field(default_factory=list)

    @property
    def total_entities(self) -> int:
        return len(self.profiles)

    @property
    def fully_resolved(self) -> int:
        return sum(1 for p in self.profiles if p.status == "RESOLVED")

    @property
    def critical_entities(self) -> int:
        return sum(1 for p in self.profiles if p.status == "CRITICAL_GAPS")

    @property
    def all_resolved(self) -> bool:
        return all(p.is_complete for p in self.profiles)

    @property
    def total_gaps(self) -> int:
        return sum(len(p.gaps) for p in self.profiles)

    @property
    def total_critical(self) -> int:
        return sum(p.critical_gaps for p in self.profiles)

    @property
    def resolution_pct(self) -> float:
        if not self.profiles:
            return 100.0
        return round(self.fully_resolved / self.total_entities * 100, 1)

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "BANKING RESOLUTION PLAN",
            f"  {self.deal_name}",
            f"  Generated: {self.created_at}",
            "=" * 70,
            "",
            f"  ALL RESOLVED: {'YES' if self.all_resolved else 'NO'}",
            f"  Resolution:   {self.resolution_pct}% ({self.fully_resolved}/{self.total_entities})",
            f"  Total Gaps:   {self.total_gaps} ({self.total_critical} critical)",
            "",
        ]

        for profile in self.profiles:
            status_icon = {
                "RESOLVED": "[+]",
                "CRITICAL_GAPS": "[X]",
                "MINOR_GAPS": "[~]",
            }.get(profile.status, "[ ]")

            lines.append(
                f"--- {status_icon} {profile.entity_name} "
                f"({profile.jurisdiction}) ---"
            )
            lines.append(f"    Type:   {profile.entity_type}")
            lines.append(f"    Source: {profile.source} "
                         f"(confidence: {profile.confidence}%)")

            if profile.current_bank:
                lines.append(f"    Current: {profile.current_bank} [{profile.current_swift}]")

            lines.append(f"    Resolved: {profile.resolved_bank} [{profile.resolved_swift}]")
            if profile.resolved_aba:
                lines.append(f"    ABA:      {profile.resolved_aba}")
            if profile.resolved_tier:
                lines.append(f"    Tier:     {profile.resolved_tier}")
            if profile.resolved_services:
                lines.append(f"    Services: {', '.join(profile.resolved_services[:5])}")

            if profile.gaps:
                lines.append(f"    Gaps ({len(profile.gaps)}):")
                for gap in profile.gaps:
                    sev_icon = "!!" if gap.severity == "CRITICAL" else "!"
                    lines.append(
                        f"      [{sev_icon}] {gap.field_name}: {gap.description}"
                    )
                    if gap.resolution:
                        lines.append(f"           Fix: {gap.resolution}")

            if profile.implementation_steps:
                lines.append(f"    Steps:")
                for i, step in enumerate(profile.implementation_steps, 1):
                    lines.append(f"      {i}. {step}")

            for note in profile.notes:
                lines.append(f"    [i] {note}")

            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "all_resolved": self.all_resolved,
            "total_entities": self.total_entities,
            "fully_resolved": self.fully_resolved,
            "critical_entities": self.critical_entities,
            "resolution_pct": self.resolution_pct,
            "total_gaps": self.total_gaps,
            "profiles": [p.to_dict() for p in self.profiles],
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class BankingResolverEngine:
    """
    Resolves banking gaps and generates complete banking profiles.

    Usage:
        engine = BankingResolverEngine()
        plan = engine.resolve(
            deal_name="TC Advantage 5B MTN",
            entity_paths=[
                Path("data/entities/tc_advantage_traders.yaml"),
                Path("data/entities/optkas1_spv.yaml"),
                Path("data/entities/querubin_usa.yaml"),
            ],
        )
        print(plan.summary())
    """

    def resolve(
        self,
        deal_name: str,
        entity_paths: list[Path] | None = None,
    ) -> BankingResolutionPlan:
        """Resolve banking gaps for all entities."""
        plan = BankingResolutionPlan(deal_name=deal_name)

        for ep in (entity_paths or []):
            try:
                data = load_entity(ep)
                profile = self._resolve_entity(data)
                plan.profiles.append(profile)
            except Exception as exc:
                plan.profiles.append(ResolvedBanking(
                    entity_name=str(ep),
                    jurisdiction="??",
                    notes=[f"Error loading entity: {exc}"],
                ))

        return plan

    def _resolve_entity(self, entity: dict) -> ResolvedBanking:
        """Resolve banking for a single entity."""
        e = entity.get("entity", entity)
        banking = e.get("banking", {})
        reg = e.get("regulatory_status", {})
        name = e.get("legal_name", "Unknown")
        jur = e.get("jurisdiction", "")
        base_jur = jur.split("-")[0].upper() if jur else ""
        entity_type = e.get("entity_type", "")

        profile = ResolvedBanking(
            entity_name=name,
            jurisdiction=jur,
            entity_type=entity_type,
        )

        # Record current state
        profile.current_bank = banking.get("settlement_bank", "")
        profile.current_swift = banking.get("swift_code", "")
        profile.current_aba = banking.get("aba_routing", "")
        profile.current_account = banking.get(
            "beneficiary_account_number",
            banking.get("account_number", ""),
        )
        profile.current_custodian = banking.get("custodian", "")

        # Banks don't need resolution
        is_bank = reg.get("is_bank", False)
        if is_bank:
            profile.resolved_bank = name
            profile.resolved_swift = profile.current_swift
            profile.resolved_aba = profile.current_aba
            profile.source = "self_bank"
            profile.confidence = 100
            profile.notes.append("Entity is a bank. Self-clearing.")
            return profile

        # Check if fully resolved already
        if (profile.current_bank and profile.current_swift
                and profile.current_account):
            # Has everything — copy to resolved
            profile.resolved_bank = profile.current_bank
            profile.resolved_swift = profile.current_swift
            profile.resolved_aba = profile.current_aba
            profile.resolved_country = self._swift_country(profile.current_swift)
            profile.source = "existing"
            profile.confidence = 95

            # Look up tier/services from directory
            bank_info = BANK_DIRECTORY.get(profile.current_swift, {})
            if bank_info:
                profile.resolved_tier = bank_info.get("tier", "")
                profile.resolved_services = bank_info.get("services", [])

            # Check for minor gaps
            if not profile.current_aba and base_jur == "US":
                bank_info = BANK_DIRECTORY.get(profile.current_swift, {})
                aba = bank_info.get("aba", "")
                if aba:
                    profile.resolved_aba = aba
                    profile.notes.append(
                        f"ABA routing resolved from bank directory: {aba}"
                    )
                else:
                    profile.gaps.append(BankingGap(
                        field_name="aba_routing",
                        severity="MEDIUM",
                        description="Missing ABA routing for US settlement.",
                        resolution=f"Obtain ABA from {profile.current_bank}.",
                    ))

            profile.notes.append(
                f"Existing banking relationship with {profile.current_bank}."
            )
            return profile

        # Need to recommend a bank
        self._recommend_and_resolve(profile, e, base_jur)
        return profile

    def _recommend_and_resolve(
        self,
        profile: ResolvedBanking,
        entity: dict,
        base_jur: str,
    ) -> None:
        """Recommend and resolve banking for an entity without full banking."""
        banking = entity.get("banking", {})
        mtn = entity.get("mtn_program", {})
        custodian = banking.get("custodian", "")
        entity_type = entity.get("entity_type", "")

        # Get candidates
        candidates = CANDIDATE_BANKS.get(base_jur, DEFAULT_CANDIDATES)

        # Score candidates
        scored: list[tuple[int, dict]] = []
        for c in candidates:
            score = 50
            services = c.get("services", [])

            # GSIB preference
            if c.get("tier") in ("GSIB", "GLOBAL_SYSTEMICALLY_IMPORTANT"):
                score += 15

            # Settlement capability
            if "settlement" in services:
                score += 10

            # DTC/DWAC
            if mtn.get("settlement_method", "").upper() in ("DTC/DWAC", "DTC/DWAC FAST"):
                if "clearing" in services or "custody" in services:
                    score += 15

            # SPV needs custody
            if entity_type == "special_purpose_vehicle" and "custody" in services:
                score += 10

            # Existing custodian
            if custodian and c["name"].lower() in custodian.lower():
                score += 20

            # Correspondent for offshore
            if base_jur in ("BS", "KY", "BM") and "correspondent" in services:
                score += 10

            # Escrow capability
            if "escrow" in services:
                score += 5

            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1] if scored else {}

        if not best:
            profile.notes.append("No candidate banks available for jurisdiction.")
            return

        # Resolve from best candidate
        best_swift = best.get("swift", "")
        bank_info = BANK_DIRECTORY.get(best_swift, {})

        profile.resolved_bank = best.get("name", "TBD")
        profile.resolved_swift = best_swift
        profile.resolved_aba = bank_info.get("aba", "")
        profile.resolved_country = bank_info.get("country", "")
        profile.resolved_tier = best.get("tier", bank_info.get("tier", ""))
        profile.resolved_services = best.get("services", bank_info.get("services", []))
        profile.source = "recommended"
        profile.confidence = min(100, scored[0][0])

        # Identify gaps
        if not profile.current_bank:
            profile.gaps.append(BankingGap(
                field_name="settlement_bank",
                severity="CRITICAL",
                description="No settlement bank assigned.",
                resolution=f"Open account with {profile.resolved_bank} [{best_swift}].",
            ))

        if not profile.current_swift:
            profile.gaps.append(BankingGap(
                field_name="swift_code",
                severity="CRITICAL",
                description="No SWIFT code for settlement.",
                resolution=f"Use SWIFT code {best_swift} ({profile.resolved_bank}).",
            ))

        if not profile.current_aba and base_jur == "US":
            aba = bank_info.get("aba", "")
            if aba:
                profile.resolved_aba = aba
            profile.gaps.append(BankingGap(
                field_name="aba_routing",
                severity="HIGH",
                description="Missing ABA routing number for US wire transfers.",
                resolution=f"ABA: {aba}" if aba else f"Obtain from {profile.resolved_bank}.",
            ))

        if not profile.current_account:
            profile.gaps.append(BankingGap(
                field_name="account_number",
                severity="CRITICAL",
                description="No settlement account number.",
                resolution=f"Open account with {profile.resolved_bank}.",
            ))

        # Implementation steps
        profile.implementation_steps = self._generate_steps(profile, entity)

        profile.notes.append(
            f"Recommended: {profile.resolved_bank} ({profile.resolved_tier}). "
            f"Confidence: {profile.confidence}%."
        )
        if best.get("notes"):
            profile.notes.append(best["notes"])

    def _generate_steps(
        self, profile: ResolvedBanking, entity: dict,
    ) -> list[str]:
        """Generate implementation steps for banking resolution."""
        steps: list[str] = []

        if "settlement_bank" in [g.field_name for g in profile.gaps]:
            steps.append(
                f"Contact {profile.resolved_bank} institutional banking "
                f"to initiate account opening."
            )

        steps.append(
            "Prepare KYC/AML documentation package: certificate of formation, "
            "beneficial ownership, tax ID, authorized signatories, board resolution."
        )

        if "account_number" in [g.field_name for g in profile.gaps]:
            steps.append(
                f"Open settlement account with {profile.resolved_bank}. "
                f"Estimated timeline: 10-15 business days."
            )

        mtn = entity.get("mtn_program", {})
        if mtn.get("settlement_method", "").upper() in ("DTC/DWAC", "DTC/DWAC FAST"):
            steps.append(
                "Confirm DTC/DWAC FAST eligibility with bank and "
                "transfer agent (Securities Transfer Corporation)."
            )

        steps.append(
            "Execute test wire transfer to verify settlement rails."
        )

        steps.append(
            f"Update entity YAML with: settlement_bank, swift_code "
            f"({profile.resolved_swift})"
            + (f", aba_routing ({profile.resolved_aba})" if profile.resolved_aba else "")
            + ", account_number."
        )

        return steps

    def _swift_country(self, swift: str) -> str:
        """Extract country from SWIFT code (positions 5-6)."""
        if swift and len(swift) >= 6:
            return swift[4:6]
        return ""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, plan: BankingResolutionPlan) -> Path:
        """Persist resolution plan to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = plan.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"banking_resolution_{name}_{ts}.json"
        path.write_text(
            json.dumps(plan.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path
