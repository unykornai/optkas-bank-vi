"""
Deal Room Packager
===================
Packages an entire deal into a single exportable folder.

A deal room is what gets sent to the counterparty's counsel,
handed to the fund admin, or delivered to the board.

Contents of a deal room:
  /deal_room_{slug}_{timestamp}/
    01_agreement.md              — Assembled agreement
    02_legal_opinion.txt         — Full legal opinion
    03_execution_checklist.txt   — Pre-closing checklist
    04_entity_dossier.txt        — Entity risk dossier
    05_counterparty_dossier.txt  — Counterparty risk dossier
    06_deal_classification.json  — Risk classification
    07_policy_snapshot.json      — Policy applied at generation
    08_audit_record.json         — Audit trail entry
    _manifest.json               — Index of all files

This is the difference between sending an email with an attachment
and delivering a deal package.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schema_loader import ROOT_DIR, load_transaction_type
from engine.assembler import DocumentAssembler
from engine.validator import ComplianceValidator
from engine.red_flags import RedFlagDetector
from engine.legal_opinion import LegalOpinionGenerator
from engine.evidence_validator import EvidenceValidator
from engine.conflict_matrix import ConflictMatrix
from engine.deal_classifier import DealClassifier
from engine.execution_checklist import ChecklistBuilder
from engine.counterparty_dossier import DossierBuilder
from engine.policy_engine import PolicyEngine
from engine.audit_logger import AuditLogger


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEAL_ROOMS_DIR = ROOT_DIR / "output" / "deal_rooms"


# ---------------------------------------------------------------------------
# Deal Room
# ---------------------------------------------------------------------------

class DealRoomPackager:
    """
    Runs every engine layer and packages all outputs into a single folder.
    """

    def package(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any],
        transaction_type: str,
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        """
        Build and export a complete deal room.

        Returns:
            Dict with keys: 'deal_room_path', 'manifest', and individual
            component results.
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        a_short = entity.get("trade_name", entity.get("legal_name", "PartyA"))
        b_short = counterparty.get("trade_name", counterparty.get("legal_name", "PartyB"))
        slug = (
            f"{transaction_type}_{a_short}_{b_short}"
            .replace(" ", "_").replace(",", "").replace(".", "")
        )

        room_dir = (output_dir or DEAL_ROOMS_DIR) / f"deal_room_{slug}_{timestamp}"
        room_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {
            "deal_room_version": "1.0",
            "created_at": now.isoformat(timespec="seconds"),
            "transaction_type": transaction_type,
            "entity": entity.get("legal_name", "UNKNOWN"),
            "counterparty": counterparty.get("legal_name", "UNKNOWN"),
            "files": {},
        }

        results: dict[str, Any] = {"deal_room_path": room_dir, "manifest": manifest}

        # --- Load transaction definition ---
        try:
            tx_def = load_transaction_type(transaction_type)
        except Exception:
            tx_def = {}

        # --- 1. Agreement ---
        assembler = DocumentAssembler()
        document = assembler.assemble(entity, counterparty, transaction_type)

        # Append compliance appendices
        validator = ComplianceValidator()
        val_a = validator.validate_entity(entity, transaction_type, counterparty)
        val_b = validator.validate_entity(counterparty, transaction_type, entity)

        detector = RedFlagDetector()
        rf = detector.scan(entity, counterparty, transaction_type)

        document += "\n\n---\n\n"
        document += "# APPENDIX A -- COMPLIANCE CHECKLIST\n\n"
        document += val_a.summary() + "\n\n" + val_b.summary()
        document += "\n\n---\n\n"
        document += "# APPENDIX B -- RED FLAG SUMMARY\n\n"
        document += rf.summary()

        agreement_path = room_dir / "01_agreement.md"
        agreement_path.write_text(document, encoding="utf-8")
        manifest["files"]["agreement"] = agreement_path.name
        results["agreement_path"] = agreement_path

        # --- 2. Legal Opinion ---
        opinion_gen = LegalOpinionGenerator()
        opinion = opinion_gen.generate(entity, counterparty, transaction_type)
        rendered_opinion = opinion.render()

        opinion_path = room_dir / "02_legal_opinion.txt"
        opinion_path.write_text(rendered_opinion, encoding="utf-8")
        manifest["files"]["legal_opinion"] = opinion_path.name
        manifest["opinion_grade"] = opinion.overall_grade
        manifest["signature_ready"] = opinion.signature_ready
        results["opinion"] = opinion

        # --- 3. Execution Checklist ---
        evidence = EvidenceValidator()
        ev_a = evidence.validate_entity_evidence(entity, counterparty)
        ev_b = evidence.validate_entity_evidence(counterparty, entity)

        conflict_matrix = ConflictMatrix()
        jur_a = entity.get("jurisdiction", "").split("-")[0].upper()
        jur_b = counterparty.get("jurisdiction", "").split("-")[0].upper()
        conflicts = conflict_matrix.analyze(jur_a, jur_b, transaction_type, entity, counterparty)

        classifier = DealClassifier()
        classification = classifier.classify(entity, counterparty, transaction_type, tx_def)

        # Gather opinion conditions
        opinion_conditions = []
        for sec in opinion.sections:
            opinion_conditions.extend(sec.conditions)

        builder = ChecklistBuilder()
        checklist = builder.build(
            entity, counterparty, transaction_type,
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

        checklist_path = room_dir / "03_execution_checklist.txt"
        checklist_path.write_text(checklist.summary(), encoding="utf-8")
        manifest["files"]["execution_checklist"] = checklist_path.name
        manifest["checklist_items"] = len(checklist.items)
        manifest["clear_to_close"] = checklist.is_clear_to_close
        results["checklist"] = checklist

        # --- 4. Entity Dossier ---
        dossier_builder = DossierBuilder()
        entity_dossier = dossier_builder.build(entity, counterparty, transaction_type)

        entity_dossier_path = room_dir / "04_entity_dossier.txt"
        entity_dossier_path.write_text(entity_dossier.render(), encoding="utf-8")
        manifest["files"]["entity_dossier"] = entity_dossier_path.name
        results["entity_dossier"] = entity_dossier

        # --- 5. Counterparty Dossier ---
        cp_dossier = dossier_builder.build(counterparty, entity, transaction_type)

        cp_dossier_path = room_dir / "05_counterparty_dossier.txt"
        cp_dossier_path.write_text(cp_dossier.render(), encoding="utf-8")
        manifest["files"]["counterparty_dossier"] = cp_dossier_path.name
        results["counterparty_dossier"] = cp_dossier

        # --- 6. Deal Classification ---
        classification_path = room_dir / "06_deal_classification.json"
        classification_path.write_text(
            json.dumps(classification.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        manifest["files"]["deal_classification"] = classification_path.name
        manifest["risk_tier"] = classification.risk_tier
        manifest["risk_score"] = classification.risk_score
        results["classification"] = classification

        # --- 7. Policy Snapshot ---
        policy = PolicyEngine()
        policy_snapshot = {
            "version": policy.version,
            "execution_tier": policy.execution_tier,
            "tier_label": policy.tier_label,
            "captured_at": now.isoformat(timespec="seconds"),
        }
        policy_path = room_dir / "07_policy_snapshot.json"
        policy_path.write_text(
            json.dumps(policy_snapshot, indent=2), encoding="utf-8",
        )
        manifest["files"]["policy_snapshot"] = policy_path.name
        results["policy_snapshot"] = policy_snapshot

        # --- 8. Audit Record ---
        try:
            audit = AuditLogger(logs_dir=room_dir)
            audit_path = audit.log_run(
                operation="deal-room",
                entity=entity,
                counterparty=counterparty,
                transaction_type=transaction_type,
                compliance_findings=(
                    AuditLogger.findings_to_dicts(val_a.findings)
                    + AuditLogger.findings_to_dicts(val_b.findings)
                ),
                red_flags=AuditLogger.findings_to_dicts(rf.flags),
                opinion_grade=opinion.overall_grade,
                deal_classification=classification.to_dict(),
                policy_snapshot=policy_snapshot,
            )
            # Rename to standard name
            final_audit = room_dir / "08_audit_record.json"
            audit_path.rename(final_audit)
            manifest["files"]["audit_record"] = final_audit.name
        except Exception:
            pass

        # --- Write manifest ---
        manifest_path = room_dir / "_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8",
        )

        results["manifest"] = manifest
        return results
