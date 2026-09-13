"""The AI Personal CIO.

The model's job here is narrow and stated explicitly: interpret, explain,
converse and personalise. It does not calculate, it does not retrieve prices,
and it does not decide. Those are :mod:`aicio.engine`, :mod:`aicio.market` and
:mod:`aicio.decisions` respectively.

That boundary is enforced, not merely documented:

*   The model sees a :class:`~aicio.provenance.FactSheet` and a tool surface.
    Anything not in the fact sheet does not exist as far as it is concerned,
    and the system prompt says so in those terms.
*   Every reply passes :mod:`aicio.ai.safety`, which checks the numbers in the
    answer against the numbers in the facts and rewrites or refuses when they
    do not match.
*   Uploaded documents are scrubbed before they can reach a prompt, because a
    PDF is an untrusted input that arrives with the user's own credibility
    attached to it.
*   Prompts are versioned and stored with each reply, so an answer given in
    March can be reproduced in September.
"""

from __future__ import annotations

from .banker import AIBanker, BankerReply
from .gateway import (
    AnthropicGateway, LLMGateway, LLMResponse, OfflineGateway, OpenAIGateway,
    build_gateway,
)
from .safety import GroundingReport, check_grounding, scrub_document

__all__ = [
    "AIBanker", "BankerReply", "LLMGateway", "LLMResponse", "AnthropicGateway",
    "OpenAIGateway", "OfflineGateway", "build_gateway", "check_grounding",
    "scrub_document", "GroundingReport",
]
