"""
tests/test_leveling_premi_b2.py
===============================
#124 B2 (LIV-042, 043, 047, 034, 038): più ruoli per livello, ricontrollo dei premi, avviso in DM,
testo dell'annuncio con segnaposto, prova dell'annuncio; resti di B1 (XP di mese e settimana
nel ripristino, copia e azzeramento senza XP persi). Archivio su PostgreSQL vero, oggetti Discord finti.
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import MAX_RUOLI_PER_LIVELLO, rendi_annuncio
from core.repositories.leveling_copie_repo import LevelingCopieRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.level_reward_repo import LevelRewardRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_member, fake_role

GUILD = 100


# ---------------------------------------------------------------- LIV-042 archivio
@pytest.fixture
def premi(clean_db):
    return LevelRewardRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_un_livello_puo_avere_fino_a_tre_ruoli(premi):
    for ruolo in (11, 22, 33):
        assert await premi.add_reward(GUILD, 5, ruolo) is not None
    assert MAX_RUOLI_PER_LIVELLO == 3
    assert await premi.add_reward(GUILD, 5, 44) is None  # il quarto no
    assert [r.role_id for r in await premi.list_rewards(GUILD)] == [11, 22, 33]
    assert await premi.add_reward(GUILD, 6, 44) is not None  # un altro livello sì


@pytest.mark.asyncio
async def test_stesso_ruolo_due_volte_cambia_solo_l_avviso(premi):
    primo = await premi.add_reward(GUILD, 5, 11)
    assert await premi.add_reward(GUILD, 5, 11, avvisa_dm=True) == primo
    rewards = await premi.list_rewards(GUILD)
    assert len(rewards) == 1 and rewards[0].avvisa_dm is True


@pytest.mark.asyncio
async def test_due_comandi_insieme_non_superano_il_tetto(premi, clean_db):
    for ruolo in (1, 2):
        await premi.add_reward(GUILD, 5, ruolo)
    await apri_connessioni(clean_db)
    esiti = await asyncio.gather(*(premi.add_reward(GUILD, 5, 100 + n) for n in range(5)))
    assert sum(e is not None for e in esiti) == 1
    assert len(await premi.list_rewards(GUILD)) == 3


# ---------------------------------------------------------------- LIV-034 testo
def test_segnaposto_dell_annuncio():
    r = rendi_annuncio("{utente} livello {livello} su {server}!{premio: Hai preso {ruolo_premio}.}",
                       utente="<@1>", livello=5, server="Casa", ruoli_premio=["<@&9>", "<@&8>"])
    assert r == "<@1> livello 5 su Casa! Hai preso <@&9>, <@&8>."


def test_il_blocco_premio_sparisce_senza_ruoli():
    r = rendi_annuncio("{utente}{premio: ruolo {ruolo_premio}}.", utente="U", livello=1, server="S", ruoli_premio=[])
    assert r == "U."


def test_un_valore_con_un_segnaposto_non_viene_sostituito_due_volte():
    r = rendi_annuncio("{server}", utente="U", livello=1, server="{utente}", ruoli_premio=[])
    assert r == "{utente}"


def test_testo_lungo_resta_sotto_i_2000():
    assert len(rendi_annuncio("x" * 1800 + "{server}", utente="U", livello=1, server="s" * 500, ruoli_premio=[])) <= 2000


# ---------------------------------------------------------------- B1: ripristino con mese e settimana
@pytest.fixture
def xp(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.fixture
def copie(clean_db):
    return LevelingCopieRepository(pool_provider=lambda: clean_db)


async def _attivita(pool, user):
    return await pool.fetchval(
        "SELECT COALESCE(sum(xp), 0) FROM leveling_activity WHERE guild_id = $1 AND user_id = $2", GUILD, user
    )


@pytest.mark.asyncio
async def test_il_ripristino_rimette_anche_gli_xp_di_mese_e_settimana(xp, copie, clean_db):
    await xp.modifica_xp(GUILD, 1, "aggiungi", 500)
    await xp.add_coins(GUILD, 1, 10)
    await clean_db.execute("UPDATE leveling_activity SET xp = 70 WHERE guild_id = $1", GUILD)
    prima = await _attivita(clean_db, 1)
    esito = await copie.azzera_server(GUILD, 7, "")
    assert await _attivita(clean_db, 1) == 0
    await copie.ripristina(GUILD, esito.copia_id)
    assert await _attivita(clean_db, 1) == prima
    assert (await xp.get_totals(GUILD, 1)).xp_total == 500
    # ripetuto: non toglie e non raddoppia
    await copie.ripristina(GUILD, esito.copia_id)
    assert await _attivita(clean_db, 1) == prima


@pytest.mark.asyncio
async def test_chi_ha_guadagnato_dopo_l_azzeramento_tiene_il_suo_mese(xp, copie, clean_db):
    await xp.modifica_xp(GUILD, 1, "aggiungi", 500)
    await xp.add_coins(GUILD, 1, 10)
    await clean_db.execute("UPDATE leveling_activity SET xp = 70 WHERE guild_id = $1", GUILD)
    esito = await copie.azzera_server(GUILD, 7, "")
    await clean_db.execute("UPDATE leveling_activity SET xp = 90 WHERE guild_id = $1", GUILD)
    await copie.ripristina(GUILD, esito.copia_id)
    assert await clean_db.fetchval("SELECT max(xp) FROM leveling_activity WHERE guild_id = $1", GUILD) == 90


@pytest.mark.asyncio
async def test_nessun_xp_si_perde_tra_copia_e_azzeramento(xp, copie, clean_db):
    """Un messaggio che dà XP mentre si azzera finisce o nella copia o nel totale, mai nel nulla."""
    for u in range(1, 40):
        await xp.modifica_xp(GUILD, u, "aggiungi", 100)
    await apri_connessioni(clean_db)

    async def guadagna():
        for _ in range(20):
            await clean_db.execute(
                "UPDATE leveling_totals SET xp_total = xp_total + 1 WHERE guild_id = $1 AND user_id = 5", GUILD
            )

    esito, _ = await asyncio.gather(copie.azzera_server(GUILD, 7, ""), guadagna())
    copiati = await clean_db.fetchval(
        "SELECT xp_total FROM leveling_copie_righe WHERE copia_id = $1 AND user_id = 5", esito.copia_id
    )
    rimasti = (await xp.get_totals(GUILD, 5)).xp_total
    assert copiati + rimasti == 120


@pytest.mark.asyncio
async def test_ids_copia(xp, copie):
    await xp.modifica_xp(GUILD, 1, "aggiungi", 5)
    await xp.modifica_xp(GUILD, 2, "aggiungi", 5)
    esito = await copie.azzera_server(GUILD, 7, "")
    assert sorted(await copie.ids_copia(GUILD, esito.copia_id)) == [1, 2]
    assert await copie.ids_copia(GUILD + 1, esito.copia_id) == []


# ---------------------------------------------------------------- scena dei ruoli (cog)
def _bot(manage_roles=True):
    return fake_member(
        999, bot=True, guild_permissions=discord.Permissions(manage_roles=manage_roles),
        roles=[fake_role(role_id=1, name="bot", position=50)],
    )


@pytest.fixture
def scena(monkeypatch, premi):
    ruoli = {r: fake_role(role_id=r, name=f"r{r}", position=1) for r in (11, 22, 33)}
    guild = fake_guild(GUILD, me=_bot())
    guild.get_role = lambda rid: ruoli.get(rid)
    monkeypatch.setattr(modulo, "level_reward_repo", premi)
    cog = modulo.LevelingCog.__new__(modulo.LevelingCog)
    membro = fake_member(5, name="u5")
    membro.add_roles = AsyncMock()
    membro.remove_roles = AsyncMock()
    membro.send = AsyncMock()
    return cog, guild, membro, ruoli, premi


@pytest.mark.asyncio
async def test_due_ruoli_dello_stesso_livello_si_danno_con_una_sola_chiamata(scena):
    cog, guild, membro, ruoli, premi = scena
    await premi.add_reward(GUILD, 5, 11)
    await premi.add_reward(GUILD, 5, 22)
    assert await cog._grant_level_rewards(membro, guild, 5)
    membro.add_roles.assert_awaited_once()
    assert set(membro.add_roles.await_args.args) == {ruoli[11], ruoli[22]}


@pytest.mark.asyncio
async def test_il_dm_parte_solo_per_i_ruoli_con_avviso_e_solo_se_richiesto(scena):
    cog, guild, membro, ruoli, premi = scena
    await premi.add_reward(GUILD, 5, 11, avvisa_dm=True)
    await premi.add_reward(GUILD, 5, 22)
    await cog._grant_level_rewards(membro, guild, 5)  # ricontrollo: niente DM
    membro.send.assert_not_awaited()
    membro.add_roles.reset_mock()
    membro.roles = []
    await cog._grant_level_rewards(membro, guild, 5, avvisa=True)
    membro.send.assert_awaited_once()
    assert "r11" in membro.send.await_args.args[0] and "r22" not in membro.send.await_args.args[0]


@pytest.mark.asyncio
async def test_dm_chiusi_non_danno_errore_e_non_si_ripetono(scena):
    cog, guild, membro, ruoli, premi = scena
    await premi.add_reward(GUILD, 5, 11, avvisa_dm=True)
    membro.send.side_effect = discord.Forbidden(MagicMock(status=403), "chiusi")
    assert await cog._grant_level_rewards(membro, guild, 5, avvisa=True) is True
    membro.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_senza_gestire_ruoli_il_bot_salta_e_non_chiama_discord(scena):
    cog, guild, membro, ruoli, premi = scena
    guild.me = _bot(manage_roles=False)
    await premi.add_reward(GUILD, 5, 11)
    assert await cog._grant_level_rewards(membro, guild, 5) is False
    membro.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_ruolo_sopra_il_bot_saltato_senza_chiamare_discord(scena):
    cog, guild, membro, ruoli, premi = scena
    ruoli[11].position = 60
    await premi.add_reward(GUILD, 5, 11)
    await cog._grant_level_rewards(membro, guild, 5)
    membro.add_roles.assert_not_awaited()


# ---------------------------------------------------------------- LIV-043 ricontrollo
@pytest.mark.asyncio
async def test_sincronizza_premi_una_volta_ogni_dieci_minuti(scena, monkeypatch):
    cog, guild, membro, ruoli, premi = scena
    cog._config = AsyncMock(return_value=modulo.ConfigLivelli())
    monkeypatch.setattr(modulo.leveling_repo, "get_totals", AsyncMock(return_value=MagicMock(level=7)))
    cog._grant_level_rewards = AsyncMock(return_value=True)
    assert await cog.sincronizza_premi(guild, membro)
    assert await cog.sincronizza_premi(guild, membro) is None  # pausa
    cog._grant_level_rewards.assert_awaited_once()
    assert cog._grant_level_rewards.await_args.kwargs["togli_superiori"] is True
    await cog.sincronizza_premi(guild, membro, forza=True)
    assert cog._grant_level_rewards.await_count == 2
    await cog.sincronizza_premi(guild, fake_member(6, bot=True))  # i bot no
    assert cog._grant_level_rewards.await_count == 2


@pytest.mark.asyncio
async def test_sincronizza_server_a_lotti_con_pausa(scena, monkeypatch):
    cog, guild, membro, ruoli, premi = scena
    await premi.add_reward(GUILD, 5, 11)
    ruoli[11].members = [fake_member(1), fake_member(2)]
    guild.get_member = lambda uid: fake_member(uid) if uid in (2, 3) else None
    cog.sincronizza_premi = AsyncMock()
    pause = []
    monkeypatch.setattr(modulo.asyncio, "sleep", AsyncMock(side_effect=lambda s: pause.append(s)))
    monkeypatch.setattr(modulo, "LOTTO_SINCRONIA", 2)
    await cog.sincronizza_server(guild, [2, 3, 4])
    chiamati = sorted(c.args[1].id for c in cog.sincronizza_premi.await_args_list)
    assert chiamati == [1, 2, 3]  # chi tiene il ruolo e chi era nella copia, una volta sola
    assert all(c.kwargs["forza"] for c in cog.sincronizza_premi.await_args_list)
    assert pause  # almeno una pausa tra i lotti


@pytest.mark.asyncio
async def test_all_ingresso_i_premi_si_ricontrollano_solo_a_modulo_acceso(scena, monkeypatch, clean_db):
    from tests.support.moduli import attiva_livelli

    cog, guild, membro, ruoli, premi = scena
    cog.sincronizza_premi = AsyncMock()
    membro.guild = guild
    await attiva_livelli(monkeypatch, clean_db)
    await cog.on_member_join(membro)
    cog.sincronizza_premi.assert_not_awaited()
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    await cog.on_member_join(membro)
    cog.sincronizza_premi.assert_awaited_once()


# ---------------------------------------------------------------- LIV-042 comando e Premium
async def _aggiungi(cog, guild, livello, ruolo, **kw):
    admin = fake_member(1, roles=[fake_role(role_id=2000, name="Admin", position=90)])
    admin.top_role = admin.roles[0]
    inter = MagicMock()
    inter.guild, inter.user = guild, admin
    inter.response.send_message = AsyncMock()
    inter.response.is_done.return_value = False
    await cog.level_roles_add.callback(cog, inter, livello, ruolo, **kw)
    return inter.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_il_quarto_ruolo_dello_stesso_livello_e_rifiutato(scena, monkeypatch, clean_db):
    from tests.support.moduli import attiva_livelli

    cog, guild, membro, ruoli, premi = scena
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    ruoli[44] = fake_role(role_id=44, name="r44", position=1)
    for r in (11, 22, 33):
        await _aggiungi(cog, guild, 5, ruoli[r])
    testo = await _aggiungi(cog, guild, 5, ruoli[44])
    assert "3" in testo and len(await premi.list_rewards(GUILD)) == 3


@pytest.mark.asyncio
async def test_piu_ruoli_per_livello_premium_il_primo_resta_libero(scena, monkeypatch, clean_db):
    from core import livelli_funzione as lf
    from tests.support.moduli import attiva_livelli

    cog, guild, membro, ruoli, premi = scena
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(lf, "_livelli", {"livelli_piu_ruoli": lf.PREMIUM})
    monkeypatch.setattr(lf, "ha_livello", AsyncMock(return_value=False))
    await _aggiungi(cog, guild, 5, ruoli[11])
    testo = await _aggiungi(cog, guild, 5, ruoli[22])
    assert "Premium" in testo
    assert [r.role_id for r in await premi.list_rewards(GUILD)] == [11]
    lf.ha_livello.return_value = True
    await _aggiungi(cog, guild, 5, ruoli[22])
    assert len(await premi.list_rewards(GUILD)) == 2


@pytest.mark.asyncio
async def test_tutto_gratuito_di_base(scena, monkeypatch, clean_db):
    from core import livelli_funzione as lf

    assert lf.livello_di("livelli_piu_ruoli") == lf.GRATUITO
    assert "livelli_piu_ruoli" in lf.FUNZIONI


# ---------------------------------------------------------------- LIV-034 annuncio con testo
@pytest.fixture
def annuncio(scena, monkeypatch):
    cog, guild, membro, ruoli, premi = scena
    monkeypatch.setattr(modulo.leveling_repo, "registra_level_up", AsyncMock())
    canale = MagicMock()
    canale.send = AsyncMock()
    return cog, guild, membro, premi, canale


@pytest.mark.asyncio
async def test_annuncio_con_testo_del_server_e_solo_l_utente_si_menziona(annuncio):
    cog, guild, membro, premi, canale = annuncio
    await premi.add_reward(GUILD, 5, 11)
    imp = modulo.LevelingSettings(levelup_testo="{utente} è al {livello}!{premio: Ha preso {ruolo_premio}}")
    await cog._annuncia_level_up(membro, guild, canale, 5, imp, 4)
    canale.send.assert_awaited_once()
    assert canale.send.await_args.args[0] == "<@5> è al 5! Ha preso <@&11>"
    permessi = canale.send.await_args.kwargs["allowed_mentions"]
    assert permessi.roles is False and permessi.everyone is False and permessi.users == [membro]


@pytest.mark.asyncio
async def test_senza_premio_il_blocco_non_compare_e_senza_testo_vale_quello_di_base(annuncio):
    cog, guild, membro, premi, canale = annuncio
    await premi.add_reward(GUILD, 9, 11)
    imp = modulo.LevelingSettings(levelup_testo="{utente}{premio: ruolo {ruolo_premio}}.")
    await cog._annuncia_level_up(membro, guild, canale, 5, imp, 4)
    assert canale.send.await_args.args[0] == "<@5>."
    canale.send.reset_mock()
    await cog._annuncia_level_up(membro, guild, canale, 5, modulo.LevelingSettings(), 4)
    assert "livello **5**" in canale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_un_salto_di_livelli_conta_il_premio_di_un_livello_saltato(annuncio):
    cog, guild, membro, premi, canale = annuncio
    await premi.add_reward(GUILD, 6, 11)
    imp = modulo.LevelingSettings(levelup_testo="{premio:P}x")
    await cog._annuncia_level_up(membro, guild, canale, 8, imp, 4)
    assert canale.send.await_args.args[0] == "Px"


# ---------------------------------------------------------------- LIV-038 prova
@pytest.fixture
async def prova(monkeypatch, clean_db, scena):
    from core.repositories.leveling_settings_repo import leveling_settings_repo
    from tests.support.moduli import attiva_livelli

    cog, guild, membro, ruoli, premi = scena
    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_settings_repo", leveling_settings_repo)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)
    canale = MagicMock()
    canale.id = 111
    canale.mention = "<#111>"
    canale.send = AsyncMock()
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True)
    guild.get_channel = lambda cid: canale if cid == 111 else None
    inter = MagicMock()
    inter.guild, inter.user, inter.channel = guild, fake_member(1), canale
    inter.response.send_message = AsyncMock()
    inter.response.is_done.return_value = False
    cog.__dict__.pop("_prove", None)
    yield cog, inter, canale, leveling_settings_repo
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=10)


async def _lancia(cog, inter, **kw):
    argomenti = dict(modo=None, canale=None, livello_minimo=None, ogni=None, solo_premi=None,
                     testo=None, testo_base=None, prova=None)
    argomenti.update(kw)
    await cog.impostazioni_annuncio.callback(cog, inter, **argomenti)
    return inter.response.send_message.await_args


@pytest.mark.asyncio
async def test_prova_manda_un_annuncio_finto_nel_canale_scelto(prova):
    cog, inter, canale, repo = prova
    await repo.set_options(GUILD, levelup_mode="canale_scelto", levelup_channel_id=111,
                           levelup_testo="Bravo {utente}, livello {livello}!")
    await _lancia(cog, inter, prova=True)
    canale.send.assert_awaited_once()
    assert "<@1>" in canale.send.await_args.args[0] and "Bravo" in canale.send.await_args.args[0]
    assert canale.send.await_args.kwargs["allowed_mentions"].roles is False


@pytest.mark.asyncio
async def test_seconda_prova_entro_cinque_minuti_e_rifiutata(prova):
    cog, inter, canale, repo = prova
    await _lancia(cog, inter, prova=True)
    await _lancia(cog, inter, prova=True)
    canale.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_prova_senza_permesso_di_scrittura_non_scrive(prova):
    cog, inter, canale, repo = prova
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=False)
    await _lancia(cog, inter, prova=True)
    canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_prova_con_annuncio_spento_lo_dice_e_non_scrive(prova):
    cog, inter, canale, repo = prova
    await repo.set_options(GUILD, levelup_mode="spento")
    await _lancia(cog, inter, prova=True)
    canale.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_testo_salvato_e_riportato_a_quello_di_base(prova):
    cog, inter, canale, repo = prova
    await _lancia(cog, inter, testo="Ciao {utente}")
    assert (await repo.get_config(GUILD, fresco=True)).impostazioni.levelup_testo == "Ciao {utente}"
    await _lancia(cog, inter, testo_base=True)
    assert (await repo.get_config(GUILD, fresco=True)).impostazioni.levelup_testo == ""
