"""Yardım: kullanıcı Jarvis'e neler yapabildiğini sorarsa."""


def list_abilities() -> str:
    from skills import capability_summary, load_skills  # noqa: PLC0415

    tools = {k: v for k, v in load_skills().items() if k != "list_abilities"}
    return "Şunları yapabilirim: " + capability_summary(tools) + "."


SKILLS = [
    {
        "name": "list_abilities",
        "description": "Jarvis'in neler yapabildiğini listeler. Kullanıcı neler yapabildiğini veya ne işe yaradığını sorarsa kullan.",
        "run": list_abilities,
    }
]
