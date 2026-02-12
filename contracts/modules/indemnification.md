{# ============================================================ #}
{# MODULE: INDEMNIFICATION                                     #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("VII") }} — INDEMNIFICATION

### Section {{ article_number | default("VII") }}.1 — General Indemnification

Each Party (the "**Indemnifying Party**") shall indemnify, defend, and hold harmless the other Party and its directors, officers, employees, agents, and Affiliates (each, an "**Indemnified Party**") from and against any and all Losses arising out of or resulting from:

(a) any breach of any representation or warranty of the Indemnifying Party contained in this Agreement;

(b) any breach or non-performance of any covenant or obligation of the Indemnifying Party under this Agreement;

(c) any fraud or willful misconduct by the Indemnifying Party; or

(d) any violation of Applicable Law by the Indemnifying Party in connection with this Agreement.

### Section {{ article_number | default("VII") }}.2 — Indemnification Procedures

(a) **Notice.** An Indemnified Party seeking indemnification shall promptly deliver to the Indemnifying Party written notice of any claim (a "**Claim Notice**"), which shall describe in reasonable detail the facts constituting the basis for such claim and the estimated amount of Losses.

(b) **Defense.** The Indemnifying Party shall have the right, at its sole cost, to assume the defense of any third-party claim with counsel reasonably satisfactory to the Indemnified Party.

(c) **Cooperation.** The Indemnified Party shall cooperate in the defense of any claim and make available all records and information reasonably requested by the Indemnifying Party.

### Section {{ article_number | default("VII") }}.3 — Limitations

(a) The aggregate liability of either Party under this Article shall not exceed {{ indemnity_cap | default("the total consideration paid under this Agreement") }}.

(b) No Party shall be liable for any indirect, incidental, consequential, special, or punitive damages, except in the case of fraud or willful misconduct.

(c) No claim for indemnification may be brought after {{ indemnity_survival_months | default("18") }} months following the Closing Date, except with respect to claims arising from fraud, which shall survive indefinitely.
