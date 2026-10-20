"""Adaptador OpenJarvis com verificação prévia de memória."""

from .inference_policy import (
    LocalInferenceUnavailable,
    check_current_resources,
)


class OpenJarvisConversation:
    """Conversação experimental sem ferramentas físicas."""

    def __call__(self, prompt: str) -> str:
        decision = check_current_resources()
        if not decision.allowed:
            raise LocalInferenceUnavailable(decision.reason)

        # Importação e inicialização somente após a avaliação de recursos.
        from openjarvis import Jarvis

        with Jarvis(
            engine_key="ollama",
            model=self.model,
        ) as jarvis:
            return jarvis.ask(
                prompt,
                agent="simple",
                tools=[],
                context=False,
                temperature=0.2,
                max_tokens=self.max_tokens,
            )

    def __init__(
        self, *, model: str = "jarvis-dev-lite:latest", max_tokens: int = 192
    ) -> None:
        self.model, self.max_tokens = model, max_tokens
