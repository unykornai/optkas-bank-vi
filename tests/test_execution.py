"""
Tests for the Execution Control Layer.

Covers:
  - ExecutionChecklist — build, gate grouping, clear-to-close logic
  - CounterpartyDossier — build, risk rating, render, save
  - DealRoomPackager — full package, manifest, file creation
  - DealLifecycleManager — state machine, transitions, gates, persistence
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.schema_loader import load_entity, load_transaction_type, ROOT_DIR
from engine.execution_checklist import (
    ChecklistBuilder,
    ExecutionChecklist,
    ChecklistItem,
)
from engine.counterparty_dossier import (
    DossierBuilder,
    CounterpartyDossier,
    RiskRating,
)
from engine.deal_room import DealRoomPackager
from engine.deal_lifecycle import (
    DealLifecycleManager,
    DealRecord,
    DealState,
    TRANSITIONS,
)
from engine.validator import ComplianceValidator, Finding, Severity
from engine.red_flags import RedFlagDetector
from engine.evidence_validator import EvidenceValidator
from engine.deal_classifier import DealClassifier


ENTITIES_DIR = ROOT_DIR / "data" / "entities"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def us_entity():
    return load_entity(ENTITIES_DIR / "sample_us_corp.yaml")


@pytest.fixture
def vn_entity():
    return load_entity(ENTITIES_DIR / "sample_vn_entity.yaml")


# =========================================================================
# ExecutionChecklist
# =========================================================================

class TestExecutionChecklist:
    def test_build_produces_items(self, us_entity, vn_entity):
        validator = ComplianceValidator()
        val_a = validator.validate_entity(us_entity, "loan_agreement", vn_entity)
        rf = RedFlagDetector().scan(us_entity, vn_entity, "loan_agreement")
        ev = EvidenceValidator().validate_entity_evidence(us_entity, vn_entity)

        tx_def = load_transaction_type("loan_agreement")
        cls = DealClassifier().classify(us_entity, vn_entity, "loan_agreement", tx_def)

        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            validation_findings=val_a.findings,
            red_flags=rf.flags,
            evidence_gaps=ev.gaps,
            classification_tags=cls.tags,
        )

        assert len(checklist.items) > 0
        assert checklist.transaction_type == "loan_agreement"
        assert checklist.entity_name == "Meridian Capital Holdings, Inc."

    def test_items_have_required_fields(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            validation_findings=[Finding(Severity.ERROR, "TEST-001", "Test error", "field")],
        )
        item = checklist.items[0]
        assert item.item_id
        assert item.category
        assert item.priority
        assert item.gate
        assert item.responsible

    def test_clear_to_close_false_when_open(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            validation_findings=[Finding(Severity.ERROR, "BLK-001", "Blocks")],
        )
        assert checklist.is_clear_to_close is False

    def test_clear_to_close_true_when_all_cleared(self):
        checklist = ExecutionChecklist(
            transaction_type="test",
            entity_name="A",
            counterparty_name="B",
        )
        checklist.items.append(ChecklistItem(
            item_id="T-001", category="TEST", priority="HIGH",
            description="Test item", gate="PRE_CLOSING",
            status="CLEARED",
        ))
        assert checklist.is_clear_to_close is True

    def test_items_by_gate_grouping(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            validation_findings=[
                Finding(Severity.ERROR, "A-001", "Error item"),
                Finding(Severity.WARNING, "B-001", "Warning item"),
            ],
        )
        gates = checklist.items_by_gate()
        assert isinstance(gates, dict)
        # At least PRE_GENERATION (from ERROR) and PRE_SIGNATURE (from WARNING)
        assert len(gates) >= 1

    def test_summary_readable(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            validation_findings=[Finding(Severity.ERROR, "X-001", "Test")],
        )
        summary = checklist.summary()
        assert "EXECUTION CHECKLIST" in summary
        assert "Open:" in summary

    def test_to_dict_serializable(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            red_flags=RedFlagDetector().scan(us_entity, vn_entity).flags,
        )
        d = checklist.to_dict()
        assert json.dumps(d)  # Must be JSON-serializable
        assert "items" in d

    def test_signature_blocked_item(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(
            us_entity, vn_entity, "loan_agreement",
            signature_blocked=True,
        )
        sig_items = [i for i in checklist.items if i.category == "SIGNATURE"]
        assert len(sig_items) == 1
        assert sig_items[0].priority == "CRITICAL"
        assert sig_items[0].gate == "PRE_SIGNATURE"

    def test_empty_checklist(self, us_entity, vn_entity):
        builder = ChecklistBuilder()
        checklist = builder.build(us_entity, vn_entity, "loan_agreement")
        assert isinstance(checklist, ExecutionChecklist)
        assert checklist.generated_at


# =========================================================================
# CounterpartyDossier
# =========================================================================

class TestCounterpartyDossier:
    def test_build_us_entity(self, us_entity, vn_entity):
        builder = DossierBuilder()
        dossier = builder.build(us_entity, vn_entity, "loan_agreement")

        assert dossier.legal_name == "Meridian Capital Holdings, Inc."
        assert dossier.jurisdiction == "US-DE"
        assert dossier.entity_type == "corporation"

    def test_build_vn_entity(self, vn_entity, us_entity):
        builder = DossierBuilder()
        dossier = builder.build(vn_entity, us_entity, "loan_agreement")

        assert "DN2NC" in dossier.legal_name
        assert dossier.jurisdiction == "VN"

    def test_risk_rating_calculated(self, us_entity, vn_entity):
        builder = DossierBuilder()
        dossier = builder.build(us_entity, vn_entity, "loan_agreement")

        assert 0 <= dossier.risk_rating.total <= 100
        assert dossier.risk_rating.grade in ("A", "B", "C", "D", "F")

    def test_risk_rating_components(self):
        rating = RiskRating(
            regulatory_score=20,
            evidence_score=25,
            governance_score=20,
            red_flag_score=20,
        )
        assert rating.total == 85
        assert rating.grade == "A"

    def test_risk_rating_grades(self):
        assert RiskRating(regulatory_score=25, evidence_score=25, governance_score=25, red_flag_score=25).grade == "A"
        assert RiskRating(regulatory_score=20, evidence_score=20, governance_score=20, red_flag_score=15).grade == "B"
        assert RiskRating(regulatory_score=15, evidence_score=15, governance_score=15, red_flag_score=10).grade == "C"
        assert RiskRating(regulatory_score=10, evidence_score=10, governance_score=10, red_flag_score=5).grade == "D"
        assert RiskRating(regulatory_score=5, evidence_score=5, governance_score=5, red_flag_score=5).grade == "F"

    def test_dossier_render(self, us_entity, vn_entity):
        builder = DossierBuilder()
        dossier = builder.build(us_entity, vn_entity)
        rendered = dossier.render()
        assert "COUNTERPARTY RISK DOSSIER" in rendered
        assert "REGULATORY POSTURE" in rendered
        assert "SIGNATORY AUTHORITY MAP" in rendered
        assert "RISK RATING" in rendered

    def test_dossier_save(self, us_entity, tmp_path):
        builder = DossierBuilder()
        dossier = builder.build(us_entity)
        path = dossier.save(directory=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["legal_name"] == dossier.legal_name

    def test_dossier_to_dict(self, us_entity):
        builder = DossierBuilder()
        dossier = builder.build(us_entity)
        d = dossier.to_dict()
        assert json.dumps(d)
        assert "risk_rating" in d
        assert d["risk_rating"]["grade"] in ("A", "B", "C", "D", "F")

    def test_regulatory_posture_populated(self, us_entity):
        builder = DossierBuilder()
        dossier = builder.build(us_entity)
        rp = dossier.regulatory_posture
        assert rp["is_broker_dealer"] is True
        assert rp["license_count"] >= 2

    def test_signatory_map_populated(self, us_entity):
        builder = DossierBuilder()
        dossier = builder.build(us_entity)
        assert len(dossier.signatory_map) > 0
        assert "name" in dossier.signatory_map[0]


# =========================================================================
# DealRoom
# =========================================================================

class TestDealRoom:
    def test_package_creates_folder(self, us_entity, vn_entity, tmp_path):
        packager = DealRoomPackager()
        results = packager.package(us_entity, vn_entity, "loan_agreement", output_dir=tmp_path)

        room_path = results["deal_room_path"]
        assert room_path.exists()
        assert room_path.is_dir()

    def test_manifest_created(self, us_entity, vn_entity, tmp_path):
        packager = DealRoomPackager()
        results = packager.package(us_entity, vn_entity, "loan_agreement", output_dir=tmp_path)

        manifest_path = results["deal_room_path"] / "_manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["deal_room_version"] == "1.0"
        assert "files" in manifest

    def test_all_files_present(self, us_entity, vn_entity, tmp_path):
        packager = DealRoomPackager()
        results = packager.package(us_entity, vn_entity, "loan_agreement", output_dir=tmp_path)

        room = results["deal_room_path"]
        expected = [
            "01_agreement.md",
            "02_legal_opinion.txt",
            "03_execution_checklist.txt",
            "04_entity_dossier.txt",
            "05_counterparty_dossier.txt",
            "06_deal_classification.json",
            "07_policy_snapshot.json",
        ]
        for fname in expected:
            assert (room / fname).exists(), f"Missing: {fname}"

    def test_manifest_has_risk_data(self, us_entity, vn_entity, tmp_path):
        packager = DealRoomPackager()
        results = packager.package(us_entity, vn_entity, "loan_agreement", output_dir=tmp_path)

        manifest = results["manifest"]
        assert "opinion_grade" in manifest
        assert "risk_tier" in manifest
        assert "risk_score" in manifest
        assert "checklist_items" in manifest

    def test_results_have_components(self, us_entity, vn_entity, tmp_path):
        packager = DealRoomPackager()
        results = packager.package(us_entity, vn_entity, "loan_agreement", output_dir=tmp_path)

        assert "opinion" in results
        assert "checklist" in results
        assert "entity_dossier" in results
        assert "counterparty_dossier" in results
        assert "classification" in results


# =========================================================================
# DealLifecycle
# =========================================================================

class TestDealLifecycle:
    def test_create_deal(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        deal = manager.create_deal("DEAL-001", "loan_agreement", "Meridian", "DN2NC")

        assert deal.deal_id == "DEAL-001"
        assert deal.state == "DRAFT"
        assert deal.created_at

    def test_deal_persists(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-002", "loan_agreement", "A", "B")

        loaded = manager.load_deal("DEAL-002")
        assert loaded.deal_id == "DEAL-002"
        assert loaded.state == "DRAFT"

    def test_draft_to_review(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-003", "loan_agreement", "A", "B")

        deal = manager.transition("DEAL-003", "REVIEW", actor="test", reason="Ready for review")
        assert deal.state == "REVIEW"
        assert len(deal.transitions) == 1

    def test_review_to_conditional(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-004", "loan_agreement", "A", "B")
        manager.transition("DEAL-004", "REVIEW")

        deal = manager.transition(
            "DEAL-004", "CONDITIONALLY_APPROVED",
            compliance_score=75, opinion_grade="QUALIFIED",
        )
        assert deal.state == "CONDITIONALLY_APPROVED"

    def test_gate_blocks_on_adverse(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-005", "loan_agreement", "A", "B")
        manager.transition("DEAL-005", "REVIEW")

        deal = manager.transition(
            "DEAL-005", "CONDITIONALLY_APPROVED",
            opinion_grade="ADVERSE",
        )
        # Should auto-block because ADVERSE grade fails gate
        assert deal.state == "BLOCKED"

    def test_gate_blocks_on_low_compliance(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-006", "loan_agreement", "A", "B")
        manager.transition("DEAL-006", "REVIEW")

        deal = manager.transition(
            "DEAL-006", "CONDITIONALLY_APPROVED",
            compliance_score=30,
        )
        assert deal.state == "BLOCKED"

    def test_force_overrides_gate(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-007", "loan_agreement", "A", "B")
        manager.transition("DEAL-007", "REVIEW")

        deal = manager.transition(
            "DEAL-007", "CONDITIONALLY_APPROVED",
            opinion_grade="ADVERSE",
            force=True,
        )
        assert deal.state == "CONDITIONALLY_APPROVED"

    def test_blocked_returns_to_review(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-008", "loan_agreement", "A", "B")
        manager.transition("DEAL-008", "REVIEW")
        manager.transition("DEAL-008", "CONDITIONALLY_APPROVED", opinion_grade="ADVERSE")
        assert manager.load_deal("DEAL-008").state == "BLOCKED"

        deal = manager.transition("DEAL-008", "REVIEW", reason="Conditions remediated")
        assert deal.state == "REVIEW"

    def test_invalid_transition_raises(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-009", "loan_agreement", "A", "B")

        with pytest.raises(ValueError, match="Cannot transition"):
            manager.transition("DEAL-009", "EXECUTED")

    def test_full_lifecycle(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-010", "loan_agreement", "A", "B")

        manager.transition("DEAL-010", "REVIEW")
        manager.transition("DEAL-010", "CONDITIONALLY_APPROVED",
                          compliance_score=80, opinion_grade="QUALIFIED")
        manager.transition("DEAL-010", "APPROVED", checklist_clear=True,
                          opinion_grade="QUALIFIED")
        manager.transition("DEAL-010", "EXECUTED", checklist_clear=True)
        deal = manager.transition("DEAL-010", "CLOSED", reason="Deal completed")

        assert deal.state == "CLOSED"
        assert len(deal.transitions) == 5
        assert deal.is_terminal is True
        assert deal.available_transitions() == []

    def test_list_deals(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-A", "loan_agreement", "A", "B")
        manager.create_deal("DEAL-B", "subscription_agreement", "C", "D")

        deals = manager.list_deals()
        assert len(deals) == 2
        ids = {d.deal_id for d in deals}
        assert "DEAL-A" in ids
        assert "DEAL-B" in ids

    def test_deal_summary_readable(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        deal = manager.create_deal("DEAL-SUM", "loan_agreement", "A", "B")
        summary = deal.summary()
        assert "DEAL LIFECYCLE" in summary
        assert "DRAFT" in summary

    def test_deal_to_dict(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-DICT", "loan_agreement", "A", "B")
        manager.transition("DEAL-DICT", "REVIEW")

        deal = manager.load_deal("DEAL-DICT")
        d = deal.to_dict()
        assert json.dumps(d)
        assert d["state"] == "REVIEW"
        assert len(d["transitions"]) == 1

    def test_transition_records_gate_checks(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        manager.create_deal("DEAL-GATE", "loan_agreement", "A", "B")
        manager.transition("DEAL-GATE", "REVIEW")

        deal = manager.transition(
            "DEAL-GATE", "CONDITIONALLY_APPROVED",
            compliance_score=80, opinion_grade="QUALIFIED", risk_tier="HIGH",
        )

        last_t = deal.transitions[-1]
        assert "compliance_score" in last_t.gate_check
        assert last_t.gate_check["compliance_score"]["passed"] is True

    def test_deal_not_found_raises(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.load_deal("NONEXISTENT")

    def test_transition_model(self):
        """Verify all states have defined transitions."""
        for state in DealState:
            assert state in TRANSITIONS

    def test_closed_is_terminal(self, tmp_path):
        manager = DealLifecycleManager(deals_dir=tmp_path)
        deal = DealRecord(
            deal_id="T", transaction_type="t",
            entity_name="A", counterparty_name="B",
            state="CLOSED",
        )
        assert deal.is_terminal is True
        assert deal.available_transitions() == []
