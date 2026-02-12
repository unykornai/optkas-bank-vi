"""
Audit Logger
=============
Writes provable compliance trails for every engine operation.

Each run produces a timestamped JSON file in /logs/ containing:
  - Entity and counterparty hashes
  - Evidence file hashes
  - All compliance findings
  - Conflict matrix results
  - Regulatory validation results
  - Compliance scores
  - Final decision grade
  - Policy applied
  - Git commit hash (if available)

This is not debug logging. This is an institutional audit record.
Without it, you have generation. With it, you have provable compliance.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import ROOT_DIR


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGS_DIR = ROOT_DIR / "logs"


# ---------------------------------------------------------------------------
# Audit Logger
# ---------------------------------------------------------------------------

class AuditLogger:
    """
    Writes structured audit records for every engine operation.
    """

    def __init__(self, logs_dir: Path | None = None) -> None:
        self._logs_dir = logs_dir or LOGS_DIR
        self._logs_dir.mkdir(parents=True, exist_ok=True)

    def log_run(
        self,
        *,
        operation: str,
        entity: dict[str, Any] | None = None,
        counterparty: dict[str, Any] | None = None,
        transaction_type: str | None = None,
        compliance_findings: list[dict] | None = None,
        red_flags: list[dict] | None = None,
        conflict_findings: list[dict] | None = None,
        regulatory_findings: list[dict] | None = None,
        evidence_hashes: dict[str, list[dict]] | None = None,
        compliance_score_entity: int | None = None,
        compliance_score_counterparty: int | None = None,
        opinion_grade: str | None = None,
        deal_classification: dict[str, Any] | None = None,
        policy_snapshot: dict[str, Any] | None = None,
        output_file: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        """
        Write a single audit record.

        Returns:
            Path to the written audit log file.
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%dT%H-%M-%S")

        record: dict[str, Any] = {
            "audit_version": "1.0",
            "timestamp_utc": now.isoformat(),
            "operation": operation,
            "git_commit": self._git_commit(),
        }

        # Entity hashes
        if entity:
            record["entity"] = {
                "legal_name": entity.get("legal_name", "UNKNOWN"),
                "jurisdiction": entity.get("jurisdiction", ""),
                "data_hash": self._hash_dict(entity),
            }

        if counterparty:
            record["counterparty"] = {
                "legal_name": counterparty.get("legal_name", "UNKNOWN"),
                "jurisdiction": counterparty.get("jurisdiction", ""),
                "data_hash": self._hash_dict(counterparty),
            }

        if transaction_type:
            record["transaction_type"] = transaction_type

        # Compliance
        if compliance_findings is not None:
            record["compliance_findings"] = compliance_findings
            record["compliance_finding_count"] = len(compliance_findings)

        if compliance_score_entity is not None:
            record["compliance_score_entity"] = compliance_score_entity
        if compliance_score_counterparty is not None:
            record["compliance_score_counterparty"] = compliance_score_counterparty

        # Red flags
        if red_flags is not None:
            record["red_flags"] = red_flags
            record["red_flag_count"] = len(red_flags)

        # Conflicts
        if conflict_findings is not None:
            record["conflict_findings"] = conflict_findings

        # Regulatory
        if regulatory_findings is not None:
            record["regulatory_findings"] = regulatory_findings

        # Evidence
        if evidence_hashes is not None:
            record["evidence_hashes"] = evidence_hashes

        # Opinion
        if opinion_grade is not None:
            record["opinion_grade"] = opinion_grade

        # Deal classification
        if deal_classification is not None:
            record["deal_classification"] = deal_classification

        # Policy
        if policy_snapshot is not None:
            record["policy_applied"] = policy_snapshot

        # Output
        if output_file:
            record["output_file"] = output_file

        if extra:
            record["extra"] = extra

        # Compute record hash for tamper detection
        record_json = json.dumps(record, sort_keys=True, default=str)
        record["record_hash"] = hashlib.sha256(record_json.encode()).hexdigest()

        # Write file
        op_slug = operation.replace(" ", "_").replace("-", "_").lower()
        filename = f"{timestamp}_{op_slug}.json"
        filepath = self._logs_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str, ensure_ascii=False)

        return filepath

    # --- Helpers ---

    @staticmethod
    def _hash_dict(d: dict[str, Any]) -> str:
        """SHA256 hash of a dictionary for tamper detection."""
        canonical = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _git_commit() -> str | None:
        """Get current git commit hash, or None if not in a repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(ROOT_DIR),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    # --- Serialization helpers ---

    @staticmethod
    def findings_to_dicts(findings: list) -> list[dict]:
        """Convert Finding/RedFlag/Conflict objects to plain dicts."""
        result = []
        for f in findings:
            d: dict[str, Any] = {}
            if hasattr(f, "severity"):
                sev = f.severity
                d["severity"] = sev.value if hasattr(sev, "value") else str(sev)
            if hasattr(f, "code"):
                d["code"] = f.code
            if hasattr(f, "message"):
                d["message"] = f.message
            if hasattr(f, "category"):
                d["category"] = f.category
            if hasattr(f, "description"):
                d["description"] = f.description
            if hasattr(f, "recommendation"):
                d["recommendation"] = f.recommendation
            if hasattr(f, "field") and f.field:
                d["field"] = f.field
            result.append(d)
        return result
