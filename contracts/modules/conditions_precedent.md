{# ============================================================ #}
{# MODULE: CONDITIONS PRECEDENT                                #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XVII") }} — CONDITIONS PRECEDENT

### Section {{ article_number | default("XVII") }}.1 — Conditions to All Parties' Obligations

The obligations of each Party to consummate the transactions contemplated by this Agreement are subject to the satisfaction (or waiver by each Party) of the following conditions:

(a) **No Injunction.** No Governmental Authority shall have enacted, issued, or enforced any order, decree, or ruling that prohibits the consummation of the transactions contemplated hereby.

(b) **No Material Adverse Effect.** Since the date of this Agreement, no Material Adverse Effect shall have occurred with respect to either Party.

(c) **Regulatory Approvals.** All regulatory approvals, consents, and filings required in connection with the transactions contemplated hereby shall have been obtained or made.

### Section {{ article_number | default("XVII") }}.2 — Transaction-Specific Conditions

The following conditions must be satisfied prior to Closing:

{% for cp in conditions_precedent %}
({{ loop.index | alpha_lower }}) {{ cp }}
{% endfor %}

{% if not conditions_precedent %}
{# Default conditions if none specified #}
(a) Entity formation documents of each Party, certified by the relevant Governmental Authority.

(b) Certificates of good standing (or equivalent) for each Party, issued within {{ good_standing_days | default("30") }} days of Closing.

(c) Board resolution or equivalent authorization from each Party authorizing the execution and delivery of this Agreement.

(d) Completed AML/KYC documentation for each Party.

(e) Audited financial statements of each Party for the {{ financial_years | default("two (2)") }} most recent fiscal years.

(f) Legal opinion from counsel to each Party as to due authorization, execution, and enforceability.
{% endif %}

{% if is_cross_border %}
### Section {{ article_number | default("XVII") }}.3 — Cross-Border Conditions

In addition to the foregoing:

(a) All foreign exchange approvals required by any applicable Governmental Authority shall have been obtained.

(b) All tax clearance certificates or exemption documentation shall have been provided.

(c) Legalization or apostille of all foreign documents shall have been completed.

{% if "VN" in jurisdictions %}
(d) The Investment Registration Certificate from the Department of Planning and Investment of Vietnam shall have been obtained (if required for the transaction).
{% endif %}
{% endif %}

### Section {{ article_number | default("XVII") }}.4 — Waiver of Conditions

Any condition set forth in this Article may be waived, in whole or in part, by the Party or Parties for whose benefit such condition exists, by written notice to the other Party. No such waiver shall constitute a waiver of any other condition.
