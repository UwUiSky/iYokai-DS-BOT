"""
tests/test_automod_nomi_pulizia.py
==================================
MOD-102 (#115): dehoist e simboli nei nomi. Spenti di base; si applicano all'ingresso e al cambio nome; il giro
una tantum ha tetto e non tocca bot, proprietario ed esenti. Logica pura e cog con oggetti finti.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.automod import parole_odio
from core import automod_nomi_logic as nomi
from core.automod_parole_opzioni import OpzioniParole

SOST = "Nome rimosso"
P = lambda n, **k: nomi.pulisci_nome(n, sostitutivo=SOST, **{"dehoist": False, "simboli": False, **k})


def test_dehoist_toglie_i_simboli_iniziali():
    assert P("!!! Pippo", dehoist=True) == "Pippo" and P("~.-Anna", dehoist=True) == "Anna"
    assert P("Pippo", dehoist=True) is None  # gia' pulito: nessun cambio
    assert P("!!!", dehoist=True) == SOST  # non resta niente
    assert P("!!! Pippo") is None  # spento: non tocca


def test_simboli_lettere_decorative_invisibili_e_testo_impilato():
    assert P("𝓟𝓲𝓹𝓹𝓸", simboli=True) == "Pippo"
    assert P("Pi​ppo", simboli=True) == "Pippo"
    zalgo = "P" + "̀" * 20 + "ippo"
    assert P(zalgo, simboli=True) == "P̀̀ippo"
    assert P("Zoë", simboli=True) is None and P("Müller", simboli=True) is None  # gli accenti veri restano


def test_idempotente_e_tetto_32():
    primo = P("!!!" + "a" * 50, dehoist=True)
    assert len(primo) == 32 and P(primo, dehoist=True) is None


def _membro(nick=None, global_name="Pippo", bot=False):
    m = MagicMock()
    m.nick, m.global_name, m.name, m.bot, m.id = nick, global_name, "pippo", bot, 5
    m.guild = SimpleNamespace(id=1, owner_id=99)
    m.edit = AsyncMock()
    return m


@pytest.fixture
def cog_env(monkeypatch):
    def prepara(opz):
        filtro = MagicMock()
        filtro.vuoto.return_value = True
        monkeypatch.setattr(parole_odio.opzioni_parole, "filtro_del_server", AsyncMock(return_value=(filtro, opz)))
        monkeypatch.setattr(parole_odio.db, "is_module_active_for_guild", AsyncMock(return_value=True))
        monkeypatch.setattr(parole_odio.automod_advanced_repo, "get_settings", AsyncMock(return_value=SimpleNamespace(log_channel_id=None)))
        monkeypatch.setattr(parole_odio, "is_member_exempt", lambda *a: False)
        monkeypatch.setattr(parole_odio.router, "destinazione", AsyncMock(return_value=None))

    return prepara


async def test_di_base_non_cambia_niente(cog_env):
    cog_env(OpzioniParole())
    m = _membro(global_name="!!Pippo")
    assert await parole_odio.controlla_nome(m) is None
    m.edit.assert_not_awaited()


async def test_dehoist_acceso_cambia_il_nickname_e_poi_si_ferma(cog_env):
    cog_env(OpzioniParole(dehoist=True))
    m = _membro(global_name="!!Pippo")
    assert await parole_odio.controlla_nome(m) is not None
    m.edit.assert_awaited_once()
    assert m.edit.await_args.kwargs["nick"] == "Pippo"
    m2 = _membro(nick="Pippo", global_name="!!Pippo")  # il bot ha gia' ripulito: nessun giro a vuoto
    assert await parole_odio.controlla_nome(m2) is None


async def test_bot_e_proprietario_non_si_toccano(cog_env):
    cog_env(OpzioniParole(dehoist=True, simboli=True))
    assert await parole_odio.controlla_nome(_membro(global_name="!!x", bot=True)) is None
    prop = _membro(global_name="!!x")
    prop.id = 99
    assert await parole_odio.controlla_nome(prop) is None


async def test_giro_ha_il_tetto_e_salta_chi_non_serve(cog_env, monkeypatch):
    cog_env(OpzioniParole(dehoist=True))
    monkeypatch.setattr(parole_odio, "MAX_MEMBRI_GIRO", 3)
    monkeypatch.setattr(parole_odio, "PAUSA_GIRO", 0)
    monkeypatch.setattr(parole_odio.opzioni_parole, "leggi", AsyncMock(return_value=OpzioniParole(dehoist=True)))
    membri = [_membro(global_name=f"!!n{i}") for i in range(10)] + [_membro(global_name="ok", bot=False)]
    for i, m in enumerate(membri):
        m.id = 100 + i
    guild = SimpleNamespace(id=1, owner_id=99, members=membri)
    cog = parole_odio.ParoleOdioCog(bot=MagicMock())
    assert await cog._giro_pulizia(guild) == 3
