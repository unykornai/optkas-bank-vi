{# ============================================================ #}
{# MODULE: GOVERNING LAW                                       #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("IX") }} — GOVERNING LAW

### Section {{ article_number | default("IX") }}.1 — Choice of Law

This Agreement shall be governed by and construed in accordance with the laws of {{ governing_law_text }}, without giving effect to any choice or conflict of law provision or rule that would cause the application of the laws of any other jurisdiction.

{% if "US" in jurisdictions %}
{% if governing_law_state == "New York" %}
The Parties hereby agree that Section 5-1401 of the New York General Obligations Law shall apply to this Agreement.
{% endif %}
{% endif %}

{% if is_cross_border %}
### Section {{ article_number | default("IX") }}.2 — Conflicts of Law

To the extent that the laws of more than one jurisdiction may be applicable to any matter arising under this Agreement, the Parties agree that the governing law specified in Section {{ article_number | default("IX") }}.1 shall control, and any conflicting provisions of the laws of any other jurisdiction shall be disregarded to the maximum extent permitted by law.
{% endif %}

### Section {{ article_number | default("IX") }}.3 — Consent to Jurisdiction

Each Party irrevocably submits to the exclusive jurisdiction of {{ court_jurisdiction | default("the federal and state courts located in the Borough of Manhattan, City of New York") }} for any action or proceeding arising out of or relating to this Agreement, and each Party irrevocably waives any objection to venue or any claim of inconvenient forum.

{% if waive_jury_trial | default(true) %}
### Section {{ article_number | default("IX") }}.4 — Waiver of Jury Trial

**EACH PARTY HEREBY IRREVOCABLY WAIVES, TO THE FULLEST EXTENT PERMITTED BY APPLICABLE LAW, ANY RIGHT IT MAY HAVE TO A TRIAL BY JURY IN ANY LEGAL PROCEEDING ARISING OUT OF OR RELATING TO THIS AGREEMENT OR THE TRANSACTIONS CONTEMPLATED HEREBY.**
{% endif %}
