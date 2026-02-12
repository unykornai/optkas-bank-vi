{# ============================================================ #}
{# MODULE: COVENANTS                                           #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("IV") }} — COVENANTS

### Section {{ article_number | default("IV") }}.1 — Affirmative Covenants

Each Party covenants and agrees that, for so long as this Agreement remains in effect:

**(a) Compliance.** It shall comply in all material respects with all Applicable Laws and maintain all licenses, permits, and authorizations necessary to conduct its business.

**(b) Notices.** It shall promptly notify the other Party of (i) any Material Adverse Effect, (ii) any default or event of default under this Agreement, or (iii) any litigation, investigation, or proceeding that could reasonably be expected to affect its obligations hereunder.

**(c) Financial Reporting.** It shall furnish to the other Party, within {{ financial_reporting_days | default("120") }} days after the end of each fiscal year, audited financial statements prepared in accordance with {{ accounting_standard | default("U.S. GAAP") }}.

**(d) Books and Records.** It shall maintain complete and accurate books and records in accordance with generally accepted accounting principles.

**(e) Regulatory Compliance.** It shall maintain all regulatory licenses and registrations in good standing and shall promptly notify the other Party of any suspension, revocation, or modification thereof.

### Section {{ article_number | default("IV") }}.2 — Negative Covenants

Without the prior written consent of the other Party, no Party shall:

**(a)** Merge, consolidate, or transfer all or substantially all of its assets.

**(b)** Change its jurisdiction of organization.

**(c)** Amend its organizational documents in any manner that would materially and adversely affect its obligations under this Agreement.

{% if transaction_category == "debt" %}
**(d)** Incur additional indebtedness in excess of {{ debt_threshold | default("$1,000,000") }} without prior written notice.

**(e)** Create, assume, or permit to exist any lien on the collateral, if any, other than permitted liens.
{% endif %}

{% if transaction_category == "securities" %}
**(d)** Transfer, assign, or otherwise dispose of the Securities except in compliance with the transfer restrictions set forth herein.
{% endif %}
