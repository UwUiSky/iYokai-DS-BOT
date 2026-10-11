"""
tests/test_leveling_settings.py
===================================
NF-15 (#86): impostazioni dei livelli per server. Logica pura, archivio
su PostgreSQL vero e comportamento del cog (canale escluso, moltiplicatore,
dove annunciare il level-up, modalità dei ruoli premio).
Funzioni coperte: SPEC §22.14
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, create_autospec

import discord
import pytest

import cogs.leveling.leveling as modulo
from core.database import Database
from core.leveling_logic import (
    ConfigLivelli,
    LevelingSettings,
    deve_annunciare,
    moltiplicatore_xp,
    scegli_premi,
    xp_con_moltiplicatore,
)
from core.repositories.guild_clan_repo import GuildClanRepository
from core.repositories.level_reward_repo import LevelReward
from core.repositories.leveling_repo import LevelingRepository, TextXpResult
from core.repositories.leveling_settings_repo import (
    LevelingSettingsRepository,
    RegolaPiena,
)
from tests.support.discord_fakes import fake_member, fake_message, fake_role, fake_text_channel

GUILD = 100


# ----------------------------------------------------------------------
# Logica pura
# ----------------------------------------------------------------------
def test_moltiplicatori_si_sommano_oppure_vale_il_piu_alto():
    assert moltiplicatore_xp("somma", [1.5, 2.0]) == 2.5
    assert moltiplicatore_xp("massimo", [1.5, 2.0]) == 2.0
    assert moltiplicatore_xp("somma", []) == 1.0
    assert moltiplicatore_xp("massimo", []) == 1.0
    # Un fattore sotto 1 (rallentamento) conta come +(-0.5) nella somma.
    assert moltiplicatore_xp("somma", [0.5, 2.0]) == 1.5


def test_xp_con_moltiplicatore_arrotonda_per_eccesso_sul_mezzo():
    assert xp_con_moltiplicatore(15, 1.0) == 15
    assert xp_con_moltiplicatore(15, 2.5) == 38
    assert xp_con_moltiplicatore(15, 0.1) == 2
    assert xp_con_moltiplicatore(15, 0.0) == 0


@pytest.mark.parametrize(
    "modo, livello, min_livello, ogni, solo_premi, ha_premio, atteso",
    [
        ("spento", 5, 0, 1, False, False, False),
        ("canale_corrente", 5, 0, 1, False, False, True),
        ("canale_corrente", 4, 5, 1, False, False, False),  # sotto il livello minimo
        ("canale_corrente", 5, 5, 1, False, False, True),
        ("canale_corrente", 7, 0, 5, False, False, False),  # solo ogni 5 livelli
        ("canale_corrente", 10, 0, 5, False, False, True),
        ("dm", 3, 0, 1, True, False, False),  # solo i livelli con un premio
        ("dm", 3, 0, 1, True, True, True),
    ],
)
def test_deve_annunciare(modo, livello, min_livello, ogni, solo_premi, ha_premio, atteso):
    impostazioni = LevelingSettings(
        levelup_mode=modo,
        levelup_min_level=min_livello,
        levelup_every=ogni,
        levelup_only_rewards=solo_premi,
    )
    assert deve_annunciare(livello, impostazioni, ha_premio) is atteso


def _premio(livello: int, ruolo: int) -> LevelReward:
    return LevelReward(
        id=livello, guild_id=GUILD, level_threshold=livello, role_id=ruolo,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_premi_accumula_li_tiene_tutti():
    premi = [_premio(5, 50), _premio(10, 100)]
    assert scegli_premi(premi, "accumula") == ([50, 100], [])


def test_premi_sostituisci_tiene_solo_il_piu_alto_e_toglie_gli_altri():
    premi = [_premio(5, 50), _premio(10, 100), _premio(20, 200)]
    assert scegli_premi(premi, "sostituisci") == ([200], [50, 100])
    assert scegli_premi([], "sostituisci") == ([], [])


# ----------------------------------------------------------------------
# Archivio
# ----------------------------------------------------------------------
@pytest.fixture
def repo(clean_db):
    return LevelingSettingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_senza_righe_valgono_i_valori_di_prima(repo):
    config = await repo.get_config(GUILD)

    assert config.impostazioni == LevelingSettings()
    assert config.impostazioni.text_xp == 15
    assert config.impostazioni.text_cooldown_seconds == 60
    assert config.impostazioni.levelup_mode == "canale_corrente"
    assert config.impostazioni.reward_mode == "accumula"
    assert config.canali_esclusi == frozenset() and config.ruoli_esclusi == frozenset()


@pytest.mark.asyncio
async def test_set_options_cambia_solo_i_campi_dati(repo):
    await repo.set_options(GUILD, text_xp=30)
    await repo.set_options(GUILD, levelup_mode="dm", levelup_every=5)

    imp = (await repo.get_config(GUILD)).impostazioni
    assert (imp.text_xp, imp.levelup_mode, imp.levelup_every) == (30, "dm", 5)
    assert imp.voice_xp_per_minute == 5  # non toccato


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "campi",
    [
        {"text_xp": 0},
        {"text_xp": 101},
        {"text_cooldown_seconds": 9},
        {"voice_xp_per_minute": 51},
        {"levelup_every": 0},
        {"levelup_mode": "ovunque"},
        {"reward_mode": "boh"},
        {"multiplier_mode": "boh"},
        {"campo_inventato": 1},
    ],
)
async def test_valori_fuori_dai_limiti_sono_rifiutati(repo, campi):
    with pytest.raises(ValueError):
        await repo.set_options(GUILD, **campi)


@pytest.mark.asyncio
async def test_canale_scelto_senza_canale_e_rifiutato(repo):
    with pytest.raises(ValueError):
        await repo.set_options(GUILD, levelup_mode="canale_scelto")
    await repo.set_options(GUILD, levelup_mode="canale_scelto", levelup_channel_id=77)
    assert (await repo.get_config(GUILD)).impostazioni.levelup_channel_id == 77


@pytest.mark.asyncio
async def test_regole_di_esclusione_e_moltiplicatori(repo):
    await repo.set_rule(GUILD, "canale_escluso", 1)
    await repo.set_rule(GUILD, "ruolo_escluso", 2)
    await repo.set_rule(GUILD, "mult_canale", 3, 2.0)
    await repo.set_rule(GUILD, "mult_ruolo", 4, 1.5)
    await repo.set_rule(GUILD, "mult_ruolo", 4, 3.0)  # aggiorna, non duplica

    config = await repo.get_config(GUILD)
    assert config.canali_esclusi == {1}
    assert config.ruoli_esclusi == {2}
    assert config.mult_canali == {3: 2.0}
    assert config.mult_ruoli == {4: 3.0}

    assert await repo.remove_rule(GUILD, "mult_ruolo", 4) is True
    assert await repo.remove_rule(GUILD, "mult_ruolo", 4) is False
    assert (await repo.get_config(GUILD)).mult_ruoli == {}


@pytest.mark.asyncio
async def test_fattore_fuori_dai_limiti_o_mancante_e_rifiutato(repo):
    for fattore in (0.0, 0.09, 10.01, None):
        with pytest.raises(ValueError):
            await repo.set_rule(GUILD, "mult_canale", 3, fattore)
    with pytest.raises(ValueError):
        await repo.set_rule(GUILD, "canale_escluso", 3, 2.0)  # le esclusioni non hanno fattore
    with pytest.raises(ValueError):
        await repo.set_rule(GUILD, "tipo_inventato", 3)


@pytest.mark.asyncio
async def test_massimo_25_regole_per_tipo(repo):
    for i in range(25):
        await repo.set_rule(GUILD, "canale_escluso", 1000 + i)
    with pytest.raises(RegolaPiena):
        await repo.set_rule(GUILD, "canale_escluso", 5000)
    # Aggiornare una già presente non conta come nuova.
    await repo.set_rule(GUILD, "canale_escluso", 1000)
    # Un altro tipo ha il suo tetto.
    await repo.set_rule(GUILD, "ruolo_escluso", 5000)


@pytest.mark.asyncio
async def test_server_diversi_non_si_mischiano(repo):
    await repo.set_rule(GUILD, "canale_escluso", 1)
    await repo.set_options(GUILD, text_xp=50)

    altra = await repo.get_config(GUILD + 1)
    assert altra.canali_esclusi == frozenset()
    assert altra.impostazioni.text_xp == 15


@pytest.mark.asyncio
async def test_la_cache_si_aggiorna_dopo_una_modifica(repo):
    assert (await repo.get_config(GUILD)).impostazioni.text_xp == 15  # riempie la cache
    await repo.set_options(GUILD, text_xp=40)
    assert (await repo.get_config(GUILD)).impostazioni.text_xp == 40


# ----------------------------------------------------------------------
# Cog: XP testuale
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_xp(monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)

    async def mai_in_blacklist(user_id):
        return False

    monkeypatch.setattr(modulo.blacklist_repo, "is_user_blacklisted", mai_in_blacklist)
    clan_finto = create_autospec(GuildClanRepository, instance=True)
    clan_finto.get_member_clan_in_guild.return_value = None
    monkeypatch.setattr(modulo, "guild_clan_repo", clan_finto)
    monkeypatch.setattr(modulo, "should_trigger_drop", lambda valore: False)

    repo_xp = create_autospec(LevelingRepository, instance=True)
    repo_xp.add_text_xp.return_value = TextXpResult(
        granted=True, new_xp_total=100, leveled_up=True, new_level=5
    )
    monkeypatch.setattr(modulo, "leveling_repo", repo_xp)
    grant = AsyncMock()
    monkeypatch.setattr(modulo.LevelingCog, "_grant_level_rewards", grant)

    config = {"valore": ConfigLivelli()}

    async def get_config(guild_id):
        return config["valore"]

    monkeypatch.setattr(modulo.leveling_settings_repo, "get_config", get_config)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    return cog, repo_xp, config, grant


def _messaggio(canale_id=111, ruoli=()):
    autore = fake_member(roles=[fake_role(role_id=r, name=f"r{r}") for r in ruoli])
    autore.send = AsyncMock()
    canale = fake_text_channel(channel_id=canale_id)
    canale.send = AsyncMock()
    msg = fake_message(author=autore, channel=canale)
    msg.type = discord.MessageType.default
    return msg


@pytest.mark.asyncio
async def test_canale_escluso_non_da_xp(cog_xp):
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(canali_esclusi=frozenset({111}))

    await cog.on_message(_messaggio(111))

    repo_xp.add_text_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_ruolo_escluso_non_da_xp(cog_xp):
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(ruoli_esclusi=frozenset({9}))

    await cog.on_message(_messaggio(ruoli=(8, 9)))

    repo_xp.add_text_xp.assert_not_awaited()


@pytest.mark.asyncio
async def test_senza_impostazioni_l_xp_e_quello_di_prima(cog_xp):
    cog, repo_xp, _, _ = cog_xp

    await cog.on_message(_messaggio())

    repo_xp.add_text_xp.assert_awaited_once()
    assert repo_xp.add_text_xp.await_args.kwargs == {"amount": 15, "cooldown_seconds": 60}


@pytest.mark.asyncio
async def test_moltiplicatore_di_canale_e_di_ruolo_si_sommano(cog_xp):
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(text_xp=10, multiplier_mode="somma"),
        mult_canali={111: 2.0},
        mult_ruoli={8: 1.5},
    )

    await cog.on_message(_messaggio(111, ruoli=(8,)))

    assert repo_xp.add_text_xp.await_args.kwargs["amount"] == 25  # 10 * (1 + 1.0 + 0.5)


@pytest.mark.asyncio
async def test_moltiplicatore_modalita_massimo(cog_xp):
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(text_xp=10, multiplier_mode="massimo"),
        mult_canali={111: 2.0},
        mult_ruoli={8: 1.5},
    )

    await cog.on_message(_messaggio(111, ruoli=(8,)))

    assert repo_xp.add_text_xp.await_args.kwargs["amount"] == 20


@pytest.mark.asyncio
async def test_annuncio_nel_canale_corrente_e_i_ruoli_premio(cog_xp):
    cog, _, _, grant = cog_xp
    msg = _messaggio()

    await cog.on_message(msg)

    msg.channel.send.assert_awaited_once()
    grant.assert_awaited_once()


@pytest.mark.asyncio
async def test_annuncio_spento_non_scrive_ma_i_ruoli_arrivano(cog_xp):
    cog, _, config, grant = cog_xp
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(levelup_mode="spento"))
    msg = _messaggio()

    await cog.on_message(msg)

    msg.channel.send.assert_not_awaited()
    msg.author.send.assert_not_awaited()
    grant.assert_awaited_once()


@pytest.mark.asyncio
async def test_annuncio_in_dm(cog_xp):
    cog, _, config, _ = cog_xp
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(levelup_mode="dm"))
    msg = _messaggio()

    await cog.on_message(msg)

    msg.author.send.assert_awaited_once()
    msg.channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_annuncio_dm_con_dm_chiuso_non_solleva(cog_xp):
    cog, _, config, grant = cog_xp
    config["valore"] = ConfigLivelli(impostazioni=LevelingSettings(levelup_mode="dm"))
    msg = _messaggio()
    msg.author.send.side_effect = discord.Forbidden(AsyncMock(status=403, reason="x"), "dm chiusi")

    await cog.on_message(msg)

    grant.assert_awaited_once()


@pytest.mark.asyncio
async def test_annuncio_nel_canale_scelto(cog_xp):
    cog, _, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(levelup_mode="canale_scelto", levelup_channel_id=555)
    )
    scelto = AsyncMock()
    msg = _messaggio()
    msg.guild.get_channel = lambda cid: scelto if cid == 555 else None

    await cog.on_message(msg)

    scelto.send.assert_awaited_once()
    msg.channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_xp_testuale_usa_importo_e_attesa_configurati(cog_xp):
    cog, repo_xp, config, _ = cog_xp
    config["valore"] = ConfigLivelli(
        impostazioni=LevelingSettings(text_xp=40, text_cooldown_seconds=120)
    )

    await cog.on_message(_messaggio())

    assert repo_xp.add_text_xp.await_args.kwargs == {"amount": 40, "cooldown_seconds": 120}


# ----------------------------------------------------------------------
# XP vocale con le impostazioni
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_xp_vocale_usa_numeri_del_server_e_moltiplicatore(clean_db):
    repo_xp = LevelingRepository(pool_provider=lambda: clean_db)
    imp = LevelingSettings(voice_xp_per_minute=10, voice_coins_per_minute=0)

    risultati = await repo_xp.add_voice_minutes(
        GUILD, [(1, 5, True), (2, 5, True)], impostazioni=imp, moltiplicatori={1: 2.0}
    )

    assert (risultati[1].xp_granted, risultati[1].coins_granted) == (20, 0)
    assert (risultati[2].xp_granted, risultati[2].coins_granted) == (10, 0)


@pytest.mark.asyncio
async def test_xp_testuale_usa_importo_e_attesa_del_server(clean_db):
    repo_xp = LevelingRepository(pool_provider=lambda: clean_db)

    primo = await repo_xp.add_text_xp(GUILD, 1, amount=40, cooldown_seconds=60)
    secondo = await repo_xp.add_text_xp(GUILD, 1, amount=40, cooldown_seconds=60)
    assert primo.granted and primo.new_xp_total == 40
    assert not secondo.granted


# ----------------------------------------------------------------------
# Ruoli premio: accumula o sostituisci
# ----------------------------------------------------------------------
@pytest.fixture
def scena_premi(monkeypatch):
    from core.repositories.level_reward_repo import level_reward_repo

    ruoli = {r: fake_role(role_id=r, name=f"r{r}", position=1) for r in (50, 100)}
    bot_member = fake_member(
        user_id=999, bot=True, roles=[fake_role(role_id=1, name="bot", position=50)]
    )
    guild = create_autospec(discord.Guild, instance=True)
    guild.id = GUILD
    guild.me = bot_member
    guild.get_role = lambda rid: ruoli.get(rid)
    guild.roles = list(ruoli.values())
    membro = fake_member(user_id=5, roles=[ruoli[50]])
    membro.add_roles = AsyncMock()
    membro.remove_roles = AsyncMock()

    async def premi(guild_id, livello):
        return [_premio(5, 50), _premio(10, 100)]

    monkeypatch.setattr(level_reward_repo, "get_rewards_up_to_level", premi)
    cog = modulo.LevelingCog.__new__(modulo.LevelingCog)
    return cog, guild, membro, ruoli


@pytest.mark.asyncio
async def test_sostituisci_da_il_ruolo_nuovo_e_toglie_il_vecchio(scena_premi):
    cog, guild, membro, ruoli = scena_premi

    await cog._grant_level_rewards(membro, guild, 10, "sostituisci")

    membro.add_roles.assert_awaited_once()
    assert membro.add_roles.await_args.args == (ruoli[100],)
    membro.remove_roles.assert_awaited_once()
    assert membro.remove_roles.await_args.args == (ruoli[50],)


@pytest.mark.asyncio
async def test_accumula_non_toglie_nulla(scena_premi):
    cog, guild, membro, ruoli = scena_premi

    await cog._grant_level_rewards(membro, guild, 10, "accumula")

    assert membro.add_roles.await_args.args == (ruoli[100],)
    membro.remove_roles.assert_not_awaited()


# ----------------------------------------------------------------------
# Comandi /level impostazioni
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_comandi(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
    from core.repositories.leveling_settings_repo import leveling_settings_repo
    from tests.support.moduli import attiva_livelli

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return cog, comandi, leveling_settings_repo


def _interazione():
    from tests.support.discord_fakes import fake_guild, fake_interaction

    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(1))


def _messaggio_inviato(interazione) -> str:
    return interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_i_comandi_stanno_sotto_level_impostazioni(cog_comandi):
    _, comandi, _ = cog_comandi
    nomi = sorted(n for n in comandi if n.startswith("level impostazioni"))
    assert nomi == [
        "level impostazioni annuncio",
        "level impostazioni escludi",
        "level impostazioni moltiplicatore",
        "level impostazioni mostra",
        "level impostazioni premi",
        "level impostazioni xp",
    ]


@pytest.mark.asyncio
async def test_comando_annuncio_salva_e_mostra(cog_comandi):
    cog, comandi, repo = cog_comandi
    interazione = _interazione()
    scelta = type("C", (), {"value": "dm"})()

    await comandi["level impostazioni annuncio"].callback(
        cog, interazione, modo=scelta, canale=None, livello_minimo=10, ogni=5, solo_premi=None
    )

    imp = (await repo.get_config(GUILD)).impostazioni
    assert (imp.levelup_mode, imp.levelup_min_level, imp.levelup_every) == ("dm", 10, 5)
    assert "salvate" in _messaggio_inviato(interazione)


@pytest.mark.asyncio
async def test_comando_annuncio_canale_scelto_senza_canale_dice_errore(cog_comandi):
    cog, comandi, repo = cog_comandi
    interazione = _interazione()
    scelta = type("C", (), {"value": "canale_scelto"})()

    await comandi["level impostazioni annuncio"].callback(
        cog, interazione, modo=scelta, canale=None, livello_minimo=None, ogni=None, solo_premi=None
    )

    assert "❌" in _messaggio_inviato(interazione)
    assert (await repo.get_config(GUILD)).impostazioni.levelup_mode == "canale_corrente"


@pytest.mark.asyncio
async def test_comando_xp_senza_valori_non_scrive(cog_comandi):
    cog, comandi, _ = cog_comandi
    interazione = _interazione()

    await comandi["level impostazioni xp"].callback(
        cog, interazione, testo=None, attesa=None, voce_xp=None, voce_coin=None, moltiplicatori=None
    )

    assert "almeno un valore" in _messaggio_inviato(interazione)


@pytest.mark.asyncio
async def test_comando_escludi_aggiunge_e_poi_toglie(cog_comandi):
    from tests.support.discord_fakes import fake_text_channel

    cog, comandi, repo = cog_comandi
    canale = fake_text_channel(channel_id=321)

    await comandi["level impostazioni escludi"].callback(cog, _interazione(), canale=canale, ruolo=None)
    assert (await repo.get_config(GUILD)).canali_esclusi == {321}

    await comandi["level impostazioni escludi"].callback(cog, _interazione(), canale=canale, ruolo=None)
    assert (await repo.get_config(GUILD)).canali_esclusi == frozenset()


@pytest.mark.asyncio
async def test_comando_escludi_vuole_un_solo_bersaglio(cog_comandi):
    cog, comandi, _ = cog_comandi
    interazione = _interazione()

    await comandi["level impostazioni escludi"].callback(cog, interazione, canale=None, ruolo=None)

    assert "un canale oppure un ruolo" in _messaggio_inviato(interazione)


@pytest.mark.asyncio
async def test_comando_moltiplicatore_imposta_e_con_fattore_1_toglie(cog_comandi):
    cog, comandi, repo = cog_comandi
    ruolo = fake_role(role_id=88, name="vip")

    await comandi["level impostazioni moltiplicatore"].callback(
        cog, _interazione(), fattore=2.0, canale=None, ruolo=ruolo
    )
    assert (await repo.get_config(GUILD)).mult_ruoli == {88: 2.0}

    await comandi["level impostazioni moltiplicatore"].callback(
        cog, _interazione(), fattore=1.0, canale=None, ruolo=ruolo
    )
    assert (await repo.get_config(GUILD)).mult_ruoli == {}


@pytest.mark.asyncio
async def test_comando_mostra_rientra_nei_limiti_degli_embed(cog_comandi):
    cog, comandi, repo = cog_comandi
    for i in range(25):
        await repo.set_rule(GUILD, "canale_escluso", 10**17 + i)
        await repo.set_rule(GUILD, "ruolo_escluso", 10**17 + i)
        await repo.set_rule(GUILD, "mult_canale", 10**17 + i, 2.0)
        await repo.set_rule(GUILD, "mult_ruolo", 10**17 + i, 2.0)
    interazione = _interazione()

    await comandi["level impostazioni mostra"].callback(cog, interazione)

    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert len(embed) <= 6000
    assert all(len(c.value) <= 1024 for c in embed.fields)
