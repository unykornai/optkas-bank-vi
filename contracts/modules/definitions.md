{# ============================================================ #}
{# MODULE: DEFINITIONS                                         #}
{# ============================================================ #}

## ARTICLE I — DEFINITIONS

As used in this Agreement, the following terms shall have the meanings set forth below:

"**Affiliate**" means, with respect to any Person, any other Person that directly or indirectly controls, is controlled by, or is under common control with such Person.

"**Agreement**" means this {{ transaction_type_display }}, including all exhibits, schedules, and annexes attached hereto.

"**Applicable Law**" means all applicable laws, statutes, rules, regulations, ordinances, orders, decrees, judgments, injunctions, and governmental requirements of any Governmental Authority.

"**Business Day**" means any day other than a Saturday, Sunday, or a day on which banking institutions in {{ governing_law_jurisdiction }} are authorized or required by law to remain closed.

"**Governmental Authority**" means any government, governmental department, commission, board, bureau, agency, court, tribunal, or other instrumentality, whether federal, state, provincial, local, or foreign.

"**Losses**" means any and all losses, damages, liabilities, claims, costs, and expenses (including reasonable attorneys' fees).

"**Material Adverse Effect**" means any event, circumstance, or condition that, individually or in the aggregate, has or would reasonably be expected to have a material adverse effect on (a) the business, assets, financial condition, or results of operations of the applicable Party, or (b) the ability of the applicable Party to consummate the transactions contemplated hereby.

"**Person**" means any natural person, corporation, limited liability company, partnership, trust, governmental authority, or other entity.

{% if transaction_category == "securities" %}
"**Securities**" means the securities described in Schedule A hereto.

"**Securities Act**" means the Securities Act of 1933, as amended.

"**Exchange Act**" means the Securities Exchange Act of 1934, as amended.

"**Accredited Investor**" has the meaning set forth in Rule 501(a) of Regulation D under the Securities Act.
{% endif %}

{% if transaction_category == "debt" %}
"**Facility**" means the credit facility established pursuant to this Agreement.

"**Interest Rate**" means the rate of interest specified in Schedule A hereto.

"**Maturity Date**" means the date specified in Schedule A hereto.

"**Principal Amount**" means the aggregate principal amount outstanding under the Facility.
{% endif %}

{% if is_cross_border %}
"**Foreign Exchange Rate**" means the exchange rate published by {{ fx_rate_source | default("Bloomberg") }} at the close of business on the relevant date.

"**Sanctioned Jurisdiction**" means any country or territory that is the subject of comprehensive Sanctions.

"**Sanctions**" means economic or financial sanctions or trade embargoes imposed, administered, or enforced by the U.S. Department of the Treasury's Office of Foreign Assets Control, the United Nations Security Council, the European Union, or Her Majesty's Treasury.
{% endif %}
