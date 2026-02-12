{# ============================================================ #}
{# MODULE: SOURCE OF FUNDS                                     #}
{# Cross-border transactions.                                  #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XV") }} — SOURCE OF FUNDS

### Section {{ article_number | default("XV") }}.1 — Source of Funds Representation

Each Party represents and warrants that:

(a) All funds used in connection with this Agreement and the transactions contemplated hereby are derived from legitimate sources and do not constitute the proceeds of any unlawful activity.

(b) No part of the funds used or to be used in connection with this Agreement:

  (i) constitutes or will constitute funds obtained or derived from illegal activities;

  (ii) is being or will be used, directly or indirectly, in contravention of any applicable anti-money laundering, counter-terrorist financing, or sanctions laws; or

  (iii) is being or will be used for the purpose of furthering bribery or corruption.

(c) It has implemented and maintains policies and procedures reasonably designed to ensure compliance with applicable source-of-funds requirements.

### Section {{ article_number | default("XV") }}.2 — Anti-Bribery Representation

{% if "US" in jurisdictions %}
Each Party represents that it is in compliance with the U.S. Foreign Corrupt Practices Act (15 U.S.C. §§ 78dd-1 et seq.) and has not made, offered, or authorized any payment or transfer of value, directly or indirectly, to any government official, political party, or candidate for political office for the purpose of obtaining or retaining business or securing any improper advantage.
{% endif %}

{% if "GB" in jurisdictions %}
Each Party represents that it is in compliance with the UK Bribery Act 2010 and has adequate procedures in place to prevent bribery by persons associated with it.
{% endif %}

{% if "VN" in jurisdictions %}
Each Party represents that it is in compliance with the Vietnam Law on Anti-Corruption 2018 and the relevant provisions of the Vietnam Penal Code.
{% endif %}

### Section {{ article_number | default("XV") }}.3 — Tax Representations

Each Party represents that:

(a) It has complied with all applicable tax laws in connection with the funds to be used in this transaction.

(b) It shall be solely responsible for any taxes imposed on it by its jurisdiction of organization or residence.

(c) It shall provide such tax documentation (including, without limitation, IRS Forms W-8 or W-9, or equivalent documentation under applicable law) as may be reasonably requested by the other Party.
