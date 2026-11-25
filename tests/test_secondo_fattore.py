"""
tests/test_secondo_fattore.py
=============================
Blocco A, voce 12: eval, shell, cog load e aggiornamento a caldo vogliono un codice TOTP (core/secondo_fattore.py).
Senza segreto si rifiutano (solo da console); un codice vale una volta sola.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.utility.owner_premium as owner
from core import secondo_fattore as sf
from tests.support.discord_fakes import fake_interaction

SEGRETO = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # "12345678901234567890" in base32: il segreto di prova della RFC 6238


@pytest.fixture(autouse=True)
def _passo_pulito(monkeypatch):
    monkeypatch.setattr(sf, "_ultimo_passo_usato", 0)


def test_vettore_della_rfc_6238():
    # RFC 6238, appendice B (SHA-1): a 59 secondi il codice a 8 cifre è 94287082, quindi a 6 cifre 287082.
    assert sf.codice_al_passo(SEGRETO, 59 // 30) == "287082"
    assert sf.codice_al_passo(SEGRETO, 1111111109 // 30) == "081804"


def test_un_codice_giusto_vale_una_volta_sola():
    assert sf.verifica_codice(SEGRETO, "287082", adesso=59) is True
    assert sf.verifica_codice(SEGRETO, "287082", adesso=59) is False  # replay
    assert sf.verifica_codice(SEGRETO, "287082", adesso=70) is False  # stesso passo, ancora no


def test_codici_storti_segreti_storti():
    for codice in (None, "", "12345", "1234567", "abcdef", "２８７０８２", " 28708 "):
        assert sf.verifica_codice(SEGRETO, codice, adesso=59) is False
    assert sf.verifica_codice("", "287082", adesso=59) is False
    assert sf.verifica_codice("corto", "287082", adesso=59) is False
    assert sf.verifica_codice("!!!!!!!!!!!!!!!!!!!!", "287082", adesso=59) is False
    assert sf.verifica_codice(SEGRETO, "000000", adesso=59) is False


def test_si_accetta_il_passo_accanto_ma_non_uno_lontano():
    assert sf.verifica_codice(SEGRETO, sf.codice_al_passo(SEGRETO, 100), adesso=100 * 30 + 31) is True  # un passo dopo
    assert sf.verifica_codice(SEGRETO, sf.codice_al_passo(SEGRETO, 200), adesso=205 * 30) is False


def _cog():
    return owner.OwnerPremiumCog(SimpleNamespace(user=SimpleNamespace(id=1)))


async def test_senza_segreto_i_comandi_pericolosi_si_rifiutano(monkeypatch):
    monkeypatch.setattr(owner, "config", SimpleNamespace(OWNER_TOTP_SECRET="", OWNER_ID=5, ENABLE_EVAL=True, ENABLE_HOT_PATCH=True))
    i = fake_interaction()
    assert await owner._richiedi_secondo_fattore(i, "287082") is False
    assert "console" in i.response.send_message.call_args.args[0]


async def test_il_codice_sbagliato_si_rifiuta_e_quello_giusto_passa(monkeypatch):
    monkeypatch.setattr(owner, "config", SimpleNamespace(OWNER_TOTP_SECRET=SEGRETO))
    monkeypatch.setattr(owner.secondo_fattore.time, "time", lambda: 59)
    i = fake_interaction()
    assert await owner._richiedi_secondo_fattore(i, None) is False
    assert await owner._richiedi_secondo_fattore(i, "000000") is False
    assert await owner._richiedi_secondo_fattore(fake_interaction(), "287082") is True
    assert await owner._richiedi_secondo_fattore(fake_interaction(), "287082") is False  # già usato


@pytest.mark.parametrize("comando,argomenti", [
    ("eval_code", ("1+1",)), ("shell_command", ("echo ciao",)), ("owner_cog_load", ("cogs.qualcosa",)),
])
async def test_eval_shell_e_load_non_partono_senza_il_codice(monkeypatch, comando, argomenti):
    monkeypatch.setattr(owner, "config", SimpleNamespace(OWNER_TOTP_SECRET=SEGRETO, OWNER_ID=5, ENABLE_EVAL=True))
    monkeypatch.setattr(owner, "_is_owner", lambda i: True)
    cog = _cog()
    cog.bot.load_extension = AsyncMock()
    i = fake_interaction()
    await getattr(cog, comando).callback(cog, i, *argomenti)  # nessun codice
    cog.bot.load_extension.assert_not_awaited()
    assert "view" not in i.response.send_message.call_args.kwargs  # nessuna conferma di esecuzione


async def test_il_hot_patch_non_parte_senza_il_codice(monkeypatch):
    monkeypatch.setattr(owner, "config", SimpleNamespace(OWNER_TOTP_SECRET=SEGRETO, OWNER_ID=5, ENABLE_HOT_PATCH=True))
    cog = _cog()
    i = fake_interaction(user=SimpleNamespace(id=5))
    i.response.defer = AsyncMock()
    await cog._aggiorna_a_caldo(i, None, "main", None, None)
    i.response.defer.assert_not_awaited()  # si è fermato prima di scaricare qualsiasi cosa
    assert i.response.send_message.await_count == 1
