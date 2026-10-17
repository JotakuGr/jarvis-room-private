"""Catálogo dos fatos conhecidos nesta fase do projeto."""

from .command_router import normalize

VERIFIED_REPLIES = {
    "quem e voce": (
        "Sou J.A.R.V.I.S., o assistente inteligente "
        "da Sala Temática Universitária. "
        "Minha função é oferecer uma interface de "
        "conversação e, futuramente, integrar os "
        "sistemas de automação da sala. "
        "Ainda não possuo controle físico habilitado."
    ),
    "explique a arquitetura da sala": (
        "A arquitetura planejada utiliza OpenJarvis "
        "para conversação, Ollama para inferência local "
        "e Home Assistant para automação. "
        "ESP32, WLED e Frigate estão previstos para "
        "integrações futuras. "
        "A conexão física com esses sistemas ainda "
        "não foi validada."
    ),
    "quais sao os dois monitores da sala": (
        "O monitor 1 será dedicado à interface visual "
        "do J.A.R.V.I.S. "
        "O monitor 2 apresentará o dashboard operacional "
        "com sensores e estados dos equipamentos. "
        "Essas funcionalidades estão planejadas e "
        "não representam dispositivos já integrados."
    ),
}


def verified_reply_for(message: str) -> str:
    return VERIFIED_REPLIES.get(
        normalize(message),
        "Informação ainda não disponível nesta interface.",
    )
