"""
tests/test_automod_inviti_parole.py
===================================
Parole vietate con gli asterischi scelti dal comando (AMD-013) e inviti
da lasciar passare nella regola anti-invito (AMD-026, AMD-027): le
eccezioni dell'admin restano, quelle di iYokai seguono la configurazione.
Il server è finto ma "ricorda" le modifiche; il database è vero.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord import app_commands

import cogs.automod.automod as modulo_automod
import cogs.moderation._shared as modulo_shared
from core.automod_native_logic import (
    MAX_CODICI_INVITO,
    codice_da_testo,
    codici_ammessi,
    parola_con_modo,
    stessa_parola,
    voci_per_codici,
)
from core.automod_sync import DesiredRule, ExistingRule, SyncActionType, compute_sync_plan
from core.database import Database
from core.repositories.automod_repo import AutomodRepository
from tests.support.discord_fakes import fake_guild, fake_interaction

GUILD_ID = 666


# --------------------------------------------------------------------
# Logica semplice
# --------------------------------------------------------------------
@pytest.mark.parametrize(
    "modo, atteso",
    [("intera", "spam"), ("dentro", "*spam*"), ("inizio", "spam*"), ("fine", "*spam")],
)
def test_parola_con_modo_mette_gli_asterischi(modo, atteso):
    assert parola_con_modo("spam", modo) == atteso


def test_parola_con_modo_toglie_gli_asterischi_scritti_a_mano():
    assert parola_con_modo("*spam*", "inizio") == "spam*"


def test_parola_con_modo_rifiuta_oltre_60_caratteri():
    assert len(parola_con_modo("a" * 60, "intera")) == 60
    with pytest.raises(ValueError, match="60"):
        parola_con_modo("a" * 59, "dentro")


def test_parola_vuota_rifiutata():
    with pytest.raises(ValueError):
        parola_con_modo("***", "dentro")


def test_stessa_parola_senza_asterischi_vale_per_tutte_le_forme():
    assert all(stessa_parola(v, "spam") for v in ("spam", "*spam*", "spam*", "*spam"))
    assert not stessa_parola("*spam*", "spam*")
    assert stessa_parola("spam*", "spam*")


def test_codice_da_testo():
    assert codice_da_testo("https://discord.gg/abc123") == "abc123"
    assert codice_da_testo("discord.com/invite/XyZ-9") == "XyZ-9"
    assert codice_da_testo("abc123") == "abc123"
    assert codice_da_testo("non un invito!") is None


def test_codici_ammessi_senza_doppioni_e_con_tetto():
    codici, troncato = codici_ammessi(("a1", "b2"), ("b2", "c3"))
    assert codici == ("a1", "b2", "c3") and not troncato
    molti = tuple(f"cod{n}" for n in range(MAX_CODICI_INVITO + 2))
    codici, troncato = codici_ammessi((), molti)
    assert len(codici) == MAX_CODICI_INVITO and troncato
    assert len(voci_per_codici(codici)) <= 25


def test_piano_eccezioni_tre_vie_conserva_quelle_dell_admin():
    esistente = ExistingRule(
        name="r",
        regex_patterns=("x",),
        allow_list=("discord.gg/admin", "discord.gg/vecchio"),
    )
    voluta = DesiredRule(
        name="r",
        regex_patterns=("x",),
        allow_list=("discord.gg/nuovo",),
        previously_synced_allow=("discord.gg/vecchio",),
    )
    (azione,) = compute_sync_plan([esistente], [voluta])
    assert azione.action == SyncActionType.UPDATE
    assert azione.final_allow_list == ("discord.gg/admin", "discord.gg/nuovo")
    assert azione.own_allow_list == ("discord.gg/nuovo",)


# --------------------------------------------------------------------
# Comandi e sincronizzazione
# --------------------------------------------------------------------
@pytest.fixture
def repo(clean_db, monkeypatch) -> AutomodRepository:
    vero = AutomodRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo_automod, "automod_repo", vero)
    return vero


@pytest.fixture
def cog(repo, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = None
    monkeypatch.setattr(modulo_shared, "db", db_finto)
    monkeypatch.setattr(modulo_automod, "db", db_finto)
    return modulo_automod.AutomodCog(bot=None)


def _regola_finta(nome: str, **campi_trigger) -> MagicMock:
    regola = create_autospec(discord.AutoModRule, instance=True)
    regola.name = nome
    regola.trigger = discord.AutoModTrigger(
        type=discord.AutoModRuleTriggerType.keyword, **campi_trigger
    )

    async def _edit(**kwargs):
        if "trigger" in kwargs:
            regola.trigger = kwargs["trigger"]
        return regola

    regola.edit.side_effect = _edit
    return regola


def _server(regole: list, inviti: list[str] | None = None):
    server = fake_guild(guild_id=GUILD_ID)
    server.fetch_automod_rules.return_value = regole
    server.invites.return_value = [MagicMock(code=c) for c in (inviti or [])]
    return server


def _scelta(valore: str) -> app_commands.Choice:
    return app_commands.Choice(name=valore, value=valore)


async def test_parole_add_con_modo_salva_la_voce_con_gli_asterischi(cog, repo):
    server = _server([])
    await cog.badword_add.callback(cog, fake_interaction(guild=server), "spam", _scelta("dentro"))
    await cog.badword_add.callback(cog, fake_interaction(guild=server), "truffa", None)

    config = await repo.get_config(GUILD_ID)
    assert config.custom_badwords == ("*spam*", "truffa")
    keywords = server.create_automod_rule.call_args.kwargs["trigger"].keyword_filter
    assert keywords == ["*spam*", "truffa"]


async def test_parole_add_rifiuta_se_con_gli_asterischi_supera_60(cog, repo):
    interazione = fake_interaction(guild=_server([]))
    await cog.badword_add.callback(cog, interazione, "a" * 59, _scelta("dentro"))

    assert (await repo.get_config(GUILD_ID)).custom_badwords == ()
    assert "60" in interazione.response.send_message.call_args.args[0]


async def test_parole_remove_toglie_tutte_le_forme(cog, repo):
    await repo.add_badword(GUILD_ID, "*spam*")
    await cog.badword_remove.callback(cog, fake_interaction(guild=_server([])), "spam")

    assert (await repo.get_config(GUILD_ID)).custom_badwords == ()


async def test_invites_permetti_mette_i_codici_nelle_eccezioni(cog, repo):
    regola = _regola_finta(
        modulo_automod.RULE_NAME_INVITES,
        regex_patterns=list(modulo_automod.INVITE_REGEX_PATTERNS),
        allow_list=["discord.gg/admin"],
    )
    server = _server([regola])

    await cog.invites.callback(
        cog, fake_interaction(guild=server), True, "https://discord.gg/amici", None, None
    )

    assert (await repo.get_config(GUILD_ID)).invite_allowed == ("amici",)
    allow = regola.trigger.allow_list
    assert allow[0] == "discord.gg/admin"
    assert set(voci_per_codici(("amici",))) <= set(allow)


async def test_invites_togli_toglie_solo_le_nostre_voci(cog, repo):
    regola = _regola_finta(
        modulo_automod.RULE_NAME_INVITES,
        regex_patterns=list(modulo_automod.INVITE_REGEX_PATTERNS),
        allow_list=["discord.gg/admin"],
    )
    server = _server([regola])
    await cog.invites.callback(cog, fake_interaction(guild=server), True, "amici", None, None)
    await cog.invites.callback(cog, fake_interaction(guild=server), None, None, "amici", None)

    assert (await repo.get_config(GUILD_ID)).invite_allowed == ()
    assert regola.trigger.allow_list == ["discord.gg/admin"]


async def test_invites_rifiuta_il_nono_codice(cog, repo):
    interazione = fake_interaction(guild=_server([]))
    for n in range(MAX_CODICI_INVITO):
        await cog.invites.callback(cog, fake_interaction(guild=_server([])), True, f"cod{n}", None, None)

    await cog.invites.callback(cog, interazione, None, "uno-di-troppo", None, None)

    assert len((await repo.get_config(GUILD_ID)).invite_allowed) == MAX_CODICI_INVITO
    assert str(MAX_CODICI_INVITO) in interazione.response.send_message.call_args.args[0]


async def test_invites_senza_opzioni_chiede_di_sceglierne_una(cog):
    interazione = fake_interaction(guild=_server([]))
    await cog.invites.callback(cog, interazione, None, None, None, None)
    interazione.response.send_message.assert_awaited_once()


async def test_invites_propri_legge_gli_inviti_del_server(cog, repo):
    server = _server([], inviti=["mio1", "mio2"])
    await cog.invites.callback(cog, fake_interaction(guild=server), True, None, None, True)

    allow = server.create_automod_rule.call_args.kwargs["trigger"].allow_list
    assert set(allow) == set(voci_per_codici(("mio1", "mio2")))


async def test_invito_nuovo_o_tolto_aggiorna_le_eccezioni(cog, repo, monkeypatch):
    monkeypatch.setattr(modulo_automod, "PAUSA_SYNC_INVITI", 0)
    regola = _regola_finta(
        modulo_automod.RULE_NAME_INVITES, regex_patterns=list(modulo_automod.INVITE_REGEX_PATTERNS)
    )
    server = _server([regola], inviti=["mio1"])
    await cog.invites.callback(cog, fake_interaction(guild=server), True, None, None, True)
    assert set(regola.trigger.allow_list) == set(voci_per_codici(("mio1",)))

    server.invites.return_value = [MagicMock(code="mio1"), MagicMock(code="mio2")]
    await cog.on_invite_create(MagicMock(guild=server))
    assert set(regola.trigger.allow_list) == set(voci_per_codici(("mio1", "mio2")))

    server.invites.return_value = [MagicMock(code="mio2")]
    await cog.on_invite_delete(MagicMock(guild=server))
    assert set(regola.trigger.allow_list) == set(voci_per_codici(("mio2",)))


async def test_invito_nuovo_senza_propri_non_tocca_nulla(cog, repo, monkeypatch):
    monkeypatch.setattr(modulo_automod, "PAUSA_SYNC_INVITI", 0)
    server = _server([])
    await cog.on_invite_create(MagicMock(guild=server))
    server.fetch_automod_rules.assert_not_awaited()


# --------------------------------------------------------------------
# Violazioni di un utente (AMD-062) e una sola da togliere (AMD-065)
# --------------------------------------------------------------------
async def test_violazioni_in_pagine_e_togli_una(cog, clean_db, monkeypatch):
    from core.repositories.automod_advanced_repo import automod_advanced_repo
    from tests.support.discord_fakes import fake_member

    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    for _ in range(12):
        await automod_advanced_repo.log_action(GUILD_ID, 42, 7, "anti_caps", ("delete",), "x")
    await automod_advanced_repo.log_action(GUILD_ID + 1, 42, 7, "anti_link", ("delete",), "altro server")
    server = fake_guild(guild_id=GUILD_ID)
    utente = fake_member(user_id=42)

    prima = fake_interaction(guild=server)
    await cog.violazioni.callback(cog, prima, utente, 1)
    testo = prima.response.send_message.call_args.args[0]
    assert "(12)" in testo and "pagina 1 di 2" in testo and testo.count("anti_caps") == 10

    seconda = fake_interaction(guild=server)
    await cog.violazioni.callback(cog, seconda, utente, 2)
    assert seconda.response.send_message.call_args.args[0].count("anti_caps") == 2

    righe, _ = await automod_advanced_repo.get_user_actions(GUILD_ID, 42, 1)
    togli = fake_interaction(guild=server)
    await cog.violazione_togli.callback(cog, togli, righe[0]["id"])
    assert "tolta" in togli.response.send_message.call_args.args[0]
    assert (await automod_advanced_repo.get_user_actions(GUILD_ID, 42, 1))[1] == 11


async def test_togli_non_tocca_altri_server_e_numeri_inesistenti(cog, clean_db, monkeypatch):
    from core.repositories.automod_advanced_repo import automod_advanced_repo

    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    await automod_advanced_repo.log_action(GUILD_ID + 1, 42, 7, "anti_link", ("delete",), "altro")
    altro, _ = await automod_advanced_repo.get_user_actions(GUILD_ID + 1, 42, 1)

    risposta = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    await cog.violazione_togli.callback(cog, risposta, altro[0]["id"])

    assert "Non c'è" in risposta.response.send_message.call_args.args[0]
    assert (await automod_advanced_repo.get_user_actions(GUILD_ID + 1, 42, 1))[1] == 1
