"""
tests/test_guild_clan_cog_behavior.py
=========================================
Test del comportamento REALE di /clan crea|info|membri|classifica|
sciogli|tesoreria dona — contro PostgreSQL vero (SPEC.md §15.14,
primo pezzo di comandi Discord sopra il motore economico già
esistente).
"""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from cogs.leveling.leveling import LevelingCog
from core.database import Database
from core.repositories.guild_clan_repo import GuildClanRepository
from core.repositories.leveling_repo import LevelingRepository


class _FakeResponse:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.sent_embeds: list = []

    async def send_message(self, content: str = None, embed=None, ephemeral: bool = False) -> None:
        if content is not None:
            self.sent_messages.append(content)
        if embed is not None:
            self.sent_embeds.append(embed)


class _FakeHTTPResponse:
    status = 403
    reason = "Forbidden"


class _FakeChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.deleted = False

    async def delete(self, reason: str | None = None) -> None:
        self.deleted = True


class _FakeCategory:
    def __init__(self, category_id: int, channels: list | None = None) -> None:
        self.id = category_id
        self.channels = channels or []
        self.deleted = False
        self.overwrites_impostati: dict = {}

    async def delete(self, reason: str | None = None) -> None:
        self.deleted = True

    async def set_permissions(self, target, overwrite=None) -> None:
        if overwrite is None:
            self.overwrites_impostati.pop(target, None)
        else:
            self.overwrites_impostati[target] = overwrite


class _FakeRole:
    def __init__(self, name: str = "@everyone", role_id: int = 0) -> None:
        self.name = name
        self.id = role_id

    def __eq__(self, other) -> bool:
        return isinstance(other, _FakeRole) and other.id == self.id and other.name == self.name

    def __hash__(self) -> int:
        return hash((self.id, self.name))


class _FakeGuild:
    def __init__(self, guild_id: int, category_creation_forbidden: bool = False) -> None:
        self.id = guild_id
        self.default_role = _FakeRole()
        self.me = _FakeMember(0)
        self._channels_by_id: dict[int, object] = {}
        self._next_category_id = 1000
        self._category_creation_forbidden = category_creation_forbidden
        self.created_categories: list = []
        self.roles: list = []
        self._next_role_id = 1

    async def create_category(self, name: str, overwrites=None, reason=None):
        if self._category_creation_forbidden:
            raise discord.Forbidden(response=_FakeHTTPResponse(), message="niente permessi")
        categoria = _FakeCategory(self._next_category_id)
        self._next_category_id += 1
        self._channels_by_id[categoria.id] = categoria
        self.created_categories.append(categoria)
        return categoria

    async def create_role(self, name: str, mentionable: bool = False, reason=None):
        ruolo = _FakeRole(name=name, role_id=self._next_role_id)
        self._next_role_id += 1
        self.roles.append(ruolo)
        return ruolo

    def get_channel(self, channel_id: int):
        return self._channels_by_id.get(channel_id)


class _FakeMember(discord.Member):
    def __init__(self, member_id: int) -> None:
        self._id_finto = member_id
        self._ruoli_finti: list = []
        self.chiamate_add_roles: list = []
        self.chiamate_remove_roles: list = []

    @property
    def id(self):
        return self._id_finto

    @property
    def roles(self):
        return self._ruoli_finti

    @property
    def mention(self):
        return f"<@{self._id_finto}>"

    def __hash__(self) -> int:
        return hash(self._id_finto)

    def __eq__(self, other) -> bool:
        return isinstance(other, _FakeMember) and other._id_finto == self._id_finto

    def __str__(self) -> str:
        return f"Utente#{self._id_finto}"

    async def add_roles(self, *roles, reason=None) -> None:
        self.chiamate_add_roles.append(roles)
        for r in roles:
            if r not in self._ruoli_finti:
                self._ruoli_finti.append(r)

    async def remove_roles(self, *roles, reason=None) -> None:
        self.chiamate_remove_roles.append(roles)
        for r in roles:
            if r in self._ruoli_finti:
                self._ruoli_finti.remove(r)


class _FakeInteraction:
    def __init__(self, guild, user=None) -> None:
        self.guild = guild
        self.user = user or _FakeMember(1)
        self.response = _FakeResponse()


@pytest.fixture
async def cog_e_repos(monkeypatch):
    import cogs.leveling.leveling as leveling_module

    database = Database()
    await database.connect()
    await database.run_migrations()
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.pool.execute("DELETE FROM leveling_totals")

    clan_repo = GuildClanRepository(pool_provider=lambda: database.pool)
    leveling_repo = LevelingRepository(pool_provider=lambda: database.pool)
    monkeypatch.setattr(leveling_module, "guild_clan_repo", clan_repo)
    monkeypatch.setattr(leveling_module, "leveling_repo", leveling_repo)

    cog = LevelingCog(bot=None)
    cog.cog_unload()

    yield cog, clan_repo, leveling_repo
    await database.pool.execute("DELETE FROM clan_treasury_ledger")
    await database.pool.execute("DELETE FROM clan_members")
    await database.pool.execute("DELETE FROM clans")
    await database.pool.execute("DELETE FROM leveling_totals")
    await database.close()


@pytest.mark.asyncio
async def test_crea_una_gilda_con_categoria(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_crea.callback(cog, interaction, tag="ABC", name="I Cavalieri")

    assert "creata" in interaction.response.sent_messages[0]
    clan = await clan_repo.get_clan_by_tag(100, "ABC")
    assert clan is not None
    assert clan.owner_id == 1
    assert clan.officialized is False
    assert clan.category_id == guild.created_categories[0].id


@pytest.mark.asyncio
async def test_crea_con_tag_invalido_non_crea_nulla(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild)

    await cog.clan_crea.callback(cog, interaction, tag="TROPPOLUNGO", name="X")

    assert await clan_repo.get_clan_by_tag(100, "TROPPOLUNGO") is None
    assert len(guild.created_categories) == 0


@pytest.mark.asyncio
async def test_crea_con_tag_gia_preso_fallisce(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    await clan_repo.create_clan(
        100, tag="ABC", name="Primo", owner_id=99,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_crea.callback(cog, interaction, tag="ABC", name="Secondo")

    assert "già usato" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_crea_chi_e_gia_in_una_gilda_non_puo_crearne_unaltra(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    await clan_repo.create_clan(
        100, tag="ABC", name="Primo", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_crea.callback(cog, interaction, tag="XYZ", name="Secondo")

    assert "Fai già parte" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_crea_permessi_mancanti_avvisa(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100, category_creation_forbidden=True)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_crea.callback(cog, interaction, tag="ABC", name="X")

    assert "permessi" in interaction.response.sent_messages[0]
    assert await clan_repo.get_clan_by_tag(100, "ABC") is None


@pytest.mark.asyncio
async def test_info_della_propria_gilda(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    await clan_repo.create_clan(
        100, tag="ABC", name="I Cavalieri", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_info.callback(cog, interaction, tag=None)

    embed = interaction.response.sent_embeds[0]
    assert "ABC" in embed.title
    assert "I Cavalieri" in embed.title


@pytest.mark.asyncio
async def test_info_utente_senza_gilda(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_info.callback(cog, interaction, tag=None)

    assert "Non fai parte" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_membri_elenca_i_membri(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="X", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await clan_repo.add_member(clan_id, user_id=2)
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_membri.callback(cog, interaction, tag=None)

    embed = interaction.response.sent_embeds[0]
    assert "<@1>" in embed.description
    assert "<@2>" in embed.description


@pytest.mark.asyncio
async def test_classifica_ordina_per_xp(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    id_basso = await clan_repo.create_clan(
        100, tag="AAA", name="Bassa", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    id_alto = await clan_repo.create_clan(
        100, tag="BBB", name="Alta", owner_id=2,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await clan_repo.add_xp(id_basso, 10)
    await clan_repo.add_xp(id_alto, 500)
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild)

    await cog.clan_classifica.callback(cog, interaction)

    embed = interaction.response.sent_embeds[0]
    assert embed.description.index("Alta") < embed.description.index("Bassa")


@pytest.mark.asyncio
async def test_sciogli_rimuove_clan_e_categoria(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    canale = _FakeChannel(111)
    categoria = _FakeCategory(50, [canale])
    guild._channels_by_id[50] = categoria
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="X", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await clan_repo.set_category_id(clan_id, categoria.id)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_sciogli.callback(cog, interaction)

    assert "sciolta" in interaction.response.sent_messages[0]
    assert await clan_repo.get_clan(clan_id) is None
    assert canale.deleted is True
    assert categoria.deleted is True


@pytest.mark.asyncio
async def test_sciogli_solo_il_capo_clan_puo_farlo(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="X", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await clan_repo.add_member(clan_id, user_id=2)
    interaction = _FakeInteraction(guild, user=_FakeMember(2))  # non owner

    await cog.clan_sciogli.callback(cog, interaction)

    assert "Solo il Capo Clan" in interaction.response.sent_messages[0]
    assert await clan_repo.get_clan(clan_id) is not None


@pytest.mark.asyncio
async def test_tesoreria_dona_sottrae_dal_saldo_personale_e_accredita_il_clan(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="X", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await leveling_repo.add_coins(100, 1, 20_000)
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_tesoreria_dona.callback(cog, interaction, importo=15_000)

    assert "donato" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 1)).coins_total == 5_000
    clan = await clan_repo.get_clan(clan_id)
    assert clan.treasury_balance == 0  # -15.000 (deficit) + 15.000 donati


@pytest.mark.asyncio
async def test_tesoreria_dona_ufficializza_quando_il_deficit_e_coperto(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    clan_id = await clan_repo.create_clan(
        100, tag="ABC", name="X", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await leveling_repo.add_coins(100, 1, 20_000)
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_tesoreria_dona.callback(cog, interaction, importo=15_000)

    assert "ufficializzata" in interaction.response.sent_messages[0]
    clan = await clan_repo.get_clan(clan_id)
    assert clan.officialized is True


@pytest.mark.asyncio
async def test_tesoreria_dona_saldo_personale_insufficiente(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    await clan_repo.create_clan(
        100, tag="ABC", name="X", owner_id=1,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    await leveling_repo.add_coins(100, 1, 100)
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_tesoreria_dona.callback(cog, interaction, importo=15_000)

    assert "Non hai abbastanza coin" in interaction.response.sent_messages[0]
    assert (await leveling_repo.get_totals(100, 1)).coins_total == 100  # invariato


@pytest.mark.asyncio
async def test_tesoreria_dona_senza_gilda_avvisa(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    interaction = _FakeInteraction(guild, user=_FakeMember(1))

    await cog.clan_tesoreria_dona.callback(cog, interaction, importo=100)

    assert "Non fai parte" in interaction.response.sent_messages[0]


# ======================================================================
# invita / espelli / promuovi — ruoli Discord Capo Clan/Admin Clan
# ======================================================================

async def _crea_clan_con_categoria(clan_repo, guild, owner_id=1, tag="ABC", max_members=None):
    kwargs = {}
    if max_members is not None:
        kwargs["max_members"] = max_members
    clan_id = await clan_repo.create_clan(
        guild.id, tag=tag, name="I Cavalieri", owner_id=owner_id,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
        **kwargs,
    )
    categoria = _FakeCategory(50)
    guild._channels_by_id[categoria.id] = categoria
    await clan_repo.set_category_id(clan_id, categoria.id)
    return clan_id, categoria


@pytest.mark.asyncio
async def test_invita_aggiunge_membro_e_gli_da_accesso_alla_categoria(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    capo = _FakeMember(1)
    invitato = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_invita.callback(cog, interaction, membro=invitato)

    assert "invitato" in interaction.response.sent_messages[0]
    membro_db = await clan_repo.get_member(clan_id, 2)
    assert membro_db is not None
    assert membro_db.role == "member"
    assert categoria.overwrites_impostati[invitato].view_channel is True


@pytest.mark.asyncio
async def test_invita_un_admin_puo_farlo(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=5, role="admin")
    admin = _FakeMember(5)
    invitato = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=admin)

    await cog.clan_invita.callback(cog, interaction, membro=invitato)

    assert "invitato" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_invita_un_membro_semplice_non_puo_farlo(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=5, role="member")
    membro_semplice = _FakeMember(5)
    invitato = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=membro_semplice)

    await cog.clan_invita.callback(cog, interaction, membro=invitato)

    assert "Solo il Capo Clan o un Admin Clan" in interaction.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, 2) is None


@pytest.mark.asyncio
async def test_invita_chi_e_gia_in_una_gilda_fallisce(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild, owner_id=1, tag="ABC")
    await clan_repo.create_clan(
        100, tag="XYZ", name="Altra", owner_id=2,
        officialize_deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    capo = _FakeMember(1)
    gia_in_gilda = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_invita.callback(cog, interaction, membro=gia_in_gilda)

    assert "già parte di una gilda" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_invita_gilda_piena_fallisce(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild, max_members=1)
    capo = _FakeMember(1)
    invitato = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_invita.callback(cog, interaction, membro=invitato)

    assert "limite" in interaction.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, 2) is None


@pytest.mark.asyncio
async def test_espelli_rimuove_membro_e_revoca_accesso(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=2)
    capo = _FakeMember(1)
    target = _FakeMember(2)
    await categoria.set_permissions(target, overwrite=discord.PermissionOverwrite(view_channel=True))
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_espelli.callback(cog, interaction, membro=target)

    assert "espulso" in interaction.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, 2) is None
    assert target not in categoria.overwrites_impostati


@pytest.mark.asyncio
async def test_espelli_il_capo_clan_non_si_puo_espellere(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    capo = _FakeMember(1)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_espelli.callback(cog, interaction, membro=capo)

    assert "non può essere espulso" in interaction.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, 1) is not None


@pytest.mark.asyncio
async def test_espelli_un_admin_non_puo_espellere_un_altro_admin(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=5, role="admin")
    await clan_repo.add_member(clan_id, user_id=6, role="admin")
    admin_1 = _FakeMember(5)
    admin_2 = _FakeMember(6)
    interaction = _FakeInteraction(guild, user=admin_1)

    await cog.clan_espelli.callback(cog, interaction, membro=admin_2)

    assert "non può espellere un altro Admin Clan" in interaction.response.sent_messages[0]
    assert await clan_repo.get_member(clan_id, 6) is not None


@pytest.mark.asyncio
async def test_espelli_chi_non_e_nella_gilda_avvisa(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    capo = _FakeMember(1)
    estraneo = _FakeMember(9)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_espelli.callback(cog, interaction, membro=estraneo)

    assert "non fa parte della tua gilda" in interaction.response.sent_messages[0]


@pytest.mark.asyncio
async def test_promuovi_ad_admin_assegna_ruolo_discord_condiviso(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=2)
    capo = _FakeMember(1)
    target = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_promuovi.callback(cog, interaction, membro=target, ruolo="admin")

    assert "ora **admin**" in interaction.response.sent_messages[0]
    membro_db = await clan_repo.get_member(clan_id, 2)
    assert membro_db.role == "admin"
    assert any(r.name == "Admin Clan" for r in target.roles)
    assert categoria.overwrites_impostati[target].manage_channels is True


@pytest.mark.asyncio
async def test_promuovi_solo_il_capo_clan_puo_farlo(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=5, role="admin")
    await clan_repo.add_member(clan_id, user_id=2)
    admin = _FakeMember(5)
    target = _FakeMember(2)
    interaction = _FakeInteraction(guild, user=admin)

    await cog.clan_promuovi.callback(cog, interaction, membro=target, ruolo="admin")

    assert "Solo il Capo Clan" in interaction.response.sent_messages[0]
    assert (await clan_repo.get_member(clan_id, 2)).role == "member"


@pytest.mark.asyncio
async def test_promuovi_rispetta_il_tetto_massimo_di_admin(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    for uid in (2, 3, 4):
        await clan_repo.add_member(clan_id, user_id=uid, role="admin")
    await clan_repo.add_member(clan_id, user_id=5, role="member")
    capo = _FakeMember(1)
    target = _FakeMember(5)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_promuovi.callback(cog, interaction, membro=target, ruolo="admin")

    assert "limite" in interaction.response.sent_messages[0]
    assert (await clan_repo.get_member(clan_id, 5)).role == "member"


@pytest.mark.asyncio
async def test_promuovi_a_member_declassa_e_rimuove_ruolo_discord(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, categoria = await _crea_clan_con_categoria(clan_repo, guild)
    await clan_repo.add_member(clan_id, user_id=2, role="admin")
    capo = _FakeMember(1)
    target = _FakeMember(2)
    await cog.clan_promuovi.callback(
        cog, _FakeInteraction(guild, user=capo), membro=target, ruolo="admin"
    )
    assert any(r.name == "Admin Clan" for r in target.roles)

    await cog.clan_promuovi.callback(
        cog, _FakeInteraction(guild, user=capo), membro=target, ruolo="member"
    )

    assert not any(r.name == "Admin Clan" for r in target.roles)
    assert (await clan_repo.get_member(clan_id, 2)).role == "member"
    assert categoria.overwrites_impostati[target].manage_channels is not True


@pytest.mark.asyncio
async def test_promuovi_il_capo_non_puo_cambiare_il_proprio_ruolo(cog_e_repos):
    cog, clan_repo, leveling_repo = cog_e_repos
    guild = _FakeGuild(100)
    clan_id, _ = await _crea_clan_con_categoria(clan_repo, guild)
    capo = _FakeMember(1)
    interaction = _FakeInteraction(guild, user=capo)

    await cog.clan_promuovi.callback(cog, interaction, membro=capo, ruolo="admin")

    assert "non può cambiare il proprio ruolo" in interaction.response.sent_messages[0]
