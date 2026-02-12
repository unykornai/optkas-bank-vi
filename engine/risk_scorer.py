"""
Counterparty Risk Scoring Engine
==================================
Quantitative multi-factor risk model for counterparty assessment
at the deal-group level.

Unlike the DossierBuilder (which builds per-entity profiles), this
engine scores risk ACROSS the entire deal group:

  Factor 1: Jurisdiction Risk       (0-20)  - Political stability, AML regime, treaty network
  Factor 2: Documentation Score     (0-20)  - Evidence completeness, opinion coverage, insurance
  Factor 3: Concentration Risk      (0-20)  - Single-counterparty exposure, cross-entity dependencies
  Factor 4: Regulatory Exposure     (0-20)  - Licensing gaps, regulatory status, sanctions proximity
  Factor 5: Settlement Complexity   (0-20)  - Banking chain length, FX risk, correspondent depth

Total: 0-100. Grade: A (85+) / B (70+) / C (50+) / D (30+) / F (<30)

Each factor produces sub-scores and explanatory detail so the output
is not a black box — every point is traceable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import load_entity
from engine.correspondent_banking import CorrespondentBankingEngine
from engine.jurisdiction_intel import JurisdictionIntelEngine


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "risk_scores"
EVIDENCE_DIR = ROOT_DIR / "data" / "evidence"

# Jurisdictions with heightened risk (not blocked, just elevated monitoring)
ELEVATED_RISK_JURISDICTIONS = {
    "VN": {"level": "MEDIUM", "reason": "FX controls, limited treaty network"},
    "CN": {"level": "HIGH", "reason": "Capital controls, SAFE approval required"},
    "RU": {"level": "HIGH", "reason": "Sanctions exposure, restricted correspondent banking"},
    "IR": {"level": "CRITICAL", "reason": "Comprehensive sanctions regime"},
    "KP": {"level": "CRITICAL", "reason": "Comprehensive sanctions regime"},
    "CU": {"level": "HIGH", "reason": "US embargo, limited banking access"},
    "VE": {"level": "HIGH", "reason": "Sanctions, currency instability"},
}

# Jurisdictions with strong regulatory frameworks (favorable)
STRONG_REGULATORY_JURISDICTIONS = {
    "US", "GB", "DE", "FR", "CH", "SG", "HK", "JP", "CA", "AU",
    "NL", "LU", "IE", "AT", "DK", "SE", "NO", "FI", "NZ",
}

# SPV-friendly jurisdictions
SPV_FAVORABLE = {"US-WY", "US-DE", "US-NV", "KY", "BM", "IE", "LU", "JE", "GG"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class RiskFactor:
    """A single scored risk factor with breakdown."""
    name: str
    max_score: int = 20
    raw_score: float = 0.0
    components: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return min(self.max_score, max(0.0, self.raw_score))

    @property
    def pct(self) -> float:
        return round(self.score / self.max_score * 100, 1) if self.max_score else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "max_score": self.max_score,
            "percentage": self.pct,
            "components": self.components,
            "notes": self.notes,
        }


@dataclass
class CounterpartyRiskReport:
    """Complete multi-factor risk assessment."""
    deal_name: str
    assessed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    entities: list[str] = field(default_factory=list)
    factors: list[RiskFactor] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # Risk flags
    mitigants: list[str] = field(default_factory=list)  # Positive factors

    @property
    def total_score(self) -> float:
        return round(sum(f.score for f in self.factors), 1)

    @property
    def max_score(self) -> float:
        return sum(f.max_score for f in self.factors)

    @property
    def grade(self) -> str:
        s = self.total_score
        if s >= 85:
            return "A"
        if s >= 70:
            return "B"
        if s >= 50:
            return "C"
        if s >= 30:
            return "D"
        return "F"

    @property
    def risk_level(self) -> str:
        g = self.grade
        if g == "A":
            return "LOW"
        if g == "B":
            return "MODERATE"
        if g == "C":
            return "ELEVATED"
        if g == "D":
            return "HIGH"
        return "CRITICAL"

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "COUNTERPARTY RISK ASSESSMENT",
            f"  {self.deal_name}",
            f"  Assessed: {self.assessed_at}",
            "=" * 70,
            "",
            f"  SCORE:      {self.total_score}/{self.max_score}",
            f"  GRADE:      {self.grade}",
            f"  RISK LEVEL: {self.risk_level}",
            f"  Entities:   {len(self.entities)}",
            "",
            "--- FACTOR BREAKDOWN ---",
        ]

        for f in self.factors:
            bar_len = int(f.pct / 5)  # 20 char max
            bar = "#" * bar_len + "." * (20 - bar_len)
            lines.append(
                f"  {f.name:<25s} {f.score:>5.1f}/{f.max_score:<3d}  "
                f"[{bar}] {f.pct:.0f}%"
            )
            for note in f.notes[:3]:
                lines.append(f"    {note}")

        if self.flags:
            lines.append("")
            lines.append("--- RISK FLAGS ---")
            for flag in self.flags:
                lines.append(f"  [!] {flag}")

        if self.mitigants:
            lines.append("")
            lines.append("--- MITIGANTS ---")
            for m in self.mitigants:
                lines.append(f"  [+] {m}")

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "assessed_at": self.assessed_at,
            "total_score": self.total_score,
            "max_score": self.max_score,
            "grade": self.grade,
            "risk_level": self.risk_level,
            "entities": self.entities,
            "factors": [f.to_dict() for f in self.factors],
            "flags": self.flags,
            "mitigants": self.mitigants,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CounterpartyRiskEngine:
    """
    Scores deal-group counterparty risk across 5 quantitative factors.

    Usage:
        engine = CounterpartyRiskEngine()
        report = engine.score(
            deal_name="OPTKAS-TC Deal Group",
            entity_paths=[
                Path("data/entities/tc_advantage_traders.yaml"),
                Path("data/entities/optkas1_spv.yaml"),
            ],
        )
        print(report.summary())
    """

    def __init__(self) -> None:
        self.banking_engine = CorrespondentBankingEngine()
        self.jurisdiction_engine = JurisdictionIntelEngine()

    def score(
        self,
        deal_name: str,
        entity_paths: list[Path] | None = None,
    ) -> CounterpartyRiskReport:
        """Compute multi-factor risk score."""
        report = CounterpartyRiskReport(deal_name=deal_name)
        entities: list[dict] = []

        for ep in (entity_paths or []):
            e = load_entity(ep)
            entities.append(e)
            report.entities.append(e.get("legal_name", str(ep)))

        # Score each factor
        report.factors.append(self._score_jurisdiction(entities, report))
        report.factors.append(self._score_documentation(entities, report))
        report.factors.append(self._score_concentration(entities, report))
        report.factors.append(self._score_regulatory(entities, report))
        report.factors.append(self._score_settlement(entities, report))

        return report

    # ------------------------------------------------------------------
    # Factor 1: Jurisdiction Risk (0-20)
    # ------------------------------------------------------------------

    def _score_jurisdiction(
        self, entities: list[dict], report: CounterpartyRiskReport,
    ) -> RiskFactor:
        factor = RiskFactor(name="Jurisdiction Risk", max_score=20)
        if not entities:
            factor.raw_score = 10
            factor.notes.append("No entities to assess.")
            return factor

        score = 20.0
        jurisdictions: list[str] = []

        for e in entities:
            jur = e.get("jurisdiction", "")
            base_jur = jur.split("-")[0].upper()
            jurisdictions.append(jur)

            # Check elevated risk
            risk = ELEVATED_RISK_JURISDICTIONS.get(base_jur)
            if risk:
                level = risk["level"]
                deduct = {"MEDIUM": 3, "HIGH": 6, "CRITICAL": 15}.get(level, 2)
                score -= deduct
                report.flags.append(
                    f"Elevated jurisdiction risk: {jur} ({risk['reason']})"
                )
                factor.components.append({
                    "entity": e.get("legal_name", "?"),
                    "jurisdiction": jur,
                    "risk_level": level,
                    "deduction": deduct,
                })
            elif base_jur in STRONG_REGULATORY_JURISDICTIONS:
                factor.components.append({
                    "entity": e.get("legal_name", "?"),
                    "jurisdiction": jur,
                    "risk_level": "LOW",
                    "deduction": 0,
                })
                report.mitigants.append(
                    f"{e.get('legal_name', '?')} in strong regulatory jurisdiction ({jur})."
                )

            # SPV jurisdiction bonus
            if jur in SPV_FAVORABLE and e.get("entity_type") == "special_purpose_vehicle":
                score += 1
                factor.notes.append(f"SPV in favorable jurisdiction: {jur}")

        # Multi-jurisdiction diversification
        unique_base = set(j.split("-")[0] for j in jurisdictions)
        if len(unique_base) >= 2:
            factor.notes.append(
                f"Cross-border deal spans {len(unique_base)} jurisdictions: "
                f"{', '.join(sorted(unique_base))}"
            )

        factor.raw_score = score
        return factor

    # ------------------------------------------------------------------
    # Factor 2: Documentation Score (0-20)
    # ------------------------------------------------------------------

    def _score_documentation(
        self, entities: list[dict], report: CounterpartyRiskReport,
    ) -> RiskFactor:
        factor = RiskFactor(name="Documentation Score", max_score=20)
        if not entities:
            factor.raw_score = 0
            return factor

        score = 0.0

        # Evidence files
        evidence_count = 0
        if EVIDENCE_DIR.exists():
            for sub in EVIDENCE_DIR.iterdir():
                if sub.is_dir():
                    evidence_count += len(list(sub.glob("*")))

        if evidence_count >= 10:
            score += 5
            factor.notes.append(f"{evidence_count} evidence documents on file.")
        elif evidence_count >= 5:
            score += 3
            factor.notes.append(f"{evidence_count} evidence documents (adequate).")
        elif evidence_count > 0:
            score += 1
            factor.notes.append(f"Only {evidence_count} evidence documents.")
            report.flags.append("Low evidence document count.")

        # Legal opinions
        for e in entities:
            opinions = e.get("legal_opinions", [])
            if opinions:
                signed = sum(1 for o in opinions if o.get("status", "").upper() != "DRAFT")
                drafts = len(opinions) - signed
                score += min(5, signed * 2.5)
                if drafts:
                    score += drafts * 0.5
                    report.flags.append(f"{drafts} draft opinion(s) pending finalization.")
                factor.components.append({
                    "entity": e.get("legal_name", "?"),
                    "opinions_signed": signed,
                    "opinions_draft": drafts,
                })

        # Insurance
        for e in entities:
            ins = e.get("insurance")
            if ins:
                coverage = ins.get("coverage", {})
                si = coverage.get("sum_insured", 0)
                if si > 0:
                    score += 4
                    factor.notes.append(f"Insurance coverage: ${si:,.0f}")
                    report.mitigants.append(f"Insurance coverage of ${si:,.0f} in place.")

                broker = ins.get("broker", {})
                if broker.get("fca_number"):
                    score += 1
                    factor.notes.append("Insurance broker FCA authorized.")

        # MTN program documentation
        for e in entities:
            mtn = e.get("mtn_program")
            if mtn:
                score += 3
                cusips = mtn.get("cusips", [])
                if cusips:
                    factor.notes.append(f"MTN program with {len(cusips)} CUSIPs documented.")
                break

        factor.raw_score = score
        return factor

    # ------------------------------------------------------------------
    # Factor 3: Concentration Risk (0-20)
    # ------------------------------------------------------------------

    def _score_concentration(
        self, entities: list[dict], report: CounterpartyRiskReport,
    ) -> RiskFactor:
        factor = RiskFactor(name="Concentration Risk", max_score=20)
        if not entities:
            factor.raw_score = 10
            return factor

        score = 20.0  # Start at max, deduct for concentration

        # Single entity = max concentration risk
        if len(entities) == 1:
            score -= 8
            report.flags.append("Single-entity deal. Maximum concentration risk.")
            factor.notes.append("No diversification across entities.")

        # Check if same person controls multiple entities
        owners: dict[str, list[str]] = {}
        for e in entities:
            for bo in e.get("beneficial_owners", []):
                name = bo.get("name", "").lower().strip()
                if name:
                    owners.setdefault(name, []).append(e.get("legal_name", "?"))

        for owner_name, entity_list in owners.items():
            if len(entity_list) >= 2:
                score -= 3
                factor.components.append({
                    "owner": owner_name,
                    "controls_entities": entity_list,
                    "concentration": "HIGH",
                })
                report.flags.append(
                    f"Beneficial owner '{owner_name}' controls {len(entity_list)} entities."
                )

        # Same jurisdiction concentration
        jurs = [e.get("jurisdiction", "")[:2] for e in entities]
        jur_counts: dict[str, int] = {}
        for j in jurs:
            jur_counts[j] = jur_counts.get(j, 0) + 1

        for j, count in jur_counts.items():
            if count == len(entities) and len(entities) > 1:
                score -= 2
                factor.notes.append(
                    f"All entities in same jurisdiction ({j}). "
                    "No geographic diversification."
                )

        # Collateral backing (mitigant)
        for e in entities:
            col = e.get("collateral_framework") or e.get("reserve_system")
            if col:
                score += 2
                report.mitigants.append(
                    f"Collateral/reserve system at {e.get('legal_name', '?')} "
                    "reduces concentration impact."
                )
                break

        # Multiple banking relationships (mitigant)
        banks: set[str] = set()
        for e in entities:
            bank = e.get("banking", {}).get("settlement_bank")
            if bank:
                banks.add(bank.lower())
        if len(banks) >= 2:
            score += 1
            factor.notes.append(f"Multiple banking relationships ({len(banks)} banks).")

        factor.raw_score = score
        return factor

    # ------------------------------------------------------------------
    # Factor 4: Regulatory Exposure (0-20)
    # ------------------------------------------------------------------

    def _score_regulatory(
        self, entities: list[dict], report: CounterpartyRiskReport,
    ) -> RiskFactor:
        factor = RiskFactor(name="Regulatory Exposure", max_score=20)
        if not entities:
            factor.raw_score = 10
            return factor

        score = 14.0  # Base for neutral entities

        for e in entities:
            rs = e.get("regulatory_status", {})
            licenses = e.get("licenses", [])
            name = e.get("legal_name", "?")

            # Regulated entities get bonus for active licenses
            is_regulated = any(
                rs.get(k) for k in ("is_bank", "is_broker_dealer", "is_ria", "is_fund")
            )

            if is_regulated:
                active = sum(1 for lic in licenses if lic.get("status") == "active")
                if active > 0:
                    score += min(3, active * 1.5)
                    factor.notes.append(f"{name}: {active} active license(s).")
                    report.mitigants.append(f"{name} has {active} active regulatory license(s).")
                else:
                    score -= 4
                    report.flags.append(f"{name} claims regulated status but has no active licenses.")

            # Check sanctions screening
            owners = e.get("beneficial_owners", [])
            if owners:
                screened = sum(1 for o in owners if o.get("sanctions_screened"))
                if screened == len(owners):
                    score += 1
                    factor.components.append({
                        "entity": name,
                        "sanctions_screening": "COMPLETE",
                    })
                else:
                    unscreened = len(owners) - screened
                    score -= min(3, unscreened * 1.5)
                    report.flags.append(
                        f"{name}: {unscreened} beneficial owner(s) not sanctions-screened."
                    )
                    factor.components.append({
                        "entity": name,
                        "sanctions_screening": "INCOMPLETE",
                        "unscreened": unscreened,
                    })

        factor.raw_score = score
        return factor

    # ------------------------------------------------------------------
    # Factor 5: Settlement Complexity (0-20)
    # ------------------------------------------------------------------

    def _score_settlement(
        self, entities: list[dict], report: CounterpartyRiskReport,
    ) -> RiskFactor:
        factor = RiskFactor(name="Settlement Complexity", max_score=20)
        if len(entities) < 2:
            factor.raw_score = 10
            factor.notes.append("Need 2+ entities to assess settlement complexity.")
            return factor

        score = 20.0

        try:
            path = self.banking_engine.resolve_settlement_path(
                entities[0], entities[1], "USD",
            )

            node_count = len(path.nodes)
            factor.components.append({
                "path": f"{path.originator_entity} -> {path.beneficiary_entity}",
                "nodes": node_count,
                "is_valid": path.is_valid,
                "requires_fx": path.requires_fx,
            })

            # More nodes = more complexity = lower score
            if node_count > 5:
                score -= 4
                factor.notes.append(f"Complex chain: {node_count} nodes.")
            elif node_count >= 3:
                factor.notes.append(f"Standard chain: {node_count} nodes.")

            # FX risk
            if path.requires_fx:
                score -= 3
                factor.notes.append("Cross-border FX required.")
                report.flags.append("Settlement requires foreign exchange conversion.")

            if path.fx_approval_required:
                score -= 3
                factor.notes.append(f"FX authority approval: {path.fx_authority}")
                report.flags.append(f"FX approval required from {path.fx_authority}.")

            # Invalid path
            if not path.is_valid:
                score -= 5
                for issue in path.validation_issues:
                    factor.notes.append(f"Issue: {issue}")
                report.flags.append("Settlement path validation failed.")

            # Known GSIB banks (mitigant)
            gsib = [n for n in path.nodes if "GLOBAL" in (n.tier or "")]
            if gsib:
                score += 2
                report.mitigants.append(
                    f"Settlement chain includes GSIB: {', '.join(n.name for n in gsib)}."
                )

        except Exception as ex:
            score -= 5
            factor.notes.append(f"Could not resolve settlement path: {ex}")

        # DTC/DWAC settlement (mitigant)
        for e in entities:
            mtn = e.get("mtn_program", {})
            settlement = mtn.get("settlement_method", "")
            if "dtc" in settlement.lower() or "dwac" in settlement.lower():
                score += 2
                report.mitigants.append(f"DTC/DWAC settlement for securities delivery.")
                factor.notes.append("DTC/DWAC FAST settlement available.")
                break

        factor.raw_score = score
        return factor

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, report: CounterpartyRiskReport) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = report.deal_name.replace(" ", "_").replace(",", "").replace(".", "")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = OUTPUT_DIR / f"risk_score_{slug}_{ts}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path
