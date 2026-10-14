"""
tests/test_command_search_bilingue.py
=====================================
NF-06 (#77, SPEC 21.5): la ricerca dei comandi capisce l'italiano e l'inglese, mostra il testo nella
lingua di chi cerca e nasconde i comandi il cui modulo è spento nel server.
"""

import pytest
from discord import app_commands

from core import command_search_logic as logica


def _albero():
    async def cb(interaction):  # pragma: no cover
        pass

    modban = app_commands.Group(name="modban", description="Moderazione dura: ban, kick, softban e sban")
    modban.add_command(app_commands.Command(name="ban", description="Banna permanentemente un membro.", callback=cb))
    mod = app_commands.Group(name="mod", description="Moderazione")
    mod.add_command(app_commands.Command(name="mute", description="Silenzia un membro con un ruolo dedicato.", callback=cb))
    mod.add_command(app_commands.Command(name="clear", description="Cancella un numero di messaggi.", callback=cb))
    gestione = app_commands.Group(name="gestione", description="Gestione del server")
    gestione.add_command(app_commands.Command(name="crea", description="Crea qualcosa.", callback=cb))
    return [modban, mod]


def _comandi():
    return logica.raccogli_comandi(_albero())


def test_il_comando_porta_con_se_la_versione_inglese():
    ban = next(c for c in _comandi() if c.percorso == "modban ban")
    assert ban.percorso_en == "modban ban"
    assert ban.descrizione_en == "Permanently bans a member."


@pytest.mark.parametrize(
    "domanda, atteso",
    [
        ("ban a member", "modban ban"),
        ("kick someone out", "modban ban"),
        ("I want to silence someone", "mod mute"),
        ("delete messages", "mod clear"),
        ("bannare qualcuno", "modban ban"),          # l'italiano non si rompe
        ("cancella messaggi", "mod clear"),
    ],
)
def test_la_ricerca_trova_il_comando_in_entrambe_le_lingue(domanda, atteso):
    risultati = logica.cerca(domanda, _comandi())
    assert risultati and risultati[0].percorso == atteso


def test_i_risultati_si_mostrano_nella_lingua_di_chi_cerca():
    risultati = logica.cerca("ban a member", _comandi())
    en = logica.embed_risultati(risultati, {}, "ban a member", "en")
    assert en.title == '🔍 Results for "ban a member"'
    assert "Permanently bans a member." in en.fields[0].value and "No options." in en.fields[0].value
    it = logica.embed_risultati(risultati, {}, "ban a member", "it")
    assert "Banna permanentemente" in it.fields[0].value and "Nessuna opzione." in it.fields[0].value


def test_il_completamento_mostra_la_descrizione_inglese_agli_utenti_inglesi():
    voci = logica.suggerimenti("modban", _comandi(), lingua="en")
    assert voci and "Permanently bans a member." in voci[0][0]
    assert voci[0][1] == "modban ban"  # il valore resta il percorso di base


@pytest.mark.asyncio
async def test_un_comando_con_il_modulo_spento_non_si_propone():
    spento = logica.ComandoInfo("a uno", "x", "a", (), moduli=("mod_x",))
    acceso = logica.ComandoInfo("b uno", "x", "b", (), moduli=("mod_x", "mod_y"))
    libero = logica.ComandoInfo("c uno", "x", "c", ())

    async def attivo(nome):
        return nome == "mod_y"

    async def tutti_spenti(nome):
        return False

    assert [c.percorso for c in await logica.filtra_per_moduli([spento, acceso, libero], attivo)] == ["b uno", "c uno"]
    assert [c.percorso for c in await logica.filtra_per_moduli([spento, acceso, libero], tutti_spenti)] == ["c uno"]


@pytest.mark.asyncio
async def test_i_moduli_di_un_comando_vengono_dal_file_che_lo_definisce():
    from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

    creato = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti
        tutti = logica.raccogli_comandi(bot.tree.get_commands())
        con_moduli = [c for c in tutti if c.moduli]
        assert len(con_moduli) > 50, "i comandi dei moduli accendibili devono dichiarare il modulo"
        assert any(not c.moduli for c in tutti), "ci devono essere comandi sempre disponibili"
        gioco = next(c for c in tutti if c.percorso == "fun rps")
        assert "fun" in gioco.moduli
    finally:
        await close_full_bot(bot)
        if creato:
            from core.database import db

            await db.close()
