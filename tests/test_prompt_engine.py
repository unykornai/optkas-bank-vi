"""Tests for the Prompt Engine (Layer 5)."""

import json
import pytest
from engine.schema_loader import load_entity, ROOT_DIR
from engine.prompt_engine import PromptEngine


ENTITIES_DIR = ROOT_DIR / "data" / "entities"


@pytest.fixture
def engine():
    return PromptEngine()


@pytest.fixture
def us_entity():
    return load_entity(ENTITIES_DIR / "sample_us_corp.yaml")


@pytest.fixture
def vn_entity():
    return load_entity(ENTITIES_DIR / "sample_vn_entity.yaml")


class TestPromptEngine:
    def test_build_prompt_returns_package(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        assert "system_prompt" in package
        assert "user_prompt" in package
        assert "validation_report" in package
        assert "red_flag_report" in package
        assert "metadata" in package

    def test_system_prompt_contains_rules(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        sp = package["system_prompt"]
        assert "You may not invent licenses" in sp
        assert "Red-flag summary appended" in sp

    def test_user_prompt_contains_entity_data(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        up = package["user_prompt"]
        assert "Meridian Capital" in up
        assert "DN2NC" in up

    def test_cross_border_detected_in_metadata(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        assert package["metadata"]["is_cross_border"] is True

    def test_same_jurisdiction_not_crossborder(self, engine, us_entity):
        package = engine.build_prompt(us_entity, us_entity, "loan_agreement")
        assert package["metadata"]["is_cross_border"] is False

    def test_compliance_scores_present(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        meta = package["metadata"]
        assert 0 <= meta["compliance_score_entity"] <= 100
        assert 0 <= meta["compliance_score_counterparty"] <= 100

    def test_jurisdiction_rules_in_prompt(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        up = package["user_prompt"]
        assert "Required Clauses" in up

    def test_prompt_contains_generation_command(self, engine, us_entity, vn_entity):
        package = engine.build_prompt(us_entity, vn_entity, "loan_agreement")
        up = package["user_prompt"]
        assert "GENERATE THE FOLLOWING" in up
        assert "Compliance checklist" in up
        assert "Missing data warnings" in up


