"""
Deal Dashboard Engine
========================
Unified deal status dashboard that aggregates output from ALL
analysis engines into a single institutional-grade status view.

This is the command a managing director runs to see:
  "Where does this deal stand, end to end?"

Pulls from:
  - MTN Validation (program readiness)
  - Collateral Verification (asset integrity)
  - Deal Readiness (aggregate readiness)
  - Deal Governance (framework compliance)
  - Risk Score (counterparty risk)
  - Closing Tracker (conditions precedent)
  - Settlement Path (banking rails)
  - Settlement Onboarding (banking readiness)
  - Wire Instructions (payment readiness)
  - Signing Ceremony (execution status)

Output: Single unified DealDashboard with section-by-section
        RAG status (Red/Amber/Green) and executive summary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import load_entity
from engine.mtn_validator import MTNProgramValidator
from engine.collateral_verifier import CollateralVerifier
from engine.deal_readiness import DealReadinessEngine
from engine.deal_governance import DealGovernanceEngine
from engine.risk_scorer import CounterpartyRiskEngine
from engine.closing_tracker import ClosingTrackerEngine
from engine.settlement_onboarding import SettlementOnboardingEngine
from engine.correspondent_banking import CorrespondentBankingEngine
from engine.escrow_engine import EscrowEngine
from engine.banking_resolver import BankingResolverEngine
from engine.cp_resolution import CPResolutionEngine


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "dashboards"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class DashboardSection:
    """One section of the deal dashboard."""
    name: str
    rag: str = "GREY"  # RED, AMBER, GREEN, GREY (not assessed)
    score: float | None = None
    max_score: float | None = None
    headline: str = ""
    details: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    @property
    def pct(self) -> float | None:
        if self.score is not None and self.max_score and self.max_score > 0:
            return round(self.score / self.max_score * 100, 1)
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "rag": self.rag,
            "score": self.score,
            "max_score": self.max_score,
            "percentage": self.pct,
            "headline": self.headline,
            "details": self.details,
            "action_items": self.action_items,
        }


@dataclass
class DealDashboard:
    """Complete unified deal dashboard."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    entities: list[str] = field(default_factory=list)
    sections: list[DashboardSection] = field(default_factory=list)

    @property
    def overall_rag(self) -> str:
        """Overall RAG: RED if any RED, AMBER if any AMBER, GREEN if all GREEN."""
        rags = [s.rag for s in self.sections if s.rag != "GREY"]
        if not rags:
            return "GREY"
        if "RED" in rags:
            return "RED"
        if "AMBER" in rags:
            return "AMBER"
        return "GREEN"

    @property
    def green_count(self) -> int:
        return sum(1 for s in self.sections if s.rag == "GREEN")

    @property
    def amber_count(self) -> int:
        return sum(1 for s in self.sections if s.rag == "AMBER")

    @property
    def red_count(self) -> int:
        return sum(1 for s in self.sections if s.rag == "RED")

    @property
    def total_sections(self) -> int:
        return len(self.sections)

    @property
    def all_action_items(self) -> list[str]:
        items = []
        for s in self.sections:
            for ai in s.action_items:
                items.append(f"[{s.name}] {ai}")
        return items

    def summary(self) -> str:
        rag_icon = {"RED": "[X]", "AMBER": "[~]", "GREEN": "[+]", "GREY": "[-]"}

        lines = [
            "=" * 70,
            "DEAL DASHBOARD",
            f"  {self.deal_name}",
            f"  Generated: {self.created_at}",
            "=" * 70,
            "",
            f"  OVERALL STATUS:  {self.overall_rag}",
            f"  Green: {self.green_count}  |  Amber: {self.amber_count}  |  "
            f"Red: {self.red_count}  |  Grey: "
            f"{self.total_sections - self.green_count - self.amber_count - self.red_count}",
            f"  Entities:  {len(self.entities)}",
            "",
            "=" * 70,
        ]

        for section in self.sections:
            icon = rag_icon.get(section.rag, "[ ]")
            pct_str = f"  ({section.pct:.0f}%)" if section.pct is not None else ""
            score_str = ""
            if section.score is not None and section.max_score is not None:
                score_str = f"  [{section.score}/{section.max_score}]"

            lines.append(f"  {icon} {section.name}{score_str}{pct_str}")
            lines.append(f"      {section.headline}")

            for detail in section.details[:5]:
                lines.append(f"      - {detail}")

            if section.action_items:
                for ai in section.action_items[:3]:
                    lines.append(f"      ACTION: {ai}")

            lines.append("")

        # Executive summary
        all_actions = self.all_action_items
        if all_actions:
            lines.append("--- EXECUTIVE ACTION ITEMS ---")
            for i, action in enumerate(all_actions, 1):
                lines.append(f"  {i}. {action}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "overall_rag": self.overall_rag,
            "entities": self.entities,
            "green": self.green_count,
            "amber": self.amber_count,
            "red": self.red_count,
            "sections": [s.to_dict() for s in self.sections],
            "action_items": self.all_action_items,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DealDashboardEngine:
    """
    Generates a unified deal dashboard from all analysis engines.

    Usage:
        engine = DealDashboardEngine()
        dashboard = engine.generate(
            deal_name="OPTKAS-TC Full Deal",
            issuer_path=Path("data/entities/tc_advantage_traders.yaml"),
            spv_path=Path("data/entities/optkas1_spv.yaml"),
            additional_entities=[
                Path("data/entities/optkas_platform.yaml"),
                Path("data/entities/querubin_usa.yaml"),
            ],
        )
        print(dashboard.summary())
    """

    def generate(
        self,
        deal_name: str,
        issuer_path: Path | None = None,
        spv_path: Path | None = None,
        additional_entities: list[Path] | None = None,
    ) -> DealDashboard:
        """Generate comprehensive deal dashboard."""
        dashboard = DealDashboard(deal_name=deal_name)

        # Collect all entity paths
        all_paths: list[Path] = []
        if issuer_path:
            all_paths.append(issuer_path)
        if spv_path:
            all_paths.append(spv_path)
        for ep in (additional_entities or []):
            all_paths.append(ep)

        # Load entity names
        for ep in all_paths:
            try:
                e = load_entity(ep)
                dashboard.entities.append(e.get("legal_name", str(ep)))
            except Exception:
                dashboard.entities.append(str(ep))

        # Run each assessment
        dashboard.sections.append(self._assess_mtn(issuer_path))
        dashboard.sections.append(self._assess_collateral(issuer_path, spv_path))
        dashboard.sections.append(
            self._assess_readiness(deal_name, issuer_path, spv_path, additional_entities)
        )
        dashboard.sections.append(self._assess_governance(deal_name, all_paths))
        dashboard.sections.append(self._assess_risk(deal_name, all_paths))
        dashboard.sections.append(
            self._assess_closing(deal_name, issuer_path, spv_path, additional_entities)
        )
        dashboard.sections.append(
            self._assess_settlement_enhanced(deal_name, all_paths)
        )
        dashboard.sections.append(
            self._assess_onboarding_enhanced(deal_name, all_paths)
        )
        dashboard.sections.append(
            self._assess_escrow(deal_name, all_paths)
        )
        dashboard.sections.append(
            self._assess_cp_resolution(
                deal_name, issuer_path, spv_path, additional_entities
            )
        )

        return dashboard

    # ------------------------------------------------------------------
    # Section assessors
    # ------------------------------------------------------------------

    def _assess_mtn(self, issuer_path: Path | None) -> DashboardSection:
        """MTN Program Validation section."""
        section = DashboardSection(name="MTN Program")
        if not issuer_path:
            section.rag = "GREY"
            section.headline = "No issuer specified."
            return section

        try:
            issuer = load_entity(issuer_path)
            validator = MTNProgramValidator()
            report = validator.validate(issuer)
            pct = report.score  # score is already a percentage
            section.score = pct
            section.max_score = 100

            if pct >= 90:
                section.rag = "GREEN"
                section.headline = f"MTN program validated at {pct:.0f}%."
            elif pct >= 70:
                section.rag = "AMBER"
                section.headline = f"MTN program has warnings ({pct:.0f}%)."
            else:
                section.rag = "RED"
                section.headline = f"MTN program has critical issues ({pct:.0f}%)."

            fails = [c for c in report.items if c.status == "FAIL"]
            warns = [c for c in report.items if c.status == "WARN"]
            if fails:
                section.details.append(f"{len(fails)} FAIL check(s)")
                for f in fails[:3]:
                    section.action_items.append(f"MTN: {f.detail}")
            if warns:
                section.details.append(f"{len(warns)} WARN check(s)")

            section.details.append(f"{report.pass_count} PASS checks")

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_collateral(
        self, issuer_path: Path | None, spv_path: Path | None,
    ) -> DashboardSection:
        """Collateral Verification section."""
        section = DashboardSection(name="Collateral")
        if not issuer_path or not spv_path:
            section.rag = "GREY"
            section.headline = "Issuer or SPV not specified."
            return section

        try:
            issuer = load_entity(issuer_path)
            spv = load_entity(spv_path)
            verifier = CollateralVerifier()
            report = verifier.verify(spv, issuer)
            pct = report.score  # score is already a percentage
            section.score = pct
            section.max_score = 100

            if pct >= 90:
                section.rag = "GREEN"
                section.headline = f"Collateral verified at {pct:.0f}%."
            elif pct >= 70:
                section.rag = "AMBER"
                section.headline = f"Collateral has warnings ({pct:.0f}%)."
            else:
                section.rag = "RED"
                section.headline = f"Collateral has critical issues ({pct:.0f}%)."

            fails = [c for c in report.items if c.status == "FAIL"]
            if fails:
                for f in fails[:3]:
                    section.action_items.append(f"Collateral: {f.detail}")

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_readiness(
        self, deal_name: str, issuer_path: Path | None,
        spv_path: Path | None, extra: list[Path] | None,
    ) -> DashboardSection:
        """Deal Readiness section."""
        section = DashboardSection(name="Deal Readiness")

        try:
            engine = DealReadinessEngine()
            report = engine.assess(
                deal_name=deal_name,
                issuer_path=issuer_path,
                spv_path=spv_path,
                additional_entities=extra,
            )

            verdict = report.verdict
            if verdict == "READY":
                section.rag = "GREEN"
            elif verdict == "CONDITIONAL":
                section.rag = "AMBER"
            else:
                section.rag = "RED"

            section.headline = f"Verdict: {verdict}  |  Score: {report.overall_score:.0f}%"
            section.score = report.overall_score
            section.max_score = 100

            if report.blockers:
                section.details.append(f"{len(report.blockers)} blocker(s)")
            if report.action_items:
                section.details.append(f"{len(report.action_items)} action item(s)")
                for ai in report.action_items[:3]:
                    section.action_items.append(ai)

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_governance(
        self, deal_name: str, all_paths: list[Path],
    ) -> DashboardSection:
        """Governance Framework section."""
        section = DashboardSection(name="Governance")

        try:
            engine = DealGovernanceEngine()
            report = engine.assess(
                deal_name=deal_name,
                entity_paths=all_paths if all_paths else None,
            )

            section.score = report.score
            section.max_score = 100

            if report.grade in ("A", "B"):
                section.rag = "GREEN"
            elif report.grade == "C":
                section.rag = "AMBER"
            else:
                section.rag = "RED"

            section.headline = (
                f"Grade: {report.grade}  |  Score: {report.score:.0f}%  |  "
                f"Compliant: {'YES' if report.is_compliant else 'NO'}"
            )

            if report.conflicts:
                section.details.append(f"{len(report.conflicts)} authority conflict(s)")
            if report.gaps:
                section.details.append(f"{len(report.gaps)} governance gap(s)")
                for gap in report.gaps[:3]:
                    section.action_items.append(f"Governance: {gap.description}")

            section.details.append(f"{len(report.authority_map)} person(s) in authority map")

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_risk(
        self, deal_name: str, all_paths: list[Path],
    ) -> DashboardSection:
        """Counterparty Risk section."""
        section = DashboardSection(name="Risk Score")

        try:
            engine = CounterpartyRiskEngine()
            report = engine.score(
                deal_name=deal_name,
                entity_paths=all_paths if all_paths else None,
            )

            section.score = report.total_score
            section.max_score = report.max_score

            if report.grade in ("A",):
                section.rag = "GREEN"
            elif report.grade in ("B", "C"):
                section.rag = "AMBER"
            else:
                section.rag = "RED"

            section.headline = (
                f"Score: {report.total_score}/{report.max_score}  |  "
                f"Grade: {report.grade}  |  Risk: {report.risk_level}"
            )

            if report.flags:
                section.details.append(f"{len(report.flags)} risk flag(s)")
                for flag in report.flags[:2]:
                    section.action_items.append(f"Risk: {flag}")

            if report.mitigants:
                section.details.append(f"{len(report.mitigants)} mitigant(s)")

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_closing(
        self, deal_name: str, issuer_path: Path | None,
        spv_path: Path | None, extra: list[Path] | None,
    ) -> DashboardSection:
        """Closing Conditions section — uses CP Resolution for auto-resolution."""
        section = DashboardSection(name="Closing Conditions")

        try:
            # Use CP Resolution engine which auto-resolves CPs
            cp_engine = CPResolutionEngine()
            report = cp_engine.resolve(
                deal_name=deal_name,
                issuer_path=issuer_path,
                spv_path=spv_path,
                additional_entities=extra,
            )

            tracker = report.tracker
            section.score = tracker.resolved
            section.max_score = tracker.total

            if tracker.closing_ready:
                section.rag = "GREEN"
            elif tracker.completion_pct >= 50:
                section.rag = "AMBER"
            elif tracker.completion_pct > 0:
                section.rag = "AMBER"
            else:
                section.rag = "RED"

            section.headline = (
                f"Completion: {tracker.completion_pct:.0f}%  |  "
                f"Signing: {'READY' if tracker.signing_ready else 'NOT READY'}  |  "
                f"Closing: {'READY' if tracker.closing_ready else 'NOT READY'}"
            )

            section.details.append(
                f"{tracker.total} CP(s): {tracker.satisfied} satisfied, "
                f"{tracker.in_progress} in progress, "
                f"{tracker.open} open, {tracker.blocked} blocked"
            )

            if report.auto_resolved > 0:
                section.details.append(
                    f"{report.auto_resolved} CP(s) auto-resolved from evidence/data"
                )

            if tracker.overdue:
                section.action_items.append(f"{tracker.overdue} overdue condition(s)")

            # Add unresolved CPs as action items
            for cp in tracker.conditions:
                if not cp.is_resolved:
                    section.action_items.append(f"CP {cp.cp_id}: {cp.description[:60]}")
                    if len(section.action_items) >= 5:
                        break

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_settlement(self, all_paths: list[Path]) -> DashboardSection:
        """Settlement Path section."""
        section = DashboardSection(name="Settlement")

        if len(all_paths) < 2:
            section.rag = "GREY"
            section.headline = "Need at least 2 entities for settlement path."
            return section

        try:
            engine = CorrespondentBankingEngine()
            e1 = load_entity(all_paths[0])
            e2 = load_entity(all_paths[1])
            path = engine.resolve_settlement_path(e1, e2)

            if path.is_valid:
                section.rag = "GREEN"
                section.headline = (
                    f"Settlement path valid. {len(path.nodes)} nodes. "
                    f"FX: {'YES' if path.requires_fx else 'NO'}."
                )
            else:
                section.rag = "RED"
                section.headline = (
                    f"Settlement path INVALID. {len(path.nodes)} nodes. "
                    f"{len(path.validation_issues)} issue(s)."
                )
                for issue in path.validation_issues:
                    section.action_items.append(f"Settlement: {issue}")

            for note in path.validation_notes[:3]:
                section.details.append(note)

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_onboarding(
        self, deal_name: str, all_paths: list[Path],
    ) -> DashboardSection:
        """Settlement Onboarding section."""
        section = DashboardSection(name="Banking Onboarding")

        try:
            engine = SettlementOnboardingEngine()
            plan = engine.assess(
                deal_name=deal_name,
                entity_paths=all_paths if all_paths else None,
            )

            if plan.settlement_ready:
                section.rag = "GREEN"
                section.headline = "All entities settlement-ready."
            elif plan.needs_onboarding > 0:
                section.rag = "RED"
                section.headline = (
                    f"{plan.needs_onboarding} entity(ies) need banking onboarding."
                )
                for p in plan.profiles:
                    if p.status == "NEEDS_ONBOARDING":
                        section.action_items.append(
                            f"Onboard {p.entity_name}: "
                            f"missing {', '.join(p.missing)}"
                        )
            else:
                section.rag = "AMBER"
                section.headline = f"{plan.partial} entity(ies) partially onboarded."

            section.details.append(
                f"Complete: {plan.complete}  |  Partial: {plan.partial}  |  "
                f"Needs Onboarding: {plan.needs_onboarding}"
            )
            section.score = plan.complete
            section.max_score = plan.total_entities

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_settlement_enhanced(
        self, deal_name: str, all_paths: list[Path],
    ) -> DashboardSection:
        """Settlement Path section — enhanced with escrow engine."""
        section = DashboardSection(name="Settlement")

        if len(all_paths) < 2:
            section.rag = "GREY"
            section.headline = "Need at least 2 entities for settlement path."
            return section

        try:
            engine = EscrowEngine()
            plan = engine.build(
                deal_name=deal_name,
                entity_paths=all_paths,
                escrow_currency="USD",
            )

            if plan.overall_valid:
                section.rag = "GREEN"
                section.headline = (
                    f"Settlement rails valid. {plan.total_legs} leg(s), "
                    f"{plan.total_nodes} nodes. Escrow: "
                    f"{plan.escrow_terms.escrow_agent if plan.escrow_terms else 'TBD'}."
                )
            else:
                # Has legs but with issues — AMBER if legs exist, RED if none
                if plan.valid_legs > 0:
                    section.rag = "AMBER"
                    section.headline = (
                        f"{plan.valid_legs}/{plan.total_legs} legs valid. "
                        f"{len(plan.overall_issues)} issue(s) remaining."
                    )
                else:
                    section.rag = "AMBER"
                    section.headline = (
                        f"Escrow plan built. {plan.total_legs} leg(s), "
                        f"{plan.total_nodes} nodes. "
                        f"{len(plan.overall_issues)} issue(s) to resolve."
                    )

            section.score = plan.valid_legs
            section.max_score = plan.total_legs if plan.total_legs > 0 else 1

            if plan.escrow_terms:
                section.details.append(
                    f"Escrow: {plan.escrow_terms.escrow_agent} "
                    f"[{plan.escrow_terms.escrow_agent_swift}]"
                )

            for issue in plan.overall_issues[:3]:
                section.action_items.append(f"Settlement: {issue}")

            for rec in plan.recommendations[:2]:
                section.details.append(rec)

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_onboarding_enhanced(
        self, deal_name: str, all_paths: list[Path],
    ) -> DashboardSection:
        """Banking Onboarding section — enhanced with banking resolver."""
        section = DashboardSection(name="Banking Onboarding")

        try:
            engine = BankingResolverEngine()
            plan = engine.resolve(
                deal_name=deal_name,
                entity_paths=all_paths if all_paths else None,
            )

            if plan.all_resolved:
                section.rag = "GREEN"
                section.headline = (
                    f"All {plan.total_entities} entities have resolved banking."
                )
            elif plan.critical_entities == 0:
                section.rag = "AMBER"
                section.headline = (
                    f"{plan.fully_resolved}/{plan.total_entities} resolved. "
                    f"{plan.total_gaps} minor gap(s)."
                )
            else:
                section.rag = "AMBER"
                section.headline = (
                    f"{plan.fully_resolved}/{plan.total_entities} resolved. "
                    f"{plan.total_critical} critical gap(s). "
                    f"Recommended banks assigned."
                )

            section.score = plan.fully_resolved
            section.max_score = plan.total_entities

            section.details.append(
                f"Resolved: {plan.fully_resolved}  |  "
                f"Critical: {plan.critical_entities}  |  "
                f"Gaps: {plan.total_gaps}"
            )

            for p in plan.profiles:
                if p.status == "CRITICAL_GAPS":
                    section.action_items.append(
                        f"Onboard {p.entity_name} with "
                        f"{p.resolved_bank} [{p.resolved_swift}]"
                    )

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_escrow(
        self, deal_name: str, all_paths: list[Path],
    ) -> DashboardSection:
        """Escrow Arrangement section."""
        section = DashboardSection(name="Escrow")

        if len(all_paths) < 2:
            section.rag = "GREY"
            section.headline = "Need at least 2 entities for escrow."
            return section

        try:
            engine = EscrowEngine()
            plan = engine.build(
                deal_name=deal_name,
                entity_paths=all_paths,
                escrow_currency="USD",
            )

            # Auto-satisfy escrow conditions from evidence/entity data
            engine.auto_satisfy_conditions(plan, entity_paths=all_paths)

            if plan.escrow_terms:
                et = plan.escrow_terms
                section.score = et.met_count
                section.max_score = len(et.conditions)

                if et.all_conditions_met:
                    section.rag = "GREEN"
                    section.headline = (
                        f"Escrow ready. Agent: {et.escrow_agent}. "
                        f"All {len(et.conditions)} conditions met."
                    )
                elif et.met_count > 0:
                    section.rag = "AMBER"
                    section.headline = (
                        f"Escrow: {et.escrow_agent}. "
                        f"{et.met_count}/{len(et.conditions)} conditions met."
                    )
                else:
                    section.rag = "AMBER"
                    section.headline = (
                        f"Escrow agent selected: {et.escrow_agent} "
                        f"[{et.escrow_agent_swift}]. "
                        f"{et.pending_count} conditions pending."
                    )

                section.details.append(
                    f"Currency: {et.escrow_currency} | "
                    f"Type: {et.escrow_type} | "
                    f"Release: {et.release_mechanism}"
                )

                for cond in et.conditions:
                    if not cond.is_met:
                        section.action_items.append(
                            f"Escrow {cond.condition_id}: {cond.description[:50]}"
                        )
                        if len(section.action_items) >= 3:
                            break
            else:
                section.rag = "RED"
                section.headline = "No escrow arrangement could be established."

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def _assess_cp_resolution(
        self, deal_name: str, issuer_path: Path | None,
        spv_path: Path | None, extra: list[Path] | None,
    ) -> DashboardSection:
        """CP Resolution section — auto-resolved closing conditions."""
        section = DashboardSection(name="CP Resolution")

        try:
            engine = CPResolutionEngine()
            report = engine.resolve(
                deal_name=deal_name,
                issuer_path=issuer_path,
                spv_path=spv_path,
                additional_entities=extra,
            )

            section.score = report.auto_resolved + report.satisfied
            section.max_score = report.total_cps

            if report.remaining_open == 0:
                section.rag = "GREEN"
                section.headline = (
                    f"All {report.total_cps} CPs resolved or in progress."
                )
            elif report.resolution_pct >= 50:
                section.rag = "AMBER"
                section.headline = (
                    f"{report.resolution_pct:.0f}% resolved. "
                    f"{report.auto_resolved} auto-resolved, "
                    f"{report.remaining_open} open."
                )
            else:
                section.rag = "AMBER"
                section.headline = (
                    f"{report.resolution_pct:.0f}% resolved. "
                    f"{report.remaining_open} CPs still open."
                )

            section.details.append(
                f"Total: {report.total_cps} | Satisfied: {report.satisfied} | "
                f"In Progress: {report.moved_to_in_progress} | "
                f"Open: {report.remaining_open}"
            )

            # List remaining open CPs as action items
            for r in report.resolutions:
                if r.new_status == "OPEN":
                    section.action_items.append(
                        f"CP {r.cp_id}: {r.description[:50]}"
                    )
                    if len(section.action_items) >= 3:
                        break

        except Exception as exc:
            section.rag = "RED"
            section.headline = f"Error: {exc}"

        return section

    def save(self, dashboard: DealDashboard) -> Path:
        """Persist dashboard to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = dashboard.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"dashboard_{name}_{ts}.json"
        path.write_text(
            json.dumps(dashboard.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path
