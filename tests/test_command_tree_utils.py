"""
tests/test_command_tree_utils.py
====================================
Test di core/command_tree_utils.py — con app_commands.Command/Group
VERI (non finti), dato che è proprio il comportamento di
app_commands.Group ad essere sotto test (isinstance, .commands).
"""

from discord import app_commands


async def _callback_vuoto(interaction) -> None:
    pass


def _comando(name: str, description: str) -> app_commands.Command:
    return app_commands.Command(name=name, description=description, callback=_callback_vuoto)


class TestWalkCommands:
    def test_comandi_top_level_semplici(self):
        from core.command_tree_utils import walk_commands

        comandi = [_comando("ping", "Controlla la latenza."), _comando("poll", "Crea un sondaggio.")]
        risultato = walk_commands(comandi)

        assert ("ping", "Controlla la latenza.") in risultato
        assert ("poll", "Crea un sondaggio.") in risultato

    def test_sottocomandi_di_un_gruppo_hanno_il_prefisso(self):
        from core.command_tree_utils import walk_commands

        gruppo = app_commands.Group(name="reminder", description="Promemoria")
        gruppo.add_command(_comando("set", "Imposta un promemoria."))
        gruppo.add_command(_comando("list", "Mostra i promemoria."))

        risultato = walk_commands([gruppo])

        assert ("reminder set", "Imposta un promemoria.") in risultato
        assert ("reminder list", "Mostra i promemoria.") in risultato

    def test_gruppo_e_comandi_semplici_insieme(self):
        from core.command_tree_utils import walk_commands

        gruppo = app_commands.Group(name="sticky", description="Sticky message")
        gruppo.add_command(_comando("set", "Imposta lo sticky."))

        risultato = walk_commands([_comando("ping", "Latenza."), gruppo])

        assert ("ping", "Latenza.") in risultato
        assert ("sticky set", "Imposta lo sticky.") in risultato

    def test_comando_senza_descrizione_ha_un_placeholder(self):
        from core.command_tree_utils import walk_commands

        comando = app_commands.Command(
            name="senza_desc", description="", callback=_callback_vuoto
        )
        risultato = walk_commands([comando])

        assert risultato == [("senza_desc", "(nessuna descrizione)")]
