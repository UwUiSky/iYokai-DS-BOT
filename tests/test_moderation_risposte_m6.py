"""
tests/test_moderation_risposte_m6.py
====================================
M6 (#115): conferma a due tasti prima di sanzionare (MOD-066) e risposte compatte o cancellate dopo N secondi
(MOD-067). Opzioni nel punto unico, di base come prima. Database vero.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core import moderation_conferma as conferma
from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from core.moderation_conferma import ConfermaSanzione, conferma_sanzione, invia_esito
from core import moderation_opzioni, moderation_risposte as risposte
from core.command_access import Livello
from core.database import db
from tests.support.discord_fakes import fake_interaction
from tests.test_moderation_ordine_azione import ID_CANALE_LOG, ID_SERVER, Scena

G = ID_SERVER


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    yield
    database_module.db._modules_cache.clear()


def test_logica_modi_e_secondi():
    assert risposte.modo_valido("compatta") == "compatta" and risposte.modo_valido("boh") == "normale"
    assert [risposte.secondi_validi(x) for x in (5, 300, 4, 301, True, "9", None)] == [5, 300, 30, 30, 30, 30, 30]
    assert risposte.puo_cancellare(300) and not risposte.puo_cancellare(60, trascorsi=risposte.VITA_TOKEN_S)


def test_riga_compatta_una_riga_con_tetto():
    riga = risposte.riga_compatta("Warn", {"Utente": "<@1>", "Caso": "#3", "Motivo": "x" * 900}, nota="DM no")
    assert "\n" not in riga and riga.startswith("Warn · <@1> · #3") and len(riga) <= risposte.MAX_RIGA


async def test_di_base_come_prima():
    o = await moderation_opzioni.leggi(G)
    assert (o.conferma, o.risposte, o.risposte_secondi) == (False, "normale", 30)


async def test_opzioni_si_salvano_e_i_valori_strani_si_rifiutano():
    await moderation_opzioni.imposta_conferma(G, True, 1)
    await moderation_opzioni.imposta_risposte(G, "cancella-dopo", 45, 1)
    o = await moderation_opzioni.leggi(G)
    assert (o.conferma, o.risposte, o.risposte_secondi) == (True, "cancella-dopo", 45)
    with pytest.raises(ValueError):
        await moderation_opzioni.imposta_risposte(G, "boh", None, 1)
    with pytest.raises(ValueError):
        await moderation_opzioni.imposta_risposte(G, "compatta", 4, 1)


async def test_warn_di_base_risponde_col_riquadro_senza_domande():
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    scena.interazione.response.send_message.assert_awaited_once()
    assert "embed" in scena.interazione.response.send_message.await_args.kwargs


async def test_con_compatta_il_warn_e_una_riga():
    await moderation_opzioni.imposta_risposte(G, "compatta", None, 1)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    kw = scena.interazione.response.send_message.await_args.kwargs
    assert "embed" not in kw and "Warn" in kw["content"] and "Spam ripetuto" in kw["content"]


async def test_cancella_dopo_programma_la_cancellazione(monkeypatch):
    await moderation_opzioni.imposta_risposte(G, "cancella-dopo", 7, 1)
    scena = Scena()
    messaggio = MagicMock()
    messaggio.delete = AsyncMock()
    scena.interazione.original_response = AsyncMock(return_value=messaggio)
    attese = []

    async def _sonno(s):
        attese.append(s)

    monkeypatch.setattr(conferma.asyncio, "sleep", _sonno)
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    await __import__("asyncio").gather(*list(conferma._cancellazioni))
    assert attese == [7]
    messaggio.delete.assert_awaited_once()


async def test_con_conferma_la_sanzione_non_parte_senza_clic(monkeypatch):
    await moderation_opzioni.imposta_conferma(G, True, 1)
    scena = Scena()

    async def _scade(self, *a, **k):
        return True

    monkeypatch.setattr(ConfermaSanzione, "wait", _scade)  # scaduta: esito resta None
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    kw = scena.interazione.response.send_message.await_args.kwargs
    assert kw["ephemeral"] is True and isinstance(kw["view"], ConfermaSanzione)
    scena.interazione.edit_original_response.assert_awaited_once()
    assert scena.interazione.response.send_message.await_count == 1  # nessun riquadro di warn
    assert scena.chiamate == []


async def test_conferma_continua_con_l_interazione_del_tasto(monkeypatch):
    await moderation_opzioni.imposta_conferma(G, True, 1)
    scena = Scena()
    tasto = fake_interaction(guild=scena.server, user=scena.moderatore)
    monkeypatch.setattr("core.moderation_conferma.puo_usare", AsyncMock(return_value=True))

    async def _clic(self, *a, **k):
        self.esito, self.interazione = True, tasto
        return True

    monkeypatch.setattr(ConfermaSanzione, "wait", _clic)
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    tasto.response.send_message.assert_awaited_once()  # il riquadro del warn esce sull'interazione del tasto
    assert "embed" in tasto.response.send_message.await_args.kwargs


async def test_alla_conferma_il_livello_si_ricontrolla(monkeypatch):
    await moderation_opzioni.imposta_conferma(G, True, 1)
    scena = Scena()
    tasto = fake_interaction(guild=scena.server, user=scena.moderatore)
    monkeypatch.setattr("core.moderation_conferma.puo_usare", AsyncMock(return_value=False))

    async def _clic(self, *a, **k):
        self.esito, self.interazione = True, tasto
        return True

    monkeypatch.setattr(ConfermaSanzione, "wait", _clic)
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "Spam ripetuto")
    assert tasto.response.send_message.await_args.kwargs["ephemeral"] is True
    assert "embed" not in tasto.response.send_message.await_args.kwargs


async def test_conferma_gerarchia_cambiata_blocca(monkeypatch):
    await moderation_opzioni.imposta_conferma(G, True, 1)
    scena = Scena()
    tasto = fake_interaction(guild=scena.server, user=scena.moderatore)
    monkeypatch.setattr("core.moderation_conferma.puo_usare", AsyncMock(return_value=True))
    monkeypatch.setattr("core.moderation_conferma.check_can_moderate", AsyncMock(return_value=False))
    scena.interazione.edit_original_response = AsyncMock()
    r = None

    async def _clic(self, *a, **k):
        self.esito, self.interazione = True, tasto
        return True

    monkeypatch.setattr(ConfermaSanzione, "wait", _clic)
    r = await conferma_sanzione(scena.interazione, scena.bersaglio, "warn", "x", livello=Livello.MOD)
    assert r is None


async def test_doppio_clic_e_altro_utente():
    vista = ConfermaSanzione(autore_id=5)
    i1, i2 = MagicMock(), MagicMock()
    await vista.conferma.callback(i1)
    await vista.conferma.callback(i2)
    assert vista.interazione is i1 and vista.esito is True
    altro = fake_interaction()
    altro.user.id = 99
    assert await vista.interaction_check(altro) is False
