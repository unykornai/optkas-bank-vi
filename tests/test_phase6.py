"""
Tests for Phase 6: Governance, Fund Flow, Compliance Package, and expanded entities.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from engine.schema_loader import load_entity
from engine.governance_rules import (
    GovernanceBuilder,
    GovernanceFramework,
    Committee,
    DecisionThreshold,
    SignatureRule,
    ReportingRequirement,
)
from engine.fund_flow import (
    FundFlowBuilder,
    FundFlowLedger,
    PartyFlow,
    FlowState,
    FlowEvent,
    VALID_TRANSITIONS,
)
from engine.compliance_package import (
    CompliancePackageGenerator,
    CompliancePackage,
    EvidenceItem,
)


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def tc_advantage():
    return load_entity(Path("data/entities/tc_advantage_traders.yaml"))


@pytest.fixture
def optkas1_spv():
    return load_entity(Path("data/entities/optkas1_spv.yaml"))


@pytest.fixture
def optkas_platform():
    return load_entity(Path("data/entities/optkas_platform.yaml"))


@pytest.fixture
def cuerpo_markets():
    return load_entity(Path("data/entities/cuerpo_markets.yaml"))


@pytest.fixture
def sample_cap_structure(tmp_path):
    """Create a sample capital structure JSON for testing."""
    cs = {
        "deal_name": "Test JV",
        "total_commitment": 10_000_000,
        "currency": "USD",
        "total_committed_pct": 100.0,
        "commitments": [
            {
                "party_name": "UHNWI Family",
                "party_type": "uhnwi",
                "commitment_percentage": 50.0,
                "commitment_amount": 5_000_000,
                "contribution_type": "cash",
                "funded_amount": 0.0,
                "status": "COMMITTED",
            },
            {
                "party_name": "GP Partner",
                "party_type": "gp",
                "commitment_percentage": 50.0,
                "commitment_amount": 5_000_000,
                "contribution_type": "cash",
                "funded_amount": 0.0,
                "status": "COMMITTED",
            },
        ],
    }
    path = tmp_path / "test_cap.json"
    path.write_text(json.dumps(cs), encoding="utf-8")
    return path


# =========================================================================
# Test Entity Loading (new entities)
# =========================================================================

class TestNewEntities:
    def test_load_tc_advantage(self, tc_advantage):
        assert tc_advantage["legal_name"] == "TC Advantage Traders, Ltd."
        assert tc_advantage["jurisdiction"] == "BS"
        assert tc_advantage["entity_type"] == "limited_company"

    def test_tc_advantage_mtn_program(self, tc_advantage):
        mtn = tc_advantage["mtn_program"]
        assert mtn["max_offering"] == 5_000_000_000
        assert mtn["coupon_rate"] == 5.0
        assert mtn["settlement_method"] == "DTC/DWAC FAST"
        assert len(mtn["cusips"]) >= 4

    def test_tc_advantage_cusips(self, tc_advantage):
        cusips = tc_advantage["mtn_program"]["cusips"]
        ids = {c["id"] for c in cusips}
        assert "87225HAB4" in ids  # 144A
        assert "P9000TAA8" in ids  # Reg S

    def test_tc_advantage_insurance(self, tc_advantage):
        ins = tc_advantage["insurance"]
        assert ins["broker"]["fca_number"] == 30820
        assert ins["coverage"]["sum_insured"] == 625_000_000
        assert "Lloyd's of London" in ins["coverage"]["market"]

    def test_tc_advantage_legal_opinions(self, tc_advantage):
        opinions = tc_advantage["legal_opinions"]
        assert len(opinions) >= 2
        scopes_all = []
        for op in opinions:
            scopes_all.extend(op.get("scope", []))
        assert any("XRPL" in s for s in scopes_all)

    def test_tc_advantage_stc(self, tc_advantage):
        stc = tc_advantage["mtn_program"]["transfer_agent"]
        assert stc["name"] == "Securities Transfer Corporation"
        assert "Transfer Agent" in stc["roles"]
        assert "Escrow Agent" in stc["roles"]
        assert "Paying Agent" in stc["roles"]

    def test_load_optkas1_spv(self, optkas1_spv):
        assert optkas1_spv["legal_name"] == "OPTKAS1-MAIN"
        assert optkas1_spv["jurisdiction"] == "US-WY"
        assert optkas1_spv["entity_type"] == "special_purpose_vehicle"

    def test_optkas1_xrpl_system(self, optkas1_spv):
        xrpl = optkas1_spv["xrpl_reserve_system"]
        assert xrpl["name"] == "Optima XRPL System"
        categories = [c["type"] for c in xrpl["components"][1]["categories"]]
        assert "CREDIT_MTN" in categories
        assert "CASH" in categories

    def test_optkas1_collateral(self, optkas1_spv):
        coll = optkas1_spv["collateral_holdings"]
        assert "87225HAB4" in coll["cusips_referenced"]
        assert coll["perfection"] == "UCC filing in Wyoming + custodial control at STC"

    def test_optkas1_eligible_facilities(self, optkas1_spv):
        facilities = optkas1_spv["eligible_facilities"]
        types = {f["type"] for f in facilities}
        assert "Secured revolving facility" in types
        assert "Repo / reverse-repo" in types
        assert "Warehouse credit line" in types

    def test_load_optkas_platform(self, optkas_platform):
        assert optkas_platform["legal_name"] == "OPTKAS Sovereign Platform"
        assert optkas_platform["entity_type"] == "sovereign_platform"

    def test_optkas_bond_program(self, optkas_platform):
        bp = optkas_platform["bond_program"]
        assert bp["size"] == 500_000_000
        assert "SEC 144A standards" in bp["securities_compliance"]

    def test_optkas_governance(self, optkas_platform):
        gov = optkas_platform["governance"]
        assert gov["structure"] == "dual_signature"
        committees = {c["name"] for c in gov["committees"]}
        assert "Risk Committee" in committees
        assert "Compliance Committee" in committees

    def test_load_cuerpo_markets(self, cuerpo_markets):
        assert cuerpo_markets["legal_name"] == "Cuerpo Markets"
        assert cuerpo_markets["entity_type"] == "sovereign_platform"

    def test_cuerpo_bond_program(self, cuerpo_markets):
        bp = cuerpo_markets["bond_program"]
        assert bp["size"] == 5_000_000_000
        assert bp["custodial_backing"] == 200_000_000_000
        assert bp["custodian"] == "STC"

    def test_cuerpo_banking(self, cuerpo_markets):
        b = cuerpo_markets["banking"]
        assert b["custodian"] == "STC (Securities Transfer Corporation)"
        assert b["custodial_value"] == 200_000_000_000


# =========================================================================
# Test Governance Rules Engine
# =========================================================================

class TestGovernanceRules:
    def test_build_institutional(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV", "50/50")
        assert fw.deal_name == "Test JV"
        assert fw.structure == "dual_signature"
        assert fw.ownership_split == "50/50"

    def test_institutional_has_committees(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        assert len(fw.committees) >= 4
        names = {c.name for c in fw.committees}
        assert "Risk Committee" in names
        assert "Compliance Committee" in names

    def test_institutional_is_compliant(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        assert fw.is_compliant
        assert len(fw.validate()) == 0

    def test_institutional_has_signature_rules(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        assert len(fw.signature_rules) >= 5
        dual_sigs = [sr for sr in fw.signature_rules if sr.required_signers >= 2]
        assert len(dual_sigs) >= 3

    def test_institutional_has_decision_thresholds(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        assert len(fw.decision_thresholds) >= 4
        categories = {dt.category for dt in fw.decision_thresholds}
        assert "capital_deployment" in categories
        assert "collateral_pledge" in categories

    def test_institutional_has_reporting(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        assert len(fw.reporting) >= 6
        freqs = {r.frequency for r in fw.reporting}
        assert "monthly" in freqs
        assert "quarterly" in freqs

    def test_empty_framework_fails_validation(self):
        fw = GovernanceFramework(deal_name="Empty")
        issues = fw.validate()
        assert len(issues) > 0
        assert not fw.is_compliant

    def test_missing_committee_flagged(self):
        fw = GovernanceFramework(
            deal_name="Partial",
            committees=[Committee("Risk Committee", "risk")],
            signature_rules=[SignatureRule("test", 2, ["admin"])],
            decision_thresholds=[DecisionThreshold("test", 1000, "dual")],
            reporting=[ReportingRequirement("test", "monthly", "internal")],
            controls=["Test control"],
        )
        issues = fw.validate()
        assert any("compliance" in i.lower() or "audit" in i.lower() for i in issues)

    def test_summary_readable(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        s = fw.summary()
        assert "GOVERNANCE FRAMEWORK" in s
        assert "DUAL-SIGNATURE" in s
        assert "Risk Committee" in s

    def test_to_dict_serializable(self):
        builder = GovernanceBuilder()
        fw = builder.build_institutional("Test JV")
        d = fw.to_dict()
        json_str = json.dumps(d)
        assert "deal_name" in json_str
        assert d["is_compliant"] is True

    def test_build_from_entity(self, optkas_platform):
        builder = GovernanceBuilder()
        fw = builder.build_from_entity(optkas_platform, "OPTKAS JV")
        assert fw.deal_name == "OPTKAS JV"
        assert fw.structure == "dual_signature"
        assert len(fw.committees) >= 4

    def test_save(self, tmp_path):
        import os
        orig = os.getcwd()
        os.chdir(tmp_path)
        try:
            builder = GovernanceBuilder()
            fw = builder.build_institutional("Save Test")
            path = builder.save(fw)
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["deal_name"] == "Save Test"
        finally:
            os.chdir(orig)


# =========================================================================
# Test Fund Flow Tracker
# =========================================================================

class TestFundFlow:
    def test_build_from_cap_structure(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)
        assert ledger.deal_name == "Test JV"
        assert len(ledger.parties) == 2
        assert ledger.total_commitment == 10_000_000

    def test_initial_state_committed(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)
        for p in ledger.parties:
            assert p.current_state == "COMMITTED"

    def test_transition_call(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        event = ledger.transition(
            "UHNWI Family", FlowState.CALLED, 5_000_000,
            authorized_by="Domenico Danieli",
        )
        assert event.to_state == "CALLED"
        assert event.amount == 5_000_000
        party = ledger.get_party("UHNWI Family")
        assert party.current_state == "CALLED"
        assert party.called_amount == 5_000_000

    def test_transition_fund(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        ledger.transition("UHNWI Family", FlowState.CALLED, 5_000_000, authorized_by="DD")
        ledger.transition("UHNWI Family", FlowState.FUNDED, 5_000_000, authorized_by="DD")
        party = ledger.get_party("UHNWI Family")
        assert party.current_state == "FUNDED"
        assert party.funded_amount == 5_000_000
        assert party.outstanding == 0.0

    def test_invalid_transition_raises(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        with pytest.raises(ValueError, match="Invalid transition"):
            ledger.transition("UHNWI Family", FlowState.DEPLOYED, 1_000_000, authorized_by="DD")

    def test_compliance_hold(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        event = ledger.transition(
            "UHNWI Family", FlowState.HELD, 0,
            authorized_by="Compliance",
            compliance_hold=True,
            hold_reason="KYC pending",
        )
        assert event.compliance_hold is True
        assert event.hold_reason == "KYC pending"

    def test_blocked_flagged_in_validation(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        ledger.transition("UHNWI Family", FlowState.CALLED, 5_000_000, authorized_by="DD")
        ledger.transition("UHNWI Family", FlowState.BLOCKED, 0, authorized_by="Compliance")
        issues = ledger.validate()
        assert any("BLOCKED" in i for i in issues)

    def test_full_lifecycle(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        ledger.transition("GP Partner", FlowState.CALLED, 5_000_000, authorized_by="DD")
        ledger.transition("GP Partner", FlowState.FUNDED, 5_000_000, authorized_by="DD")
        ledger.transition("GP Partner", FlowState.DEPLOYED, 5_000_000, authorized_by="DD")
        ledger.transition("GP Partner", FlowState.RETURNED, 5_000_000, authorized_by="DD")

        party = ledger.get_party("GP Partner")
        assert party.current_state == "RETURNED"
        assert party.net_deployed == 0.0

    def test_event_ids_sequential(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        e1 = ledger.transition("UHNWI Family", FlowState.CALLED, 5_000_000, authorized_by="DD")
        e2 = ledger.transition("GP Partner", FlowState.CALLED, 5_000_000, authorized_by="DD")
        assert e1.event_id == "FF-0001"
        assert e2.event_id == "FF-0002"

    def test_funding_percentage(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)

        ledger.transition("UHNWI Family", FlowState.CALLED, 5_000_000, authorized_by="DD")
        ledger.transition("UHNWI Family", FlowState.FUNDED, 5_000_000, authorized_by="DD")
        assert ledger.funding_percentage == 50.0

    def test_summary_readable(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)
        s = ledger.summary()
        assert "FUND FLOW LEDGER" in s
        assert "UHNWI Family" in s

    def test_to_dict_serializable(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)
        d = ledger.to_dict()
        json_str = json.dumps(d)
        assert "deal_name" in json_str

    def test_save(self, sample_cap_structure, tmp_path):
        import os
        orig = os.getcwd()
        os.chdir(tmp_path)
        try:
            cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
            builder = FundFlowBuilder()
            ledger = builder.build_from_capital_structure(cs_data)
            path = builder.save(ledger)
            assert path.exists()
        finally:
            os.chdir(orig)

    def test_party_not_found_raises(self, sample_cap_structure):
        cs_data = json.loads(sample_cap_structure.read_text(encoding="utf-8"))
        builder = FundFlowBuilder()
        ledger = builder.build_from_capital_structure(cs_data)
        with pytest.raises(ValueError, match="not found"):
            ledger.transition("Nonexistent", FlowState.CALLED, 1000, authorized_by="DD")


# =========================================================================
# Test Compliance Package Generator
# =========================================================================

class TestCompliancePackage:
    def test_generate_basic(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Test Deal",
            entity_paths=[Path("data/entities/querubin_usa.yaml")],
        )
        assert pkg.deal_name == "Test Deal"
        assert len(pkg.entities) == 1
        assert pkg.compliance_status in ("CLEAR", "CONDITIONAL", "REQUIRES_ACTION")

    def test_generate_with_two_entities(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Cross-Border Test",
            entity_paths=[
                Path("data/entities/querubin_usa.yaml"),
                Path("data/entities/sample_vn_entity.yaml"),
            ],
        )
        assert len(pkg.entities) == 2
        assert pkg.settlement_path is not None

    def test_settlement_path_included(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Settlement Test",
            entity_paths=[
                Path("data/entities/querubin_usa.yaml"),
                Path("data/entities/sample_vn_entity.yaml"),
            ],
        )
        sp = pkg.settlement_path
        assert sp is not None
        # Settlement path uses originator_entity / beneficiary_entity keys
        assert "originator_entity" in sp or "beneficiary_entity" in sp
        assert "currency" in sp

    def test_jurisdictions_populated(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Jurisdiction Test",
            entity_paths=[
                Path("data/entities/querubin_usa.yaml"),
                Path("data/entities/sample_vn_entity.yaml"),
            ],
        )
        codes = {j["code"] for j in pkg.jurisdictions}
        assert "US" in codes
        assert "VN" in codes

    def test_governance_populated(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Governance Test",
            entity_paths=[Path("data/entities/optkas_platform.yaml")],
        )
        assert pkg.governance is not None
        assert "committees" in pkg.governance

    def test_cap_structure_integration(self, sample_cap_structure):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Cap Test",
            entity_paths=[Path("data/entities/querubin_usa.yaml")],
            cap_structure_path=sample_cap_structure,
        )
        assert pkg.capital_structure is not None
        assert pkg.fund_flow is not None

    def test_evidence_inventory(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Evidence Test",
            entity_paths=[Path("data/entities/querubin_usa.yaml")],
        )
        assert len(pkg.evidence_inventory) > 0
        entities_with_evidence = {e.entity for e in pkg.evidence_inventory}
        assert "querubin_usa" in entities_with_evidence

    def test_summary_readable(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Summary Test",
            entity_paths=[
                Path("data/entities/querubin_usa.yaml"),
                Path("data/entities/tc_advantage_traders.yaml"),
            ],
        )
        s = pkg.summary()
        assert "COMPLIANCE PACKAGE" in s
        assert "Summary Test" in s
        assert "ENTITIES" in s

    def test_to_dict_serializable(self):
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="Dict Test",
            entity_paths=[Path("data/entities/querubin_usa.yaml")],
        )
        d = pkg.to_dict()
        json_str = json.dumps(d)
        assert "deal_name" in json_str

    def test_save(self, tmp_path):
        import os
        orig = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Create a minimal evidence directory so the generator doesn't fail
            (tmp_path / "data" / "evidence").mkdir(parents=True, exist_ok=True)
            gen = CompliancePackageGenerator()
            pkg = CompliancePackage(
                deal_name="Save Test",
                generated_at="2026-02-12T00:00:00Z",
            )
            path = gen.save(pkg)
            assert path.exists()
        finally:
            os.chdir(orig)

    def test_full_deal_group_package(self):
        """Integration test: full compliance package for the real deal group."""
        gen = CompliancePackageGenerator()
        pkg = gen.generate(
            deal_name="OPTKAS-Querubin-TC Full Deal",
            entity_paths=[
                Path("data/entities/querubin_usa.yaml"),
                Path("data/entities/tc_advantage_traders.yaml"),
                Path("data/entities/optkas_platform.yaml"),
                Path("data/entities/optkas1_spv.yaml"),
            ],
        )
        assert len(pkg.entities) == 4
        assert pkg.governance is not None
        assert len(pkg.evidence_inventory) > 0
        assert pkg.compliance_status in ("CLEAR", "CONDITIONAL", "REQUIRES_ACTION")
        # Should have US and BS jurisdictions at minimum
        codes = {j["code"] for j in pkg.jurisdictions}
        assert "US" in codes
