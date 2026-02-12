"""Tests for the Document Assembler."""

import pytest
from engine.schema_loader import load_entity, ROOT_DIR
from engine.assembler import DocumentAssembler


ENTITIES_DIR = ROOT_DIR / "data" / "entities"


@pytest.fixture
def assembler():
    return DocumentAssembler()


@pytest.fixture
def us_entity():
    return load_entity(ENTITIES_DIR / "sample_us_corp.yaml")


@pytest.fixture
def vn_entity():
    return load_entity(ENTITIES_DIR / "sample_vn_entity.yaml")


class TestAssembly:
    def test_assemble_loan_agreement(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        assert "LOAN AGREEMENT" in doc
        assert "Meridian Capital Holdings" in doc
        assert "DN2NC" in doc

    def test_contains_recitals(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        assert "RECITALS" in doc
        assert "WHEREAS" in doc

    def test_contains_aml_clause(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        assert "ANTI-MONEY LAUNDERING" in doc
        assert "Bank Secrecy Act" in doc

    def test_cross_border_modules_included(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        # Cross-border should include source of funds and currency controls
        assert "SOURCE OF FUNDS" in doc
        assert "CURRENCY" in doc

    def test_contains_signatory_block(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        assert "EXECUTION" in doc
        assert "IN WITNESS WHEREOF" in doc

    def test_contains_governing_law(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        assert "GOVERNING LAW" in doc

    def test_vietnam_specific_language(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "loan_agreement")
        # Should include Vietnam-specific AML reference
        assert "Vietnam" in doc

    def test_unknown_transaction_type_raises(self, assembler, us_entity, vn_entity):
        with pytest.raises(ValueError, match="Unknown transaction type"):
            assembler.assemble(us_entity, vn_entity, "fake_type")

    def test_securities_transaction(self, assembler, us_entity, vn_entity):
        doc = assembler.assemble(us_entity, vn_entity, "subscription_agreement")
        assert "SUBSCRIPTION AGREEMENT" in doc
        assert "INVESTOR REPRESENTATIONS" in doc or "TRANSFER RESTRICTIONS" in doc
