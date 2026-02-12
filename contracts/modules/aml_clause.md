{# ============================================================ #}
{# MODULE: AML CLAUSE                                          #}
{# Jurisdiction-conditional anti-money laundering language.     #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("V") }} — ANTI-MONEY LAUNDERING

### Section {{ article_number | default("V") }}.1 — AML Representations

Each Party represents and warrants that:

**(a)** It is in compliance with all applicable anti-money laundering laws and regulations, including but not limited to:

{% if "US" in jurisdictions %}
- The Bank Secrecy Act (31 U.S.C. § 5311 et seq.)
- The USA PATRIOT Act (Pub. L. 107-56)
- FinCEN Customer Due Diligence Rule (31 C.F.R. § 1010.230)
{% endif %}

{% if "VN" in jurisdictions %}
- The Law on Anti-Money Laundering of Vietnam (Law No. 14/2022/QH15)
- Decree No. 19/2023/ND-CP on AML Implementation
- State Bank of Vietnam AML regulations
{% endif %}

{% if "CH" in jurisdictions %}
- The Swiss Anti-Money Laundering Act (AMLA, SR 955.0)
- The Swiss Anti-Money Laundering Ordinance (AMLO, SR 955.01)
- FINMA Anti-Money Laundering Ordinance (SR 955.033.0)
{% endif %}

{% if "GB" in jurisdictions %}
- The Proceeds of Crime Act 2002 (POCA)
- The Money Laundering, Terrorist Financing and Transfer of Funds Regulations 2017 (SI 2017/692)
- The Sanctions and Anti-Money Laundering Act 2018 (SAMLA)
{% endif %}

{% if "SG" in jurisdictions %}
- The Corruption, Drug Trafficking and Other Serious Crimes (Confiscation of Benefits) Act (CDSA, Cap 65A)
- MAS Notice 626 on Prevention of Money Laundering and Countering the Financing of Terrorism
{% endif %}

{% if "KY" in jurisdictions %}
- The Cayman Islands Proceeds of Crime Act (2020 Revision)
- The Cayman Islands Anti-Money Laundering Regulations (2020 Revision)
- The Beneficial Ownership Transparency Act (2020)
{% endif %}

**(b)** It has established and maintains an anti-money laundering compliance program reasonably designed to detect and prevent money laundering activities.

**(c)** It has conducted, and will continue to conduct, appropriate due diligence on its counterparties, beneficial owners, and sources of funds.

### Section {{ article_number | default("V") }}.2 — Beneficial Ownership

Each Party represents that it has disclosed to the other Party all beneficial owners holding, directly or indirectly, {{ beneficial_ownership_threshold | default("25%") }} or more of its equity interests.

{% if "CH" in jurisdictions %}
The Parties acknowledge the requirement to complete Form A (Declaration of Beneficial Owner) in accordance with the Swiss Agreement on the Swiss Banks' Code of Conduct with regard to the Exercise of Due Diligence (CDB 20).
{% endif %}

### Section {{ article_number | default("V") }}.3 — Ongoing Obligations

Each Party agrees to:

(a) Promptly notify the other Party if it becomes aware of any suspicious activity related to this Agreement.

(b) Cooperate with any lawful investigation by a Governmental Authority relating to anti-money laundering compliance.

(c) Maintain records sufficient to demonstrate compliance with applicable AML laws for a period of not less than {{ record_retention_years | default("5") }} years following the termination of this Agreement.
