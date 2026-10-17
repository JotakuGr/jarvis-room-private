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
            model="jarvis-dev-lite:latest",
        ) as jarvis:
            return jarvis.ask(
                prompt,
                agent="simple",
                tools=[],
                context=False,
                temperature=0.2,
                max_tokens=192,
            )
