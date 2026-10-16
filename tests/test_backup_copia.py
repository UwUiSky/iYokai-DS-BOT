"""
tests/test_backup_copia.py
==========================
BKP-024 e BKP-025: copia di un canale (una categoria con i canali dentro) e di
un ruolo con i permessi nei canali, nei tetti di Discord.
Funzioni coperte: BKP-024, BKP-025
"""

from __future__ import annotations

from types import SimpleNamespace

import discord

from core.backup_copia_logic import MAX_CANALI, copia_canale, copia_ruolo
from core.backup_mirror_logic import NOME_CANALE_OFFUSCATO
from tests.support.discord_fakes import fake_role


class _Canale:
    def __init__(self, nome, posizione=0, overwrites=None):
        self.name, self.position = nome, posizione
        self.type = discord.ChannelType.text
        self.overwrites = overwrites or {}
        self.cloni = []
        self.permessi = []

    async def clone(self, **kw):
        self.cloni.append(kw)
        return SimpleNamespace(name=kw.get("name") or self.name, mention=f"#{self.name}")

    async def set_permissions(self, bersaglio, **kw):
        self.permessi.append((bersaglio.name, kw["overwrite"]))


class _Categoria(_Canale):
    def __init__(self, nome, figli):
        super().__init__(nome)
        self.type = discord.ChannelType.category
        self.channels = figli


def _guild(canali=(), ruoli=()):
    g = SimpleNamespace(channels=list(canali), roles=list(ruoli), me=None)
    creati = []

    async def create_role(**kw):
        creati.append(kw)
        return SimpleNamespace(name=kw["name"], mention="@x")

    g.create_role, g.creati = create_role, creati
    return g


async def test_categoria_copiata_con_i_canali_in_ordine_senza_quelli_nascosti():
    b, a, nascosto = _Canale("b", 2), _Canale("a", 1), _Canale(NOME_CANALE_OFFUSCATO, 3)
    cat = _Categoria("Info", [b, a, nascosto])
    esito = await copia_canale(_guild([cat, a, b, nascosto]), cat, "Info 2")
    assert cat.cloni[0]["name"] == "Info 2"
    assert a.cloni[0]["category"] is esito.nuovo and b.cloni[0]["category"] is esito.nuovo
    assert (esito.copiati, esito.saltati) == (3, 1)


async def test_server_pieno_niente_copia():
    canale = _Canale("x")
    esito = await copia_canale(_guild([canale] * MAX_CANALI), canale)
    assert esito.errore and canale.cloni == []


async def test_ruolo_copiato_con_i_permessi_nei_canali():
    ruolo = fake_role(5, "Staff", position=3, permissions=discord.Permissions(kick_members=True))
    ruolo.colour, ruolo.hoist, ruolo.mentionable = discord.Colour(1), True, False
    ow = discord.PermissionOverwrite(send_messages=False)
    con, senza = _Canale("con", overwrites={ruolo: ow}), _Canale("senza")
    g = _guild([con, senza], [ruolo])
    esito = await copia_ruolo(g, ruolo, "Staff 2", permessi_canali=True)
    assert g.creati[0]["name"] == "Staff 2" and g.creati[0]["permissions"].kick_members
    assert con.permessi == [("Staff 2", ow)] and senza.permessi == []
    assert esito.copiati == 2


async def test_ruolo_gestito_non_si_copia():
    gestito = fake_role(5, "Bot", managed=True)
    g = _guild(ruoli=[gestito])
    esito = await copia_ruolo(g, gestito)
    assert esito.errore and g.creati == []
