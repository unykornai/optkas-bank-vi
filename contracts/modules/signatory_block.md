{# ============================================================ #}
{# MODULE: SIGNATORY BLOCK                                     #}
{# ============================================================ #}

## EXECUTION

**IN WITNESS WHEREOF**, the Parties have caused this Agreement to be executed by their duly authorized representatives as of the date first written above.

---

{% for party in parties %}
**{{ party.legal_name | upper }}**

{% if party.jurisdiction == "VN" %}
{# Vietnamese entities require legal representative and company seal #}
By: ___________________________
Name: {{ party.signatory_name | default("[SIGNATORY NAME — REQUIRED]") }}
Title: {{ party.signatory_title | default("[TITLE — REQUIRED]") }}
Date: ___________________________

[Company Seal]

{% elif party.jurisdiction == "GB" %}
{# UK entities require witness signature #}
By: ___________________________
Name: {{ party.signatory_name | default("[SIGNATORY NAME — REQUIRED]") }}
Title: {{ party.signatory_title | default("[TITLE — REQUIRED]") }}
Date: ___________________________

Witnessed by:
Signature: ___________________________
Name: ___________________________
Address: ___________________________

{% else %}
By: ___________________________
Name: {{ party.signatory_name | default("[SIGNATORY NAME — REQUIRED]") }}
Title: {{ party.signatory_title | default("[TITLE — REQUIRED]") }}
Date: ___________________________

{% endif %}

{% if not party.signatory_validated %}
{# ⚠️ COMPLIANCE FLAG: Signatory authority not validated #}
{# Authorization document: {{ party.signatory_authorization | default("NOT PROVIDED") }} #}
{% endif %}

{% endfor %}
