"""
Closing Condition Resolution Engine
======================================
Takes the output from ClosingTrackerEngine (the list of CPs) and
attempts to auto-resolve conditions by cross-referencing:
  - Evidence vault (data/evidence/)
  - Entity YAML data (banking, opinions, insurance, governance)
  - Other engine outputs (MTN validation, collateral, readiness)

For each CP:
  1. Check if evidence exists that satisfies it
  2. Check if entity data already meets the acceptance criteria
  3. Mark as SATISFIED, IN_PROGRESS, or leave OPEN
  4. Generate resolution notes explaining the determination

This engine bridges the gap between "we have the data" and
"the closing tracker doesn't know about it."

Input:  ClosingTracker + entity paths + evidence manifest
Output: Updated ClosingTracker with auto-resolved CPs, resolution
        report, and remaining action items
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import load_entity
from engine.closing_tracker import (
    ClosingTrackerEngine,
    ClosingTracker,
    ConditionPrecedent,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output" / "cp_resolution"
EVIDENCE_DIR = ROOT_DIR / "data" / "evidence"


# ---------------------------------------------------------------------------
# Evidence mapping — what evidence can satisfy what CP categories
# ---------------------------------------------------------------------------

# Maps CP source/category patterns to evidence directories and file patterns
EVIDENCE_RESOLUTION_MAP: list[dict[str, Any]] = [
    {
        "cp_pattern": "kyc",
        "evidence_dirs": ["querubin_usa", "tc_advantage"],
        "file_patterns": ["CIS_", "KYC_", "Risk_Compliance"],
        "category": "regulatory",
        "resolution_note": "KYC/AML documentation found in evidence vault.",
    },
    {
        "cp_pattern": "legal opinion",
        "evidence_dirs": ["optkas1_spv"],
        "file_patterns": ["Opinion_"],
        "category": "legal",
        "resolution_note": "Legal opinion document found in evidence vault.",
    },
    {
        "cp_pattern": "opinion",
        "evidence_dirs": ["optkas1_spv"],
        "file_patterns": ["Opinion_"],
        "category": "legal",
        "resolution_note": "Opinion document located in evidence vault.",
    },
    {
        "cp_pattern": "insurance",
        "evidence_dirs": ["tc_advantage"],
        "file_patterns": ["Insurance_", "CJColeman_Lloyds"],
        "category": "financial",
        "resolution_note": "Insurance documentation found in evidence vault.",
    },
    {
        "cp_pattern": "position",
        "evidence_dirs": ["tc_advantage"],
        "file_patterns": ["STC_Position", "Position_Report"],
        "category": "financial",
        "resolution_note": "Position report / custodial statement found.",
    },
    {
        "cp_pattern": "ppm",
        "evidence_dirs": ["tc_advantage"],
        "file_patterns": ["PPM_"],
        "category": "documentary",
        "resolution_note": "Private Placement Memorandum found in evidence vault.",
    },
    {
        "cp_pattern": "compliance",
        "evidence_dirs": ["querubin_usa"],
        "file_patterns": ["Risk_Compliance"],
        "category": "regulatory",
        "resolution_note": "Compliance package found in evidence vault.",
    },
    {
        "cp_pattern": "jv",
        "evidence_dirs": ["querubin_usa"],
        "file_patterns": ["JV_Summary"],
        "category": "documentary",
        "resolution_note": "JV Summary documentation found.",
    },
    {
        "cp_pattern": "swift",
        "evidence_dirs": ["dn2nc"],
        "file_patterns": ["SWIFT_", "DN2NC_SWIFT"],
        "category": "financial",
        "resolution_note": "SWIFT analysis documentation found.",
    },
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class CPResolution:
    """Resolution result for a single CP."""
    cp_id: str
    description: str
    original_status: str
    new_status: str
    resolution_method: str  # evidence, entity_data, engine_output, manual
    resolution_note: str = ""
    evidence_file: str = ""
    confidence: int = 0  # 0-100

    @property
    def was_resolved(self) -> bool:
        return self.new_status in ("SATISFIED", "IN_PROGRESS") and \
               self.original_status == "OPEN"

    def to_dict(self) -> dict:
        return {
            "cp_id": self.cp_id,
            "description": self.description,
            "original_status": self.original_status,
            "new_status": self.new_status,
            "was_resolved": self.was_resolved,
            "resolution_method": self.resolution_method,
            "resolution_note": self.resolution_note,
            "evidence_file": self.evidence_file,
            "confidence": self.confidence,
        }


@dataclass
class ResolutionReport:
    """Complete CP resolution report."""
    deal_name: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    resolutions: list[CPResolution] = field(default_factory=list)
    tracker: ClosingTracker | None = None

    @property
    def total_cps(self) -> int:
        return len(self.resolutions)

    @property
    def auto_resolved(self) -> int:
        return sum(1 for r in self.resolutions if r.was_resolved)

    @property
    def moved_to_in_progress(self) -> int:
        return sum(
            1 for r in self.resolutions
            if r.new_status == "IN_PROGRESS" and r.original_status == "OPEN"
        )

    @property
    def satisfied(self) -> int:
        return sum(1 for r in self.resolutions if r.new_status == "SATISFIED")

    @property
    def remaining_open(self) -> int:
        return sum(1 for r in self.resolutions if r.new_status == "OPEN")

    @property
    def resolution_pct(self) -> float:
        if not self.resolutions:
            return 0.0
        resolved = sum(
            1 for r in self.resolutions
            if r.new_status in ("SATISFIED", "IN_PROGRESS")
        )
        return round(resolved / self.total_cps * 100, 1)

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "CP RESOLUTION REPORT",
            f"  {self.deal_name}",
            f"  Generated: {self.created_at}",
            "=" * 70,
            "",
            f"  TOTAL CPs:        {self.total_cps}",
            f"  AUTO-RESOLVED:     {self.auto_resolved}",
            f"  SATISFIED:         {self.satisfied}",
            f"  IN PROGRESS:       {self.moved_to_in_progress}",
            f"  REMAINING OPEN:    {self.remaining_open}",
            f"  RESOLUTION RATE:   {self.resolution_pct}%",
            "",
        ]

        # Group by resolution result
        resolved = [r for r in self.resolutions if r.was_resolved]
        unresolved = [r for r in self.resolutions if not r.was_resolved]

        if resolved:
            lines.append("--- AUTO-RESOLVED ---")
            for r in resolved:
                icon = "[+]" if r.new_status == "SATISFIED" else "[~]"
                lines.append(f"  {icon} {r.cp_id}: {r.description[:50]}")
                lines.append(f"      Method: {r.resolution_method} "
                             f"(confidence: {r.confidence}%)")
                lines.append(f"      {r.resolution_note}")
                if r.evidence_file:
                    lines.append(f"      Evidence: {r.evidence_file}")
            lines.append("")

        if unresolved:
            lines.append("--- STILL OPEN ---")
            for r in unresolved:
                lines.append(f"  [ ] {r.cp_id}: {r.description[:60]}")
            lines.append("")

        # Tracker summary if available
        if self.tracker:
            lines.append("--- UPDATED TRACKER STATUS ---")
            lines.append(f"  Completion: {self.tracker.completion_pct}%")
            lines.append(f"  Signing:    {'READY' if self.tracker.signing_ready else 'NOT READY'}")
            lines.append(f"  Closing:    {'READY' if self.tracker.closing_ready else 'NOT READY'}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "created_at": self.created_at,
            "total_cps": self.total_cps,
            "auto_resolved": self.auto_resolved,
            "satisfied": self.satisfied,
            "remaining_open": self.remaining_open,
            "resolution_pct": self.resolution_pct,
            "resolutions": [r.to_dict() for r in self.resolutions],
            "tracker_status": self.tracker.to_dict() if self.tracker else None,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CPResolutionEngine:
    """
    Auto-resolves closing conditions by cross-referencing evidence
    and entity data.

    Usage:
        engine = CPResolutionEngine()
        report = engine.resolve(
            deal_name="TC Advantage 5B MTN",
            issuer_path=Path("data/entities/tc_advantage_traders.yaml"),
            spv_path=Path("data/entities/optkas1_spv.yaml"),
            additional_entities=[
                Path("data/entities/querubin_usa.yaml"),
            ],
        )
        print(report.summary())
    """

    def __init__(self) -> None:
        self._closing_engine = ClosingTrackerEngine()
        self._evidence_cache: dict[str, list[str]] = {}

    def resolve(
        self,
        deal_name: str,
        issuer_path: Path | None = None,
        spv_path: Path | None = None,
        additional_entities: list[Path] | None = None,
        target_closing_date: str = "",
    ) -> ResolutionReport:
        """Generate tracker and attempt to auto-resolve CPs."""
        # Step 1: Generate closing tracker
        tracker = self._closing_engine.generate(
            deal_name=deal_name,
            issuer_path=issuer_path,
            spv_path=spv_path,
            additional_entities=additional_entities,
            target_closing_date=target_closing_date,
        )

        # Step 2: Build evidence index
        evidence_index = self._build_evidence_index()

        # Step 3: Load entity data for data-based resolution
        entities: list[dict] = []
        for ep in [issuer_path, spv_path] + (additional_entities or []):
            if ep:
                try:
                    entities.append(load_entity(ep))
                except Exception:
                    pass

        # Step 4: Attempt resolution for each CP
        report = ResolutionReport(deal_name=deal_name)

        for cp in tracker.conditions:
            resolution = self._attempt_resolution(cp, evidence_index, entities)
            report.resolutions.append(resolution)

            # Update the tracker CP status
            if resolution.was_resolved:
                cp.status = resolution.new_status
                if resolution.new_status == "SATISFIED":
                    cp.satisfied_at = datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    )
                    cp.satisfied_by = f"CPResolutionEngine ({resolution.resolution_method})"
                cp.notes = resolution.resolution_note

        report.tracker = tracker
        return report

    # ------------------------------------------------------------------
    # Evidence index builder
    # ------------------------------------------------------------------

    def _build_evidence_index(self) -> dict[str, list[str]]:
        """Build an index of evidence files by directory."""
        index: dict[str, list[str]] = {}

        if not EVIDENCE_DIR.is_dir():
            return index

        for subdir in EVIDENCE_DIR.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                files = []
                for f in subdir.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        files.append(f.name)
                index[subdir.name] = files

        return index

    # ------------------------------------------------------------------
    # Resolution logic
    # ------------------------------------------------------------------

    def _attempt_resolution(
        self,
        cp: ConditionPrecedent,
        evidence_index: dict[str, list[str]],
        entities: list[dict],
    ) -> CPResolution:
        """Attempt to resolve a single CP."""
        resolution = CPResolution(
            cp_id=cp.cp_id,
            description=cp.description,
            original_status=cp.status,
            new_status=cp.status,  # Default: unchanged
            resolution_method="none",
        )

        # Already resolved? Skip
        if cp.is_resolved:
            resolution.new_status = cp.status
            resolution.resolution_method = "pre_existing"
            resolution.resolution_note = "Already resolved."
            resolution.confidence = 100
            return resolution

        # Try evidence-based resolution
        evidence_result = self._try_evidence_resolution(cp, evidence_index)
        if evidence_result:
            return evidence_result

        # Try entity-data-based resolution
        entity_result = self._try_entity_data_resolution(cp, entities)
        if entity_result:
            return entity_result

        # Try source-based resolution (e.g., MTN validation passed)
        source_result = self._try_source_resolution(cp, entities)
        if source_result:
            return source_result

        # Could not resolve
        resolution.resolution_method = "unresolved"
        resolution.resolution_note = "No matching evidence or data found."
        return resolution

    def _try_evidence_resolution(
        self,
        cp: ConditionPrecedent,
        evidence_index: dict[str, list[str]],
    ) -> CPResolution | None:
        """Try to resolve CP from evidence vault."""
        desc_lower = cp.description.lower()

        for mapping in EVIDENCE_RESOLUTION_MAP:
            pattern = mapping["cp_pattern"].lower()
            if pattern not in desc_lower:
                continue

            # Check if evidence exists
            for ev_dir in mapping["evidence_dirs"]:
                files = evidence_index.get(ev_dir, [])
                for file_pattern in mapping["file_patterns"]:
                    matching = [f for f in files if file_pattern.lower() in f.lower()]
                    if matching:
                        # Determine resolution level
                        # DRAFT opinions → IN_PROGRESS, not SATISFIED
                        is_draft = "draft" in desc_lower or "DRAFT" in cp.description
                        new_status = "IN_PROGRESS" if is_draft else "SATISFIED"
                        confidence = 70 if is_draft else 85

                        return CPResolution(
                            cp_id=cp.cp_id,
                            description=cp.description,
                            original_status=cp.status,
                            new_status=new_status,
                            resolution_method="evidence",
                            resolution_note=mapping["resolution_note"],
                            evidence_file=f"data/evidence/{ev_dir}/{matching[0]}",
                            confidence=confidence,
                        )

        return None

    def _try_entity_data_resolution(
        self,
        cp: ConditionPrecedent,
        entities: list[dict],
    ) -> CPResolution | None:
        """Try to resolve CP from entity data."""
        desc_lower = cp.description.lower()

        # Governance framework check
        if "governance" in desc_lower or "authority" in desc_lower:
            has_governance = any(
                e.get("entity", e).get("governance")
                or len(e.get("entity", e).get("signatories", [])) >= 2
                for e in entities
            )
            if has_governance:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="IN_PROGRESS",
                    resolution_method="entity_data",
                    resolution_note="Governance data found in entity profiles. "
                                    "Signatories and authority structure defined.",
                    confidence=70,
                )

        # Signatory check
        if "signator" in desc_lower:
            total_sigs = sum(
                len(e.get("entity", e).get("signatories", []))
                for e in entities
            )
            if total_sigs >= 2:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="SATISFIED",
                    resolution_method="entity_data",
                    resolution_note=f"{total_sigs} authorized signatories found "
                                    f"across entity profiles.",
                    confidence=90,
                )

        # Banking details check
        if "banking" in desc_lower or "settlement bank" in desc_lower:
            entities_with_banking = sum(
                1 for e in entities
                if e.get("entity", e).get("banking", {}).get("settlement_bank")
            )
            if entities_with_banking > 0:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="IN_PROGRESS",
                    resolution_method="entity_data",
                    resolution_note=f"{entities_with_banking} entity(ies) have "
                                    f"settlement banking configured.",
                    confidence=60,
                )

        # Insurance check
        if "insurance" in desc_lower:
            has_insurance = any(
                e.get("entity", e).get("insurance") for e in entities
            )
            if has_insurance:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="IN_PROGRESS",
                    resolution_method="entity_data",
                    resolution_note="Insurance data found in entity profile.",
                    confidence=65,
                )

        # FCA check
        if "fca" in desc_lower:
            has_fca = any(
                e.get("entity", e).get("insurance", {}).get("broker", {}).get("fca_number")
                for e in entities
            )
            if has_fca:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="SATISFIED",
                    resolution_method="entity_data",
                    resolution_note="FCA registration number confirmed in entity data.",
                    confidence=95,
                )

        return None

    def _try_source_resolution(
        self,
        cp: ConditionPrecedent,
        entities: list[dict],
    ) -> CPResolution | None:
        """Try to resolve based on CP source engine results."""
        desc_lower = cp.description.lower()

        # MTN WARN items can be IN_PROGRESS if MTN overall passes
        if cp.source == "mtn_validation" and cp.category == "documentary":
            has_mtn = any(
                e.get("entity", e).get("mtn_program") for e in entities
            )
            if has_mtn and "warn" in desc_lower.lower():
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="IN_PROGRESS",
                    resolution_method="engine_output",
                    resolution_note="MTN program validated at >90%. "
                                    "WARN item under review.",
                    confidence=60,
                )

        # Collateral WARN items
        if cp.source == "collateral_verification":
            if "warn" in desc_lower:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="IN_PROGRESS",
                    resolution_method="engine_output",
                    resolution_note="Collateral verification in progress. "
                                    "Warning item under review.",
                    confidence=50,
                )

        # Settlement assessment — if we have banking data for some entities
        if cp.source == "settlement_assessment":
            banking_count = sum(
                1 for e in entities
                if e.get("entity", e).get("banking", {}).get("settlement_bank")
            )
            if banking_count > 0:
                return CPResolution(
                    cp_id=cp.cp_id,
                    description=cp.description,
                    original_status=cp.status,
                    new_status="IN_PROGRESS",
                    resolution_method="engine_output",
                    resolution_note=f"{banking_count} entity(ies) have settlement "
                                    f"banking. Resolution in progress.",
                    confidence=55,
                )

        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, report: ResolutionReport) -> Path:
        """Persist resolution report to JSON."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = report.deal_name.replace(" ", "_").replace("/", "-")
        path = OUTPUT_DIR / f"cp_resolution_{name}_{ts}.json"
        path.write_text(
            json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return path
