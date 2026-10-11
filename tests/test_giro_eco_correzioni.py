"""
tests/test_giro_eco_correzioni.py
=====================================
Correzioni dopo il controllo del giro eco (#65, #83, #86): blocchi nello
stesso ordine, "sostituisci" prudente, categorie escluse, cache delle
impostazioni, XP a zero, salti di livello, righe nuove, rank card con emoji,
permessi e tetto di 25 regole sotto concorrenza.
"""

import asyncio
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest
from PIL import ImageFont

import cogs.leveling.leveling as modulo
from core.leveling_logic import (
    ConfigLivelli,
    LevelingSettings,
    deve_annunciare,
    id_canali_per_le_regole,
)
from core.rank_card_image import DatiRankCard, render_rank_card, senza_quadrati
from core.repositories.level_reward_repo import LevelReward
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository, RegolaPiena
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import (
    fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel, fake_voice_channel,
)
from tests.test_leveling_settings import _messaggio, cog_xp  # noqa: F401  (fixture condivisa)

GUILD = 100
NATI_PRIMA_DI = datetime(2099, 1, 1, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# 1. Deadlock: stesso ordine di blocco
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_decadimento_e_xp_vocale_insieme_con_righe_in_ordine_inverso(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    utenti = list(range(1, 41))
    # Righe scritte dal più grande al più piccolo: l'ordine fisico è inverso.
    await clean_db.executemany(
        "INSERT INTO leveling_totals (guild_id, user_id, coins_total) VALUES ($1, $2, 500)",
        [(GUILD, u) for u in reversed(utenti)],
    )
    await apri_connessioni(clean_db, 3)

    for giro in range(15):
        await clean_db.execute(
            "UPDATE leveling_totals SET last_weekly_decay_period = NULL WHERE guild_id = $1", GUILD
        )
        esiti = await asyncio.gather(
            repo.add_voice_minutes(GUILD, [(u, 5, True) for u in utenti]),
            repo.apply_weekly_decay_guild(GUILD, f"2026-W{giro:02d}", NATI_PRIMA_DI),
            repo.add_voice_minutes(GUILD, [(u, 5, True) for u in reversed(utenti)]),
            return_exceptions=True,
        )
        assert not [e for e in esiti if isinstance(e, Exception)], esiti


def test_il_decadimento_blocca_le_righe_in_ordine_di_utente():
    from core.repositories.leveling_repo import QUERY_DECADIMENTO_DEL_SERVER

    assert "ORDER BY user_id" in QUERY_DECADIMENTO_DEL_SERVER
    assert QUERY_DECADIMENTO_DEL_SERVER.index("ORDER BY user_id") < QUERY_DECADIMENTO_DEL_SERVER.index("FOR UPDATE")


# ----------------------------------------------------------------------
# 2. "sostituisci": i vecchi ruoli si tolgono solo dopo il nuovo
# ----------------------------------------------------------------------
def _premio(livello, ruolo):
    return LevelReward(
        id=livello, guild_id=GUILD, level_threshold=livello, role_id=ruolo,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def scena(monkeypatch):
    from core.repositories.level_reward_repo import level_reward_repo

    ruoli = {50: fake_role(role_id=50, name="vecchio", position=1),
             100: fake_role(role_id=100, name="nuovo", position=1)}
    bot = fake_member(user_id=999, bot=True, roles=[fake_role(role_id=1, name="bot", position=50)])
    guild = create_autospec(discord.Guild, instance=True)
    guild.id = GUILD
    guild.me = bot
    guild.get_role = lambda rid: ruoli.get(rid)
    guild.roles = list(ruoli.values())
    membro = fake_member(user_id=5, roles=[ruoli[50]])
    membro.add_roles = AsyncMock()
    membro.remove_roles = AsyncMock()

    async def premi(guild_id, livello):
        return [_premio(5, 50), _premio(10, 100)]

    monkeypatch.setattr(level_reward_repo, "get_rewards_up_to_level", premi)
    return modulo.LevelingCog.__new__(modulo.LevelingCog), guild, membro, ruoli


@pytest.mark.asyncio
async def test_sostituisci_con_nuovo_ruolo_sopra_il_bot_non_toglie_il_vecchio(scena):
    cog, guild, membro, ruoli = scena
    ruoli[100].position = 99  # sopra il bot: non assegnabile

    await cog._grant_level_rewards(membro, guild, 10, "sostituisci")

    membro.add_roles.assert_not_awaited()
    membro.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_sostituisci_se_l_assegnazione_fallisce_non_toglie_il_vecchio(scena):
    cog, guild, membro, _ = scena
    membro.add_roles.side_effect = discord.Forbidden(AsyncMock(status=403, reason="x"), "no")

    await cog._grant_level_rewards(membro, guild, 10, "sostituisci")

    membro.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_sostituisci_con_nuovo_ruolo_gia_posseduto_toglie_il_vecchio(scena):
    cog, guild, membro, ruoli = scena
    membro.roles = [ruoli[50], ruoli[100]]

    await cog._grant_level_rewards(membro, guild, 10, "sostituisci")

    membro.add_roles.assert_not_awaited()
    assert membro.remove_roles.await_args.args == (ruoli[50],)


# ----------------------------------------------------------------------
# 3 e 10. Categoria esclusa: valgono i canali figli (testo, vocale, clan)
# ----------------------------------------------------------------------
def test_id_canali_include_il_canale_e_la_categoria():
    canale = fake_text_channel(channel_id=10)
    canale.category_id = 900
    assert id_canali_per_le_regole(canale) == [10, 900]

    thread = fake_text_channel(channel_id=11)
    thread.parent_id = 10
    thread.parent = canale
    assert id_canali_per_le_regole(thread) == [11, 10, 900]

    senza = fake_text_channel(channel_id=12)
    assert id_canali_per_le_regole(senza) == [12]


@pytest.mark.asyncio
async def test_messaggio_in_un_canale_di_una_categoria_esclusa_non_da_xp(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(canali_esclusi=frozenset({900}))
    msg = _messaggio(111)
    msg.channel.category_id = 900

    await cog.on_message(msg)

    repo_xp.add_text_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_moltiplicatore_della_categoria_vale_per_i_figli(cog_xp):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(text_xp=10), mult_canali={900: 3.0}
    )
    msg = _messaggio(111)
    msg.channel.category_id = 900

    await cog.on_message(msg)

    assert repo_xp.add_text_xp.await_args.kwargs["amount"] == 30


@pytest.mark.asyncio
async def test_xp_dei_clan_non_matura_in_un_canale_escluso(cog_xp, monkeypatch):  # noqa: F811
    cog, repo_xp, config, _ = cog_xp
    from core.repositories.guild_clan_repo import GuildClanRepository

    clan = create_autospec(GuildClanRepository, instance=True)
    monkeypatch.setattr(modulo, "guild_clan_repo", clan)
    config["valore"] = ConfigLivelli(canali_esclusi=frozenset({111}))

    await cog.on_message(_messaggio(111))

    clan.apply_text_tick.assert_not_awaited()


@pytest.mark.asyncio
async def test_vocale_in_categoria_esclusa_non_e_idoneo(monkeypatch):
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    async def get_config(_):
        return ConfigLivelli(canali_esclusi=frozenset({900}))

    async def nessuno(ids):
        return set()

    chiamate = []

    class _Repo:
        async def add_voice_minutes(self, guild_id, presenze, **_):
            chiamate.append(presenze)
            return {u: None for u, _, _ in presenze}

    monkeypatch.setattr(leveling_settings_repo, "get_config", get_config)
    monkeypatch.setattr(modulo.blacklist_repo, "blacklisted_among", nessuno)
    monkeypatch.setattr(modulo, "leveling_repo", _Repo())
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    canale = fake_voice_channel(channel_id=222)
    canale.category_id = 900
    a, b = fake_member(user_id=1), fake_member(user_id=2)
    for m in (a, b):
        m.voice = type("V", (), {"self_deaf": False, "self_mute": False})()
    canale.members = [a, b]
    guild = fake_guild(GUILD)
    guild.afk_channel = None
    guild.voice_channels = [canale]

    await cog._process_guild_voice_xp(guild)

    assert chiamate == [[(1, 222, False), (2, 222, False)]]


# ----------------------------------------------------------------------
# 4. Cache delle impostazioni: nessuna sovrascrittura con il valore vecchio
# ----------------------------------------------------------------------
class _PoolLento:
    """Pool che ferma la lettura delle regole finché il test non la libera."""

    def __init__(self, pool, via_libera: asyncio.Event, partita: asyncio.Event) -> None:
        self._pool, self._via_libera, self._partita = pool, via_libera, partita

    async def fetch(self, *a, **k):
        self._partita.set()
        await self._via_libera.wait()
        return await self._pool.fetch(*a, **k)

    def __getattr__(self, nome):
        return getattr(self._pool, nome)


@pytest.mark.asyncio
async def test_un_salvataggio_durante_la_lettura_non_viene_sovrascritto(clean_db):
    via_libera, partita = asyncio.Event(), asyncio.Event()
    lento = LevelingSettingsRepository(pool_provider=lambda: _PoolLento(clean_db, via_libera, partita))
    veloce = LevelingSettingsRepository(pool_provider=lambda: clean_db)
    veloce._cache = lento._cache  # stessa cache: simula lo stesso processo
    veloce._versione = lento._versione

    lettura = asyncio.create_task(lento.get_config(GUILD))
    await partita.wait()  # la lettura ha già visto il valore vecchio
    await veloce.set_options(GUILD, text_xp=40)
    via_libera.set()
    await lettura

    assert (await veloce.get_config(GUILD)).impostazioni.text_xp == 40


# ----------------------------------------------------------------------
# 5. XP a zero: niente attesa
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_importo_zero_non_fa_partire_l_attesa(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)

    zero = await repo.add_text_xp(GUILD, 1, amount=0)
    subito_dopo = await repo.add_text_xp(GUILD, 1, amount=15)

    assert not zero.granted
    assert subito_dopo.granted and subito_dopo.new_xp_total == 15


# ----------------------------------------------------------------------
# 6. Salto di più livelli
# ----------------------------------------------------------------------
def test_ogni_n_conta_i_livelli_saltati():
    imp = LevelingSettings(levelup_every=5)
    assert deve_annunciare(12, imp, False, livello_precedente=3) is True  # salta il 5 e il 10
    assert deve_annunciare(12, imp, False, livello_precedente=10) is False
    assert deve_annunciare(12, imp, False) is False


@pytest.mark.asyncio
async def test_solo_premi_annuncia_se_un_livello_saltato_ha_il_premio(monkeypatch):
    from core.repositories.level_reward_repo import level_reward_repo

    async def premi(guild_id, livello):
        return [_premio(10, 100)]

    monkeypatch.setattr(level_reward_repo, "get_rewards_up_to_level", premi)
    cog = modulo.LevelingCog.__new__(modulo.LevelingCog)
    guild, canale = fake_guild(GUILD), AsyncMock()
    membro = fake_member(user_id=5)
    imp = LevelingSettings(levelup_only_rewards=True)

    await cog._annuncia_level_up(membro, guild, canale, 12, imp, livello_precedente=3)
    assert canale.send.await_count == 1  # il 10 è stato saltato: il premio è arrivato

    await cog._annuncia_level_up(membro, guild, canale, 12, imp, livello_precedente=11)
    assert canale.send.await_count == 1  # nessun premio tra 11 e 12


@pytest.mark.asyncio
async def test_il_repo_dice_da_che_livello_si_parte(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    risultato = await repo.add_text_xp(GUILD, 1, amount=700)
    assert risultato.previous_level == 0 and risultato.new_level > 0


# ----------------------------------------------------------------------
# 7. Riga nuova creata insieme: nessun guadagno perso
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_testo_e_vocale_su_utenti_nuovi_si_sommano_sempre(clean_db):
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    await apri_connessioni(clean_db, 3)
    utenti = list(range(1, 31))

    await asyncio.gather(
        asyncio.gather(*(repo.add_text_xp(GUILD, u) for u in utenti)),
        repo.add_voice_minutes(GUILD, [(u, 5, True) for u in utenti]),
    )

    xp = {r["user_id"]: r["xp_total"] for r in await clean_db.fetch(
        "SELECT user_id, xp_total FROM leveling_totals WHERE guild_id = $1", GUILD)}
    assert xp == {u: 15 + 5 for u in utenti}


# ----------------------------------------------------------------------
# 8. Rank card: emoji, errori dell'avatar, Pillow
# ----------------------------------------------------------------------
def _font():
    from core.rank_card_image import _font as f

    return f(40)


def test_le_emoji_nel_nome_non_diventano_quadrati():
    font = _font()
    assert senza_quadrati("Yokai 🐉🔥", font) == "Yokai"
    assert senza_quadrati("🐉🔥", font) == "Utente"
    assert senza_quadrati("Yokai Bot", font) == "Yokai Bot"
    assert senza_quadrati("", font) == "Utente"


def test_render_con_nome_di_sole_emoji():
    dati = DatiRankCard("🐉🔥", 1, 0, 100, 0, 1, 0)
    assert render_rank_card(dati, None).startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_rank_con_un_errore_qualunque_dell_avatar_manda_la_card(monkeypatch):
    from tests.test_rank_card_image import _bersaglio

    repo = AsyncMock()
    repo.get_totals.return_value = type("T", (), dict(level=1, xp_total=100, coins_total=5))()
    repo.get_xp_position.return_value = 1
    repo.get_rank_card_prefs.return_value = (None, None)
    db_finto = AsyncMock()
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "leveling_repo", repo)
    monkeypatch.setattr(modulo, "db", db_finto)
    cog = modulo.LevelingCog.__new__(modulo.LevelingCog)
    utente = _bersaglio(1)
    utente.display_avatar.read.side_effect = ConnectionResetError("rete")
    interazione = fake_interaction(guild=fake_guild(GUILD), user=utente)

    await cog.rank.callback(cog, interazione, member=None, colore=None, tema=None, reimposta=None)

    assert isinstance(interazione.followup.send.await_args.kwargs["file"], discord.File)


def test_pillow_minimo_e_quello_che_serve_a_load_default_con_size():
    testo = open("requirements.txt", encoding="utf-8").read()
    riga = next(r for r in testo.splitlines() if r.lower().startswith("pillow"))
    assert ">=10.1" in riga or ">=11" in riga or ">=12" in riga


# ----------------------------------------------------------------------
# Permessi veri di /level impostazioni e tetto di 25 sotto concorrenza
# ----------------------------------------------------------------------
@pytest.fixture
async def comandi(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
    from tests.support.moduli import attiva_livelli

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    return {c.qualified_name: c for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)}


@pytest.mark.asyncio
@pytest.mark.parametrize("nome", ["mostra", "annuncio", "premi", "xp", "escludi", "moltiplicatore"])
async def test_chi_non_e_admin_non_puo_usare_level_impostazioni(comandi, nome):
    from core.command_access import AccessoNegato

    comando = comandi[f"level impostazioni {nome}"]
    interazione = fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id=42))

    with pytest.raises((AccessoNegato, discord.app_commands.CheckFailure)):
        await comando._check_can_run(interazione)


@pytest.mark.asyncio
async def test_un_admin_puo_usare_level_impostazioni(comandi):
    comando = comandi["level impostazioni mostra"]
    admin = fake_member(user_id=42, guild_permissions=discord.Permissions(manage_guild=True))
    interazione = fake_interaction(guild=fake_guild(GUILD), user=admin)

    assert await comando._check_can_run(interazione) is True


@pytest.mark.asyncio
async def test_il_tetto_di_25_regole_regge_con_60_chiamate_insieme(clean_db):
    repo = LevelingSettingsRepository(pool_provider=lambda: clean_db)
    await apri_connessioni(clean_db, 3)

    esiti = await asyncio.gather(
        *(repo.set_rule(GUILD, "canale_escluso", 1000 + i) for i in range(60)),
        return_exceptions=True,
    )

    assert sum(isinstance(e, RegolaPiena) for e in esiti) == 35
    assert not [e for e in esiti if isinstance(e, Exception) and not isinstance(e, RegolaPiena)]
    assert await clean_db.fetchval(
        "SELECT count(*) FROM leveling_xp_rules WHERE guild_id = $1", GUILD
    ) == 25


# ----------------------------------------------------------------------
# 10. Clan vocale: l'esclusione vale anche per la gilda
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_il_tick_vocale_dei_clan_salta_i_canali_di_una_categoria_esclusa(monkeypatch):
    import core.guild_clan_voice_worker as w

    async def get_config(_):
        return ConfigLivelli(canali_esclusi=frozenset({900}))

    monkeypatch.setattr(w.leveling_settings_repo, "get_config", get_config)
    chiamate = []

    async def bloccati(_):
        return False

    clan = AsyncMock()
    clan.get_member_clan_in_guild.side_effect = lambda *a: chiamate.append(a)
    monkeypatch.setattr(w, "guild_clan_repo", clan)
    monkeypatch.setattr(w.blacklist_repo, "is_user_blacklisted", bloccati)
    monkeypatch.setattr(w, "clan_voice_activity_repo", AsyncMock(get_tracked_as_in_voice=AsyncMock(return_value=[])))
    voce = type("V", (), {"self_deaf": False, "self_mute": False})()
    canale = fake_voice_channel(channel_id=222)
    canale.category_id = 900
    membri = [fake_member(user_id=1), fake_member(user_id=2)]
    for m in membri:
        m.voice = voce
    canale.members = membri
    guild = fake_guild(GUILD)
    guild.afk_channel = None
    guild.voice_channels = [canale]
    bot = type("B", (), {"guilds": [guild]})()

    await w.GuildClanVoiceWorker().tick(bot)

    assert chiamate == []
