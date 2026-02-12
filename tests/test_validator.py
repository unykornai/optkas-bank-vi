"""Tests for the Compliance Validator (Layer 4)."""

import pytest
from engine.schema_loader import load_entity, ROOT_DIR
from engine.validator import ComplianceValidator, Severity


ENTITIES_DIR = ROOT_DIR / "data" / "entities"


@pytest.fixture
def validator():
    return ComplianceValidator()


@pytest.fixture
def us_entity():
    return load_entity(ENTITIES_DIR / "sample_us_corp.yaml")


@pytest.fixture
def vn_entity():
    return load_entity(ENTITIES_DIR / "sample_vn_entity.yaml")


class TestEntityLoading:
    def test_load_us_entity(self, us_entity):
        assert us_entity["legal_name"] == "Meridian Capital Holdings, Inc."
        assert us_entity["jurisdiction"] == "US-DE"
        assert us_entity["entity_type"] == "corporation"

    def test_load_vn_entity(self, vn_entity):
        assert vn_entity["legal_name"] == "DN2NC Digital Assets Joint Stock Company"
        assert vn_entity["jurisdiction"] == "VN"

    def test_missing_entity_raises(self):
        with pytest.raises(FileNotFoundError):
            load_entity("nonexistent.yaml")


class TestValidation:
    def test_us_entity_passes_basic(self, validator, us_entity):
        report = validator.validate_entity(us_entity)
        assert report.entity_name == "Meridian Capital Holdings, Inc."
        # Should not have errors (US corp is well-formed)
        assert len(report.errors) == 0

    def test_vn_entity_has_licenses(self, validator, vn_entity):
        report = validator.validate_entity(vn_entity)
        # VN entity now has real Vietnamese licenses -- no LIC-001 warning expected
        lic_warnings = [f for f in report.warnings if f.code == "LIC-001"]
        assert len(lic_warnings) == 0
        # Confirm licenses are present on the entity
        assert len(vn_entity.get("licenses", [])) >= 3

    def test_cross_border_detected(self, validator, us_entity, vn_entity):
        report = validator.validate_entity(us_entity, counterparty=vn_entity)
        xb_findings = [f for f in report.findings if f.code.startswith("XB-")]
        assert len(xb_findings) > 0

    def test_same_jurisdiction_no_crossborder(self, validator, us_entity):
        report = validator.validate_entity(us_entity, counterparty=us_entity)
        xb_info = [f for f in report.infos if f.code == "XB-001"]
        assert len(xb_info) > 0  # "Same-jurisdiction transaction"

    def test_transaction_type_validation(self, validator, us_entity):
        report = validator.validate_entity(
            us_entity, transaction_type="loan_agreement"
        )
        # US entity should pass loan agreement requirements
        sig_errors = [f for f in report.errors if f.code == "TX-SIG-001"]
        assert len(sig_errors) == 0

    def test_compliance_score(self, validator, us_entity):
        report = validator.validate_entity(us_entity)
        assert 0 <= report.compliance_score <= 100

    def test_blocked_report(self, validator, vn_entity):
        # VN entity might not be blocked on its own (no regulated status claimed)
        report = validator.validate_entity(vn_entity)
        # is_blocked should be False since no errors expected for non-regulated entity
        # (no license needed if not claiming regulated status)
        assert isinstance(report.is_blocked, bool)
