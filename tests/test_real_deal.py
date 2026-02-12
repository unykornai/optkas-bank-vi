"""
Tests for the Real-Deal Infrastructure Layer.

Covers:
  - CorrespondentBankingEngine — settlement path mapping, validation
  - CapitalStructureBuilder — allocation, waterfall, governance validation
  - JurisdictionIntelEngine — profiles, learning, SWIFT eligibility
  - Real entity loading — querubin_usa.yaml, updated sample_vn_entity.yaml
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.schema_loader import load_entity, ROOT_DIR
from engine.correspondent_banking import (
    CorrespondentBankingEngine,
    SettlementPath,
    BankNode,
    KNOWN_BANKS,
)
from engine.capital_structure import (
    CapitalStructureBuilder,
    CapitalStructure,
    CapitalCommitment,
    RevenueAllocation,
)
from engine.jurisdiction_intel import (
    JurisdictionIntelEngine,
    JurisdictionProfile,
)


ENTITIES_DIR = ROOT_DIR / "data" / "entities"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def querubin():
    return load_entity(ENTITIES_DIR / "querubin_usa.yaml")


@pytest.fixture
def dn2nc():
    return load_entity(ENTITIES_DIR / "sample_vn_entity.yaml")


@pytest.fixture
def us_entity():
    return load_entity(ENTITIES_DIR / "sample_us_corp.yaml")


# =========================================================================
# CorrespondentBankingEngine
# =========================================================================

class TestCorrespondentBanking:
    def test_resolve_path_querubin_to_dn2nc(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)

        assert path.originator_entity == "Querubin USA, LLC"
        assert path.beneficiary_entity == "DN2NC Digital Assets Joint Stock Company"
        assert len(path.nodes) >= 3
        assert path.requires_fx is True

    def test_path_has_swift_node(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)

        swift_nodes = [n for n in path.nodes if n.swift_code]
        assert len(swift_nodes) >= 1

    def test_non_bank_gets_partner_bank(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)

        partner_nodes = [n for n in path.nodes if n.role == "partner_bank"]
        assert len(partner_nodes) >= 1

    def test_path_notes_explain_non_swift(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)

        partner_notes = [n for n in path.validation_notes if "not a bank" in n.lower() or "partner bank" in n.lower()]
        assert len(partner_notes) >= 1

    def test_fx_approval_for_vietnam(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)

        assert path.fx_approval_required is True
        assert "SBV" in (path.fx_authority or "")

    def test_same_jurisdiction_no_fx(self, querubin, us_entity):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, us_entity)

        assert path.requires_fx is False

    def test_path_summary_readable(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)
        summary = path.summary()

        assert "SETTLEMENT PATH ANALYSIS" in summary
        assert "Querubin" in summary

    def test_path_to_dict(self, querubin, dn2nc):
        engine = CorrespondentBankingEngine()
        path = engine.resolve_settlement_path(querubin, dn2nc)
        d = path.to_dict()

        assert json.dumps(d)
        assert d["requires_fx"] is True
        assert len(d["nodes"]) >= 3

    def test_known_banks_registry(self):
        assert "CHASUS33" in KNOWN_BANKS
        assert "IRVTUS3N" in KNOWN_BANKS
        assert KNOWN_BANKS["IRVTUS3N"]["name"] == "The Bank of New York Mellon Corporation"


# =========================================================================
# CapitalStructure
# =========================================================================

class TestCapitalStructure:
    def test_build_jv_structure(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="OPTKAS x Bank JV",
            parties=[
                {"party_name": "UHNWI Family", "party_type": "uhnwi", "commitment_percentage": 50},
                {"party_name": "Wealth Manager", "party_type": "wealth_manager", "commitment_percentage": 10},
                {"party_name": "Family Office", "party_type": "family_office", "commitment_percentage": 10},
                {"party_name": "Querubin", "party_type": "gp", "commitment_percentage": 15},
                {"party_name": "Partner Group", "party_type": "partner", "commitment_percentage": 15},
            ],
        )

        assert structure.total_committed_pct == 100.0
        assert structure.is_fully_allocated is True
        assert len(structure.commitments) == 5

    def test_allocation_sums_validated(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="Bad Alloc",
            parties=[
                {"party_name": "A", "commitment_percentage": 60},
                {"party_name": "B", "commitment_percentage": 60},
            ],
        )

        issues = structure.validate()
        assert any("120" in i for i in issues)  # Overallocated

    def test_underallocated_flagged(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="Under",
            parties=[
                {"party_name": "A", "commitment_percentage": 30},
            ],
        )

        issues = structure.validate()
        assert any("Underallocated" in i for i in issues)

    def test_in_kind_requires_description(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="InKind Test",
            parties=[
                {"party_name": "OPTKAS", "commitment_percentage": 50, "contribution_type": "in_kind"},
                {"party_name": "Bank", "commitment_percentage": 50, "contribution_type": "cash"},
            ],
        )

        issues = structure.validate()
        assert any("In-kind" in i for i in issues)

    def test_in_kind_with_description_ok(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="InKind OK",
            parties=[
                {
                    "party_name": "OPTKAS",
                    "commitment_percentage": 50,
                    "contribution_type": "in_kind",
                    "in_kind_description": "Sovereign infrastructure, tokenization engines, deal pipeline",
                },
                {"party_name": "Bank", "commitment_percentage": 50, "contribution_type": "cash"},
            ],
            governance_rules=["Dual-signature authority"],
        )

        in_kind_issues = [i for i in structure.validate() if "In-kind" in i]
        assert len(in_kind_issues) == 0

    def test_governance_required(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="No Gov",
            parties=[{"party_name": "A", "commitment_percentage": 100}],
        )

        issues = structure.validate()
        assert any("governance" in i.lower() for i in issues)

    def test_revenue_waterfall(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="Rev Split",
            parties=[
                {"party_name": "A", "commitment_percentage": 50},
                {"party_name": "B", "commitment_percentage": 50},
            ],
            revenue_splits=[
                {"party_name": "A", "revenue_percentage": 50, "priority": 1},
                {"party_name": "B", "revenue_percentage": 50, "priority": 1},
            ],
            governance_rules=["Dual-signature"],
        )

        rev_issues = [i for i in structure.validate() if "Revenue" in i]
        assert len(rev_issues) == 0

    def test_summary_readable(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="Test JV",
            total_commitment=10_000_000,
            parties=[
                {"party_name": "A", "commitment_percentage": 50, "commitment_amount": 5_000_000},
                {"party_name": "B", "commitment_percentage": 50, "commitment_amount": 5_000_000},
            ],
            governance_rules=["Dual-signature"],
        )

        summary = structure.summary()
        assert "CAPITAL STRUCTURE" in summary
        assert "Test JV" in summary

    def test_to_dict_serializable(self):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="Dict Test",
            parties=[{"party_name": "A", "commitment_percentage": 100}],
        )

        d = structure.to_dict()
        assert json.dumps(d)
        assert d["is_fully_allocated"] is True

    def test_save(self, tmp_path):
        builder = CapitalStructureBuilder()
        structure = builder.build_jv_structure(
            deal_name="Save Test",
            parties=[{"party_name": "A", "commitment_percentage": 100}],
        )

        path = builder.save(structure, directory=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["deal_name"] == "Save Test"

    def test_funded_tracking(self):
        c = CapitalCommitment(
            party_name="Investor",
            party_type="uhnwi",
            commitment_percentage=50,
            commitment_amount=5_000_000,
            funded_amount=2_500_000,
        )
        assert c.unfunded == 2_500_000
        assert c.funded_percentage == 50.0


# =========================================================================
# JurisdictionIntelEngine
# =========================================================================

class TestJurisdictionIntel:
    def test_us_profile_exists(self):
        intel = JurisdictionIntelEngine()
        us = intel.get_profile("US")

        assert us is not None
        assert us.jurisdiction_name == "United States of America"
        assert us.fatf_status == "MEMBER"

    def test_vn_profile_exists(self):
        intel = JurisdictionIntelEngine()
        vn = intel.get_profile("VN")

        assert vn is not None
        assert vn.banking.fx_controls is True
        assert "SBV" in (vn.banking.fx_authority or "")

    def test_ch_profile_exists(self):
        intel = JurisdictionIntelEngine()
        ch = intel.get_profile("CH")

        assert ch is not None
        assert ch.legal_system == "civil_law"

    def test_unknown_jurisdiction_returns_none(self):
        intel = JurisdictionIntelEngine()
        assert intel.get_profile("ZZ") is None

    def test_get_or_create_unknown(self):
        intel = JurisdictionIntelEngine()
        profile = intel.get_or_create("ZZ")

        assert profile.jurisdiction_code == "ZZ"
        assert any("Auto-created" in n for n in profile.learned_notes)

    def test_learn_from_entity(self, dn2nc):
        intel = JurisdictionIntelEngine()
        learnings = intel.learn_from_entity(dn2nc)

        # Should learn something from DN2NC's Vietnam profile
        vn = intel.get_profile("VN")
        assert vn.deal_count >= 1

    def test_learn_from_querubin(self, querubin):
        intel = JurisdictionIntelEngine()
        learnings = intel.learn_from_entity(querubin)

        us = intel.get_profile("US")
        assert us.deal_count >= 1

    def test_swift_eligibility_dn2nc(self, dn2nc):
        intel = JurisdictionIntelEngine()
        eligible, reason = intel.can_entity_use_swift(dn2nc)

        assert eligible is False
        assert "partner bank" in reason.lower() or "not swift" in reason.lower()

    def test_swift_eligibility_bank(self):
        intel = JurisdictionIntelEngine()
        fake_bank = {"entity": {"regulatory_status": {"is_bank": True}}}
        eligible, reason = intel.can_entity_use_swift(fake_bank)

        assert eligible is True

    def test_learn_from_deal(self, querubin, dn2nc):
        intel = JurisdictionIntelEngine()
        results = intel.learn_from_deal(querubin, dn2nc)

        # Should have learnings for at least one jurisdiction
        assert isinstance(results, dict)

    def test_list_profiles(self):
        intel = JurisdictionIntelEngine()
        profiles = intel.list_profiles()

        assert len(profiles) >= 4  # US, VN, CH, IT
        codes = {p.jurisdiction_code for p in profiles}
        assert "US" in codes
        assert "VN" in codes

    def test_profile_summary(self):
        intel = JurisdictionIntelEngine()
        us = intel.get_profile("US")
        summary = us.summary()

        assert "JURISDICTION INTELLIGENCE" in summary
        assert "United States" in summary
        assert "SWIFT MEMBERSHIP" in summary
        assert "REGULATORS" in summary

    def test_profile_to_dict(self):
        intel = JurisdictionIntelEngine()
        us = intel.get_profile("US")
        d = us.to_dict()

        assert json.dumps(d)
        assert d["fatf_status"] == "MEMBER"
        assert len(d["regulatory_bodies"]) >= 3

    def test_save_and_persistence(self, tmp_path):
        intel = JurisdictionIntelEngine()
        # Modify something
        us = intel.get_profile("US")
        us.deal_count = 42
        path = intel.save()
        assert path.exists()


# =========================================================================
# Real Entity Loading
# =========================================================================

class TestRealEntities:
    def test_load_querubin(self, querubin):
        # load_entity() returns inner entity dict directly
        assert querubin["legal_name"] == "Querubin USA, LLC"
        assert querubin["ein"] == "84-1975191"
        assert querubin["jurisdiction"] == "US-NY"
        assert len(querubin["directors"]) == 2
        assert len(querubin["signatories"]) == 2
        assert len(querubin["beneficial_owners"]) == 2

    def test_querubin_banking(self, querubin):
        b = querubin["banking"]
        assert b["swift_code"] == "IRVTUS3N"
        assert b["custodian"] == "Pershing LLC"
        assert b["settlement_bank"] == "The Bank of New York Mellon Corporation"
        assert b["ultimate_beneficiary_name"] == "Querubin USA, LLC"

    def test_querubin_directors(self, querubin):
        directors = querubin["directors"]
        names = {d["name"] for d in directors}
        assert "Domenico Savio Danieli" in names
        assert "Rudy Agustin Rodriguez" in names

    def test_querubin_beneficial_owners(self, querubin):
        owners = querubin["beneficial_owners"]
        nationalities = {o["nationality"] for o in owners}
        assert "IT" in nationalities
        assert "US" in nationalities

    def test_dn2nc_has_licenses(self, dn2nc):
        assert len(dn2nc["licenses"]) >= 3
        types = {lic["license_type"] for lic in dn2nc["licenses"]}
        assert "custody_depository" in types
        assert "financial_intermediation" in types

    def test_dn2nc_swift_status(self, dn2nc):
        reg = dn2nc["regulatory_status"]
        assert reg.get("swift_eligible") is False
        assert reg.get("uses_partner_bank_for_swift") is True
