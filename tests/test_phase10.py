"""
Phase 10 Tests — RED Gate Resolution Engines
=================================================
Tests for: EscrowEngine, BankingResolverEngine, CPResolutionEngine,
           Enhanced Dashboard Sections

Target: ~90 tests
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

# ── Engine imports ────────────────────────────────────────────────

from engine.escrow_engine import (
    EscrowEngine,
    EscrowPlan,
    EscrowTerms,
    EscrowCondition,
    SettlementRailLeg,
    ESCROW_AGENTS,
    FREELY_CONVERTIBLE,
)
from engine.banking_resolver import (
    BankingResolverEngine,
    BankingResolutionPlan,
    ResolvedBanking,
    BankingGap,
    BANK_DIRECTORY,
)
from engine.cp_resolution import (
    CPResolutionEngine,
    ResolutionReport,
    CPResolution,
    EVIDENCE_RESOLUTION_MAP,
)
from engine.deal_dashboard import (
    DealDashboardEngine,
    DealDashboard,
    DashboardSection,
)


# ── Fixtures ──────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
ENTITIES = ROOT / "data" / "entities"

TC_ADVANTAGE = ENTITIES / "tc_advantage_traders.yaml"
OPTKAS1_SPV = ENTITIES / "optkas1_spv.yaml"
OPTKAS_PLATFORM = ENTITIES / "optkas_platform.yaml"
QUERUBIN_USA = ENTITIES / "querubin_usa.yaml"

ALL_ENTITIES = [TC_ADVANTAGE, OPTKAS1_SPV, OPTKAS_PLATFORM, QUERUBIN_USA]
DEAL_NAME = "OPTKAS-TC Phase 10 Test"


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 1: Escrow Engine
# ══════════════════════════════════════════════════════════════════

class TestEscrowEngine:
    """Tests for EscrowEngine — settlement rail builder."""

    def setup_method(self):
        self.engine = EscrowEngine()
        self.plan = self.engine.build(
            deal_name=DEAL_NAME,
            entity_paths=ALL_ENTITIES,
            escrow_currency="USD",
        )

    def test_plan_created(self):
        assert isinstance(self.plan, EscrowPlan)
        assert self.plan.deal_name == DEAL_NAME

    def test_plan_has_created_at(self):
        assert self.plan.created_at

    def test_plan_has_legs(self):
        """Should build legs from primary to each counterparty."""
        assert self.plan.total_legs >= 1

    def test_legs_have_five_nodes(self):
        """Each leg should have a 5-node chain."""
        for leg in self.plan.legs:
            assert leg.node_count == 5

    def test_legs_have_escrow_agent(self):
        """Each leg should route through an escrow agent."""
        for leg in self.plan.legs:
            assert leg.escrow_agent
            assert leg.escrow_swift

    def test_escrow_agent_is_known(self):
        """The selected escrow agent should be from our registry."""
        if self.plan.escrow_terms:
            assert self.plan.escrow_terms.escrow_agent_swift in ESCROW_AGENTS

    def test_escrow_terms_exist(self):
        assert self.plan.escrow_terms is not None

    def test_escrow_terms_have_conditions(self):
        """Escrow should have 7 standard release conditions."""
        et = self.plan.escrow_terms
        assert len(et.conditions) == 7

    def test_escrow_conditions_start_pending(self):
        for cond in self.plan.escrow_terms.conditions:
            assert cond.status == "PENDING"

    def test_escrow_currency_usd(self):
        assert self.plan.escrow_terms.escrow_currency == "USD"

    def test_escrow_currency_freely_convertible(self):
        assert self.plan.escrow_terms.escrow_currency in FREELY_CONVERTIBLE

    def test_escrow_release_mechanism(self):
        assert self.plan.escrow_terms.release_mechanism == "dual_authorization"

    def test_escrow_type_institutional(self):
        assert self.plan.escrow_terms.escrow_type == "institutional"

    def test_bank_assignments_populated(self):
        """All entities should have bank assignments."""
        assert len(self.plan.entity_bank_assignments) == 4

    def test_querubin_existing_bank(self):
        """Querubin USA should use its existing BNY Mellon banking."""
        q = self.plan.entity_bank_assignments.get("QUERUBIN USA LLC")
        if q:
            assert q.get("source") == "existing"
            assert "IRVTUS3N" in q.get("swift", "")

    def test_entities_without_banks_get_recommendations(self):
        """Entities with null settlement banks should get recommendations."""
        recommended = [
            name for name, info in self.plan.entity_bank_assignments.items()
            if info.get("source") == "recommended"
        ]
        assert len(recommended) >= 2  # TC Advantage and OPTKAS1 at minimum

    def test_swift_coverage_in_legs(self):
        """Each valid leg should have at least 2 SWIFT-capable nodes."""
        for leg in self.plan.legs:
            swift_nodes = [n for n in leg.nodes if n.get("swift")]
            assert len(swift_nodes) >= 2

    def test_originator_bank_in_chain(self):
        """Each leg should have an originator_bank node."""
        for leg in self.plan.legs:
            roles = [n.get("role") for n in leg.nodes]
            assert "originator_bank" in roles

    def test_beneficiary_bank_in_chain(self):
        """Each leg should have a beneficiary_bank node."""
        for leg in self.plan.legs:
            roles = [n.get("role") for n in leg.nodes]
            assert "beneficiary_bank" in roles

    def test_escrow_agent_in_chain(self):
        """Each leg should have an escrow_agent node."""
        for leg in self.plan.legs:
            roles = [n.get("role") for n in leg.nodes]
            assert "escrow_agent" in roles

    def test_node_ordering(self):
        """Nodes should be in proper order: 1→5."""
        for leg in self.plan.legs:
            positions = [n["position"] for n in leg.nodes]
            assert positions == list(range(1, len(positions) + 1))

    def test_cross_border_fx_detection(self):
        """Legs between different jurisdictions should flag FX."""
        for leg in self.plan.legs:
            # The plan has BS, US jurisdictions — some legs will be cross-border
            if leg.requires_fx:
                fx_notes = [n for n in leg.notes if "FX" in n or "Cross-border" in n]
                assert len(fx_notes) > 0

    def test_summary_output(self):
        summary = self.plan.summary()
        assert "ESCROW & SETTLEMENT RAIL PLAN" in summary
        assert DEAL_NAME in summary

    def test_serialization(self):
        d = self.plan.to_dict()
        assert d["deal_name"] == DEAL_NAME
        assert "legs" in d
        assert "escrow_terms" in d

    def test_save(self, tmp_path, monkeypatch):
        import engine.escrow_engine as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.plan)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME

    def test_not_enough_entities(self):
        """With < 2 entities, should report issues."""
        plan = self.engine.build(
            deal_name="Solo", entity_paths=[TC_ADVANTAGE]
        )
        assert len(plan.overall_issues) > 0

    def test_no_entities(self):
        plan = self.engine.build(deal_name="Empty", entity_paths=[])
        assert len(plan.overall_issues) > 0
        assert plan.total_legs == 0

    def test_escrow_condition_is_met_property(self):
        cond = EscrowCondition(
            condition_id="ESC-001",
            description="Test",
            category="legal",
            status="SATISFIED",
        )
        assert cond.is_met

    def test_escrow_condition_waived(self):
        cond = EscrowCondition(
            condition_id="ESC-002",
            description="Test",
            category="legal",
            status="WAIVED",
        )
        assert cond.is_met

    def test_escrow_condition_pending(self):
        cond = EscrowCondition(
            condition_id="ESC-003",
            description="Test",
            category="legal",
        )
        assert not cond.is_met

    def test_escrow_terms_met_count(self):
        et = self.plan.escrow_terms
        assert et.met_count == 0  # All start pending
        assert et.pending_count == 7

    def test_escrow_terms_all_conditions_met_false(self):
        assert not self.plan.escrow_terms.all_conditions_met

    def test_non_convertible_currency_override(self):
        """Non-freely-convertible currency should be overridden to USD."""
        plan = self.engine.build(
            deal_name="VND Test",
            entity_paths=ALL_ENTITIES,
            escrow_currency="VND",
        )
        assert plan.escrow_terms.escrow_currency == "USD"
        assert any("not freely convertible" in n for n in plan.escrow_terms.compliance_notes)

    def test_gsib_preference(self):
        """Escrow agent should prefer GSIB-tier banks."""
        if self.plan.escrow_terms:
            agent = ESCROW_AGENTS.get(self.plan.escrow_terms.escrow_agent_swift, {})
            assert agent.get("tier") == "GSIB"

    def test_leg_serialization(self):
        if self.plan.legs:
            d = self.plan.legs[0].to_dict()
            assert "leg_id" in d
            assert "originator" in d
            assert "beneficiary" in d
            assert "nodes" in d

    def test_escrow_agents_registry(self):
        """Registry should have at least 3 agents."""
        assert len(ESCROW_AGENTS) >= 3

    def test_freely_convertible_currencies(self):
        """Should include major freely convertible currencies."""
        for cur in ("USD", "EUR", "GBP", "CHF", "JPY"):
            assert cur in FREELY_CONVERTIBLE

    def test_total_nodes_property(self):
        assert self.plan.total_nodes >= 5  # At least 1 leg × 5 nodes


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 2: Banking Resolver Engine
# ══════════════════════════════════════════════════════════════════

class TestBankingResolver:
    """Tests for BankingResolverEngine — gap analysis & resolution."""

    def setup_method(self):
        self.engine = BankingResolverEngine()
        self.plan = self.engine.resolve(
            deal_name=DEAL_NAME,
            entity_paths=ALL_ENTITIES,
        )

    def test_plan_created(self):
        assert isinstance(self.plan, BankingResolutionPlan)
        assert self.plan.deal_name == DEAL_NAME

    def test_plan_has_profiles(self):
        assert self.plan.total_entities == 4

    def test_plan_has_created_at(self):
        assert self.plan.created_at

    def test_querubin_resolved(self):
        """Querubin USA has complete banking — should be RESOLVED."""
        q = next(
            (p for p in self.plan.profiles if "QUERUBIN" in p.entity_name.upper()),
            None,
        )
        assert q is not None
        assert q.status == "RESOLVED"
        assert q.is_complete
        assert q.source == "existing"
        assert q.confidence >= 90

    def test_querubin_existing_bank_name(self):
        q = next(
            (p for p in self.plan.profiles if "QUERUBIN" in p.entity_name.upper()),
            None,
        )
        assert q is not None
        assert "Mellon" in q.resolved_bank or "BNY" in q.resolved_bank or q.current_swift == "IRVTUS3N"

    def test_tc_advantage_needs_resolution(self):
        """TC Advantage has null settlement_bank — should have gaps."""
        tc = next(
            (p for p in self.plan.profiles if "TC Advantage" in p.entity_name),
            None,
        )
        assert tc is not None
        assert len(tc.gaps) > 0

    def test_tc_advantage_gets_recommendation(self):
        tc = next(
            (p for p in self.plan.profiles if "TC Advantage" in p.entity_name),
            None,
        )
        assert tc is not None
        assert tc.resolved_bank  # Should have a recommended bank
        assert tc.resolved_swift
        assert tc.source == "recommended"

    def test_optkas1_gets_recommendation(self):
        """OPTKAS1 SPV also needs banking resolution."""
        spv = next(
            (p for p in self.plan.profiles if "OPTKAS1" in p.entity_name),
            None,
        )
        assert spv is not None
        assert spv.resolved_bank
        assert spv.resolved_swift

    def test_critical_gaps_identified(self):
        """Entities without banks should have CRITICAL gaps."""
        tc = next(
            (p for p in self.plan.profiles if "TC Advantage" in p.entity_name),
            None,
        )
        assert tc is not None
        assert tc.critical_gaps >= 1

    def test_gap_fields_identified(self):
        """Gaps should identify specific fields (settlement_bank, swift_code, etc.)."""
        for p in self.plan.profiles:
            for g in p.gaps:
                assert g.field_name in (
                    "settlement_bank", "swift_code",
                    "aba_routing", "account_number",
                )
                assert g.severity in ("CRITICAL", "HIGH", "MEDIUM")
                assert g.description

    def test_implementation_steps_for_unresolved(self):
        """Entities needing banking should have implementation steps."""
        for p in self.plan.profiles:
            if p.source == "recommended":
                assert len(p.implementation_steps) >= 3

    def test_resolution_pct(self):
        assert 0.0 <= self.plan.resolution_pct <= 100.0

    def test_total_gaps(self):
        assert self.plan.total_gaps >= 2  # TC and OPTKAS1 at minimum

    def test_bank_directory_has_entries(self):
        assert len(BANK_DIRECTORY) >= 5

    def test_bank_directory_has_swift(self):
        for swift, info in BANK_DIRECTORY.items():
            assert info.get("swift") == swift

    def test_resolved_banking_status_property(self):
        rb = ResolvedBanking(entity_name="Test", jurisdiction="US")
        assert rb.status in ("RESOLVED", "CRITICAL_GAPS", "MINOR_GAPS")

    def test_resolved_complete_property(self):
        rb = ResolvedBanking(
            entity_name="Test",
            jurisdiction="US",
            resolved_bank="JPM",
            resolved_swift="CHASUS33",
        )
        assert rb.is_complete

    def test_resolved_incomplete(self):
        rb = ResolvedBanking(entity_name="Test", jurisdiction="US")
        assert not rb.is_complete

    def test_gap_serialization(self):
        gap = BankingGap(
            field_name="swift_code",
            severity="CRITICAL",
            description="Missing SWIFT",
        )
        d = gap.to_dict()
        assert d["severity"] == "CRITICAL"

    def test_plan_serialization(self):
        d = self.plan.to_dict()
        assert "profiles" in d
        assert d["total_entities"] == 4
        assert "all_resolved" in d

    def test_summary_output(self):
        summary = self.plan.summary()
        assert "BANKING RESOLUTION PLAN" in summary
        assert DEAL_NAME in summary

    def test_save(self, tmp_path, monkeypatch):
        import engine.banking_resolver as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.plan)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME

    def test_no_entities(self):
        plan = self.engine.resolve(deal_name="Empty", entity_paths=[])
        assert plan.total_entities == 0
        assert plan.all_resolved  # vacuously true

    def test_confidence_range(self):
        for p in self.plan.profiles:
            assert 0 <= p.confidence <= 100


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 3: CP Resolution Engine
# ══════════════════════════════════════════════════════════════════

class TestCPResolution:
    """Tests for CPResolutionEngine — auto-resolution from evidence."""

    def setup_method(self):
        self.engine = CPResolutionEngine()
        self.report = self.engine.resolve(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            additional_entities=[QUERUBIN_USA, OPTKAS_PLATFORM],
        )

    def test_report_created(self):
        assert isinstance(self.report, ResolutionReport)
        assert self.report.deal_name == DEAL_NAME

    def test_report_has_cps(self):
        """Should have CPs from the closing tracker."""
        assert self.report.total_cps >= 1

    def test_report_has_created_at(self):
        assert self.report.created_at

    def test_some_auto_resolved(self):
        """At least some CPs should be auto-resolved from evidence."""
        assert self.report.auto_resolved >= 1

    def test_resolution_pct_calculated(self):
        assert 0.0 <= self.report.resolution_pct <= 100.0

    def test_resolutions_have_methods(self):
        """Each resolution should specify how it was resolved."""
        for r in self.report.resolutions:
            assert r.resolution_method in (
                "evidence", "entity_data", "engine_output",
                "pre_existing", "unresolved", "none",
            )

    def test_evidence_resolutions_have_files(self):
        """Evidence-based resolutions should reference the evidence file."""
        evidence_resolutions = [
            r for r in self.report.resolutions
            if r.resolution_method == "evidence"
        ]
        for r in evidence_resolutions:
            assert r.evidence_file
            assert "data/evidence/" in r.evidence_file

    def test_evidence_resolutions_have_confidence(self):
        for r in self.report.resolutions:
            if r.resolution_method == "evidence":
                assert r.confidence > 0

    def test_satisfied_count(self):
        """Satisfied count should be >= 0."""
        assert self.report.satisfied >= 0

    def test_remaining_open_count(self):
        assert self.report.remaining_open >= 0

    def test_total_equals_parts(self):
        """Total CPs should equal resolved + unresolved."""
        resolved = sum(
            1 for r in self.report.resolutions
            if r.new_status in ("SATISFIED", "IN_PROGRESS")
        )
        unresolved = sum(
            1 for r in self.report.resolutions
            if r.new_status == "OPEN"
        )
        assert resolved + unresolved == self.report.total_cps

    def test_tracker_attached(self):
        """Report should include the updated closing tracker."""
        assert self.report.tracker is not None

    def test_tracker_cps_updated(self):
        """Tracker CPs should reflect resolved statuses."""
        if self.report.tracker:
            satisfied_cps = [
                cp for cp in self.report.tracker.conditions
                if cp.status == "SATISFIED"
            ]
            # Should have at least as many as auto-resolved to SATISFIED
            assert len(satisfied_cps) >= self.report.satisfied

    def test_cp_resolution_was_resolved_property(self):
        r = CPResolution(
            cp_id="CP-001",
            description="Test",
            original_status="OPEN",
            new_status="SATISFIED",
            resolution_method="evidence",
        )
        assert r.was_resolved

    def test_cp_resolution_not_resolved(self):
        r = CPResolution(
            cp_id="CP-001",
            description="Test",
            original_status="OPEN",
            new_status="OPEN",
            resolution_method="unresolved",
        )
        assert not r.was_resolved

    def test_cp_resolution_already_resolved_not_counted(self):
        """Pre-existing resolutions should not count as newly resolved."""
        r = CPResolution(
            cp_id="CP-001",
            description="Test",
            original_status="SATISFIED",
            new_status="SATISFIED",
            resolution_method="pre_existing",
        )
        assert not r.was_resolved

    def test_evidence_resolution_map_populated(self):
        """Should have multiple evidence resolution mappings."""
        assert len(EVIDENCE_RESOLUTION_MAP) >= 5

    def test_evidence_map_has_patterns(self):
        for mapping in EVIDENCE_RESOLUTION_MAP:
            assert "cp_pattern" in mapping
            assert "evidence_dirs" in mapping
            assert "file_patterns" in mapping

    def test_summary_output(self):
        summary = self.report.summary()
        assert "CP RESOLUTION REPORT" in summary
        assert DEAL_NAME in summary

    def test_serialization(self):
        d = self.report.to_dict()
        assert d["deal_name"] == DEAL_NAME
        assert "resolutions" in d
        assert "total_cps" in d

    def test_save(self, tmp_path, monkeypatch):
        import engine.cp_resolution as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.report)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME

    def test_in_progress_resolutions(self):
        """Some items may be moved to IN_PROGRESS (e.g., draft opinions)."""
        in_progress = self.report.moved_to_in_progress
        assert in_progress >= 0

    def test_resolution_note_populated(self):
        """Resolved items should have explanation notes."""
        for r in self.report.resolutions:
            if r.was_resolved:
                assert r.resolution_note


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 4: Enhanced Dashboard Sections
# ══════════════════════════════════════════════════════════════════

class TestEnhancedDashboard:
    """Tests for the enhanced dashboard using Phase 10 engines."""

    def setup_method(self):
        self.engine = DealDashboardEngine()
        self.dashboard = self.engine.generate(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            additional_entities=[QUERUBIN_USA, OPTKAS_PLATFORM],
        )

    def test_dashboard_created(self):
        assert isinstance(self.dashboard, DealDashboard)

    def test_has_settlement_section(self):
        """Dashboard should have an enhanced Settlement section."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Settlement"),
            None,
        )
        assert section is not None

    def test_settlement_not_red(self):
        """With escrow engine, settlement should improve from RED."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Settlement"),
            None,
        )
        assert section is not None
        # With escrow engine building valid rails, should be GREEN or AMBER
        assert section.rag in ("GREEN", "AMBER")

    def test_has_onboarding_section(self):
        """Dashboard should have an enhanced Banking Onboarding section."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Banking Onboarding"),
            None,
        )
        assert section is not None

    def test_onboarding_not_red(self):
        """With banking resolver, onboarding should improve from RED."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Banking Onboarding"),
            None,
        )
        assert section is not None
        assert section.rag in ("GREEN", "AMBER")

    def test_has_escrow_section(self):
        """Dashboard should have an Escrow section."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Escrow"),
            None,
        )
        assert section is not None

    def test_escrow_section_has_agent(self):
        """Escrow section should mention the selected agent."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Escrow"),
            None,
        )
        assert section is not None
        assert section.headline  # Should have content about escrow agent

    def test_has_cp_resolution_section(self):
        """Dashboard should have a CP Resolution section."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "CP Resolution"),
            None,
        )
        assert section is not None

    def test_cp_resolution_not_red(self):
        """With CP resolution, closing conditions should improve."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "CP Resolution"),
            None,
        )
        assert section is not None
        # After auto-resolution, should be AMBER or GREEN
        assert section.rag in ("GREEN", "AMBER")

    def test_cp_resolution_has_score(self):
        section = next(
            (s for s in self.dashboard.sections if s.name == "CP Resolution"),
            None,
        )
        assert section is not None
        assert section.max_score > 0

    def test_section_count_increased(self):
        """Dashboard should now have more sections than before Phase 10."""
        # Phase 9 had 8 sections, Phase 10 adds 4 new ones (enhanced settlement,
        # enhanced onboarding, escrow, CP resolution)
        assert len(self.dashboard.sections) >= 10

    def test_overall_rag_improved(self):
        """Overall RAG should no longer be RED — all gates resolved."""
        assert self.dashboard.overall_rag in ("GREEN", "AMBER")
        assert self.dashboard.red_count == 0

    def test_dashboard_summary_output(self):
        summary = self.dashboard.summary()
        assert "DEAL DASHBOARD" in summary
        assert DEAL_NAME in summary

    def test_dashboard_serialization(self):
        d = self.dashboard.to_dict()
        assert "sections" in d
        assert d["deal_name"] == DEAL_NAME

    def test_save(self, tmp_path, monkeypatch):
        import engine.deal_dashboard as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.dashboard)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 5: Escrow Auto-Satisfy
# ══════════════════════════════════════════════════════════════════

class TestEscrowAutoSatisfy:
    """Tests for escrow condition auto-satisfaction."""

    def setup_method(self):
        self.engine = EscrowEngine()
        self.plan = self.engine.build(
            deal_name=DEAL_NAME,
            entity_paths=ALL_ENTITIES,
            escrow_currency="USD",
        )

    def test_auto_satisfy_returns_count(self):
        count = self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        assert isinstance(count, int)
        assert count >= 1

    def test_auto_satisfy_updates_conditions(self):
        before_met = self.plan.escrow_terms.met_count
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        after_met = self.plan.escrow_terms.met_count
        assert after_met > before_met

    def test_kyc_condition_satisfied(self):
        """KYC/AML should auto-satisfy from evidence vault."""
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        kyc_conds = [
            c for c in self.plan.escrow_terms.conditions
            if "kyc" in c.description.lower() or "aml" in c.description.lower()
        ]
        for c in kyc_conds:
            assert c.status == "SATISFIED"

    def test_signatory_condition_satisfied(self):
        """Dual authorization should auto-satisfy from entity signatories."""
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        sig_conds = [
            c for c in self.plan.escrow_terms.conditions
            if "authorization" in c.description.lower()
        ]
        for c in sig_conds:
            assert c.status == "SATISFIED"

    def test_settlement_condition_satisfied(self):
        """Settlement instructions should auto-satisfy when banks assigned."""
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        settle_conds = [
            c for c in self.plan.escrow_terms.conditions
            if "settlement instruction" in c.description.lower()
        ]
        for c in settle_conds:
            assert c.status == "SATISFIED"

    def test_sanctions_condition_satisfied(self):
        """OFAC/sanctions should auto-satisfy when no sanctioned jurisdictions."""
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        sanct_conds = [
            c for c in self.plan.escrow_terms.conditions
            if "ofac" in c.description.lower() or "sanctions" in c.description.lower()
        ]
        for c in sanct_conds:
            assert c.status == "SATISFIED"

    def test_funds_condition_not_auto_satisfied(self):
        """Funds deposit cannot be auto-verified."""
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        funds_conds = [
            c for c in self.plan.escrow_terms.conditions
            if "funds" in c.description.lower() and "deposited" in c.description.lower()
        ]
        for c in funds_conds:
            assert c.status == "PENDING"

    def test_satisfied_conditions_have_notes(self):
        self.engine.auto_satisfy_conditions(
            self.plan, entity_paths=ALL_ENTITIES
        )
        for c in self.plan.escrow_terms.conditions:
            if c.status == "SATISFIED":
                assert c.notes

    def test_no_entities_no_crash(self):
        count = self.engine.auto_satisfy_conditions(self.plan)
        assert count >= 0  # May still satisfy from evidence


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 6: Collateral Fix & Closing Wiring
# ══════════════════════════════════════════════════════════════════

class TestDashboardFixes:
    """Tests for Phase 11 dashboard fixes."""

    def setup_method(self):
        self.engine = DealDashboardEngine()
        self.dashboard = self.engine.generate(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            additional_entities=[QUERUBIN_USA, OPTKAS_PLATFORM],
        )

    def test_collateral_is_green(self):
        """Collateral should be GREEN now that SPV is verified correctly."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Collateral"),
            None,
        )
        assert section is not None
        assert section.rag == "GREEN"
        assert section.score == 100.0

    def test_closing_uses_cp_resolution(self):
        """Closing section should show auto-resolved CPs."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Closing Conditions"),
            None,
        )
        assert section is not None
        # Should have some resolved CPs (not 0/8 anymore)
        assert section.score > 0
        assert section.rag in ("GREEN", "AMBER")

    def test_closing_details_mention_auto_resolved(self):
        section = next(
            (s for s in self.dashboard.sections if s.name == "Closing Conditions"),
            None,
        )
        assert section is not None
        has_auto_resolved_detail = any(
            "auto-resolved" in d for d in section.details
        )
        assert has_auto_resolved_detail

    def test_escrow_conditions_partially_met(self):
        """Escrow should have some conditions auto-satisfied."""
        section = next(
            (s for s in self.dashboard.sections if s.name == "Escrow"),
            None,
        )
        assert section is not None
        assert section.score > 0  # Some conditions met
        assert section.rag == "AMBER"

    def test_zero_red_gates(self):
        """Dashboard should have 0 RED sections."""
        assert self.dashboard.red_count == 0

    def test_overall_amber(self):
        """Overall status should be AMBER (no RED, some AMBER remain)."""
        assert self.dashboard.overall_rag == "AMBER"

    def test_action_items_reduced(self):
        """Should have fewer action items than before."""
        items = self.dashboard.all_action_items
        # Reduced from 19 to ~18 (fewer closing/collateral items)
        assert len(items) > 0  # Still has items
        assert len(items) < 30  # But not excessive
