"""
tests/test_leveling_gestione_staff.py
=====================================
LIV-064..067 (XP a mano: aggiungi, togli, livello, XP nel livello, azzera),
LIV-041 (ruolo-premio tolto a chi scende), ECO-009 e ECO-011 (monete a mano,
azzera saldo). Archivio su PostgreSQL vero; i comandi stanno sotto
`/economia`.
Funzioni coperte: SPEC §15 (catalogo #124 e #125)
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

import cogs.leveling.leveling as modulo
from core.leveling_logic import level_for_xp, xp_dopo_modifica, xp_for_level
from core.repositories.level_reward_repo import LevelReward
from core.repositories.leveling_repo import LevelingRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
)
from tests.support.moduli import attiva_livelli

GUILD = 100


# ----------------------------------------------------------------------
# Logica pura
# ----------------------------------------------------------------------
def test_xp_dopo_modifica():
    base = xp_for_level(3) + 20
    assert xp_dopo_modifica(base, "aggiungi", 30) == base + 30
    assert xp_dopo_modifica(base, "togli", 30) == base - 30
    assert xp_dopo_modifica(10, "togli", 500) == 0  # mai sotto zero
    assert xp_dopo_modifica(base, "livello", 5) == xp_for_level(5)
    assert xp_dopo_modifica(base, "azzera", 0) == 0
    # XP dentro il livello corrente: il livello non cambia, anche con un valore enorme.
    dopo = xp_dopo_modifica(base, "xp_nel_livello", 7)
    assert (level_for_xp(dopo), dopo - xp_for_level(3)) == (3, 7)
    dopo = xp_dopo_modifica(base, "xp_nel_livello", 10_000_000)
    assert level_for_xp(dopo) == 3
    with pytest.raises(ValueError):
        xp_dopo_modifica(base, "inventata", 1)


def test_il_livello_impostato_rispetta_il_tetto():
    assert xp_dopo_modifica(0, "livello", 50, max_level=10) == xp_for_level(10)


# ----------------------------------------------------------------------
# Archivio
# ----------------------------------------------------------------------
@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_modifica_xp_salva_xp_e_livello_ma_non_la_classifica_del_mese(repo, clean_db):
    risultato = await repo.modifica_xp(GUILD, 1, "livello", 4)
    assert (risultato.livello_dopo, risultato.xp_dopo) == (4, xp_for_level(4))
    totali = await repo.get_totals(GUILD, 1)
    assert (totali.level, totali.xp_total) == (4, xp_for_level(4))
    # Un dono dello staff non è attività del mese.
    assert await clean_db.fetchval("SELECT count(*) FROM leveling_activity WHERE guild_id = $1", GUILD) == 0

    risultato = await repo.modifica_xp(GUILD, 1, "togli", 10_000_000)
    assert (risultato.xp_dopo, risultato.livello_dopo, risultato.livello_prima) == (0, 0, 4)


@pytest.mark.asyncio
async def test_modifica_xp_non_tocca_le_monete_ne_gli_altri(repo):
    await repo.add_coins(GUILD, 1, 50)
    await repo.add_coins(GUILD, 2, 70)
    await repo.modifica_xp(GUILD, 1, "aggiungi", 100)
    assert (await repo.get_totals(GUILD, 1)).coins_total == 50
    assert (await repo.get_totals(GUILD, 2)).xp_total == 0


@pytest.mark.asyncio
async def test_due_modifiche_insieme_non_si_perdono(repo, clean_db):
    await apri_connessioni(clean_db)
    await asyncio.gather(*(repo.modifica_xp(GUILD, 1, "aggiungi", 10) for _ in range(8)))
    assert (await repo.get_totals(GUILD, 1)).xp_total == 80


@pytest.mark.asyncio
async def test_modifica_monete(repo):
    r = await repo.modifica_monete(GUILD, 1, "aggiungi", 100)
    assert (r.prima, r.dopo) == (0, 100)
    r = await repo.modifica_monete(GUILD, 1, "togli", 30)
    assert (r.prima, r.dopo) == (100, 70)
    r = await repo.modifica_monete(GUILD, 1, "togli", 500)  # mai un saldo negativo
    assert r.dopo == 0
    r = await repo.modifica_monete(GUILD, 1, "imposta", 42)
    assert r.dopo == 42
    r = await repo.modifica_monete(GUILD, 1, "azzera", 0)
    assert (r.prima, r.dopo) == (42, 0)
    assert (await repo.get_totals(GUILD, 1)).coins_total == 0
    with pytest.raises(ValueError):
        await repo.modifica_monete(GUILD, 1, "inventata", 1)


@pytest.mark.asyncio
async def test_monete_a_mano_non_contano_nella_classifica_del_mese(repo, clean_db):
    await repo.modifica_monete(GUILD, 1, "aggiungi", 500)
    assert await clean_db.fetchval("SELECT count(*) FROM leveling_activity WHERE guild_id = $1", GUILD) == 0


@pytest.mark.asyncio
async def test_togli_monete_insieme_non_porta_il_saldo_sotto_zero(repo, clean_db):
    await apri_connessioni(clean_db)
    await repo.modifica_monete(GUILD, 1, "aggiungi", 100)
    await asyncio.gather(*(repo.modifica_monete(GUILD, 1, "togli", 30) for _ in range(6)))
    assert (await repo.get_totals(GUILD, 1)).coins_total == 0


# ----------------------------------------------------------------------
# Ruoli-premio
# ----------------------------------------------------------------------
@pytest.fixture
def scena_ruoli(monkeypatch):
    from core.repositories.level_reward_repo import level_reward_repo

    ruoli = {r: fake_role(role_id=r, name=f"r{r}", position=1) for r in (50, 100)}
    bot_member = fake_member(
        user_id=999, bot=True, roles=[fake_role(role_id=1, name="bot", position=50)]
    )
    guild = fake_guild(GUILD)
    guild.me = bot_member
    guild.get_role = lambda rid: ruoli.get(rid)
    membro = fake_member(user_id=5, roles=[ruoli[50], ruoli[100]])
    membro.add_roles = AsyncMock()
    membro.remove_roles = AsyncMock()
    tutti = [
        LevelReward(id=1, guild_id=GUILD, level_threshold=5, role_id=50, created_at=None),
        LevelReward(id=2, guild_id=GUILD, level_threshold=10, role_id=100, created_at=None),
    ]

    async def fino_a(guild_id, livello):
        return [r for r in tutti if r.level_threshold <= livello]

    async def elenco(guild_id):
        return tutti

    monkeypatch.setattr(level_reward_repo, "get_rewards_up_to_level", fino_a)
    monkeypatch.setattr(level_reward_repo, "list_rewards", elenco)
    cog = modulo.LevelingCog.__new__(modulo.LevelingCog)
    return cog, guild, membro, ruoli


@pytest.mark.asyncio
async def test_chi_scende_perde_i_ruoli_dei_livelli_che_non_ha_piu(scena_ruoli):
    cog, guild, membro, ruoli = scena_ruoli

    await cog._grant_level_rewards(membro, guild, 6, "accumula", togli_superiori=True)

    membro.remove_roles.assert_awaited_once()
    assert membro.remove_roles.await_args.args == (ruoli[100],)


@pytest.mark.asyncio
async def test_a_livello_zero_si_tolgono_tutti_i_ruoli_premio(scena_ruoli):
    cog, guild, membro, ruoli = scena_ruoli

    await cog._grant_level_rewards(membro, guild, 0, "accumula", togli_superiori=True)

    assert set(membro.remove_roles.await_args.args) == {ruoli[50], ruoli[100]}


@pytest.mark.asyncio
async def test_senza_togli_superiori_nulla_viene_tolto(scena_ruoli):
    cog, guild, membro, ruoli = scena_ruoli

    await cog._grant_level_rewards(membro, guild, 6, "accumula")

    membro.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_lo_staff_non_tocca_ruoli_premio_sopra_il_suo(scena_ruoli):
    cog, guild, membro, ruoli = scena_ruoli
    ruoli[50].position = 5
    ruoli[100].position = 30
    staff = fake_member(user_id=1, roles=[fake_role(role_id=7, name="staff", position=10)])

    await cog._grant_level_rewards(
        membro, guild, 0, "accumula", togli_superiori=True, esecutore=staff
    )

    # Il ruolo a posizione 30 supera quello dello staff (10): resta al membro.
    assert membro.remove_roles.await_args.args == (ruoli[50],)


@pytest.mark.asyncio
async def test_lo_staff_non_assegna_ruoli_premio_sopra_il_suo(scena_ruoli):
    cog, guild, membro, ruoli = scena_ruoli
    membro.roles = []
    ruoli[50].position = 5
    ruoli[100].position = 30
    staff = fake_member(user_id=1, roles=[fake_role(role_id=7, name="staff", position=10)])

    await cog._grant_level_rewards(membro, guild, 20, "accumula", esecutore=staff)

    assert membro.add_roles.await_args.args == (ruoli[50],)


@pytest.mark.asyncio
async def test_il_proprietario_non_ha_il_limite_di_gerarchia(scena_ruoli):
    cog, guild, membro, ruoli = scena_ruoli
    ruoli[100].position = 30
    guild.owner_id = 1
    owner = fake_member(user_id=1, roles=[fake_role(role_id=7, name="staff", position=10)])

    await cog._grant_level_rewards(
        membro, guild, 0, "accumula", togli_superiori=True, esecutore=owner
    )

    assert set(membro.remove_roles.await_args.args) == {ruoli[50], ruoli[100]}


def test_level_for_xp_non_cicla_e_coincide_con_la_definizione():
    import time

    for xp in (0, 1, 54, 55, 56, 10_000, xp_for_level(777), xp_for_level(777) - 1):
        liv = level_for_xp(xp)
        assert xp_for_level(liv) <= xp < xp_for_level(liv + 1)
    inizio = time.perf_counter()
    assert level_for_xp(5 * 10**15) > 10**7
    assert level_for_xp(5 * 10**15, max_level=40) == 40
    assert time.perf_counter() - inizio < 0.5


def test_il_livello_impostato_a_mano_ha_un_tetto_assoluto():
    from core.leveling_logic import LIVELLO_MASSIMO

    assert xp_dopo_modifica(0, "livello", 10_000_000) == xp_for_level(LIVELLO_MASSIMO)


@pytest.mark.asyncio
async def test_comando_xp_rifiuta_livelli_oltre_il_massimo(cog_comandi):
    cog, comandi, repo, _ = cog_comandi
    interazione = _interazione()

    await comandi["economia xp"].callback(
        cog, interazione, azione=_scelta("livello"), membro=fake_member(user_id=9), valore=5000
    )

    assert (await repo.get_totals(GUILD, 9)).xp_total == 0
    assert "massimo" in interazione.response.send_message.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_comando_xp_passa_lesecutore_ai_ruoli(cog_comandi):
    cog, comandi, repo, sincronizza = cog_comandi
    interazione = _interazione()

    await comandi["economia xp"].callback(
        cog, interazione, azione=_scelta("livello"), membro=fake_member(user_id=9), valore=3
    )

    assert sincronizza.await_args.kwargs.get("esecutore") is interazione.user


# ----------------------------------------------------------------------
# Comandi
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_comandi(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    monkeypatch.setattr(leveling_settings_repo, "_pool_provider", lambda: clean_db)
    leveling_settings_repo._cache = type(leveling_settings_repo._cache)(max_size=100)
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", repo)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    sincronizza = AsyncMock()
    monkeypatch.setattr(modulo.LevelingCog, "_grant_level_rewards", sincronizza)
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return cog, comandi, repo, sincronizza


def _interazione():
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(1))


def _scelta(valore):
    return type("C", (), {"value": valore})()


@pytest.mark.asyncio
async def test_i_comandi_stanno_sotto_economia(cog_comandi):
    _, comandi, _, _ = cog_comandi
    assert "economia xp" in comandi
    assert "economia monete" in comandi


@pytest.mark.asyncio
async def test_comando_xp_risponde_dopo_defer_e_allinea_i_ruoli(cog_comandi):
    cog, comandi, repo, sincronizza = cog_comandi
    interazione = _interazione()
    membro = fake_member(user_id=9)

    await comandi["economia xp"].callback(
        cog, interazione, azione=_scelta("livello"), membro=membro, valore=6
    )

    interazione.response.defer.assert_awaited_once()
    assert (await repo.get_totals(GUILD, 9)).level == 6
    sincronizza.assert_awaited_once()
    assert sincronizza.await_args.kwargs.get("togli_superiori") is True
    assert sincronizza.await_args.args[2] == 6
    assert "livello" in interazione.followup.send.await_args.args[0].lower()


@pytest.mark.asyncio
async def test_comando_xp_rifiuta_i_bot(cog_comandi):
    cog, comandi, repo, _ = cog_comandi
    interazione = _interazione()
    bot = fake_member(user_id=9, bot=True)

    await comandi["economia xp"].callback(
        cog, interazione, azione=_scelta("aggiungi"), membro=bot, valore=10
    )

    assert (await repo.get_totals(GUILD, 9)).xp_total == 0


@pytest.mark.asyncio
async def test_comando_monete_aggiunge_e_azzera(cog_comandi):
    cog, comandi, repo, _ = cog_comandi
    membro = fake_member(user_id=9)

    await comandi["economia monete"].callback(
        cog, _interazione(), azione=_scelta("aggiungi"), membro=membro, importo=250
    )
    assert (await repo.get_totals(GUILD, 9)).coins_total == 250

    interazione = _interazione()
    await comandi["economia monete"].callback(
        cog, interazione, azione=_scelta("azzera"), membro=membro, importo=None
    )
    assert (await repo.get_totals(GUILD, 9)).coins_total == 0
    assert "250" in interazione.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_comando_monete_senza_importo_non_scrive(cog_comandi):
    cog, comandi, repo, _ = cog_comandi
    interazione = _interazione()

    await comandi["economia monete"].callback(
        cog, interazione, azione=_scelta("aggiungi"), membro=fake_member(user_id=9), importo=None
    )

    assert (await repo.get_totals(GUILD, 9)).coins_total == 0
    assert "importo" in interazione.response.send_message.await_args.args[0].lower()
