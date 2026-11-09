"""B3 di #131 (D70): tabella punteggi, dado, spinner, mazzo e azzeramento con conferma."""
import asyncio
import random
from unittest.mock import AsyncMock, patch

import discord
import pytest

from cogs.fun import giochi_extra as ge
from cogs.fun.entertainment import MODULE_FUN
from core import fun_gare_logic as g
from core.database import db
from core.repositories.fun_gare_repo import fun_gare_repo as repo
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction

ID = 103


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


# --- logica ---------------------------------------------------------------

def test_mazzo_52_carte_uniche_e_pesca():
    mazzo = g.nuovo_mazzo(random.Random(1))
    assert len(set(mazzo.split(","))) == 52
    carte, resto = g.pesca_dal_mazzo(mazzo, 3)
    assert len(carte) == 3 and g.restanti(resto) == 49
    assert len(g.pesca_dal_mazzo(mazzo, 99)[0]) == g.MAX_PESCA
    assert g.pesca_dal_mazzo("", 2) == ([], "")
    assert g.carta_testo("TS") == "10♠" and g.carta_testo("AH") == "A♥"


def test_periodi_e_righe():
    from datetime import datetime, timezone

    d = datetime(2026, 11, 9, tzinfo=timezone.utc)
    assert g.periodo_giorno(d) == "2026-11-09" and g.periodo_giorno(d, 1) == "2026-11-08"
    assert g.periodo_settimana(d) == "2026-W46"
    testo = g.testo_classifica([(i, 99999999999) for i in range(1, 30)])
    assert len(testo.split("\n")) == g.TOP and all(len(r) <= g.MAX_RIGA for r in testo.split("\n"))


def test_durata_spinner_nei_limiti():
    r = random.Random(5)
    assert all(1 <= g.durata_spinner(r) <= 60 for _ in range(200))


# --- repository -----------------------------------------------------------

@pytest.fixture(autouse=True)
async def _db(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    dm.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID, MODULE_FUN, True)
    yield
    dm.db._modules_cache.clear()


async def test_dado_un_solo_tiro_al_giorno_anche_insieme(clean_db):
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(*[repo.prova_dado(ID, 7, "2026-11-09", 50 + i) for i in range(8)])
    assert sum(e is not None for e in esiti) == 1
    assert await repo.tiro_del_giorno(ID, 7, "2026-11-09") in range(50, 58)


async def test_classifiche_oggi_ieri_sempre():
    await repo.prova_dado(ID, 1, "2026-11-09", 30)
    await repo.prova_dado(ID, 2, "2026-11-09", 80)
    await repo.prova_dado(ID, 1, "2026-11-08", 90)
    assert await repo.classifica(ID, "dado", "2026-11-09") == [(2, 80), (1, 30)]
    assert await repo.classifica(ID, "dado", "2026-11-08") == [(1, 90)]
    assert await repo.classifica_sempre(ID, "dado") == [(1, 120), (2, 80)]
    assert await repo.classifica(ID + 1, "dado", "2026-11-09") == []


async def test_spinner_un_giro_ogni_ora_e_record_della_settimana(clean_db):
    assert await repo.registra_giro(ID, 5, "2026-W46", 20) is True
    assert await repo.registra_giro(ID, 5, "2026-W46", 59) is False
    await clean_db.execute("UPDATE fun_punteggi SET aggiornato = now() - interval '2 hours'")
    assert await repo.registra_giro(ID, 5, "2026-W46", 10) is True
    assert await repo.classifica(ID, "spinner", "2026-W46") == [(5, 20)]  # tiene il record
    await clean_db.execute("UPDATE fun_punteggi SET aggiornato = now() - interval '2 hours'")
    assert await repo.registra_giro(ID, 5, "2026-W47", 3) is True  # settimana nuova, ma l'ora e' passata


async def test_spinner_giri_insieme_ne_parte_uno(clean_db):
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(*[repo.registra_giro(ID, 9, "2026-W46", 5 + i) for i in range(8)])
    assert sum(esiti) == 1


async def test_mazzo_pesca_senza_doppioni_anche_insieme_e_rimescola(clean_db):
    await apri_connessioni(clean_db)
    rng = random.Random(2)
    risultati = await asyncio.gather(*[repo.pesca(ID, 10, rng) for _ in range(6)])
    carte = [c for cc, _ in risultati for c in cc]
    assert len(carte) == 52 and len(set(carte)) == 52
    assert await repo.carte_restanti(ID) == 0
    assert await repo.pesca(ID, 1, rng) == ([], 0)
    await repo.rimescola(ID, rng)
    assert await repo.carte_restanti(ID) == 52
    assert await repo.carte_restanti(ID + 5) == 52  # server senza mazzo: ancora intero


async def test_azzera_una_gara_o_tutte():
    await repo.prova_dado(ID, 1, "2026-11-09", 30)
    await repo.registra_giro(ID, 1, "2026-W46", 4)
    await repo.prova_dado(ID + 1, 1, "2026-11-09", 30)
    assert await repo.azzera(ID, "dado") == 1
    assert await repo.classifica(ID, "spinner", "2026-W46") == [(1, 4)]
    assert await repo.azzera(ID, None) == 1
    assert await repo.classifica(ID + 1, "dado", "2026-11-09") == [(1, 30)]


# --- comandi --------------------------------------------------------------

def _it(user_id=11):
    it = fake_interaction(guild=fake_guild(ID))
    it.user.id = user_id
    return it


async def test_comando_dado_tira_una_volta_e_mostra_classifica():
    cog = ge.GiochiExtraCog(bot=None)
    it = _it()
    await cog.dado.callback(cog, it, None)
    primo = it.response.send_message.await_args
    assert "<@11>" in primo.kwargs["embed"].description
    it2 = _it()
    await cog.dado.callback(cog, it2, _C("sempre"))
    assert len(await repo.classifica(ID, "dado", g.periodo_giorno())) == 1
    assert it2.response.send_message.await_args.kwargs["embed"].title


async def test_comando_mazzo_azioni():
    cog = ge.GiochiExtraCog(bot=None)
    it = _it()
    await cog.mazzo.callback(cog, it, None, 3)
    assert it.response.send_message.await_args.args[0].count("`") == 6
    it = _it()
    await cog.mazzo.callback(cog, it, _C("restanti"), 1)
    assert "49" in it.response.send_message.await_args.args[0]
    it = _it()
    await cog.mazzo.callback(cog, it, _C("rimescola"), 1)
    assert await repo.carte_restanti(ID) == 52


async def test_spinner_bottone_doppio_clic_e_cooldown(monkeypatch):
    monkeypatch.setattr(ge, "SECONDI_FRA_MODIFICHE", 1)
    monkeypatch.setattr(ge.gare, "durata_spinner", lambda rng: 2)
    sleep = AsyncMock()
    monkeypatch.setattr(ge.asyncio, "sleep", sleep)
    vista = ge.VistaSpinner(11, ID, random.Random(1), "Gira")
    it = _it(11)
    it.edit_original_response = AsyncMock()
    await vista.gira.callback(it)
    await vista.gira.callback(it)  # secondo clic: ignorato
    assert it.response.edit_message.await_count == 1
    assert it.edit_original_response.await_args.kwargs["content"].count("<@11>") == 1
    # un altro messaggio dello stesso utente entro un'ora: rifiutato
    vista2 = ge.VistaSpinner(11, ID, random.Random(1), "Gira")
    it2 = _it(11)
    await vista2.gira.callback(it2)
    assert "ora" in it2.response.edit_message.await_args.kwargs["content"]
    assert len(vista.children) == 1 and vista.gira.label == "Gira"


async def test_spinner_solo_chi_gioca():
    vista = ge.VistaSpinner(11, ID, random.Random(1), "Gira")
    it = _it(99)
    assert await vista.interaction_check(it) is False
    assert it.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_azzera_conferma_annulla_e_livello():
    await repo.prova_dado(ID, 1, "2026-11-09", 30)
    v = ge.ConfermaAzzera(11, ID, "dado")
    it = _it(11)
    await v.annulla.callback(it)
    await v.conferma.callback(it)  # dopo l'annulla non fa nulla
    assert len(await repo.classifica(ID, "dado", "2026-11-09")) == 1
    v = ge.ConfermaAzzera(11, ID, "dado")
    with patch.object(ge, "puo_usare", AsyncMock(return_value=False)):
        await v.conferma.callback(_it(11))
    assert len(await repo.classifica(ID, "dado", "2026-11-09")) == 1
    v = ge.ConfermaAzzera(11, ID, "dado")
    with patch.object(ge, "puo_usare", AsyncMock(return_value=True)):
        await v.conferma.callback(_it(11))
        await v.conferma.callback(_it(11))
    assert await repo.classifica(ID, "dado", "2026-11-09") == []


async def test_albero_giochi_e_admin_giochi():
    from discord.ext import commands

    from core.command_groups import GRUPPI
    from tests.support.percorsi import percorsi_del_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await ge.setup(bot)
    assert {"dado", "spinner", "mazzo", "minato"} <= percorsi_del_gruppo("giochi")
    assert "punteggi azzera" in percorsi_del_gruppo("admin-giochi")
    assert len(GRUPPI["giochi"].commands) <= 25
