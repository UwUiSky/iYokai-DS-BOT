"""
tests/test_coin_games_cog.py
============================
NF-40 (#111): comandi /fun gioca, /fun misura, /fun conteggio e il listener
del gioco del conteggio. Archivio su PostgreSQL vero.
Funzioni coperte: SPEC §23.16
"""

import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

import cogs.fun.coin_games as modulo
from core.repositories.counting_game_repo import CountingGameRepository
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_text_channel,
)
from tests.support.moduli import attiva_livelli

GUILD = 100


@pytest.fixture
async def scena(monkeypatch, clean_db):
    import core.database as database_module
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    await database_module.db.set_module_active_for_guild(GUILD, "fun", True)
    monkeypatch.setattr(modulo, "db", database_module.db)
    monete = LevelingRepository(pool_provider=lambda: clean_db)
    conteggio = CountingGameRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", monete)
    monkeypatch.setattr(modulo, "counting_game_repo", conteggio)
    cog = modulo.CoinGamesCog(bot=None)
    comandi = {
        c.qualified_name: c
        for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None)
    }
    return SimpleNamespace(cog=cog, comandi=comandi, monete=monete, conteggio=conteggio)


def _interazione(user_id=1):
    return fake_interaction(guild=fake_guild(GUILD), user=fake_member(user_id, name=f"u{user_id}"))


def _scelta(valore, nome=None):
    return SimpleNamespace(value=valore, name=nome or valore)


def _testo(interazione):
    chiamata = interazione.response.send_message.await_args
    if chiamata.args:
        return chiamata.args[0]
    return chiamata.kwargs["embed"].description


class _Rng:
    def __init__(self, *valori):
        self._valori = list(valori)

    def randint(self, a, b):
        return self._valori.pop(0)

    def choice(self, seq):
        return seq[self._valori.pop(0)]


async def _libera_attesa(scena):
    await scena.monete._pool.execute("UPDATE leveling_totals SET ultima_partita_at = NULL")


# ----------------------------------------------------------------------
# /fun gioca
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_due_partite_insieme_ne_passa_una_sola(scena):
    from tests.support.concorrenza import apri_connessioni
    import asyncio

    await scena.monete.add_coins(GUILD, 1, 1000)
    await apri_connessioni(scena.monete._pool, 6)
    scena.cog._rng = _Rng(*([1] * 10))  # croce: ogni partita persa costa la puntata
    interazioni = [_interazione() for _ in range(5)]

    await asyncio.gather(*(
        scena.comandi["fun gioca"].callback(
            scena.cog, i, gioco=_scelta("monetina"), puntata=10, scelta=_scelta("testa")
        )
        for i in interazioni
    ))

    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 990
    messaggi = [_testo(i) for i in interazioni]
    assert sum("Piano" in m for m in messaggi) == 4


@pytest.mark.asyncio
async def test_gioca_richiede_anche_il_modulo_livelli(scena):
    import core.database as database_module

    await scena.monete.add_coins(GUILD, 1, 100)
    await database_module.db.set_module_active_for_guild(GUILD, "leveling", False)
    interazione = _interazione()

    await scena.comandi["fun gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=10, scelta=None
    )

    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100
    assert "Livelli" in _testo(interazione)


@pytest.mark.asyncio
async def test_i_comandi_sono_sotto_fun(scena):
    for nome in ("fun gioca", "fun misura", "fun conteggio"):
        assert nome in scena.comandi


@pytest.mark.asyncio
async def test_vincita_e_perdita_cambiano_il_saldo(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    scena.cog._rng = _Rng(0)  # esce testa
    await scena.comandi["fun gioca"].callback(
        scena.cog, _interazione(), gioco=_scelta("monetina"), puntata=40, scelta=_scelta("testa")
    )
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 140

    await _libera_attesa(scena)
    scena.cog._rng = _Rng(1)  # esce croce
    interazione = _interazione()
    await scena.comandi["fun gioca"].callback(
        scena.cog, interazione, gioco=_scelta("monetina"), puntata=40, scelta=_scelta("testa")
    )
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100
    assert "perso" in _testo(interazione)


@pytest.mark.asyncio
async def test_senza_coin_a_sufficienza_non_si_gioca(scena):
    await scena.monete.add_coins(GUILD, 1, 10)
    interazione = _interazione()
    await scena.comandi["fun gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=50, scelta=None
    )
    assert "abbastanza" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 10


@pytest.mark.asyncio
async def test_monetina_senza_lato_e_rifiutata(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["fun gioca"].callback(
        scena.cog, interazione, gioco=_scelta("monetina"), puntata=10, scelta=None
    )
    assert "testa o croce" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100


@pytest.mark.asyncio
async def test_due_partite_di_fila_vengono_fermate(scena):
    await scena.monete.add_coins(GUILD, 1, 100)
    scena.cog._rng = random.Random(1)
    await scena.comandi["fun gioca"].callback(
        scena.cog, _interazione(), gioco=_scelta("dadi"), puntata=10, scelta=None
    )
    dopo_la_prima = (await scena.monete.get_totals(GUILD, 1)).coins_total
    interazione = _interazione()
    await scena.comandi["fun gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=10, scelta=None
    )
    assert "Aspetta" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == dopo_la_prima


@pytest.mark.asyncio
async def test_modulo_spento_nessuna_partita(scena):
    import core.database as database_module

    await database_module.db.set_module_active_for_guild(GUILD, "fun", False)
    await scena.monete.add_coins(GUILD, 1, 100)
    interazione = _interazione()
    await scena.comandi["fun gioca"].callback(
        scena.cog, interazione, gioco=_scelta("dadi"), puntata=10, scelta=None
    )
    assert "non è attivo" in _testo(interazione)
    assert (await scena.monete.get_totals(GUILD, 1)).coins_total == 100


# ----------------------------------------------------------------------
# /fun misura
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_misura_risponde_con_una_percentuale(scena):
    interazione = _interazione()
    await scena.comandi["fun misura"].callback(scena.cog, interazione, tema="coraggio", membro=None)
    assert "coraggio" in _testo(interazione) and "%" in _testo(interazione)


@pytest.mark.asyncio
async def test_misura_rifiuta_i_temi_su_caratteristiche_protette(scena):
    interazione = _interazione()
    await scena.comandi["fun misura"].callback(scena.cog, interazione, tema="quanto sei gay", membro=None)
    assert "non misuro" in _testo(interazione)
    assert interazione.response.send_message.await_args.kwargs.get("ephemeral") is True


# ----------------------------------------------------------------------
# Gioco del conteggio
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conteggio_imposta_stato_e_spegni(scena):
    comando = scena.comandi["fun conteggio"]
    canale = fake_text_channel(channel_id=555)
    await comando.callback(scena.cog, _interazione(), azione=_scelta("imposta"), canale=canale)
    assert (await scena.conteggio.get(GUILD)).channel_id == 555

    interazione = _interazione()
    await comando.callback(scena.cog, interazione, azione=_scelta("stato"), canale=None)
    assert "Record" in _testo(interazione)

    await comando.callback(scena.cog, _interazione(), azione=_scelta("spegni"), canale=None)
    assert await scena.conteggio.get(GUILD) is None


@pytest.mark.asyncio
async def test_conteggio_non_si_imposta_dove_il_bot_non_puo_reagire(scena):
    canale = fake_text_channel(channel_id=555)
    canale.permissions_for = lambda me: SimpleNamespace(
        view_channel=True, send_messages=True, add_reactions=False, read_message_history=True
    )
    interazione = _interazione()

    await scena.comandi["fun conteggio"].callback(
        scena.cog, interazione, azione=_scelta("imposta"), canale=canale
    )

    assert "Aggiungere reazioni" in _testo(interazione)
    assert await scena.conteggio.get(GUILD) is None


def _messaggio(testo, user_id, canale_id=555):
    canale = fake_text_channel(channel_id=canale_id)
    canale.send = AsyncMock()
    msg = fake_message(
        author=fake_member(user_id, name=f"u{user_id}"), channel=canale,
        guild=fake_guild(GUILD), content=testo,
    )
    msg.add_reaction = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_si_conta_a_turno_e_chi_sbaglia_azzera(scena):
    await scena.conteggio.set_channel(GUILD, 555)
    for testo, utente in (("1", 1), ("2", 2), ("3", 1)):
        msg = _messaggio(testo, utente)
        await scena.cog.on_message(msg)
        msg.add_reaction.assert_awaited_once_with("✅")
    assert (await scena.conteggio.get(GUILD)).current == 3

    sbagliato = _messaggio("7", 2)
    await scena.cog.on_message(sbagliato)
    sbagliato.add_reaction.assert_awaited_once_with("❌")
    assert "ha rovinato tutto a **3**" in sbagliato.channel.send.await_args.args[0]
    stato = await scena.conteggio.get(GUILD)
    assert (stato.current, stato.best) == (0, 3)


@pytest.mark.asyncio
async def test_la_stessa_persona_non_conta_due_volte_di_fila(scena):
    await scena.conteggio.set_channel(GUILD, 555)
    await scena.cog.on_message(_messaggio("1", 1))
    doppio = _messaggio("2", 1)
    await scena.cog.on_message(doppio)
    doppio.add_reaction.assert_awaited_once_with("❌")
    assert (await scena.conteggio.get(GUILD)).current == 0


@pytest.mark.asyncio
async def test_chiacchiere_altri_canali_e_bot_non_contano(scena):
    await scena.conteggio.set_channel(GUILD, 555)
    chiacchiera = _messaggio("ciao a tutti", 1)
    altro_canale = _messaggio("1", 1, canale_id=999)
    bot = _messaggio("1", 3)
    bot.author.bot = True
    for msg in (chiacchiera, altro_canale, bot):
        await scena.cog.on_message(msg)
        msg.add_reaction.assert_not_awaited()
    assert (await scena.conteggio.get(GUILD)).current == 0


@pytest.mark.asyncio
async def test_due_numeri_insieme_ne_passa_uno_solo(scena, clean_db):
    import asyncio

    from tests.support.concorrenza import apri_connessioni

    await apri_connessioni(clean_db)
    await scena.conteggio.set_channel(GUILD, 555)
    await scena.conteggio.register(GUILD, 555, 1, 1)
    esiti = await asyncio.gather(
        *(scena.conteggio.register(GUILD, 555, 10 + i, 2) for i in range(6))
    )
    # Il primo 2 passa; gli altri arrivano quando il conteggio è già a 2 (o tornato a zero).
    assert sum(1 for e in esiti if e.corretto) == 1


@pytest.mark.asyncio
async def test_il_record_resta_quando_si_cambia_canale(scena):
    await scena.conteggio.set_channel(GUILD, 555)
    for n, u in ((1, 1), (2, 2)):
        await scena.conteggio.register(GUILD, 555, u, n)
    await scena.conteggio.set_channel(GUILD, 777)
    stato = await scena.conteggio.get(GUILD)
    assert (stato.channel_id, stato.current, stato.best) == (777, 0, 2)
