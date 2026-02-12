{# ============================================================ #}
{# MODULE: ACCREDITED INVESTOR REPRESENTATION                 #}
{# Securities transactions only.                               #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XIV") }} — INVESTOR REPRESENTATIONS

### Section {{ article_number | default("XIV") }}.1 — Accredited Investor Status

{% if "US" in jurisdictions %}
The Investor hereby represents and warrants that it is an "accredited investor" as defined in Rule 501(a) of Regulation D promulgated under the Securities Act of 1933, as amended, by reason of one or more of the following:

(a) It is a bank, insurance company, registered investment company, business development company, or small business investment company;

(b) It is an employee benefit plan with total assets in excess of $5,000,000;

(c) It is a corporation, partnership, limited liability company, or other entity with total assets in excess of $5,000,000;

(d) It is a natural person whose individual net worth, or joint net worth with such person's spouse, exceeds $1,000,000 (excluding the value of the primary residence);

(e) It is a natural person who had individual income in excess of $200,000 in each of the two most recent years (or joint income with such person's spouse in excess of $300,000) and who reasonably expects to reach the same income level in the current year;

(f) It is a "qualified institutional buyer" as defined in Rule 144A under the Securities Act; or

(g) It otherwise qualifies as an "accredited investor" under applicable law.
{% endif %}

{% if "SG" in jurisdictions %}
The Investor hereby represents and warrants that it is an "accredited investor" as defined in Section 4A of the Securities and Futures Act of Singapore (Cap. 289), being an individual whose:

(a) net personal assets exceed SGD 2,000,000 (or its equivalent in a foreign currency); or

(b) income in the preceding 12 months is not less than SGD 300,000 (or its equivalent in a foreign currency).
{% endif %}

### Section {{ article_number | default("XIV") }}.2 — Investment Representations

The Investor further represents and warrants that:

(a) It is acquiring the Securities for its own account, for investment purposes only, and not with a view to, or in connection with, any distribution thereof.

(b) It has such knowledge and experience in financial and business matters as to be capable of evaluating the merits and risks of the investment.

(c) It has been given the opportunity to ask questions of and receive answers from the Company and to obtain additional information necessary to verify the information provided.

(d) It understands that the Securities are "restricted securities" and may not be resold without registration or an applicable exemption.

(e) It can bear the economic risk of the investment, including the total loss thereof.

### Section {{ article_number | default("XIV") }}.3 — Risk Acknowledgment

The Investor acknowledges that an investment in the Securities involves a high degree of risk and that there can be no assurance that the investment objectives will be achieved. The Investor has reviewed the risk factors set forth in the offering materials, if any, and understands the speculative nature of the investment.
