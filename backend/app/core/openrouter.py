from typing import Any

from openai.types import chat
from pydantic_ai.models.openai import OpenAIStreamedResponse
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

_OPENAI_SERVICE_TIERS = {"auto", "default", "flex", "scale", "priority", None}


def _drop_unknown_service_tier(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("service_tier") not in _OPENAI_SERVICE_TIERS:
        data.pop("service_tier", None)
    return data


class CompatibleOpenRouterModel(OpenRouterModel):
    """OpenRouter model with response compatibility for OpenAI SDK enums.

    OpenRouter may return provider-specific metadata values that are not yet part
    of OpenAI's response schema. Pydantic AI revalidates non-streamed responses,
    so strip the incompatible field before delegating to its OpenRouter handling.
    """

    def _validate_completion(self, response: chat.ChatCompletion):
        data = _drop_unknown_service_tier(response.model_dump())
        return super()._validate_completion(chat.ChatCompletion.model_construct(**data))

    @property
    def _streamed_response_cls(self):
        # Pydantic AI's OpenAI streamed response path does not revalidate chunks,
        # which keeps OpenRouter's provider-specific response fields forward-compatible.
        return OpenAIStreamedResponse


def create_openrouter_model() -> CompatibleOpenRouterModel:
    from app.config import settings

    return CompatibleOpenRouterModel(
        model_name=settings.DEFAULT_CHAT_MODEL,
        provider=OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY),
    )
