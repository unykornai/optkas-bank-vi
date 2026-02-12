{# ============================================================ #}
{# MODULE: TRANSFER RESTRICTIONS                               #}
{# Securities transactions only.                               #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XIII") }} — TRANSFER RESTRICTIONS

### Section {{ article_number | default("XIII") }}.1 — Restrictions on Transfer

The Securities acquired pursuant to this Agreement have not been registered under the Securities Act or the securities laws of any state or other jurisdiction and may not be offered, sold, transferred, pledged, hypothecated, or otherwise disposed of except:

{% if "US" in jurisdictions %}
(a) pursuant to an effective registration statement under the Securities Act;

(b) pursuant to an available exemption from registration under the Securities Act, including without limitation Rule 144 or Rule 144A thereunder (if available);

(c) in a transaction not requiring registration under the Securities Act; or

(d) pursuant to Regulation S under the Securities Act in an offshore transaction,

in each case, in compliance with all applicable securities laws.
{% endif %}

{% if "SG" in jurisdictions %}
The Securities have not been registered under the Securities and Futures Act of Singapore (Cap. 289) and may not be offered, sold, or transferred except in compliance with the conditions specified in Section 272B or other applicable exemptions under the SFA.
{% endif %}

{% if "VN" in jurisdictions %}
The Securities are subject to a lock-up period of {{ lockup_period | default("1 year") }} from the date of issuance and may not be transferred during such period. Thereafter, transfers shall comply with the regulations of the State Securities Commission of Vietnam.
{% endif %}

### Section {{ article_number | default("XIII") }}.2 — Legend

Each certificate or book-entry representing the Securities shall bear a restrictive legend substantially in the following form:

> "THE SECURITIES REPRESENTED HEREBY HAVE NOT BEEN REGISTERED UNDER THE SECURITIES ACT OF 1933, AS AMENDED, OR THE SECURITIES LAWS OF ANY STATE OR OTHER JURISDICTION. THESE SECURITIES MAY NOT BE OFFERED, SOLD, TRANSFERRED, OR OTHERWISE DISPOSED OF EXCEPT PURSUANT TO AN EFFECTIVE REGISTRATION STATEMENT OR AN APPLICABLE EXEMPTION FROM REGISTRATION."

### Section {{ article_number | default("XIII") }}.3 — No Public Offering

The issuer has not made, and will not make, any public offering of the Securities. This Agreement does not constitute an offer to sell or a solicitation of an offer to buy any securities in any jurisdiction in which such offer or solicitation would be unlawful.
