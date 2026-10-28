"""
tests/test_progressi.py
=======================
Missioni, serie, traguardi, stagione e profilo globale (SPEC §23.17, D49). Logica pura,
tabelle vere, servizio, aggancio nel livellamento e comandi.
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.leveling.progressi as modulo
from core import progressi_service as servizio
from core.database import db
from core.progressi_logic import testo_profilo_globale as scrivi_profilo
from core.progressi_logic import testo_stagione as scrivi_stagione
from core.progressi_logic import testo_traguardi as scrivi_traguardi
from core.progressi_logic import (
    EVENTO_DAILY,
    EVENTO_MESSAGGI,
    EVENTO_VOCALE,
    MISSIONI,
    STAGIONE_GRADINI,
    ProfiloGlobale,
    Statistiche,
    aggiorna_serie,
    bonus_serie,
    gradini_raggiunti,
    premio_gradini,
    serie_attuale,
    stato_missione,
    traguardi_raggiunti,
)
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.progressi_repo import ProgressiRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

SERVER = 700
A = 111111111111111111
OGGI = date(2026, 10, 28)


# ------------------------------------------------------------------ logica pura
def test_la_serie_sale_resta_o_riparte():
    assert aggiorna_serie(0, 0, None, OGGI) == (1, 1, OGGI)
    assert aggiorna_serie(3, 3, OGGI - timedelta(days=1), OGGI) == (4, 4, OGGI)
    assert aggiorna_serie(3, 9, OGGI, OGGI) == (3, 9, OGGI)  # già riscossa oggi
    assert aggiorna_serie(5, 9, OGGI - timedelta(days=2), OGGI) == (1, 9, OGGI)  # buco: riparte, il record resta


def test_la_serie_finita_non_si_vede_piu():
    assert serie_attuale(5, OGGI - timedelta(days=1), OGGI) == 5
    assert serie_attuale(5, OGGI, OGGI) == 5
    assert serie_attuale(5, OGGI - timedelta(days=2), OGGI) == 0
    assert serie_attuale(0, None, OGGI) == 0


def test_il_bonus_arriva_ogni_sette_giorni_con_un_tetto():
    assert [bonus_serie(n) for n in (0, 1, 6, 7, 8, 14)] == [0, 0, 0, 35, 0, 70]
    assert bonus_serie(70) == 200


def test_una_missione_non_supera_l_obiettivo_e_dice_se_c_e_un_premio():
    m = MISSIONI[0]
    assert stato_missione(m, 3, False).startswith("⬜")
    assert stato_missione(m, 999, False).startswith("🎁") and f"({m.obiettivo}/{m.obiettivo}" in stato_missione(m, 999, False)
    assert stato_missione(m, m.obiettivo, True).startswith("✅")


def test_traguardi_dalle_statistiche():
    assert traguardi_raggiunti(Statistiche()) == set()
    tutti = traguardi_raggiunti(Statistiche(livello=50, record_serie=30, missioni_completate=100, stagioni_complete=1))
    assert {"livello_5", "livello_50", "serie_30", "missioni_100", "stagione_completa"} <= tutti
    assert "livello_25" in traguardi_raggiunti(Statistiche(livello=25))
    assert "▫️" in scrivi_traguardi({"livello_5"}) and "🌱" in scrivi_traguardi({"livello_5"})


def test_stagione_gradini_e_premi():
    assert gradini_raggiunti(0) == 0 and gradini_raggiunti(1499) == 0 and gradini_raggiunti(1500) == 1
    assert gradini_raggiunti(10**9) == STAGIONE_GRADINI
    assert premio_gradini(0, 3) == 40 + 80 + 120
    assert premio_gradini(3, 3) == 0
    testo = scrivi_stagione(1600, 0, "2026-10")
    assert "🎁 Gradino 1" in testo and "⬜ Gradino 2" in testo and "mancano" in testo


def test_il_profilo_globale_ha_solo_numeri_e_niente_nomi():
    testo = scrivi_profilo(ProfiloGlobale(server=3, livello_massimo=12, record_serie=9, traguardi=4))
    assert "**3**" in testo and "**12**" in testo and "**9**" in testo and "**4**" in testo


# ------------------------------------------------------------------ tabelle
@pytest.fixture
def repo(clean_db):
    return ProgressiRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_missioni_il_progresso_si_ferma_all_obiettivo_e_il_premio_esce_una_volta(repo, clean_db):
    guadagni = LevelingRepository(pool_provider=lambda: clean_db)
    m = MISSIONI[0]
    await repo.aggiungi_progressi([(SERVER, A, OGGI, m.chiave, 10, m.obiettivo)])
    await repo.aggiungi_progressi([(SERVER, A, OGGI, m.chiave, 99, m.obiettivo)])
    assert (await repo.missioni_di(SERVER, A, OGGI))[m.chiave] == (m.obiettivo, False)

    elenco = [(x.chiave, x.obiettivo, x.premio) for x in MISSIONI]
    assert await repo.riscatta_missioni(SERVER, A, OGGI, elenco) == (m.premio, 1)
    assert await repo.riscatta_missioni(SERVER, A, OGGI, elenco) == (0, 0)  # niente doppio premio
    assert await repo.missioni_completate(SERVER, A) == 1
    assert (await guadagni.get_totals(SERVER, A)).coins_total == m.premio


@pytest.mark.asyncio
async def test_missione_non_finita_non_si_paga(repo):
    m = MISSIONI[0]
    await repo.aggiungi_progressi([(SERVER, A, OGGI, m.chiave, m.obiettivo - 1, m.obiettivo)])
    assert await repo.riscatta_missioni(SERVER, A, OGGI, [(m.chiave, m.obiettivo, m.premio)]) == (0, 0)


@pytest.mark.asyncio
async def test_serie_nel_database(repo):
    assert await repo.registra_riscossione(SERVER, A, OGGI - timedelta(days=1)) == (1, 1, True)
    assert await repo.registra_riscossione(SERVER, A, OGGI) == (2, 2, True)
    assert await repo.registra_riscossione(SERVER, A, OGGI) == (2, 2, False)  # stesso giorno
    assert await repo.serie_di(SERVER, A) == (2, 2, OGGI)
    assert await repo.serie_di(SERVER, A + 1) == (0, 0, None)


@pytest.mark.asyncio
async def test_traguardi_nuovi_si_dicono_una_volta(repo):
    assert await repo.segna_traguardi(SERVER, A, ["livello_5", "serie_7"]) == ["livello_5", "serie_7"]
    assert await repo.segna_traguardi(SERVER, A, ["livello_5", "livello_10"]) == ["livello_10"]
    assert await repo.traguardi_di(SERVER, A) == {"livello_5", "serie_7", "livello_10"}


@pytest.mark.asyncio
async def test_stagione_i_gradini_si_pagano_una_volta(repo, clean_db):
    guadagni = LevelingRepository(pool_provider=lambda: clean_db)
    assert await repo.riscatta_gradini(SERVER, A, "2026-10", 0, premio_gradini) is None
    assert await repo.riscatta_gradini(SERVER, A, "2026-10", 2, premio_gradini) == (2, 40 + 80)
    assert await repo.riscatta_gradini(SERVER, A, "2026-10", 2, premio_gradini) is None
    assert await repo.riscatta_gradini(SERVER, A, "2026-10", 3, premio_gradini) == (1, 120)
    assert await repo.gradini_riscattati(SERVER, A, "2026-10") == 3
    assert await repo.gradini_riscattati(SERVER, A, "2026-09") == 0
    assert (await guadagni.get_totals(SERVER, A)).coins_total == 240
    assert await repo.stagioni_complete(SERVER, A) == 0
    await repo.riscatta_gradini(SERVER, A, "2026-10", STAGIONE_GRADINI, premio_gradini)
    assert await repo.stagioni_complete(SERVER, A) == 1


@pytest.mark.asyncio
async def test_profilo_globale_conta_server_livelli_serie_e_traguardi(repo, clean_db):
    clean_db_exec = clean_db.execute
    await clean_db_exec(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total, level) VALUES ($1, $2, 500, 4), ($3, $2, 900, 9), ($4, $2, 0, 0)",
        SERVER, A, SERVER + 1, SERVER + 2,
    )
    await repo.registra_riscossione(SERVER, A, OGGI)
    await repo.segna_traguardi(SERVER, A, ["livello_5"])
    await repo.segna_traguardi(SERVER + 1, A, ["livello_5", "livello_10"])
    assert await repo.profilo_globale(A) == (2, 9, 1, 2)  # il server con 0 XP non conta
    assert await repo.profilo_globale(A + 1) == (0, 0, 0, 0)


# ------------------------------------------------------------------ servizio
@pytest.fixture
def mondo(repo, monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._settings_cache.clear()
    monkeypatch.setattr(servizio, "progressi_repo", repo)
    monkeypatch.setattr(servizio, "_oggi", lambda: OGGI)
    servizio._pendenti.clear()
    yield
    servizio._pendenti.clear()
    database_module.db._settings_cache.clear()


@pytest.mark.asyncio
async def test_spento_di_base_non_si_conta_niente(mondo):
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)
    assert servizio._pendenti == {}
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")
    assert await servizio.progressi_repo.serie_di(SERVER, A) == (0, 0, None)


@pytest.mark.asyncio
async def test_acceso_gli_eventi_si_contano_e_si_scrivono(mondo):
    await servizio.imposta_attivo(SERVER, True, A)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)
    await servizio.registra_molti(SERVER, [A, A + 1], EVENTO_VOCALE, 2)
    await servizio.registra(SERVER, A, "evento-sconosciuto")
    assert servizio._pendenti == {(SERVER, A, EVENTO_MESSAGGI): 1, (SERVER, A, EVENTO_VOCALE): 2, (SERVER, A + 1, EVENTO_VOCALE): 2}
    await servizio.svuota(SERVER, A)  # solo quelli di A
    assert list(servizio._pendenti) == [(SERVER, A + 1, EVENTO_VOCALE)]
    assert (await servizio.progressi_repo.missioni_di(SERVER, A, OGGI))[EVENTO_MESSAGGI][0] == 1
    await servizio.svuota()
    assert servizio._pendenti == {}


@pytest.mark.asyncio
async def test_il_tetto_di_memoria_scarta_le_voci_nuove(mondo, monkeypatch):
    await servizio.imposta_attivo(SERVER, True)
    monkeypatch.setattr(servizio, "MAX_PENDENTI", 1)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)
    await servizio.registra(SERVER, A + 1, EVENTO_MESSAGGI)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)  # la voce c'è già: sale
    assert servizio._pendenti == {(SERVER, A, EVENTO_MESSAGGI): 2}


@pytest.mark.asyncio
async def test_riscossione_giornaliera_serie_missione_e_bonus(mondo, monkeypatch, repo, clean_db):
    await servizio.imposta_attivo(SERVER, True)
    guadagni = LevelingRepository(pool_provider=lambda: clean_db)
    import core.repositories.leveling_repo as lr

    monkeypatch.setattr(lr, "leveling_repo", guadagni)
    # sei giorni già fatti: oggi è il settimo, arriva il bonus (7 * 5 = 35)
    await repo.registra_riscossione(SERVER, A, OGGI - timedelta(days=1))
    await clean_db.execute("UPDATE progress_serie SET serie = 6, record = 6 WHERE guild_id = $1 AND user_id = $2", SERVER, A)

    await servizio.dopo_riscossione(SERVER, A, "last_work_at")  # il lavoro non conta
    assert (await repo.serie_di(SERVER, A))[0] == 6
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")
    assert (await repo.serie_di(SERVER, A))[:2] == (7, 7)
    assert (await guadagni.get_totals(SERVER, A)).coins_total == 35
    assert servizio._pendenti[(SERVER, A, EVENTO_DAILY)] == 1
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")  # stesso giorno: niente secondo bonus
    assert (await guadagni.get_totals(SERVER, A)).coins_total == 35


@pytest.mark.asyncio
async def test_riscatto_delle_missioni_scrive_prima_gli_eventi_in_attesa(mondo, repo, clean_db):
    await servizio.imposta_attivo(SERVER, True)
    daily = next(m for m in MISSIONI if m.chiave == EVENTO_DAILY)
    await servizio.registra(SERVER, A, EVENTO_DAILY)  # ancora in memoria
    esito = await servizio.riscatta_missioni(SERVER, A)
    assert (esito.monete, esito.quanti) == (daily.premio, 1)
    assert await servizio.riscatta_missioni(SERVER, A) == servizio.EsitoRiscatto(0, 0)


@pytest.mark.asyncio
async def test_riscatto_della_stagione_e_traguardo_a_dieci_gradini(mondo, repo, clean_db):
    from core.leveling_logic import period_key

    await servizio.imposta_attivo(SERVER, True)
    await clean_db.execute(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total, level) VALUES ($1, $2, 20000, 12)", SERVER, A
    )
    await clean_db.execute(
        "INSERT INTO leveling_activity (guild_id, user_id, period_key, xp) VALUES ($1, $2, $3, 3100)",
        SERVER, A, period_key(),
    )
    esito = await servizio.riscatta_stagione(SERVER, A)
    assert (esito.quanti, esito.monete) == (2, 40 + 80)
    assert await repo.traguardi_di(SERVER, A) == set()  # i traguardi si valutano a stagione finita
    assert (await servizio.riscatta_stagione(SERVER, A)).quanti == 0
    await clean_db.execute("UPDATE leveling_activity SET xp = 99999 WHERE guild_id = $1 AND user_id = $2", SERVER, A)
    finale = await servizio.riscatta_stagione(SERVER, A)
    assert finale.quanti == STAGIONE_GRADINI - 2
    assert "stagione_completa" in finale.traguardi_nuovi and "livello_10" in await repo.traguardi_di(SERVER, A)


# ------------------------------------------------------------------ aggancio nel livellamento
@pytest.mark.asyncio
async def test_il_livellamento_conta_messaggi_vocale_e_riscossione(mondo, clean_db, monkeypatch):
    await servizio.imposta_attivo(SERVER, True)
    guadagni = LevelingRepository(pool_provider=lambda: clean_db)
    await guadagni.add_text_xp(SERVER, A)
    assert servizio._pendenti[(SERVER, A, EVENTO_MESSAGGI)] == 1
    await guadagni.add_text_xp(SERVER, A)  # pausa tra due messaggi: niente XP, niente conteggio
    assert servizio._pendenti[(SERVER, A, EVENTO_MESSAGGI)] == 1

    await guadagni.add_voice_minutes(SERVER, [(A, 5, True), (A + 1, 5, False)])
    assert servizio._pendenti.get((SERVER, A, EVENTO_VOCALE)) == 1
    assert (SERVER, A + 1, EVENTO_VOCALE) not in servizio._pendenti

    import core.repositories.leveling_repo as lr

    monkeypatch.setattr(lr, "leveling_repo", guadagni)
    import datetime as dt

    adesso = dt.datetime.now(dt.timezone.utc)
    assert await guadagni.claim_daily(SERVER, A, 10, 86400, adesso) is True
    assert servizio._pendenti[(SERVER, A, EVENTO_DAILY)] == 1


@pytest.mark.asyncio
async def test_con_i_progressi_spenti_il_livellamento_resta_com_e(mondo, clean_db):
    guadagni = LevelingRepository(pool_provider=lambda: clean_db)
    assert (await guadagni.add_text_xp(SERVER, A)).granted is True
    assert servizio._pendenti == {}


# ------------------------------------------------------------------ comandi
def _scena(monkeypatch, attivo=True):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    monkeypatch.setattr(servizio, "attivo", AsyncMock(return_value=attivo))
    server = fake_guild(SERVER)
    i = fake_interaction(guild=server, user=fake_member(A))
    return modulo.ProgressiCog(MagicMock()), i


def _scelta(valore):
    return discord.app_commands.Choice(name=valore, value=valore)


@pytest.mark.asyncio
async def test_spenti_il_comando_lo_dice_ma_il_profilo_globale_si_vede(mondo, monkeypatch, repo):
    cog, i = _scena(monkeypatch, attivo=False)
    await cog.progressi.callback(cog, i, _scelta("missioni"))
    assert "/economia progressi" in i.response.send_message.await_args.args[0]

    i2 = fake_interaction(guild=fake_guild(SERVER), user=fake_member(A))
    await cog.progressi.callback(cog, i2, _scelta("globale"))
    embed = i2.response.send_message.await_args.kwargs["embed"]
    assert "Server in cui giochi" in embed.description and i2.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("sezione", ["missioni", "traguardi", "serie", "stagione"])
async def test_ogni_sezione_risponde_con_un_embed_privato(mondo, monkeypatch, repo, sezione):
    cog, i = _scena(monkeypatch)
    await cog.progressi.callback(cog, i, _scelta(sezione))
    argomenti = i.response.send_message.await_args.kwargs
    assert argomenti["ephemeral"] is True and argomenti["embed"].description
    assert len(argomenti["embed"].description) <= 4000


@pytest.mark.asyncio
async def test_il_bottone_riscuoti_paga_e_lo_preme_solo_chi_ha_aperto(mondo, monkeypatch, repo, clean_db):
    monkeypatch.setattr(servizio, "attivo", AsyncMock(return_value=True))
    daily = next(m for m in MISSIONI if m.chiave == EVENTO_DAILY)
    await repo.aggiungi_progressi([(SERVER, A, OGGI, daily.chiave, 1, daily.obiettivo)])
    vista = modulo.VistaRiscatto(A, "missioni")

    altro = fake_interaction(guild=fake_guild(SERVER), user=fake_member(A + 5))
    assert await vista.interaction_check(altro) is False

    i = fake_interaction(guild=fake_guild(SERVER), user=fake_member(A))
    await vista.riscuoti.callback(i)
    assert f"**{daily.premio}**" in i.response.send_message.await_args.args[0]
    i2 = fake_interaction(guild=fake_guild(SERVER), user=fake_member(A))
    await vista.riscuoti.callback(i2)
    assert "niente da riscuotere" in i2.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_il_comando_dello_staff_accende_e_spegne(mondo, monkeypatch):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    cog = modulo.ProgressiCog(MagicMock())
    i = fake_interaction(guild=fake_guild(SERVER), user=fake_member(A))
    await cog.progressi_staff.callback(cog, i, True)
    assert await servizio.attivo(SERVER) is True and "accesi" in i.response.send_message.await_args.args[0]
    i2 = fake_interaction(guild=fake_guild(SERVER), user=fake_member(A))
    await cog.progressi_staff.callback(cog, i2, False)
    assert await servizio.attivo(SERVER) is False and "spenti" in i2.response.send_message.await_args.args[0]
