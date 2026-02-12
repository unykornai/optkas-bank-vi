"""
Evidence Validator
==================
Validates that entity claims (licenses, registrations, banking)
are backed by actual uploaded evidence files.

Every claim must have a corresponding document.
Every document is SHA256-hashed for tamper detection.
All operations are logged to an immutable audit trail.

Institutional systems require document-backed claims.
YAML declarations alone are not sufficient.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from engine.schema_loader import ROOT_DIR
from engine._icons import ICON_BLOCK, ICON_WARN, ICON_FOLDER, ICON_ALERT, ICON_CHECK, ICON_CLEAR


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVIDENCE_DIR = ROOT_DIR / "data" / "evidence"
AUDIT_LOG_DIR = ROOT_DIR / "output" / "audit"
MANIFEST_PATH = EVIDENCE_DIR / "_manifest.yaml"

ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".csv"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class EvidenceFile:
    filename: str
    path: str
    sha256: str
    size_bytes: int
    category: str  # registration, regulatory_license, etc.
    verified_at: str  # ISO timestamp


@dataclass
class EvidenceGap:
    category: str
    description: str
    severity: str  # ERROR, WARNING
    entity_name: str

    def __str__(self) -> str:
        icon = ICON_BLOCK if self.severity == "ERROR" else ICON_WARN
        return f"{icon} [{self.severity}] EVIDENCE GAP — {self.category}: {self.description}"


@dataclass
class EvidenceReport:
    entity_name: str
    entity_slug: str
    files_found: list[EvidenceFile] = field(default_factory=list)
    gaps: list[EvidenceGap] = field(default_factory=list)
    audit_entries: list[dict] = field(default_factory=list)

    @property
    def has_critical_gaps(self) -> bool:
        return any(g.severity == "ERROR" for g in self.gaps)

    @property
    def files_hashed(self) -> int:
        return len(self.files_found)

    def summary(self) -> str:
        lines = [
            f"═══ EVIDENCE REPORT: {self.entity_name} ═══",
            f"Directory: data/evidence/{self.entity_slug}/",
            f"Files Found: {self.files_hashed}",
            f"Gaps: {len(self.gaps)} ({sum(1 for g in self.gaps if g.severity == 'ERROR')} errors)",
            "",
        ]
        if self.files_found:
            lines.append(f"{ICON_FOLDER} VERIFIED FILES:")
            for ef in self.files_found:
                lines.append(f"  {ICON_CHECK} {ef.filename}")
                lines.append(f"    SHA256: {ef.sha256[:16]}...")
                lines.append(f"    Size: {ef.size_bytes:,} bytes")
                lines.append(f"    Category: {ef.category}")
                lines.append("")

        if self.gaps:
            lines.append(f"{ICON_ALERT} EVIDENCE GAPS:")
            for gap in self.gaps:
                lines.append(f"  {gap}")
            lines.append("")

        if self.has_critical_gaps:
            lines.append(f"{ICON_BLOCK} EVIDENCE VALIDATION FAILED \u2014 Missing required documents.")
        else:
            lines.append(f"{ICON_CLEAR} Evidence baseline satisfied.")

        lines.append("═" * 50)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core Evidence Validator
# ---------------------------------------------------------------------------

class EvidenceValidator:
    """
    Validates that entity claims are backed by evidence files.
    Hashes all evidence, writes audit log.
    """

    def __init__(self) -> None:
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict[str, Any]:
        if MANIFEST_PATH.exists():
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def validate_entity_evidence(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any] | None = None,
    ) -> EvidenceReport:
        """
        Validate that an entity's claims are backed by evidence.

        Checks:
          1. Entity has an evidence directory
          2. All claimed licenses have corresponding PDFs
          3. Banking claims have supporting docs
          4. Signatory authorizations have uploaded docs
          5. Cross-border transactions require additional evidence
        """
        entity_name = entity.get("legal_name", "UNKNOWN")
        entity_slug = self._entity_slug(entity)
        evidence_path = EVIDENCE_DIR / entity_slug

        report = EvidenceReport(
            entity_name=entity_name,
            entity_slug=entity_slug,
        )

        # 1. Check evidence directory exists
        if not evidence_path.exists() or not evidence_path.is_dir():
            report.gaps.append(EvidenceGap(
                category="EVIDENCE_DIRECTORY",
                description=f"No evidence directory found at data/evidence/{entity_slug}/",
                severity="WARNING",
                entity_name=entity_name,
            ))
            # Still run claim checks to surface all gaps
        else:
            # Hash all files in the directory
            report.files_found = self._hash_directory(evidence_path)

        # 2. Check license evidence
        self._check_license_evidence(entity, report)

        # 3. Check banking evidence
        self._check_banking_evidence(entity, report)

        # 4. Check signatory authorization evidence
        self._check_signatory_evidence(entity, report)

        # 5. Check registration evidence
        self._check_registration_evidence(entity, report)

        # 6. Cross-border additional evidence
        if counterparty:
            jur_a = entity.get("jurisdiction", "").split("-")[0].upper()
            jur_b = counterparty.get("jurisdiction", "").split("-")[0].upper()
            if jur_a != jur_b:
                self._check_cross_border_evidence(entity, report)

        # Write audit log
        self._write_audit_log(report)

        return report

    # --- File Hashing ---

    def _hash_directory(self, directory: Path) -> list[EvidenceFile]:
        """SHA256-hash all evidence files in a directory."""
        files = []
        for filepath in sorted(directory.iterdir()):
            if filepath.is_file() and filepath.suffix.lower() in ACCEPTED_EXTENSIONS:
                sha256 = self._sha256(filepath)
                category = self._categorize_file(filepath.name)
                files.append(EvidenceFile(
                    filename=filepath.name,
                    path=str(filepath.relative_to(ROOT_DIR)),
                    sha256=sha256,
                    size_bytes=filepath.stat().st_size,
                    category=category,
                    verified_at=datetime.now(timezone.utc).isoformat(),
                ))
        return files

    @staticmethod
    def _sha256(filepath: Path) -> str:
        """Compute SHA256 hash of a file."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _categorize_file(filename: str) -> str:
        """Infer evidence category from filename patterns."""
        name_lower = filename.lower()
        category_map = {
            "registration": ["registration", "incorporation", "formation", "certificate"],
            "regulatory_license": ["license", "licence", "regulatory", "permit"],
            "custodian_letter": ["custodian", "custody"],
            "settlement_bank_letter": ["bank", "settlement", "swift"],
            "board_resolution": ["resolution", "board"],
            "signatory_authorization": ["authorization", "power_of_attorney", "poa"],
            "beneficial_ownership": ["beneficial", "ubo", "ownership"],
            "sanctions_screening": ["sanction", "ofac", "screening", "sdn"],
            "operating_agreement": ["operating", "bylaws", "articles"],
            "source_of_funds": ["source_of_funds", "bank_statement"],
        }
        for category, keywords in category_map.items():
            if any(kw in name_lower for kw in keywords):
                return category
        return "uncategorized"

    # --- Claim-vs-Evidence Checks ---

    def _check_license_evidence(self, entity: dict, report: EvidenceReport) -> None:
        """Every claimed license must have a corresponding evidence file."""
        licenses = entity.get("licenses", [])
        if not licenses:
            return

        license_files = [
            f for f in report.files_found if f.category == "regulatory_license"
        ]

        for lic in licenses:
            lic_type = lic.get("license_type", "UNKNOWN")
            regulator = lic.get("regulator", "UNKNOWN")
            lic_number = lic.get("license_number", "")

            # Check if there's a file that could correspond to this license
            matched = False
            for ef in license_files:
                # Match by regulator name or license number in filename
                name_lower = ef.filename.lower()
                if (
                    regulator.lower() in name_lower
                    or lic_number.lower().replace("-", "") in name_lower.replace("-", "")
                    or lic_type.lower().replace("_", " ") in name_lower.replace("_", " ")
                ):
                    matched = True
                    break

            if not matched:
                report.gaps.append(EvidenceGap(
                    category="LICENSE_EVIDENCE",
                    description=(
                        f"License '{lic_type}' from {regulator} "
                        f"(#{lic_number}) has no supporting document. "
                        f"Upload to data/evidence/{report.entity_slug}/"
                    ),
                    severity="ERROR",
                    entity_name=report.entity_name,
                ))

    def _check_banking_evidence(self, entity: dict, report: EvidenceReport) -> None:
        """If entity claims custodian or banking, require evidence."""
        banking = entity.get("banking", {})
        if not banking:
            return

        bank_files = [
            f for f in report.files_found
            if f.category in ("settlement_bank_letter", "custodian_letter")
        ]

        if banking.get("custodian") and not any(f.category == "custodian_letter" for f in bank_files):
            report.gaps.append(EvidenceGap(
                category="CUSTODIAN_EVIDENCE",
                description=(
                    f"Custodian '{banking['custodian']}' claimed but no custodian "
                    f"letter/agreement on file."
                ),
                severity="ERROR",
                entity_name=report.entity_name,
            ))

        if banking.get("settlement_bank") and not any(
            f.category == "settlement_bank_letter" for f in bank_files
        ):
            report.gaps.append(EvidenceGap(
                category="BANK_EVIDENCE",
                description=(
                    f"Settlement bank '{banking['settlement_bank']}' claimed but no "
                    f"bank reference letter on file."
                ),
                severity="WARNING",
                entity_name=report.entity_name,
            ))

    def _check_signatory_evidence(self, entity: dict, report: EvidenceReport) -> None:
        """Check for board resolution / authorization docs."""
        signatories = entity.get("signatories", [])
        auth_files = [
            f for f in report.files_found
            if f.category in ("signatory_authorization", "board_resolution")
        ]

        binding_sigs = [s for s in signatories if s.get("can_bind_company")]
        if binding_sigs and not auth_files:
            report.gaps.append(EvidenceGap(
                category="SIGNATORY_AUTHORIZATION",
                description=(
                    "Binding signatory declared but no board resolution or "
                    "authorization document uploaded."
                ),
                severity="WARNING",
                entity_name=report.entity_name,
            ))

    def _check_registration_evidence(self, entity: dict, report: EvidenceReport) -> None:
        """Check for certificate of incorporation / registration."""
        reg_files = [f for f in report.files_found if f.category == "registration"]
        reg_number = entity.get("registration_number", "")

        if reg_number and not reg_files:
            report.gaps.append(EvidenceGap(
                category="REGISTRATION_EVIDENCE",
                description=(
                    f"Registration #{reg_number} claimed but no certificate "
                    f"of incorporation/formation on file."
                ),
                severity="WARNING",
                entity_name=report.entity_name,
            ))

    def _check_cross_border_evidence(self, entity: dict, report: EvidenceReport) -> None:
        """Cross-border transactions require additional evidence."""
        bo_files = [f for f in report.files_found if f.category == "beneficial_ownership"]
        sanctions_files = [f for f in report.files_found if f.category == "sanctions_screening"]
        sof_files = [f for f in report.files_found if f.category == "source_of_funds"]

        if not bo_files:
            report.gaps.append(EvidenceGap(
                category="BENEFICIAL_OWNERSHIP_DECLARATION",
                description="Cross-border: No beneficial ownership declaration on file.",
                severity="ERROR",
                entity_name=report.entity_name,
            ))

        if not sanctions_files:
            report.gaps.append(EvidenceGap(
                category="SANCTIONS_SCREENING",
                description="Cross-border: No sanctions screening report on file.",
                severity="ERROR",
                entity_name=report.entity_name,
            ))

        if not sof_files:
            report.gaps.append(EvidenceGap(
                category="SOURCE_OF_FUNDS",
                description="Cross-border: No source of funds documentation on file.",
                severity="WARNING",
                entity_name=report.entity_name,
            ))

    # --- Audit Log ---

    def _write_audit_log(self, report: EvidenceReport) -> None:
        """Write an immutable audit log entry for evidence validation."""
        AUDIT_LOG_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc)
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "action": "EVIDENCE_VALIDATION",
            "entity": report.entity_name,
            "entity_slug": report.entity_slug,
            "files_verified": [
                {
                    "filename": f.filename,
                    "sha256": f.sha256,
                    "size_bytes": f.size_bytes,
                    "category": f.category,
                }
                for f in report.files_found
            ],
            "gaps_found": [
                {
                    "category": g.category,
                    "severity": g.severity,
                    "description": g.description,
                }
                for g in report.gaps
            ],
            "result": "FAIL" if report.has_critical_gaps else "PASS",
        }

        # Append to per-entity audit log (JSONL — one entry per line, append-only)
        log_file = AUDIT_LOG_DIR / f"{report.entity_slug}_evidence.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, default=str) + "\n")

        report.audit_entries.append(log_entry)

    # --- Utilities ---

    @staticmethod
    def _entity_slug(entity: dict) -> str:
        """Generate a filesystem-safe slug from entity name."""
        name = entity.get("trade_name") or entity.get("legal_name", "unknown")
        slug = name.lower().replace(" ", "_").replace(",", "").replace(".", "")
        slug = slug.replace("__", "_").strip("_")
        # Keep only alphanumeric and underscore
        return "".join(c for c in slug if c.isalnum() or c == "_")
