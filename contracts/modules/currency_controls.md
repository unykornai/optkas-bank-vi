{# ============================================================ #}
{# MODULE: CURRENCY CONTROLS                                   #}
{# Cross-border transactions.                                  #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XVI") }} — CURRENCY AND FOREIGN EXCHANGE

### Section {{ article_number | default("XVI") }}.1 — Currency of Payment

All payments under this Agreement shall be made in {{ settlement_currency | default("United States Dollars (USD)") }}.

### Section {{ article_number | default("XVI") }}.2 — Foreign Exchange Compliance

{% if "VN" in jurisdictions %}
The Parties acknowledge that the Socialist Republic of Vietnam maintains foreign exchange controls pursuant to the Ordinance on Foreign Exchange Control and related regulations issued by the State Bank of Vietnam. Each Party domiciled in Vietnam represents and warrants that:

(a) It has obtained all necessary approvals from the State Bank of Vietnam for foreign exchange transactions contemplated by this Agreement.

(b) All payments to and from Vietnam shall be made through a properly registered capital account at an authorized Vietnamese bank.

(c) It has complied with all reporting obligations to the State Bank of Vietnam in connection with cross-border fund transfers.

(d) It acknowledges that the transaction reporting threshold for foreign exchange transactions is USD {{ vn_fx_threshold | default("5,000") }} or equivalent.
{% endif %}

{% if "CH" in jurisdictions %}
The Parties acknowledge that Switzerland participates in the Common Reporting Standard (CRS) for the automatic exchange of financial account information. Each Party shall comply with all applicable reporting obligations under CRS and Swiss tax law.
{% endif %}

### Section {{ article_number | default("XVI") }}.3 — Settlement Mechanics

(a) **Wire Instructions.** All payments shall be made by wire transfer of immediately available funds in accordance with the wire instructions set forth in Schedule {{ wire_schedule | default("D") }}.

(b) **Exchange Rate.** To the extent any conversion of currency is required, such conversion shall be at the spot rate quoted by {{ fx_rate_source | default("Bloomberg") }} at the close of business on the Business Day immediately preceding the date of payment.

(c) **Payment Costs.** Each Party shall bear its own bank charges and transfer fees. The payor shall bear the cost of any intermediary or correspondent bank fees.

### Section {{ article_number | default("XVI") }}.4 — Withholding

All payments shall be made free and clear of, and without deduction or withholding for, any taxes, unless such deduction or withholding is required by Applicable Law, in which case the payor shall:

(a) pay such additional amounts as are necessary to ensure that the net amount received by the payee equals the full amount that would have been received absent such deduction or withholding; and

(b) provide evidence of payment of the withheld amounts to the relevant Governmental Authority.
