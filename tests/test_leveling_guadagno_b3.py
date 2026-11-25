"""
tests/test_leveling_guadagno_b3.py
==================================
#124 B3 (LIV-004, 006, 007, 017, 018, 021): archivio su PostgreSQL vero e cog con oggetti finti.
Formula (ricalcolo dei livelli), prefissi in una scrittura sola, comandi `/admin-livelli guadagno`,
XP dei messaggi e dei comandi slash.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.leveling.leveling as lev
from cogs.leveling.guadagno import GuadagnoCog
from cogs.leveling.leveling import LevelingCog
from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
from core.leveling_logic import ConfigLivelli, LevelingSettings, xp_for_level
from core.repositories.blacklist_repo import blacklist_repo
from core.repositories.leveling_repo import LevelingRepository, TextXpResult, leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_message, fake_text_channel
from tests.support.moduli import attiva_livelli
from tests.test_leveling_settings import cog_xp  # noqa: F401  (fixture del cog con archivio finto)

GUILD = 100
OWNER = 555
STAFF = 7
GESTORE = discord.Permissions(manage_guild=True)


@pytest.fixture
async def ambiente(monkeypatch, clean_db):
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    for repo in (leveling_repo, leveling_settings_repo):
        monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)
    yield GuadagnoCog(bot=None)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)


def _comando(cog, nome):
    return next(c for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None) if c.qualified_name == nome)


def _inter(utente=STAFF, permessi=GESTORE):
    return fake_interaction(guild=fake_guild(GUILD, "Casa", owner_id=OWNER), user=fake_member(utente), permissions=permessi)


def _scelta(valore):
    s = MagicMock()
    s.value = s.name = valore
    return s


def _testo(inter):
    c = inter.response.send_message.await_args or inter.followup.send.await_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# ---------------------------------------------------------------- LIV-004
@pytest.mark.asyncio
async def test_liv004_cambiare_formula_ricalcola_i_livelli(ambiente):
    cog = ambiente
    await leveling_repo.modifica_xp(GUILD, 1, "aggiungi", 1000, 0, "classica")
    await leveling_repo.modifica_xp(GUILD, 2, "aggiungi", 10, 0, "classica")
    inter = _inter()
    await _comando(cog, "admin-livelli-guadagno formula").callback(cog, inter, _scelta("costante"))
    assert (await leveling_repo.get_totals(GUILD, 1)).level == 1000 // 200
    assert (await leveling_repo.get_totals(GUILD, 2)).level == 0
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.formula == "costante"
    assert "**1**" in _testo(inter)  # solo il livello di una persona è cambiato


@pytest.mark.asyncio
async def test_liv004_il_guadagno_e_la_modifica_usano_la_formula_del_server(ambiente):
    await leveling_settings_repo.cambia_formula(GUILD, "costante")
    r = await leveling_repo.add_text_xp(GUILD, 9, amount=450, cooldown_seconds=10, formula="costante")
    assert r.new_level == 2 and r.leveled_up
    # Chi non passa la formula (i giochi con AI) usa quella del server.
    esito = await leveling_repo.modifica_xp(GUILD, 9, "livello", 5)
    assert esito.xp_dopo == xp_for_level(5, "costante") and esito.livello_dopo == 5


@pytest.mark.asyncio
async def test_liv004_due_cambi_insieme_restano_coerenti(ambiente):
    await leveling_repo.modifica_xp(GUILD, 1, "aggiungi", 5000, 0, "classica")
    await asyncio.gather(
        leveling_settings_repo.cambia_formula(GUILD, "lineare"),
        leveling_settings_repo.cambia_formula(GUILD, "costante"),
    )
    f = (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.formula
    assert (await leveling_repo.get_totals(GUILD, 1)).level == __import__("core.leveling_logic", fromlist=["x"]).level_for_xp(5000, 0, f)


@pytest.mark.asyncio
async def test_liv004_il_blocco_al_proprietario_ferma_il_cambio(ambiente):
    cog = ambiente
    await leveling_settings_repo.set_options(GUILD, blocca_azzeramento=True)
    inter = _inter()
    await _comando(cog, "admin-livelli-guadagno formula").callback(cog, inter, _scelta("lineare"))
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.formula == "classica"


@pytest.mark.asyncio
async def test_liv004_senza_permesso_non_cambia_niente(ambiente):
    cog = ambiente
    inter = _inter(permessi=discord.Permissions.none())
    await _comando(cog, "admin-livelli-guadagno formula").callback(cog, inter, _scelta("lineare"))
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.formula == "classica"


# ---------------------------------------------------------------- LIV-018
@pytest.mark.asyncio
async def test_liv018_prefissi_aggiunta_doppioni_e_tetto(ambiente):
    r = leveling_settings_repo
    assert await r.aggiungi_prefisso(GUILD, " ! ") == "aggiunto"
    assert await r.aggiungi_prefisso(GUILD, "!") == "presente"
    assert await r.aggiungi_prefisso(GUILD, "a b") == "non_valido"
    for n in range(9):
        assert await r.aggiungi_prefisso(GUILD, f"~{n}") == "aggiunto"
    assert await r.aggiungi_prefisso(GUILD, "?") == "pieno"
    assert len((await r.get_config(GUILD, fresco=True)).impostazioni.prefissi_ignorati) == 10
    assert await r.togli_prefisso(GUILD, "!") == 9
    assert await r.togli_prefisso(GUILD, None) == 0


@pytest.mark.asyncio
async def test_liv018_dodici_aggiunte_insieme_non_superano_il_tetto(ambiente):
    esiti = await asyncio.gather(*(leveling_settings_repo.aggiungi_prefisso(GUILD, f"#{n}") for n in range(12)))
    assert esiti.count("aggiunto") == 10 and esiti.count("pieno") == 2
    assert len((await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.prefissi_ignorati) == 10


@pytest.mark.asyncio
async def test_liv018_il_comando_mostra_l_elenco_senza_rompere_il_blocco_di_codice(ambiente):
    cog = ambiente
    cmd = _comando(cog, "admin-livelli-guadagno prefissi")
    await cmd.callback(cog, _inter(), _scelta("aggiungi"), "!")
    inter = _inter()
    await cmd.callback(cog, inter, _scelta("elenco"), None)
    assert "`!`" in _testo(inter)
    assert inter.response.send_message.await_args.kwargs["allowed_mentions"].everyone is False


@pytest.mark.asyncio
async def test_liv018_senza_prefisso_non_si_aggiunge(ambiente):
    cog = ambiente
    inter = _inter()
    await _comando(cog, "admin-livelli-guadagno prefissi").callback(cog, inter, _scelta("aggiungi"), None)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.prefissi_ignorati == ()


# ---------------------------------------------------------------- LIV-006, 007, 017, 021: comandi
@pytest.mark.asyncio
async def test_liv006_007_021_017_i_comandi_salvano_le_impostazioni(ambiente):
    cog = ambiente
    await _comando(cog, "admin-livelli-guadagno messaggi").callback(
        cog, _inter(), _scelta("parola"), 3, 20, 5, 100
    )
    await _comando(cog, "admin-livelli-guadagno comandi").callback(cog, _inter(), True)
    await _comando(cog, "admin-livelli-guadagno canali").callback(cog, _inter(), _scelta("solo_questi"))
    i = (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni
    assert (i.xp_modo, i.xp_per_parola, i.parole_max, i.bonus_impegno, i.impegno_caratteri) == ("parola", 3, 20, 5, 100)
    assert i.xp_comandi is True and i.canali_modo == "solo_questi"


@pytest.mark.asyncio
@pytest.mark.parametrize("nome,args", [
    ("formula", (None,)), ("messaggi", (None, None, None, None, None)), ("comandi", (True,)),
    ("prefissi", (None, None)), ("canali", (None,)),
])
async def test_i_comandi_senza_permesso_non_salvano(ambiente, nome, args):
    cog = ambiente
    inter = _inter(permessi=discord.Permissions.none())
    await _comando(cog, f"admin-livelli-guadagno {nome}").callback(cog, inter, *args)
    inter.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_liv021_elenco_vuoto_avvisa(ambiente):
    cog = ambiente
    inter = _inter()
    await _comando(cog, "admin-livelli-guadagno canali").callback(cog, inter, _scelta("solo_questi"))
    assert "vuoto" in _testo(inter)


# ---------------------------------------------------------------- messaggi nel cog
def _msg(testo="", canale_id=111, immagine=False):
    canale = fake_text_channel(channel_id=canale_id)
    canale.send = AsyncMock()
    autore = fake_member()
    autore.send = AsyncMock()
    m = fake_message(author=autore, channel=canale, content=testo)
    m.type = discord.MessageType.default
    allegato = MagicMock()
    allegato.content_type = "image/png" if immagine else "application/pdf"
    m.attachments = [allegato] if immagine else []
    return m


@pytest.mark.asyncio
async def test_liv018_un_messaggio_con_prefisso_di_un_altro_bot_non_da_xp(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(prefissi_ignorati=("!",)))
    await cog.on_message(_msg("!play musica"))
    repo_xp.add_text_xp.assert_not_awaited()
    await cog.on_message(_msg("ciao a tutti"))
    repo_xp.add_text_xp.assert_awaited_once()


@pytest.mark.asyncio
async def test_liv006_007_xp_a_parola_e_bonus_arrivano_all_archivio(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(
        xp_modo="parola", xp_per_parola=2, parole_max=10, bonus_impegno=5))
    await cog.on_message(_msg("ciao a tutti voi", immagine=True))
    assert repo_xp.add_text_xp.await_args.kwargs["amount"] == 3 * 2 + 5
    repo_xp.add_text_xp.reset_mock()
    await cog.on_message(_msg("ok"))  # nessuna parola: niente XP
    assert repo_xp.add_text_xp.await_args.kwargs["amount"] == 0


@pytest.mark.asyncio
async def test_liv021_solo_i_canali_dell_elenco_danno_xp(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(canali_modo="solo_questi"), canali_esclusi=frozenset({111}))
    await cog.on_message(_msg("ciao", canale_id=222))
    repo_xp.add_text_xp.assert_not_awaited()
    await cog.on_message(_msg("ciao", canale_id=111))
    repo_xp.add_text_xp.assert_awaited_once()


# ---------------------------------------------------------------- LIV-017: comandi slash
def _inter_comando(bot=False, canale_id=111):
    inter = fake_interaction(guild=fake_guild(GUILD, "Casa"), user=fake_member(5, bot=bot),
                             channel=fake_text_channel(channel_id=canale_id))
    inter.type = discord.InteractionType.application_command
    return inter


@pytest.mark.asyncio
async def test_liv017_di_base_i_comandi_non_danno_xp(cog_xp):  # noqa: F811
    cog, repo_xp, _, _ = cog_xp
    await cog.on_app_command_completion(_inter_comando(), MagicMock())
    repo_xp.add_text_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_liv017_acceso_da_xp_con_la_stessa_attesa_ma_non_ai_bot_ne_ai_canali_esclusi(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(xp_comandi=True, text_xp=20, text_cooldown_seconds=90),
        canali_esclusi=frozenset({999}),
    )
    await cog.on_app_command_completion(_inter_comando(bot=True), MagicMock())
    await cog.on_app_command_completion(_inter_comando(canale_id=999), MagicMock())
    repo_xp.add_text_xp.assert_not_awaited()
    await cog.on_app_command_completion(_inter_comando(), MagicMock())
    kw = repo_xp.add_text_xp.await_args.kwargs
    assert (kw["amount"], kw["cooldown_seconds"]) == (20, 90)


@pytest.mark.asyncio
async def test_liv017_un_comando_nei_messaggi_privati_non_da_xp(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(xp_comandi=True))
    inter = _inter_comando()
    inter.guild = None
    await cog.on_app_command_completion(inter, MagicMock())
    repo_xp.add_text_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_liv017_comando_e_messaggio_insieme_non_pagano_due_volte(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    prima, seconda = await asyncio.gather(
        repo.add_text_xp(GUILD, 3, amount=15, cooldown_seconds=60),
        repo.add_text_xp(GUILD, 3, amount=15, cooldown_seconds=60),
    )
    assert [prima.granted, seconda.granted].count(True) == 1
