"""
tests/test_giveaway_avanzati.py
===============================
NF-28 (#99): giveaway avanzati. Ingressi extra per ruolo, requisito sul numero
di messaggi (contati dall'inizio del giveaway), ruoli che saltano i requisiti,
modelli riusabili e giveaway programmati. Logica pura, archivio su PostgreSQL
vero, worker e comandi sotto `/gestione economia`.
Funzioni coperte: SPEC §23.6
"""

import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.leveling.leveling as modulo
from core.giveaway_logic import (
    biglietti_di,
    is_eligible,
    pick_winners_pesati,
    requisiti_mancanti,
)
from core.giveaway_worker import GiveawayWorker
from core.repositories.giveaway_repo import GiveawayRepository, ModelloPieno
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.support.moduli import attiva_livelli

GUILD = 100
ORA = datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Logica pura
# ----------------------------------------------------------------------
def test_biglietti_extra_solo_con_il_ruolo():
    assert biglietti_di({1, 2}, bonus_role_id=2, bonus_entries=3) == 4
    assert biglietti_di({1}, bonus_role_id=2, bonus_entries=3) == 1
    assert biglietti_di({1}, bonus_role_id=None, bonus_entries=3) == 1


def test_il_ruolo_bypass_salta_tutti_i_requisiti():
    assert not is_eligible(0, set(), 10, 5, messages=0, min_messages=50)
    assert is_eligible(0, {9}, 10, 5, messages=0, min_messages=50, bypass_role_ids={9})


def test_requisito_sui_messaggi():
    assert not is_eligible(0, set(), 0, None, messages=4, min_messages=5)
    assert is_eligible(0, set(), 0, None, messages=5, min_messages=5)
    # Senza i nuovi argomenti vale come prima.
    assert is_eligible(3, {5}, 3, 5)


def test_requisiti_mancanti_dice_cosa_manca():
    mancanti = requisiti_mancanti(
        2, set(), min_level=5, required_role_id=7, messages=1, min_messages=10
    )
    assert mancanti == ["livello 5", "il ruolo <@&7>", "10 messaggi (ne hai 1)"]
    assert requisiti_mancanti(9, {7}, 5, 7, messages=10, min_messages=10) == []


def test_pesi_dei_biglietti_cambiano_le_probabilita():
    vittorie = 0
    for seme in range(300):
        vincitori = pick_winners_pesati([(1, 1), (2, 30)], 1, random.Random(seme))
        vittorie += vincitori == [2]
    assert vittorie > 250  # con 30 biglietti su 31 vince quasi sempre


def test_pesati_nessuna_ripetizione_e_tutti_se_pochi():
    assert sorted(pick_winners_pesati([(1, 5), (2, 1)], 5, random.Random(1))) == [1, 2]
    vincitori = pick_winners_pesati([(i, i) for i in range(1, 8)], 4, random.Random(3))
    assert len(set(vincitori)) == 4
    assert pick_winners_pesati([], 3, random.Random(1)) == []
    # Stesso seme, stesso risultato.
    a = pick_winners_pesati([(i, 2) for i in range(10)], 3, random.Random(7))
    b = pick_winners_pesati([(i, 2) for i in range(10)], 3, random.Random(7))
    assert a == b


# ----------------------------------------------------------------------
# Archivio
# ----------------------------------------------------------------------
@pytest.fixture
def repo(clean_db):
    return GiveawayRepository(pool_provider=lambda: clean_db)


async def _crea(repo, **extra):
    return await repo.create_giveaway(
        GUILD, 500, "Nitro", 1, 0, None, ORA + timedelta(hours=1), 1, **extra
    )


@pytest.mark.asyncio
async def test_le_opzioni_avanzate_si_salvano(repo):
    gid = await _crea(
        repo, min_messages=20, bypass_role_id=8, bonus_role_id=9, bonus_entries=4
    )
    g = await repo.get_giveaway(gid)
    assert (g.min_messages, g.bypass_role_id, g.bonus_role_id, g.bonus_entries) == (20, 8, 9, 4)
    base = await repo.get_giveaway(await _crea(repo))
    assert (base.min_messages, base.bypass_role_id, base.bonus_entries, base.started) == (0, None, 0, True)


@pytest.mark.asyncio
async def test_i_biglietti_si_salvano_e_si_leggono(repo):
    gid = await _crea(repo)
    assert await repo.add_entry(gid, 1) is True
    assert await repo.add_entry(gid, 2, tickets=5) is True
    assert await repo.add_entry(gid, 2, tickets=9) is False  # già dentro: nessun cambio
    assert sorted(await repo.get_weighted_entries(gid)) == [(1, 1), (2, 5)]


@pytest.mark.asyncio
async def test_i_messaggi_contano_solo_nei_giveaway_che_li_chiedono(repo):
    con = await _crea(repo, min_messages=3)
    senza = await _crea(repo)
    for _ in range(4):
        await repo.count_message(GUILD, 7)
    await repo.count_message(GUILD + 1, 7)  # altro server
    assert await repo.message_count(con, 7) == 4
    assert await repo.message_count(senza, 7) == 0
    assert await repo.message_count(con, 8) == 0


@pytest.mark.asyncio
async def test_messaggi_non_contati_dopo_la_fine(repo):
    gid = await _crea(repo, min_messages=3)
    await repo.count_message(GUILD, 7)
    await repo.mark_ended(gid)
    await repo.count_message(GUILD, 7)
    assert await repo.message_count(gid, 7) == 1


@pytest.mark.asyncio
async def test_giveaway_programmato_non_e_attivo_ne_scade_prima_di_partire(repo):
    gid = await _crea(repo, starts_at=ORA + timedelta(minutes=10), duration_seconds=3600)
    g = await repo.get_giveaway(gid)
    assert g.started is False
    assert gid not in [x.id for x in await repo.get_active_giveaways()]
    assert gid not in [x.id for x in await repo.get_due_giveaways(ORA + timedelta(days=9))]
    assert await repo.get_giveaways_to_start(ORA) == []
    assert [x.id for x in await repo.get_giveaways_to_start(ORA + timedelta(minutes=11))] == [gid]


@pytest.mark.asyncio
async def test_avvio_una_volta_sola_e_scadenza_dall_avvio(repo):
    gid = await _crea(repo, starts_at=ORA, duration_seconds=3600)
    adesso = ORA + timedelta(minutes=1)
    primo = await repo.claim_start(gid, adesso)
    assert primo is not None and primo.ends_at == adesso + timedelta(seconds=3600)
    assert await repo.claim_start(gid, adesso) is None  # il secondo non parte


@pytest.mark.asyncio
async def test_modelli_salva_aggiorna_elenca_elimina(repo):
    await repo.save_template(GUILD, "classico", prize="Nitro", winners_count=2, duration_minutes=60)
    await repo.save_template(GUILD, "classico", prize="Nitro Classic", winners_count=2, duration_minutes=60)
    modelli = await repo.list_templates(GUILD)
    assert [(m.name, m.prize) for m in modelli] == [("classico", "Nitro Classic")]
    assert (await repo.get_template(GUILD, "classico")).duration_minutes == 60
    assert await repo.get_template(GUILD + 1, "classico") is None
    assert await repo.delete_template(GUILD, "classico") is True
    assert await repo.delete_template(GUILD, "classico") is False


@pytest.mark.asyncio
async def test_massimo_25_modelli_per_server(repo):
    for i in range(25):
        await repo.save_template(GUILD, f"m{i}", prize="x", winners_count=1, duration_minutes=5)
    with pytest.raises(ModelloPieno):
        await repo.save_template(GUILD, "uno-di-troppo", prize="x", winners_count=1, duration_minutes=5)
    await repo.save_template(GUILD, "m3", prize="y", winners_count=1, duration_minutes=5)  # aggiornare si può


# ----------------------------------------------------------------------
# Worker
# ----------------------------------------------------------------------
class _Canale:
    def __init__(self):
        self.inviati = []
        self.id = 500

    async def send(self, contenuto=None, **kw):
        self.inviati.append((contenuto, kw))
        return SimpleNamespace(id=4242)


@pytest.fixture
def worker_in_scena(monkeypatch, repo):
    import core.giveaway_worker as w

    monkeypatch.setattr(w, "giveaway_repo", repo)
    canale = _Canale()

    async def trova(guild, channel_id):
        return canale

    monkeypatch.setattr(w, "_canale_del_giveaway", trova)
    bot = SimpleNamespace(get_guild=lambda gid: object())
    return GiveawayWorker(), bot, canale


@pytest.mark.asyncio
async def test_il_worker_estrae_con_i_biglietti(worker_in_scena, repo, monkeypatch):
    import core.giveaway_worker as w

    worker, bot, canale = worker_in_scena
    gid = await repo.create_giveaway(GUILD, 500, "Nitro", 1, 0, None, ORA - timedelta(seconds=5), 1)
    await repo.add_entry(gid, 1, tickets=1)
    await repo.add_entry(gid, 2, tickets=21)
    viste = []
    originale = w.pick_winners_pesati

    def spia(entries, count, rng):
        viste.append(sorted(entries))
        return originale(entries, count, rng)

    monkeypatch.setattr(w, "pick_winners_pesati", spia)

    await worker.tick(bot, ORA)

    assert viste == [[(1, 1), (2, 21)]]
    assert "Congratulazioni" in canale.inviati[0][0]


@pytest.mark.asyncio
async def test_il_worker_fa_partire_il_programmato_e_dopo_lo_chiude(worker_in_scena, repo, monkeypatch):
    worker, bot, canale = worker_in_scena
    gid = await _crea(repo, starts_at=ORA - timedelta(seconds=1), duration_seconds=600)

    await worker.tick(bot, ORA)

    contenuto, kw = canale.inviati[0]
    assert "Nitro" in kw["embed"].title
    assert kw["view"].giveaway_id == gid
    g = await repo.get_giveaway(gid)
    assert (g.started, g.message_id, g.ended) == (True, 4242, False)
    assert g.ends_at == ORA + timedelta(seconds=600)

    await worker.tick(bot, ORA)  # secondo giro: non lo rimanda
    assert len(canale.inviati) == 1
    await worker.tick(bot, ORA + timedelta(minutes=11))
    assert "terminato" in canale.inviati[1][0]


@pytest.mark.asyncio
async def test_canale_sparito_il_programmato_si_chiude(monkeypatch, repo):
    import core.giveaway_worker as w

    monkeypatch.setattr(w, "giveaway_repo", repo)

    async def nessuno(guild, channel_id):
        return None

    monkeypatch.setattr(w, "_canale_del_giveaway", nessuno)
    gid = await _crea(repo, starts_at=ORA - timedelta(seconds=1), duration_seconds=600)
    await GiveawayWorker().tick(SimpleNamespace(get_guild=lambda g: object()), ORA)
    assert (await repo.get_giveaway(gid)).ended is True


# ----------------------------------------------------------------------
# Comandi e bottone
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_comandi(monkeypatch, clean_db):
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    giveaway = GiveawayRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "giveaway_repo", giveaway)
    monkeypatch.setattr(modulo, "leveling_repo", LevelingRepository(pool_provider=lambda: clean_db))
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return cog, comandi, giveaway


def _interazione():
    i = fake_interaction(guild=fake_guild(GUILD), user=fake_member(1))
    i.channel = SimpleNamespace(id=500)
    i.original_response = AsyncMock(return_value=SimpleNamespace(id=777))
    return i


def _scelta(valore):
    return SimpleNamespace(value=valore)


@pytest.mark.asyncio
async def test_giveaway_con_opzioni_avanzate(cog_comandi):
    cog, comandi, giveaway = cog_comandi
    bypass, extra = fake_role(role_id=8), fake_role(role_id=9)
    interazione = _interazione()

    await comandi["gestione economia giveaway"].callback(
        cog, interazione, prize="Nitro", duration_minutes=60, winners=1, min_level=0,
        required_role=None, min_messaggi=20, ruolo_bypass=bypass, ruolo_extra=extra,
        ingressi_extra=3, inizia_tra=None,
    )

    embed = interazione.response.send_message.await_args.kwargs["embed"]
    assert "**20** messaggi" in embed.description and "<@&8>" in embed.description
    assert "**4** ingressi" in embed.description
    vista = interazione.response.send_message.await_args.kwargs["view"]
    g = await giveaway.get_giveaway(vista.giveaway_id)
    assert (g.min_messages, g.bypass_role_id, g.bonus_role_id, g.bonus_entries) == (20, 8, 9, 3)


@pytest.mark.asyncio
async def test_giveaway_programmato_non_posta_subito(cog_comandi):
    cog, comandi, giveaway = cog_comandi
    interazione = _interazione()

    await comandi["gestione economia giveaway"].callback(
        cog, interazione, prize="Nitro", duration_minutes=60, winners=1, min_level=0,
        required_role=None, min_messaggi=0, ruolo_bypass=None, ruolo_extra=None,
        ingressi_extra=0, inizia_tra=30,
    )

    interazione.response.send_message.assert_awaited_once()
    assert "programmato" in interazione.response.send_message.await_args.args[0].lower()
    assert interazione.response.send_message.await_args.kwargs.get("view") is None
    da_partire = await giveaway.get_giveaways_to_start(datetime.now(timezone.utc) + timedelta(minutes=31))
    assert len(da_partire) == 1 and da_partire[0].duration_seconds == 3600


@pytest.mark.asyncio
async def test_extra_senza_ruolo_e_rifiutato(cog_comandi):
    cog, comandi, giveaway = cog_comandi
    interazione = _interazione()

    await comandi["gestione economia giveaway"].callback(
        cog, interazione, prize="Nitro", duration_minutes=60, winners=1, min_level=0,
        required_role=None, min_messaggi=0, ruolo_bypass=None, ruolo_extra=None,
        ingressi_extra=3, inizia_tra=None,
    )

    assert "ruolo" in interazione.response.send_message.await_args.args[0].lower()
    assert await giveaway.get_active_giveaways() == []


@pytest.mark.asyncio
async def test_modello_salva_elenca_avvia_elimina(cog_comandi):
    cog, comandi, giveaway = cog_comandi
    comando = comandi["gestione economia giveaway-modello"]
    base = dict(
        nome="classico", premio="Nitro", vincitori=2, durata_minuti=90, min_livello=0,
        ruolo_richiesto=None, min_messaggi=0, ruolo_bypass=None, ruolo_extra=None,
        ingressi_extra=0, inizia_tra=None,
    )

    await comando.callback(cog, _interazione(), azione=_scelta("salva"), **base)
    assert (await giveaway.get_template(GUILD, "classico")).winners_count == 2

    interazione = _interazione()
    await comando.callback(cog, interazione, azione=_scelta("elenco"), **{**base, "nome": None})
    assert "classico" in str(interazione.response.send_message.await_args)

    interazione = _interazione()
    await comando.callback(cog, interazione, azione=_scelta("avvia"), **{**base, "premio": None})
    vista = interazione.response.send_message.await_args.kwargs["view"]
    g = await giveaway.get_giveaway(vista.giveaway_id)
    assert (g.prize, g.winners_count) == ("Nitro", 2)

    await comando.callback(cog, _interazione(), azione=_scelta("elimina"), **base)
    assert await giveaway.get_template(GUILD, "classico") is None


@pytest.mark.asyncio
async def test_modello_inesistente_non_avvia_nulla(cog_comandi):
    cog, comandi, giveaway = cog_comandi
    interazione = _interazione()
    await comandi["gestione economia giveaway-modello"].callback(
        cog, interazione, azione=_scelta("avvia"), nome="boh", premio=None, vincitori=None,
        durata_minuti=None, min_livello=None, ruolo_richiesto=None, min_messaggi=None,
        ruolo_bypass=None, ruolo_extra=None, ingressi_extra=None, inizia_tra=None,
    )
    assert "non esiste" in interazione.response.send_message.await_args.args[0].lower()
    assert await giveaway.get_active_giveaways() == []


class _Click:
    def __init__(self, user):
        self.user = user
        self.response = SimpleNamespace(send_message=AsyncMock())


@pytest.mark.asyncio
async def test_bottone_ingressi_extra_e_requisito_messaggi(cog_comandi):
    cog, _, giveaway = cog_comandi
    gid = await _crea(giveaway, min_messages=2, bonus_role_id=9, bonus_entries=3)
    vista = cog.GiveawayEnterView(gid)
    ruolo = fake_role(role_id=9)

    pochi = _Click(fake_member(user_id=5, roles=[ruolo]))
    await vista.children[0].callback(pochi)
    assert "messaggi" in pochi.response.send_message.await_args.args[0]
    assert await giveaway.has_entered(gid, 5) is False

    await giveaway.count_message(GUILD, 5)
    await giveaway.count_message(GUILD, 5)
    ok = _Click(fake_member(user_id=5, roles=[ruolo]))
    await vista.children[0].callback(ok)
    assert "registrata" in ok.response.send_message.await_args.args[0]
    assert await giveaway.get_weighted_entries(gid) == [(5, 4)]


@pytest.mark.asyncio
async def test_bottone_il_ruolo_bypass_entra_senza_requisiti(cog_comandi):
    cog, _, giveaway = cog_comandi
    gid = await _crea(giveaway, min_messages=50, bypass_role_id=8)
    vista = cog.GiveawayEnterView(gid)

    click = _Click(fake_member(user_id=6, roles=[fake_role(role_id=8)]))
    await vista.children[0].callback(click)

    assert await giveaway.has_entered(gid, 6) is True


@pytest.mark.asyncio
async def test_on_message_conta_i_messaggi_per_i_giveaway(cog_comandi, monkeypatch):
    import discord

    cog, _, giveaway = cog_comandi
    gid = await _crea(giveaway, min_messages=5)
    monkeypatch.setattr(modulo, "should_trigger_drop", lambda v: False)
    from tests.support.discord_fakes import fake_message, fake_text_channel

    autore = fake_member(user_id=5)
    canale = fake_text_channel(channel_id=111)
    msg = fake_message(author=autore, channel=canale)
    msg.type = discord.MessageType.default
    msg.guild = fake_guild(GUILD)

    await cog.on_message(msg)
    await cog.on_message(msg)

    assert await giveaway.message_count(gid, 5) == 2
