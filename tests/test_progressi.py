"""
tests/test_progressi.py
=======================
Missioni (giorno, settimana, server), serie con protezione, traguardi nascosti, pass di 90 giorni e
profilo globale (SPEC §23.17, D49, D51). Logica pura, tabelle vere, servizio, aggancio nel
livellamento e finestra di /level progressi.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.leveling.progressi as modulo
from core import progressi_service as servizio
from core.profile_logic import PER_ID
from core.progressi_logic import (
    CATEGORIE,
    EVENTO_DAILY,
    EVENTO_MESSAGGI,
    EVENTO_VOCALE,
    MISSIONE_PER_CHIAVE,
    MISSIONI,
    MISSIONI_GIORNO,
    MISSIONI_SERVER,
    MISSIONI_SETTIMANA,
    PASS_LIVELLI,
    PASS_PREZZO_PREMIUM,
    PREMI_PASS_PREMIUM,
    PREMI_SERIE,
    SCUDI_MAX,
    SCUDO_PREZZO,
    TRAGUARDI,
    ProfiloGlobale,
    Statistiche,
    aggiorna_serie,
    giorno_del_periodo,
    livelli_raggiunti,
    lunedi_di,
    minimo_partecipazione,
    monete_livelli,
    obiettivo_server,
    oggetti_livelli,
    premi_serie_raggiunti,
    premio_livello,
    prossima_tappa,
    scade_tra_ore,
    serie_attuale,
    serve_promemoria,
    stagione_di,
    stato_missione,
    stato_missione_server,
    traguardi_raggiunti,
)
from core.progressi_logic import testo_pass as scrivi_pass
from core.progressi_logic import testo_promemoria as scrivi_promemoria
from core.progressi_logic import testo_profilo_globale as scrivi_profilo
from core.progressi_logic import testo_traguardi as scrivi_traguardi
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.profile_repo import ProfileRepository
from core.repositories.progressi_repo import ProgressiRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

SERVER = 700
A = 111111111111111111
B = 222222222222222222
ADESSO = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)  # un mercoledì
OGGI = ADESSO.date()
LUNEDI = date(2026, 10, 26)
ORE = timedelta(hours=1)


def _giorno(chiave):
    return next(m for m in MISSIONI if m.chiave == chiave)


# ------------------------------------------------------------------ logica pura: missioni
def test_il_lunedi_e_le_date_delle_missioni_della_settimana():
    assert lunedi_di(date(2026, 10, 28)) == LUNEDI and lunedi_di(LUNEDI) == LUNEDI
    assert lunedi_di(date(2026, 11, 1)) == LUNEDI  # la domenica è ancora la stessa settimana
    assert giorno_del_periodo(MISSIONI_GIORNO[0], OGGI) == OGGI
    assert giorno_del_periodo(MISSIONI_SETTIMANA[0], OGGI) == LUNEDI


def test_ogni_evento_ha_una_missione_del_giorno_e_una_della_settimana():
    for evento in (EVENTO_MESSAGGI, EVENTO_VOCALE, EVENTO_DAILY):
        assert {m.periodo for m in MISSIONI if m.evento == evento} == {"giorno", "settimana"}
    assert len({m.chiave for m in MISSIONI}) == len(MISSIONI)


def test_una_missione_non_supera_l_obiettivo_e_dice_se_c_e_un_premio():
    m = MISSIONI_GIORNO[0]
    assert stato_missione(m, 3, False).startswith("⬜")
    assert stato_missione(m, 999, False).startswith("🎁") and f"({m.obiettivo}/{m.obiettivo}" in stato_missione(m, 999, False)
    assert stato_missione(m, m.obiettivo, True).startswith("✅")


def test_la_missione_del_server_segue_l_obiettivo_e_chiede_di_aver_partecipato():
    ms = MISSIONI_SERVER[0]
    assert obiettivo_server(ms, 1000) == 1000 and obiettivo_server(MISSIONI_SERVER[1], 1000) == 600
    assert obiettivo_server(ms, 1) == 50  # mai sotto il minimo
    minimo = minimo_partecipazione(ms)
    assert minimo == MISSIONE_PER_CHIAVE[ms.personale].obiettivo // 10
    assert stato_missione_server(ms, 1000, 400, 50, False).startswith("⬜") and "400/1000" in stato_missione_server(ms, 1000, 400, 50, False)
    assert stato_missione_server(ms, 1000, 1000, minimo, False).startswith("🎁")
    fuori = stato_missione_server(ms, 1000, 1000, 0, False)
    assert fuori.startswith("⬜") and f"ti mancano {minimo}" in fuori
    assert stato_missione_server(ms, 1000, 1000, minimo, True).startswith("✅")


# ------------------------------------------------------------------ logica pura: serie
def test_la_serie_sale_entro_36_ore_resta_se_e_la_stessa_e_riparte_oltre():
    primo = aggiorna_serie(0, 0, None, 0, ADESSO)
    assert (primo.serie, primo.record, primo.contata) == (1, 1, True)
    assert aggiorna_serie(3, 3, ADESSO - 24 * ORE, 0, ADESSO).serie == 4
    assert aggiorna_serie(3, 3, ADESSO - 36 * ORE, 0, ADESSO).serie == 4  # il limite incluso
    stessa = aggiorna_serie(3, 9, ADESSO - 5 * ORE, 0, ADESSO)
    assert (stessa.serie, stessa.contata) == (3, False)
    buco = aggiorna_serie(5, 9, ADESSO - 37 * ORE, 0, ADESSO)
    assert (buco.serie, buco.record, buco.scudi_usati) == (1, 9, 0)  # riparte, il record resta


def test_lo_scudo_copre_un_giorno_saltato_e_si_consuma():
    coperto = aggiorna_serie(5, 5, ADESSO - 60 * ORE, 1, ADESSO)  # 60 h: un giorno saltato
    assert (coperto.serie, coperto.scudi, coperto.scudi_usati) == (6, 0, 1)
    due = aggiorna_serie(5, 5, ADESSO - 84 * ORE, 2, ADESSO)
    assert (due.serie, due.scudi, due.scudi_usati) == (6, 0, 2)
    scoperto = aggiorna_serie(5, 5, ADESSO - 84 * ORE, 1, ADESSO)  # servono due scudi, ce n'è uno
    assert (scoperto.serie, scoperto.scudi, scoperto.scudi_usati) == (1, 1, 0)  # lo scudo non si perde


def test_la_serie_finita_non_si_vede_piu_e_gli_scudi_allungano_il_tempo():
    assert serie_attuale(5, ADESSO - 30 * ORE, 0, ADESSO) == 5
    assert serie_attuale(5, ADESSO - 37 * ORE, 0, ADESSO) == 0
    assert serie_attuale(5, ADESSO - 37 * ORE, 1, ADESSO) == 5
    assert serie_attuale(0, None, 0, ADESSO) == 0
    assert scade_tra_ore(ADESSO - 30 * ORE, 0, ADESSO) == 6
    assert scade_tra_ore(ADESSO - 30 * ORE, 1, ADESSO) == 30
    assert scade_tra_ore(None, 0, ADESSO) is None


def test_il_promemoria_serve_tra_20_ore_e_la_perdita_della_serie():
    assert not serve_promemoria(5, ADESSO - 19 * ORE, 0, ADESSO)
    assert serve_promemoria(5, ADESSO - 20 * ORE, 0, ADESSO)
    assert serve_promemoria(5, ADESSO - 36 * ORE, 0, ADESSO)
    assert not serve_promemoria(5, ADESSO - 37 * ORE, 0, ADESSO)  # troppo tardi
    assert serve_promemoria(5, ADESSO - 50 * ORE, 1, ADESSO)  # lo scudo allunga
    assert not serve_promemoria(2, ADESSO - 25 * ORE, 0, ADESSO)  # serie troppo corta
    testo = scrivi_promemoria(5, ADESSO - 20 * ORE, 0, ADESSO, "Casa")
    assert "**5**" in testo and "Casa" in testo and "tra circa 4 ore" in testo and "azzera tra circa 16 ore" in testo
    assert "Puoi riscuotere adesso" in scrivi_promemoria(5, ADESSO - 30 * ORE, 0, ADESSO, "Casa")


def test_premi_estetici_a_7_14_30_60_100_giorni():
    assert sorted(PREMI_SERIE) == [7, 14, 30, 60, 100]
    assert premi_serie_raggiunti(6) == [] and premi_serie_raggiunti(14) == ["scintilla", "cometa"]
    assert len(premi_serie_raggiunti(100)) == 5
    assert prossima_tappa(0) == 7 and prossima_tappa(14) == 30 and prossima_tappa(100) is None
    assert all(PER_ID[o].premio and PER_ID[o].prezzo == 0 for o in PREMI_SERIE.values())  # non si comprano


# ------------------------------------------------------------------ logica pura: traguardi
def test_traguardi_dalle_statistiche():
    assert traguardi_raggiunti(Statistiche()) == set()
    tutti = traguardi_raggiunti(Statistiche(livello=50, record_serie=30, missioni_completate=100, stagioni_complete=1))
    assert {"livello_5", "livello_50", "serie_30", "missioni_100", "stagione_completa"} <= tutti
    assert "serie_100" not in tutti and "livello_25" in traguardi_raggiunti(Statistiche(livello=25))
    nascosti = traguardi_raggiunti(Statistiche(scudi_usati=1, missioni_settimana=3, missioni_server=1, pass_premium=1))
    assert nascosti == {"scudo_salvaserie", "settimana_piena", "squadra", "pass_premium"}


def test_i_traguardi_nascosti_si_vedono_solo_da_ottenuti_e_ci_sono_le_categorie():
    vuoto = scrivi_traguardi(set())
    assert "Segreti" not in vuoto and "Salvato dallo scudo" not in vuoto
    assert "4 traguardi nascosti da scoprire" in vuoto
    preso = scrivi_traguardi({"scudo_salvaserie"})
    assert "**Segreti**" in preso and "Salvato dallo scudo" in preso and "3 traguardi nascosti" in preso
    assert all(f"**{c}**" in preso for c in CATEGORIE if c != "Segreti")
    assert "▫️" in scrivi_traguardi({"livello_5"}) and "🌱" in scrivi_traguardi({"livello_5"})
    assert {t.categoria for t in TRAGUARDI if t.nascosto} == {"Segreti"}


# ------------------------------------------------------------------ logica pura: pass
def test_le_stagioni_durano_90_giorni_senza_buchi():
    chiave, inizio, fine = stagione_di(date(2026, 1, 1))
    assert (chiave, inizio, fine) == ("2026-01", date(2026, 1, 1), date(2026, 3, 31))
    assert (fine - inizio).days + 1 == 90
    assert stagione_di(date(2026, 4, 1))[1] == date(2026, 4, 1)
    chiave, inizio, fine = stagione_di(OGGI)
    assert inizio <= OGGI <= fine and (fine - inizio).days == 89
    assert stagione_di(fine + timedelta(days=1))[1] == fine + timedelta(days=1)
    assert len({stagione_di(date(2026, 1, 1) + timedelta(days=90 * n))[0] for n in range(12)}) == 12


def test_il_pass_ha_50_livelli_e_la_traccia_premium_vale_il_doppio():
    assert livelli_raggiunti(0) == 0 and livelli_raggiunti(499) == 0 and livelli_raggiunti(500) == 1
    assert livelli_raggiunti(10**9) == PASS_LIVELLI == 50
    assert premio_livello(1, False) == 12 and premio_livello(1, True) == 24
    assert monete_livelli(0, 3, False) == 12 + 14 + 16 and monete_livelli(3, 3, True) == 0
    assert monete_livelli(0, 50, True) > 2 * monete_livelli(0, 50, False) - 1000
    assert oggetti_livelli(0, 9) == [] and oggetti_livelli(9, 10) == ["sigillo"]
    assert oggetti_livelli(0, 50) == ["sigillo", "zenit", "trofeo"]
    assert oggetti_livelli(10, 50) == ["zenit", "trofeo"]  # il livello 10 era già riscosso
    assert all(PER_ID[o].premio for o in PREMI_PASS_PREMIUM.values())


def test_il_testo_del_pass_dice_cosa_manca_e_come_aprire_la_traccia_premium():
    spento = scrivi_pass(1200, 0, 0, False, date(2026, 12, 26), booster=False)
    assert "Livello 2/50" in spento and "2 da riscuotere" in spento and "26/12/2026" in spento
    assert f"{PASS_PREZZO_PREMIUM:,}" in spento and "non ce l'hai" in spento and "spenta" in spento
    assert "ce l'hai" in scrivi_pass(0, 0, 0, False, date(2026, 12, 26), booster=True)
    aperto = scrivi_pass(1200, 2, 0, True, date(2026, 12, 26))
    assert "Traccia premium: 0 livelli riscossi, 2 da riscuotere" in aperto and "spenta" not in aperto
    assert "mancano 300 XP" in aperto
    assert "mancano" not in scrivi_pass(10**6, 50, 50, True, date(2026, 12, 26))


def test_il_profilo_globale_ha_solo_numeri_e_niente_nomi():
    testo = scrivi_profilo(ProfiloGlobale(server=3, livello_massimo=12, record_serie=9, traguardi=4))
    assert "**3**" in testo and "**12**" in testo and "**9**" in testo and "**4**" in testo


# ------------------------------------------------------------------ tabelle
@pytest.fixture
def repo(clean_db):
    return ProgressiRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def guadagni(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


async def _monete(guadagni, utente=A):
    return (await guadagni.get_totals(SERVER, utente)).coins_total


@pytest.mark.asyncio
async def test_missioni_il_progresso_si_ferma_all_obiettivo_e_il_premio_esce_una_volta(repo, guadagni):
    m = MISSIONI_GIORNO[0]
    await repo.aggiungi_progressi([(SERVER, A, OGGI, m.chiave, 10, m.obiettivo)])
    await repo.aggiungi_progressi([(SERVER, A, OGGI, m.chiave, 99, m.obiettivo)])
    assert (await repo.missioni_di(SERVER, A, OGGI))[m.chiave] == (m.obiettivo, False)

    elenco = [(x.chiave, x.obiettivo, x.premio) for x in MISSIONI_GIORNO]
    assert await repo.riscatta_missioni(SERVER, A, OGGI, elenco) == (m.premio, 1)
    assert await repo.riscatta_missioni(SERVER, A, OGGI, elenco) == (0, 0)  # niente doppio premio
    assert await repo.missioni_completate(SERVER, A) == 1
    assert await _monete(guadagni) == m.premio


@pytest.mark.asyncio
async def test_missione_non_finita_non_si_paga(repo):
    m = MISSIONI_GIORNO[0]
    await repo.aggiungi_progressi([(SERVER, A, OGGI, m.chiave, m.obiettivo - 1, m.obiettivo)])
    assert await repo.riscatta_missioni(SERVER, A, OGGI, [(m.chiave, m.obiettivo, m.premio)]) == (0, 0)


@pytest.mark.asyncio
async def test_missioni_della_settimana_contate_dal_lunedi_e_riconosciute(repo):
    m = MISSIONI_SETTIMANA[2]  # riscossioni del daily
    await repo.aggiungi_progressi([(SERVER, A, LUNEDI, m.chiave, m.obiettivo, m.obiettivo)])
    assert await repo.riscatta_missioni(SERVER, A, LUNEDI, [(m.chiave, m.obiettivo, m.premio)]) == (m.premio, 1)
    assert await repo.missioni_settimana_riscattate(SERVER, A) == 1
    giorno = MISSIONI_GIORNO[0]
    await repo.aggiungi_progressi([(SERVER, A, OGGI, giorno.chiave, giorno.obiettivo, giorno.obiettivo)])
    await repo.riscatta_missioni(SERVER, A, OGGI, [(giorno.chiave, giorno.obiettivo, giorno.premio)])
    assert await repo.missioni_settimana_riscattate(SERVER, A) == 1  # quella del giorno non conta qui


@pytest.mark.asyncio
async def test_missione_del_server_totale_con_tetto_per_persona_e_premio_una_volta(repo, guadagni):
    ms = MISSIONI_SERVER[0]
    personale = MISSIONE_PER_CHIAVE[ms.personale]
    minimo = minimo_partecipazione(ms)
    # A fa il massimo, B appena il minimo, C troppo poco, un altro server non c'entra
    await repo.aggiungi_progressi([
        (SERVER, A, LUNEDI, personale.chiave, 5000, personale.obiettivo),
        (SERVER, B, LUNEDI, personale.chiave, minimo, personale.obiettivo),
        (SERVER, B + 1, LUNEDI, personale.chiave, minimo - 1, personale.obiettivo),
        (SERVER + 1, A, LUNEDI, personale.chiave, 100, personale.obiettivo),
    ])
    totale, quanti = await repo.totale_server(SERVER, LUNEDI, personale.chiave, minimo)
    assert totale == personale.obiettivo + minimo + minimo - 1  # A è tagliato al suo obiettivo
    assert quanti == 2

    def chiedi(utente, obiettivo):
        return repo.riscatta_server(SERVER, utente, LUNEDI, ms.chiave, personale.chiave, obiettivo, minimo, ms.premio)

    assert await chiedi(A, totale + 1) == 0  # obiettivo non raggiunto
    assert await chiedi(B + 1, totale) == 0  # il server c'è, ma lui non ha partecipato
    assert await chiedi(A, totale) == ms.premio
    assert await chiedi(A, totale) == 0  # una volta sola
    assert await chiedi(B, totale) == ms.premio
    assert await repo.server_riscattate(SERVER, A, LUNEDI) == {ms.chiave}
    assert await repo.server_riscattate(SERVER, A, LUNEDI - timedelta(days=7)) == set()
    assert await repo.missioni_server_riscattate(SERVER, A) == 1
    assert await _monete(guadagni) == ms.premio


@pytest.mark.asyncio
async def test_serie_nel_database_con_scudi_e_record(repo):
    assert await repo.serie_di(SERVER, A) == (0, 0, None, 0, False)
    uno = await repo.registra_riscossione(SERVER, A, ADESSO - 30 * ORE)
    assert (uno.serie, uno.contata) == (1, True)
    due = await repo.registra_riscossione(SERVER, A, ADESSO)
    assert (due.serie, due.record) == (2, 2)
    ripetuta = await repo.registra_riscossione(SERVER, A, ADESSO + 2 * ORE)
    assert (ripetuta.serie, ripetuta.contata) == (2, False)  # la stessa riscossione
    assert await repo.serie_di(SERVER, A) == (2, 2, ADESSO, 0, False)
    assert await repo.serie_di(SERVER, A + 1) == (0, 0, None, 0, False)


@pytest.mark.asyncio
async def test_le_serie_di_prima_della_regola_delle_36_ore_non_si_azzerano(repo, clean_db):
    """Righe scritte con la vecchia regola (solo `ultimo_giorno`): la migrazione 0484 dà loro l'ora."""
    from pathlib import Path

    ieri = OGGI - timedelta(days=1)
    await clean_db.execute(
        "INSERT INTO progress_serie (guild_id, user_id, serie, record, ultimo_giorno) VALUES ($1, $2, 9, 9, $3)",
        SERVER, A, ieri,
    )
    sql = (Path(__file__).parent.parent / "core/migrations/0484_serie_ora_di_prima.sql").read_text()
    await clean_db.execute(sql)
    assert serie_attuale(9, (await repo.serie_di(SERVER, A))[2], 0, ADESSO) == 9
    for ora in (0, 23):  # oggi a qualsiasi ora la serie sale, come con la regola di prima
        await clean_db.execute(
            "UPDATE progress_serie SET serie = 9, ultima_at = NULL, ultimo_giorno = $3 WHERE guild_id = $1 AND user_id = $2",
            SERVER, A, ieri,
        )
        await clean_db.execute(sql)
        esito = await repo.registra_riscossione(SERVER, A, datetime(2026, 10, 28, ora, 30, tzinfo=timezone.utc))
        assert (esito.serie, esito.contata) == (10, True)


@pytest.mark.asyncio
async def test_settimana_piena_vuole_tutte_le_missioni_della_stessa_settimana(repo):
    m = MISSIONI_SETTIMANA[0]
    for settimane in range(3):  # una missione a settimana, per tre settimane
        lunedi = LUNEDI - timedelta(days=7 * settimane)
        await repo.aggiungi_progressi([(SERVER, A, lunedi, m.chiave, m.obiettivo, m.obiettivo)])
        await repo.riscatta_missioni(SERVER, A, lunedi, [(m.chiave, m.obiettivo, m.premio)])
    assert await repo.missioni_settimana_riscattate(SERVER, A) == 1
    for x in MISSIONI_SETTIMANA[1:]:
        await repo.aggiungi_progressi([(SERVER, A, LUNEDI, x.chiave, x.obiettivo, x.obiettivo)])
    await repo.riscatta_missioni(SERVER, A, LUNEDI, [(x.chiave, x.obiettivo, x.premio) for x in MISSIONI_SETTIMANA])
    assert await repo.missioni_settimana_riscattate(SERVER, A) == len(MISSIONI_SETTIMANA)


@pytest.mark.asyncio
async def test_lo_scudo_si_compra_con_le_monete_fino_al_massimo_e_salva_la_serie(repo, guadagni, clean_db):
    assert await repo.compra_scudo(SERVER, A, SCUDO_PREZZO) == "saldo"
    await guadagni.add_coins(SERVER, A, SCUDO_PREZZO * 3)
    assert await repo.compra_scudo(SERVER, A, SCUDO_PREZZO) == "ok"
    assert await repo.compra_scudo(SERVER, A, SCUDO_PREZZO) == "ok"
    assert await repo.compra_scudo(SERVER, A, SCUDO_PREZZO) == "pieno"  # niente addebito oltre il massimo
    assert await _monete(guadagni) == SCUDO_PREZZO
    assert (await repo.serie_di(SERVER, A))[3] == SCUDI_MAX

    await repo.registra_riscossione(SERVER, A, ADESSO - 84 * ORE)
    await clean_db.execute("UPDATE progress_serie SET serie = 5 WHERE guild_id = $1 AND user_id = $2", SERVER, A)
    esito = await repo.registra_riscossione(SERVER, A, ADESSO)  # 84 h: servono due scudi
    assert (esito.serie, esito.scudi_usati, esito.scudi) == (6, 2, 0)
    assert await repo.scudi_usati(SERVER, A) == 2


@pytest.mark.asyncio
async def test_il_promemoria_va_solo_a_chi_lo_vuole_e_una_volta_per_riscossione(repo, clean_db):
    await repo.registra_riscossione(SERVER, A, datetime.now(timezone.utc) - 25 * ORE)
    await repo.registra_riscossione(SERVER, B, datetime.now(timezone.utc) - 25 * ORE)
    await clean_db.execute("UPDATE progress_serie SET serie = 4")
    await repo.imposta_promemoria(SERVER, A, True)
    assert [(g, u) for g, u, *_ in await repo.da_avvisare()] == [(SERVER, A)]
    await repo.segna_avvisato(SERVER, A)
    assert await repo.da_avvisare() == []
    await repo.registra_riscossione(SERVER, A, datetime.now(timezone.utc) - 1 * ORE)  # nuova riscossione: riparte
    await clean_db.execute("UPDATE progress_serie SET ultima_at = now() - interval '21 hours' WHERE user_id = $1", A)
    assert len(await repo.da_avvisare()) == 1
    await repo.imposta_promemoria(SERVER, A, False)
    assert await repo.da_avvisare() == []


@pytest.mark.asyncio
async def test_i_premi_estetici_della_serie_si_danno_una_volta_e_si_possono_mettere(repo, clean_db):
    profili = ProfileRepository(pool_provider=lambda: clean_db)
    assert await repo.regala_premi_serie(SERVER, A, 6) == []
    assert sorted(await repo.regala_premi_serie(SERVER, A, 14)) == ["cometa", "scintilla"]
    assert sorted(await repo.regala_premi_serie(SERVER, A, 30)) == ["alba"]  # gli altri due c'erano già
    assert await repo.regala_premi_serie(SERVER, A, 30) == []
    assert {"scintilla", "cometa", "alba"} <= (await profili.get_profile(SERVER, A)).posseduti
    assert await profili.equip(SERVER, A, "badge", "scintilla")


@pytest.mark.asyncio
async def test_traguardi_nuovi_si_dicono_una_volta(repo):
    assert await repo.segna_traguardi(SERVER, A, ["livello_5", "serie_7"]) == ["livello_5", "serie_7"]
    assert await repo.segna_traguardi(SERVER, A, ["livello_5", "livello_10"]) == ["livello_10"]
    assert await repo.traguardi_di(SERVER, A) == {"livello_5", "serie_7", "livello_10"}


STAGIONE = stagione_di(OGGI)[0]


@pytest.mark.asyncio
async def test_pass_i_livelli_liberi_si_pagano_una_volta(repo, guadagni):
    assert (await repo.riscatta_pass(SERVER, A, STAGIONE)).vuoto  # niente XP, niente riga
    await repo.aggiungi_xp_pass([(SERVER, A, STAGIONE, 700), (SERVER, A, STAGIONE, 900)])
    assert await repo.stato_pass(SERVER, A, STAGIONE) == (1600, 0, 0, False)
    esito = await repo.riscatta_pass(SERVER, A, STAGIONE)
    assert (esito.livelli_liberi, esito.livelli_premium, esito.monete) == (3, 0, 12 + 14 + 16)
    assert (await repo.riscatta_pass(SERVER, A, STAGIONE)).vuoto
    await repo.aggiungi_xp_pass([(SERVER, A, STAGIONE, 400)])  # 2000 XP: livello 4
    assert (await repo.riscatta_pass(SERVER, A, STAGIONE)).monete == 18
    assert await _monete(guadagni) == 12 + 14 + 16 + 18
    assert await repo.stato_pass(SERVER, A, "2026-01") == (0, 0, 0, False)
    assert await repo.stagioni_complete(SERVER, A) == 0
    await repo.aggiungi_xp_pass([(SERVER, A, STAGIONE, 10**6)])
    await repo.riscatta_pass(SERVER, A, STAGIONE)
    assert await repo.stagioni_complete(SERVER, A) == 1


@pytest.mark.asyncio
async def test_la_traccia_premium_costa_500mila_monete_o_il_boost_e_dà_doppio_e_oggetti(repo, guadagni, clean_db):
    profili = ProfileRepository(pool_provider=lambda: clean_db)
    await repo.aggiungi_xp_pass([(SERVER, A, STAGIONE, 500 * 10)])  # livello 10
    assert await repo.sblocca_premium(SERVER, A, STAGIONE, pagando=True) == "saldo"
    assert not await repo.ha_aperto_premium(SERVER, A)
    await guadagni.add_coins(SERVER, A, PASS_PREZZO_PREMIUM + 5)
    assert await repo.sblocca_premium(SERVER, A, STAGIONE, pagando=True) == "ok"
    assert await _monete(guadagni) == 5
    assert await repo.sblocca_premium(SERVER, A, STAGIONE, pagando=True) == "gia"  # niente secondo addebito
    assert await _monete(guadagni) == 5 and await repo.ha_aperto_premium(SERVER, A)

    esito = await repo.riscatta_pass(SERVER, A, STAGIONE)
    assert (esito.livelli_liberi, esito.livelli_premium) == (10, 10)
    assert esito.monete == monete_livelli(0, 10, False) + monete_livelli(0, 10, True)
    assert esito.oggetti == ("sigillo",)
    assert "sigillo" in (await profili.get_profile(SERVER, A)).posseduti
    assert (await repo.riscatta_pass(SERVER, A, STAGIONE)).vuoto

    # il boost apre gratis, e i livelli già fatti si pagano anche sulla traccia premium
    await repo.aggiungi_xp_pass([(SERVER, B, STAGIONE, 1000)])
    await repo.riscatta_pass(SERVER, B, STAGIONE)  # solo la libera
    assert await repo.sblocca_premium(SERVER, B, STAGIONE, pagando=False) == "ok"
    tardivo = await repo.riscatta_pass(SERVER, B, STAGIONE)
    assert (tardivo.livelli_liberi, tardivo.livelli_premium, tardivo.monete) == (0, 2, monete_livelli(0, 2, True))


@pytest.mark.asyncio
async def test_profilo_globale_conta_server_livelli_serie_e_traguardi(repo, clean_db):
    await clean_db.execute(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total, level) VALUES ($1, $2, 500, 4), ($3, $2, 900, 9), ($4, $2, 0, 0)",
        SERVER, A, SERVER + 1, SERVER + 2,
    )
    await repo.registra_riscossione(SERVER, A, ADESSO)
    await repo.segna_traguardi(SERVER, A, ["livello_5"])
    await repo.segna_traguardi(SERVER + 1, A, ["livello_5", "livello_10"])
    assert await repo.profilo_globale(A) == (2, 9, 1, 2)  # il server con 0 XP non conta
    assert await repo.profilo_globale(A + 1) == (0, 0, 0, 0)


# ------------------------------------------------------------------ servizio
@pytest.fixture
def mondo(repo, monkeypatch, clean_db, guadagni):
    import core.database as database_module
    import core.repositories.leveling_repo as lr

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._settings_cache.clear()
    monkeypatch.setattr(servizio, "progressi_repo", repo)
    monkeypatch.setattr(lr, "leveling_repo", guadagni)
    monkeypatch.setattr(servizio, "_adesso", lambda: ADESSO)
    monkeypatch.setattr(servizio, "_oggi", lambda: OGGI)
    servizio._pendenti.clear()
    monkeypatch.setattr(servizio, "_giorno_pendenti", None, raising=False)
    yield
    servizio._pendenti.clear()
    database_module.db._settings_cache.clear()


@pytest.mark.asyncio
async def test_spento_di_base_non_si_conta_niente(mondo):
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI, xp=20)
    assert servizio._pendenti == {}
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")
    assert await servizio.progressi_repo.serie_di(SERVER, A) == (0, 0, None, 0, False)


@pytest.mark.asyncio
async def test_acceso_gli_eventi_con_gli_xp_si_scrivono_su_giorno_settimana_e_pass(mondo):
    await servizio.imposta_attivo(SERVER, True, A)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI, xp=20)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI, xp=15)
    await servizio.registra(SERVER, A, EVENTO_VOCALE, 2, xp=10)
    await servizio.registra(SERVER, A, "evento-sconosciuto")
    assert servizio._pendenti == {(SERVER, A, EVENTO_MESSAGGI): [2, 35], (SERVER, A, EVENTO_VOCALE): [2, 10]}
    await servizio.registra_molti(SERVER, [B], EVENTO_VOCALE, 1)
    await servizio.svuota(SERVER, A)  # solo quelli di A
    assert list(servizio._pendenti) == [(SERVER, B, EVENTO_VOCALE)]
    repo = servizio.progressi_repo
    assert (await repo.missioni_di(SERVER, A, OGGI))[EVENTO_MESSAGGI][0] == 2
    assert (await repo.missioni_di(SERVER, A, LUNEDI))["sett_messaggi"][0] == 2
    assert "messaggi" not in await repo.missioni_di(SERVER, A, LUNEDI)  # le missioni del giorno non vanno al lunedì
    assert (await repo.stato_pass(SERVER, A, STAGIONE))[0] == 45
    await servizio.svuota()
    assert servizio._pendenti == {}
    assert (await repo.stato_pass(SERVER, B, STAGIONE))[0] == 0  # nessun XP: nessuna riga da pagare


@pytest.mark.asyncio
async def test_a_mezzanotte_gli_eventi_restano_nel_loro_giorno(mondo, monkeypatch):
    await servizio.imposta_attivo(SERVER, True)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)
    domani = OGGI + timedelta(days=1)
    monkeypatch.setattr(servizio, "_oggi", lambda: domani)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)
    await servizio.svuota()
    repo = servizio.progressi_repo
    assert (await repo.missioni_di(SERVER, A, OGGI))[EVENTO_MESSAGGI][0] == 1
    assert (await repo.missioni_di(SERVER, A, domani))[EVENTO_MESSAGGI][0] == 1


@pytest.mark.asyncio
async def test_il_tetto_di_memoria_scarta_le_voci_nuove(mondo, monkeypatch):
    await servizio.imposta_attivo(SERVER, True)
    monkeypatch.setattr(servizio, "MAX_PENDENTI", 1)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)
    await servizio.registra(SERVER, A + 1, EVENTO_MESSAGGI)
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI)  # la voce c'è già: sale
    assert servizio._pendenti == {(SERVER, A, EVENTO_MESSAGGI): [2, 0]}


@pytest.mark.asyncio
async def test_l_obiettivo_del_server_e_una_impostazione_con_un_punto_solo(mondo):
    assert await servizio.obiettivo_server_base(SERVER) == 1000
    await servizio.imposta_obiettivo_server(SERVER, 300, A)
    assert await servizio.obiettivo_server_base(SERVER) == 300
    with pytest.raises(ValueError):
        await servizio.imposta_obiettivo_server(SERVER, 10)
    assert await servizio.obiettivo_server_base(SERVER) == 300


@pytest.mark.asyncio
async def test_riscossione_giornaliera_serie_missione_e_premio_estetico_a_sette_giorni(mondo, repo, clean_db):
    await servizio.imposta_attivo(SERVER, True)
    profili = ProfileRepository(pool_provider=lambda: clean_db)
    await repo.registra_riscossione(SERVER, A, ADESSO - 24 * ORE)
    await clean_db.execute("UPDATE progress_serie SET serie = 6, record = 6 WHERE guild_id = $1 AND user_id = $2", SERVER, A)

    await servizio.dopo_riscossione(SERVER, A, "last_work_at")  # il lavoro non conta
    assert (await repo.serie_di(SERVER, A))[0] == 6
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")
    assert (await repo.serie_di(SERVER, A))[:2] == (7, 7)
    assert "scintilla" in (await profili.get_profile(SERVER, A)).posseduti  # premio estetico
    assert await servizio.progressi_repo.missioni_completate(SERVER, A) == 0
    assert servizio._pendenti[(SERVER, A, EVENTO_DAILY)] == [1, 0]
    assert "serie_7" in await repo.traguardi_di(SERVER, A)
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")  # la stessa riscossione di poco fa
    assert (await repo.serie_di(SERVER, A))[0] == 7
    assert await repo.da_avvisare() == []  # nessun promemoria non chiesto


@pytest.mark.asyncio
async def test_la_protezione_salva_la_serie_e_sblocca_il_traguardo_nascosto(mondo, repo, guadagni, clean_db):
    await servizio.imposta_attivo(SERVER, True)
    await guadagni.add_coins(SERVER, A, SCUDO_PREZZO)
    assert await servizio.compra_scudo(SERVER, A) == "ok"
    await repo.registra_riscossione(SERVER, A, ADESSO - 60 * ORE)
    await clean_db.execute("UPDATE progress_serie SET serie = 4 WHERE guild_id = $1 AND user_id = $2", SERVER, A)
    await servizio.dopo_riscossione(SERVER, A, "last_daily_at")
    assert (await repo.serie_di(SERVER, A))[0] == 5
    assert "scudo_salvaserie" in await repo.traguardi_di(SERVER, A)


@pytest.mark.asyncio
async def test_il_promemoria_arriva_in_privato_solo_a_chi_l_ha_chiesto(mondo, repo, monkeypatch):
    await servizio.imposta_attivo(SERVER, True)
    adesso = datetime.now(timezone.utc)
    monkeypatch.setattr(servizio, "_adesso", lambda: adesso)
    await repo.registra_riscossione(SERVER, A, adesso - 25 * ORE)
    await repo.registra_riscossione(SERVER, B, adesso - 25 * ORE)
    await servizio.progressi_repo._pool.execute("UPDATE progress_serie SET serie = 5")
    await servizio.imposta_promemoria(SERVER, A, True)
    utente = MagicMock()
    utente.send = AsyncMock()
    bot = MagicMock()
    bot.get_user.return_value = utente
    bot.get_guild.return_value.name = "Casa"
    assert await servizio.manda_promemoria(bot) == 1
    assert "Casa" in utente.send.await_args.args[0]
    assert await servizio.manda_promemoria(bot) == 0  # una volta per riscossione

    import discord

    await repo.registra_riscossione(SERVER, A, adesso - 25 * ORE)
    await servizio.progressi_repo._pool.execute("UPDATE progress_serie SET serie = 5, ultima_at = $1", adesso - 25 * ORE)
    utente.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403, reason="x"), "chiusi"))
    assert await servizio.manda_promemoria(bot) == 0  # messaggi privati chiusi: niente errori
    assert await repo.da_avvisare() == []  # e niente riprove


@pytest.mark.asyncio
async def test_riscatto_delle_missioni_giorno_settimana_e_server_scrive_prima_gli_eventi(mondo, repo, guadagni):
    await servizio.imposta_attivo(SERVER, True)
    await servizio.imposta_obiettivo_server(SERVER, 50)  # missione del server: 50 messaggi
    daily, sett = _giorno(EVENTO_DAILY), _giorno("sett_daily")
    await servizio.registra(SERVER, A, EVENTO_DAILY, 5)  # ancora in memoria: chiude la missione del giorno e della settimana
    msg = _giorno("sett_messaggi")
    await servizio.registra(SERVER, A, EVENTO_MESSAGGI, msg.obiettivo)  # e tutta la settimana di messaggi
    esito = await servizio.riscatta_missioni(SERVER, A)
    ms = MISSIONI_SERVER[0]
    # giorno: daily (messaggi del giorno non è finita? 120 >= 15, sì) ; settimana: daily, messaggi ; server: messaggi
    atteso = daily.premio + _giorno("messaggi").premio + sett.premio + msg.premio + ms.premio
    assert esito.monete == atteso and esito.quanti == 5
    assert await servizio.riscatta_missioni(SERVER, A) == servizio.EsitoRiscatto(0, 0)
    assert await _monete(guadagni) == atteso
    # B non ha partecipato: il server ha finito ma lui non prende il premio del server
    assert (await servizio.riscatta_missioni(SERVER, B)).monete == 0


@pytest.mark.asyncio
async def test_riscatto_del_pass_e_traguardo_a_cinquanta_livelli(mondo, repo):
    await servizio.imposta_attivo(SERVER, True)
    await repo.aggiungi_xp_pass([(SERVER, A, STAGIONE, 1000)])
    esito, nuovi = await servizio.riscatta_pass(SERVER, A)
    assert (esito.livelli_liberi, esito.monete) == (2, 12 + 14) and nuovi == ()
    assert (await servizio.riscatta_pass(SERVER, A))[0].vuoto
    await repo.aggiungi_xp_pass([(SERVER, A, STAGIONE, 10**6)])
    _, nuovi = await servizio.riscatta_pass(SERVER, A)
    assert "stagione_completa" in nuovi


@pytest.mark.asyncio
async def test_sbloccare_la_traccia_premium_col_boost_e_gratis_e_da_il_traguardo_nascosto(mondo, repo, guadagni):
    await servizio.imposta_attivo(SERVER, True)
    assert (await servizio.sblocca_premium(SERVER, A, booster=False))[0] == "saldo"
    esito, nuovi = await servizio.sblocca_premium(SERVER, A, booster=True)
    assert esito == "ok" and "pass_premium" in nuovi
    assert (await servizio.sblocca_premium(SERVER, A, booster=True))[0] == "gia"
    assert await _monete(guadagni) == 0


# ------------------------------------------------------------------ aggancio nel livellamento
@pytest.mark.asyncio
async def test_il_livellamento_conta_messaggi_vocale_e_riscossione_con_gli_xp(mondo, guadagni):
    await servizio.imposta_attivo(SERVER, True)
    await guadagni.add_text_xp(SERVER, A)
    voce = servizio._pendenti[(SERVER, A, EVENTO_MESSAGGI)]
    assert voce[0] == 1 and voce[1] > 0  # gli XP del messaggio contano per il pass
    await guadagni.add_text_xp(SERVER, A)  # pausa tra due messaggi: niente XP, niente conteggio
    assert servizio._pendenti[(SERVER, A, EVENTO_MESSAGGI)][0] == 1

    await guadagni.add_voice_minutes(SERVER, [(A, 5, True), (A + 1, 5, False)])
    assert servizio._pendenti[(SERVER, A, EVENTO_VOCALE)][0] == 1 and servizio._pendenti[(SERVER, A, EVENTO_VOCALE)][1] > 0
    assert (SERVER, A + 1, EVENTO_VOCALE) not in servizio._pendenti

    assert await guadagni.claim_daily(SERVER, A, 10, 86400, datetime.now(timezone.utc)) is True
    assert servizio._pendenti[(SERVER, A, EVENTO_DAILY)][0] == 1


@pytest.mark.asyncio
async def test_con_i_progressi_spenti_il_livellamento_resta_com_e(mondo, guadagni):
    assert (await guadagni.add_text_xp(SERVER, A)).granted is True
    assert servizio._pendenti == {}


# ------------------------------------------------------------------ finestra e comandi
def _interazione(utente=A, dati=None):
    membro = fake_member(utente)
    membro.premium_since = None
    i = fake_interaction(guild=fake_guild(SERVER), user=membro)
    i.data = dati or {}
    return i


@pytest.fixture
def acceso(mondo, monkeypatch):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))


@pytest.mark.asyncio
async def test_spenti_la_finestra_lo_dice_ma_il_profilo_globale_si_vede(mondo, monkeypatch):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    cog = modulo.ProgressiCog(MagicMock())
    i = _interazione()
    await cog.progressi.callback(cog, i)
    assert "/economia progressi" in i.response.send_message.await_args.kwargs["embed"].description

    embed, vista = await modulo.costruisci(i.guild, i.user, "globale")
    assert "Server in cui giochi" in embed.description


@pytest.mark.asyncio
@pytest.mark.parametrize("sezione", ["missioni", "traguardi", "serie", "pass", "globale"])
async def test_ogni_sezione_ha_un_embed_corto_e_un_menu_con_la_scelta_attuale(acceso, sezione):
    await servizio.imposta_attivo(SERVER, True)
    i = _interazione()
    embed, vista = await modulo.costruisci(i.guild, i.user, sezione)
    assert embed.description and len(embed.description) <= 4000
    menu = vista.children[0]
    assert [o.value for o in menu.options] == [c for c, _ in modulo.MENU]
    assert [o.value for o in menu.options if o.default] == [sezione]
    assert len(vista.children) <= 5  # righe e bottoni dentro i limiti di Discord


@pytest.mark.asyncio
async def test_il_comando_apre_le_missioni_in_privato(acceso):
    await servizio.imposta_attivo(SERVER, True)
    cog = modulo.ProgressiCog(MagicMock())
    i = _interazione()
    await cog.progressi.callback(cog, i)
    argomenti = i.response.send_message.await_args.kwargs
    assert argomenti["ephemeral"] is True and "Di tutto il server" in argomenti["embed"].description
    assert "Della settimana" in argomenti["embed"].description


@pytest.mark.asyncio
async def test_il_menu_cambia_sezione_e_lo_usa_solo_chi_ha_aperto(acceso):
    await servizio.imposta_attivo(SERVER, True)
    i = _interazione()
    _, vista = await modulo.costruisci(i.guild, i.user, "missioni")
    assert await vista.interaction_check(_interazione(A + 5)) is False
    i2 = _interazione(dati={"values": ["serie"]})
    await vista._scelta(i2)
    argomenti = i2.response.edit_message.await_args.kwargs
    assert argomenti["embed"].title == "Serie di giorni"
    assert [o.value for o in argomenti["view"].children[0].options if o.default] == ["serie"]


def _bottone(vista, inizio):
    return next(b for b in vista.children if getattr(b, "label", "").startswith(inizio))


@pytest.mark.asyncio
async def test_il_bottone_riscuoti_paga_poi_non_c_e_piu_niente(acceso, repo, guadagni):
    await servizio.imposta_attivo(SERVER, True)
    daily = _giorno(EVENTO_DAILY)
    await repo.aggiungi_progressi([(SERVER, A, OGGI, daily.chiave, 1, daily.obiettivo)])
    i = _interazione()
    _, vista = await modulo.costruisci(i.guild, i.user, "missioni")
    assert _bottone(vista, "Riscuoti").disabled is False
    i2 = _interazione()
    await vista._riscuoti(i2)
    assert f"**{daily.premio}**" in i2.followup.send.await_args.args[0]
    assert i2.response.edit_message.await_args.kwargs["embed"].title == "Missioni"
    i3 = _interazione()
    await vista._riscuoti(i3)
    assert "niente da riscuotere" in i3.response.send_message.await_args.args[0]
    _, nuova = await modulo.costruisci(i.guild, i.user, "missioni")
    assert _bottone(nuova, "Riscuoti").disabled is True


@pytest.mark.asyncio
async def test_serie_scudo_e_promemoria_dalla_finestra(acceso, guadagni, repo):
    await servizio.imposta_attivo(SERVER, True)
    i = _interazione()
    _, vista = await modulo.costruisci(i.guild, i.user, "serie")
    assert _bottone(vista, "Accendi il promemoria")
    i2 = _interazione()
    await vista._scudo(i2)
    assert f"Servono {SCUDO_PREZZO}" in i2.response.send_message.await_args.args[0]
    await guadagni.add_coins(SERVER, A, SCUDO_PREZZO)
    i3 = _interazione()
    await vista._scudo(i3)
    assert "Scudo comprato" in i3.followup.send.await_args.args[0]
    assert (await repo.serie_di(SERVER, A))[3] == 1
    await vista._promemoria(_interazione())
    assert (await repo.serie_di(SERVER, A))[4] is True
    _, nuova = await modulo.costruisci(i.guild, i.user, "serie")
    assert _bottone(nuova, "Spegni il promemoria")
    await nuova._promemoria(_interazione())
    assert (await repo.serie_di(SERVER, A))[4] is False


@pytest.mark.asyncio
async def test_pass_la_traccia_premium_si_apre_dal_bottone_col_boost_o_con_le_monete(acceso, guadagni, repo):
    await servizio.imposta_attivo(SERVER, True)
    i = _interazione()
    _, vista = await modulo.costruisci(i.guild, i.user, "pass")
    i2 = _interazione()
    await vista._apri_premium(i2)
    assert "boost" in i2.response.send_message.await_args.args[0]
    booster = _interazione()
    booster.user.premium_since = datetime.now(timezone.utc)
    await vista._apri_premium(booster)
    assert "grazie al boost" in booster.followup.send.await_args.args[0]
    _, aperta = await modulo.costruisci(i.guild, i.user, "pass")
    assert not any(getattr(b, "label", "").startswith("Apri") for b in aperta.children)
    i3 = _interazione()
    await aperta._apri_premium(i3)
    assert "già aperta" in i3.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_il_comando_dello_staff_accende_spegne_e_fissa_l_obiettivo(mondo, monkeypatch):
    monkeypatch.setattr(modulo, "_comando_rifiutato", AsyncMock(return_value=False))
    cog = modulo.ProgressiCog(MagicMock())
    i = _interazione()
    await cog.progressi_staff.callback(cog, i, True, 400)
    assert await servizio.attivo(SERVER) is True and await servizio.obiettivo_server_base(SERVER) == 400
    assert "accesi" in i.response.send_message.await_args.args[0]
    i2 = _interazione()
    await cog.progressi_staff.callback(cog, i2, False, None)
    assert await servizio.attivo(SERVER) is False and "spenti" in i2.response.send_message.await_args.args[0]
    i3 = _interazione()
    await cog.progressi_staff.callback(cog, i3, None, None)  # senza opzioni: dice com'è
    assert "spenti" in i3.response.send_message.await_args.args[0] and "400" in i3.response.send_message.await_args.args[0]
