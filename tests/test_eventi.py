"""
tests/test_eventi.py
====================
D69 B24 (UTL-113): lettura della data, posti e lista d'attesa senza corse, promemoria, modifica e annullo.
Archivio su PostgreSQL vero.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from core import eventi_logic as L
from core.repositories.eventi_repo import EventiRepository

G = 31
ADESSO = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
ROMA = ZoneInfo("Europe/Rome")


def test_quando_data_o_durata():
    assert L.leggi_quando("24/12/2026 21:00", ADESSO, ROMA) == datetime(2026, 12, 24, 20, 0, tzinfo=timezone.utc)
    assert L.leggi_quando("2026-12-24  21:00", ADESSO, ROMA) == datetime(2026, 12, 24, 20, 0, tzinfo=timezone.utc)
    assert L.leggi_quando("3d", ADESSO, ROMA) == ADESSO + timedelta(days=3)
    assert L.leggi_quando("ieri sera", ADESSO, ROMA) == "formato"
    assert L.leggi_quando("30s", ADESSO, ROMA) == "passato"
    assert L.leggi_quando("01/01/2026 10:00", ADESSO, ROMA) == "passato"
    assert L.leggi_quando("01/01/2030 10:00", ADESSO, ROMA) == "lontano"


def test_promemoria_solo_se_l_evento_non_e_vicino():
    assert L.promemoria_a(ADESSO + timedelta(hours=1), ADESSO) == ADESSO + timedelta(minutes=45)
    assert L.promemoria_a(ADESSO + timedelta(minutes=10), ADESSO) is None
    assert L.testo_posti(3, 10) == "3/10" and L.testo_posti(3, None) == "3"
    assert L.pagine(0) == 1 and L.pagine(15) == 1 and L.pagine(16) == 2


@pytest.fixture
def repo(clean_db):
    return EventiRepository(pool_provider=lambda: clean_db)


async def _evento(repo, posti=2, quando=None):
    return await repo.crea(G, 5, 99, "Serata", "gioco", quando or ADESSO + timedelta(days=1), posti, None)


@pytest.mark.asyncio
async def test_posti_finiti_lista_d_attesa_e_promozione(repo):
    e = await _evento(repo)
    assert (await repo.iscriviti(e, 1, "si", ADESSO))[:2] == ("ok", "si")
    assert (await repo.iscriviti(e, 2, "si", ADESSO))[:2] == ("ok", "si")
    assert (await repo.iscriviti(e, 3, "si", ADESSO))[:2] == ("ok", "attesa")
    assert (await repo.iscriviti(e, 4, "si", ADESSO))[:2] == ("ok", "attesa")
    assert (await repo.iscriviti(e, 3, "si", ADESSO))[0] == "uguale"
    assert await repo.conteggi(e) == {"si": 2, "forse": 0, "attesa": 2}
    # chi esce libera un posto: passa il primo arrivato in attesa
    assert await repo.iscriviti(e, 1, "esco", ADESSO) == ("ok", None, [3])
    # chi passa a «forse» libera un posto
    assert (await repo.iscriviti(e, 2, "forse", ADESSO))[2] == [4]
    assert await repo.conteggi(e) == {"si": 2, "forse": 1, "attesa": 0}
    assert (await repo.iscriviti(e, 9, "esco", ADESSO))[0] == "niente"
    assert await repo.iscritti(e, "si", 10) == [3, 4]


@pytest.mark.asyncio
async def test_clic_insieme_non_superano_i_posti(repo):
    e = await _evento(repo, posti=3)
    await asyncio.gather(*[repo.iscriviti(e, u, "si", ADESSO) for u in range(1, 13)])
    assert await repo.conteggi(e) == {"si": 3, "forse": 0, "attesa": 9}


@pytest.mark.asyncio
async def test_senza_limite_nessuna_attesa_e_dopo_l_ora_chiuso(repo):
    e = await _evento(repo, posti=None)
    for u in range(1, 8):
        assert (await repo.iscriviti(e, u, "si", ADESSO))[1] == "si"
    assert (await repo.iscriviti(e, 1, "si", ADESSO + timedelta(days=2)))[0] == "chiuso"


@pytest.mark.asyncio
async def test_modifica_posti_fa_scorrere_l_attesa(repo):
    e = await _evento(repo, posti=1)
    for u in (1, 2, 3):
        await repo.iscriviti(e, u, "si", ADESSO)
    assert await repo.modifica(e, posti=3) == [2, 3]
    assert await repo.modifica(e, posti=1) == []  # meno posti: chi c'è resta
    assert await repo.conteggi(e) == {"si": 3, "forse": 0, "attesa": 0}
    await repo.iscriviti(e, 4, "si", ADESSO)
    assert await repo.modifica(e, titolo="Nuovo", togli_posti=True) == [4]
    assert (await repo.prendi(e))["titolo"] == "Nuovo" and (await repo.prendi(e))["posti"] is None


@pytest.mark.asyncio
async def test_annulla_una_volta_e_poi_nessuna_iscrizione(repo):
    e = await _evento(repo)
    assert sorted(await asyncio.gather(repo.annulla(e), repo.annulla(e))) == [False, True]
    assert (await repo.iscriviti(e, 1, "si", ADESSO))[0] == "chiuso"
    assert await repo.modifica(e, titolo="x") is None
    assert await repo.elenco(G, ADESSO) == []


@pytest.mark.asyncio
async def test_elenco_cerca_e_canale_cancellato(repo):
    a = await _evento(repo)
    b = await repo.crea(G, 6, 98, "Torneo", "", ADESSO + timedelta(hours=3), None, None)
    assert [r["id"] for r in await repo.elenco(G, ADESSO)] == [b, a]
    assert [r["id"] for r in await repo.elenco(G, ADESSO, autore_id=99)] == [a]
    assert [r["id"] for r in await repo.cerca(G, "torn", ADESSO)] == [b]
    assert await repo.cerca(G, "%", ADESSO) == []
    assert await repo.conta_aperti(G, 99, ADESSO) == 1
    await repo.iscriviti(a, 1, "si", ADESSO)
    assert await repo.elimina_del_canale(G, 5) == 1 and await repo.prendi(a) is None
    assert await repo.iscritti(a, "si", 10) == []


@pytest.fixture
def cog(repo, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from cogs.utility import eventi as M

    monkeypatch.setattr(M, "eventi_repo", repo)
    monkeypatch.setattr(M, "lingua_interazione", AsyncMock(return_value="it"))
    monkeypatch.setattr(M, "lingua_risposta", AsyncMock(return_value="it"))
    monkeypatch.setattr(M.scheduler, "schedule", AsyncMock())
    bot = MagicMock()
    c = M.EventiCog(bot)
    c.aggiorna_messaggio = AsyncMock()
    return c


def _clic(user_id=1, permessi=None):
    import discord

    from tests.support.discord_fakes import fake_interaction, fake_member

    i = fake_interaction(user=fake_member(user_id=user_id), permissions=permessi or discord.Permissions.none())
    i.guild.id = G
    return i


@pytest.mark.asyncio
async def test_bottoni_testi_e_avviso_a_chi_entra_dall_attesa(repo, cog):
    from unittest.mock import AsyncMock, MagicMock

    from cogs.utility import eventi as M

    e = await repo.crea(G, 5, 99, "Serata", "", datetime.now(timezone.utc) + timedelta(days=1), 1, None)
    canale = MagicMock(send=AsyncMock())
    cog.bot.get_channel.return_value = canale
    for u, atteso in ((1, "ev_iscritto_si"), (2, "ev_iscritto_attesa"), (2, "ev_gia_cosi")):
        i = _clic(u)
        await cog.scegli(i, e, "si")
        assert i.followup.send.await_args.args[0] == M.t(atteso, "it")
    i = _clic(1)
    await cog.scegli(i, e, "esco")
    assert i.followup.send.await_args.args[0] == M.t("ev_uscito", "it")
    assert "<@2>" in canale.send.await_args.args[0]
    i = _clic(7)
    await cog.scegli(i, e, "esco")
    assert i.followup.send.await_args.args[0] == M.t("ev_niente_da_togliere", "it")


@pytest.mark.asyncio
async def test_crea_serve_il_permesso_e_modifica_annulla_solo_autore_o_staff(repo, cog):
    import discord

    from cogs.utility import eventi as M

    i = _clic(5)
    await cog.crea.callback(cog, i, "Titolo", "3d")
    assert i.response.send_message.await_args.args[0] == M.t("ev_serve_permesso", "it")
    e = await repo.crea(G, 5, 99, "Serata", "", datetime.now(timezone.utc) + timedelta(days=1), None, None)
    i = _clic(5)
    await cog.annulla.callback(cog, i, str(e))
    assert i.response.send_message.await_args.args[0] == M.t("ev_non_si_puo", "it")
    assert (await repo.prendi(e))["stato"] == "attivo"
    i = _clic(5, discord.Permissions(manage_events=True))
    cog.bot.get_guild.return_value = None
    await cog.annulla.callback(cog, i, str(e))
    assert (await repo.prendi(e))["stato"] == "annullato"
    cog.aggiorna_messaggio.assert_awaited()


@pytest.mark.asyncio
async def test_promemoria_solo_se_data_invariata_e_chi_ha_detto_si(repo, cog):
    from unittest.mock import AsyncMock, MagicMock

    quando = datetime.now(timezone.utc) + timedelta(hours=1)
    e = await repo.crea(G, 5, 99, "Serata", "", quando, None, None)
    await repo.iscriviti(e, 1, "si", ADESSO)
    await repo.iscriviti(e, 2, "forse", ADESSO)
    canale = MagicMock(send=AsyncMock())
    cog.bot.get_channel.return_value = canale
    await cog.promemoria(G, 99, {"id": e, "quando": int(quando.timestamp()) + 600})  # data vecchia: spostato
    canale.send.assert_not_awaited()
    await cog.promemoria(G, 99, {"id": e, "quando": int(quando.timestamp())})
    testo = canale.send.await_args.args[0]
    assert "<@1>" in testo and "<@2>" not in testo
    await repo.annulla(e)
    canale.send.reset_mock()
    await cog.promemoria(G, 99, {"id": e, "quando": int(quando.timestamp())})
    canale.send.assert_not_awaited()
