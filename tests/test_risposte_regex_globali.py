"""
tests/test_risposte_regex_globali.py
====================================
D69 B18 (UTL-061, 068, 069, 055): risposte automatiche con espressione regolare (RE2), «inizia con» col segnaposto
{resto}, svuota con conferma e risposte globali dell'owner (max 20, ogni server le può spegnere).
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import cogs.utility.autoresponder as modulo
from core.autoresponder_logic import MAX_GLOBALI, MAX_REGEX, regex_valida, resto_dopo, trigger_corrisponde
from core.repositories.autoresponder_repo import AutoresponderRepository
from core.repositories.autorisposte_globali_repo import AutorisposteGlobaliRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


def test_regex_valida_e_corrisponde():
    assert regex_valida(r"ciao\s+(mondo|a tutti)") is None
    assert regex_valida("(?=x)") == "sintassi" and regex_valida("(a") == "sintassi" and regex_valida("") == "lunghezza"
    assert regex_valida("a" * (MAX_REGEX + 1)) == "lunghezza"
    assert trigger_corrisponde(r"ciao\s+mondo", "regex", "Oh CIAO   Mondo!") and not trigger_corrisponde(r"ciao\s+mondo", "regex", "ciaomondo")
    assert not trigger_corrisponde("(a", "regex", "a")  # mai un'eccezione sul messaggio


def test_regex_con_backtracking_cattivo_non_blocca():
    inizio = time.monotonic()
    assert not trigger_corrisponde(r"(a+)+$", "regex", "a" * 1500 + "b")
    assert time.monotonic() - inizio < 2


def test_inizia_con_e_resto():
    assert trigger_corrisponde("!dado", "inizia", "!dado 3d6") and trigger_corrisponde("!dado", "inizia", "!DADO")
    assert not trigger_corrisponde("!dado", "inizia", "ciao !dado") and not trigger_corrisponde("dado", "inizia", "dadone")
    assert resto_dopo("!dado", "!dado   3d6 ") == "3d6" and resto_dopo("!dado", "!dado") == ""
    assert len(resto_dopo("a", "a " + "x" * 5000)) == 500


@pytest.fixture
def repo(clean_db):
    return AutoresponderRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_modi_nuovi_si_salvano_e_svuota_cancella_solo_il_server(repo):
    for i, modo in enumerate(("inizia", "regex")):
        assert (await repo.create(1, f"t{i}" + "x" * 150, match_mode=modo, response="r", channel_id=None, role_id=None, ping_ruoli=False, created_by=2))[0] == "ok"
    await repo.create(2, "altro", match_mode="esatta", response="r", channel_id=None, role_id=None, ping_ruoli=False, created_by=2)
    assert await repo.conta(1) == 2 and await repo.svuota(1) == 2 and await repo.conta(1) == 0 and await repo.conta(2) == 1


@pytest.mark.asyncio
async def test_globali_tetto_unicita_e_spegnimento(clean_db):
    r = AutorisposteGlobaliRepository(pool_provider=lambda: clean_db)
    for i in range(MAX_GLOBALI):
        assert await r.aggiungi(f"frase {i}", "ok", 1) == "ok"
    assert await r.aggiungi("altra", "ok", 1) == "pieno" and await r.aggiungi("FRASE 0", "ok", 1) == "pieno"
    assert await r.togli((await r.elenco())[0].id) is True
    assert await r.aggiungi("FRASE 1", "ok", 1) == "esiste"
    assert await r.spente_nel_server(7) is False
    await r.imposta_spente(7, True)
    assert await r.spente_nel_server(7) is True and await r.spente_nel_server(8) is False


@pytest.mark.asyncio
async def test_il_bot_usa_la_globale_solo_se_il_server_non_l_ha_spenta():
    cog = modulo.AutoresponderCog(MagicMock())
    modulo._cache_globali.delete(0)
    modulo._cache_spente.delete(4)
    glob = SimpleNamespace(id=3, innesco="buongiorno", risposta="salve")
    with patch.object(modulo, "autorisposte_globali_repo") as r:
        r.elenco = AsyncMock(return_value=[glob])
        r.spente_nel_server = AsyncMock(return_value=False)
        assert await cog._globale(4, "buongiorno a tutti") is glob
        assert await cog._globale(4, "boh") is None
        modulo._cache_spente.delete(4)
        r.spente_nel_server = AsyncMock(return_value=True)
        assert await cog._globale(4, "buongiorno") is None
    modulo._cache_globali.delete(0)
    modulo._cache_spente.delete(4)
