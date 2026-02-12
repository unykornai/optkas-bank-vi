{# ============================================================ #}
{# MODULE: REPRESENTATIONS & WARRANTIES                        #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("III") }} — REPRESENTATIONS AND WARRANTIES

### Section {{ article_number | default("III") }}.1 — Mutual Representations

Each Party hereby represents and warrants to the other Party as of the date hereof and as of the Closing Date:

**(a) Organization and Authority.** Such Party is duly organized, validly existing, and in good standing under the laws of its jurisdiction of organization and has full power and authority to execute, deliver, and perform this Agreement.

**(b) Authorization.** The execution, delivery, and performance of this Agreement have been duly authorized by all necessary corporate, partnership, or other organizational action.

**(c) Enforceability.** This Agreement constitutes the legal, valid, and binding obligation of such Party, enforceable against it in accordance with its terms, subject to applicable bankruptcy, insolvency, and similar laws affecting creditors' rights generally.

**(d) No Conflicts.** The execution, delivery, and performance of this Agreement do not and will not (i) violate any Applicable Law, (ii) conflict with or result in a breach of the organizational documents of such Party, or (iii) require any consent, approval, or authorization that has not been obtained.

**(e) No Litigation.** There is no action, suit, or proceeding pending or, to such Party's knowledge, threatened against it that would reasonably be expected to have a Material Adverse Effect or impair its ability to perform its obligations hereunder.

**(f) Compliance with Law.** Such Party is in compliance with all Applicable Laws material to the transactions contemplated hereby.

{% if party_a.regulatory_status.is_broker_dealer or party_b.regulatory_status.is_broker_dealer %}
### Section {{ article_number | default("III") }}.2 — Broker-Dealer Representations

The Party that is a registered broker-dealer further represents and warrants that:

(a) It is duly registered as a broker-dealer with the Securities and Exchange Commission and is a member in good standing of the Financial Industry Regulatory Authority.

(b) It is in compliance with the net capital requirements of Rule 15c3-1 under the Exchange Act.

(c) It maintains the reserve requirements of Rule 15c3-3 under the Exchange Act.
{% endif %}

{% if party_a.regulatory_status.is_ria or party_b.regulatory_status.is_ria %}
### Section {{ article_number | default("III") }}.3 — Investment Adviser Representations

The Party that is a registered investment adviser further represents and warrants that:

(a) It is duly registered as an investment adviser with the Securities and Exchange Commission.

(b) Its current Form ADV is accurate and complete in all material respects.

(c) It acknowledges its fiduciary duties to its clients in connection with the transactions contemplated hereby.
{% endif %}

{% if party_a.regulatory_status.is_bank or party_b.regulatory_status.is_bank %}
### Section {{ article_number | default("III") }}.4 — Banking Representations

The Party that is a banking institution further represents and warrants that:

(a) It holds all licenses, charters, and approvals required by its primary banking regulator.

(b) It is in compliance with all applicable capital adequacy requirements.

(c) Its deposits are insured by the applicable governmental deposit insurance program to the extent required by law.
{% endif %}
