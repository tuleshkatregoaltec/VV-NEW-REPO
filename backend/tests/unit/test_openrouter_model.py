from openai.types.chat import ChatCompletion
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.core.openrouter import CompatibleOpenRouterModel


def test_openrouter_model_accepts_standard_response_service_tier() -> None:
    model = CompatibleOpenRouterModel(
        "google/gemini-3-flash-preview",
        provider=OpenRouterProvider(api_key="test-key"),
    )
    response = ChatCompletion.model_construct(
        id="chatcmpl-test",
        choices=[
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {"content": "ok", "role": "assistant"},
                "native_finish_reason": "stop",
            }
        ],
        created=1,
        model="google/gemini-3-flash-preview",
        object="chat.completion",
        provider="google-ai-studio",
        service_tier="standard",
    )

    validated = model._validate_completion(response)

    assert validated.choices[0].message.content == "ok"
    assert validated.provider == "google-ai-studio"
    assert validated.service_tier is None
