{# ============================================================ #}
{# MODULE: SECURITY INTEREST (UCC / Collateral)                #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("X") }} — SECURITY INTEREST

### Section {{ article_number | default("X") }}.1 — Grant of Security Interest

{% if "US" in jurisdictions %}
To secure the prompt and complete payment and performance of all Obligations, {{ grantor_name }} (the "**Grantor**") hereby grants to {{ secured_party_name }} (the "**Secured Party**") a continuing first-priority security interest in and lien upon all of the Grantor's right, title, and interest in and to the Collateral described in Schedule B hereto (the "**Collateral**"), pursuant to Article 9 of the Uniform Commercial Code as in effect in {{ ucc_filing_state | default("the State of New York") }} (the "**UCC**").
{% else %}
To secure the prompt and complete payment and performance of all Obligations, {{ grantor_name }} (the "**Grantor**") hereby grants to {{ secured_party_name }} (the "**Secured Party**") a continuing first-priority security interest in and charge over all of the Grantor's right, title, and interest in and to the Collateral described in Schedule B hereto (the "**Collateral**").
{% endif %}

### Section {{ article_number | default("X") }}.2 — Collateral

The Collateral shall include, without limitation:

(a) All accounts, chattel paper, instruments, and general intangibles;

(b) All deposit accounts and investment property;

(c) All inventory, equipment, and fixtures;

(d) All documents and letters of credit;

(e) All proceeds of the foregoing; and

(f) Such other property as specifically described in Schedule B.

{% if "US" in jurisdictions %}
### Section {{ article_number | default("X") }}.3 — UCC Filings

The Grantor hereby authorizes the Secured Party to file one or more UCC financing statements (and continuation statements, amendments, and assignments thereof) in any filing office as the Secured Party may determine, in its sole discretion, to be necessary or advisable to perfect the security interest granted herein.

**Filing Jurisdiction:** {{ ucc_filing_state | default("Secretary of State of Delaware") }}
{% endif %}

### Section {{ article_number | default("X") }}.4 — Remedies Upon Default

Upon the occurrence of an Event of Default, the Secured Party shall have all rights and remedies available under Applicable Law, including:

(a) The right to take possession of and sell the Collateral;

(b) The right to apply the proceeds to the Obligations; and

(c) All other rights and remedies available under the UCC or other Applicable Law.
