"""
tests/test_anti_nuke_117.py
===========================
Catalogo #117, anti-nuke:
- SIC-001  seconda soglia (un'ora) che prende l'attacco lento;
- SIC-002  quarantena come punizione, con fallback sul toglie-ruoli;
- SIC-017  registro degli attacchi (/security antinuke casi, rilascia);
- SIC-018  extra owner e fidati: chi puo' cambiare la lista;
- SIC-019  fiducia limitata a un tipo di azione o a una categoria di canali;
- SIC-020  esenzione di un webhook.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import cogs.security.anti_nuke as modulo
import core.security_quarantine as quarantena
from core.repositories.security_repo import security_repo
from core.security_logic import NUKE_CATEGORY_CHANNEL, NUKE_CATEGORY_WEBHOOK, voci_fiducia
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)
from tests.test_anti_nuke_f1 import (  # noqa: F401  (fixture condivise)
    AUTORE_ID,
    BOT_ID,
    GUILD_ID,
    _canale_cancellato,
    _interazione,
    _server,
    _voce,
    attese,
    cog,
    db_finto,
)

PROPRIETARIO_ID = 555


def _scelta(valore: str, nome: str = "x") -> app_commands.Choice:
    return app_commands.Choice(name=nome, value=valore)


def _come(utente_id: int) -> MagicMock:
    """Interazione di un utente che non e' (necessariamente) il proprietario."""
    return fake_interaction(
        guild=fake_guild(guild_id=GUILD_ID, owner_id=PROPRIETARIO_ID),
        user=fake_member(user_id=utente_id),
    )


def _risposta(interazione) -> str:
    chiamata = interazione.response.send_message.call_args
    return (chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")) or ""


# ====================================================================
# SIC-001 — seconda soglia
# ====================================================================
async def test_attacco_lento_supera_la_soglia_oraria(cog):
    # Al minuto ne servono 100, all'ora 2: tre cancellazioni in una finestra lunga.
    await cog.limits.callback(cog, _interazione(), _scelta(NUKE_CATEGORY_CHANNEL), 100, 60, 2)
    await cog.punish_action.callback(cog, _interazione(), _scelta("strip_roles"))
    ruolo = fake_role(role_id=52, name="Admin", position=5)
    autore = fake_member(user_id=AUTORE_ID, roles=[ruolo])
    server = _server(autore, [[]])

    for numero in (1, 2):
        assert await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, f"azione {numero}") is None
    autore.edit.assert_not_awaited()
    assert await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "azione 3") is not None
    autore.edit.assert_awaited_once()


async def test_senza_soglia_oraria_non_scatta(cog):
    await cog.limits.callback(cog, _interazione(), _scelta(NUKE_CATEGORY_CHANNEL), 100, 60, 0)
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[]])
    for numero in range(5):
        assert await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, f"azione {numero}") is None


# ====================================================================
# SIC-002 — quarantena
# ====================================================================
async def test_quarantena_di_default_toglie_i_ruoli_e_salva_il_caso(cog, monkeypatch):
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"))
    finta = AsyncMock(return_value=quarantena.EsitoQuarantena(True, [52, 53]))
    monkeypatch.setattr(modulo, "metti_in_quarantena", finta)
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[]])

    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "azione")

    finta.assert_awaited_once()
    assert finta.call_args.kwargs["togli_ruoli"] is True
    caso = await security_repo.get_nuke_case(GUILD_ID, 1)
    assert caso.removed_role_ids == (52, 53)
    assert "quarantena" in caso.punishment
    autore.edit.assert_not_awaited()


async def test_se_la_quarantena_non_riesce_si_tolgono_i_ruoli(cog, monkeypatch):
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"))
    monkeypatch.setattr(modulo, "metti_in_quarantena", AsyncMock(return_value=quarantena.EsitoQuarantena(False)))
    booster = fake_role(role_id=51, name="Booster", managed=True)
    admin = fake_role(role_id=52, name="Admin", position=5)
    autore = fake_member(user_id=AUTORE_ID, roles=[booster, admin])
    server = _server(autore, [[]])

    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "azione")

    assert autore.edit.call_args.kwargs["roles"] == [booster]
    assert (await security_repo.get_nuke_case(GUILD_ID, 1)).removed_role_ids == (52,)


async def test_metti_in_quarantena_toglie_gli_altri_ruoli_e_aggiunge_il_ruolo(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    quarantined = fake_role(role_id=900, name="Quarantined")
    booster = fake_role(role_id=51, name="Booster", managed=True)
    admin = fake_role(role_id=52, name="Admin", position=5)
    server = fake_guild(guild_id=GUILD_ID)
    server.roles = [quarantined]
    server.channels = []
    server.get_role = MagicMock(side_effect=lambda rid: quarantined if rid == 900 else None)
    membro = fake_member(user_id=AUTORE_ID, roles=[booster, admin])
    membro.guild = server
    from core.security_logic import AntiNukeConfig, AntiRaidConfig
    from core.repositories.security_repo import SecuritySettings
    await security_repo.save_settings(
        SecuritySettings(GUILD_ID, AntiRaidConfig(), AntiNukeConfig(), 900, None)
    )

    esito = await quarantena.metti_in_quarantena(membro, "motivo", togli_ruoli=True)

    assert esito.completo is True
    assert esito.ruoli_tolti == [52]
    assert membro.edit.call_args.kwargs["roles"] == [booster, quarantined]


# ====================================================================
# SIC-017 — registro degli attacchi
# ====================================================================
async def test_la_violazione_scrive_il_caso_e_lo_dice_nell_avviso(cog):
    await cog.punish_action.callback(cog, _interazione(), _scelta("strip_roles"))
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[]])
    avvisi = []
    server.owner.send = AsyncMock(side_effect=lambda **kw: avvisi.append(kw))

    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "azione")

    caso = await security_repo.get_nuke_case(GUILD_ID, 1)
    assert caso.actor_id == AUTORE_ID and caso.category == NUKE_CATEGORY_CHANNEL
    assert "caso #1" in avvisi[0]["embed"].title


async def test_casi_elenco_e_dettaglio(cog):
    await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "cancellati 4 canali", "quarantena", (52,))
    elenco = _interazione()
    await cog.casi.callback(cog, elenco, None, 1)
    assert "#1" in elenco.response.send_message.call_args.kwargs["embed"].description

    dettaglio = _interazione()
    await cog.casi.callback(cog, dettaglio, 1, 1)
    campi = {c.name: c.value for c in dettaglio.response.send_message.call_args.kwargs["embed"].fields}
    assert "<@&52>" in campi["Ruoli tolti"]

    assenti = _interazione()
    await cog.casi.callback(cog, assenti, 9, 1)
    assert "non esiste" in _risposta(assenti)


async def test_rilascia_rimette_i_ruoli_una_volta_sola(cog):
    numero = await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "x", "quarantena", (52,))
    ruolo = fake_role(role_id=52, name="Admin", position=2)
    autore = fake_member(user_id=AUTORE_ID, roles=[])

    def _interazione_con_server():
        interazione = _interazione()
        interazione.guild.get_member = MagicMock(return_value=autore)
        interazione.guild.get_role = MagicMock(side_effect=lambda i: ruolo if i == 52 else None)
        interazione.guild.me.top_role = fake_role(role_id=9, position=10)
        autore.guild = interazione.guild
        return interazione

    await cog.rilascia.callback(cog, _interazione_con_server(), numero)
    assert ruolo in autore.edit.call_args.kwargs["roles"]
    assert (await security_repo.get_nuke_case(GUILD_ID, numero)).released_at is not None

    di_nuovo = _interazione_con_server()
    await cog.rilascia.callback(cog, di_nuovo, numero)
    assert "già" in di_nuovo.followup.send.call_args.args[0]
    autore.edit.assert_awaited_once()


# ====================================================================
# SIC-018 — chi puo' cambiare la lista dei fidati
# ====================================================================
async def test_un_amministratore_qualsiasi_non_puo_esentarsi(cog):
    interazione = _come(777)
    await cog.trusted_add.callback(cog, interazione, "777")
    assert "Solo il proprietario" in _risposta(interazione)
    assert (await security_repo.get_settings(GUILD_ID)).anti_nuke.trusted_ids == ()


async def test_un_amministratore_non_puo_spegnere_l_anti_nuke(cog):
    interazione = _come(777)
    await cog.enable.callback(cog, interazione, False)
    assert "Solo il proprietario" in _risposta(interazione)
    assert (await security_repo.get_settings(GUILD_ID)).anti_nuke.enabled is True


async def test_il_proprietario_nomina_un_extra_owner_che_poi_gestisce_i_fidati(cog):
    await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), "888", None, _scelta("extra_owner"))
    n = (await security_repo.get_settings(GUILD_ID)).anti_nuke
    assert [(v.target_id, v.level) for v in n.trust_entries] == [(888, "extra_owner")]

    # L'extra owner aggiunge un fidato semplice...
    await cog.trusted_add.callback(cog, _come(888), "42")
    assert {v.target_id for v in voci_fiducia((await security_repo.get_settings(GUILD_ID)).anti_nuke)} == {888, 42}

    # ...ma non nomina altri extra owner, ne' toglie l'altro extra owner.
    rifiuto = _come(888)
    await cog.trusted_add.callback(cog, rifiuto, "999", None, _scelta("extra_owner"))
    assert "Solo il proprietario" in _risposta(rifiuto)
    rifiuto = _come(888)
    await cog.trusted_remove.callback(cog, rifiuto, "888")
    assert "Solo il proprietario" in _risposta(rifiuto)


async def test_extra_owner_con_ambito_e_rifiutato(cog):
    interazione = _come(PROPRIETARIO_ID)
    await cog.trusted_add.callback(cog, interazione, "888", None, _scelta("extra_owner"), _scelta("channel"))
    assert "tutte le azioni" in _risposta(interazione)


async def test_la_lista_ha_un_tetto(cog, monkeypatch):
    monkeypatch.setattr(modulo, "MAX_FIDATI", 2)
    await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), "1")
    await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), "2")
    pieno = _come(PROPRIETARIO_ID)
    await cog.trusted_add.callback(cog, pieno, "3")
    assert "piena" in _risposta(pieno)


# ====================================================================
# SIC-019 — fiducia per tipo di azione e per categoria di canali
# ====================================================================
async def test_fidato_per_i_canali_ma_non_per_i_ruoli(cog):
    await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), str(AUTORE_ID), None, None, _scelta("channel"))
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[]])
    assert await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "x") is None
    assert await cog._handle_event(server, "role", AUTORE_ID, "x") is None  # soglia ruoli non a zero
    await cog.limits.callback(cog, _interazione(), _scelta("role"), 0, 60)
    assert await cog._handle_event(server, "role", AUTORE_ID, "x") is not None


async def test_bot_dei_ticket_cancella_solo_nella_sua_categoria(cog):
    categoria = MagicMock(spec=discord.CategoryChannel)
    categoria.id = 900
    categoria.name = "Ticket"
    await cog.trusted_add.callback(
        cog, _come(PROPRIETARIO_ID), str(AUTORE_ID), None, None, None, categoria
    )
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[_voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7001)]])

    dentro = _canale_cancellato(fake_text_channel(), server, "ticket-1")
    dentro.category_id = 900
    await cog.on_guild_channel_delete(dentro)
    autore.edit.assert_not_awaited()

    fuori = _canale_cancellato(fake_text_channel(), server, "generale")
    fuori.category_id = 123
    await cog.on_guild_channel_delete(fuori)
    autore.edit.assert_awaited()


# ====================================================================
# SIC-020 — webhook esente
# ====================================================================
async def test_webhook_esente_non_conta_ma_un_altro_si(cog):
    await cog.limits.callback(cog, _interazione(), _scelta(NUKE_CATEGORY_WEBHOOK), 0, 60)
    await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), "55", _scelta("webhook"))
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    canale = fake_text_channel()
    canale.guild = None

    server = _server(autore, [[_voce(discord.AuditLogAction.webhook_create, AUTORE_ID, 55)]])
    canale.guild = server
    await cog.on_webhooks_update(canale)
    autore.edit.assert_not_awaited()

    server = _server(autore, [[_voce(discord.AuditLogAction.webhook_create, AUTORE_ID, 56)]])
    canale.guild = server
    await cog.on_webhooks_update(canale)
    autore.edit.assert_awaited()
