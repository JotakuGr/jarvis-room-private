"""Adaptador de conversação OpenJarvis sem ferramentas de automação."""


class OpenJarvisConversation:
    """Adaptador de conversação sem ferramentas físicas."""

    def __call__(self, prompt: str) -> str:
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
