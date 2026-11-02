"""
tests/test_automod_regole_repo.py
=================================
Regole AutoMod su PostgreSQL vero: servizio D16, tetti, gruppi, e la migrazione 0501 che copia le vecchie azioni
(le punizioni devono essere le stesse prima e dopo).
Funzioni coperte: SPEC §6 (AMD-043, AMD-067), D63
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import automod_regole_service as S
from core.automod_advanced_logic import AZIONI_DI_PARTENZA, AZIONI_DI_PARTENZA_GENERALI
from core.automod_regole_logic import Azione, Regola, RegolaNonValida, azioni_dai_nomi_vecchi
from core.repositories.automod_advanced_repo import AutomodAdvancedSettings, _from_json

SQL_0501 = (Path(__file__).parent.parent / "core/migrations/0501_automod_azioni_nelle_regole.sql").read_text()
ORDINE = ("delete", "warn", "mute", "kick", "ban")


@pytest.fixture(autouse=True)
def _cache():
    S.svuota_cache()
    yield
    S.svuota_cache()


@pytest.fixture
def repo_vero(clean_db, monkeypatch):
    from core.repositories import automod_regole_repo as modulo

    monkeypatch.setattr(modulo.automod_regole_repo, "_pool_provider", lambda: clean_db)
    return clean_db


async def test_filtro_senza_riga_usa_le_azioni_di_partenza(repo_vero):
    r = await S.regola_effettiva(1, "anti_link", azioni_dai_nomi_vecchi(("delete",), 600))
    assert [a.t for a in r.azioni] == ["cancella"]
    assert r.tipo == "filtro"
    assert [a.t for a in await S.azioni_del_filtro(1, "anti_link", ("delete", "mute"), 900)] == ["cancella", "timeout"]


async def test_salva_cache_e_invalidazione(repo_vero):
    await S.imposta_azioni_filtro(1, "anti_link", ("delete", "ban"), 600, 7)
    assert [a.t for a in (await S.regola_effettiva(1, "anti_link")).azioni] == ["cancella", "ban"]
    await S.imposta_azioni_filtro(1, "anti_link", (), 600, 7)  # nessuna azione: resta nessuna, non torna il difetto
    assert (await S.azioni_del_filtro(1, "anti_link", ("delete",), 600)) == ()
    assert await repo_vero.fetchval("SELECT aggiornata_da FROM automod_regole WHERE guild_id = 1") == 7


async def test_regole_personali_numero_tetto_e_isolamento_tra_server(repo_vero):
    base = Regola(chiave="x", tipo="personale", nome="Prova", azioni=(Azione("cancella"),))
    r = await S.crea_personale(1, base, 5)
    assert r.chiave == f"p:{await repo_vero.fetchval('SELECT id FROM automod_regole')}"
    for _ in range(49):
        await S.crea_personale(1, base, 5)
    with pytest.raises(RegolaNonValida):
        await S.crea_personale(1, base, 5)
    await S.crea_personale(1, base, 5, premium=True)  # il Premium arriva a 100
    await S.crea_personale(2, base, 5)  # un altro server ha il suo tetto
    assert len(await S.regole_del_server(2)) == 1


async def test_elimina_solo_le_personali(repo_vero):
    f = await S.imposta_azioni_filtro(1, "anti_link", ("delete",), 600, 1)
    p = await S.crea_personale(1, Regola(chiave="x", tipo="personale", nome="P"), 1)
    assert not await S.elimina(1, f.chiave)
    assert await S.elimina(1, p.chiave)
    assert [r.chiave for r in await S.regole_del_server(1)] == ["anti_link"]


async def test_gruppo_acceso_e_spento(repo_vero):
    for n in ("a", "b"):
        await S.crea_personale(1, Regola(chiave="x", tipo="personale", nome=n, gruppo="raid"), 1)
    await S.crea_personale(1, Regola(chiave="x", tipo="personale", nome="c", gruppo="altro"), 1)
    assert await S.attiva_gruppo(1, "raid", False) == 2
    assert [r.attiva for r in await S.regole_del_server(1)] == [False, False, True]
    assert await S.attiva_gruppo(1, "raid", False) == 0


async def test_durata_mute_segue_solo_i_timeout_di_prima(repo_vero):
    await S.imposta_azioni_filtro(1, "anti_link", ("delete", "mute"), 600, 1)
    await S.imposta_azioni_filtro(1, "anti_caps", ("mute",), 600, 1)
    await repo_vero.execute(
        "UPDATE automod_regole SET azioni = '[{\"t\":\"timeout\",\"secondi\":60}]' WHERE chiave = 'anti_caps'")
    await S.cambia_durata_mute(1, 600, 1800)
    assert (await S.regola_effettiva(1, "anti_link")).azioni[1].get("secondi") == 1800
    assert (await S.regola_effettiva(1, "anti_caps")).azioni[0].get("secondi") == 60  # scelto a mano: resta


# ---------------------------------------------------------------- 0501

def _settings(guild_id, azioni, mute):
    return {"actions": azioni, "mute_duration_seconds": mute}


CASI = [
    (11, {"anti_link": ["ban", "delete"], "phishing": ["delete", "mute", "kick"], "ripetuti": []}, 900),
    (12, {"anti_caps": ["warn", "mute", "ban", "kick", "delete"]}, 600),
    (13, {"anti_zalgo": ["mute"]}, 99_999_999),  # oltre i 28 giorni: si taglia al limite di Discord
    (14, {}, 600),
    (15, {"anti_link": ["delete"], "x" * 40: ["warn"]}, 600),
]


async def test_0501_stesse_punizioni_prima_e_dopo(repo_vero):
    for gid, azioni, mute in CASI:
        await repo_vero.execute(
            "INSERT INTO automod_advanced_config (guild_id, settings) VALUES ($1, $2::jsonb)",
            gid, json.dumps(_settings(gid, azioni, mute)))
    await repo_vero.execute("DELETE FROM automod_regole")
    await repo_vero.execute(SQL_0501)
    await repo_vero.execute(SQL_0501)  # rieseguibile: nessun doppione
    S.svuota_cache()
    for gid, azioni, mute in CASI:
        prima = _from_json(gid, json.dumps(_settings(gid, azioni, mute)))
        regole = {r.chiave: r for r in await S.regole_del_server(gid)}
        assert set(regole) == set(azioni), gid
        for chiave, nomi in azioni.items():
            attese = azioni_dai_nomi_vecchi(tuple(nomi), prima.mute_duration_seconds)
            assert regole[chiave].azioni == attese, (gid, chiave)
            # stesso ordine di esecuzione di prima (VALID_ACTIONS), stesse punizioni
            assert [a.t for a in regole[chiave].azioni] == [
                {"delete": "cancella", "mute": "timeout"}.get(n, n) for n in ORDINE if n in nomi
            ]
            assert regole[chiave].tipo == "filtro" and regole[chiave].nome == chiave[:32]
    # i timeout copiati portano la durata di mute del server (al massimo 28 giorni)
    assert regole_timeout(await S.regole_del_server(13)) == 2_419_200
    assert regole_timeout(await S.regole_del_server(11)) == 900


def regole_timeout(regole):
    return next(a.get("secondi") for r in regole for a in r.azioni if a.t == "timeout")


async def test_0501_ignora_dati_sporchi(repo_vero):
    await repo_vero.execute("INSERT INTO automod_advanced_config (guild_id, settings) VALUES (21, '{\"actions\": 5}')")
    await repo_vero.execute("INSERT INTO automod_advanced_config (guild_id, settings) VALUES (22, '{}')")
    await repo_vero.execute("INSERT INTO automod_advanced_config (guild_id, settings) VALUES (23, '{\"actions\": {\"k\": \"x\"}}')")
    await repo_vero.execute(SQL_0501)
    assert await repo_vero.fetchval("SELECT count(*) FROM automod_regole WHERE guild_id IN (21, 22, 23)") == 0


def test_azioni_di_partenza_senza_riga_restano_le_stesse():
    # il difetto dei filtri senza riga è quello di prima: cancella (e per il phishing anche il timeout)
    assert [a.t for a in azioni_dai_nomi_vecchi(AZIONI_DI_PARTENZA["phishing"] if "phishing" in AZIONI_DI_PARTENZA else AZIONI_DI_PARTENZA_GENERALI, 600)][0] == "cancella"


async def test_una_riga_illeggibile_non_spegne_le_altre_e_non_si_rilegge_a_ogni_messaggio(repo_vero, monkeypatch):
    from core.repositories import automod_regole_repo as modulo

    await S.salva(50, Regola(chiave="anti_caps", tipo="filtro", nome="anti_caps", attiva=False), 1)
    await repo_vero.execute(  # una riga che i tetti di oggi rifiutano (es. scritta con tetti più larghi)
        "INSERT INTO automod_regole (guild_id, chiave, tipo, nome, azioni) VALUES (50, 'p:9', 'personale', 'x', "
        "'[{\"t\": \"boh\"}]'::jsonb)")
    S.svuota_cache()
    letture = 0
    vera = modulo.automod_regole_repo.elenca

    async def conta(*a, **k):
        nonlocal letture
        letture += 1
        return await vera(*a, **k)

    monkeypatch.setattr(modulo.automod_regole_repo, "elenca", conta)
    regole = await S.regole_del_server(50)
    assert [r.chiave for r in regole] == ["anti_caps"]  # la regola spenta resta spenta, la riga rotta si salta
    assert regole[0].attiva is False
    await S.regole_del_server(50)
    assert letture == 1  # in cache: niente query e niente errore nel log a ogni messaggio
