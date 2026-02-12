"""
Jurisdiction Intelligence Engine
=================================

Self-learning jurisdiction knowledge base that maps:
  - SWIFT membership rules per entity type
  - License-to-capability mapping per jurisdiction
  - Regulatory body registry
  - Cross-border routing intelligence
  - Banking infrastructure per jurisdiction

Design: The system starts with a curated knowledge base and
accumulates intelligence from every deal it processes. Each
entity validation enriches the jurisdiction model.

This is the "self-aware learning mechanism" — it doesn't use AI.
It uses structured accumulation: every deal adds data points
that refine the system's understanding of each jurisdiction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import ROOT_DIR

INTEL_DIR = ROOT_DIR / "data" / "jurisdiction_intel"


# ── Jurisdiction Knowledge Models ───────────────────────────────


@dataclass
class SwiftMembershipRules:
    """SWIFT membership eligibility rules for a jurisdiction."""
    eligible_entity_types: list[str] = field(default_factory=list)
    ineligible_entity_types: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class LicenseCapability:
    """Maps a license type to the capabilities it grants."""
    license_type: str
    regulator: str
    capabilities: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    swift_eligible: bool = False
    can_custody: bool = False
    can_issue_instruments: bool = False
    can_settle: bool = False


@dataclass
class RegulatoryBody:
    """A regulatory authority in a jurisdiction."""
    name: str
    abbreviation: str
    jurisdiction: str
    oversight_areas: list[str] = field(default_factory=list)
    website: str | None = None


@dataclass
class BankingInfrastructure:
    """Banking infrastructure profile for a jurisdiction."""
    domestic_swift_banks: list[str] = field(default_factory=list)
    correspondent_banks: list[str] = field(default_factory=list)
    central_bank: str | None = None
    currency: str = "USD"
    fx_controls: bool = False
    fx_authority: str | None = None
    clearing_systems: list[str] = field(default_factory=list)
    settlement_finality: str | None = None


@dataclass
class JurisdictionProfile:
    """Complete intelligence profile for a jurisdiction."""
    jurisdiction_code: str
    jurisdiction_name: str
    region: str  # APAC, EMEA, AMERICAS, etc.
    legal_system: str  # common_law, civil_law, mixed, sharia
    swift_rules: SwiftMembershipRules = field(default_factory=SwiftMembershipRules)
    license_capabilities: list[LicenseCapability] = field(default_factory=list)
    regulatory_bodies: list[RegulatoryBody] = field(default_factory=list)
    banking: BankingInfrastructure = field(default_factory=BankingInfrastructure)
    treaty_memberships: list[str] = field(default_factory=list)
    aml_framework: str | None = None
    fatf_status: str | None = None  # MEMBER, GREY_LIST, BLACK_LIST, OBSERVER
    sanctions_exposure: list[str] = field(default_factory=list)
    deal_count: int = 0  # How many deals the system has processed in this jurisdiction
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    learned_notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"JURISDICTION INTELLIGENCE: {self.jurisdiction_code}",
            f"  {self.jurisdiction_name}",
            "=" * 60,
            f"Region:       {self.region}",
            f"Legal System: {self.legal_system}",
            f"FATF Status:  {self.fatf_status or 'Unknown'}",
            f"Deals Processed: {self.deal_count}",
            "",
        ]

        # SWIFT
        lines.append("--- SWIFT MEMBERSHIP ---")
        if self.swift_rules.eligible_entity_types:
            lines.append(f"  Eligible: {', '.join(self.swift_rules.eligible_entity_types)}")
        if self.swift_rules.ineligible_entity_types:
            lines.append(f"  Ineligible: {', '.join(self.swift_rules.ineligible_entity_types)}")
        for n in self.swift_rules.notes:
            lines.append(f"  Note: {n}")

        # Licenses
        if self.license_capabilities:
            lines.append("")
            lines.append("--- LICENSE CAPABILITIES ---")
            for lc in self.license_capabilities:
                swift_tag = " [SWIFT-eligible]" if lc.swift_eligible else ""
                lines.append(f"  {lc.license_type} ({lc.regulator}){swift_tag}")
                for cap in lc.capabilities:
                    lines.append(f"    + {cap}")
                for res in lc.restrictions:
                    lines.append(f"    - {res}")

        # Banking
        lines.append("")
        lines.append("--- BANKING INFRASTRUCTURE ---")
        lines.append(f"  Central Bank: {self.banking.central_bank or 'Unknown'}")
        lines.append(f"  Currency: {self.banking.currency}")
        lines.append(f"  FX Controls: {'YES' if self.banking.fx_controls else 'NO'}")
        if self.banking.fx_authority:
            lines.append(f"  FX Authority: {self.banking.fx_authority}")
        if self.banking.correspondent_banks:
            lines.append(f"  Correspondent Banks: {', '.join(self.banking.correspondent_banks)}")

        # Regulatory Bodies
        if self.regulatory_bodies:
            lines.append("")
            lines.append("--- REGULATORS ---")
            for rb in self.regulatory_bodies:
                lines.append(f"  {rb.abbreviation} ({rb.name})")
                lines.append(f"    Oversight: {', '.join(rb.oversight_areas)}")

        # Learned notes
        if self.learned_notes:
            lines.append("")
            lines.append("--- LEARNED INTELLIGENCE ---")
            for note in self.learned_notes:
                lines.append(f"  * {note}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "jurisdiction_code": self.jurisdiction_code,
            "jurisdiction_name": self.jurisdiction_name,
            "region": self.region,
            "legal_system": self.legal_system,
            "fatf_status": self.fatf_status,
            "deal_count": self.deal_count,
            "swift_rules": {
                "eligible": self.swift_rules.eligible_entity_types,
                "ineligible": self.swift_rules.ineligible_entity_types,
                "notes": self.swift_rules.notes,
            },
            "license_capabilities": [
                {
                    "license_type": lc.license_type,
                    "regulator": lc.regulator,
                    "capabilities": lc.capabilities,
                    "restrictions": lc.restrictions,
                    "swift_eligible": lc.swift_eligible,
                    "can_custody": lc.can_custody,
                    "can_issue_instruments": lc.can_issue_instruments,
                    "can_settle": lc.can_settle,
                }
                for lc in self.license_capabilities
            ],
            "regulatory_bodies": [
                {
                    "name": rb.name,
                    "abbreviation": rb.abbreviation,
                    "oversight_areas": rb.oversight_areas,
                }
                for rb in self.regulatory_bodies
            ],
            "banking": {
                "central_bank": self.banking.central_bank,
                "currency": self.banking.currency,
                "fx_controls": self.banking.fx_controls,
                "fx_authority": self.banking.fx_authority,
                "correspondent_banks": self.banking.correspondent_banks,
                "domestic_swift_banks": self.banking.domestic_swift_banks,
            },
            "treaty_memberships": self.treaty_memberships,
            "aml_framework": self.aml_framework,
            "sanctions_exposure": self.sanctions_exposure,
            "learned_notes": self.learned_notes,
            "last_updated": self.last_updated,
        }


# ── Curated Jurisdiction Knowledge Base ─────────────────────────

def _build_base_profiles() -> dict[str, JurisdictionProfile]:
    """Curated starting knowledge. Enriched by every deal processed."""
    profiles: dict[str, JurisdictionProfile] = {}

    # ── United States ───────────────────────────────────────────
    profiles["US"] = JurisdictionProfile(
        jurisdiction_code="US",
        jurisdiction_name="United States of America",
        region="AMERICAS",
        legal_system="common_law",
        fatf_status="MEMBER",
        aml_framework="Bank Secrecy Act / USA PATRIOT Act / FinCEN",
        swift_rules=SwiftMembershipRules(
            eligible_entity_types=["bank", "payment_institution", "securities_depository"],
            ineligible_entity_types=[
                "broker_dealer", "ria", "fund", "custodian",
                "securities_house", "family_office",
            ],
            notes=[
                "Non-bank financial entities use banking partners for SWIFT",
                "Broker-dealers (e.g., Pershing) clear through banks on SWIFT",
            ],
        ),
        license_capabilities=[
            LicenseCapability(
                license_type="broker_dealer",
                regulator="FINRA/SEC",
                capabilities=["trade execution", "client custody", "clearing"],
                restrictions=["Cannot accept deposits", "Cannot issue loans directly"],
                swift_eligible=False,
                can_custody=True,
                can_issue_instruments=True,
                can_settle=False,
            ),
            LicenseCapability(
                license_type="investment_adviser",
                regulator="SEC",
                capabilities=["advisory", "discretionary management", "fund management"],
                restrictions=["Cannot custody directly without separate license"],
                swift_eligible=False,
                can_custody=False,
                can_issue_instruments=False,
                can_settle=False,
            ),
            LicenseCapability(
                license_type="national_bank",
                regulator="OCC",
                capabilities=["deposits", "lending", "settlement", "custody", "fx"],
                swift_eligible=True,
                can_custody=True,
                can_issue_instruments=True,
                can_settle=True,
            ),
        ],
        regulatory_bodies=[
            RegulatoryBody("Securities and Exchange Commission", "SEC", "US",
                           ["securities", "investment_advisers", "funds"]),
            RegulatoryBody("Financial Industry Regulatory Authority", "FINRA", "US",
                           ["broker_dealers", "market_conduct"]),
            RegulatoryBody("Office of the Comptroller of the Currency", "OCC", "US",
                           ["national_banks", "thrifts"]),
            RegulatoryBody("Financial Crimes Enforcement Network", "FinCEN", "US",
                           ["aml", "cft", "bsa_reporting"]),
            RegulatoryBody("Office of Foreign Assets Control", "OFAC", "US",
                           ["sanctions", "embargoes", "trade_restrictions"]),
        ],
        banking=BankingInfrastructure(
            central_bank="Federal Reserve System",
            currency="USD",
            fx_controls=False,
            domestic_swift_banks=["CHASUS33", "BOFAUS3N", "IRVTUS3N", "CITIUS33"],
            correspondent_banks=["JP Morgan", "BNY Mellon", "Citibank", "Bank of America"],
            clearing_systems=["Fedwire", "CHIPS", "ACH", "DTC", "NSCC"],
            settlement_finality="Real-time (Fedwire), Same-day (CHIPS)",
        ),
        treaty_memberships=[
            "New York Convention (1958)",
            "Hague Convention",
            "US-VN Bilateral Trade Agreement",
            "FATCA (reporting framework)",
        ],
        sanctions_exposure=[
            "OFAC SDN List",
            "FCPA anti-bribery",
            "Dodd-Frank (financial instruments)",
            "FATCA (tax reporting)",
        ],
    )

    # ── Vietnam ─────────────────────────────────────────────────
    profiles["VN"] = JurisdictionProfile(
        jurisdiction_code="VN",
        jurisdiction_name="Socialist Republic of Vietnam",
        region="APAC",
        legal_system="civil_law",
        fatf_status="MEMBER",
        aml_framework="Law on Anti-Money Laundering (2022)",
        swift_rules=SwiftMembershipRules(
            eligible_entity_types=["bank", "central_bank"],
            ineligible_entity_types=[
                "securities_house", "custodian", "fund",
                "financial_intermediary",
            ],
            notes=[
                "Vietnamese financial/securities houses use partner banks for SWIFT",
                "Activity codes 5210ff/6619ff grant custody but NOT SWIFT access",
                "Standard practice: custodian authorizes, bank executes SWIFT",
            ],
        ),
        license_capabilities=[
            LicenseCapability(
                license_type="custody_depository",
                regulator="Vietnam Ministry of Finance",
                capabilities=[
                    "hold private M0",
                    "issue deposit certificates",
                    "issue custody statements",
                    "issue payment authorizations",
                    "issue guarantees",
                    "issue credit instruments",
                    "act as securities custodian",
                ],
                restrictions=[
                    "Cannot operate as correspondent bank",
                    "Cannot send/receive SWIFT messages directly",
                    "Must use banking partner for cross-border settlement",
                ],
                swift_eligible=False,
                can_custody=True,
                can_issue_instruments=True,
                can_settle=False,
            ),
            LicenseCapability(
                license_type="financial_intermediation",
                regulator="Vietnam Ministry of Finance",
                capabilities=["intermediation", "brokerage", "advisory"],
                swift_eligible=False,
                can_custody=False,
                can_issue_instruments=False,
                can_settle=False,
            ),
        ],
        regulatory_bodies=[
            RegulatoryBody("State Bank of Vietnam", "SBV", "VN",
                           ["banking", "fx_controls", "monetary_policy", "aml"]),
            RegulatoryBody("Ministry of Finance", "MOF", "VN",
                           ["securities", "insurance", "fiscal_policy"]),
            RegulatoryBody("State Securities Commission", "SSC", "VN",
                           ["securities_markets", "fund_management"]),
        ],
        banking=BankingInfrastructure(
            central_bank="State Bank of Vietnam (SBV)",
            currency="VND",
            fx_controls=True,
            fx_authority="State Bank of Vietnam (SBV)",
            domestic_swift_banks=["BFTVVNVX", "BFTKVNVX", "ICBVVNVX"],
            correspondent_banks=["Standard Chartered", "HSBC", "Citibank"],
            clearing_systems=["NAPAS", "SBV RTGS"],
        ),
        treaty_memberships=[
            "New York Convention (1958) — via VIAC",
            "ASEAN Framework Agreement",
            "US-VN Bilateral Trade Agreement",
            "Vietnam-EU Free Trade Agreement",
        ],
        sanctions_exposure=[
            "SBV currency control compliance",
            "Tax clearance for profit repatriation",
            "Capital account registration requirement",
        ],
    )

    # ── Switzerland ─────────────────────────────────────────────
    profiles["CH"] = JurisdictionProfile(
        jurisdiction_code="CH",
        jurisdiction_name="Swiss Confederation",
        region="EMEA",
        legal_system="civil_law",
        fatf_status="MEMBER",
        aml_framework="AMLA (Anti-Money Laundering Act) / FINMA",
        swift_rules=SwiftMembershipRules(
            eligible_entity_types=["bank", "securities_dealer"],
            notes=["Swiss banking secrecy partially lifted for AML/tax purposes"],
        ),
        regulatory_bodies=[
            RegulatoryBody("Swiss Financial Market Supervisory Authority", "FINMA", "CH",
                           ["banking", "securities", "insurance", "aml"]),
        ],
        banking=BankingInfrastructure(
            central_bank="Swiss National Bank (SNB)",
            currency="CHF",
            fx_controls=False,
            clearing_systems=["SIX SIS", "SIX Interbank Clearing"],
        ),
        treaty_memberships=[
            "New York Convention (1958)",
            "Hague Convention",
            "Swiss-US Tax Information Exchange",
        ],
    )

    # ── Italy ───────────────────────────────────────────────────
    profiles["IT"] = JurisdictionProfile(
        jurisdiction_code="IT",
        jurisdiction_name="Italian Republic",
        region="EMEA",
        legal_system="civil_law",
        fatf_status="MEMBER",
        aml_framework="EU Anti-Money Laundering Directives / UIF",
        regulatory_bodies=[
            RegulatoryBody("Bank of Italy", "BOI", "IT",
                           ["banking", "payment_systems", "aml"]),
            RegulatoryBody("CONSOB", "CONSOB", "IT",
                           ["securities", "markets"]),
        ],
        banking=BankingInfrastructure(
            central_bank="Bank of Italy / ECB",
            currency="EUR",
            fx_controls=False,
            clearing_systems=["TARGET2", "Monte Titoli"],
        ),
    )

    return profiles


# ── Jurisdiction Intelligence Engine ────────────────────────────


class JurisdictionIntelEngine:
    """
    Self-learning jurisdiction knowledge base.

    Starts with curated profiles and enriches from every deal:
    - New entities teach the system about their jurisdiction
    - Banking relationships map correspondent networks
    - Compliance findings become learned notes
    - Each deal increments the jurisdiction's deal_count
    """

    def __init__(self) -> None:
        self._profiles = _build_base_profiles()
        self._load_persisted()

    def get_profile(self, jurisdiction_code: str) -> JurisdictionProfile | None:
        """Get jurisdiction profile. Returns None if unknown."""
        code = jurisdiction_code.upper()[:2]
        return self._profiles.get(code)

    def get_or_create(self, jurisdiction_code: str) -> JurisdictionProfile:
        """Get or create a minimal profile for an unknown jurisdiction."""
        code = jurisdiction_code.upper()[:2]
        if code not in self._profiles:
            self._profiles[code] = JurisdictionProfile(
                jurisdiction_code=code,
                jurisdiction_name=f"Unknown ({code})",
                region="UNKNOWN",
                legal_system="unknown",
                learned_notes=["Auto-created from deal processing. Needs enrichment."],
            )
        return self._profiles[code]

    def learn_from_entity(self, entity: dict) -> list[str]:
        """
        Extract jurisdiction intelligence from an entity profile.
        Returns list of new learnings added.
        """
        e = entity.get("entity", entity)
        jurisdiction = e.get("jurisdiction", "")[:2]
        if not jurisdiction:
            return []

        profile = self.get_or_create(jurisdiction)
        learnings: list[str] = []

        # Learn from licenses
        for lic in e.get("licenses", []):
            lic_type = lic.get("license_type", "")
            regulator = lic.get("regulator", "")
            capabilities = lic.get("capabilities", [])

            # Check if we already know this license type
            known = any(
                lc.license_type == lic_type
                for lc in profile.license_capabilities
            )
            if not known and lic_type:
                new_lc = LicenseCapability(
                    license_type=lic_type,
                    regulator=regulator,
                    capabilities=capabilities,
                )
                profile.license_capabilities.append(new_lc)
                note = f"Learned license type '{lic_type}' from {regulator}"
                learnings.append(note)
                profile.learned_notes.append(
                    f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}] {note}"
                )

        # Learn from banking relationships
        banking = e.get("banking", {})
        settlement = banking.get("settlement_bank")
        swift = banking.get("swift_code")
        if settlement and settlement not in profile.banking.correspondent_banks:
            profile.banking.correspondent_banks.append(settlement)
            note = f"Learned banking relationship: {settlement}"
            if swift:
                note += f" [{swift}]"
            learnings.append(note)

        corr = banking.get("correspondent_bank")
        if corr and corr not in profile.banking.correspondent_banks:
            profile.banking.correspondent_banks.append(corr)

        # Learn from regulatory status
        reg = e.get("regulatory_status", {})
        swift_eligible = reg.get("swift_eligible")
        if swift_eligible is False:
            entity_type = e.get("entity_type", "unknown")
            if entity_type not in profile.swift_rules.ineligible_entity_types:
                profile.swift_rules.ineligible_entity_types.append(entity_type)
                note = f"Confirmed '{entity_type}' is NOT SWIFT-eligible in {jurisdiction}"
                learnings.append(note)

        profile.deal_count += 1
        profile.last_updated = datetime.now(timezone.utc).isoformat()

        return learnings

    def learn_from_deal(
        self,
        entity: dict,
        counterparty: dict | None = None,
        findings: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """
        Learn from a complete deal. Returns learnings per jurisdiction.
        """
        results: dict[str, list[str]] = {}

        e_learnings = self.learn_from_entity(entity)
        ej = entity.get("entity", entity).get("jurisdiction", "??")[:2]
        if e_learnings:
            results[ej] = e_learnings

        if counterparty:
            cp_learnings = self.learn_from_entity(counterparty)
            cj = counterparty.get("entity", counterparty).get("jurisdiction", "??")[:2]
            if cp_learnings:
                results[cj] = cp_learnings

        return results

    def can_entity_use_swift(self, entity: dict) -> tuple[bool, str]:
        """Check if an entity is SWIFT-eligible based on jurisdiction rules."""
        e = entity.get("entity", entity)
        reg = e.get("regulatory_status", {})

        # Explicit flag
        if reg.get("swift_eligible") is False:
            partner = reg.get("uses_partner_bank_for_swift", False)
            if partner:
                return False, (
                    "Entity is not SWIFT-eligible but uses a partner bank "
                    "for SWIFT-based settlement. This is standard institutional practice."
                )
            return False, "Entity is not SWIFT-eligible."

        if reg.get("is_bank", False):
            return True, "Entity is a bank and SWIFT-eligible."

        # Check jurisdiction rules
        jurisdiction = e.get("jurisdiction", "")[:2]
        profile = self.get_profile(jurisdiction)
        if profile:
            entity_type = e.get("entity_type", "")
            if entity_type in profile.swift_rules.eligible_entity_types:
                return True, f"Entity type '{entity_type}' is SWIFT-eligible in {jurisdiction}."
            if entity_type in profile.swift_rules.ineligible_entity_types:
                return False, (
                    f"Entity type '{entity_type}' is NOT SWIFT-eligible in {jurisdiction}. "
                    f"Must use a banking partner for SWIFT rails."
                )

        return False, "SWIFT eligibility unknown. Recommend confirming with banking partner."

    def list_profiles(self) -> list[JurisdictionProfile]:
        """Return all known jurisdiction profiles."""
        return sorted(self._profiles.values(), key=lambda p: p.jurisdiction_code)

    def save(self) -> Path:
        """Persist learned intelligence to disk."""
        INTEL_DIR.mkdir(parents=True, exist_ok=True)
        path = INTEL_DIR / "jurisdiction_knowledge.json"
        data = {
            code: profile.to_dict()
            for code, profile in self._profiles.items()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    def _load_persisted(self) -> None:
        """Load any previously saved intelligence."""
        path = INTEL_DIR / "jurisdiction_knowledge.json"
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for code, profile_data in data.items():
                if code in self._profiles:
                    # Merge learned notes only
                    existing = self._profiles[code]
                    existing.deal_count = max(
                        existing.deal_count,
                        profile_data.get("deal_count", 0),
                    )
                    for note in profile_data.get("learned_notes", []):
                        if note not in existing.learned_notes:
                            existing.learned_notes.append(note)
        except Exception:
            pass  # If corrupted, start fresh
