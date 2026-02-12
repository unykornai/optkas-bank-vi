{# ============================================================ #}
{# MODULE: ARBITRATION CLAUSE                                  #}
{# ============================================================ #}

## ARTICLE {{ article_number | default("XI") }} — DISPUTE RESOLUTION

### Section {{ article_number | default("XI") }}.1 — Negotiation

The Parties shall attempt in good faith to resolve any dispute arising out of or relating to this Agreement through direct negotiation between senior executives of each Party within {{ negotiation_period_days | default("30") }} days of written notice of such dispute.

### Section {{ article_number | default("XI") }}.2 — Arbitration

Any dispute, controversy, or claim arising out of or relating to this Agreement, or the breach, termination, or invalidity thereof, that is not resolved pursuant to Section {{ article_number | default("XI") }}.1 shall be finally settled by binding arbitration.

{% if arbitration_body == "AAA" or "US" in jurisdictions %}
Such arbitration shall be administered by the **American Arbitration Association** ("**AAA**") in accordance with its Commercial Arbitration Rules then in effect.

- **Seat of Arbitration:** {{ arbitration_seat | default("New York, New York") }}
- **Number of Arbitrators:** {{ arbitrator_count | default("3") }}
- **Language:** English
{% endif %}

{% if arbitration_body == "SIAC" or "SG" in jurisdictions or "VN" in jurisdictions %}
Such arbitration shall be administered by the **Singapore International Arbitration Centre** ("**SIAC**") in accordance with the SIAC Arbitration Rules then in effect.

- **Seat of Arbitration:** Singapore
- **Number of Arbitrators:** {{ arbitrator_count | default("3") }}
- **Language:** English
{% endif %}

{% if arbitration_body == "LCIA" or "GB" in jurisdictions or "KY" in jurisdictions %}
Such arbitration shall be administered by the **London Court of International Arbitration** ("**LCIA**") in accordance with the LCIA Arbitration Rules then in effect.

- **Seat of Arbitration:** London, England
- **Number of Arbitrators:** {{ arbitrator_count | default("3") }}
- **Language:** English
{% endif %}

{% if "CH" in jurisdictions %}
Such arbitration shall be administered by the **Swiss Arbitration Centre** in accordance with the Swiss Rules of International Arbitration then in effect.

- **Seat of Arbitration:** {{ arbitration_seat | default("Zurich, Switzerland") }}
- **Number of Arbitrators:** {{ arbitrator_count | default("3") }}
- **Language:** English
{% endif %}

### Section {{ article_number | default("XI") }}.3 — Enforceability

The arbitral award shall be final and binding upon the Parties. Judgment on the award rendered may be entered in any court having jurisdiction thereof.

{% if is_cross_border %}
The Parties acknowledge that the arbitral award shall be enforceable under the Convention on the Recognition and Enforcement of Foreign Arbitral Awards (New York Convention, 1958).
{% endif %}

### Section {{ article_number | default("XI") }}.4 — Provisional Measures

Nothing in this Article shall prevent either Party from seeking provisional or injunctive relief from a court of competent jurisdiction to prevent irreparable harm pending the outcome of arbitration.
