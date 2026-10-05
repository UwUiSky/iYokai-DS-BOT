"""
tests/test_command_access.py
============================
Controllo di accesso ai gruppi di comandi (D24, D16): decisione pura,
check dei gruppi, rifiuto che risponde una volta sola.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import itertools
import types

import discord
import pytest
from discord import app_commands

from core import command_access as ca
from core.command_access import Livello, decidi_accesso
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

OWNER_BOT = 1
OWNER_SERVER = 2
UTENTE = 3
RUOLO = 500

PERMESSO = {
    Livello.ADMIN: "manage_guild",
    Livello.SECURITY: "administrator",
    Livello.LOG: "manage_guild",
    Livello.MOD: "moderate_members",
    Livello.MODBAN: "ban_members",
}
CHIAVE = {
    Livello.ADMIN: ca.TipoRuolo.ADMIN,
    Livello.SECURITY: ca.TipoRuolo.ADMIN,
    Livello.LOG: ca.TipoRuolo.ADMIN,
    Livello.MOD: ca.TipoRuolo.MOD,
    Livello.MODBAN: ca.TipoRuolo.MODBAN,
}


def _decidi(livello, *, perm, ruolo, owner_server=False, ruolo_esiste=True, configurato=True,
            user_id=UTENTE):
    permessi = discord.Permissions(**{PERMESSO[livello]: True}) if perm else discord.Permissions.none()
    return decidi_accesso(
        livello,
        user_id=OWNER_SERVER if owner_server else user_id,
        owner_bot_id=OWNER_BOT,
        guild_owner_id=OWNER_SERVER,
        permessi=permessi,
        ruoli_utente_ids={RUOLO} if ruolo else set(),
        ruolo_configurato_id=RUOLO if configurato else None,
        ruolo_esiste=ruolo_esiste,
    )


@pytest.mark.parametrize(
    "livello,perm,ruolo,owner_server",
    list(itertools.product(PERMESSO, [True, False], [True, False], [True, False])),
)
def test_matrice_completa(livello, perm, ruolo, owner_server):
    atteso = perm or ruolo or owner_server
    assert _decidi(livello, perm=perm, ruolo=ruolo, owner_server=owner_server) is atteso


def test_modban_non_accetta_il_ruolo_mod_semplice():
    # il ruolo mod configurato NON basta per i comandi di ban
    assert _decidi(Livello.MODBAN, perm=False, ruolo=False) is False
    permessi = discord.Permissions.none()
    assert decidi_accesso(
        Livello.MODBAN, user_id=UTENTE, owner_bot_id=OWNER_BOT, guild_owner_id=OWNER_SERVER,
        permessi=permessi, ruoli_utente_ids={RUOLO}, ruolo_configurato_id=None,
    ) is False


def test_security_vuole_administrator_non_manage_guild():
    permessi = discord.Permissions(manage_guild=True)
    assert decidi_accesso(
        Livello.SECURITY, user_id=UTENTE, owner_bot_id=OWNER_BOT, guild_owner_id=OWNER_SERVER,
        permessi=permessi, ruoli_utente_ids=set(), ruolo_configurato_id=None,
    ) is False


@pytest.mark.parametrize("livello", list(PERMESSO))
def test_ruolo_configurato_ma_cancellato_non_vale(livello):
    assert _decidi(livello, perm=False, ruolo=True, ruolo_esiste=False) is False


@pytest.mark.parametrize("livello", list(PERMESSO))
def test_nessun_ruolo_configurato_solo_permessi_discord(livello):
    assert _decidi(livello, perm=True, ruolo=True, configurato=False) is True
    assert _decidi(livello, perm=False, ruolo=True, configurato=False) is False


def test_owner_del_bot_solo_con_il_suo_id():
    def f(uid, owner_server=False):
        return decidi_accesso(
            Livello.OWNER, user_id=uid, owner_bot_id=OWNER_BOT, guild_owner_id=OWNER_SERVER,
            permessi=discord.Permissions.all(), ruoli_utente_ids={RUOLO}, ruolo_configurato_id=RUOLO,
        )
    assert f(OWNER_BOT) is True
    assert f(UTENTE) is False
    assert f(OWNER_SERVER) is False  # nemmeno il proprietario del server


def test_owner_del_bot_non_salta_i_livelli_del_server():
    # l'owner del bot, senza permessi né ruolo nel server, non è admin lì
    assert _decidi(Livello.ADMIN, perm=False, ruolo=False, user_id=OWNER_BOT) is False


# ---- il check vero, con interazioni finte fedeli ----

class _FakeDb:
    def __init__(self, valori=None):
        self.valori = valori or {}
        self.scritti = []

    async def get_guild_setting(self, guild_id, key, default=None):
        return self.valori.get((guild_id, key), default)

    async def set_guild_setting(self, guild_id, key, value, changed_by=None):
        self.valori[(guild_id, key)] = value
        self.scritti.append((guild_id, key, value, changed_by))


@pytest.fixture
def finto_db(monkeypatch):
    d = _FakeDb()
    monkeypatch.setattr(ca, "db", d)
    monkeypatch.setattr(ca, "config", types.SimpleNamespace(OWNER_ID=OWNER_BOT))
    return d


def _interazione(*, perm=None, ruoli=(), guild_ruoli=(RUOLO,), user_id=UTENTE):
    ruoli_m = [fake_role(role_id=r) for r in ruoli]
    guild = fake_guild(guild_id=77, owner_id=OWNER_SERVER)
    guild.get_role.side_effect = lambda rid: fake_role(role_id=rid) if rid in guild_ruoli else None
    membro = fake_member(
        user_id=user_id, roles=ruoli_m,
        guild_permissions=discord.Permissions(**{perm: True}) if perm else discord.Permissions.none(),
    )
    return fake_interaction(guild=guild, user=membro)


async def test_check_ammette_con_permesso(finto_db):
    assert await ca.puo_usare(_interazione(perm="manage_guild"), Livello.ADMIN) is True


async def test_check_ammette_con_ruolo_configurato(finto_db):
    finto_db.valori[(77, ca.SETTING_ADMIN_ROLE)] = RUOLO
    assert await ca.puo_usare(_interazione(ruoli=[RUOLO]), Livello.ADMIN) is True


async def test_check_ruolo_cancellato_dal_server_non_vale(finto_db):
    finto_db.valori[(77, ca.SETTING_ADMIN_ROLE)] = RUOLO
    ix = _interazione(ruoli=[RUOLO], guild_ruoli=())
    assert await ca.puo_usare(ix, Livello.ADMIN) is False


async def test_check_nega_senza_nulla(finto_db):
    assert await ca.puo_usare(_interazione(), Livello.MOD) is False


async def test_check_in_dm_nega_con_messaggio_solo_server(finto_db):
    ix = fake_interaction()
    ix.guild = None
    with pytest.raises(ca.AccessoNegato) as exc:
        await ca.controlla(ix, Livello.ADMIN)
    assert "server" in exc.value.messaggio.lower()


async def test_check_owner_bot(finto_db):
    assert await ca.puo_usare(_interazione(user_id=OWNER_BOT), Livello.OWNER) is True
    assert await ca.puo_usare(_interazione(), Livello.OWNER) is False


async def test_rifiuto_solleva_accesso_negato_italiano(finto_db):
    with pytest.raises(ca.AccessoNegato) as exc:
        await ca.controlla(_interazione(), Livello.MODBAN)
    assert exc.value.livello is Livello.MODBAN
    assert "non puoi" in exc.value.messaggio.lower()
    assert isinstance(exc.value, app_commands.CheckFailure)


async def test_rifiuto_risponde_una_volta_sola_effimero(finto_db):
    from core.premium import handle_app_command_error

    ix = _interazione()
    with pytest.raises(ca.AccessoNegato) as exc:
        await ca.controlla(ix, Livello.MOD)
    # il check NON risponde da solo
    ix.response.send_message.assert_not_called()
    await handle_app_command_error(ix, exc.value)
    ix.response.send_message.assert_awaited_once()
    assert ix.response.send_message.await_args.kwargs["ephemeral"] is True
    ix.followup.send.assert_not_called()
    assert exc.value.messaggio in ix.response.send_message.await_args.args[0]


async def test_rifiuto_dopo_defer_usa_solo_followup(finto_db):
    from core.premium import handle_app_command_error

    ix = _interazione()
    ix.response.is_done.return_value = True
    await handle_app_command_error(ix, ca.AccessoNegato(Livello.MOD))
    ix.response.send_message.assert_not_called()
    ix.followup.send.assert_awaited_once()


# ---- impostazioni dei ruoli (D16: un solo punto) ----

async def test_leggi_ruolo_assente_e_none(finto_db):
    assert await ca.leggi_ruolo(77, ca.TipoRuolo.MOD) is None


async def test_imposta_e_leggi_ruolo(finto_db):
    guild = fake_guild(guild_id=77)
    ruolo = fake_role(role_id=RUOLO)
    guild.get_role.side_effect = lambda rid: ruolo if rid == RUOLO else None
    await ca.imposta_ruolo(guild, ca.TipoRuolo.MODBAN, ruolo, changed_by=9)
    assert finto_db.scritti == [(77, "modban_role_id", RUOLO, 9)]
    assert await ca.leggi_ruolo(77, ca.TipoRuolo.MODBAN) == RUOLO
    await ca.imposta_ruolo(guild, ca.TipoRuolo.MODBAN, None, changed_by=9)
    assert await ca.leggi_ruolo(77, ca.TipoRuolo.MODBAN) is None


async def test_imposta_rifiuta_everyone_e_ruoli_di_altri_server(finto_db):
    guild = fake_guild(guild_id=77)
    everyone = fake_role(role_id=77)
    with pytest.raises(ValueError):
        await ca.imposta_ruolo(guild, ca.TipoRuolo.ADMIN, everyone, changed_by=9)
    estraneo = fake_role(role_id=999)  # guild.get_role -> None
    with pytest.raises(ValueError):
        await ca.imposta_ruolo(guild, ca.TipoRuolo.ADMIN, estraneo, changed_by=9)
    assert finto_db.scritti == []


def test_chiavi_delle_impostazioni():
    assert ca.SETTING_ADMIN_ROLE == "admin_role_id"
    assert ca.SETTING_MOD_ROLE == "mod_role_id"
    assert ca.SETTING_MODBAN_ROLE == "modban_role_id"


# ---- il decorator e i gruppi ----

async def test_richiedi_come_check_di_un_comando(finto_db):
    @app_commands.command(name="prova", description="Prova")
    @ca.richiedi(Livello.MOD)
    async def prova(interaction: discord.Interaction):  # pragma: no cover
        pass

    assert len(prova.checks) == 1
    with pytest.raises(ca.AccessoNegato):
        await prova.checks[0](_interazione())
    assert await prova.checks[0](_interazione(perm="moderate_members")) is True


async def test_sottogruppo_eredita_il_controllo_del_padre(finto_db):
    padre = ca.GruppoYokai(name="padre", description="Padre", livello=Livello.MOD)
    figlio = ca.GruppoYokai(name="figlio", description="Figlio", parent=padre)
    with pytest.raises(ca.AccessoNegato):
        await figlio.interaction_check(_interazione())
    assert await figlio.interaction_check(_interazione(perm="moderate_members")) is True
