"""
Fund Flow Tracker
=================
Tracks capital through its lifecycle:
  COMMITTED -> CALLED -> FUNDED -> DEPLOYED -> RETURNED

Each transition is gated, auditable, and compliance-checked.
Integrates with capital_structure.py for allocation tracking.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class FlowState(str, Enum):
    """Capital lifecycle states."""
    COMMITTED = "COMMITTED"     # Investor has committed capital
    CALLED = "CALLED"           # Capital call issued
    FUNDED = "FUNDED"           # Capital received in escrow/account
    DEPLOYED = "DEPLOYED"       # Capital deployed to deal/asset
    RETURNED = "RETURNED"       # Capital returned to investor
    HELD = "HELD"               # Capital held pending compliance
    BLOCKED = "BLOCKED"         # Capital blocked by compliance gate


# Valid state transitions
VALID_TRANSITIONS = {
    FlowState.COMMITTED: [FlowState.CALLED, FlowState.HELD],
    FlowState.CALLED:    [FlowState.FUNDED, FlowState.HELD, FlowState.BLOCKED],
    FlowState.FUNDED:    [FlowState.DEPLOYED, FlowState.HELD, FlowState.RETURNED],
    FlowState.DEPLOYED:  [FlowState.RETURNED],
    FlowState.RETURNED:  [],
    FlowState.HELD:      [FlowState.CALLED, FlowState.FUNDED, FlowState.DEPLOYED, FlowState.BLOCKED],
    FlowState.BLOCKED:   [FlowState.HELD, FlowState.CALLED],
}


@dataclass
class FlowEvent:
    """Single fund flow event with audit trail."""
    event_id: str
    timestamp: str
    party_name: str
    from_state: str
    to_state: str
    amount: float
    currency: str
    authorized_by: str
    gate_checks: list[str] = field(default_factory=list)
    notes: str = ""
    compliance_hold: bool = False
    hold_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "party_name": self.party_name,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "amount": self.amount,
            "currency": self.currency,
            "authorized_by": self.authorized_by,
            "gate_checks": self.gate_checks,
            "notes": self.notes,
            "compliance_hold": self.compliance_hold,
            "hold_reason": self.hold_reason,
        }


@dataclass
class PartyFlow:
    """Fund flow state for a single party."""
    party_name: str
    party_type: str
    committed_amount: float
    called_amount: float = 0.0
    funded_amount: float = 0.0
    deployed_amount: float = 0.0
    returned_amount: float = 0.0
    held_amount: float = 0.0
    current_state: str = "COMMITTED"
    events: list[FlowEvent] = field(default_factory=list)

    @property
    def outstanding(self) -> float:
        """Amount still owed (committed - funded)."""
        return max(0.0, self.committed_amount - self.funded_amount)

    @property
    def net_deployed(self) -> float:
        """Amount currently deployed (deployed - returned)."""
        return self.deployed_amount - self.returned_amount

    def to_dict(self) -> dict:
        return {
            "party_name": self.party_name,
            "party_type": self.party_type,
            "committed_amount": self.committed_amount,
            "called_amount": self.called_amount,
            "funded_amount": self.funded_amount,
            "deployed_amount": self.deployed_amount,
            "returned_amount": self.returned_amount,
            "held_amount": self.held_amount,
            "current_state": self.current_state,
            "outstanding": self.outstanding,
            "net_deployed": self.net_deployed,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class FundFlowLedger:
    """Complete fund flow ledger for a deal."""
    deal_name: str
    currency: str = "USD"
    total_commitment: float = 0.0
    parties: list[PartyFlow] = field(default_factory=list)
    _event_counter: int = field(default=0, repr=False)

    @property
    def total_called(self) -> float:
        return sum(p.called_amount for p in self.parties)

    @property
    def total_funded(self) -> float:
        return sum(p.funded_amount for p in self.parties)

    @property
    def total_deployed(self) -> float:
        return sum(p.deployed_amount for p in self.parties)

    @property
    def total_returned(self) -> float:
        return sum(p.returned_amount for p in self.parties)

    @property
    def total_held(self) -> float:
        return sum(p.held_amount for p in self.parties)

    @property
    def total_outstanding(self) -> float:
        return sum(p.outstanding for p in self.parties)

    @property
    def funding_percentage(self) -> float:
        if self.total_commitment == 0:
            return 0.0
        return (self.total_funded / self.total_commitment) * 100.0

    def get_party(self, name: str) -> Optional[PartyFlow]:
        for p in self.parties:
            if p.party_name == name:
                return p
        return None

    def transition(
        self,
        party_name: str,
        to_state: FlowState,
        amount: float,
        authorized_by: str,
        gate_checks: Optional[list[str]] = None,
        notes: str = "",
        compliance_hold: bool = False,
        hold_reason: str = "",
    ) -> FlowEvent:
        """Execute a fund flow state transition with audit trail."""
        party = self.get_party(party_name)
        if party is None:
            raise ValueError(f"Party '{party_name}' not found in ledger")

        from_state = FlowState(party.current_state)
        if to_state not in VALID_TRANSITIONS.get(from_state, []):
            raise ValueError(
                f"Invalid transition: {from_state.value} -> {to_state.value} "
                f"for {party_name}. "
                f"Valid: {[s.value for s in VALID_TRANSITIONS.get(from_state, [])]}"
            )

        # Apply state
        party.current_state = to_state.value

        if to_state == FlowState.CALLED:
            party.called_amount += amount
        elif to_state == FlowState.FUNDED:
            party.funded_amount += amount
        elif to_state == FlowState.DEPLOYED:
            party.deployed_amount += amount
        elif to_state == FlowState.RETURNED:
            party.returned_amount += amount
        elif to_state in (FlowState.HELD, FlowState.BLOCKED):
            party.held_amount += amount

        # Generate event
        self._event_counter += 1
        event = FlowEvent(
            event_id=f"FF-{self._event_counter:04d}",
            timestamp=datetime.utcnow().isoformat() + "Z",
            party_name=party_name,
            from_state=from_state.value,
            to_state=to_state.value,
            amount=amount,
            currency=self.currency,
            authorized_by=authorized_by,
            gate_checks=gate_checks or [],
            notes=notes,
            compliance_hold=compliance_hold,
            hold_reason=hold_reason,
        )
        party.events.append(event)
        return event

    def validate(self) -> list[str]:
        """Validate the fund flow ledger. Returns list of issues."""
        issues = []

        for p in self.parties:
            if p.funded_amount > p.committed_amount:
                issues.append(
                    f"{p.party_name}: funded ({p.funded_amount:,.0f}) "
                    f"exceeds committed ({p.committed_amount:,.0f})"
                )
            if p.deployed_amount > p.funded_amount:
                issues.append(
                    f"{p.party_name}: deployed ({p.deployed_amount:,.0f}) "
                    f"exceeds funded ({p.funded_amount:,.0f})"
                )
            if p.returned_amount > p.deployed_amount:
                issues.append(
                    f"{p.party_name}: returned ({p.returned_amount:,.0f}) "
                    f"exceeds deployed ({p.deployed_amount:,.0f})"
                )
            if p.current_state == FlowState.BLOCKED.value:
                issues.append(
                    f"{p.party_name}: currently BLOCKED — compliance hold active"
                )

        return issues

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "FUND FLOW LEDGER",
            f"  {self.deal_name}",
            "=" * 50,
            f"Total Commitment:  ${self.total_commitment:,.0f} {self.currency}",
            f"Total Called:      ${self.total_called:,.0f}",
            f"Total Funded:      ${self.total_funded:,.0f} ({self.funding_percentage:.1f}%)",
            f"Total Deployed:    ${self.total_deployed:,.0f}",
            f"Total Returned:    ${self.total_returned:,.0f}",
            f"Total Outstanding: ${self.total_outstanding:,.0f}",
        ]
        if self.total_held > 0:
            lines.append(f"Total Held/Blocked: ${self.total_held:,.0f}")

        lines.append("\n--- PARTY STATUS ---")
        for p in self.parties:
            state_icon = {
                "COMMITTED": "[.]",
                "CALLED": "[>]",
                "FUNDED": "[$]",
                "DEPLOYED": "[D]",
                "RETURNED": "[R]",
                "HELD": "[H]",
                "BLOCKED": "[X]",
            }.get(p.current_state, "[?]")
            lines.append(
                f"  {state_icon} {p.party_name}: "
                f"${p.funded_amount:,.0f} / ${p.committed_amount:,.0f} funded"
            )
            if p.held_amount > 0:
                lines.append(f"       HELD: ${p.held_amount:,.0f}")

        # Events
        all_events = []
        for p in self.parties:
            all_events.extend(p.events)
        all_events.sort(key=lambda e: e.timestamp)

        if all_events:
            lines.append(f"\n--- EVENT LOG ({len(all_events)}) ---")
            for ev in all_events[-10:]:  # Last 10 events
                lines.append(
                    f"  [{ev.event_id}] {ev.party_name}: "
                    f"{ev.from_state} -> {ev.to_state} "
                    f"${ev.amount:,.0f} (by: {ev.authorized_by})"
                )
                if ev.compliance_hold:
                    lines.append(f"       HOLD: {ev.hold_reason}")

        issues = self.validate()
        if issues:
            lines.append(f"\n--- ISSUES ({len(issues)}) ---")
            for issue in issues:
                lines.append(f"  [!] {issue}")

        lines.append("=" * 50)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "deal_name": self.deal_name,
            "currency": self.currency,
            "total_commitment": self.total_commitment,
            "total_called": self.total_called,
            "total_funded": self.total_funded,
            "total_deployed": self.total_deployed,
            "total_returned": self.total_returned,
            "total_outstanding": self.total_outstanding,
            "funding_percentage": self.funding_percentage,
            "parties": [p.to_dict() for p in self.parties],
            "issues": self.validate(),
        }


# ── Builder ─────────────────────────────────────────────────────────

class FundFlowBuilder:
    """Builds fund flow ledgers from capital structure data."""

    def build_from_capital_structure(self, cap_dict: dict) -> FundFlowLedger:
        """Build a fund flow ledger from a capital structure dict."""
        ledger = FundFlowLedger(
            deal_name=cap_dict.get("deal_name", "Unknown"),
            currency=cap_dict.get("currency", "USD"),
            total_commitment=cap_dict.get("total_commitment", 0.0),
        )

        for c in cap_dict.get("commitments", []):
            ledger.parties.append(
                PartyFlow(
                    party_name=c["party_name"],
                    party_type=c.get("party_type", "partner"),
                    committed_amount=c.get("commitment_amount", 0.0),
                    funded_amount=c.get("funded_amount", 0.0),
                    current_state=c.get("status", "COMMITTED"),
                )
            )

        return ledger

    def save(self, ledger: FundFlowLedger) -> Path:
        """Persist fund flow ledger to JSON."""
        out_dir = Path("output/fund_flows")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = ledger.deal_name.replace(" ", "_").replace("/", "-")
        path = out_dir / f"fund_flow_{safe_name}.json"
        path.write_text(json.dumps(ledger.to_dict(), indent=2, default=str), encoding="utf-8")
        return path
