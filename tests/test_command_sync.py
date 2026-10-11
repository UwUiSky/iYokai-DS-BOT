"""
tests/test_command_sync.py
==========================
Sincronizzazione dei comandi solo se l'albero cambia: impronta stabile,
sync saltata con impronta uguale, ripetuta dopo un errore, tabella vera.
Funzioni coperte: NF-05 (issue #76)
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core import command_sync as cs
from core.command_sync import (
    StatoSyncDatabase,
    impronta_albero,
    scope_guild,
    sincronizza_all_avvio,
    sincronizza_se_cambiato,
)


class StatoInMemoria:
    def __init__(self):
        self.valori: dict[str, str] = {}

    async def leggi(self, scope):
        return self.valori.get(scope)

    async def salva(self, scope, impronta):
        self.valori[scope] = impronta


class Sync:
    def __init__(self, errore=None):
        self.chiamate = 0
        self.errore = errore

    async def __call__(self):
        self.chiamate += 1
        if self.errore:
            raise self.errore
        return []


def _bot(descrizione="Ciao"):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

    @bot.tree.command(name="prova", description=descrizione)
    @app_commands.describe(testo="Un testo")
    async def prova(interaction: discord.Interaction, testo: str) -> None: ...

    return bot


def test_impronta_uguale_per_alberi_uguali_e_diversa_se_cambia_una_descrizione():
    a, b, c = _bot(), _bot(), _bot("Altro")
    assert impronta_albero(a.tree.get_commands(), a.tree) == impronta_albero(b.tree.get_commands(), b.tree)
    assert impronta_albero(a.tree.get_commands(), a.tree) != impronta_albero(c.tree.get_commands(), c.tree)
    assert len(impronta_albero(a.tree.get_commands(), a.tree)) == 64


def test_impronta_non_dipende_dall_ordine_di_registrazione():
    bot = _bot()

    @bot.tree.command(name="altro", description="Altro")
    async def altro(interaction: discord.Interaction) -> None: ...

    comandi = bot.tree.get_commands()
    assert impronta_albero(comandi, bot.tree) == impronta_albero(list(reversed(comandi)), bot.tree)


async def test_prima_volta_sincronizza_e_salva_poi_con_impronta_uguale_salta():
    bot, stato, sync = _bot(), StatoInMemoria(), Sync()
    assert await sincronizza_se_cambiato("global", bot.tree.get_commands(), bot.tree, sync, stato) == cs.SINCRONIZZATA
    assert sync.chiamate == 1 and "global" in stato.valori
    assert await sincronizza_se_cambiato("global", bot.tree.get_commands(), bot.tree, sync, stato) == cs.SALTATA
    assert sync.chiamate == 1


async def test_albero_cambiato_sincronizza_e_aggiorna_l_impronta():
    stato, sync = StatoInMemoria(), Sync()
    vecchio, nuovo = _bot(), _bot("Cambiata")
    await sincronizza_se_cambiato("global", vecchio.tree.get_commands(), vecchio.tree, sync, stato)
    prima = stato.valori["global"]
    assert await sincronizza_se_cambiato("global", nuovo.tree.get_commands(), nuovo.tree, sync, stato) == cs.SINCRONIZZATA
    assert sync.chiamate == 2 and stato.valori["global"] != prima


async def test_errore_di_sync_non_aggiorna_l_impronta_e_si_riprova(caplog):
    bot, stato = _bot(), StatoInMemoria()
    guasto = Sync(errore=discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "errore"))
    with caplog.at_level("WARNING"):
        esito = await sincronizza_se_cambiato("global", bot.tree.get_commands(), bot.tree, guasto, stato)
    assert esito == cs.ERRORE and stato.valori == {}
    assert "global" in caplog.text
    sano = Sync()
    assert await sincronizza_se_cambiato("global", bot.tree.get_commands(), bot.tree, sano, stato) == cs.SINCRONIZZATA
    assert sano.chiamate == 1 and "global" in stato.valori


async def test_stato_illeggibile_sincronizza_comunque():
    class Rotto(StatoInMemoria):
        async def leggi(self, scope):
            raise RuntimeError("tabella assente")

    bot, sync = _bot(), Sync()
    assert await sincronizza_se_cambiato("global", bot.tree.get_commands(), bot.tree, sync, Rotto()) == cs.SINCRONIZZATA
    assert sync.chiamate == 1


async def test_salvataggio_fallito_non_blocca_l_avvio():
    class NonSalva(StatoInMemoria):
        async def salva(self, scope, impronta):
            raise RuntimeError("database spento")

    bot, sync = _bot(), Sync()
    assert await sincronizza_se_cambiato("global", bot.tree.get_commands(), bot.tree, sync, NonSalva()) == cs.SINCRONIZZATA


# ---- i tre ambiti, con l'albero vero e tree.sync sostituito ----
def _registra_sync(bot, monkeypatch):
    chiamate = []

    async def finta_sync(*, guild=None):
        chiamate.append(None if guild is None else guild.id)
        return []

    monkeypatch.setattr(bot.tree, "sync", finta_sync)
    return chiamate


async def test_produzione_sincronizza_globale_e_server_dell_owner_solo_se_cambiano(monkeypatch):
    bot, stato = _bot(), StatoInMemoria()
    from core.command_groups import registra_owner

    chiamate = _registra_sync(bot, monkeypatch)
    owner = registra_owner  # il gruppo /owner di prova entra solo nel server dell'owner
    gruppi = {"owner": app_commands.Group(name="owner", description="Owner")}

    @gruppi["owner"].command(name="x", description="X")
    async def x(interaction: discord.Interaction) -> None: ...

    owner(bot.tree, 99, gruppi=gruppi)
    r1 = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=99, stato=stato)
    assert r1 == {"global": cs.SINCRONIZZATA, scope_guild(99): cs.SINCRONIZZATA}
    assert chiamate == [None, 99]
    r2 = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=99, stato=stato)
    assert r2 == {"global": cs.SALTATA, scope_guild(99): cs.SALTATA}
    assert chiamate == [None, 99]
    bot.tree.get_command("prova").description = "Modificata"
    r3 = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=99, stato=stato)
    assert r3 == {"global": cs.SINCRONIZZATA, scope_guild(99): cs.SALTATA}


async def test_sviluppo_copia_il_globale_nel_server_di_prova_e_sincronizza_solo_quello(monkeypatch):
    bot, stato = _bot(), StatoInMemoria()
    chiamate = _registra_sync(bot, monkeypatch)
    r1 = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=55, guild_owner_id=55, stato=stato)
    assert r1 == {scope_guild(55): cs.SINCRONIZZATA} and chiamate == [55]
    assert bot.tree.get_command("prova", guild=discord.Object(id=55)) is not None
    r2 = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=55, guild_owner_id=55, stato=stato)
    assert r2 == {scope_guild(55): cs.SALTATA} and chiamate == [55]


async def test_produzione_senza_server_owner_sincronizza_solo_il_globale(monkeypatch):
    bot, stato = _bot(), StatoInMemoria()
    chiamate = _registra_sync(bot, monkeypatch)
    r = await sincronizza_all_avvio(bot.tree, guild_sviluppo_id=None, guild_owner_id=None, stato=stato)
    assert r == {"global": cs.SINCRONIZZATA} and chiamate == [None]


# ---- la tabella vera ----
async def test_stato_database_salva_legge_e_aggiorna(clean_db):
    stato = StatoSyncDatabase(clean_db)
    assert await stato.leggi("global") is None
    await stato.salva("global", "aaa")
    assert await stato.leggi("global") == "aaa"
    prima = await clean_db.fetchval("SELECT synced_at FROM command_sync_state WHERE scope = 'global'")
    await stato.salva("global", "bbb")
    assert await stato.leggi("global") == "bbb"
    assert await stato.leggi("guild:1") is None
    dopo = await clean_db.fetchval("SELECT synced_at FROM command_sync_state WHERE scope = 'global'")
    assert dopo >= prima


async def test_la_tabella_ha_le_colonne_previste(clean_db):
    righe = await clean_db.fetch(
        "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'command_sync_state'"
    )
    assert {r["column_name"]: r["is_nullable"] for r in righe} == {
        "scope": "NO", "tree_hash": "NO", "synced_at": "NO",
    }
