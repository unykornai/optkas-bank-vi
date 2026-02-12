{# ============================================================ #}
{# MODULE: ESCROW CONDITIONS                                   #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XII") }} — ESCROW

### Section {{ article_number | default("XII") }}.1 — Escrow Agent

The Parties hereby appoint {{ escrow_agent | default("[ESCROW AGENT NAME — REQUIRED]") }} (the "**Escrow Agent**") to hold and disburse the Escrow Amount in accordance with the terms of this Agreement and the Escrow Agreement attached hereto as Exhibit {{ escrow_exhibit | default("C") }}.

### Section {{ article_number | default("XII") }}.2 — Escrow Amount

The {{ depositing_party | default("Purchaser") }} shall deposit the sum of {{ escrow_amount | default("[AMOUNT — REQUIRED]") }} (the "**Escrow Amount**") with the Escrow Agent within {{ escrow_deposit_days | default("5") }} Business Days of the execution of this Agreement.

### Section {{ article_number | default("XII") }}.3 — Release Conditions

The Escrow Amount (or applicable portion thereof) shall be released by the Escrow Agent upon the occurrence of the following:

(a) **Full Release to {{ release_to_party | default("Seller") }}:** Upon satisfaction of all Conditions Precedent set forth in Article {{ cp_article | default("XIV") }} and confirmation of Closing.

(b) **Full Release to {{ depositing_party | default("Purchaser") }}:** Upon the failure of the Conditions Precedent to be satisfied by the {{ longstop_date | default("[LONGSTOP DATE — REQUIRED]") }} (the "**Longstop Date**").

(c) **Partial Release:** As mutually agreed by the Parties in writing.

### Section {{ article_number | default("XII") }}.4 — Escrow Agent Duties

The Escrow Agent shall:

(a) Hold the Escrow Amount in a segregated, interest-bearing account at {{ escrow_bank | default("[BANK — REQUIRED]") }};

(b) Not release any portion of the Escrow Amount except as expressly provided herein;

(c) Act in accordance with joint written instructions of the Parties or a final, non-appealable court order or arbitral award; and

(d) Be entitled to rely upon any written notice, instruction, or document believed by it in good faith to be genuine.

{% if is_cross_border %}
### Section {{ article_number | default("XII") }}.5 — Cross-Border Escrow Considerations

(a) The Escrow Amount shall be denominated in {{ escrow_currency | default("USD") }}.

(b) Any foreign exchange conversion required for release shall be at the prevailing market rate on the date of release.

(c) Each Party shall bear its own tax obligations arising from the escrow arrangement, including any withholding taxes imposed by its jurisdiction.
{% endif %}
