"""Stub agents for the example suites. Pure Python, offline, deterministic.

These exist so the suites can be run end to end with --fake-judge and no
network access. They are intentionally simple keyword matchers, not real
agents.
"""


def support_agent(user_input: str) -> str:
    """Tiny customer-support agent answering from a small knowledge dict."""
    text = user_input.lower()

    topics = [
        (
            {"damaged", "arrived broken", "broken item", "broken", "defective"},
            "I'm really sorry about that. For a damaged item we can send a "
            "free replacement right away, or issue a full refund, whichever "
            "you prefer. Just share your order number and a photo of the "
            "damage if you have one.",
        ),
        (
            {"refund", "return", "stopped working", "broken"},
            "I'm sorry to hear that! Happy to help. Our policy offers a full "
            "refund within 30 days of delivery for faulty or damaged items. "
            "Just reply with your order number and we will process your refund "
            "right away.",
        ),
        (
            {"where is my order", "track", "order status", "order number is"},
            "I can help you track that. Your order {order} is on its way, "
            "currently at the regional sorting facility. Use this tracking "
            "link to follow it live: https://example.com/track/{order}. "
            "It should arrive within the estimated window.",
        ),
        (
            {"how long", "shipping take", "delivery take", "when will it arrive"},
            "Happy to help! Standard shipping takes 3-5 business days after "
            "your order ships, and express shipping takes 1-2 business days. "
            "You will get a tracking link by email as soon as it leaves our warehouse.",
        ),
        (
            {"cancel my order", "cancel order"},
            "Of course. Orders can be cancelled for a full refund within 24 "
            "hours of purchase, before they ship. Share your order number and "
            "I will cancel it for you now.",
        ),
    ]

    for keywords, answer in topics:
        if any(k in text for k in keywords):
            order = _find_order_number(user_input) or "UNKNOWN"
            return answer.format(order=order)

    return (
        "Thanks for reaching out. I can only help with orders and shipping "
        "questions. For anything else, please contact our support team and "
        "they will point you in the right direction."
    )


def _find_order_number(text: str) -> str | None:
    import re

    match = re.search(r"\b\d{4,}\b", text)
    return match.group(0) if match else None


_HOT_SIGNALS = [
    "budget approved", "budget is approved", "ready to buy", "sign this week",
    "sign today", "call me today", "asap", "send me the contract",
    "purchase order", "need 50", "let's do it",
]
_COLD_SIGNALS = [
    "just browsing", "just looking", "not looking to buy", "not interested",
    "maybe later", "unsubscribe", "not really", "no thanks",
]


def lead_triage_agent(message: str) -> str:
    """Stub lead-qualification agent: classifies a lead as HOT, WARM, or COLD."""
    text = message.lower()

    hot_hits = [s for s in _HOT_SIGNALS if s in text]
    if hot_hits:
        signals = ", ".join(f"'{s}'" for s in hot_hits)
        return (
            "Classification: HOT\n"
            f"Rationale: the lead's message references strong buying signals ({signals}) "
            "with an immediate timeline. The stated urgency captures the deal size, "
            "so route to sales immediately."
        )
    cold_hits = [s for s in _COLD_SIGNALS if s in text]
    if cold_hits:
        signals = ", ".join(f"'{s}'" for s in cold_hits)
        return (
            "Classification: COLD\n"
            f"Rationale: the lead's message references weak buying signals ({signals}). "
            "The stated intent shows this is not sales-ready, so keep it on the nurture list."
        )
    return (
        "Classification: WARM\n"
        "Rationale: the lead is evaluating vendors and asked for pricing, but "
        "gave no immediate timeline. Nurture with a follow-up next week."
    )
