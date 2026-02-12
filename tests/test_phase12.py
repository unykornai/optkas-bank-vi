"""
Phase 12 Tests — Executive Briefing Pack
=================================================
Tests for: BriefingPackEngine, EntityStanding, DealStructure,
           ForwardPath, CLI commands (briefing-pack, entity-standing, forward-path)

Target: ~100 tests
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

# ── Engine imports ────────────────────────────────────────────────

from engine.briefing_pack import (
    BriefingPackEngine,
    BriefingPack,
    EntityStanding,
    DealStructure,
    ForwardPath,
    ForwardAction,
)
from engine.deal_dashboard import DealDashboard


# ── Paths ─────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent

TC_ADVANTAGE = ROOT / "data" / "entities" / "tc_advantage_traders.yaml"
OPTKAS1_SPV = ROOT / "data" / "entities" / "optkas1_spv.yaml"
OPTKAS_PLATFORM = ROOT / "data" / "entities" / "optkas_platform.yaml"
QUERUBIN_USA = ROOT / "data" / "entities" / "querubin_usa.yaml"
CUERPO_MARKETS = ROOT / "data" / "entities" / "cuerpo_markets.yaml"

DEAL_NAME = "OPTKAS-TC Full Deal"


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 1: BriefingPack Model
# ══════════════════════════════════════════════════════════════════

class TestBriefingPackModel:
    """Tests for BriefingPack dataclass."""

    def test_briefing_pack_creation(self):
        pack = BriefingPack(deal_name="Test Deal")
        assert pack.deal_name == "Test Deal"
        assert pack.generated_at
        assert pack.entity_standings == []
        assert pack.dashboard is None
        assert pack.forward_path is None

    def test_briefing_pack_render_markdown(self):
        pack = BriefingPack(deal_name="Test Deal")
        md = pack.render_markdown()
        assert "EXECUTIVE BRIEFING PACK" in md
        assert "Test Deal" in md
        assert "PLATFORM OVERVIEW" in md
        assert "ENTITY STANDINGS" in md
        assert "DEAL STRUCTURE" in md
        assert "DEAL DASHBOARD" in md
        assert "FORWARD PATH" in md

    def test_briefing_pack_to_dict(self):
        pack = BriefingPack(deal_name="Test Deal")
        d = pack.to_dict()
        assert d["deal_name"] == "Test Deal"
        assert "generated_at" in d
        assert "entity_standings" in d
        assert "platform_overview" in d


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 2: EntityStanding Model
# ══════════════════════════════════════════════════════════════════

class TestEntityStandingModel:
    """Tests for EntityStanding dataclass."""

    def test_entity_standing_creation(self):
        es = EntityStanding(
            legal_name="Test Corp",
            trade_name="Test",
            entity_type="llc",
            jurisdiction="US",
            jurisdiction_risk="LOW",
            formation_date="2020-01-01",
            directors=[{"name": "A", "title": "Dir"}],
            signatories=[{"name": "A", "title": "Dir", "authority": "full"}],
            beneficial_owners=[],
            banking_status="COMPLETE",
            banking_summary="Full banking available",
            swift_code="TESTUS33",
            settlement_bank="Test Bank",
            custodian=None,
            evidence_files=["doc1.pdf"],
            evidence_score="ADEQUATE",
            regulatory_notes=[],
            gaps=[],
            strengths=["Good standing"],
            role_in_deal="ISSUER",
        )
        assert es.legal_name == "Test Corp"
        assert es.jurisdiction_risk == "LOW"
        assert es.banking_status == "COMPLETE"
        assert es.role_in_deal == "ISSUER"


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 3: ForwardAction & ForwardPath Models
# ══════════════════════════════════════════════════════════════════

class TestForwardPathModel:
    """Tests for ForwardAction and ForwardPath."""

    def test_forward_action_creation(self):
        a = ForwardAction(
            action_id="FP-001",
            phase=1,
            category="COMPLIANCE",
            description="Screen beneficial owners",
            responsible="Entity XYZ",
            dependency=None,
            priority="CRITICAL",
            status="NOT_STARTED",
            estimated_days=3,
        )
        assert a.action_id == "FP-001"
        assert a.priority == "CRITICAL"

    def test_forward_path_totals(self):
        actions = [
            ForwardAction("FP-001", 1, "C", "A", "X", None, "CRITICAL", "COMPLETE", 1),
            ForwardAction("FP-002", 1, "C", "B", "X", None, "HIGH", "NOT_STARTED", 2),
            ForwardAction("FP-003", 2, "C", "C", "X", None, "MEDIUM", "IN_PROGRESS", 3),
        ]
        fp = ForwardPath(
            phases=[{"name": "P1"}, {"name": "P2"}],
            actions=actions,
            phase_1_target="t1",
            phase_2_target="t2",
            phase_3_target="t3",
        )
        assert fp.total_actions == 3
        assert fp.completed == 1
        assert len(fp.critical_actions) == 1

    def test_forward_path_by_phase(self):
        actions = [
            ForwardAction("FP-001", 1, "C", "A", "X", None, "CRITICAL", "COMPLETE", 1),
            ForwardAction("FP-002", 2, "C", "B", "X", None, "HIGH", "NOT_STARTED", 2),
            ForwardAction("FP-003", 2, "C", "C", "X", None, "MEDIUM", "NOT_STARTED", 3),
        ]
        fp = ForwardPath(
            phases=[{"name": "P1"}, {"name": "P2"}],
            actions=actions,
            phase_1_target="t1",
            phase_2_target="t2",
            phase_3_target="t3",
        )
        by_phase = fp.by_phase
        assert len(by_phase[1]) == 1
        assert len(by_phase[2]) == 2


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 4: BriefingPackEngine — Full Build
# ══════════════════════════════════════════════════════════════════

class TestBriefingPackBuild:
    """Tests for BriefingPackEngine.build() with real entities."""

    def setup_method(self):
        self.engine = BriefingPackEngine()
        self.pack = self.engine.build(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            platform_path=OPTKAS_PLATFORM,
            investor_path=QUERUBIN_USA,
        )

    def test_pack_deal_name(self):
        assert self.pack.deal_name == DEAL_NAME

    def test_pack_has_generated_at(self):
        assert self.pack.generated_at
        assert "T" in self.pack.generated_at  # ISO format

    def test_pack_has_platform_overview(self):
        po = self.pack.platform_overview
        assert po["legal_name"] == "OPTKAS Sovereign Platform"
        assert "sovereign_platform" in po["entity_type"]

    def test_platform_what_we_do(self):
        items = self.pack.platform_overview.get("what_we_do", [])
        assert len(items) >= 5

    def test_platform_optkas_contributions(self):
        items = self.pack.platform_overview.get("optkas_contributions", [])
        assert len(items) >= 5

    def test_platform_bank_contributions(self):
        items = self.pack.platform_overview.get("bank_contributions", [])
        assert len(items) >= 5

    def test_platform_revenue_sources(self):
        items = self.pack.platform_overview.get("revenue_sources", [])
        assert len(items) >= 3

    def test_platform_technology(self):
        items = self.pack.platform_overview.get("technology", [])
        assert len(items) >= 2
        assert any("XRPL" in i for i in items)

    def test_platform_governance(self):
        items = self.pack.platform_overview.get("governance", [])
        assert len(items) >= 3

    def test_four_entity_standings(self):
        assert len(self.pack.entity_standings) == 4

    def test_issuer_standing(self):
        issuer = self.pack.entity_standings[0]
        assert issuer.legal_name == "TC Advantage Traders, Ltd."
        assert issuer.role_in_deal == "ISSUER"
        assert issuer.jurisdiction == "BS"
        assert issuer.jurisdiction_risk == "MODERATE"

    def test_spv_standing(self):
        spv = self.pack.entity_standings[1]
        assert spv.legal_name == "OPTKAS1-MAIN"
        assert spv.role_in_deal == "SPV"
        assert spv.entity_type == "special_purpose_vehicle"

    def test_platform_standing(self):
        platform = self.pack.entity_standings[2]
        assert platform.legal_name == "OPTKAS Sovereign Platform"
        assert platform.role_in_deal == "PLATFORM"

    def test_investor_standing(self):
        investor = self.pack.entity_standings[3]
        assert investor.legal_name == "Querubin USA, LLC"
        assert investor.role_in_deal == "INVESTOR"

    def test_deal_structure_present(self):
        ds = self.pack.deal_structure
        assert ds is not None
        assert ds.deal_name == DEAL_NAME

    def test_deal_structure_program(self):
        ds = self.pack.deal_structure
        assert "TC Advantage" in ds.program_name
        assert ds.program_size == 5_000_000_000
        assert ds.currency == "USD"
        assert ds.coupon == 5.0

    def test_deal_structure_cusips(self):
        cusips = self.pack.deal_structure.cusips
        assert len(cusips) >= 3
        cusip_ids = [c.get("id") for c in cusips]
        assert "87225HAB4" in cusip_ids

    def test_deal_structure_legal_opinions(self):
        opinions = self.pack.deal_structure.legal_opinions
        assert len(opinions) >= 1
        assert any("Knowles" in o.get("counsel", "") for o in opinions)

    def test_deal_structure_facilities(self):
        facs = self.pack.deal_structure.eligible_facilities
        assert len(facs) >= 3

    def test_dashboard_present(self):
        assert self.pack.dashboard is not None
        assert isinstance(self.pack.dashboard, DealDashboard)

    def test_dashboard_overall_not_red(self):
        assert self.pack.dashboard.overall_rag in ("GREEN", "AMBER")

    def test_forward_path_present(self):
        assert self.pack.forward_path is not None
        assert self.pack.forward_path.total_actions >= 5

    def test_forward_path_three_phases(self):
        assert len(self.pack.forward_path.phases) == 3

    def test_forward_path_has_critical_actions(self):
        assert len(self.pack.forward_path.critical_actions) >= 2

    def test_to_dict_complete(self):
        d = self.pack.to_dict()
        assert "deal_name" in d
        assert "platform_overview" in d
        assert "entity_standings" in d
        assert "deal_structure" in d
        assert "dashboard" in d
        assert "forward_path" in d


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 5: Entity Standing Details
# ══════════════════════════════════════════════════════════════════

class TestEntityStandingDetails:
    """Deep tests for individual entity standings."""

    def setup_method(self):
        self.engine = BriefingPackEngine()

    def test_tc_advantage_strengths(self):
        standing = self.engine._build_entity_standing(TC_ADVANTAGE, "ISSUER")
        assert any("MTN" in s for s in standing.strengths)
        assert any("Insurance" in s or "Lloyd" in s for s in standing.strengths)

    def test_tc_advantage_gaps(self):
        standing = self.engine._build_entity_standing(TC_ADVANTAGE, "ISSUER")
        assert any("banking" in g.lower() or "SWIFT" in g for g in standing.gaps)
        assert any("DRAFT" in g for g in standing.gaps)

    def test_tc_advantage_evidence_strong(self):
        standing = self.engine._build_entity_standing(TC_ADVANTAGE, "ISSUER")
        assert standing.evidence_score == "STRONG"
        assert len(standing.evidence_files) >= 3

    def test_optkas1_spv_characteristics(self):
        standing = self.engine._build_entity_standing(OPTKAS1_SPV, "SPV")
        assert any("SPV" in s or "Bankruptcy" in s for s in standing.strengths)
        assert any("collateral" in s.lower() or "Collateral" in s for s in standing.strengths)

    def test_optkas1_custodian(self):
        standing = self.engine._build_entity_standing(OPTKAS1_SPV, "SPV")
        assert standing.custodian == "Securities Transfer Corporation"
        assert standing.banking_status == "PARTIAL"

    def test_querubin_banking_complete(self):
        standing = self.engine._build_entity_standing(QUERUBIN_USA, "INVESTOR")
        assert standing.banking_status == "COMPLETE"
        assert standing.swift_code == "IRVTUS3N"
        assert "Mellon" in standing.settlement_bank

    def test_querubin_bo_screening_gaps(self):
        standing = self.engine._build_entity_standing(QUERUBIN_USA, "INVESTOR")
        unscreened_gaps = [g for g in standing.gaps if "screened" in g.lower()]
        assert len(unscreened_gaps) >= 2

    def test_querubin_formation_date(self):
        standing = self.engine._build_entity_standing(QUERUBIN_USA, "INVESTOR")
        assert standing.formation_date == "2019-06-06"

    def test_querubin_directors(self):
        standing = self.engine._build_entity_standing(QUERUBIN_USA, "INVESTOR")
        assert len(standing.directors) == 2
        names = [d["name"] for d in standing.directors]
        assert "Domenico Savio Danieli" in names

    def test_platform_jv_strength(self):
        standing = self.engine._build_entity_standing(OPTKAS_PLATFORM, "PLATFORM")
        assert any("JV" in s or "50/50" in s for s in standing.strengths)

    def test_platform_banking_none(self):
        standing = self.engine._build_entity_standing(OPTKAS_PLATFORM, "PLATFORM")
        assert standing.banking_status == "NONE"

    def test_jurisdiction_risk_moderate_bahamas(self):
        standing = self.engine._build_entity_standing(TC_ADVANTAGE, "ISSUER")
        assert standing.jurisdiction_risk == "MODERATE"

    def test_jurisdiction_risk_low_us(self):
        standing = self.engine._build_entity_standing(QUERUBIN_USA, "INVESTOR")
        assert standing.jurisdiction_risk == "LOW"


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 6: Forward Path Analysis
# ══════════════════════════════════════════════════════════════════

class TestForwardPathAnalysis:
    """Tests for forward path generation."""

    def setup_method(self):
        engine = BriefingPackEngine()
        self.pack = engine.build(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            platform_path=OPTKAS_PLATFORM,
            investor_path=QUERUBIN_USA,
        )
        self.fp = self.pack.forward_path

    def test_phase_1_actions_exist(self):
        phase_1 = self.fp.by_phase.get(1, [])
        assert len(phase_1) >= 1

    def test_phase_2_actions_exist(self):
        phase_2 = self.fp.by_phase.get(2, [])
        assert len(phase_2) >= 1

    def test_phase_3_actions_exist(self):
        phase_3 = self.fp.by_phase.get(3, [])
        assert len(phase_3) >= 1

    def test_bo_screening_in_phase_1(self):
        phase_1 = self.fp.by_phase.get(1, [])
        bo_actions = [a for a in phase_1 if "screening" in a.description.lower()]
        assert len(bo_actions) >= 2  # Both Querubin BOs

    def test_banking_in_phase_2(self):
        phase_2 = self.fp.by_phase.get(2, [])
        banking_actions = [a for a in phase_2 if a.category == "BANKING"]
        assert len(banking_actions) >= 1

    def test_signing_in_phase_3(self):
        phase_3 = self.fp.by_phase.get(3, [])
        signing = [a for a in phase_3 if "signing" in a.description.lower()]
        assert len(signing) >= 1

    def test_escrow_in_phase_3(self):
        phase_3 = self.fp.by_phase.get(3, [])
        escrow = [a for a in phase_3 if "escrow" in a.description.lower()]
        assert len(escrow) >= 1

    def test_all_actions_have_responsible(self):
        for a in self.fp.actions:
            assert a.responsible

    def test_all_actions_have_priority(self):
        for a in self.fp.actions:
            assert a.priority in ("CRITICAL", "HIGH", "MEDIUM")

    def test_critical_actions_are_critical(self):
        for a in self.fp.critical_actions:
            assert a.priority == "CRITICAL"

    def test_phase_timelines(self):
        for phase in self.fp.phases:
            assert "name" in phase
            assert "target" in phase
            assert "timeline" in phase

    def test_legal_opinion_action_in_progress(self):
        legal = [a for a in self.fp.actions if a.category == "LEGAL"]
        if legal:
            # Draft opinion should be IN_PROGRESS
            assert any(a.status == "IN_PROGRESS" for a in legal)


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 7: Markdown Rendering
# ══════════════════════════════════════════════════════════════════

class TestMarkdownRendering:
    """Tests for briefing pack Markdown output."""

    def setup_method(self):
        engine = BriefingPackEngine()
        self.pack = engine.build(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            platform_path=OPTKAS_PLATFORM,
            investor_path=QUERUBIN_USA,
        )
        self.md = self.pack.render_markdown()

    def test_has_header(self):
        assert "OPTKAS SOVEREIGN CAPITAL MARKETS" in self.md

    def test_has_deal_name(self):
        assert DEAL_NAME in self.md

    def test_has_platform_section(self):
        assert "1. PLATFORM OVERVIEW" in self.md
        assert "WHAT IS OPTKAS?" in self.md

    def test_has_entity_standings_section(self):
        assert "2. ENTITY STANDINGS" in self.md
        assert "WHERE EVERYONE STANDS" in self.md

    def test_has_deal_structure_section(self):
        assert "3. DEAL STRUCTURE" in self.md

    def test_has_dashboard_section(self):
        assert "4. CURRENT STATUS" in self.md

    def test_has_forward_path_section(self):
        assert "5. FORWARD PATH" in self.md

    def test_entity_names_in_markdown(self):
        assert "TC Advantage Traders, Ltd." in self.md
        assert "OPTKAS1-MAIN" in self.md
        assert "OPTKAS Sovereign Platform" in self.md
        assert "Querubin USA, LLC" in self.md

    def test_cusips_in_markdown(self):
        assert "87225HAB4" in self.md

    def test_insurance_in_markdown(self):
        assert "625" in self.md
        assert "Lloyd" in self.md

    def test_swift_in_markdown(self):
        assert "IRVTUS3N" in self.md

    def test_bo_screening_in_markdown(self):
        assert "NOT SCREENED" in self.md

    def test_phase_labels_in_markdown(self):
        assert "PHASE 1" in self.md
        assert "PHASE 2" in self.md
        assert "PHASE 3" in self.md

    def test_markdown_length(self):
        lines = self.md.split("\n")
        assert len(lines) >= 200  # Should be a substantial document

    def test_ends_with_footer(self):
        assert "END OF BRIEFING PACK" in self.md


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 8: Save & Serialization
# ══════════════════════════════════════════════════════════════════

class TestSaveAndSerialization:
    """Tests for briefing pack save functionality."""

    def setup_method(self):
        self.engine = BriefingPackEngine()
        self.pack = self.engine.build(
            deal_name=DEAL_NAME,
            issuer_path=TC_ADVANTAGE,
            spv_path=OPTKAS1_SPV,
            platform_path=OPTKAS_PLATFORM,
            investor_path=QUERUBIN_USA,
        )

    def test_save(self, tmp_path, monkeypatch):
        import engine.briefing_pack as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pack)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_json_parseable(self, tmp_path, monkeypatch):
        import engine.briefing_pack as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pack)
        data = json.loads(path.read_text())
        assert data["deal_name"] == DEAL_NAME

    def test_save_markdown_file(self, tmp_path, monkeypatch):
        import engine.briefing_pack as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pack)
        md_path = path.with_suffix(".md")
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "EXECUTIVE BRIEFING PACK" in content

    def test_json_has_all_sections(self, tmp_path, monkeypatch):
        import engine.briefing_pack as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pack)
        data = json.loads(path.read_text())
        assert "platform_overview" in data
        assert "entity_standings" in data
        assert "deal_structure" in data
        assert "dashboard" in data
        assert "forward_path" in data

    def test_json_entity_standings_count(self, tmp_path, monkeypatch):
        import engine.briefing_pack as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pack)
        data = json.loads(path.read_text())
        assert len(data["entity_standings"]) == 4

    def test_json_forward_path_actions(self, tmp_path, monkeypatch):
        import engine.briefing_pack as mod
        monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path)
        path = self.engine.save(self.pack)
        data = json.loads(path.read_text())
        assert len(data["forward_path"]["actions"]) >= 5


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 9: Edge Cases
# ══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Tests for edge cases and partial inputs."""

    def test_no_entities(self):
        engine = BriefingPackEngine()
        pack = engine.build(deal_name="Empty Deal")
        assert pack.deal_name == "Empty Deal"
        assert len(pack.entity_standings) == 0

    def test_only_issuer(self):
        engine = BriefingPackEngine()
        pack = engine.build(
            deal_name="Issuer Only",
            issuer_path=TC_ADVANTAGE,
        )
        assert len(pack.entity_standings) == 1
        assert pack.entity_standings[0].role_in_deal == "ISSUER"

    def test_cuerpo_markets_entity(self):
        engine = BriefingPackEngine()
        standing = engine._build_entity_standing(CUERPO_MARKETS, "PLATFORM")
        assert standing.legal_name == "Cuerpo Markets"
        assert standing.entity_type == "sovereign_platform"

    def test_render_with_no_dashboard(self):
        pack = BriefingPack(deal_name="No Dashboard")
        md = pack.render_markdown()
        assert "DEAL DASHBOARD" in md  # Section header exists

    def test_render_with_no_forward_path(self):
        pack = BriefingPack(deal_name="No Path")
        md = pack.render_markdown()
        assert "FORWARD PATH" in md  # Section header exists


# ══════════════════════════════════════════════════════════════════
# TEST CLASS 10: CLI Commands
# ══════════════════════════════════════════════════════════════════

class TestCLICommands:
    """Tests for briefing pack CLI commands."""

    def test_briefing_pack_command_exists(self):
        from engine.cli import main
        cmds = {c.name for c in main.commands.values()}
        assert "briefing-pack" in cmds

    def test_entity_standing_command_exists(self):
        from engine.cli import main
        cmds = {c.name for c in main.commands.values()}
        assert "entity-standing" in cmds

    def test_forward_path_command_exists(self):
        from engine.cli import main
        cmds = {c.name for c in main.commands.values()}
        assert "forward-path" in cmds

    def test_total_commands_43(self):
        """We should now have 43 CLI commands."""
        from engine.cli import main
        cmds = list(main.commands.keys())
        assert len(cmds) >= 43
