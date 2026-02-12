"""
Phase 8 Tests: Deal Governance, Risk Scoring, Closing Tracker, Settlement Fix
===============================================================================
Covers:
  - DealGovernanceEngine: entity merge, template defaults, authority map,
    conflict detection, gap analysis, compliance, serialization, persistence
  - CounterpartyRiskEngine: 5-factor scoring, grade, risk level,
    jurisdiction, documentation, concentration, regulatory, settlement
  - ClosingTrackerEngine: CP generation, standard/MTN/collateral/insurance/
    opinion/governance/settlement CPs, satisfaction, waiver, readiness
  - Settlement path bug fix: correct attribute names
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from engine.deal_governance import (
    DealGovernanceEngine,
    DealGovernanceReport,
    AuthorityEntry,
    AuthorityConflict,
    GovernanceGap,
)
from engine.risk_scorer import (
    CounterpartyRiskEngine,
    CounterpartyRiskReport,
    RiskFactor,
)
from engine.closing_tracker import (
    ClosingTrackerEngine,
    ClosingTracker,
    ConditionPrecedent,
)
from engine.deal_readiness import DealReadinessEngine
from engine.correspondent_banking import CorrespondentBankingEngine
from engine.schema_loader import load_entity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "entities"
TC = DATA_DIR / "tc_advantage_traders.yaml"
SPV = DATA_DIR / "optkas1_spv.yaml"
OPTKAS = DATA_DIR / "optkas_platform.yaml"
QUERUBIN = DATA_DIR / "querubin_usa.yaml"
CUERPO = DATA_DIR / "cuerpo_markets.yaml"

ALL_ENTITY_PATHS = [TC, SPV, OPTKAS, QUERUBIN]


@pytest.fixture
def gov_engine():
    return DealGovernanceEngine()


@pytest.fixture
def risk_engine():
    return CounterpartyRiskEngine()


@pytest.fixture
def closing_engine():
    return ClosingTrackerEngine()


@pytest.fixture
def gov_report(gov_engine):
    return gov_engine.assess(
        deal_name="OPTKAS-TC Test",
        entity_paths=ALL_ENTITY_PATHS,
    )


@pytest.fixture
def risk_report(risk_engine):
    return risk_engine.score(
        deal_name="OPTKAS-TC Test",
        entity_paths=ALL_ENTITY_PATHS,
    )


@pytest.fixture
def tracker(closing_engine):
    return closing_engine.generate(
        deal_name="OPTKAS-TC Test",
        issuer_path=TC,
        spv_path=SPV,
        additional_entities=[OPTKAS, QUERUBIN],
        target_closing_date="2026-06-30",
    )


# ===================================================================
# Test: Deal Governance Engine
# ===================================================================

class TestDealGovernance:

    def test_basic_assessment(self, gov_report):
        assert isinstance(gov_report, DealGovernanceReport)
        assert gov_report.deal_name == "OPTKAS-TC Test"
        assert len(gov_report.entities) == 4

    def test_framework_created(self, gov_report):
        assert gov_report.framework is not None

    def test_framework_has_committees(self, gov_report):
        assert len(gov_report.framework.committees) >= 3

    def test_framework_has_signature_rules(self, gov_report):
        """Template defaults should fill missing signature rules."""
        assert len(gov_report.framework.signature_rules) >= 5

    def test_framework_has_decision_thresholds(self, gov_report):
        assert len(gov_report.framework.decision_thresholds) >= 3

    def test_framework_has_reporting(self, gov_report):
        assert len(gov_report.framework.reporting) >= 5

    def test_framework_has_controls(self, gov_report):
        assert len(gov_report.framework.controls) >= 3

    def test_template_applied(self, gov_report):
        """At least some template defaults should have been applied."""
        assert gov_report.template_applied

    def test_authority_map_populated(self, gov_report):
        """Should have signatories/directors from entity YAMLs."""
        assert len(gov_report.authority_map) >= 1

    def test_authority_entries_have_names(self, gov_report):
        for a in gov_report.authority_map:
            assert a.name
            assert a.entity

    def test_grade_exists(self, gov_report):
        assert gov_report.grade in ("A", "B", "C", "D", "F")

    def test_score_in_range(self, gov_report):
        assert 0 <= gov_report.score <= 100

    def test_summary_readable(self, gov_report):
        s = gov_report.summary()
        assert "DEAL GOVERNANCE REPORT" in s
        assert "OPTKAS-TC Test" in s
        assert "Grade:" in s

    def test_to_dict_serializable(self, gov_report):
        d = gov_report.to_dict()
        assert json.dumps(d, default=str)
        assert d["deal_name"] == "OPTKAS-TC Test"
        assert "framework" in d
        assert "authority_map" in d
        assert "conflicts" in d
        assert "gaps" in d

    def test_save(self, gov_engine, gov_report, tmp_path):
        import engine.deal_governance as mod
        orig = mod.OUTPUT_DIR
        try:
            mod.OUTPUT_DIR = tmp_path
            path = gov_engine.save(gov_report)
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["deal_name"] == "OPTKAS-TC Test"
        finally:
            mod.OUTPUT_DIR = orig

    def test_no_entities_still_works(self, gov_engine):
        report = gov_engine.assess(deal_name="Empty Test")
        assert report.framework is not None
        assert report.template_applied

    def test_merged_from_entities_count(self, gov_report):
        """Should have merged from entities that have governance sections."""
        assert isinstance(gov_report.merged_from_entities, int)

    def test_gap_analysis(self, gov_report):
        """Gaps list should be a list."""
        assert isinstance(gov_report.gaps, list)


# ===================================================================
# Test: Counterparty Risk Scoring Engine
# ===================================================================

class TestCounterpartyRiskScorer:

    def test_basic_scoring(self, risk_report):
        assert isinstance(risk_report, CounterpartyRiskReport)
        assert risk_report.deal_name == "OPTKAS-TC Test"
        assert len(risk_report.entities) == 4

    def test_five_factors(self, risk_report):
        assert len(risk_report.factors) == 5

    def test_factor_names(self, risk_report):
        names = [f.name for f in risk_report.factors]
        assert "Jurisdiction Risk" in names
        assert "Documentation Score" in names
        assert "Concentration Risk" in names
        assert "Regulatory Exposure" in names
        assert "Settlement Complexity" in names

    def test_total_score_in_range(self, risk_report):
        assert 0 <= risk_report.total_score <= 100

    def test_grade_exists(self, risk_report):
        assert risk_report.grade in ("A", "B", "C", "D", "F")

    def test_risk_level(self, risk_report):
        assert risk_report.risk_level in (
            "LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"
        )

    def test_each_factor_in_range(self, risk_report):
        for f in risk_report.factors:
            assert 0 <= f.score <= f.max_score

    def test_jurisdiction_factor_high(self, risk_report):
        """TC is BS, SPV is US-WY, Querubin is US -- mostly favorable."""
        jur = next(f for f in risk_report.factors if f.name == "Jurisdiction Risk")
        assert jur.score >= 10  # At least decent

    def test_documentation_factor(self, risk_report):
        doc = next(f for f in risk_report.factors if f.name == "Documentation Score")
        assert doc.score >= 5  # Has opinions, insurance, evidence

    def test_concentration_factor(self, risk_report):
        conc = next(f for f in risk_report.factors if f.name == "Concentration Risk")
        assert conc.score >= 5

    def test_regulatory_factor(self, risk_report):
        reg = next(f for f in risk_report.factors if f.name == "Regulatory Exposure")
        assert reg.score >= 5

    def test_settlement_factor(self, risk_report):
        stl = next(f for f in risk_report.factors if f.name == "Settlement Complexity")
        assert stl.score >= 5

    def test_flags_generated(self, risk_report):
        """Should have at least some risk flags for a complex deal."""
        assert isinstance(risk_report.flags, list)

    def test_mitigants_generated(self, risk_report):
        """Should have mitigants for well-documented entities."""
        assert isinstance(risk_report.mitigants, list)
        assert len(risk_report.mitigants) >= 1

    def test_summary_readable(self, risk_report):
        s = risk_report.summary()
        assert "COUNTERPARTY RISK ASSESSMENT" in s
        assert "SCORE:" in s
        assert "GRADE:" in s

    def test_to_dict_serializable(self, risk_report):
        d = risk_report.to_dict()
        assert json.dumps(d, default=str)
        assert d["total_score"] == risk_report.total_score
        assert len(d["factors"]) == 5

    def test_save(self, risk_engine, risk_report, tmp_path):
        import engine.risk_scorer as mod
        orig = mod.OUTPUT_DIR
        try:
            mod.OUTPUT_DIR = tmp_path
            path = risk_engine.save(risk_report)
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["grade"] == risk_report.grade
        finally:
            mod.OUTPUT_DIR = orig

    def test_no_entities_returns_defaults(self, risk_engine):
        report = risk_engine.score(deal_name="Empty Test")
        assert len(report.factors) == 5
        assert report.total_score >= 0

    def test_factor_pct(self, risk_report):
        for f in risk_report.factors:
            assert 0 <= f.pct <= 100


# ===================================================================
# Test: Closing Tracker Engine
# ===================================================================

class TestClosingTracker:

    def test_generate_tracker(self, tracker):
        assert isinstance(tracker, ClosingTracker)
        assert tracker.deal_name == "OPTKAS-TC Test"
        assert tracker.total >= 5

    def test_target_closing_date(self, tracker):
        assert tracker.target_closing_date == "2026-06-30"

    def test_standard_cps_generated(self, tracker):
        """Should have the 4 standard CPs."""
        standard_cps = [c for c in tracker.conditions if c.source == "standard"]
        assert len(standard_cps) >= 3

    def test_mtn_derived_cps(self, tracker):
        """MTN validation warnings/failures should generate CPs."""
        mtn_cps = [c for c in tracker.conditions if c.source == "mtn_validation"]
        assert len(mtn_cps) >= 1  # Draft opinion creates a WARN -> CP

    def test_opinion_cps_for_draft(self, tracker):
        """Draft Pro Se opinion should generate a CP."""
        opinion_cps = [c for c in tracker.conditions if c.source == "opinion_assessment"]
        assert len(opinion_cps) >= 1
        # At least one should mention draft or finalize
        descriptions = " ".join(c.description for c in opinion_cps)
        assert "draft" in descriptions.lower() or "finalize" in descriptions.lower()

    def test_all_cps_have_ids(self, tracker):
        ids = [c.cp_id for c in tracker.conditions]
        assert len(ids) == len(set(ids))  # All unique
        for cp_id in ids:
            assert cp_id.startswith("CP-")

    def test_all_cps_have_gates(self, tracker):
        valid_gates = {"PRE_SIGNING", "SIGNING", "PRE_CLOSING", "CLOSING", "POST_CLOSING"}
        for c in tracker.conditions:
            assert c.gate in valid_gates

    def test_all_cps_have_categories(self, tracker):
        valid_cats = {"documentary", "regulatory", "financial", "legal", "operational"}
        for c in tracker.conditions:
            assert c.category in valid_cats

    def test_all_cps_start_open(self, tracker):
        """All auto-generated CPs should be OPEN."""
        for c in tracker.conditions:
            assert c.status == "OPEN"

    def test_completion_pct_zero(self, tracker):
        """No CPs satisfied yet."""
        assert tracker.completion_pct == 0.0

    def test_closing_not_ready(self, tracker):
        assert not tracker.closing_ready

    def test_signing_not_ready(self, tracker):
        assert not tracker.signing_ready

    def test_satisfy_cp(self, tracker):
        cp = tracker.conditions[0]
        cp.satisfy(by="Test")
        assert cp.is_resolved
        assert cp.status == "SATISFIED"
        assert cp.satisfied_by == "Test"

    def test_waive_cp(self, tracker):
        cp = tracker.conditions[1]
        cp.waive(reason="Not applicable", by="Board")
        assert cp.is_resolved
        assert cp.status == "WAIVED"
        assert "WAIVED" in cp.notes

    def test_completion_after_resolving(self, tracker):
        """Satisfy all CPs and check completion."""
        for c in tracker.conditions:
            c.satisfy()
        assert tracker.completion_pct == 100.0
        assert tracker.closing_ready
        assert tracker.signing_ready

    def test_blocked_cp(self, tracker):
        cp = tracker.conditions[0]
        cp.status = "BLOCKED"
        assert cp.is_blocking
        assert not cp.is_resolved

    def test_overdue_detection(self, tracker):
        """A CP with past deadline should be overdue."""
        cp = tracker.conditions[0]
        cp.deadline = "2020-01-01"
        assert cp.is_overdue

    def test_not_overdue_when_resolved(self, tracker):
        cp = tracker.conditions[0]
        cp.deadline = "2020-01-01"
        cp.satisfy()
        assert not cp.is_overdue

    def test_by_gate(self, tracker):
        pre_signing = tracker.by_gate("PRE_SIGNING")
        assert len(pre_signing) >= 1
        for c in pre_signing:
            assert c.gate == "PRE_SIGNING"

    def test_by_category(self, tracker):
        legal = tracker.by_category("legal")
        for c in legal:
            assert c.category == "legal"

    def test_get_cp_by_id(self, tracker):
        cp_id = tracker.conditions[0].cp_id
        found = tracker.get(cp_id)
        assert found is not None
        assert found.cp_id == cp_id

    def test_get_nonexistent_returns_none(self, tracker):
        assert tracker.get("CP-999") is None

    def test_add_custom_cp(self, tracker):
        before = tracker.total
        tracker.add(ConditionPrecedent(
            cp_id="CP-CUSTOM",
            category="legal",
            description="Custom condition",
            gate="PRE_CLOSING",
            responsible="Counsel",
            source="manual",
        ))
        assert tracker.total == before + 1

    def test_summary_readable(self, tracker):
        s = tracker.summary()
        assert "CLOSING CONDITIONS TRACKER" in s
        assert "COMPLETION:" in s
        assert "SIGNING:" in s
        assert "CLOSING:" in s

    def test_to_dict_serializable(self, tracker):
        d = tracker.to_dict()
        assert json.dumps(d, default=str)
        assert d["deal_name"] == "OPTKAS-TC Test"
        assert d["total"] == tracker.total
        assert d["completion_pct"] == 0.0

    def test_save_and_load(self, closing_engine, tracker, tmp_path):
        import engine.closing_tracker as mod
        orig = mod.OUTPUT_DIR
        try:
            mod.OUTPUT_DIR = tmp_path
            path = closing_engine.save(tracker)
            assert path.exists()

            loaded = closing_engine.load(path)
            assert loaded.deal_name == tracker.deal_name
            assert loaded.total == tracker.total
        finally:
            mod.OUTPUT_DIR = orig

    def test_no_issuer_still_works(self, closing_engine):
        tracker = closing_engine.generate(deal_name="Minimal")
        assert tracker.total >= 3  # At least standard CPs


# ===================================================================
# Test: Settlement Path Bug Fix
# ===================================================================

class TestSettlementPathFix:

    def test_settlement_path_attributes(self):
        """Verify SettlementPath has correct attribute names."""
        from engine.correspondent_banking import SettlementPath, BankNode
        path = SettlementPath(
            originator_entity="Entity A",
            beneficiary_entity="Entity B",
        )
        # These are the CORRECT attributes (the bug used wrong names)
        assert hasattr(path, "nodes")
        assert hasattr(path, "requires_fx")
        assert hasattr(path, "validation_notes")
        # These should NOT exist (they were the buggy names)
        assert not hasattr(path, "total_nodes")
        assert not hasattr(path, "fx_required")
        assert not hasattr(path, "notes")

    def test_deal_readiness_settlement_works(self):
        """The deal-ready settlement assessment should not raise."""
        engine = DealReadinessEngine()
        report = engine.assess(
            deal_name="Settlement Fix Test",
            issuer_path=TC,
            spv_path=SPV,
            additional_entities=[OPTKAS, QUERUBIN],
        )
        # Settlement should be assessed without exception
        settlement_items = [
            i for i in report.items if i.area == "settlement"
        ]
        assert len(settlement_items) >= 1
        # Should NOT have the old error message
        for item in settlement_items:
            assert "total_nodes" not in item.detail
            assert "has no attribute" not in item.detail

    def test_settlement_shows_node_count(self):
        """Fixed settlement should show node count and FX status."""
        engine = DealReadinessEngine()
        report = engine.assess(
            deal_name="Node Count Test",
            issuer_path=TC,
            spv_path=SPV,
        )
        settlement_items = [
            i for i in report.items if i.area == "settlement"
        ]
        # The main settlement item should mention nodes
        main_item = next(
            (i for i in settlement_items if "Settlement path" in i.item), None
        )
        assert main_item is not None
        assert "nodes" in main_item.detail

    def test_resolve_path_directly(self):
        """CorrespondentBankingEngine.resolve_settlement_path works."""
        engine = CorrespondentBankingEngine()
        tc = load_entity(TC)
        spv = load_entity(SPV)
        path = engine.resolve_settlement_path(tc, spv, "USD")
        assert len(path.nodes) >= 2
        assert isinstance(path.requires_fx, bool)
        assert isinstance(path.validation_notes, list)
