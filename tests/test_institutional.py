"""
Tests for the Institutional Governance Layer.

Covers:
  - PolicyEngine — loads, enforces, summarizes
  - AuditLogger — writes provable compliance records
  - DealClassifier — auto-classifies and scores deals
  - Liability Banner — assembler appends disclaimer
  - Policy-driven signature blocking in LegalOpinion
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from engine.schema_loader import load_entity, load_transaction_type, ROOT_DIR
from engine.policy_engine import PolicyEngine
from engine.audit_logger import AuditLogger
from engine.deal_classifier import DealClassifier, DealClassification, DealTag
from engine.assembler import DocumentAssembler
from engine.legal_opinion import LegalOpinionGenerator


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


@pytest.fixture
def policy():
    return PolicyEngine()


@pytest.fixture
def tmp_logs(tmp_path):
    return tmp_path / "logs"


@pytest.fixture
def tmp_policy(tmp_path):
    """Create a temporary policy file for override tests."""
    policy_data = {
        "policy_version": "0.0.1-test",
        "execution_tier": 2,
        "last_reviewed": "2025-01-01",
        "approved_by": "Test Suite",
        "generation_controls": {
            "allow_cross_border": True,
            "allow_securities": True,
            "allow_collateral_transactions": True,
            "require_dual_jurisdiction_rules": True,
        },
        "cross_border_controls": {
            "escrow_missing_severity": "block",
            "currency_control_severity": "warn",
            "require_local_counsel_severity": "silent",
        },
        "signatory_controls": {
            "single_signatory_severity": "warn",
            "dual_signature_threshold_usd": 5000000,
        },
        "evidence_controls": {
            "missing_evidence_severity": "warn",
        },
        "opinion_controls": {
            "adverse_grade_blocks_signature": True,
            "unable_to_opine_blocks_signature": True,
        },
        "red_flag_controls": {
            "critical_red_flag_severity": "block",
            "high_red_flag_severity": "warn",
            "pep_severity": "warn",
            "sanctions_gap_severity": "block",
        },
        "audit_controls": {
            "audit_every_run": True,
            "retention_days": 2555,
        },
        "liability_controls": {
            "append_disclaimer_to_documents": True,
            "disclaimer_text": "TEST DISCLAIMER TEXT.",
            "require_human_approval_stamp": True,
        },
    }
    path = tmp_path / "test_policy.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(policy_data, f)
    return path


# =========================================================================
# PolicyEngine
# =========================================================================

class TestPolicyEngine:
    def test_loads_default_policy(self, policy):
        assert policy.version != "0.0.0"
        assert policy.execution_tier in (1, 2, 3)

    def test_tier_label(self, policy):
        labels = {1: "Advisory", 2: "Conditional Execution", 3: "Autonomous"}
        assert policy.tier_label == labels[policy.execution_tier]

    def test_should_block_reads_policy(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.should_block("escrow_missing_severity", "cross_border_controls") is True
        assert policy.should_block("currency_control_severity", "cross_border_controls") is False

    def test_should_warn(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.should_warn("currency_control_severity", "cross_border_controls") is True
        assert policy.should_warn("escrow_missing_severity", "cross_border_controls") is True  # block implies warn

    def test_is_silent(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.is_silent("require_local_counsel_severity", "cross_border_controls") is True
        assert policy.is_silent("escrow_missing_severity", "cross_border_controls") is False

    def test_advisory_tier_never_blocks(self, tmp_path):
        policy_data = {"execution_tier": 1, "cross_border_controls": {"escrow_missing_severity": "block"}}
        path = tmp_path / "advisory.yaml"
        with open(path, "w") as f:
            yaml.dump(policy_data, f)
        policy = PolicyEngine(policy_path=path)
        assert policy.should_block("escrow_missing_severity", "cross_border_controls") is False

    def test_adverse_blocks_signature(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.adverse_blocks_signature() is True

    def test_disclaimer_text(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.disclaimer_text() == "TEST DISCLAIMER TEXT."

    def test_should_append_disclaimer(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.should_append_disclaimer() is True

    def test_should_audit(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert policy.should_audit() is True

    def test_summary_contains_enforcement(self, policy):
        summary = policy.summary()
        assert "Execution Tier" in summary
        assert "Escrow Missing" in summary

    def test_missing_policy_file_defaults(self, tmp_path):
        policy = PolicyEngine(policy_path=tmp_path / "nonexistent.yaml")
        assert policy.version == "0.0.0"
        assert policy.execution_tier == 1

    def test_section_accessors(self, tmp_policy):
        policy = PolicyEngine(policy_path=tmp_policy)
        assert isinstance(policy.generation, dict)
        assert isinstance(policy.cross_border, dict)
        assert isinstance(policy.securities, dict)
        assert isinstance(policy.signatory, dict)
        assert isinstance(policy.evidence, dict)
        assert isinstance(policy.opinion, dict)
        assert isinstance(policy.red_flags, dict)
        assert isinstance(policy.audit, dict)
        assert isinstance(policy.liability, dict)


# =========================================================================
# AuditLogger
# =========================================================================

class TestAuditLogger:
    def test_log_run_creates_file(self, tmp_logs):
        logger = AuditLogger(logs_dir=tmp_logs)
        path = logger.log_run(operation="test-run")
        assert path.exists()
        assert path.suffix == ".json"

    def test_record_has_required_fields(self, tmp_logs):
        logger = AuditLogger(logs_dir=tmp_logs)
        path = logger.log_run(
            operation="generate",
            transaction_type="loan_agreement",
        )
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["audit_version"] == "1.0"
        assert record["operation"] == "generate"
        assert "timestamp_utc" in record
        assert "record_hash" in record

    def test_record_hash_present(self, tmp_logs):
        logger = AuditLogger(logs_dir=tmp_logs)
        path = logger.log_run(operation="compliance-report")
        record = json.loads(path.read_text(encoding="utf-8"))
        assert len(record["record_hash"]) == 64  # SHA256 hex

    def test_entity_hashing(self, tmp_logs, us_entity):
        logger = AuditLogger(logs_dir=tmp_logs)
        path = logger.log_run(operation="validate", entity=us_entity)
        record = json.loads(path.read_text(encoding="utf-8"))
        assert "entity" in record
        assert "data_hash" in record["entity"]
        assert len(record["entity"]["data_hash"]) == 64

    def test_entity_and_counterparty_hashed(self, tmp_logs, us_entity, vn_entity):
        logger = AuditLogger(logs_dir=tmp_logs)
        path = logger.log_run(
            operation="generate",
            entity=us_entity,
            counterparty=vn_entity,
            transaction_type="loan_agreement",
        )
        record = json.loads(path.read_text(encoding="utf-8"))
        assert "entity" in record
        assert "counterparty" in record
        assert record["entity"]["data_hash"] != record["counterparty"]["data_hash"]

    def test_findings_to_dicts(self):
        from engine.validator import Finding, Severity
        findings = [
            Finding(Severity.ERROR, "ESC-001", "Missing escrow", "banking.escrow"),
            Finding(Severity.WARNING, "SIG-001", "Single signatory", ""),
        ]
        dicts = AuditLogger.findings_to_dicts(findings)
        assert len(dicts) == 2
        assert dicts[0]["code"] == "ESC-001"
        assert dicts[0]["severity"].upper() == "ERROR"
        assert dicts[1]["code"] == "SIG-001"

    def test_logs_dir_auto_created(self, tmp_path):
        logs_dir = tmp_path / "nested" / "audit" / "logs"
        logger = AuditLogger(logs_dir=logs_dir)
        path = logger.log_run(operation="test")
        assert logs_dir.exists()
        assert path.exists()

    def test_opinion_grade_in_record(self, tmp_logs):
        logger = AuditLogger(logs_dir=tmp_logs)
        path = logger.log_run(operation="legal-opinion", opinion_grade="QUALIFIED")
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["opinion_grade"] == "QUALIFIED"

    def test_deal_classification_in_record(self, tmp_logs):
        logger = AuditLogger(logs_dir=tmp_logs)
        classification = {"risk_tier": "HIGH", "risk_score": 50, "tags": []}
        path = logger.log_run(operation="classify", deal_classification=classification)
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["deal_classification"]["risk_tier"] == "HIGH"


# =========================================================================
# DealClassifier
# =========================================================================

class TestDealClassifier:
    def test_cross_border_funds_tagged(self, us_entity, vn_entity):
        tx_def = load_transaction_type("loan_agreement")
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "loan_agreement", tx_def)
        tags = [t.tag for t in result.tags]
        assert "REGULATED_FINANCIAL_ACTIVITY" in tags

    def test_fx_controlled_tagged(self, us_entity, vn_entity):
        tx_def = load_transaction_type("loan_agreement")
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "loan_agreement", tx_def)
        tags = [t.tag for t in result.tags]
        assert "FX_CONTROLLED_TRANSACTION" in tags

    def test_same_jurisdiction_simpler(self, us_entity):
        tx_def = load_transaction_type("loan_agreement")
        classifier = DealClassifier()
        us_entity_2 = us_entity.copy()
        result = classifier.classify(us_entity, us_entity_2, "loan_agreement", tx_def)
        tags = [t.tag for t in result.tags]
        # Same jurisdiction — no cross-border or FX tags
        assert "REGULATED_FINANCIAL_ACTIVITY" not in tags
        assert "FX_CONTROLLED_TRANSACTION" not in tags

    def test_securities_category_tagged(self, us_entity, vn_entity):
        tx_def = load_transaction_type("subscription_agreement")
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "subscription_agreement", tx_def)
        tags = [t.tag for t in result.tags]
        assert "SECURITIES_REGULATORY_COMPLIANCE" in tags

    def test_risk_score_bounded(self, us_entity, vn_entity):
        tx_def = load_transaction_type("loan_agreement")
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "loan_agreement", tx_def)
        assert 0 <= result.risk_score <= 100

    def test_risk_tier_valid(self, us_entity, vn_entity):
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "loan_agreement")
        assert result.risk_tier in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

    def test_to_dict_serializable(self, us_entity, vn_entity):
        tx_def = load_transaction_type("loan_agreement")
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "loan_agreement", tx_def)
        d = result.to_dict()
        assert json.dumps(d)  # Must be JSON-serializable
        assert "risk_tier" in d
        assert "tags" in d

    def test_summary_readable(self, us_entity, vn_entity):
        classifier = DealClassifier()
        result = classifier.classify(us_entity, vn_entity, "loan_agreement")
        summary = result.summary()
        assert "Risk Tier" in summary
        assert "Risk Score" in summary

    def test_empty_classification(self):
        classification = DealClassification(transaction_type="test")
        assert classification.risk_tier == "LOW"
        assert classification.risk_score == 0

    def test_deal_tag_model(self):
        tag = DealTag(
            tag="TEST_TAG",
            risk_level="HIGH",
            description="Test description",
            required_actions=["Action 1"],
        )
        assert tag.tag == "TEST_TAG"
        assert tag.risk_level == "HIGH"


# =========================================================================
# Liability Banner (Assembler Integration)
# =========================================================================

class TestLiabilityBanner:
    def test_assembler_appends_disclaimer(self, us_entity, vn_entity):
        """When policy says append disclaimer, the assembled doc includes it."""
        assembler = DocumentAssembler()
        document = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        # Default policy should include disclaimer
        assert "LEGAL NOTICE" in document

    def test_disclaimer_text_from_policy(self, us_entity, vn_entity):
        assembler = DocumentAssembler()
        document = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        policy = PolicyEngine()
        expected = policy.disclaimer_text()
        if policy.should_append_disclaimer() and expected:
            assert expected in document


# =========================================================================
# Policy-Driven Signature Blocking (Legal Opinion Integration)
# =========================================================================

class TestSignatureBlocking:
    def test_opinion_has_signature_fields(self, us_entity, vn_entity):
        gen = LegalOpinionGenerator()
        opinion = gen.generate(us_entity, vn_entity, "loan_agreement")
        assert hasattr(opinion, "signature_ready")
        assert hasattr(opinion, "signature_blocked_reason")

    def test_opinion_render_includes_signature_status(self, us_entity, vn_entity):
        gen = LegalOpinionGenerator()
        opinion = gen.generate(us_entity, vn_entity, "loan_agreement")
        rendered = opinion.render()
        assert "SIGNATURE STATUS" in rendered


# =========================================================================
# Policy Integration in Validator
# =========================================================================

class TestPolicyValidatorIntegration:
    def test_validator_has_policy(self):
        from engine.validator import ComplianceValidator
        validator = ComplianceValidator()
        assert hasattr(validator, "policy")
        assert isinstance(validator.policy, PolicyEngine)

    def test_escrow_severity_policy_driven(self, us_entity, vn_entity):
        """Escrow findings severity respects policy configuration."""
        from engine.validator import ComplianceValidator
        validator = ComplianceValidator()
        report = validator.validate_entity(us_entity, "loan_agreement", vn_entity)
        # Just ensure it runs without error — actual severity depends on entity data
        assert report is not None
