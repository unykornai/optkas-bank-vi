"""
Phase 9 Tests — Deal Execution Infrastructure
=================================================
Tests for: SettlementOnboardingEngine, WireInstructionEngine,
           SigningCeremonyEngine, DealDashboardEngine

Target: ~80 tests
"""

import json
import pytest
from pathlib import Path
from datetime import date, datetime

# ── Engine imports ────────────────────────────────────────────────

from engine.settlement_onboarding import (
    SettlementOnboardingEngine,
    OnboardingPlan,
    EntityOnboardingProfile,
    OnboardingStep,
    CandidateBank,
)
from engine.wire_instructions import (
    WireInstructionEngine,
    WireInstructionPackage,
    WireInstruction,
    WireParty,
    ComplianceNote,
)
from engine.signing_ceremony import (
    SigningCeremonyEngine,
    SigningCeremony,
    SigningBlock,
    AuthorityValidation,
    DOCUMENT_CATEGORIES,
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
DEAL_NAME = "OPTKAS-TC Phase 9 Test"


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 1: Settlement Onboarding
# ══════════════════════════════════════════════════════════════════

class TestSettlementOnboarding:
    """Tests for SettlementOnboardingEngine."""

    def setup_method(self):
        self.engine = SettlementOnboardingEngine()
        self.plan = self.engine.assess(
            deal_name=DEAL_NAME,
            entity_paths=ALL_ENTITIES,
        )

    def test_plan_created(self):
        assert isinstance(self.plan, OnboardingPlan)
        assert self.plan.deal_name == DEAL_NAME

    def test_plan_has_profiles(self):
        assert self.plan.total_entities == 4

    def test_plan_has_created_at(self):
        assert self.plan.created_at

    def test_profiles_have_entity_names(self):
        names = [p.entity_name for p in self.plan.profiles]
        assert all(n != "Unknown" for n in names)

    def test_tc_advantage_needs_onboarding(self):
        """TC Advantage has settlement_bank: null."""
        tc = next(
            (p for p in self.plan.profiles if "TC Advantage" in p.entity_name), None,
        )
        assert tc is not None
        assert tc.status in ("NEEDS_ONBOARDING", "PARTIAL")

    def test_optkas1_needs_onboarding(self):
        """OPTKAS1 SPV has settlement_bank: null."""
        spv = next(
            (p for p in self.plan.profiles if "OPTKAS1" in p.entity_name), None,
        )
        assert spv is not None
        assert spv.status in ("NEEDS_ONBOARDING", "PARTIAL")

    def test_needs_onboarding_count(self):
        """At least 2 entities need onboarding (TC and OPTKAS1)."""
        assert self.plan.needs_onboarding >= 2

    def test_settlement_not_ready(self):
        """Settlement should NOT be ready until banks are assigned."""
        assert not self.plan.settlement_ready

    def test_missing_items_detected(self):
        """Profiles needing onboarding should list missing items."""
        for p in self.plan.profiles:
            if p.status == "NEEDS_ONBOARDING":
                assert len(p.missing) > 0
                assert "settlement_bank" in p.missing

    def test_candidate_banks_recommended(self):
        """Entities needing onboarding should have candidate banks."""
        for p in self.plan.profiles:
            if p.status == "NEEDS_ONBOARDING":
                assert len(p.candidates) > 0

    def test_candidate_has_swift(self):
        """Each candidate bank should have a SWIFT code."""
        for p in self.plan.profiles:
            for c in p.candidates:
                assert c.swift_code

    def test_candidate_has_fit_score(self):
        """Each candidate should have a fit score > 0."""
        for p in self.plan.profiles:
            for c in p.candidates:
                assert c.fit_score > 0

    def test_onboarding_steps_generated(self):
        """Entities needing onboarding should have steps."""
        for p in self.plan.profiles:
            if p.status == "NEEDS_ONBOARDING":
                assert len(p.steps) >= 3

    def test_steps_have_actions(self):
        """Each step should have an action description."""
        for p in self.plan.profiles:
            for s in p.steps:
                assert s.action

    def test_steps_start_pending(self):
        """All steps should start as PENDING."""
        for p in self.plan.profiles:
            for s in p.steps:
                assert s.status == "PENDING"

    def test_summary_output(self):
        summary = self.plan.summary()
        assert "SETTLEMENT ONBOARDING PLAN" in summary
        assert DEAL_NAME in summary

    def test_serialization(self):
        d = self.plan.to_dict()
        assert d["deal_name"] == DEAL_NAME
        assert "profiles" in d
        assert len(d["profiles"]) == 4

    def test_save(self, tmp_path, monkeypatch):
        import engine.settlement_onboarding as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.plan)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME

    def test_no_entities(self):
        plan = self.engine.assess(deal_name="Empty", entity_paths=[])
        assert plan.total_entities == 0
        assert plan.settlement_ready  # vacuously true

    def test_total_steps(self):
        assert self.plan.total_steps > 0


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 2: Wire Instructions
# ══════════════════════════════════════════════════════════════════

class TestWireInstructions:
    """Tests for WireInstructionEngine."""

    def setup_method(self):
        self.engine = WireInstructionEngine()
        self.pkg = self.engine.generate(
            deal_name=DEAL_NAME,
            originator_path=TC_ADVANTAGE,
            beneficiary_path=OPTKAS1_SPV,
            amount=10_000_000,
            currency="USD",
            purpose="MTN subscription payment",
        )

    def test_package_created(self):
        assert isinstance(self.pkg, WireInstructionPackage)
        assert self.pkg.deal_name == DEAL_NAME

    def test_has_instruction(self):
        assert self.pkg.total == 1

    def test_instruction_id(self):
        wi = self.pkg.instructions[0]
        assert wi.instruction_id.startswith("WIRE-")

    def test_originator_details(self):
        wi = self.pkg.instructions[0]
        assert "TC Advantage" in wi.originator.entity_name

    def test_beneficiary_details(self):
        wi = self.pkg.instructions[0]
        assert "OPTKAS1" in wi.beneficiary.entity_name

    def test_amount(self):
        wi = self.pkg.instructions[0]
        assert wi.amount == 10_000_000

    def test_currency(self):
        wi = self.pkg.instructions[0]
        assert wi.currency == "USD"

    def test_purpose(self):
        wi = self.pkg.instructions[0]
        assert wi.purpose == "MTN subscription payment"

    def test_status_draft(self):
        wi = self.pkg.instructions[0]
        assert wi.status == "DRAFT"

    def test_compliance_notes_exist(self):
        """Should have warnings about missing banks (settlement_bank: null)."""
        wi = self.pkg.instructions[0]
        assert len(wi.compliance_notes) > 0

    def test_missing_bank_warning(self):
        """Should warn about missing settlement bank."""
        wi = self.pkg.instructions[0]
        warnings = [n for n in wi.compliance_notes if n.severity == "WARNING"]
        assert len(warnings) > 0

    def test_no_sanctions_block(self):
        """BS and US-WY are not sanctioned — no blocks."""
        wi = self.pkg.instructions[0]
        blocks = [n for n in wi.compliance_notes if n.severity == "BLOCK"]
        assert len(blocks) == 0

    def test_not_blocked(self):
        wi = self.pkg.instructions[0]
        assert not wi.is_blocked

    def test_has_warnings(self):
        wi = self.pkg.instructions[0]
        assert wi.has_warnings

    def test_formatted_output(self):
        wi = self.pkg.instructions[0]
        text = wi.formatted()
        assert "WIRE TRANSFER INSTRUCTION" in text
        assert "ORIGINATOR" in text
        assert "BENEFICIARY" in text

    def test_package_summary(self):
        summary = self.pkg.summary()
        assert "WIRE INSTRUCTION PACKAGE" in summary

    def test_serialization(self):
        d = self.pkg.to_dict()
        assert d["deal_name"] == DEAL_NAME
        assert len(d["instructions"]) == 1

    def test_save(self, tmp_path, monkeypatch):
        import engine.wire_instructions as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pkg)
        assert path.exists()

    def test_no_paths(self):
        pkg = self.engine.generate(deal_name="Empty")
        assert pkg.total == 0

    def test_fx_detection(self):
        """TC Advantage (BS) to OPTKAS1 (US-WY) should detect FX requirement."""
        wi = self.pkg.instructions[0]
        assert wi.fx_required  # BS to US is cross-border

    def test_reference_generated(self):
        wi = self.pkg.instructions[0]
        assert wi.reference


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 3: Signing Ceremony
# ══════════════════════════════════════════════════════════════════

class TestSigningCeremony:
    """Tests for SigningCeremonyEngine."""

    def setup_method(self):
        self.engine = SigningCeremonyEngine()
        self.ceremony = self.engine.prepare(
            deal_name=DEAL_NAME,
            entity_paths=ALL_ENTITIES,
        )

    def test_ceremony_created(self):
        assert isinstance(self.ceremony, SigningCeremony)
        assert self.ceremony.deal_name == DEAL_NAME

    def test_has_entities(self):
        assert len(self.ceremony.entities) == 4

    def test_has_blocks(self):
        assert self.ceremony.total_blocks > 0

    def test_blocks_have_ids(self):
        for b in self.ceremony.blocks:
            assert b.block_id.startswith("SIG-")

    def test_blocks_have_document_names(self):
        for b in self.ceremony.blocks:
            assert b.document_name

    def test_blocks_have_entity_names(self):
        for b in self.ceremony.blocks:
            assert b.entity_name

    def test_blocks_start_pending(self):
        for b in self.ceremony.blocks:
            assert b.status == "PENDING"

    def test_not_complete(self):
        assert not self.ceremony.is_complete

    def test_completion_zero(self):
        assert self.ceremony.completion_pct == 0.0

    def test_authority_validations_exist(self):
        assert len(self.ceremony.authority_validations) > 0

    def test_authority_validation_has_entity(self):
        for v in self.ceremony.authority_validations:
            assert v.entity_name

    def test_default_documents_detected(self):
        """Should auto-detect documents from deal structure."""
        doc_types = set(b.document_type for b in self.ceremony.blocks)
        # Should have board_resolution at minimum
        assert "board_resolution" in doc_types

    def test_mtn_triggers_subscription(self):
        """MTN program should trigger subscription_agreement."""
        doc_types = set(b.document_type for b in self.ceremony.blocks)
        assert "subscription_agreement" in doc_types

    def test_spv_triggers_security_agreement(self):
        """SPV entity should trigger security_agreement."""
        doc_types = set(b.document_type for b in self.ceremony.blocks)
        assert "security_agreement" in doc_types

    def test_signing_a_block(self):
        block = self.ceremony.blocks[0]
        block.sign(signer="Test Signer", witness="Test Witness")
        assert block.status == "SIGNED"
        assert block.signed_at
        assert block.signer_name == "Test Signer"

    def test_countersigning_a_block(self):
        block = self.ceremony.blocks[0]
        block.sign(signer="Signer 1")
        block.countersign(signer="Signer 2")
        assert block.status == "COUNTERSIGNED"
        assert block.countersigned_at

    def test_is_executed_after_sign(self):
        block = SigningBlock(
            block_id="TEST-001",
            document_type="test",
            document_name="Test Doc",
            entity_name="Test Entity",
            requires_dual_sig=False,
        )
        block.sign()
        assert block.is_executed

    def test_dual_sig_not_executed_after_single_sign(self):
        block = SigningBlock(
            block_id="TEST-002",
            document_type="test",
            document_name="Test Doc",
            entity_name="Test Entity",
            requires_dual_sig=True,
        )
        block.sign()
        assert not block.is_executed  # Needs countersign

    def test_dual_sig_executed_after_countersign(self):
        block = SigningBlock(
            block_id="TEST-003",
            document_type="test",
            document_name="Test Doc",
            entity_name="Test Entity",
            requires_dual_sig=True,
        )
        block.sign()
        block.countersign()
        assert block.is_executed

    def test_completion_after_signing_all(self):
        for b in self.ceremony.blocks:
            b.sign(signer="Test")
            if b.requires_dual_sig:
                b.countersign(signer="Test 2")
        assert self.ceremony.is_complete
        assert self.ceremony.completion_pct == 100.0

    def test_signing_certificate_incomplete(self):
        cert = self.ceremony.signing_certificate()
        assert "NOT AVAILABLE" in cert

    def test_signing_certificate_after_complete(self):
        for b in self.ceremony.blocks:
            b.sign(signer="Test Signer", witness="Witness")
            if b.requires_dual_sig:
                b.countersign(signer="Counter Signer")
        cert = self.ceremony.signing_certificate()
        assert "SIGNING CERTIFICATE" in cert
        assert "duly executed" in cert

    def test_sorted_blocks(self):
        sorted_b = self.ceremony.sorted_blocks()
        for i in range(len(sorted_b) - 1):
            assert sorted_b[i].order <= sorted_b[i + 1].order

    def test_by_entity(self):
        entity_name = self.ceremony.entities[0]
        blocks = self.ceremony.by_entity(entity_name)
        assert all(b.entity_name == entity_name for b in blocks)

    def test_summary_output(self):
        summary = self.ceremony.summary()
        assert "DEAL SIGNING CEREMONY" in summary
        assert DEAL_NAME in summary

    def test_serialization(self):
        d = self.ceremony.to_dict()
        assert d["deal_name"] == DEAL_NAME
        assert "blocks" in d

    def test_save(self, tmp_path, monkeypatch):
        import engine.signing_ceremony as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.ceremony)
        assert path.exists()

    def test_execute_block_method(self):
        block_id = self.ceremony.blocks[0].block_id
        result = self.engine.execute_block(self.ceremony, block_id, signer="Exec")
        assert result is True
        assert self.ceremony.blocks[0].status == "SIGNED"

    def test_execute_block_invalid(self):
        result = self.engine.execute_block(self.ceremony, "NONEXISTENT")
        assert result is False


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 4: Deal Dashboard
# ══════════════════════════════════════════════════════════════════

class TestDealDashboard:
    """Tests for DealDashboardEngine."""

    def setup_method(self):
        self.engine = DealDashboardEngine()
        self.dashboard = self.engine.generate(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            additional_entities=[OPTKAS_PLATFORM, QUERUBIN_USA],
        )

    def test_dashboard_created(self):
        assert isinstance(self.dashboard, DealDashboard)
        assert self.dashboard.deal_name == DEAL_NAME

    def test_has_entities(self):
        assert len(self.dashboard.entities) == 4

    def test_has_sections(self):
        assert self.dashboard.total_sections >= 6

    def test_section_names(self):
        names = [s.name for s in self.dashboard.sections]
        assert "MTN Program" in names
        assert "Collateral" in names
        assert "Deal Readiness" in names
        assert "Governance" in names
        assert "Risk Score" in names
        assert "Closing Conditions" in names

    def test_overall_rag_not_grey(self):
        """With real data, should not be all GREY."""
        assert self.dashboard.overall_rag != "GREY"

    def test_mtn_section_green(self):
        """MTN program should be GREEN (98.4% in prior tests)."""
        mtn = next(s for s in self.dashboard.sections if s.name == "MTN Program")
        assert mtn.rag == "GREEN"
        assert mtn.score is not None

    def test_collateral_section_red(self):
        """Collateral RED for real entities (44.4% — 0 pass, 8 warn, 1 fail)."""
        coll = next(s for s in self.dashboard.sections if s.name == "Collateral")
        assert coll.rag == "RED"
        assert coll.score is not None

    def test_readiness_section_amber(self):
        """Deal readiness should be AMBER (CONDITIONAL — action items remain)."""
        ready = next(s for s in self.dashboard.sections if s.name == "Deal Readiness")
        assert ready.rag == "AMBER"

    def test_governance_section(self):
        gov = next(s for s in self.dashboard.sections if s.name == "Governance")
        assert gov.rag in ("GREEN", "AMBER")
        assert gov.score is not None

    def test_risk_section(self):
        risk = next(s for s in self.dashboard.sections if s.name == "Risk Score")
        assert risk.rag in ("GREEN", "AMBER", "RED")
        assert risk.score is not None

    def test_closing_section_red(self):
        """Closing should be RED (0% completion — no CPs resolved)."""
        closing = next(s for s in self.dashboard.sections if s.name == "Closing Conditions")
        assert closing.rag == "RED"

    def test_settlement_section_resolved(self):
        """Settlement should be GREEN or AMBER (escrow engine resolves rails)."""
        settlement = next(s for s in self.dashboard.sections if s.name == "Settlement")
        assert settlement.rag in ("GREEN", "AMBER")

    def test_onboarding_section_resolved(self):
        """Onboarding should be GREEN or AMBER (banking resolver assigns banks)."""
        onboarding = next(s for s in self.dashboard.sections if s.name == "Banking Onboarding")
        assert onboarding.rag in ("GREEN", "AMBER")

    def test_action_items_populated(self):
        """Should have action items across multiple sections."""
        all_items = self.dashboard.all_action_items
        assert len(all_items) > 0

    def test_summary_output(self):
        summary = self.dashboard.summary()
        assert "DEAL DASHBOARD" in summary
        assert DEAL_NAME in summary
        assert "OVERALL STATUS" in summary

    def test_summary_has_rag_counts(self):
        summary = self.dashboard.summary()
        assert "Green:" in summary
        assert "Red:" in summary

    def test_serialization(self):
        d = self.dashboard.to_dict()
        assert d["deal_name"] == DEAL_NAME
        assert "sections" in d
        assert d["overall_rag"] in ("RED", "AMBER", "GREEN", "GREY")

    def test_save(self, tmp_path, monkeypatch):
        import engine.deal_dashboard as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.dashboard)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME

    def test_no_issuer(self):
        """Should handle missing issuer gracefully."""
        d = self.engine.generate(deal_name="Minimal")
        assert isinstance(d, DealDashboard)
        assert d.total_sections >= 6

    def test_section_pct(self):
        """Sections with scores should have pct."""
        for s in self.dashboard.sections:
            if s.score is not None and s.max_score and s.max_score > 0:
                assert s.pct is not None

    def test_dashboard_section_model(self):
        s = DashboardSection(name="Test", rag="GREEN", score=80, max_score=100, headline="OK")
        assert s.pct == 80.0
        d = s.to_dict()
        assert d["name"] == "Test"
        assert d["percentage"] == 80.0
