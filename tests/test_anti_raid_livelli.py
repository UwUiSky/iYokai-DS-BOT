"""
tests/test_anti_raid_livelli.py
===============================
Anti-raid, livelli di allerta con nome (SIC-036): normale, allerta, alto, blocco.
Ogni livello stringe le regole attive senza toccare quelle scelte dal server;
si imposta a mano (con una durata) o scatta da solo quando comincia un raid.
"""

from datetime import timedelta

import pytest
from discord import app_commands

import cogs.security.anti_raid as modulo
from core import security_raid_state
from core.repositories.security_repo import _from_json, _to_json, _default_settings, security_repo
from core.security_join_logic import azzera_ingressi
from core.security_logic import LIVELLI_ALLERTA, AntiRaidConfig, config_con_livello, livello_attivo
from tests.test_anti_raid_f1 import (  # noqa: F401  (fixture condivise)
    GUILD_ID,
    INIZIO,
    _ingresso,
    _interazione,
    cog,
    db_finto,
    orologio,
    server,
)


@pytest.fixture(autouse=True)
def _memoria_pulita(monkeypatch):
    azzera_ingressi()
    security_raid_state._ultimo_ingresso.clear()
    monkeypatch.setattr(modulo, "PAUSA_AZIONI_SECONDI", 0)
    yield
    azzera_ingressi()
    security_raid_state._ultimo_ingresso.clear()


def _scelta(v):
    return app_commands.Choice(name=v, value=v)


def test_i_livelli_stringono_senza_allargare():
    base = AntiRaidConfig(enabled=True, join_rate_max=20, min_account_age_seconds=86400 * 30)
    assert LIVELLI_ALLERTA == ("normale", "allerta", "alto", "blocco")
    assert config_con_livello(base, "normale") == base
    allerta = config_con_livello(base, "allerta")
    alto = config_con_livello(base, "alto")
    blocco = config_con_livello(base, "blocco")
    assert allerta.join_rate_max == 10 > alto.join_rate_max == 5 > blocco.join_rate_max == 2
    # Un'età minima già alta del server non scende.
    assert allerta.min_account_age_seconds == base.min_account_age_seconds
    assert alto.retroattivo and alto.account_vicini_minimo == 3 and alto.nomi_simili_minimo == 3
    # Una soglia già bassa non scende sotto 2.
    assert config_con_livello(AntiRaidConfig(join_rate_max=3), "blocco").join_rate_max == 2
    # Quello che il server ha scelto di più forte resta.
    scelto = AntiRaidConfig(account_vicini_minimo=2)
    assert config_con_livello(scelto, "alto").account_vicini_minimo == 2


def test_livello_scaduto_vale_normale():
    cfg = AntiRaidConfig(livello="alto", livello_fino=1000)
    assert livello_attivo(cfg, 999) == "alto"
    assert livello_attivo(cfg, 1000) == "normale"
    assert livello_attivo(AntiRaidConfig(livello="alto", livello_fino=0), 10**10) == "alto"
    assert livello_attivo(AntiRaidConfig(livello="boh"), 0) == "normale"


async def test_livello_si_salva_e_sopravvive_al_json(cog):
    base = _default_settings(1)
    nuove = modulo._replace(base, livello="alto", livello_fino=5, livello_al_raid="allerta", livello_al_raid_ore=3)
    letto = _from_json(1, _to_json(nuove)).anti_raid
    assert (letto.livello, letto.livello_fino, letto.livello_al_raid, letto.livello_al_raid_ore) == ("alto", 5, "allerta", 3)


async def test_livello_a_mano_con_durata(cog, orologio):
    await cog.join_rate.callback(cog, _interazione(), 10, 60)
    await cog.livello.callback(cog, _interazione(), _scelta("alto"), 2, None)
    r = (await security_repo.get_settings(GUILD_ID)).anti_raid
    assert r.livello == "alto" and r.livello_fino == int((INIZIO + timedelta(hours=2)).timestamp())
    await cog.livello.callback(cog, _interazione(), _scelta("normale"), None, None)
    r = (await security_repo.get_settings(GUILD_ID)).anti_raid
    assert r.livello == "normale" and r.livello_fino == 0


async def test_senza_durata_il_livello_dura_fino_al_cambio(cog):
    await cog.livello.callback(cog, _interazione(), _scelta("allerta"), None, None)
    assert (await security_repo.get_settings(GUILD_ID)).anti_raid.livello_fino == 0


async def test_livello_alto_fa_scattare_il_raid_con_meno_ingressi(cog, server, orologio):
    await cog.join_rate.callback(cog, _interazione(), 20, 60)
    await cog.livello.callback(cog, _interazione(), _scelta("alto"), None, None)  # soglia 20 -> 5
    membri = [_ingresso(server, 200 + n) for n in range(6)]
    for n, m in enumerate(membri):  # nomi ed età diversi: conta solo la soglia
        m.name = ["Giulia", "Marco", "xQz", "Lupo", "Ombra", "Tigre"][n]
        m.created_at = INIZIO - timedelta(days=400 + 90 * n)
    for m in membri[:5]:
        await cog.on_member_join(m)
    assert not security_raid_state.raid_in_corso(GUILD_ID)
    await cog.on_member_join(membri[5])
    assert security_raid_state.raid_in_corso(GUILD_ID)
    membri[5].add_roles.assert_awaited_once()


async def test_a_livello_normale_gli_stessi_ingressi_non_sono_un_raid(cog, server):
    await cog.join_rate.callback(cog, _interazione(), 10, 60)
    for n in range(6):
        await cog.on_member_join(_ingresso(server, 300 + n))
    assert not security_raid_state.raid_in_corso(GUILD_ID)


async def test_livello_scaduto_non_stringe_piu(cog, server, orologio):
    await cog.join_rate.callback(cog, _interazione(), 10, 60)
    await cog.livello.callback(cog, _interazione(), _scelta("alto"), 1, None)
    orologio(hours=2)
    for n in range(6):
        await cog.on_member_join(_ingresso(server, 400 + n))
    assert not security_raid_state.raid_in_corso(GUILD_ID)


async def test_regola_automatica_alza_il_livello_all_inizio_del_raid(cog, server, orologio):
    await cog.livello.callback(cog, _interazione(), None, 4, _scelta("alto"))
    r = (await security_repo.get_settings(GUILD_ID)).anti_raid
    assert r.livello == "normale" and r.livello_al_raid == "alto" and r.livello_al_raid_ore == 4
    for n in range(3):  # soglia 2 del fixture: il terzo ingresso è il raid
        await cog.on_member_join(_ingresso(server, 500 + n))
    r = (await security_repo.get_settings(GUILD_ID)).anti_raid
    assert r.livello == "alto"
    assert r.livello_fino == int((INIZIO + timedelta(hours=4)).timestamp())


async def test_regola_automatica_non_abbassa_un_livello_gia_piu_alto(cog, server, orologio):
    await cog.livello.callback(cog, _interazione(), _scelta("blocco"), None, None)
    await cog.livello.callback(cog, _interazione(), None, None, _scelta("allerta"))
    for n in range(3):
        await cog.on_member_join(_ingresso(server, 600 + n))
    assert (await security_repo.get_settings(GUILD_ID)).anti_raid.livello == "blocco"


async def test_solo_chi_gestisce_cambia_il_livello(cog):
    estraneo = _interazione()
    estraneo.user.id = 9999
    estraneo.user.guild_permissions.administrator = True
    estraneo.guild.owner_id = 1
    await cog.livello.callback(cog, estraneo, _scelta("blocco"), None, None)
    assert (await security_repo.get_settings(GUILD_ID)).anti_raid.livello == "normale"


async def test_status_mostra_il_livello(cog):
    await cog.livello.callback(cog, _interazione(), _scelta("allerta"), None, None)
    i = _interazione()
    await cog.status.callback(cog, i)
    testo = i.response.send_message.call_args.args[0] if i.response.send_message.call_args.args else str(
        i.response.send_message.call_args.kwargs
    )
    assert "allerta" in testo.lower()
