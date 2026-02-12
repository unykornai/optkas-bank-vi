{# ============================================================ #}
{# MODULE: SANCTIONS COMPLIANCE                                #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("VI") }} — SANCTIONS COMPLIANCE

### Section {{ article_number | default("VI") }}.1 — OFAC and Sanctions Representations

Each Party represents and warrants that:

**(a)** Neither it, nor any of its directors, officers, employees, agents, or Affiliates, nor, to its knowledge, any of its beneficial owners:

  (i) is a Sanctioned Person (as defined below);

  (ii) is located, organized, or resident in a Sanctioned Jurisdiction;

  (iii) is owned or controlled by, or acting on behalf of, a Sanctioned Person; or

  (iv) has engaged in, or is currently engaged in, any dealings or transactions with or for the benefit of any Sanctioned Person or Sanctioned Jurisdiction.

**(b)** "**Sanctioned Person**" means any person or entity that is the subject of sanctions administered or enforced by:

{% if "US" in jurisdictions %}
  - The U.S. Department of the Treasury's Office of Foreign Assets Control ("**OFAC**"), including persons listed on the Specially Designated Nationals and Blocked Persons List ("**SDN List**"), the Sectoral Sanctions Identification List, or the Foreign Sanctions Evaders List;
  - The U.S. Department of State;
  - The U.S. Department of Commerce, Bureau of Industry and Security;
{% endif %}

{% if "GB" in jurisdictions %}
  - Her Majesty's Treasury ("**HMT**");
  - The UK Office of Financial Sanctions Implementation ("**OFSI**");
{% endif %}

{% if "SG" in jurisdictions %}
  - The Monetary Authority of Singapore ("**MAS**");
{% endif %}

  - The United Nations Security Council; or
  - The European Union.

**(c)** "**Sanctioned Jurisdiction**" means, at any time, any country or territory that is itself the subject or target of comprehensive Sanctions, including, without limitation, Cuba, Iran, North Korea, Syria, and the Crimea, Donetsk, and Luhansk regions of Ukraine.

### Section {{ article_number | default("VI") }}.2 — Covenant

Each Party covenants that it shall not, directly or indirectly, use the proceeds of the transactions contemplated by this Agreement, or lend, contribute, or otherwise make available such proceeds to any Person:

(a) to fund any activities or business of or with any Sanctioned Person or in any Sanctioned Jurisdiction; or

(b) in any other manner that would result in a violation of Sanctions by any Person.

### Section {{ article_number | default("VI") }}.3 — Ongoing Screening

Each Party agrees to conduct sanctions screening against applicable sanctions lists on a periodic basis, and no less frequently than {{ sanctions_screening_frequency | default("quarterly") }}, for the duration of this Agreement.
