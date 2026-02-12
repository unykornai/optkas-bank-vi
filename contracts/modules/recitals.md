{# ============================================================ #}
{# MODULE: RECITALS                                             #}
{# Jurisdiction-aware. Variables injected by assembler.         #}
{# ============================================================ #}

## RECITALS

**WHEREAS**, {{ party_a.legal_name }}, a {{ party_a.entity_type }} organized and existing under the laws of {{ party_a.jurisdiction_full_name }} (the "**{{ party_a.short_name }}**"), with its registered address at {{ party_a.registered_address_full }}; and

**WHEREAS**, {{ party_b.legal_name }}, a {{ party_b.entity_type }} organized and existing under the laws of {{ party_b.jurisdiction_full_name }} (the "**{{ party_b.short_name }}**"), with its registered address at {{ party_b.registered_address_full }};

**WHEREAS**, the {{ party_a.short_name }} and the {{ party_b.short_name }} (each a "**Party**" and collectively, the "**Parties**") desire to enter into this {{ transaction_type_display }} (the "**Agreement**") on the terms and conditions set forth herein;

{% if is_cross_border %}
**WHEREAS**, this Agreement involves a cross-border transaction between entities domiciled in {{ party_a.jurisdiction }} and {{ party_b.jurisdiction }}, and the Parties acknowledge that the laws, regulations, and requirements of both jurisdictions shall apply as set forth herein;
{% endif %}

{% if transaction_category == "securities" %}
**WHEREAS**, the securities contemplated by this Agreement have not been registered under the Securities Act of 1933, as amended (the "**Securities Act**"), or under any state securities laws, and are being offered and sold in reliance upon exemptions from registration thereunder;
{% endif %}

{% if transaction_category == "debt" %}
**WHEREAS**, the {{ party_b.short_name }} has requested, and the {{ party_a.short_name }} has agreed to provide, certain credit facilities subject to the terms and conditions of this Agreement;
{% endif %}

**NOW, THEREFORE**, in consideration of the mutual covenants and agreements set forth herein and for other good and valuable consideration, the receipt and sufficiency of which are hereby acknowledged, the Parties agree as follows:
