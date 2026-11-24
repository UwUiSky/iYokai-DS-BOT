"""
tests/test_creature_eco101.py
=============================
Creature di fantasia comprate al negozio e scontri con posta (ECO-101): forza 50-70 alla nascita, +1 a ogni
vittoria fino a 90, -10 a ogni sconfitta (sotto 30 la creatura fugge), posta atomica, nessuna moneta creata.
PostgreSQL vero.
Funzioni coperte: ECO-101
"""

import asyncio
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.fun.creature import CreatureCog, ScontroView
from core import creature_logic as cl
from core.repositories.creature_repo import CreatureRepository, EsitoEvoca, EsitoScontro
from core.repositories.inventario_repo import InventarioRepository
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from core.repositories.shop_repo import ShopRepository
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G = 100


def nessuno_in_blacklist(monkeypatch) -> None:
    from core import ui_base

    async def nessuno(interaction):
        return False
    monkeypatch.setattr(ui_base, "_utente_o_server_in_blacklist", nessuno)


class Fisso(random.Random):
    """`random()` sempre uguale: 0.0 fa vincere il primo, 0.999 lo fa perdere."""

    def __init__(self, valore: float) -> None:
        super().__init__(1)
        self.valore = valore

    def random(self) -> float:
        return self.valore


@pytest.fixture
def r(clean_db):
    return SimpleNamespace(
        c=CreatureRepository(pool_provider=lambda: clean_db), lev=LevelingRepository(pool_provider=lambda: clean_db),
        imp=LevelingSettingsRepository(pool_provider=lambda: clean_db), shop=ShopRepository(pool_provider=lambda: clean_db),
        inv=InventarioRepository(pool_provider=lambda: clean_db), pool=clean_db,
    )


async def _crea(r, user, forza=60, specie=1):
    return await r.pool.fetchval(
        "INSERT INTO economia_creature (guild_id, user_id, specie, forza) VALUES ($1, $2, $3, $4) RETURNING id", G, user, specie, forza
    )


async def _forza(r, cid):
    return await r.pool.fetchval("SELECT forza FROM economia_creature WHERE id = $1", cid)


async def _saldi(r, utenti):
    return [(await r.lev.get_totals(G, u)).coins_total for u in utenti]


def test_regole_della_forza():
    rng = random.Random(3)
    nascite = {cl.forza_iniziale(rng) for _ in range(500)}
    assert min(nascite) == 50 and max(nascite) == 70
    assert cl.dopo_vittoria(60) == 61 and cl.dopo_vittoria(90) == 90 and cl.dopo_vittoria(89) == 90
    assert cl.dopo_sconfitta(60) == (50, False) and cl.dopo_sconfitta(40) == (30, False) and cl.dopo_sconfitta(39) == (29, True)
    assert cl.probabilita_vittoria(60, 60) == 0.5 and cl.probabilita_vittoria(90, 30) == 0.75
    forti = sum(cl.vince_il_primo(70, 50, random.Random(s)) for s in range(1000))
    assert 540 < forti < 660  # 70/120 = 58%
    assert len(cl.SPECIE) == 8 and cl.nome_specie(1) == cl.SPECIE[0]
    with pytest.raises(ValueError):
        cl.nome_specie(0)


@pytest.mark.asyncio
async def test_evoca_consuma_il_pezzo_e_crea_la_creatura(r):
    item = await r.pool.fetchval(
        "INSERT INTO shop_items (guild_id, name, price, azione, azione_valore) VALUES ($1, 'Uovo', 10, 'creatura', 2) RETURNING id", G
    )
    await r.pool.execute("INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, 1, $2, 1)", G, item)
    e = await r.c.evoca(G, 1, item, random.Random(1))
    assert e.esito is EsitoEvoca.FATTO and 50 <= e.forza <= 70
    assert await r.pool.fetchval("SELECT count(*) FROM economia_inventario WHERE item_id = $1", item) == 0  # pezzo consumato
    assert [x["specie"] for x in await r.c.elenco(G, 1)] == [2]
    assert (await r.c.evoca(G, 1, item, random.Random(1))).esito is EsitoEvoca.NON_HAI
    assert len(await r.c.elenco(G, 1)) == 1


@pytest.mark.asyncio
async def test_evoca_con_la_scorta_piena_non_consuma_il_pezzo(r):
    item = await r.pool.fetchval(
        "INSERT INTO shop_items (guild_id, name, price, azione, azione_valore) VALUES ($1, 'Uovo', 10, 'creatura', 1) RETURNING id", G
    )
    await r.pool.execute("INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, 1, $2, 9)", G, item)
    for _ in range(cl.MAX_CREATURE):
        assert (await r.c.evoca(G, 1, item, random.Random(2))).esito is EsitoEvoca.FATTO
    assert (await r.c.evoca(G, 1, item, random.Random(2))).esito is EsitoEvoca.PIENO
    assert await r.pool.fetchval("SELECT quantita FROM economia_inventario WHERE item_id = $1", item) == 9 - cl.MAX_CREATURE


@pytest.mark.asyncio
async def test_evoca_insieme_non_supera_il_tetto(r):
    item = await r.pool.fetchval(
        "INSERT INTO shop_items (guild_id, name, price, azione, azione_valore) VALUES ($1, 'Uovo', 10, 'creatura', 1) RETURNING id", G
    )
    await r.pool.execute("INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, 1, $2, 20)", G, item)
    await apri_connessioni(r.pool, 10)
    await asyncio.gather(*[r.c.evoca(G, 1, item, random.Random(i)) for i in range(10)])
    assert len(await r.c.elenco(G, 1)) == cl.MAX_CREATURE
    assert await r.pool.fetchval("SELECT quantita FROM economia_inventario WHERE item_id = $1", item) == 20 - cl.MAX_CREATURE


@pytest.mark.asyncio
async def test_scontro_sposta_la_posta_e_cambia_le_forze(r):
    a, b = await _crea(r, 1, 60), await _crea(r, 2, 60)
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    e = await r.c.scontra(G, 1, a, 2, b, 40, Fisso(0.0))
    assert e.esito is EsitoScontro.FATTO and e.importo == 40
    assert e.vince_sfidante is True
    vinc, perd = a, b
    assert await _forza(r, vinc) == 61 and await _forza(r, perd) == 50
    saldi = await _saldi(r, [1, 2])
    assert sorted(saldi) == [60, 140] and sum(saldi) == 200
    assert await r.pool.fetchval("SELECT vittorie FROM economia_creature WHERE id = $1", vinc) == 1


@pytest.mark.asyncio
async def test_la_creatura_sconfitta_troppo_debole_fugge(r):
    a, b, c = await _crea(r, 1, 39), await _crea(r, 2, 90), await _crea(r, 1, 40)
    await r.lev.add_coins(G, 1, 10)
    await r.lev.add_coins(G, 2, 10)
    e = await r.c.scontra(G, 1, a, 2, b, 1, Fisso(0.999))
    assert e.vince_sfidante is False and e.perdente_persa is True
    assert await r.pool.fetchval("SELECT count(*) FROM economia_creature WHERE id = $1", a) == 0
    assert await _forza(r, b) == 90  # tetto
    e = await r.c.scontra(G, 1, c, 2, b, 1, Fisso(0.999))  # 40 -> 30: resta
    assert e.perdente_persa is False and await _forza(r, c) == 30
    assert (await r.c.scontra(G, 1, a, 2, b, 1, Fisso(0.0))).esito is EsitoScontro.CREATURA_NON_VALIDA  # non esiste più


@pytest.mark.asyncio
async def test_scontro_rifiuta_creature_altrui_stessi_proprietari_e_poste_brutte(r):
    a, b, c = await _crea(r, 1), await _crea(r, 2), await _crea(r, 1)
    await r.lev.add_coins(G, 1, 50)
    await r.lev.add_coins(G, 2, 50)
    assert (await r.c.scontra(G, 1, b, 2, a, 10, random.Random(1))).esito is EsitoScontro.CREATURA_NON_VALIDA  # scambiate
    assert (await r.c.scontra(G + 1, 1, a, 2, b, 10, random.Random(1))).esito is EsitoScontro.CREATURA_NON_VALIDA  # altro server
    with pytest.raises(ValueError):
        await r.c.scontra(G, 1, a, 1, c, 10, random.Random(1))  # contro se stessi
    for brutta in (0, -3, 100_001):
        with pytest.raises(ValueError):
            await r.c.scontra(G, 1, a, 2, b, brutta, random.Random(1))
    assert await _saldi(r, [1, 2]) == [50, 50]
    assert await _forza(r, a) == 60


@pytest.mark.asyncio
async def test_scontro_senza_la_posta_non_scrive_niente(r):
    a, b = await _crea(r, 1), await _crea(r, 2)
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 5)
    assert (await r.c.scontra(G, 1, a, 2, b, 50, random.Random(1))).esito is EsitoScontro.POCHE_SFIDATO
    assert (await r.c.scontra(G, 2, b, 1, a, 50, random.Random(1))).esito is EsitoScontro.POCHE_SFIDANTE
    assert await _saldi(r, [1, 2]) == [100, 5] and await _forza(r, a) == 60 and await _forza(r, b) == 60


@pytest.mark.asyncio
async def test_scontri_insieme_non_creano_monete_ne_saldi_negativi(r):
    a, b = await _crea(r, 1, 70), await _crea(r, 2, 70)
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    await apri_connessioni(r.pool, 8)
    esiti = await asyncio.gather(*[r.c.scontra(G, 1, a, 2, b, 100, random.Random(i)) for i in range(8)], return_exceptions=True)
    assert not [e for e in esiti if isinstance(e, Exception)]
    saldi = await _saldi(r, [1, 2])
    assert sum(saldi) == 200 and min(saldi) >= 0
    fatti = [e for e in esiti if e.esito is EsitoScontro.FATTO]
    assert len(fatti) >= 1
    assert await r.pool.fetchval("SELECT count(*) FROM economia_lotte_creature") == len(fatti)


@pytest.mark.asyncio
async def test_il_tetto_al_saldo_limita_il_guadagno(r):
    a, b = await _crea(r, 1, 90), await _crea(r, 2, 50)
    await r.lev.add_coins(G, 1, 100)
    await r.lev.add_coins(G, 2, 100)
    await r.imp.set_options(G, tetto_saldo=120)
    e = await r.c.scontra(G, 1, a, 2, b, 100, Fisso(0.0))
    assert e.importo == 20 and await _saldi(r, [1, 2]) == [120, 80]
    assert await _forza(r, a) == 90 and await _forza(r, b) == 40  # la forza non supera il tetto


@pytest.mark.asyncio
async def test_vista_solo_lo_sfidato_sceglie_e_una_volta_sola(r, monkeypatch):
    nessuno_in_blacklist(monkeypatch)
    a, b = await _crea(r, 1), await _crea(r, 2)
    await r.lev.add_coins(G, 1, 50)
    await r.lev.add_coins(G, 2, 50)
    import cogs.fun.creature as modulo
    monkeypatch.setattr(modulo, "creature_repo", r.c)
    sfidante, sfidato = fake_member(1), fake_member(2)
    view = ScontroView(G, sfidante, a, sfidato, 30, "coin", [(b, "Kappa")])
    ladro = fake_interaction(guild=fake_guild(G), user=sfidante)
    await view.scegli.callback(ladro)
    assert ladro.response.send_message.await_args.kwargs["ephemeral"] is True
    assert await _saldi(r, [1, 2]) == [50, 50]
    estraneo = fake_interaction(guild=fake_guild(G), user=fake_member(7))
    assert await view.interaction_check(estraneo) is False
    i = fake_interaction(guild=fake_guild(G), user=sfidato)
    i.response.edit_message = AsyncMock()
    await view._scontra(i, b)
    saldi = await _saldi(r, [1, 2])
    assert sorted(saldi) == [20, 80]
    i2 = fake_interaction(guild=fake_guild(G), user=sfidato)
    await view._scontra(i2, b)  # già fatto
    assert await _saldi(r, [1, 2]) == saldi


@pytest.mark.asyncio
async def test_comando_rifiuta_bot_se_stessi_e_chi_non_ha_creature(monkeypatch, r):
    from core.database import db

    async def attivo(self, g, n):
        return True
    monkeypatch.setattr(type(db), "is_module_active_for_guild", attivo)
    import cogs.fun.creature as modulo
    monkeypatch.setattr(modulo, "creature_repo", r.c)
    monkeypatch.setattr(modulo.sociale_repo, "ha_bloccato", AsyncMock(return_value=False))
    cog = CreatureCog(bot=None)
    for bersaglio in (fake_member(1), fake_member(9, bot=True)):
        i = fake_interaction(guild=fake_guild(G), user=fake_member(1))
        await cog.scontro.callback(cog, i, bersaglio, 10, None)
        assert i.response.send_message.await_args.kwargs["ephemeral"] is True
    i = fake_interaction(guild=fake_guild(G), user=fake_member(1))
    await cog.scontro.callback(cog, i, fake_member(2), 10, None)  # nessuno ha creature
    assert i.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_azione_creatura_dell_oggetto_vuole_una_specie_valida(r):
    item = await r.pool.fetchval("INSERT INTO shop_items (guild_id, name, price) VALUES ($1, 'Uovo', 10) RETURNING id", G)
    assert await r.shop.imposta_azione(item, G, "creatura", 3) is True
    assert await r.pool.fetchval("SELECT azione_valore FROM shop_items WHERE id = $1", item) == 3
    for brutta in (None, 0, 9, -1):
        with pytest.raises(ValueError):
            await r.shop.imposta_azione(item, G, "creatura", brutta)
    with pytest.raises(Exception):  # anche il database rifiuta una specie fuori elenco
        await r.pool.execute("UPDATE shop_items SET azione = 'creatura', azione_valore = 99 WHERE id = $1", item)
    # un oggetto che non è una creatura non evoca niente, nemmeno se lo si possiede
    altro = await r.pool.fetchval("INSERT INTO shop_items (guild_id, name, price) VALUES ($1, 'Sasso', 1) RETURNING id", G)
    await r.pool.execute("INSERT INTO economia_inventario (guild_id, user_id, item_id, quantita) VALUES ($1, 1, $2, 1)", G, altro)
    assert (await r.c.evoca(G, 1, altro, random.Random(1))).esito is EsitoEvoca.NON_HAI
    assert await r.pool.fetchval("SELECT quantita FROM economia_inventario WHERE item_id = $1", altro) == 1
