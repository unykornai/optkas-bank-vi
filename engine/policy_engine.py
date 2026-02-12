"""
Policy Engine
==============
Loads organizational execution policy and provides enforcement decisions.

The policy layer separates what the engine CAN analyze from what it is
ALLOWED to enforce. This is how institutional systems work:

  Analysis layer  → detects issues
  Policy layer    → decides severity
  Enforcement     → blocks or warns based on policy

Tier 1: Advisory         — everything is a suggestion
Tier 2: Conditional      — blocks generation on policy violations
Tier 3: Autonomous       — controls signature readiness (future)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLICY_PATH = Path(__file__).resolve().parent / "policy.yaml"


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """
    Loads and provides access to organizational deal execution policy.
    """

    def __init__(self, policy_path: Path | None = None) -> None:
        self._path = policy_path or POLICY_PATH
        self._policy: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._policy = yaml.safe_load(f) or {}
        else:
            self._policy = {}

    # --- Core accessors ---

    @property
    def raw(self) -> dict[str, Any]:
        return self._policy

    @property
    def version(self) -> str:
        return self._policy.get("policy_version", "0.0.0")

    @property
    def execution_tier(self) -> int:
        return self._policy.get("execution_tier", 1)

    @property
    def tier_label(self) -> str:
        return {1: "Advisory", 2: "Conditional Execution", 3: "Autonomous"}[
            self.execution_tier
        ]

    # --- Section accessors ---

    def _section(self, key: str) -> dict[str, Any]:
        return self._policy.get(key, {})

    @property
    def generation(self) -> dict[str, Any]:
        return self._section("generation_controls")

    @property
    def cross_border(self) -> dict[str, Any]:
        return self._section("cross_border_controls")

    @property
    def securities(self) -> dict[str, Any]:
        return self._section("securities_controls")

    @property
    def signatory(self) -> dict[str, Any]:
        return self._section("signatory_controls")

    @property
    def evidence(self) -> dict[str, Any]:
        return self._section("evidence_controls")

    @property
    def opinion(self) -> dict[str, Any]:
        return self._section("opinion_controls")

    @property
    def red_flags(self) -> dict[str, Any]:
        return self._section("red_flag_controls")

    @property
    def audit(self) -> dict[str, Any]:
        return self._section("audit_controls")

    @property
    def liability(self) -> dict[str, Any]:
        return self._section("liability_controls")

    # --- Enforcement decisions ---

    def should_block(self, policy_key: str, section: str = "") -> bool:
        """
        Returns True if the policy says this condition should block generation.

        Args:
            policy_key: The specific policy flag (e.g., 'escrow_missing_severity')
            section: The policy section (e.g., 'cross_border_controls')
        """
        if self.execution_tier == 1:
            return False  # Advisory mode never blocks

        if section:
            value = self._section(section).get(policy_key, "warn")
        else:
            # Search all sections
            for sec in self._policy.values():
                if isinstance(sec, dict) and policy_key in sec:
                    value = sec[policy_key]
                    break
            else:
                value = "warn"

        return value == "block"

    def should_warn(self, policy_key: str, section: str = "") -> bool:
        """Returns True if the policy says this condition should produce a warning."""
        if section:
            value = self._section(section).get(policy_key, "warn")
        else:
            for sec in self._policy.values():
                if isinstance(sec, dict) and policy_key in sec:
                    value = sec[policy_key]
                    break
            else:
                value = "warn"
        return value in ("warn", "block")

    def is_silent(self, policy_key: str, section: str = "") -> bool:
        """Returns True if the policy says this condition should be silently logged."""
        if section:
            value = self._section(section).get(policy_key, "warn")
        else:
            for sec in self._policy.values():
                if isinstance(sec, dict) and policy_key in sec:
                    value = sec[policy_key]
                    break
            else:
                value = "warn"
        return value == "silent"

    def adverse_blocks_signature(self) -> bool:
        """Returns True if an ADVERSE opinion grade should block signature."""
        return self.opinion.get("adverse_grade_blocks_signature", True)

    def disclaimer_text(self) -> str:
        """Returns the liability disclaimer to append to documents."""
        return self.liability.get("disclaimer_text", "").strip()

    def should_append_disclaimer(self) -> bool:
        """Returns True if documents should include the liability banner."""
        return self.liability.get("append_disclaimer_to_documents", True)

    def should_audit(self) -> bool:
        """Returns True if every run should be audit-logged."""
        return self.audit.get("audit_every_run", True)

    # --- Summary ---

    def summary(self) -> str:
        """Human-readable policy summary."""
        lines = [
            f"Policy Version: {self.version}",
            f"Execution Tier: {self.execution_tier} ({self.tier_label})",
            f"Last Reviewed:  {self._policy.get('last_reviewed', 'N/A')}",
            f"Approved By:    {self._policy.get('approved_by', 'N/A')}",
            "",
            "Enforcement Settings:",
        ]

        enforcement_keys = [
            ("cross_border_controls", "escrow_missing_severity", "Escrow Missing"),
            ("cross_border_controls", "currency_control_severity", "Currency Controls"),
            ("signatory_controls", "single_signatory_severity", "Single Signatory"),
            ("evidence_controls", "missing_evidence_severity", "Missing Evidence"),
            ("red_flag_controls", "critical_red_flag_severity", "Critical Red Flag"),
            ("red_flag_controls", "sanctions_gap_severity", "Sanctions Gap"),
        ]

        for section, key, label in enforcement_keys:
            value = self._section(section).get(key, "warn")
            marker = {"block": "[BLOCK]", "warn": "[WARN]", "silent": "[SILENT]"}.get(
                value, f"[{value}]"
            )
            lines.append(f"  {label:.<30} {marker}")

        lines.append("")
        lines.append(f"Adverse Grade Blocks Signature: {self.adverse_blocks_signature()}")
        lines.append(f"Disclaimer Appended:            {self.should_append_disclaimer()}")
        lines.append(f"Audit Every Run:                {self.should_audit()}")

        return "\n".join(lines)
