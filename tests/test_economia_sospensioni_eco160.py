"""
tests/test_economia_sospensioni_eco160.py
=========================================
ECO-160 (D121): sospensione dal gioco con richiesta di revisione. La decide lo staff del server; la revisione arriva
allo staff, non all'owner del bot. Database vero.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import economia_sospensioni as es
from core.database import db

G, U, STAFF = 970001, 980001, 990001


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    yield


async def test_sospensione_attiva_e_poi_riabilitata():
    assert await es.attiva(G, U) is None
    await es.sospendi(G, U, "abuso", None, STAFF)
    s = await es.attiva(G, U)
    assert s is not None and s["motivo"] == "abuso"
    assert await es.attiva(G + 1, U) is None  # un altro server non c'entra
    assert await es.riabilita(G, U) is True
    assert await es.attiva(G, U) is None
    assert await es.riabilita(G, U) is False


async def test_a_tempo_scade_da_sola():
    await es.sospendi(G, U, "pausa", timedelta(hours=2), STAFF)
    assert await es.attiva(G, U) is not None
    await db.pool.execute("UPDATE economia_sospensioni SET fino_a = now() - interval '1 minute'")
    assert await es.attiva(G, U) is None


async def test_il_motivo_si_taglia_e_la_durata_ha_un_tetto():
    await es.sospendi(G, U, "x" * 900, timedelta(days=9999), STAFF)
    s = await es.attiva(G, U)
    assert len(s["motivo"]) == es.MAX_MOTIVO
    assert s["fino_a"] <= datetime.now(timezone.utc) + es.MAX_DURATA + timedelta(minutes=1)


async def test_l_appello_si_apre_una_volta_sola_e_serve_la_sospensione():
    assert await es.apri_appello(G, U, "ho sbagliato") is False  # non sospeso
    await es.sospendi(G, U, "abuso", None, STAFF)
    assert await es.apri_appello(G, U, "  non lo faccio più  ") is True
    assert await es.apri_appello(G, U, "ancora") is False  # una sola richiesta
    s = await es.attiva(G, U)
    assert s["appello"] == "non lo faccio più" and s["appello_stato"] == "aperto"


async def test_accogliere_toglie_la_sospensione_respingere_la_chiude():
    await es.sospendi(G, U, "abuso", None, STAFF)
    await es.apri_appello(G, U, "scusa")
    assert await es.decidi(G, U, accogli=False, da=STAFF) is True
    assert (await es.attiva(G, U))["appello_stato"] == "respinto"
    assert await es.apri_appello(G, U, "riprovo") is False  # respinto: non si riapre
    assert await es.decidi(G, U, accogli=True, da=STAFF) is False  # già decisa: lo staff può sempre `riabilita`
    await es.sospendi(G, U, "di nuovo", None, STAFF)  # una sospensione nuova riparte da capo
    await es.apri_appello(G, U, "scusa")
    assert await es.decidi(G, U, accogli=True, da=STAFF) is True
    assert await es.attiva(G, U) is None


async def test_decidere_senza_richiesta_aperta_non_fa_niente():
    await es.sospendi(G, U, "abuso", None, STAFF)
    assert await es.decidi(G, U, accogli=True, da=STAFF) is False
    assert await es.attiva(G, U) is not None


async def test_elenco_con_tetto():
    for i in range(30):
        await es.sospendi(G, 5000 + i, "m", None, STAFF)
    assert len(await es.elenco(G)) == 25


def test_solo_i_comandi_di_gioco_sono_fermati():
    assert es.e_di_gioco("monete work") and es.e_di_gioco("giochi quiz avvia") and es.e_di_gioco("clan info")
    assert not es.e_di_gioco("level rank") and not es.e_di_gioco("admin-giochi sospensione") and not es.e_di_gioco("ticket aperti")


# ---- il controllo comune e il comando ----
from unittest.mock import AsyncMock, MagicMock

import discord

from core.economia_sospensioni_view import rifiuta_se_sospeso
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


def _inter(percorso: str, user_id: int = U):
    inter = fake_interaction(guild=fake_guild(G), user=fake_member(user_id))
    inter.command = MagicMock()
    inter.command.qualified_name = percorso
    return inter


async def test_un_sospeso_e_fermato_sui_comandi_di_gioco_con_il_bottone():
    await es.sospendi(G, U, "abuso", None, STAFF)
    inter = _inter("monete work")
    assert await rifiuta_se_sospeso(inter) is True
    kw = inter.response.send_message.await_args.kwargs
    assert kw["ephemeral"] is True and len(kw["view"].children) == 1  # il bottone della revisione


async def test_un_comando_che_non_e_di_gioco_passa_e_chi_non_e_sospeso_pure():
    await es.sospendi(G, U, "abuso", None, STAFF)
    assert await rifiuta_se_sospeso(_inter("level rank")) is False
    assert await rifiuta_se_sospeso(_inter("monete work", user_id=U + 1)) is False


async def test_dopo_la_richiesta_il_bottone_non_c_e_piu():
    await es.sospendi(G, U, "abuso", None, STAFF)
    await es.apri_appello(G, U, "scusate")
    inter = _inter("giochi quiz avvia")
    assert await rifiuta_se_sospeso(inter) is True
    assert len(inter.response.send_message.await_args.kwargs["view"].children) == 0


async def test_il_modulo_di_revisione_manda_la_richiesta_allo_staff(monkeypatch):
    from core import economia_sospensioni_view as v

    await es.sospendi(G, U, "abuso", None, STAFF)
    inviati = []

    async def _log(guild, embed):
        inviati.append(embed)

    import cogs.moderation._shared as shared

    monkeypatch.setattr(shared, "post_to_mod_log", _log)
    modulo = v.ModuloRevisione()
    modulo.testo._value = "Ho capito, non succede più"
    inter = _inter("monete work")
    await modulo.on_submit(inter)
    assert len(inviati) == 1 and "non succede più" in inviati[0].description
    assert (await es.attiva(G, U))["appello_stato"] == "aperto"
    await modulo.on_submit(_inter("monete work"))  # la seconda volta non passa
    assert len(inviati) == 1
