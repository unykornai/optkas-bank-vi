{# ============================================================ #}
{# MODULE: CLOSING MECHANICS                                   #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XVIII") }} — CLOSING

### Section {{ article_number | default("XVIII") }}.1 — Closing Date

The closing of the transactions contemplated by this Agreement (the "**Closing**") shall take place on {{ closing_date | default("[CLOSING DATE — REQUIRED]") }} (the "**Closing Date**"), or such other date as the Parties may mutually agree in writing, subject to the satisfaction or waiver of all Conditions Precedent set forth in Article {{ cp_article | default("XVII") }}.

### Section {{ article_number | default("XVIII") }}.2 — Deliverables at Closing

At or prior to the Closing, the following shall be delivered:

**By {{ party_a.short_name }}:**

(a) This Agreement, duly executed by {{ party_a.short_name }};

(b) Officer's certificate certifying that all representations and warranties are true and correct as of the Closing Date;

(c) Secretary's or equivalent certificate attaching (i) organizational documents, (ii) board resolution, and (iii) incumbency certificate;

(d) Legal opinion of counsel to {{ party_a.short_name }};

{% if transaction_category == "securities" %}
(e) Securities, in definitive form or book-entry, registered in the name of {{ party_b.short_name }};
{% endif %}

{% if transaction_category == "debt" %}
(e) Evidence of funding or wire transfer confirmation;
{% endif %}

(f) Such other documents as {{ party_b.short_name }} may reasonably request.

**By {{ party_b.short_name }}:**

(a) This Agreement, duly executed by {{ party_b.short_name }};

(b) Officer's certificate certifying that all representations and warranties are true and correct as of the Closing Date;

(c) Secretary's or equivalent certificate attaching (i) organizational documents, (ii) board resolution, and (iii) incumbency certificate;

(d) Legal opinion of counsel to {{ party_b.short_name }};

{% if transaction_category == "securities" %}
(e) Wire transfer of the purchase price in immediately available funds;
{% endif %}

(f) Such other documents as {{ party_a.short_name }} may reasonably request.

### Section {{ article_number | default("XVIII") }}.3 — Simultaneous Delivery

All deliveries at Closing shall be deemed to occur simultaneously, and no delivery shall be deemed complete until all deliveries have been made.

{% if escrow_required %}
### Section {{ article_number | default("XVIII") }}.4 — Escrow Closing

If the Conditions Precedent are not satisfied by the Longstop Date, the Escrow Agent shall return the Escrow Amount to {{ depositing_party | default("the depositing Party") }} in accordance with the Escrow Agreement.
{% endif %}
