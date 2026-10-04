"""
tests/test_restore_cog_behavior.py
======================================
Test del comportamento REALE di RestoreCog (SPEC.md §11.11/§11.12) —
contro PostgreSQL vero per i repository, con fake minimi per gli
oggetti discord.py e l'orchestrator OAuth (nessuna vera rete).
"""

from datetime import datetime, timedelta, timezone

import pytest

from cogs.utility.restore import RestoreCog
from core.database import Database
from core.oauth_crypto import generate_key
from core.repositories.backup_repo import BackupRepository
from core.repositories.backup_user_snapshot_repo import BackupUserSnapshotRepository
from core.repositories.restore_oauth_repo import RestoreOAuthRepository
from core.repositories.verify_repo import VerifyRepository

CHIAVE_TEST = generate_key()


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, bool]] = []
        self.deferred = False

    async def send_message(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append((content, ephemeral))

    async def defer(self, ephemeral: bool = False) -> None:
        self.deferred = True


class _FakeFollowup:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, bool]] = []

    async def send(self, content: str, ephemeral: bool = False) -> None:
        self.sent_messages.append((content, ephemeral))


class _FakeGuild:
    def __init__(self, guild_id: int, name: str = "Server") -> None:
        self.id = guild_id
        self.name = name


class _FakeInteraction:
    def __init__(self, guild_id: int | None) -> None:
        self.guild = _FakeGuild(guild_id) if guild_id is not None else None
        self.response = _FakeResponse()
        self.followup = _FakeFollowup()
        self.channel = _FakeChannel()


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


class _FakeInvite:
    url = "https://discord.gg/finto"


class _FakeChannel:
    async def create_invite(self, **kwargs):
        return _FakeInvite()


class _FakeUser:
    def __init__(self, user_id: int, disponibile: bool = True) -> None:
        self.id = user_id
        self._disponibile = disponibile
        self.messaggi_ricevuti: list[str] = []

    async def send(self, content: str) -> None:
        if not self._disponibile:
            import discord

            raise discord.Forbidden(response=_FakeHTTPResponse(), message="DM chiuse")
        self.messaggi_ricevuti.append(content)


class _FakeBot:
    def __init__(self, utenti: dict[int, _FakeUser]) -> None:
        self._utenti = utenti

    async def fetch_user(self, user_id: int):
        if user_id not in self._utenti:
            import discord

            raise discord.NotFound(response=_FakeHTTPResponse(), message="non trovato")
        return self._utenti[user_id]


@pytest.fixture
async def database():
    db_instance = Database()
    await db_instance.connect()
    await db_instance.run_migrations()
    yield db_instance
    await db_instance.pool.execute("DELETE FROM backup_user_snapshots")
    await db_instance.pool.execute("DELETE FROM restore_oauth_tokens")
    await db_instance.pool.execute("DELETE FROM guild_config")
    await db_instance.pool.execute("DELETE FROM guild_config_history")
    await db_instance.pool.execute("DELETE FROM verify_config")
    await db_instance.pool.execute("DELETE FROM backup_pairs")
    await db_instance.close()


def _patch_repos(monkeypatch, database):
    import cogs.utility.restore as restore_module

    snapshot_repo = BackupUserSnapshotRepository(pool_provider=lambda: database.pool)
    oauth_repo = RestoreOAuthRepository(
        pool_provider=lambda: database.pool, encryption_key_provider=lambda: CHIAVE_TEST
    )
    verify_repo_test = VerifyRepository(pool_provider=lambda: database.pool)
    backup_repo_test = BackupRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(restore_module, "backup_user_snapshot_repo", snapshot_repo)
    monkeypatch.setattr(restore_module, "restore_oauth_repo", oauth_repo)
    monkeypatch.setattr(restore_module, "verify_repo", verify_repo_test)
    monkeypatch.setattr(restore_module, "backup_repo", backup_repo_test)
    return snapshot_repo, oauth_repo, verify_repo_test, backup_repo_test


@pytest.mark.asyncio
async def test_configura_restore_salva_la_modalita(database, monkeypatch):
    import cogs.utility.restore as restore_module
    from core.database import db as db_singleton

    monkeypatch.setattr(restore_module, "db", database)
    cog = RestoreCog(bot=None)
    interaction = _FakeInteraction(guild_id=100)

    class _Scelta:
        value = "classic_invite"
        name = "Solo invito classico (nessun token salvato)"

    await cog.configura_restore.callback(cog, interaction, _Scelta(), auto_invito_nuovi_membri=True)

    assert "classic invite" not in interaction.response.sent_messages[0][0]  # sanity: usa il "name", non il value
    modalita = await database.get_guild_setting(100, "backup_restore_mode")
    assert modalita == "classic_invite"
    auto_invito = await database.get_guild_setting(100, "backup_auto_invite_on_join")
    assert auto_invito is True


@pytest.mark.asyncio
async def test_restore_users_senza_snapshot_avvisa(database, monkeypatch):
    _snapshot, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await backup_repo_test.define_main(999999)
    await backup_repo_test.define_backup(999999, 200)

    cog = RestoreCog(bot=None)
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "999999")

    assert "Nessuno snapshot" in interaction.response.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_senza_coppia_backup_rifiuta(database, monkeypatch):
    """
    SEC-2: senza una coppia main=origine/backup=questo server, il
    restore va rifiutato PRIMA di guardare lo snapshot — altrimenti
    un admin potrebbe scrivere l'ID di un server qualunque e farsi
    ripristinare gli utenti di qualcun altro nel proprio server.
    """
    snapshot_repo, _oauth, _verify, _backup = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])

    cog = RestoreCog(bot=None)
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert "non è registrato come backup" in interaction.response.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_con_coppia_verso_un_terzo_server_rifiuta(database, monkeypatch):
    """Coppia esiste ma punta a un ALTRO server di backup: rifiutato lo stesso."""
    snapshot_repo, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 777)  # backup designato è un altro server

    cog = RestoreCog(bot=None)
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert "non è registrato come backup" in interaction.response.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_con_token_attivo_fa_auto_join(database, monkeypatch):
    snapshot_repo, oauth_repo, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)

    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])
    await oauth_repo.save_token(100, 1, "access-vero", "refresh", datetime.now(timezone.utc) + timedelta(days=7))

    chiamate_join = []

    class _FakeOrchestrator:
        async def join_user_via_oauth(self, **kwargs):
            chiamate_join.append(kwargs)
            return True

        async def assign_role(self, **kwargs):
            return True

    monkeypatch.setattr(restore_module, "restore_orchestrator", _FakeOrchestrator())

    cog = RestoreCog(bot=_FakeBot({}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert len(chiamate_join) == 1
    assert chiamate_join[0]["user_id"] == 1
    assert chiamate_join[0]["guild_id"] == 200
    assert "Aggiunti automaticamente (token già autorizzato): 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_senza_token_manda_dm_di_autorizzazione(database, monkeypatch):
    snapshot_repo, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    # SEC-3: costruire il link di autorizzazione richiede una chiave
    # di firma (derivata da OAUTH_ENCRYPTION_KEY, vedi
    # core/restore_oauth_logic.py) — senza, restore_users conta
    # comunque il DM come fallito invece di sollevare un'eccezione.
    # Config è un dataclass frozen: si sostituisce il singolo campo
    # con dataclasses.replace, poi si monkeypatcha tutto l'oggetto.
    import dataclasses

    monkeypatch.setattr(
        restore_module, "config", dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST)
    )
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])

    utente_finto = _FakeUser(1)
    cog = RestoreCog(bot=_FakeBot({1: utente_finto}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert len(utente_finto.messaggi_ricevuti) == 1
    assert "DM di autorizzazione inviati: 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_senza_chiave_di_firma_conta_come_dm_fallito(database, monkeypatch):
    """SEC-3: senza OAUTH_ENCRYPTION_KEY non si può firmare lo state — non deve esplodere."""
    snapshot_repo, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    # OAUTH_ENCRYPTION_KEY è "" di default nell'ambiente di test —
    # nessun bisogno di forzarla, è già lo scenario da testare.
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])

    utente_finto = _FakeUser(1)
    cog = RestoreCog(bot=_FakeBot({1: utente_finto}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert len(utente_finto.messaggi_ricevuti) == 0
    assert "DM non consegnati (privacy/bloccati): 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_dm_bloccato_viene_contato(database, monkeypatch):
    snapshot_repo, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])

    utente_finto = _FakeUser(1, disponibile=False)
    cog = RestoreCog(bot=_FakeBot({1: utente_finto}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert "DM non consegnati (privacy/bloccati): 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_modalita_classica_usa_invito_e_non_token(database, monkeypatch):
    snapshot_repo, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])
    await database.set_guild_setting(200, "backup_restore_mode", "classic_invite")

    utente_finto = _FakeUser(1)
    cog = RestoreCog(bot=_FakeBot({1: utente_finto}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert len(utente_finto.messaggi_ricevuti) == 1
    assert "discord.gg/finto" in utente_finto.messaggi_ricevuti[0]
    assert "Inviti classici inviati: 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_bannato_viene_saltato(database, monkeypatch):
    snapshot_repo, oauth_repo, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    import cogs.utility.restore as restore_module

    monkeypatch.setattr(restore_module, "db", database)
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])
    await oauth_repo.save_token(100, 1, "a", "r", datetime.now(timezone.utc) + timedelta(days=7))
    await oauth_repo.mark_banned(100, 1)

    cog = RestoreCog(bot=_FakeBot({1: _FakeUser(1)}))
    interaction = _FakeInteraction(guild_id=200)

    await cog.restore_users.callback(cog, interaction, "100")

    assert "Saltati (in blacklist da un ban): 1" in interaction.followup.sent_messages[0][0]


@pytest.mark.asyncio
async def test_restore_users_fuori_da_un_server_rifiuta():
    cog = RestoreCog(bot=None)
    interaction = _FakeInteraction(guild_id=None)

    await cog.restore_users.callback(cog, interaction, "100")

    assert "solo dentro un server" in interaction.response.sent_messages[0][0]


# ---------------------------------------------------------------------
# SEC-19: il link mandato in DM è legato a chi lo riceve.
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_il_link_di_autorizzazione_in_dm_e_legato_al_destinatario(database, monkeypatch):
    import dataclasses
    import re
    from urllib.parse import parse_qs, urlparse

    import cogs.utility.restore as restore_module
    from core.restore_oauth_logic import decode_and_verify_state

    snapshot_repo, _oauth, _verify, backup_repo_test = _patch_repos(monkeypatch, database)
    monkeypatch.setattr(restore_module, "db", database)
    monkeypatch.setattr(
        restore_module, "config", dataclasses.replace(restore_module.config, OAUTH_ENCRYPTION_KEY=CHIAVE_TEST)
    )
    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None), (2, "Utente2", None)])

    utenti = {1: _FakeUser(1), 2: _FakeUser(2)}
    cog = RestoreCog(bot=_FakeBot(utenti))

    await cog.restore_users.callback(cog, _FakeInteraction(guild_id=200), "100")

    for user_id, utente in utenti.items():
        url = re.search(r"https://discord\.com/oauth2/authorize\S+", utente.messaggi_ricevuti[0]).group()
        state = parse_qs(urlparse(url).query)["state"][0]
        stato = decode_and_verify_state(state, CHIAVE_TEST)
        assert (stato.source_guild_id, stato.target_guild_id, stato.user_id) == (100, 200, user_id)


# ---------------------------------------------------------------------
# SEC-4/SEC-17: il ruolo verificato si ricontrolla quando viene assegnato.
# ---------------------------------------------------------------------


class _OrchestratorCheRegistra:
    def __init__(self) -> None:
        self.aggiunti: list[int] = []
        self.ruoli_assegnati: list[tuple[int, int]] = []

    async def join_user_via_oauth(self, *, bot_token, guild_id, user_id, access_token):
        self.aggiunti.append(user_id)
        return True

    async def assign_role(self, *, bot_token, guild_id, user_id, role_id):
        self.ruoli_assegnati.append((user_id, role_id))
        return True


async def _restore_con_ruolo_verificato(database, monkeypatch, ruolo):
    """Un utente con token attivo, e `ruolo` configurato come ruolo verificato del backup."""
    import cogs.utility.restore as restore_module
    from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

    snapshot_repo, oauth_repo, verify_repo_test, backup_repo_test = _patch_repos(monkeypatch, database)
    monkeypatch.setattr(restore_module, "db", database)
    orchestrator = _OrchestratorCheRegistra()
    monkeypatch.setattr(restore_module, "restore_orchestrator", orchestrator)

    await backup_repo_test.define_main(100)
    await backup_repo_test.define_backup(100, 200)
    await snapshot_repo.save_snapshot(100, [(1, "Utente1", None)])
    await oauth_repo.save_token(100, 1, "access", "refresh", datetime.now(timezone.utc) + timedelta(days=7))
    await verify_repo_test.set_config(200, "button", ruolo.id, 0, 0, False, None)

    bot_membro = fake_member(user_id=999, name="Yokai Bot", bot=True)
    bot_membro.top_role = fake_role(role_id=9000, name="Bot", position=50)
    server = fake_guild(guild_id=200, me=bot_membro)
    server.get_role.return_value = ruolo
    interaction = fake_interaction(guild=server)

    cog = RestoreCog(bot=_FakeBot({}))
    await cog.restore_users.callback(cog, interaction, "100")
    return orchestrator, interaction


@pytest.mark.asyncio
async def test_restore_users_ruolo_verificato_sicuro_viene_assegnato(database, monkeypatch):
    from tests.support.discord_fakes import fake_role

    orchestrator, _interaction = await _restore_con_ruolo_verificato(
        database, monkeypatch, fake_role(role_id=555, name="Verificato", position=5)
    )

    assert orchestrator.aggiunti == [1]
    assert orchestrator.ruoli_assegnati == [(1, 555)]


@pytest.mark.asyncio
async def test_restore_users_ruolo_verificato_pericoloso_non_viene_assegnato(
    database, monkeypatch, caplog
):
    import logging

    import discord

    from tests.support.discord_fakes import fake_role

    ruolo_admin = fake_role(
        role_id=555, name="Verificato", position=5, permissions=discord.Permissions(administrator=True)
    )
    with caplog.at_level(logging.WARNING, logger="iyokai.restore"):
        orchestrator, interaction = await _restore_con_ruolo_verificato(
            database, monkeypatch, ruolo_admin
        )

    # L'utente entra comunque, ma senza il ruolo.
    assert orchestrator.aggiunti == [1]
    assert orchestrator.ruoli_assegnati == []
    assert "administrator" in caplog.text
    assert "Ruolo verificato non assegnato" in interaction.followup.send.call_args.args[0]
