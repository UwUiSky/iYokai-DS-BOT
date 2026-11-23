"""
tests/test_panel_ruoli_collegati_giro.py
========================================
Giro periodico dei ruoli collegati Twitch (ALR-049, D127, SPEC §24.9): rinnovo del token, tipo di canale riletto,
riscrittura su Discord solo se cambia, scollegamento se il token è revocato, tetti di quota e stop al 429. Rete finta.
"""

from datetime import datetime, timedelta, timezone

import pytest

from core import oauth_crypto, ruoli_collegati_giro as giro_mod, ruoli_collegati_logic as logica, ruoli_collegati_verifica as ver
from core.repositories.ruoli_collegati_repo import ruoli_collegati_repo
from core.repositories.ruoli_collegati_verifica_repo import ruoli_collegati_verifica_repo

CHIAVE = oauth_crypto.generate_key()
CFG = logica.Configurazione("twitch-client", "segreto", CHIAVE, "token-bot")
PASSATO = datetime.now(timezone.utc) - timedelta(hours=1)
FUTURO = datetime.now(timezone.utc) + timedelta(hours=3)


class Rete:
    def __init__(self):
        self.twitch_rinnovo = ("ok", logica.TokenOAuth("tw-nuovo", "tw-refresh-nuovo", FUTURO))
        self.utente_stati = []  # (payload, stato) in ordine; l'ultimo si ripete
        self.discord_rinnovo = ("ok", logica.TokenOAuth("dc-nuovo", "dc-refresh-nuovo", FUTURO))
        self.scrittura = 200
        self.scritti = []
        self.chiamate = []

    async def twitch_rinnova(self, refresh):
        self.chiamate.append(("tw_rinnova", refresh))
        esito, token = self.twitch_rinnovo
        return (token if esito == "ok" else None), esito

    async def twitch_utente_stato(self, access):
        self.chiamate.append(("tw_utente", access))
        voce = self.utente_stati[0] if len(self.utente_stati) == 1 else self.utente_stati.pop(0)
        return voce

    async def discord_rinnova_esito(self, refresh):
        self.chiamate.append(("dc_rinnova", refresh))
        esito, token = self.discord_rinnovo
        return (token if esito == "ok" else None), esito

    async def discord_scrivi_stato(self, access, corpo):
        self.chiamate.append(("dc_scrivi", access))
        self.scritti.append(corpo)
        return self.scrittura


def profilo(tipo="affiliate", login="mario_tv", id_="123"):
    return {"data": [{"id": id_, "login": login, "broadcaster_type": tipo}]}


@pytest.fixture
def ambiente(clean_db, monkeypatch):
    for r in (ruoli_collegati_repo, ruoli_collegati_verifica_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    rete = Rete()
    rete.utente_stati = [(profilo(), 200)]
    return rete, clean_db


async def _collega(pool, uid=1001, tipo="affiliate", tw_scade=FUTURO, dc_scade=FUTURO, aggiornato=None, id_="123"):
    k = CHIAVE
    await pool.execute(
        "INSERT INTO ruoli_collegati_twitch (user_id, twitch_id, twitch_login, tipo, twitch_token, twitch_refresh, twitch_scade_il, "
        "discord_token, discord_refresh, discord_scade_il, collegato_il, aggiornato_il) "
        "VALUES ($1,$2,'mario_tv',$3,$4,$5,$6,$7,$8,$9, now(), $10)",
        uid, id_, tipo, logica.cifra(k, uid, "twitch_token", "tw-vecchio"), logica.cifra(k, uid, "twitch_refresh", "tw-refresh"),
        tw_scade, logica.cifra(k, uid, "discord_token", "dc-vecchio"), logica.cifra(k, uid, "discord_refresh", "dc-refresh"),
        dc_scade, aggiornato,
    )


async def _riga(pool, uid=1001):
    return await pool.fetchrow("SELECT * FROM ruoli_collegati_twitch WHERE user_id = $1", uid)


@pytest.mark.asyncio
async def test_tipo_cambiato_si_riscrive_su_discord(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    rete.utente_stati = [(profilo("partner"), 200)]
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert (r.controllati, r.cambiati, r.scollegati, r.errori) == (1, 1, 0, 0)
    assert rete.scritti[0]["metadata"] == {"twitch_affiliato": False, "twitch_partner": True}
    riga = await _riga(pool)
    assert riga["tipo"] == "partner" and riga["aggiornato_il"] is not None and riga["errori"] == 0


@pytest.mark.asyncio
async def test_invariato_non_scrive_su_discord_e_non_riparte_prima_delle_11_ore(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert (r.controllati, r.cambiati) == (1, 0) and rete.scritti == []
    rete.chiamate.clear()
    assert (await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)).controllati == 0  # appena aggiornato
    assert rete.chiamate == []


@pytest.mark.asyncio
async def test_token_scaduto_si_rinnova_e_si_salva_cifrato(ambiente):
    rete, pool = ambiente
    await _collega(pool, tw_scade=PASSATO)
    await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert ("tw_rinnova", "tw-refresh") in rete.chiamate and ("tw_utente", "tw-refresh-nuovo") not in rete.chiamate
    assert ("tw_utente", "tw-nuovo") in rete.chiamate
    riga = await _riga(pool)
    assert "tw-nuovo" not in riga["twitch_token"]
    assert logica.decifra(CHIAVE, 1001, "twitch_token", riga["twitch_token"]) == "tw-nuovo"
    assert logica.decifra(CHIAVE, 1001, "twitch_refresh", riga["twitch_refresh"]) == "tw-refresh-nuovo"


@pytest.mark.asyncio
async def test_rinnovo_revocato_scollega_e_azzera_twitch_su_discord(ambiente):
    rete, pool = ambiente
    await _collega(pool, tw_scade=PASSATO)
    rete.twitch_rinnovo = ("revocato", None)
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.scollegati == 1 and await _riga(pool) is None
    assert rete.scritti[0]["metadata"] == {"twitch_affiliato": False, "twitch_partner": False}


@pytest.mark.asyncio
async def test_401_dopo_un_solo_rinnovo_scollega(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    rete.utente_stati = [(None, 401)]
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.scollegati == 1 and await _riga(pool) is None
    assert sum(1 for c in rete.chiamate if c[0] == "tw_rinnova") == 1


@pytest.mark.asyncio
async def test_401_poi_rinnovo_riuscito_prosegue(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    rete.utente_stati = [(None, 401), (profilo(), 200)]
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.scollegati == 0 and await _riga(pool) is not None


@pytest.mark.asyncio
async def test_guasto_passeggero_non_scollega_e_conta_gli_errori(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    rete.utente_stati = [(None, 503)]
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.errori == 1 and r.scollegati == 0
    riga = await _riga(pool)
    assert riga is not None and riga["errori"] == 1 and riga["aggiornato_il"] is None  # si riprova al prossimo giro


@pytest.mark.asyncio
async def test_429_ferma_il_giro_e_le_altre_persone_restano(ambiente):
    rete, pool = ambiente
    await _collega(pool, uid=1001)
    await _collega(pool, uid=1002)
    rete.utente_stati = [(None, 429)]
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.fermato_per_limite and r.controllati == 1
    assert sum(1 for c in rete.chiamate if c[0] == "tw_utente") == 1


@pytest.mark.asyncio
async def test_tetto_per_giro_e_pausa_tra_persone(ambiente):
    rete, pool = ambiente
    for uid in range(2001, 2006):
        await _collega(pool, uid=uid)
    pause = []

    async def dormi(s):
        pause.append(s)

    r = await giro_mod.giro(cfg=CFG, rete=rete, limite=3, pausa=0.5, dormi=dormi)
    assert r.controllati == 3 and pause == [0.5, 0.5, 0.5]
    assert await pool.fetchval("SELECT count(*) FROM ruoli_collegati_twitch WHERE aggiornato_il IS NULL") == 2


@pytest.mark.asyncio
async def test_canale_di_un_altro_id_scollega(ambiente):
    rete, pool = ambiente
    await _collega(pool, id_="999")
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.scollegati == 1


@pytest.mark.asyncio
async def test_discord_rifiuta_la_scrittura_si_ripristina_e_si_riprova(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    rete.utente_stati = [(profilo("partner"), 200)]
    rete.scrittura = 500
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.errori == 1 and (await _riga(pool))["tipo"] == "affiliate"  # non si perde la differenza
    rete.scrittura = 200
    assert (await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)).cambiati == 1


@pytest.mark.asyncio
async def test_token_discord_revocato_in_scrittura_scollega(ambiente):
    rete, pool = ambiente
    await _collega(pool, dc_scade=PASSATO)
    rete.utente_stati = [(profilo("partner"), 200)]
    rete.discord_rinnovo = ("revocato", None)
    r = await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert r.scollegati == 1 and await _riga(pool) is None


@pytest.mark.asyncio
async def test_il_corpo_tiene_la_verifica_collegata(ambiente):
    rete, pool = ambiente
    await _collega(pool)
    await ruoli_collegati_verifica_repo.salva(1001, "x", None, None, True, True)
    rete.utente_stati = [(profilo("partner"), 200)]
    await giro_mod.giro(cfg=CFG, rete=rete, pausa=0)
    assert "verifica_superata" in rete.scritti[0]["metadata"] and rete.scritti[0]["metadata"]["twitch_partner"] is True


@pytest.mark.asyncio
async def test_ciclo_un_errore_non_lo_ferma(monkeypatch):
    import asyncio

    chiamate = []

    def crea():
        chiamate.append(1)
        if len(chiamate) == 1:
            raise RuntimeError("guasto")
        raise asyncio.CancelledError

    compito = asyncio.create_task(giro_mod.ciclo(primo_ritardo=0, intervallo_ore=0, crea=crea))
    with pytest.raises(asyncio.CancelledError):
        await compito
    assert len(chiamate) == 2
