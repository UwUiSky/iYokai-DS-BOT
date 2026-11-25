"""
tests/test_avvio_sicuro.py
==========================
Avvio che non toglie i comandi ai server: cog falliti restituiti, niente sync se manca un cog,
riprova da sola con sync finale, nessun I/O nel setup() dei cog (cricchetto), ripristino
differito delle view e avvisi all'owner raggruppati.
Funzioni coperte: consiglio 25/11/2026, critici 6 e voce 6 (blocco C)
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from core import avvio_sicuro, avvisi_owner as ao, cog_manager, command_sync as cs
from core import giro_periodico as gp
from core import ripristino_differito as rd

RADICE = Path(__file__).resolve().parent.parent


def _bot():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    @bot.tree.command(name="prova", description="Ciao")
    async def prova(interaction: discord.Interaction) -> None: ...

    return bot


class Stato:
    def __init__(self):
        self.valori = {}

    async def leggi(self, scope):
        return self.valori.get(scope)

    async def salva(self, scope, impronta):
        self.valori[scope] = impronta


@pytest.fixture(autouse=True)
def _giri_puliti(monkeypatch):
    monkeypatch.setattr(gp, "PAUSA_BASE_SECONDI", 0.01)
    monkeypatch.setattr(gp, "GIRI", {})


# ---------------------------------------------------------------- cog falliti


async def test_load_all_cogs_restituisce_i_falliti(monkeypatch):
    monkeypatch.setattr(cog_manager, "discover_cog_modules", lambda: ["cogs.a", "cogs.b", "cogs.c"])
    bot = MagicMock()

    async def carica(nome):
        if nome == "cogs.b":
            raise RuntimeError("database lento")

    bot.load_extension = carica
    assert await cog_manager.load_all_cogs(bot) == ["cogs.b"]


async def test_con_un_cog_fallito_non_si_sincronizza_niente(monkeypatch):
    bot, stato, chiamate = _bot(), Stato(), []

    async def finta_sync(*, guild=None):
        chiamate.append(guild)
        return []

    monkeypatch.setattr(bot.tree, "sync", finta_sync)
    esiti = await cs.sincronizza_all_avvio(
        bot.tree, guild_sviluppo_id=None, guild_owner_id=99, stato=stato, cog_falliti=["cogs.utility.role_menus"]
    )
    assert chiamate == [] and stato.valori == {}
    assert set(esiti.values()) == {cs.SALTATA_COG_FALLITI}
    assert avvio_sicuro.avvio_incompleto(["x"], esiti)


async def test_senza_falliti_si_sincronizza_come_prima(monkeypatch):
    bot, stato, chiamate = _bot(), Stato(), []

    async def finta_sync(*, guild=None):
        chiamate.append(guild)
        return []

    monkeypatch.setattr(bot.tree, "sync", finta_sync)
    esiti = await cs.sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=None, stato=stato)
    assert esiti == {"global": cs.SINCRONIZZATA} and len(chiamate) == 1
    assert not avvio_sicuro.avvio_incompleto([], esiti)


async def test_la_ripresa_ricarica_il_cog_poi_sincronizza_e_avvisa(monkeypatch):
    caricati = []
    tentativi = {"n": 0}

    async def carica(bot, modulo):
        tentativi["n"] += 1
        if tentativi["n"] < 3:
            return False
        caricati.append(modulo)
        return True

    monkeypatch.setattr(avvio_sicuro, "carica_cog", carica)
    avvisi = AsyncMock(return_value=True)
    monkeypatch.setattr(avvio_sicuro, "avvisa_owner_chiave", avvisi)
    monkeypatch.setattr(avvio_sicuro, "INTERVALLO_RIPROVA_SECONDI", 0.01)
    sync_viste = []

    async def sincronizza(falliti):
        sync_viste.append(list(falliti))
        return {"global": cs.SALTATA_COG_FALLITI if falliti else cs.SINCRONIZZATA}

    giro = avvio_sicuro.avvia_ripresa_avvio(MagicMock(), ["cogs.x"], sincronizza)
    for _ in range(300):
        if not giro.is_running():
            break
        await asyncio.sleep(0.02)
    assert not giro.is_running(), "il giro di riprova non si è fermato"
    assert caricati == ["cogs.x"]
    assert sync_viste[-1] == []  # l'ultima sync è con tutti i cog caricati
    assert all(v for v in sync_viste[:-1])  # prima, sempre con il cog mancante
    avvisi.assert_awaited_once()
    assert avvisi.await_args.args[1] == "owner_avvio_completato"
    assert gp.giri_in_difficolta() == []  # fermato di proposito: non è un guasto


# ---------------------------------------------------------------- cricchetto setup()


def test_cricchetto_nessun_io_nel_setup_dei_cog():
    """`setup()` aspetta solo `add_cog`: ogni lettura del database va in `ripristina_in_background`."""
    colpe = []
    for percorso in sorted((RADICE / "cogs").rglob("*.py")):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        for nodo in albero.body:
            if not (isinstance(nodo, (ast.AsyncFunctionDef, ast.FunctionDef)) and nodo.name == "setup"):
                continue
            da_visitare = list(nodo.body)
            while da_visitare:
                n = da_visitare.pop()
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef, ast.Lambda)):
                    continue  # le funzioni annidate girano più tardi, non nel setup()
                if isinstance(n, ast.Await):
                    chiamata = n.value
                    nome = chiamata.func.attr if isinstance(chiamata, ast.Call) and isinstance(chiamata.func, ast.Attribute) else None
                    if nome != "add_cog":
                        colpe.append(f"{percorso.relative_to(RADICE)}:{n.lineno} {ast.unparse(n)[:60]}")
                da_visitare.extend(ast.iter_child_nodes(n))
    assert not colpe, "I/O nel setup() (usa core.ripristino_differito): " + "; ".join(colpe)


# ---------------------------------------------------------------- ripristino differito


async def test_ripristino_riprova_finche_riesce(monkeypatch):
    monkeypatch.setattr(gp, "PAUSA_BASE_SECONDI", 0.01)
    volte = []

    async def lavoro():
        volte.append(1)
        if len(volte) < 3:
            raise ConnectionError("database lento")

    await asyncio.wait_for(rd.ripristina_in_background("prova", lavoro), timeout=5)
    assert len(volte) == 3


# ---------------------------------------------------------------- avvisi all'owner


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setattr(ao, "FINESTRA_RAGGRUPPO_SECONDI", 0.05)
    monkeypatch.setattr(ao, "PAUSA_TRA_AVVISI_SECONDI", 0.2)
    monkeypatch.setattr(ao, "_lingua_owner", AsyncMock(return_value="it"))
    utente = MagicMock()
    utente.send = AsyncMock()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=utente)
    return ao.AvvisiOwner(), bot, utente


async def test_piu_cadute_insieme_un_solo_dm(owner):
    avvisi, bot, utente = owner
    for nome in ("giro_a", "giro_b", "giro_c"):
        avvisi.caduto(bot, nome, "errore")
    await asyncio.sleep(0.2)
    assert utente.send.await_count == 1
    testo = utente.send.await_args.args[0]
    assert "giro_a" in testo and "giro_c" in testo and "3" in testo


async def test_tornato_si_dice_solo_se_la_caduta_era_stata_detta(owner):
    avvisi, bot, utente = owner
    avvisi.tornato(bot, "mai_caduto")
    await asyncio.sleep(0.15)
    assert utente.send.await_count == 0
    avvisi.caduto(bot, "giro_a", "x")
    await asyncio.sleep(0.15)
    assert utente.send.await_count == 1
    avvisi.caduto(bot, "giro_a", "x")  # ancora giù: l'owner lo sa già
    await asyncio.sleep(0.1)
    assert utente.send.await_count == 1
    avvisi.tornato(bot, "giro_a")
    await asyncio.sleep(0.4)
    assert utente.send.await_count == 2
    assert "giro_a" in utente.send.await_args.args[0]


async def test_dm_chiusi_non_rompono_niente(owner):
    avvisi, bot, utente = owner
    utente.send.side_effect = discord.Forbidden(MagicMock(status=403, reason="x"), "DM chiusi")
    avvisi.caduto(bot, "giro_a", "x")
    await asyncio.sleep(0.2)
    assert "giro_a" not in avvisi._avvisati  # non consegnato: si riprova al prossimo guasto
