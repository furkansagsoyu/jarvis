"""Son ayar veya taşıma işlemini geri alır."""
from . import _undo


def undo_last_action() -> str:
    return _undo.undo_last()


SKILLS = [
    {
        "name": "undo_last_action",
        "description": "Son yapılan ses, parlaklık veya dosya taşıma işlemini geri alır. 'Geri al', 'eski haline getir' denince kullanılır.",
        "run": undo_last_action,
    },
]
