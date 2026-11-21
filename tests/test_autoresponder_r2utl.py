"""
tests/test_autoresponder_r2utl.py
=================================
Catalogo #128, giro r2utl: risposte automatiche con modo «finisce con» (UTL-060), maiuscole che contano (UTL-062),
utenti, canali e ruoli esclusi (UTL-064, UTL-065), modifica senza ricreare (UTL-066) e dettaglio (UTL-067).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import cogs.utility.autoresponder as modulo
from cogs.utility.autoresponder import AutoresponderCog
from core.autoresponder_logic import MAX_ESCLUSI, scegli_risposta, trigger_corrisponde
from core.repositories.autoresponder_repo import AutoresponderRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel


def test_utl_060_finisce_con_il_testo_a_fine_parola():
    """UTL-060: scatta solo se il messaggio finisce con il testo, e il testo comincia a inizio parola."""
    assert trigger_corrisponde("grazie", "finisce", "Ok, GRAZIE") is True
    assert trigger_corrisponde("grazie", "finisce", "grazie mille") is False
    assert trigger_corrisponde("grazie", "finisce", "ringrazie") is False  # a metà parola
    assert trigger_corrisponde("grazie", "finisce", "grazie") is True


def test_utl_062_le_maiuscole_contano_solo_se_richiesto():
    """UTL-062: di base no; con `maiuscole` sì, anche nelle espressioni regolari."""
    assert trigger_corrisponde("Ciao", "parziale", "ciao a tutti") is True
    assert trigger_corrisponde("Ciao", "parziale", "ciao a tutti", maiuscole=True) is False
    assert trigger_corrisponde("Ciao", "parziale", "dico Ciao", maiuscole=True) is True
    assert trigger_corrisponde("Ciao", "esatta", "ciao", maiuscole=True) is False
    assert trigger_corrisponde("c.ao", "regex", "CIAO") is True
    assert trigger_corrisponde("c.ao", "regex", "CIAO", maiuscole=True) is False


def _regola(**kw):
    base = dict(id=1, trigger="ciao", match_mode="parziale", channel_id=None, role_id=None, maiuscole=False,
                canali_esclusi=(), utenti_esclusi=(), ruoli_esclusi=())
    base.update(kw)
    return SimpleNamespace(**base)


def test_utl_064_065_utenti_canali_e_ruoli_esclusi_non_fanno_scattare():
    """UTL-064: utenti e canali esclusi; UTL-065: ruoli esclusi. Gli altri sì."""
    r = _regola(utenti_esclusi=(5,), canali_esclusi=(9,), ruoli_esclusi=(7,))
    assert scegli_risposta([r], "ciao", 1, set(), utente_id=5) is None
    assert scegli_risposta([r], "ciao", 9, set(), utente_id=6) is None
    assert scegli_risposta([r], "ciao", 1, {7}, utente_id=6) is None
    assert scegli_risposta([r], "ciao", 1, {8}, utente_id=6) is r


@pytest.fixture
def repo(clean_db):
    return AutoresponderRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_utl_066_067_repo_modifica_esclusioni_e_dettaglio(repo):
    """UTL-066: modifica senza ricreare (solo campi ammessi); UTL-067: il dettaglio ha esclusioni e maiuscole."""
    esito, n = await repo.create(1, "ciao", match_mode="parziale", response="Ehi", channel_id=None, role_id=None,
                                 ping_ruoli=False, created_by=1, maiuscole=True)
    assert esito == "ok"
    assert await repo.modifica(1, n, response="Nuova", match_mode="finisce", channel_id=4) is True
    assert await repo.modifica(2, n, response="x") is False  # un altro server
    with pytest.raises(ValueError):
        await repo.modifica(1, n, trigger="x; DROP TABLE autoresponders")
    r = await repo.get(1, n)
    assert (r.response, r.match_mode, r.channel_id, r.maiuscole) == ("Nuova", "finisce", 4, True)
    assert await repo.cambia_esclusione(1, n, "utente", 5, True, MAX_ESCLUSI) == [5]
    assert await repo.cambia_esclusione(1, n, "utente", 5, True, MAX_ESCLUSI) == [5]
    for i in range(30, 30 + MAX_ESCLUSI):
        await repo.cambia_esclusione(1, n, "canale", i, True, MAX_ESCLUSI)
    assert len((await repo.get(1, n)).canali_esclusi) == MAX_ESCLUSI
    assert await repo.cambia_esclusione(1, n, "utente", 5, False, MAX_ESCLUSI) == []
    assert await repo.cambia_esclusione(1, 999, "ruolo", 5, True, MAX_ESCLUSI) is None


@pytest.fixture
def cog(monkeypatch):
    c = AutoresponderCog(MagicMock())
    r = MagicMock()
    r.get = AsyncMock(return_value=SimpleNamespace(id=3, trigger="ciao", match_mode="parziale", response="Ehi {user}",
                                                   channel_id=None, role_id=2, maiuscole=False, canali_esclusi=[], utenti_esclusi=[5],
                                                   ruoli_esclusi=[]))
    r.modifica = AsyncMock(return_value=True)
    r.cambia_esclusione = AsyncMock(return_value=[1])
    monkeypatch.setattr(modulo, "autoresponder_repo", r)
    d = MagicMock()
    d.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", d)
    modulo._cache_regole.__init__(100)
    c.repo = r
    return c


@pytest.mark.asyncio
async def test_utl_066_modifica_rifiuta_il_resto_fuori_dal_modo_inizia_e_non_tocca_nulla(cog):
    """UTL-066: `{resto}` vale solo col modo «inizia»; il rifiuto non scrive."""
    i = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await cog.risposta_modifica.callback(cog, i, 3, risposta="Detto: {resto}")
    cog.repo.modifica.assert_not_awaited()
    await cog.risposta_modifica.callback(cog, i, 3, risposta="Detto: {resto}", modalita="inizia")
    cog.repo.modifica.assert_awaited_once()
    assert cog.repo.modifica.await_args.kwargs["match_mode"] == "inizia"


@pytest.mark.asyncio
async def test_utl_067_mostra_non_pinga_e_non_esce_dal_blocco(cog):
    """UTL-067: il dettaglio mostra modo, esclusi e testo grezzo con le menzioni spente."""
    cog.repo.get.return_value.response = "``` @everyone"
    i = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await cog.risposta_mostra.callback(cog, i, 3)
    corpo = i.response.send_message.await_args.args[0]
    assert "<@5>" in corpo and len(corpo) <= 2000
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].everyone is False
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].users is False


@pytest.mark.asyncio
async def test_utl_064_escludi_chiede_una_scelta_e_aggiorna_la_cache(cog):
    i = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await cog.risposta_escludi.callback(cog, i, 3)
    cog.repo.cambia_esclusione.assert_not_awaited()
    await cog.risposta_escludi.callback(cog, i, 3, utente=fake_member(8))
    cog.repo.cambia_esclusione.assert_awaited_once()
