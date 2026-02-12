"""
Schema Loader — Loads and validates entity YAML files, jurisdiction rules,
and transaction type definitions.

This module is the structured input gate. Nothing enters the system
without passing through here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
ENTITIES_DIR = DATA_DIR / "entities"
TRANSACTIONS_DIR = DATA_DIR / "transactions"
EVIDENCE_DIR = DATA_DIR / "evidence"
RULES_DIR = ROOT_DIR / "rules" / "jurisdictions"
CONTRACTS_DIR = ROOT_DIR / "contracts" / "modules"
REGISTRY_PATH = CONTRACTS_DIR / "_registry.yaml"
PROMPTS_DIR = ROOT_DIR / "prompts"
OUTPUT_DIR = ROOT_DIR / "output"
AUDIT_DIR = OUTPUT_DIR / "audit"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dictionary."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Empty YAML file: {path}")
    return data


# ---------------------------------------------------------------------------
# Entity Loading
# ---------------------------------------------------------------------------

def load_entity(path: str | Path) -> dict[str, Any]:
    """
    Load and structurally validate an entity YAML file.

    Returns the entity dict (the value under the top-level 'entity' key).
    Raises ValueError if required fields are missing.
    """
    path = Path(path)
    raw = _load_yaml(path)

    entity = raw.get("entity")
    if entity is None:
        raise ValueError(f"Entity file {path.name} missing top-level 'entity' key.")

    # --- Enforce required fields ---
    # Fields that must be present AND truthy:
    hard_required = ["legal_name", "jurisdiction", "entity_type"]
    # Fields that must be present but may be null (external entities):
    soft_required = ["formation_date"]
    missing = [f for f in hard_required if not entity.get(f)]
    missing += [f for f in soft_required if f not in entity]
    if missing:
        raise ValueError(
            f"Entity '{entity.get('legal_name', path.name)}' missing required fields: "
            + ", ".join(missing)
        )

    # --- Enforce regulatory_status exists ---
    if "regulatory_status" not in entity or not isinstance(entity["regulatory_status"], dict):
        raise ValueError(
            f"Entity '{entity['legal_name']}' missing 'regulatory_status' block."
        )

    # --- Enforce at least one director ---
    directors = entity.get("directors", [])
    if not directors:
        raise ValueError(
            f"Entity '{entity['legal_name']}' must have at least one director."
        )

    # --- Enforce at least one signatory ---
    signatories = entity.get("signatories", [])
    if not signatories:
        raise ValueError(
            f"Entity '{entity['legal_name']}' must have at least one signatory."
        )

    # --- Enforce registered address ---
    address = entity.get("registered_address")
    if not address or not isinstance(address, dict):
        raise ValueError(
            f"Entity '{entity['legal_name']}' missing 'registered_address' block."
        )

    return entity


def load_entity_schema() -> dict[str, Any]:
    """Load the entity schema definition."""
    return _load_yaml(ENTITIES_DIR / "_schema.yaml")


# ---------------------------------------------------------------------------
# Jurisdiction Rules Loading
# ---------------------------------------------------------------------------

def load_master_rules() -> dict[str, Any]:
    """Load the master jurisdiction index."""
    return _load_yaml(RULES_DIR / "_master.yaml")


def load_jurisdiction_rules(jurisdiction_code: str) -> dict[str, Any]:
    """
    Load rules for a specific jurisdiction.

    Accepts codes like 'US', 'VN', 'CH', 'GB', 'SG', 'KY'.
    For sub-jurisdictions (e.g., 'US-DE'), loads the parent jurisdiction rules.
    """
    master = load_master_rules()
    jurisdictions = master.get("jurisdictions", {})

    # Handle sub-jurisdictions (e.g., US-DE -> US)
    base_code = jurisdiction_code.split("-")[0].upper()

    if base_code not in jurisdictions:
        raise ValueError(
            f"Unsupported jurisdiction: {jurisdiction_code}. "
            f"Supported: {', '.join(jurisdictions.keys())}"
        )

    rule_file = jurisdictions[base_code].get("rule_file")
    if not rule_file:
        raise ValueError(f"No rule file defined for jurisdiction: {base_code}")

    return _load_yaml(RULES_DIR / rule_file)


def get_all_jurisdiction_codes() -> list[str]:
    """Return all supported top-level jurisdiction codes."""
    master = load_master_rules()
    return list(master.get("jurisdictions", {}).keys())


# ---------------------------------------------------------------------------
# Transaction Type Loading
# ---------------------------------------------------------------------------

def load_transaction_types() -> dict[str, Any]:
    """Load all transaction type definitions."""
    raw = _load_yaml(TRANSACTIONS_DIR / "_types.yaml")
    return raw.get("transaction_types", {})


def load_transaction_type(tx_type: str) -> dict[str, Any]:
    """Load a specific transaction type definition."""
    types = load_transaction_types()
    if tx_type not in types:
        raise ValueError(
            f"Unknown transaction type: '{tx_type}'. "
            f"Available: {', '.join(types.keys())}"
        )
    return types[tx_type]


# ---------------------------------------------------------------------------
# Contract Module Loading
# ---------------------------------------------------------------------------

def load_contract_module(module_name: str) -> str:
    """
    Load a contract module template (Jinja2-flavored Markdown).

    Returns the raw template string.
    """
    path = CONTRACTS_DIR / f"{module_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Contract module not found: {module_name}")
    return path.read_text(encoding="utf-8")


def list_contract_modules() -> list[str]:
    """Return names of all available contract modules."""
    return sorted(
        p.stem for p in CONTRACTS_DIR.glob("*.md")
    )


# ---------------------------------------------------------------------------
# Prompt Loading
# ---------------------------------------------------------------------------

def load_master_prompt() -> str:
    """Load the master prompt template."""
    path = PROMPTS_DIR / "master_prompt.md"
    if not path.exists():
        raise FileNotFoundError("Master prompt not found at prompts/master_prompt.md")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Clause Registry Loading
# ---------------------------------------------------------------------------

def load_clause_registry() -> dict[str, Any]:
    """
    Load the clause registry for versioned module tracking.

    Returns a dict keyed by module name with version, status,
    risk_level, jurisdiction_validated, etc.
    """
    if not REGISTRY_PATH.exists():
        return {}
    raw = _load_yaml(REGISTRY_PATH)
    return raw.get("modules", {})


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def format_address(address: dict[str, Any]) -> str:
    """Format an address dict into a single-line string."""
    parts = [
        address.get("street", ""),
        address.get("city", ""),
        address.get("state_province", ""),
        address.get("postal_code", ""),
        address.get("country", ""),
    ]
    return ", ".join(p for p in parts if p)


def get_jurisdiction_full_name(code: str) -> str:
    """Get the full name of a jurisdiction from its code."""
    master = load_master_rules()
    jurisdictions = master.get("jurisdictions", {})
    base_code = code.split("-")[0].upper()

    if base_code in jurisdictions:
        name = jurisdictions[base_code].get("name", base_code)
        # If sub-jurisdiction, append it
        if "-" in code:
            sub = jurisdictions[base_code].get("sub_jurisdictions", {})
            sub_name = sub.get(code.upper(), "")
            if sub_name:
                return f"{sub_name}, {name}"
        return name
    return code


def ensure_output_dir() -> Path:
    """Ensure the output directory exists and return its path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR
