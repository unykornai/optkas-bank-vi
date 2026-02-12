"""
Legal Automation OS — CLI Interface
====================================
Main entry point for the legal document generation engine.

Commands:
  validate          — Validate an entity against schema and jurisdiction rules
  compliance-report — Full compliance check with scoring
  generate          — Assemble a complete agreement from entity data
  prompt            — Build a structured LLM prompt package
  export            — Convert Markdown output to DOCX/PDF
  list-types        — List available transaction types
  list-jurisdictions — List supported jurisdictions
  list-modules      — List available contract modules
  policy            — Display current organizational execution policy
  deal-classify     — Auto-classify deal risk tier
  checklist         — Generate pre-closing execution checklist
  dossier           — Build counterparty risk dossier
  deal-room         — Package complete deal room
  deal-create       — Create a new deal in DRAFT state
  deal-advance      — Advance deal to next lifecycle state
  deal-status       — Show deal lifecycle status
  settlement-path   — Map and validate cross-border settlement rails
  cap-structure     — Build and validate capital allocation structure
  jurisdiction      — Query jurisdiction intelligence database
  governance        — Build and display governance framework
  fund-flow         — Track capital lifecycle (call, fund, deploy)
  compliance-pkg    — Generate full compliance package for a deal
  deal-entities     — List all entity profiles in the system
  mtn-validate      — Validate MTN program structure and readiness
  collateral-check  — Verify collateral/SPV integrity
  deal-ready        — Full deal readiness assessment
  deal-governance   — Assess deal-level governance framework
  risk-score        — Multi-factor counterparty risk score
  closing-tracker   — Generate conditions precedent tracker
  settlement-onboard — Detect banking gaps and generate onboarding plan
  wire-instructions  — Generate institutional wire instruction packages
  signing-ceremony   — Prepare deal signing with authority validation
  deal-dashboard     — Unified deal status dashboard (all engines)
  escrow-plan        — Build escrow & settlement rail plan
  banking-resolve    — Resolve banking gaps across deal group
  cp-status          — Auto-resolve closing conditions from evidence
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from engine.schema_loader import (
    load_entity,
    load_transaction_types,
    get_all_jurisdiction_codes,
    list_contract_modules,
    get_jurisdiction_full_name,
    ensure_output_dir,
)
from engine.validator import ComplianceValidator
from engine.red_flags import RedFlagDetector
from engine.assembler import DocumentAssembler
from engine.prompt_engine import PromptEngine
from engine.exporter import export_markdown, export_docx, export_pdf
from engine.legal_opinion import LegalOpinionGenerator
from engine.evidence_validator import EvidenceValidator
from engine.conflict_matrix import ConflictMatrix
from engine.regulatory_validator import RegulatoryClaimValidator
from engine.policy_engine import PolicyEngine
from engine.audit_logger import AuditLogger
from engine.deal_classifier import DealClassifier
from engine.execution_checklist import ChecklistBuilder
from engine.counterparty_dossier import DossierBuilder
from engine.deal_room import DealRoomPackager
from engine.deal_lifecycle import DealLifecycleManager
from engine.correspondent_banking import CorrespondentBankingEngine
from engine.capital_structure import CapitalStructureBuilder, CapitalCommitment
from engine.jurisdiction_intel import JurisdictionIntelEngine
from engine.governance_rules import GovernanceBuilder
from engine.fund_flow import FundFlowBuilder, FlowState
from engine.compliance_package import CompliancePackageGenerator
from engine.mtn_validator import MTNProgramValidator
from engine.collateral_verifier import CollateralVerifier
from engine.deal_readiness import DealReadinessEngine
from engine.deal_governance import DealGovernanceEngine
from engine.risk_scorer import CounterpartyRiskEngine
from engine.closing_tracker import ClosingTrackerEngine
from engine.settlement_onboarding import SettlementOnboardingEngine
from engine.wire_instructions import WireInstructionEngine
from engine.signing_ceremony import SigningCeremonyEngine
from engine.deal_dashboard import DealDashboardEngine
from engine.escrow_engine import EscrowEngine
from engine.banking_resolver import BankingResolverEngine
from engine.cp_resolution import CPResolutionEngine
from engine._icons import ICON_CHECK, ICON_CROSS, ICON_WARN

console = Console()


# ---------------------------------------------------------------------------
# CLI Group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option("1.0.0", prog_name="Legal Automation OS")
def main():
    """⚖️  Legal Automation OS — Jurisdiction-Aware Document Generation Engine"""
    pass


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@main.command()
@click.option("--entity", "-e", required=True, type=click.Path(exists=True),
              help="Path to entity YAML file.")
@click.option("--transaction-type", "-t", default=None,
              help="Transaction type to validate against.")
@click.option("--counterparty", "-c", default=None, type=click.Path(exists=True),
              help="Path to counterparty entity YAML file.")
def validate(entity: str, transaction_type: str | None, counterparty: str | None):
    """Validate an entity against schema and jurisdiction rules."""
    try:
        entity_data = load_entity(entity)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]{ICON_CROSS} Entity load failed:[/red] {e}")
        sys.exit(1)

    cp_data = None
    if counterparty:
        try:
            cp_data = load_entity(counterparty)
        except (ValueError, FileNotFoundError) as e:
            console.print(f"[red]{ICON_CROSS} Counterparty load failed:[/red] {e}")
            sys.exit(1)

    validator = ComplianceValidator()
    report = validator.validate_entity(entity_data, transaction_type, cp_data)

    console.print()
    console.print(Panel(
        report.summary(),
        title=f"Validation Report — {report.entity_name}",
        border_style="blue" if not report.is_blocked else "red",
    ))

    if report.is_blocked:
        sys.exit(1)


# ---------------------------------------------------------------------------
# compliance-report
# ---------------------------------------------------------------------------

@main.command("compliance-report")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", default=None, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", default=None)
def compliance_report(entity: str, counterparty: str | None, transaction_type: str | None):
    """Full compliance check with scoring and red-flag detection."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty) if counterparty else None

    # Validation
    validator = ComplianceValidator()
    val_report = validator.validate_entity(entity_data, transaction_type, cp_data)

    # Red flags
    detector = RedFlagDetector()
    rf_report = detector.scan(entity_data, cp_data, transaction_type)

    console.print()
    console.print(Panel(
        val_report.summary(),
        title="COMPLIANCE VALIDATION",
        border_style="blue" if not val_report.is_blocked else "red",
    ))

    console.print()
    console.print(Panel(
        rf_report.summary(),
        title="RED FLAG ASSESSMENT",
        border_style="yellow" if rf_report.flags else "green",
    ))

    # Counterparty report
    if cp_data:
        cp_report = validator.validate_entity(cp_data, transaction_type, entity_data)
        cp_rf = detector.scan(cp_data, entity_data, transaction_type)

        console.print()
        console.print(Panel(
            cp_report.summary(),
            title=f"COUNTERPARTY COMPLIANCE — {cp_report.entity_name}",
            border_style="blue" if not cp_report.is_blocked else "red",
        ))

        console.print()
        console.print(Panel(
            cp_rf.summary(),
            title=f"COUNTERPARTY RED FLAGS — {cp_data.get('legal_name', '')}",
            border_style="yellow" if cp_rf.flags else "green",
        ))


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

@main.command()
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Output directory (default: ./output)")
@click.option("--format", "-f", "fmt", default="md",
              type=click.Choice(["md", "docx", "pdf", "all"]),
              help="Output format.")
@click.option("--force", is_flag=True, help="Skip validation block and generate anyway.")
def generate(
    entity: str,
    counterparty: str,
    transaction_type: str,
    output: str | None,
    fmt: str,
    force: bool,
):
    """Assemble a complete agreement from entity data."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    # Pre-generation validation
    validator = ComplianceValidator()
    val_report = validator.validate_entity(entity_data, transaction_type, cp_data)
    cp_report = validator.validate_entity(cp_data, transaction_type, entity_data)

    if (val_report.is_blocked or cp_report.is_blocked) and not force:
        console.print()
        console.print(Panel(
            val_report.summary(),
            title=f"{ICON_WARN}  GENERATION BLOCKED",
            border_style="red",
        ))
        if cp_report.is_blocked:
            console.print(Panel(
                cp_report.summary(),
                title=f"{ICON_WARN}  COUNTERPARTY VALIDATION FAILED",
                border_style="red",
            ))
        console.print("[red]Resolve errors or use --force to override.[/red]")
        sys.exit(1)

    # Assemble document
    assembler = DocumentAssembler()
    document = assembler.assemble(entity_data, cp_data, transaction_type)

    # Append compliance reports
    detector = RedFlagDetector()
    rf_report = detector.scan(entity_data, cp_data, transaction_type)

    document += "\n\n---\n\n"
    document += "# APPENDIX A — COMPLIANCE CHECKLIST\n\n"
    document += val_report.summary()
    document += "\n\n"
    document += cp_report.summary()

    document += "\n\n---\n\n"
    document += "# APPENDIX B — RED FLAG SUMMARY\n\n"
    document += rf_report.summary()

    # Determine filename
    a_short = entity_data.get("trade_name", entity_data.get("legal_name", "PartyA"))
    b_short = cp_data.get("trade_name", cp_data.get("legal_name", "PartyB"))
    filename = f"{transaction_type}_{a_short}_{b_short}".replace(" ", "_").replace(",", "")

    # Export
    md_path = export_markdown(document, filename)
    console.print(f"\n[green]{ICON_CHECK}[/green] Markdown: {md_path}")

    # Audit trail
    try:
        from engine.audit_logger import AuditLogger
        audit = AuditLogger()
        audit.log_run(
            operation="generate",
            entity=entity_data,
            counterparty=cp_data,
            transaction_type=transaction_type,
            compliance_findings=val_report.findings + cp_report.findings,
            red_flags=rf_report.flags,
            output_file=str(md_path),
        )
    except Exception:
        pass  # Audit failure must never block generation

    if fmt in ("docx", "all"):
        try:
            docx_path = export_docx(md_path, filename)
            console.print(f"[green]{ICON_CHECK}[/green] DOCX: {docx_path}")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] DOCX export failed: {e}")

    if fmt in ("pdf", "all"):
        try:
            pdf_path = export_pdf(md_path, filename)
            console.print(f"[green]{ICON_CHECK}[/green] PDF: {pdf_path}")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] PDF export failed: {e}")


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------

@main.command()
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
@click.option("--output-file", "-o", default=None, help="Save prompt to file.")
def prompt(entity: str, counterparty: str, transaction_type: str, output_file: str | None):
    """Build a structured LLM prompt package."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    engine = PromptEngine()
    package = engine.build_prompt(entity_data, cp_data, transaction_type)

    # Display metadata
    meta = package["metadata"]
    console.print()
    console.print(Panel(
        f"Transaction: {meta['transaction_type']}\n"
        f"Jurisdictions: {', '.join(meta['jurisdictions'])}\n"
        f"Cross-Border: {meta['is_cross_border']}\n"
        f"Blocked: {meta['is_blocked']}\n"
        f"Compliance Score (Entity): {meta['compliance_score_entity']}/100\n"
        f"Compliance Score (Counterparty): {meta['compliance_score_counterparty']}/100",
        title="Prompt Package Metadata",
        border_style="blue",
    ))

    # Output
    output = {
        "system_prompt": package["system_prompt"],
        "user_prompt": package["user_prompt"],
    }

    if output_file:
        Path(output_file).write_text(
            json.dumps(output, indent=2, default=str),
            encoding="utf-8",
        )
        console.print(f"\n[green]{ICON_CHECK}[/green] Prompt saved to: {output_file}")
    else:
        console.print("\n[bold]System Prompt:[/bold]")
        console.print(package["system_prompt"][:500] + "...")
        console.print("\n[bold]User Prompt:[/bold] (truncated)")
        console.print(package["user_prompt"][:1000] + "...")
        console.print(f"\n[dim]Full prompt length: {len(package['user_prompt'])} chars[/dim]")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@main.command()
@click.option("--input", "-i", "input_file", required=True, type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", required=True,
              type=click.Choice(["docx", "pdf"]))
def export(input_file: str, fmt: str):
    """Convert Markdown output to DOCX or PDF."""
    md_path = Path(input_file)

    if fmt == "docx":
        result = export_docx(md_path)
        console.print(f"[green]{ICON_CHECK}[/green] Exported: {result}")
    elif fmt == "pdf":
        result = export_pdf(md_path)
        console.print(f"[green]{ICON_CHECK}[/green] Exported: {result}")


# ---------------------------------------------------------------------------
# legal-opinion
# ---------------------------------------------------------------------------

@main.command("legal-opinion")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Save opinion to file.")
def legal_opinion(entity: str, counterparty: str, transaction_type: str, output: str | None):
    """Generate an institutional-grade legal opinion."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    generator = LegalOpinionGenerator()
    opinion = generator.generate(entity_data, cp_data, transaction_type)

    rendered = opinion.render()

    console.print()
    grade_color = {
        "CLEAR": "green",
        "QUALIFIED": "yellow",
        "ADVERSE": "red",
        "UNABLE_TO_OPINE": "magenta",
    }.get(opinion.overall_grade, "white")

    console.print(Panel(
        rendered,
        title=f"LEGAL OPINION -- {opinion.overall_grade}",
        border_style=grade_color,
    ))

    if opinion.signature_blocked_reason:
        console.print(Panel(
            opinion.signature_blocked_reason,
            title="SIGNATURE BLOCKED",
            border_style="red",
        ))
    elif opinion.signature_ready:
        console.print(Panel(
            "Signature permitted subject to human approval.",
            title="SIGNATURE READY",
            border_style="green",
        ))

    # Audit trail
    try:
        audit = AuditLogger()
        audit.log_run(
            operation="legal-opinion",
            entity=entity_data,
            counterparty=cp_data,
            transaction_type=transaction_type,
            opinion_grade=opinion.overall_grade,
        )
    except Exception:
        pass

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        console.print(f"\n[green]{ICON_CHECK}[/green] Opinion saved to: {out_path}")


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------

@main.command("evidence")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", default=None, type=click.Path(exists=True))
def evidence(entity: str, counterparty: str | None):
    """Validate evidence files for an entity."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty) if counterparty else None

    validator = EvidenceValidator()
    report = validator.validate_entity_evidence(entity_data, cp_data)

    console.print()
    console.print(Panel(
        report.summary(),
        title=f"EVIDENCE REPORT — {report.entity_name}",
        border_style="red" if report.has_critical_gaps else "green",
    ))

    if cp_data:
        cp_report = validator.validate_entity_evidence(cp_data, entity_data)
        console.print()
        console.print(Panel(
            cp_report.summary(),
            title=f"EVIDENCE REPORT — {cp_report.entity_name}",
            border_style="red" if cp_report.has_critical_gaps else "green",
        ))


# ---------------------------------------------------------------------------
# conflict-matrix
# ---------------------------------------------------------------------------

@main.command("conflict-matrix")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", default="")
def conflict_matrix_cmd(entity: str, counterparty: str, transaction_type: str):
    """Analyze governing law and jurisdiction conflicts."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    jur_a = entity_data.get("jurisdiction", "").split("-")[0].upper()
    jur_b = cp_data.get("jurisdiction", "").split("-")[0].upper()

    matrix = ConflictMatrix()
    report = matrix.analyze(jur_a, jur_b, transaction_type, entity_data, cp_data)

    console.print()
    console.print(Panel(
        report.summary(),
        title=f"CONFLICT MATRIX — {jur_a} ↔ {jur_b}",
        border_style="red" if report.has_critical else "yellow" if report.conflicts else "green",
    ))


# ---------------------------------------------------------------------------
# regulatory-check
# ---------------------------------------------------------------------------

@main.command("regulatory-check")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
def regulatory_check(entity: str):
    """Validate entity regulatory claims against the regulatory matrix."""
    entity_data = load_entity(entity)

    validator = RegulatoryClaimValidator()
    report = validator.validate(entity_data)

    console.print()
    console.print(Panel(
        report.summary(),
        title=f"REGULATORY VALIDATION — {report.entity_name}",
        border_style="red" if report.has_errors else "green",
    ))


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

@main.command("policy")
def policy_cmd():
    """Display current organizational execution policy."""
    policy = PolicyEngine()
    console.print()
    console.print(Panel(
        policy.summary(),
        title=f"EXECUTION POLICY v{policy.version} -- Tier {policy.execution_tier} ({policy.tier_label})",
        border_style="blue",
    ))


# ---------------------------------------------------------------------------
# deal-classify
# ---------------------------------------------------------------------------

@main.command("deal-classify")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
def deal_classify_cmd(entity: str, counterparty: str, transaction_type: str):
    """Auto-classify deal risk tier and flag required actions."""
    from engine.schema_loader import load_transaction_type
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    try:
        tx_def = load_transaction_type(transaction_type)
    except Exception:
        tx_def = {}

    classifier = DealClassifier()
    classification = classifier.classify(entity_data, cp_data, transaction_type, tx_def)

    tier_color = {
        "GREEN": "green",
        "AMBER": "yellow",
        "RED": "red",
        "CRITICAL": "bold red",
    }.get(classification.risk_tier, "white")

    console.print()
    console.print(Panel(
        classification.summary(),
        title=f"DEAL CLASSIFICATION -- Tier {classification.risk_tier} (Score: {classification.risk_score})",
        border_style=tier_color,
    ))

    # Required actions
    actions = []
    for tag in classification.tags:
        if tag.required_actions:
            for a in tag.required_actions:
                actions.append(f"[{tag.risk_level}] {a}")
    if actions:
        console.print()
        action_text = "\n".join(actions)
        console.print(Panel(
            action_text,
            title="REQUIRED ACTIONS",
            border_style="yellow",
        ))

    # Audit trail
    try:
        audit = AuditLogger()
        audit.log_run(
            operation="deal-classify",
            entity=entity_data,
            counterparty=cp_data,
            transaction_type=transaction_type,
            deal_classification=classification.to_dict(),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# checklist
# ---------------------------------------------------------------------------

@main.command("checklist")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
@click.option("--output", "-o", default=None, type=click.Path(),
              help="Save checklist to file.")
def checklist_cmd(entity: str, counterparty: str, transaction_type: str, output: str | None):
    """Generate a pre-closing execution checklist."""
    from engine.schema_loader import load_transaction_type
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    try:
        tx_def = load_transaction_type(transaction_type)
    except Exception:
        tx_def = {}

    # Run all analyses
    validator = ComplianceValidator()
    val_a = validator.validate_entity(entity_data, transaction_type, cp_data)
    val_b = validator.validate_entity(cp_data, transaction_type, entity_data)

    detector = RedFlagDetector()
    rf = detector.scan(entity_data, cp_data, transaction_type)

    evidence = EvidenceValidator()
    ev_a = evidence.validate_entity_evidence(entity_data, cp_data)
    ev_b = evidence.validate_entity_evidence(cp_data, entity_data)

    jur_a = entity_data.get("jurisdiction", "").split("-")[0].upper()
    jur_b = cp_data.get("jurisdiction", "").split("-")[0].upper()
    conflict_matrix = ConflictMatrix()
    conflicts = conflict_matrix.analyze(jur_a, jur_b, transaction_type, entity_data, cp_data)

    classifier = DealClassifier()
    classification = classifier.classify(entity_data, cp_data, transaction_type, tx_def)

    gen = LegalOpinionGenerator()
    opinion = gen.generate(entity_data, cp_data, transaction_type)
    opinion_conditions = []
    for sec in opinion.sections:
        opinion_conditions.extend(sec.conditions)

    builder = ChecklistBuilder()
    cl = builder.build(
        entity_data, cp_data, transaction_type,
        validation_findings=val_a.findings,
        cp_validation_findings=val_b.findings,
        red_flags=rf.flags,
        evidence_gaps=ev_a.gaps,
        cp_evidence_gaps=ev_b.gaps,
        conflict_findings=conflicts.conflicts,
        classification_tags=classification.tags,
        opinion_conditions=opinion_conditions,
        opinion_grade=opinion.overall_grade,
        signature_blocked=bool(opinion.signature_blocked_reason),
    )

    console.print()
    console.print(Panel(
        cl.summary(),
        title=f"EXECUTION CHECKLIST -- {cl.open_count} open / {len(cl.items)} total",
        border_style="red" if cl.critical_open > 0 else "yellow" if cl.open_count > 0 else "green",
    ))

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cl.summary(), encoding="utf-8")
        console.print(f"\n[green]{ICON_CHECK}[/green] Checklist saved to: {out_path}")

    # Audit
    try:
        audit = AuditLogger()
        audit.log_run(operation="checklist", entity=entity_data, counterparty=cp_data,
                      transaction_type=transaction_type)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# dossier
# ---------------------------------------------------------------------------

@main.command("dossier")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", default=None, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", default=None)
@click.option("--save", "save_flag", is_flag=True, help="Save dossier to output/dossiers/")
def dossier_cmd(entity: str, counterparty: str | None, transaction_type: str | None, save_flag: bool):
    """Build a counterparty risk dossier."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty) if counterparty else None

    builder = DossierBuilder()
    dossier = builder.build(entity_data, cp_data, transaction_type)

    grade_color = {"A": "green", "B": "blue", "C": "yellow", "D": "red", "F": "bold red"}

    console.print()
    console.print(Panel(
        dossier.render(),
        title=f"COUNTERPARTY DOSSIER -- {dossier.legal_name} (Grade: {dossier.risk_rating.grade})",
        border_style=grade_color.get(dossier.risk_rating.grade, "white"),
    ))

    if save_flag:
        path = dossier.save()
        console.print(f"\n[green]{ICON_CHECK}[/green] Dossier saved to: {path}")

    # Audit
    try:
        audit = AuditLogger()
        audit.log_run(operation="dossier", entity=entity_data)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# deal-room
# ---------------------------------------------------------------------------

@main.command("deal-room")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
def deal_room_cmd(entity: str, counterparty: str, transaction_type: str):
    """Package a complete deal room (agreement + opinion + checklist + dossiers)."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    console.print("\n[bold]Packaging deal room...[/bold]")
    console.print("  Running all analysis layers...")

    packager = DealRoomPackager()
    results = packager.package(entity_data, cp_data, transaction_type)

    room_path = results["deal_room_path"]
    manifest = results["manifest"]

    console.print()
    summary_lines = [
        f"Deal Room: {room_path.name}",
        f"Files: {len(manifest.get('files', {}))}",
        "",
        f"Opinion Grade:     {manifest.get('opinion_grade', 'N/A')}",
        f"Signature Ready:   {manifest.get('signature_ready', 'N/A')}",
        f"Risk Tier:         {manifest.get('risk_tier', 'N/A')}",
        f"Risk Score:        {manifest.get('risk_score', 'N/A')}",
        f"Checklist Items:   {manifest.get('checklist_items', 'N/A')}",
        f"Clear to Close:    {manifest.get('clear_to_close', 'N/A')}",
        "",
        "Contents:",
    ]
    for key, filename in manifest.get("files", {}).items():
        summary_lines.append(f"  {ICON_CHECK} {filename}")

    console.print(Panel(
        "\n".join(summary_lines),
        title="DEAL ROOM PACKAGED",
        border_style="green",
    ))
    console.print(f"\n[green]{ICON_CHECK}[/green] Deal room: {room_path}")


# ---------------------------------------------------------------------------
# deal-create
# ---------------------------------------------------------------------------

@main.command("deal-create")
@click.option("--deal-id", "-d", required=True, help="Unique deal identifier.")
@click.option("--entity", "-e", required=True, type=click.Path(exists=True))
@click.option("--counterparty", "-c", required=True, type=click.Path(exists=True))
@click.option("--transaction-type", "-t", required=True)
def deal_create_cmd(deal_id: str, entity: str, counterparty: str, transaction_type: str):
    """Create a new deal in DRAFT state."""
    entity_data = load_entity(entity)
    cp_data = load_entity(counterparty)

    manager = DealLifecycleManager()
    deal = manager.create_deal(
        deal_id=deal_id,
        transaction_type=transaction_type,
        entity_name=entity_data.get("legal_name", "UNKNOWN"),
        counterparty_name=cp_data.get("legal_name", "UNKNOWN"),
    )

    console.print()
    console.print(Panel(
        deal.summary(),
        title=f"DEAL CREATED -- {deal.deal_id}",
        border_style="blue",
    ))


# ---------------------------------------------------------------------------
# deal-advance
# ---------------------------------------------------------------------------

@main.command("deal-advance")
@click.option("--deal-id", "-d", required=True, help="Deal identifier.")
@click.option("--to-state", "-s", required=True,
              type=click.Choice(["REVIEW", "CONDITIONALLY_APPROVED", "APPROVED",
                                 "BLOCKED", "EXECUTED", "CLOSED"]))
@click.option("--actor", "-a", default="cli-user", help="Who is performing this transition.")
@click.option("--reason", "-r", default="", help="Reason for transition.")
@click.option("--compliance-score", type=int, default=None)
@click.option("--opinion-grade", default=None)
@click.option("--checklist-clear", is_flag=True, default=False)
@click.option("--risk-tier", default=None)
@click.option("--force", is_flag=True, help="Override gate checks.")
def deal_advance_cmd(
    deal_id: str, to_state: str, actor: str, reason: str,
    compliance_score: int | None, opinion_grade: str | None,
    checklist_clear: bool, risk_tier: str | None, force: bool,
):
    """Advance a deal to the next lifecycle state."""
    manager = DealLifecycleManager()

    try:
        deal = manager.transition(
            deal_id, to_state,
            actor=actor, reason=reason,
            compliance_score=compliance_score,
            opinion_grade=opinion_grade,
            checklist_clear=checklist_clear or None,
            risk_tier=risk_tier,
            force=force,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{ICON_CROSS} {e}[/red]")
        sys.exit(1)

    state_color = {
        "DRAFT": "blue", "REVIEW": "yellow", "CONDITIONALLY_APPROVED": "yellow",
        "APPROVED": "green", "BLOCKED": "red", "EXECUTED": "green", "CLOSED": "dim",
    }

    console.print()
    console.print(Panel(
        deal.summary(),
        title=f"DEAL {deal.deal_id} -- {deal.state}",
        border_style=state_color.get(deal.state, "white"),
    ))


# ---------------------------------------------------------------------------
# deal-status
# ---------------------------------------------------------------------------

@main.command("deal-status")
@click.option("--deal-id", "-d", default=None, help="Show specific deal. If omitted, lists all deals.")
def deal_status_cmd(deal_id: str | None):
    """Show deal lifecycle status."""
    manager = DealLifecycleManager()

    if deal_id:
        try:
            deal = manager.load_deal(deal_id)
        except FileNotFoundError:
            console.print(f"[red]{ICON_CROSS} Deal not found: {deal_id}[/red]")
            sys.exit(1)

        state_color = {
            "DRAFT": "blue", "REVIEW": "yellow", "CONDITIONALLY_APPROVED": "yellow",
            "APPROVED": "green", "BLOCKED": "red", "EXECUTED": "green", "CLOSED": "dim",
        }
        console.print()
        console.print(Panel(
            deal.summary(),
            title=f"DEAL {deal.deal_id} -- {deal.state}",
            border_style=state_color.get(deal.state, "white"),
        ))
    else:
        deals = manager.list_deals()
        if not deals:
            console.print(f"\n{ICON_WARN} No deals found.")
            return

        table = Table(title="Active Deals")
        table.add_column("Deal ID", style="cyan")
        table.add_column("State", style="yellow")
        table.add_column("Type", style="green")
        table.add_column("Entity", style="dim")
        table.add_column("Counterparty", style="dim")
        table.add_column("Updated", style="dim")

        for d in deals:
            table.add_row(
                d.deal_id, d.state, d.transaction_type,
                d.entity_name, d.counterparty_name, d.updated_at,
            )

        console.print()
        console.print(table)


# ---------------------------------------------------------------------------
# settlement-path
# ---------------------------------------------------------------------------

@main.command("settlement-path")
@click.option("-e", "--entity", required=True, help="Entity YAML file")
@click.option("-c", "--counterparty", required=True, help="Counterparty YAML file")
@click.option("--currency", default="USD", help="Settlement currency")
def settlement_path(entity, counterparty, currency):
    """Map and validate the cross-border settlement path."""
    e = load_entity(Path(entity))
    cp = load_entity(Path(counterparty))

    engine = CorrespondentBankingEngine()
    path = engine.resolve_settlement_path(e, cp, currency=currency)

    # Learn from this deal
    intel = JurisdictionIntelEngine()
    learnings = intel.learn_from_deal(e, cp)
    intel.save()

    style = "green" if path.is_valid else "red"
    console.print(Panel(path.summary(), title="SETTLEMENT PATH", border_style=style))

    if learnings:
        console.print("\n[cyan]Jurisdiction Intelligence Updated:[/cyan]")
        for jx, notes in learnings.items():
            for note in notes:
                console.print(f"  {ICON_CHECK} [{jx}] {note}")


# ---------------------------------------------------------------------------
# cap-structure
# ---------------------------------------------------------------------------

@main.command("cap-structure")
@click.option("-n", "--name", required=True, help="Deal/JV name")
@click.option("--total", type=float, default=None, help="Total commitment amount")
@click.option("--currency", default="USD", help="Currency")
@click.option("--save", "save_flag", is_flag=True, help="Save to disk")
def cap_structure(name, total, currency, save_flag):
    """Build and display a capital allocation structure."""
    # Interactive: ask for parties
    parties = []
    console.print("[bold]Enter capital commitments[/bold] (empty name to finish):")
    idx = 1
    while True:
        party_name = click.prompt(f"  Party {idx} name", default="", show_default=False)
        if not party_name:
            break
        pct = click.prompt(f"  {party_name} commitment %", type=float)
        ptype = click.prompt(
            f"  {party_name} type",
            type=click.Choice(["uhnwi", "wealth_manager", "family_office", "gp", "partner", "entity"]),
            default="partner",
        )
        ctype = click.prompt(
            f"  {party_name} contribution",
            type=click.Choice(["cash", "in_kind", "mixed"]),
            default="cash",
        )
        in_kind_desc = None
        if ctype in ("in_kind", "mixed"):
            in_kind_desc = click.prompt(f"  {party_name} in-kind description")

        parties.append({
            "party_name": party_name,
            "party_type": ptype,
            "commitment_percentage": pct,
            "contribution_type": ctype,
            "in_kind_description": in_kind_desc,
            "commitment_amount": total * pct / 100.0 if total else None,
        })
        idx += 1

    builder = CapitalStructureBuilder()
    structure = builder.build_jv_structure(
        deal_name=name,
        parties=parties,
        total_commitment=total,
        currency=currency,
    )

    issues = structure.validate()
    style = "green" if not issues else "yellow"
    console.print(Panel(structure.summary(), title="CAPITAL STRUCTURE", border_style=style))

    if save_flag:
        path = builder.save(structure)
        console.print(f"\n{ICON_CHECK} Saved: {path}")


# ---------------------------------------------------------------------------
# jurisdiction
# ---------------------------------------------------------------------------

@main.command("jurisdiction")
@click.option("-j", "--code", default=None, help="Jurisdiction code (US, VN, CH, etc.)")
@click.option("-e", "--entity", default=None, help="Learn from entity YAML file")
@click.option("--list", "list_all", is_flag=True, help="List all known jurisdictions")
def jurisdiction_cmd(code, entity, list_all):
    """Query or update the jurisdiction intelligence database."""
    intel = JurisdictionIntelEngine()

    if entity:
        e = load_entity(Path(entity))
        learnings = intel.learn_from_entity(e)
        intel.save()
        if learnings:
            console.print("[green]New intelligence learned:[/green]")
            for note in learnings:
                console.print(f"  {ICON_CHECK} {note}")
        else:
            console.print("[dim]No new intelligence from this entity.[/dim]")

        # Show the jurisdiction profile
        jx = e.get("entity", e).get("jurisdiction", "")[:2]
        profile = intel.get_profile(jx)
        if profile:
            console.print(Panel(profile.summary(), title=f"JURISDICTION: {jx}"))
        return

    if list_all:
        table = Table(title="Known Jurisdictions")
        table.add_column("Code", style="bold")
        table.add_column("Name")
        table.add_column("Region")
        table.add_column("FATF")
        table.add_column("FX Controls")
        table.add_column("Deals")
        for p in intel.list_profiles():
            fx = ICON_WARN if p.banking.fx_controls else ICON_CHECK
            table.add_row(
                p.jurisdiction_code,
                p.jurisdiction_name,
                p.region,
                p.fatf_status or "?",
                fx,
                str(p.deal_count),
            )
        console.print(table)
        return

    if code:
        profile = intel.get_profile(code.upper()[:2])
        if profile:
            console.print(Panel(profile.summary(), title=f"JURISDICTION: {code.upper()}"))
        else:
            console.print(f"[red]Unknown jurisdiction: {code}[/red]")
        return

    # Default: list all
    console.print("[dim]Use --list to show all, -j CODE for specific, -e ENTITY to learn[/dim]")


# ---------------------------------------------------------------------------
# list commands
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# governance
# ---------------------------------------------------------------------------

@main.command("governance")
@click.option("-n", "--name", required=True, help="Deal/JV name")
@click.option("-e", "--entity", default=None, help="Entity YAML to load governance from")
@click.option("--template", is_flag=True, help="Use institutional template")
@click.option("--split", default="50/50", help="Ownership split")
@click.option("--save", "save_flag", is_flag=True, help="Save to disk")
def governance_cmd(name, entity, template, split, save_flag):
    """Build and display a governance framework."""
    builder = GovernanceBuilder()

    if entity:
        e = load_entity(Path(entity))
        framework = builder.build_from_entity(e, name)
    elif template:
        framework = builder.build_institutional(name, split)
    else:
        framework = builder.build_institutional(name, split)

    issues = framework.validate()
    style = "green" if framework.is_compliant else "yellow"
    console.print(Panel(framework.summary(), title="GOVERNANCE FRAMEWORK", border_style=style))

    if save_flag:
        path = builder.save(framework)
        console.print(f"\n{ICON_CHECK} Saved: {path}")


# ---------------------------------------------------------------------------
# fund-flow
# ---------------------------------------------------------------------------

@main.command("fund-flow")
@click.option("-c", "--cap-structure", required=True, help="Path to capital structure JSON")
@click.option("--save", "save_flag", is_flag=True, help="Save to disk")
def fund_flow_cmd(cap_structure, save_flag):
    """Display fund flow status from a capital structure."""
    cs_path = Path(cap_structure)
    if not cs_path.exists():
        console.print(f"{ICON_CROSS} File not found: {cs_path}", style="red")
        return

    cs_data = json.loads(cs_path.read_text(encoding="utf-8"))
    builder = FundFlowBuilder()
    ledger = builder.build_from_capital_structure(cs_data)

    style = "green" if not ledger.validate() else "yellow"
    console.print(Panel(ledger.summary(), title="FUND FLOW LEDGER", border_style=style))

    if save_flag:
        path = builder.save(ledger)
        console.print(f"\n{ICON_CHECK} Saved: {path}")


# ---------------------------------------------------------------------------
# compliance-pkg
# ---------------------------------------------------------------------------

@main.command("compliance-pkg")
@click.option("-n", "--name", required=True, help="Deal name")
@click.option("-e", "--entities", required=True, multiple=True, help="Entity YAML paths (repeat -e for each)")
@click.option("-c", "--cap-structure", default=None, help="Path to capital structure JSON")
@click.option("--save", "save_flag", is_flag=True, help="Save to disk")
def compliance_pkg_cmd(name, entities, cap_structure, save_flag):
    """Generate a full compliance package for a deal."""
    entity_paths = [Path(e) for e in entities]
    for ep in entity_paths:
        if not ep.exists():
            console.print(f"{ICON_CROSS} Entity not found: {ep}", style="red")
            return

    cs_path = Path(cap_structure) if cap_structure else None

    generator = CompliancePackageGenerator()
    package = generator.generate(
        deal_name=name,
        entity_paths=entity_paths,
        cap_structure_path=cs_path,
    )

    status_style = {
        "CLEAR": "green",
        "CONDITIONAL": "yellow",
        "REQUIRES_ACTION": "red",
    }.get(package.compliance_status, "white")

    console.print(Panel(package.summary(), title="COMPLIANCE PACKAGE", border_style=status_style))

    if save_flag:
        path = generator.save(package)
        console.print(f"\n{ICON_CHECK} Saved: {path}")


# ---------------------------------------------------------------------------
# deal-entities
# ---------------------------------------------------------------------------

@main.command("deal-entities")
def deal_entities_cmd():
    """List all entity profiles in the system."""
    entities_dir = Path("data/entities")
    if not entities_dir.exists():
        console.print(f"{ICON_CROSS} No entities directory found", style="red")
        return

    table = Table(title="Deal Entity Profiles")
    table.add_column("File", style="cyan")
    table.add_column("Legal Name", style="green")
    table.add_column("Jurisdiction", style="yellow")
    table.add_column("Type", style="dim")
    table.add_column("SWIFT", style="dim")

    for f in sorted(entities_dir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        try:
            e = load_entity(f)
            swift = e.get("regulatory_status", {}).get("swift_eligible", None)
            swift_str = "YES" if swift else ("NO" if swift is False else "-")
            table.add_row(
                f.name,
                e.get("legal_name", "?"),
                e.get("jurisdiction", "?"),
                e.get("entity_type", "?"),
                swift_str,
            )
        except Exception as exc:
            table.add_row(f.name, f"ERROR: {exc}", "", "", "")

    console.print(table)


# ---------------------------------------------------------------------------
# mtn-validate
# ---------------------------------------------------------------------------

@main.command("mtn-validate")
@click.option("-i", "--issuer", required=True, help="Path to issuer entity YAML (with mtn_program section)")
@click.option("-s", "--spv", default=None, help="Path to collateral/SPV entity YAML for cross-referencing")
@click.option("--save", "do_save", is_flag=True, help="Save validation report to JSON")
def mtn_validate_cmd(issuer: str, spv: str | None, do_save: bool):
    """Validate MTN program structure and readiness."""
    issuer_entity = load_entity(Path(issuer))
    spv_entity = load_entity(Path(spv)) if spv else None

    validator = MTNProgramValidator()
    report = validator.validate(issuer_entity, spv_entity)

    console.print(Panel(report.summary(), title="MTN PROGRAM VALIDATION", border_style="cyan"))

    if do_save:
        path = validator.save(report)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# collateral-check
# ---------------------------------------------------------------------------

@main.command("collateral-check")
@click.option("-s", "--spv", required=True, help="Path to collateral/SPV entity YAML")
@click.option("-i", "--issuer", default=None, help="Path to issuer entity YAML for cross-referencing")
@click.option("--save", "do_save", is_flag=True, help="Save verification report to JSON")
def collateral_check_cmd(spv: str, issuer: str | None, do_save: bool):
    """Verify collateral/SPV integrity."""
    spv_entity = load_entity(Path(spv))
    issuer_entity = load_entity(Path(issuer)) if issuer else None

    verifier = CollateralVerifier()
    report = verifier.verify(spv_entity, issuer_entity)

    console.print(Panel(report.summary(), title="COLLATERAL VERIFICATION", border_style="cyan"))

    if do_save:
        path = verifier.save(report)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# deal-ready
# ---------------------------------------------------------------------------

@main.command("deal-ready")
@click.option("-n", "--name", "deal_name", required=True, help="Deal name")
@click.option("-i", "--issuer", default=None, help="Path to issuer entity YAML")
@click.option("-s", "--spv", default=None, help="Path to collateral/SPV entity YAML")
@click.option("-e", "--entity", "extra_entities", multiple=True, help="Additional entity YAML paths")
@click.option("--save", "do_save", is_flag=True, help="Save readiness report to JSON")
def deal_ready_cmd(deal_name: str, issuer: str | None, spv: str | None, extra_entities: tuple, do_save: bool):
    """Full deal readiness assessment."""
    engine = DealReadinessEngine()
    report = engine.assess(
        deal_name=deal_name,
        issuer_path=Path(issuer) if issuer else None,
        spv_path=Path(spv) if spv else None,
        additional_entities=[Path(e) for e in extra_entities] if extra_entities else None,
    )

    # Use color based on verdict
    color = {
        "READY": "green",
        "CONDITIONAL": "yellow",
        "NOT_READY": "red",
    }.get(report.verdict, "white")

    console.print(Panel(report.summary(), title="DEAL READINESS", border_style=color))

    if do_save:
        path = engine.save(report)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# deal-governance
# ---------------------------------------------------------------------------

@main.command("deal-governance")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-e", "--entity", "entity_paths", multiple=True, help="Entity YAML path(s)")
@click.option("--save", "do_save", is_flag=True, help="Save governance report to JSON")
def deal_governance_cmd(deal_name: str, entity_paths: tuple, do_save: bool):
    """Assess deal-level governance framework."""
    engine = DealGovernanceEngine()
    report = engine.assess(
        deal_name=deal_name,
        entity_paths=[Path(e) for e in entity_paths] if entity_paths else None,
    )

    color = "green" if report.is_compliant else ("yellow" if report.grade in ("B", "C") else "red")
    console.print(Panel(report.summary(), title="DEAL GOVERNANCE", border_style=color))

    if do_save:
        path = engine.save(report)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# risk-score
# ---------------------------------------------------------------------------

@main.command("risk-score")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-e", "--entity", "entity_paths", multiple=True, help="Entity YAML path(s)")
@click.option("--save", "do_save", is_flag=True, help="Save risk score to JSON")
def risk_score_cmd(deal_name: str, entity_paths: tuple, do_save: bool):
    """Multi-factor counterparty risk score."""
    engine = CounterpartyRiskEngine()
    report = engine.score(
        deal_name=deal_name,
        entity_paths=[Path(e) for e in entity_paths] if entity_paths else None,
    )

    color_map = {"A": "green", "B": "green", "C": "yellow", "D": "red", "F": "red"}
    color = color_map.get(report.grade, "white")
    console.print(Panel(report.summary(), title="COUNTERPARTY RISK SCORE", border_style=color))

    if do_save:
        path = engine.save(report)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# closing-tracker
# ---------------------------------------------------------------------------

@main.command("closing-tracker")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-i", "--issuer", default=None, help="Path to issuer entity YAML")
@click.option("-s", "--spv", default=None, help="Path to SPV entity YAML")
@click.option("-e", "--entity", "extra_entities", multiple=True, help="Additional entity YAML(s)")
@click.option("-d", "--closing-date", "closing_date", default="", help="Target closing date (YYYY-MM-DD)")
@click.option("--save", "do_save", is_flag=True, help="Save tracker to JSON")
def closing_tracker_cmd(
    deal_name: str, issuer: str | None, spv: str | None,
    extra_entities: tuple, closing_date: str, do_save: bool,
):
    """Generate conditions precedent tracker."""
    engine = ClosingTrackerEngine()
    tracker = engine.generate(
        deal_name=deal_name,
        issuer_path=Path(issuer) if issuer else None,
        spv_path=Path(spv) if spv else None,
        additional_entities=[Path(e) for e in extra_entities] if extra_entities else None,
        target_closing_date=closing_date,
    )

    color = "green" if tracker.closing_ready else ("yellow" if tracker.completion_pct > 0 else "red")
    console.print(Panel(tracker.summary(), title="CLOSING TRACKER", border_style=color))

    if do_save:
        path = engine.save(tracker)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# settlement-onboard
# ---------------------------------------------------------------------------

@main.command("settlement-onboard")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-e", "--entity", "entity_paths", multiple=True, help="Entity YAML path(s)")
@click.option("--save", "do_save", is_flag=True, help="Save onboarding plan to JSON")
def settlement_onboard_cmd(deal_name: str, entity_paths: tuple, do_save: bool):
    """Detect banking gaps and generate onboarding plan."""
    engine = SettlementOnboardingEngine()
    plan = engine.assess(
        deal_name=deal_name,
        entity_paths=[Path(e) for e in entity_paths] if entity_paths else None,
    )

    color = "green" if plan.settlement_ready else "red"
    console.print(Panel(plan.summary(), title="SETTLEMENT ONBOARDING", border_style=color))

    if do_save:
        path = engine.save(plan)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# wire-instructions
# ---------------------------------------------------------------------------

@main.command("wire-instructions")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-o", "--originator", required=True, help="Originator entity YAML")
@click.option("-b", "--beneficiary", required=True, help="Beneficiary entity YAML")
@click.option("-a", "--amount", default=0.0, type=float, help="Wire amount")
@click.option("-c", "--currency", default="USD", help="Currency (default: USD)")
@click.option("-p", "--purpose", default="", help="Wire purpose")
@click.option("--save", "do_save", is_flag=True, help="Save wire package to JSON")
def wire_instructions_cmd(
    deal_name: str, originator: str, beneficiary: str,
    amount: float, currency: str, purpose: str, do_save: bool,
):
    """Generate institutional wire instruction packages."""
    engine = WireInstructionEngine()
    pkg = engine.generate(
        deal_name=deal_name,
        originator_path=Path(originator),
        beneficiary_path=Path(beneficiary),
        amount=amount,
        currency=currency,
        purpose=purpose,
    )

    color = "green" if pkg.all_clear else "red"
    console.print(Panel(pkg.summary(), title="WIRE INSTRUCTIONS", border_style=color))

    # Show detailed instruction
    for wi in pkg.instructions:
        border = "green" if not wi.is_blocked else "red"
        console.print(Panel(wi.formatted(), title=wi.instruction_id, border_style=border))

    if do_save:
        path = engine.save(pkg)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# signing-ceremony
# ---------------------------------------------------------------------------

@main.command("signing-ceremony")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-e", "--entity", "entity_paths", multiple=True, help="Entity YAML path(s)")
@click.option("-d", "--document", "documents", multiple=True, help="Document type(s) to sign")
@click.option("--save", "do_save", is_flag=True, help="Save ceremony to JSON")
def signing_ceremony_cmd(
    deal_name: str, entity_paths: tuple, documents: tuple, do_save: bool,
):
    """Prepare deal signing with authority validation."""
    engine = SigningCeremonyEngine()
    ceremony = engine.prepare(
        deal_name=deal_name,
        entity_paths=[Path(e) for e in entity_paths] if entity_paths else None,
        documents=list(documents) if documents else None,
    )

    color = "green" if ceremony.all_authorized else ("yellow" if ceremony.authority_issues else "blue")
    console.print(Panel(ceremony.summary(), title="SIGNING CEREMONY", border_style=color))

    if do_save:
        path = engine.save(ceremony)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# deal-dashboard
# ---------------------------------------------------------------------------

@main.command("deal-dashboard")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-i", "--issuer", default=None, help="Path to issuer entity YAML")
@click.option("-s", "--spv", default=None, help="Path to SPV entity YAML")
@click.option("-e", "--entity", "extra_entities", multiple=True, help="Additional entity YAML(s)")
@click.option("--save", "do_save", is_flag=True, help="Save dashboard to JSON")
def deal_dashboard_cmd(
    deal_name: str, issuer: str | None, spv: str | None,
    extra_entities: tuple, do_save: bool,
):
    """Unified deal status dashboard (all engines)."""
    engine = DealDashboardEngine()
    dashboard = engine.generate(
        deal_name=deal_name,
        issuer_path=Path(issuer) if issuer else None,
        spv_path=Path(spv) if spv else None,
        additional_entities=[Path(e) for e in extra_entities] if extra_entities else None,
    )

    color_map = {"GREEN": "green", "AMBER": "yellow", "RED": "red", "GREY": "dim"}
    color = color_map.get(dashboard.overall_rag, "white")
    console.print(Panel(dashboard.summary(), title="DEAL DASHBOARD", border_style=color))

    if do_save:
        path = engine.save(dashboard)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# escrow-plan
# ---------------------------------------------------------------------------

@main.command("escrow-plan")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-e", "--entity", "entity_paths", multiple=True, help="Entity YAML path(s)")
@click.option("-c", "--currency", default="USD", help="Escrow currency (default: USD)")
@click.option("-a", "--amount", default=0.0, type=float, help="Escrow amount")
@click.option("--save", "do_save", is_flag=True, help="Save escrow plan to JSON")
def escrow_plan_cmd(
    deal_name: str, entity_paths: tuple, currency: str, amount: float, do_save: bool,
):
    """Build escrow & settlement rail plan."""
    engine = EscrowEngine()
    plan = engine.build(
        deal_name=deal_name,
        entity_paths=[Path(e) for e in entity_paths] if entity_paths else None,
        escrow_currency=currency,
        escrow_amount=amount,
    )

    color = "green" if plan.overall_valid else "red"
    console.print(Panel(plan.summary(), title="ESCROW & SETTLEMENT RAIL PLAN", border_style=color))

    if do_save:
        path = engine.save(plan)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# banking-resolve
# ---------------------------------------------------------------------------

@main.command("banking-resolve")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-e", "--entity", "entity_paths", multiple=True, help="Entity YAML path(s)")
@click.option("--save", "do_save", is_flag=True, help="Save resolution plan to JSON")
def banking_resolve_cmd(deal_name: str, entity_paths: tuple, do_save: bool):
    """Resolve banking gaps across deal group."""
    engine = BankingResolverEngine()
    plan = engine.resolve(
        deal_name=deal_name,
        entity_paths=[Path(e) for e in entity_paths] if entity_paths else None,
    )

    color = "green" if plan.all_resolved else ("yellow" if plan.critical_entities == 0 else "red")
    console.print(Panel(plan.summary(), title="BANKING RESOLUTION", border_style=color))

    if do_save:
        path = engine.save(plan)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


# ---------------------------------------------------------------------------
# cp-status
# ---------------------------------------------------------------------------

@main.command("cp-status")
@click.option("-n", "--name", "deal_name", required=True, help="Deal group name")
@click.option("-i", "--issuer", default=None, help="Path to issuer entity YAML")
@click.option("-s", "--spv", default=None, help="Path to SPV entity YAML")
@click.option("-e", "--entity", "extra_entities", multiple=True, help="Additional entity YAML(s)")
@click.option("--save", "do_save", is_flag=True, help="Save resolution report to JSON")
def cp_status_cmd(
    deal_name: str, issuer: str | None, spv: str | None,
    extra_entities: tuple, do_save: bool,
):
    """Auto-resolve closing conditions from evidence & entity data."""
    engine = CPResolutionEngine()
    report = engine.resolve(
        deal_name=deal_name,
        issuer_path=Path(issuer) if issuer else None,
        spv_path=Path(spv) if spv else None,
        additional_entities=[Path(e) for e in extra_entities] if extra_entities else None,
    )

    if report.remaining_open == 0:
        color = "green"
    elif report.auto_resolved > 0:
        color = "yellow"
    else:
        color = "red"
    console.print(Panel(report.summary(), title="CP RESOLUTION STATUS", border_style=color))

    if do_save:
        path = engine.save(report)
        console.print(f"\n{ICON_CHECK} Saved: {path}", style="green")


@main.command("list-types")
def list_types():
    """List available transaction types."""
    types = load_transaction_types()

    table = Table(title="Available Transaction Types")
    table.add_column("Key", style="cyan")
    table.add_column("Display Name", style="green")
    table.add_column("Category", style="yellow")
    table.add_column("Modules", style="dim")

    for key, tx in types.items():
        table.add_row(
            key,
            tx.get("display_name", ""),
            tx.get("category", ""),
            str(len(tx.get("required_modules", []))),
        )

    console.print(table)


@main.command("list-jurisdictions")
def list_jurisdictions():
    """List supported jurisdictions."""
    codes = get_all_jurisdiction_codes()

    table = Table(title="Supported Jurisdictions")
    table.add_column("Code", style="cyan")
    table.add_column("Name", style="green")

    for code in codes:
        table.add_row(code, get_jurisdiction_full_name(code))

    console.print(table)


@main.command("list-modules")
def list_modules():
    """List available contract modules."""
    modules = list_contract_modules()

    table = Table(title="Contract Modules")
    table.add_column("#", style="dim")
    table.add_column("Module", style="cyan")

    for i, mod in enumerate(modules, 1):
        table.add_row(str(i), mod)

    console.print(table)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
