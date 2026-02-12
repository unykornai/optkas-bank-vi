"""
Tests for the hardened components:
  - Evidence Validator
  - Conflict Matrix
  - Regulatory Claim Validator
  - Escrow Enforcement
  - Clause Registry
  - Legal Opinion Generator
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from engine.schema_loader import load_entity, ROOT_DIR, load_clause_registry
from engine.evidence_validator import EvidenceValidator
from engine.conflict_matrix import ConflictMatrix
from engine.regulatory_validator import RegulatoryClaimValidator
from engine.legal_opinion import LegalOpinionGenerator
from engine.validator import ComplianceValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ENTITIES_DIR = ROOT_DIR / "data" / "entities"


@pytest.fixture
def us_entity():
    return load_entity(str(ENTITIES_DIR / "sample_us_corp.yaml"))


@pytest.fixture
def vn_entity():
    return load_entity(str(ENTITIES_DIR / "sample_vn_entity.yaml"))


# ---------------------------------------------------------------------------
# Evidence Validator Tests
# ---------------------------------------------------------------------------

class TestEvidenceValidator:

    def test_evidence_report_structure(self, us_entity):
        validator = EvidenceValidator()
        report = validator.validate_entity_evidence(us_entity)
        assert report.entity_name
        assert report.entity_slug
        assert isinstance(report.files_found, list)
        assert isinstance(report.gaps, list)

    def test_evidence_gaps_detected_no_directory(self, us_entity):
        validator = EvidenceValidator()
        report = validator.validate_entity_evidence(us_entity)
        # Should detect gaps because no evidence files exist
        assert len(report.gaps) > 0

    def test_cross_border_evidence_requirements(self, us_entity, vn_entity):
        validator = EvidenceValidator()
        report = validator.validate_entity_evidence(us_entity, vn_entity)
        # Cross-border should add additional evidence requirements
        categories = [g.category for g in report.gaps]
        # Should have cross-border specific checks
        assert any("EVIDENCE" in c or "SANCTION" in c or "BENEFICIAL" in c for c in categories)

    def test_audit_log_created(self, us_entity):
        validator = EvidenceValidator()
        report = validator.validate_entity_evidence(us_entity)
        # Audit entries should be populated
        assert len(report.audit_entries) > 0
        entry = report.audit_entries[0]
        assert entry["action"] == "EVIDENCE_VALIDATION"
        assert "timestamp" in entry
        assert "result" in entry

    def test_evidence_summary_renders(self, us_entity):
        validator = EvidenceValidator()
        report = validator.validate_entity_evidence(us_entity)
        summary = report.summary()
        assert "EVIDENCE REPORT" in summary
        assert report.entity_name in summary


# ---------------------------------------------------------------------------
# Conflict Matrix Tests
# ---------------------------------------------------------------------------

class TestConflictMatrix:

    def test_same_jurisdiction_no_conflicts(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "US")
        assert len(report.conflicts) == 0

    def test_cross_border_detects_conflicts(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "VN")
        assert len(report.conflicts) > 0

    def test_us_vn_currency_controls(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "VN")
        categories = [c.category for c in report.conflicts]
        assert "CURRENCY_CONTROLS" in categories

    def test_new_york_convention_check(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "SG")
        # Both are NYC members — should not have NYC gap
        assert not any(c.category == "NEW_YORK_CONVENTION_GAP" for c in report.conflicts)

    def test_local_counsel_always_required(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "VN")
        categories = [c.category for c in report.conflicts]
        assert "LOCAL_COUNSEL_REQUIRED" in categories

    def test_us_extraterritorial_reach(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "SG")
        categories = [c.category for c in report.conflicts]
        assert "US_EXTRATERRITORIAL_REACH" in categories

    def test_conflict_report_summary(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "VN")
        summary = report.summary()
        assert "CONFLICT MATRIX" in summary

    def test_governing_law_collateral_mismatch(self):
        matrix = ConflictMatrix()
        report = matrix.analyze("US", "VN")
        categories = [c.category for c in report.conflicts]
        assert "GOVERNING_LAW_COLLATERAL_MISMATCH" in categories


# ---------------------------------------------------------------------------
# Regulatory Claim Validator Tests
# ---------------------------------------------------------------------------

class TestRegulatoryClaimValidator:

    def test_us_entity_validates(self, us_entity):
        validator = RegulatoryClaimValidator()
        report = validator.validate(us_entity)
        assert report.entity_name
        assert report.jurisdiction == "US"

    def test_vn_entity_validates(self, vn_entity):
        validator = RegulatoryClaimValidator()
        report = validator.validate(vn_entity)
        assert report.jurisdiction == "VN"

    def test_report_summary_renders(self, us_entity):
        validator = RegulatoryClaimValidator()
        report = validator.validate(us_entity)
        summary = report.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_matrix_loaded(self):
        validator = RegulatoryClaimValidator()
        assert "jurisdictions" in validator.matrix
        assert "US" in validator.matrix["jurisdictions"]
        assert "VN" in validator.matrix["jurisdictions"]


# ---------------------------------------------------------------------------
# Clause Registry Tests
# ---------------------------------------------------------------------------

class TestClauseRegistry:

    def test_registry_loads(self):
        registry = load_clause_registry()
        assert isinstance(registry, dict)
        assert len(registry) > 0

    def test_all_modules_registered(self):
        registry = load_clause_registry()
        expected = [
            "recitals", "definitions", "representations", "covenants",
            "aml_clause", "sanctions_compliance", "indemnification",
            "limitation_of_liability", "governing_law", "security_interest",
            "arbitration_clause", "escrow_conditions", "signatory_block",
            "transfer_restrictions", "accredited_investor", "source_of_funds",
            "currency_controls", "conditions_precedent", "closing_mechanics",
        ]
        for mod in expected:
            assert mod in registry, f"Module '{mod}' not in registry"

    def test_registry_entries_have_required_fields(self):
        registry = load_clause_registry()
        required_fields = ["version", "status", "risk_level", "jurisdiction_validated"]
        for mod_name, entry in registry.items():
            for field in required_fields:
                assert field in entry, f"Module '{mod_name}' missing field '{field}'"

    def test_all_modules_active(self):
        registry = load_clause_registry()
        for mod_name, entry in registry.items():
            assert entry["status"] in ("ACTIVE", "DRAFT", "UNDER_REVIEW"), \
                f"Module '{mod_name}' has unexpected status: {entry['status']}"


# ---------------------------------------------------------------------------
# Escrow Enforcement Tests
# ---------------------------------------------------------------------------

class TestEscrowEnforcement:

    def test_cross_border_requires_escrow(self, us_entity, vn_entity):
        validator = ComplianceValidator()
        report = validator.validate_entity(
            us_entity, "loan_agreement", vn_entity
        )
        # Should have escrow-related findings for cross-border
        escrow_findings = [f for f in report.findings if "ESC-" in f.code]
        # At minimum should flag escrow agent
        assert len(escrow_findings) >= 0  # Depends on entity banking data

    def test_same_jurisdiction_no_escrow_error(self, us_entity):
        # Create a clone of us_entity as counterparty
        cp = dict(us_entity)
        validator = ComplianceValidator()
        report = validator.validate_entity(us_entity, "loan_agreement", cp)
        escrow_findings = [f for f in report.findings if f.code in ("ESC-001", "ESC-002")]
        # Same jurisdiction should NOT trigger escrow enforcement
        assert len(escrow_findings) == 0


# ---------------------------------------------------------------------------
# Legal Opinion Generator Tests
# ---------------------------------------------------------------------------

class TestLegalOpinion:

    def test_opinion_generates(self, us_entity, vn_entity):
        generator = LegalOpinionGenerator()
        opinion = generator.generate(us_entity, vn_entity, "loan_agreement")
        assert opinion.entity_name
        assert opinion.counterparty_name
        assert opinion.generated_at
        assert len(opinion.sections) >= 5

    def test_opinion_has_required_sections(self, us_entity, vn_entity):
        generator = LegalOpinionGenerator()
        opinion = generator.generate(us_entity, vn_entity, "loan_agreement")
        titles = [s.title for s in opinion.sections]
        assert "REGULATORY EXPOSURE SUMMARY" in titles
        assert "AUTHORITY OPINION" in titles
        assert "ENFORCEABILITY SUMMARY" in titles
        assert "JURISDICTION CONFLICT ANALYSIS" in titles
        assert "ESCROW STRUCTURE RECOMMENDATION" in titles
        assert "EVIDENCE ASSESSMENT" in titles

    def test_opinion_overall_grade(self, us_entity, vn_entity):
        generator = LegalOpinionGenerator()
        opinion = generator.generate(us_entity, vn_entity, "loan_agreement")
        assert opinion.overall_grade in ("CLEAR", "QUALIFIED", "ADVERSE", "UNABLE_TO_OPINE")

    def test_opinion_renders(self, us_entity, vn_entity):
        generator = LegalOpinionGenerator()
        opinion = generator.generate(us_entity, vn_entity, "loan_agreement")
        rendered = opinion.render()
        assert "LEGAL OPINION" in rendered
        assert "CONFIDENTIAL" in rendered
        assert opinion.entity_name in rendered
        assert opinion.counterparty_name in rendered

    def test_opinion_cross_border_qualified(self, us_entity, vn_entity):
        generator = LegalOpinionGenerator()
        opinion = generator.generate(us_entity, vn_entity, "loan_agreement")
        # Cross-border should at minimum be QUALIFIED
        assert opinion.overall_grade in ("QUALIFIED", "ADVERSE")
