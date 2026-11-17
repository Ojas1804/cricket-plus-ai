from app.ai.models import Intent
from app.ai.providers.base import LLMProvider

INTENT_SYSTEM = """You interpret requests for a cricket analytics workspace.
Classify the request and extract the cricket entities mentioned. Do not compute or guess any statistics.

kind:
- analytics: needs statistics from historical match data (rankings, averages, comparisons, trends, filters).
- explain: asks what a statistic or cricket concept means.
- live: asks for live or in-progress match scores.
- unsupported: not about cricket, or impossible to answer from cricket statistics.

entities: copy names exactly as the user wrote them (players, teams, competitions, venues). Use empty lists when none.
If an existing widget is provided, a short follow-up (e.g. "only players with 50+ matches") is an analytics request modifying it.
Set clarification_question to a short question only when the request is too vague to act on or unsupported, otherwise an empty string.
summary: one sentence restating the request."""

EXPLAIN_SYSTEM = """You are a cricket statistics explainer. Explain the concept clearly in at most 120 words.
Do not state any specific player or team statistics or records; explain definitions and how calculations work only."""


def interpret_prompt(provider: LLMProvider, prompt: str, existing_widget: str | None = None) -> Intent:
    user = f"Request: {prompt}"
    if existing_widget:
        user += f"\n\nExisting widget being modified (JSON): {existing_widget}"
    return provider.parse(INTENT_SYSTEM, user, Intent)


def generate_explanation(provider: LLMProvider, prompt: str) -> str:
    return provider.text(EXPLAIN_SYSTEM, prompt)
