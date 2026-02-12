"""
Deal Classification Engine
============================
Auto-classifies transactions based on entity structure, jurisdiction,
and regulatory context. Dynamically escalates risk tier.

Static transaction_type tells you WHAT document to generate.
Deal classification tells you HOW DANGEROUS the transaction is.

Classification signals:
  - Cross-border + funds → Regulated Financial Activity
  - Security interest + US → UCC Filing Required
  - Vietnam entity + USD → FX Controlled Transaction
  - Custody involved → Custodial Regulatory Activity
  - No licenses + regulated claims → Unlicensed Activity Risk
  - PEP exposure → Enhanced Due Diligence Required
  - Securities category → Securities Regulatory Compliance

This turns the engine from reactive to proactive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class DealTag:
    """A single classification tag applied to a deal."""
    tag: str
    risk_level: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    description: str
    required_actions: list[str] = field(default_factory=list)


@dataclass
class DealClassification:
    """Complete classification of a deal."""
    transaction_type: str
    tags: list[DealTag] = field(default_factory=list)

    @property
    def risk_tier(self) -> str:
        """Overall risk tier based on highest tag severity."""
        levels = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        if not self.tags:
            return "LOW"
        highest = min(self.tags, key=lambda t: levels.get(t.risk_level, 4))
        return highest.risk_level

    @property
    def risk_score(self) -> int:
        """Numeric risk score 0-100. Higher = more risk."""
        weights = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 3, "INFO": 1}
        score = sum(weights.get(t.risk_level, 0) for t in self.tags)
        return min(100, score)

    def summary(self) -> str:
        lines = [
            f"Transaction: {self.transaction_type}",
            f"Risk Tier:   {self.risk_tier}",
            f"Risk Score:  {self.risk_score}/100",
            f"Tags:        {len(self.tags)}",
            "",
        ]
        for tag in sorted(
            self.tags,
            key=lambda t: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(
                t.risk_level, 4
            ),
        ):
            lines.append(f"  [{tag.risk_level}] {tag.tag}")
            lines.append(f"    {tag.description}")
            for action in tag.required_actions:
                lines.append(f"    -> {action}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for audit logging."""
        return {
            "transaction_type": self.transaction_type,
            "risk_tier": self.risk_tier,
            "risk_score": self.risk_score,
            "tags": [
                {
                    "tag": t.tag,
                    "risk_level": t.risk_level,
                    "description": t.description,
                    "required_actions": t.required_actions,
                }
                for t in self.tags
            ],
        }


# ---------------------------------------------------------------------------
# Currency control jurisdictions (shared with conflict_matrix)
# ---------------------------------------------------------------------------

FX_CONTROLLED = {"VN", "CN", "IN", "BR", "NG", "EG", "AR", "ZA", "MY"}
SECURITIES_CATEGORIES = {"securities", "collateral"}
FUND_CATEGORIES = {"debt", "securities"}


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class DealClassifier:
    """
    Auto-classifies a transaction and escalates risk tier.
    """

    def classify(
        self,
        entity: dict[str, Any],
        counterparty: dict[str, Any],
        transaction_type: str,
        tx_def: dict[str, Any] | None = None,
    ) -> DealClassification:
        """
        Classify a deal based on all available signals.
        """
        classification = DealClassification(transaction_type=transaction_type)

        jur_a = entity.get("jurisdiction", "").split("-")[0].upper()
        jur_b = counterparty.get("jurisdiction", "").split("-")[0].upper()
        is_cross_border = jur_a != jur_b
        category = (tx_def or {}).get("category", "").lower()

        # --- Signal checks ---
        self._check_cross_border_funds(
            classification, is_cross_border, category, jur_a, jur_b
        )
        self._check_fx_controlled(
            classification, is_cross_border, jur_a, jur_b
        )
        self._check_securities_activity(
            classification, category, entity, counterparty
        )
        self._check_ucc_filing(
            classification, category, jur_a, jur_b, tx_def
        )
        self._check_custody_activity(
            classification, entity, counterparty, transaction_type
        )
        self._check_unlicensed_risk(
            classification, entity, "Party A"
        )
        self._check_unlicensed_risk(
            classification, counterparty, "Party B"
        )
        self._check_pep_exposure(
            classification, entity, counterparty
        )
        self._check_sanctions_gap(
            classification, entity, counterparty
        )
        self._check_escrow_structure(
            classification, entity, counterparty, is_cross_border, category
        )
        self._check_signatory_concentration(
            classification, entity, counterparty
        )

        return classification

    # --- Individual signal checks ---

    def _check_cross_border_funds(
        self, cls: DealClassification, is_cb: bool, category: str,
        jur_a: str, jur_b: str,
    ) -> None:
        if is_cb and category in FUND_CATEGORIES:
            cls.tags.append(DealTag(
                tag="REGULATED_FINANCIAL_ACTIVITY",
                risk_level="HIGH",
                description=(
                    f"Cross-border fund movement ({jur_a} <-> {jur_b}) "
                    f"in category '{category}'. Subject to financial regulations "
                    f"in both jurisdictions."
                ),
                required_actions=[
                    "Verify AML/CFT compliance in both jurisdictions",
                    "Confirm wire transfer regulatory approvals",
                    "Include source-of-funds documentation",
                ],
            ))

    def _check_fx_controlled(
        self, cls: DealClassification, is_cb: bool, jur_a: str, jur_b: str,
    ) -> None:
        if not is_cb:
            return

        controlled = []
        if jur_a in FX_CONTROLLED:
            controlled.append(jur_a)
        if jur_b in FX_CONTROLLED:
            controlled.append(jur_b)

        if controlled:
            cls.tags.append(DealTag(
                tag="FX_CONTROLLED_TRANSACTION",
                risk_level="HIGH",
                description=(
                    f"Jurisdiction(s) {', '.join(controlled)} have active "
                    f"currency/foreign exchange controls. All fund transfers "
                    f"require regulatory pre-approval."
                ),
                required_actions=[
                    f"Obtain FX approval from central bank in {', '.join(controlled)}",
                    "Include currency control compliance clause",
                    "Consider escrow in freely convertible currency (USD/EUR/GBP)",
                ],
            ))

    def _check_securities_activity(
        self, cls: DealClassification, category: str,
        entity: dict, counterparty: dict,
    ) -> None:
        if category not in SECURITIES_CATEGORIES:
            return

        cls.tags.append(DealTag(
            tag="SECURITIES_REGULATORY_COMPLIANCE",
            risk_level="HIGH",
            description=(
                f"Transaction category '{category}' involves securities. "
                f"Subject to securities regulations in all relevant jurisdictions."
            ),
            required_actions=[
                "Verify Reg D / Reg S exemption applicability",
                "Confirm accredited investor status where required",
                "Include transfer restriction legends",
                "File required regulatory notices",
            ],
        ))

    def _check_ucc_filing(
        self, cls: DealClassification, category: str,
        jur_a: str, jur_b: str, tx_def: dict | None,
    ) -> None:
        modules = (tx_def or {}).get("required_modules", [])
        if "security_interest" not in modules:
            return

        us_involved = "US" in (jur_a, jur_b)
        if us_involved:
            cls.tags.append(DealTag(
                tag="UCC_FILING_REQUIRED",
                risk_level="MEDIUM",
                description=(
                    "Security interest with US party requires UCC-1 financing "
                    "statement filing for perfection."
                ),
                required_actions=[
                    "Prepare UCC-1 financing statement",
                    "File with appropriate Secretary of State",
                    "Conduct UCC lien search before closing",
                    "Include UCC representations in agreement",
                ],
            ))
        else:
            cls.tags.append(DealTag(
                tag="SECURITY_INTEREST_PERFECTION",
                risk_level="MEDIUM",
                description=(
                    f"Security interest requires perfection under local law "
                    f"in {jur_a} and/or {jur_b}."
                ),
                required_actions=[
                    "Engage local counsel for perfection requirements",
                    "Identify applicable registration/filing systems",
                ],
            ))

    def _check_custody_activity(
        self, cls: DealClassification, entity: dict, counterparty: dict,
        tx_type: str,
    ) -> None:
        custody_signals = (
            tx_type in ("custody_agreement",)
            or entity.get("banking", {}).get("custodian")
            or counterparty.get("banking", {}).get("custodian")
        )
        if custody_signals:
            cls.tags.append(DealTag(
                tag="CUSTODIAL_REGULATORY_ACTIVITY",
                risk_level="MEDIUM",
                description=(
                    "Transaction involves custodial arrangements. "
                    "Custodian regulatory status must be verified."
                ),
                required_actions=[
                    "Verify custodian's regulatory license and standing",
                    "Confirm insurance coverage for custodied assets",
                    "Obtain sub-custodian disclosure if applicable",
                ],
            ))

    def _check_unlicensed_risk(
        self, cls: DealClassification, party: dict, label: str,
    ) -> None:
        rs = party.get("regulatory_status", {})
        licenses = party.get("licenses", [])
        name = party.get("legal_name", label)

        regulated = any(rs.get(k) for k in (
            "is_bank", "is_broker_dealer", "is_ria", "is_fund",
            "is_insurance_company", "is_money_services_business",
        ))

        if regulated and not licenses:
            cls.tags.append(DealTag(
                tag="UNLICENSED_ACTIVITY_RISK",
                risk_level="CRITICAL",
                description=(
                    f"{name} claims regulated status but has ZERO licenses "
                    f"on file. This is a critical compliance gap."
                ),
                required_actions=[
                    f"Obtain and verify all regulatory licenses for {name}",
                    "Do NOT generate documents referencing regulatory authority",
                    "Escalate to compliance officer immediately",
                ],
            ))

    def _check_pep_exposure(
        self, cls: DealClassification, entity: dict, counterparty: dict,
    ) -> None:
        peps = []
        for party in (entity, counterparty):
            for d in party.get("directors", []):
                if d.get("pep_status"):
                    peps.append(d.get("name", "UNKNOWN"))
            for o in party.get("beneficial_owners", []):
                if o.get("pep_status"):
                    peps.append(o.get("name", "UNKNOWN"))

        if peps:
            cls.tags.append(DealTag(
                tag="PEP_ENHANCED_DUE_DILIGENCE",
                risk_level="HIGH",
                description=(
                    f"Politically Exposed Persons detected: {', '.join(peps)}. "
                    f"Enhanced due diligence (EDD) required."
                ),
                required_actions=[
                    "Conduct enhanced due diligence on all PEPs",
                    "Obtain source-of-wealth documentation",
                    "Obtain senior management approval",
                    "Document rationale for proceeding",
                ],
            ))

    def _check_sanctions_gap(
        self, cls: DealClassification, entity: dict, counterparty: dict,
    ) -> None:
        unscreened = []
        for party in (entity, counterparty):
            for o in party.get("beneficial_owners", []):
                if not o.get("sanctions_screened"):
                    unscreened.append(o.get("name", "UNKNOWN"))

        if unscreened:
            cls.tags.append(DealTag(
                tag="SANCTIONS_SCREENING_GAP",
                risk_level="CRITICAL",
                description=(
                    f"Beneficial owners NOT sanctions-screened: "
                    f"{', '.join(unscreened)}."
                ),
                required_actions=[
                    "Run OFAC/SDN/UN/EU sanctions screening immediately",
                    "Document screening results with timestamp",
                    "Do NOT proceed until screening is complete",
                ],
            ))

    def _check_escrow_structure(
        self, cls: DealClassification, entity: dict, counterparty: dict,
        is_cb: bool, category: str,
    ) -> None:
        banking_a = entity.get("banking", {})
        banking_b = counterparty.get("banking", {})

        escrow_required = (
            banking_a.get("escrow_required") or banking_b.get("escrow_required")
        )
        escrow_agent = (
            banking_a.get("escrow_agent") or banking_b.get("escrow_agent")
        )

        if escrow_required and not escrow_agent:
            cls.tags.append(DealTag(
                tag="ESCROW_AGENT_MISSING",
                risk_level="HIGH",
                description="Escrow is required but no escrow agent is defined.",
                required_actions=[
                    "Appoint a qualified third-party escrow agent",
                    "Define escrow release conditions",
                    "Include escrow fee allocation in agreement",
                ],
            ))

        if is_cb and category in FUND_CATEGORIES and not escrow_required:
            cls.tags.append(DealTag(
                tag="CROSS_BORDER_NO_ESCROW",
                risk_level="MEDIUM",
                description=(
                    "Cross-border fund transaction without escrow arrangement. "
                    "Consider adding escrow for settlement protection."
                ),
                required_actions=[
                    "Evaluate escrow requirement based on transaction size",
                    "Consider jurisdictional enforcement risks",
                ],
            ))

    def _check_signatory_concentration(
        self, cls: DealClassification, entity: dict, counterparty: dict,
    ) -> None:
        for party in (entity, counterparty):
            signatories = party.get("signatories", [])
            name = party.get("legal_name", "UNKNOWN")

            full_power = [
                s for s in signatories
                if s.get("can_bind_company") and s.get("can_move_funds")
                and s.get("can_pledge_assets")
            ]

            if len(full_power) == 1 and len(signatories) == 1:
                cls.tags.append(DealTag(
                    tag="SIGNATORY_CONCENTRATION",
                    risk_level="MEDIUM",
                    description=(
                        f"{name}: Single signatory holds ALL authority "
                        f"(bind, funds, pledge). No secondary authorization."
                    ),
                    required_actions=[
                        "Consider requiring dual signatures",
                        "Verify board resolution explicitly grants sole authority",
                    ],
                ))
