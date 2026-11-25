"""
tests/test_security_audit_memoria.py
====================================
L'anti-nuke trova l'autore di un'azione dalle voci del registro di controllo che arrivano da sole
(`on_audit_log_entry_create`), senza leggerle a ogni evento; il blocco della punizione non si perde.
Funzioni coperte: consiglio 25/11/2026, seri di stabilità (blocco C)
"""

from __future__ import annotations

import asyncio
import gc
from types import SimpleNamespace

import discord
import pytest

from core import security_audit as sa


class _Guild:
    def __init__(self, voci=()):
        self.id = 77
        self.voci = list(voci)
        self.letture = 0

    async def audit_logs(self, *, action, limit):
        self.letture += 1
        for v in self.voci:
            yield v


def _entry(guild, azione, autore, oggetto):
    return SimpleNamespace(guild=guild, action=azione, user_id=autore, target=SimpleNamespace(id=oggetto))


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    sa._RECENTI.clear()

    async def senza_attesa(secondi):
        return None

    monkeypatch.setattr(sa, "_aspetta", senza_attesa)


async def test_una_voce_arrivata_da_sola_si_trova_senza_leggere_il_registro():
    g = _Guild()
    sa.registra_voce(_entry(g, discord.AuditLogAction.channel_delete, 5, 900))
    voce = await sa.resolve_voce(g, discord.AuditLogAction.channel_delete, 900)
    assert voce == (5, 900) and g.letture == 0


async def test_in_un_nuke_con_molte_cancellazioni_nessuna_lettura_del_registro():
    g = _Guild()
    for canale in range(100, 160):
        sa.registra_voce(_entry(g, discord.AuditLogAction.channel_delete, 5, canale))
    risultati = [await sa.resolve_voce(g, discord.AuditLogAction.channel_delete, c) for c in range(100, 160)]
    assert all(r == (5, c) for r, c in zip(risultati, range(100, 160)))
    assert g.letture == 0


async def test_senza_voce_in_memoria_si_legge_il_registro_dopo_il_primo_giro():
    voce = SimpleNamespace(
        created_at=discord.utils.utcnow(), target=SimpleNamespace(id=900), user_id=8
    )
    g = _Guild([voce])
    assert await sa.resolve_voce(g, discord.AuditLogAction.channel_delete, 900) == (8, 900)
    assert g.letture == 1  # solo al secondo tentativo: il primo guarda soltanto la memoria


async def test_una_voce_vecchia_in_memoria_non_vale(monkeypatch):
    g = _Guild()
    sa.registra_voce(_entry(g, discord.AuditLogAction.channel_delete, 5, 900))
    avanti = sa.time.monotonic() + sa.LOOKBACK_REGISTRO_SECONDI + 1
    monkeypatch.setattr(sa.time, "monotonic", lambda: avanti)
    assert await sa.resolve_voce(g, discord.AuditLogAction.channel_delete, 900) is None


async def test_voce_di_un_altro_oggetto_o_un_altra_azione_non_vale():
    g = _Guild()
    sa.registra_voce(_entry(g, discord.AuditLogAction.channel_delete, 5, 900))
    assert await sa.resolve_voce(g, discord.AuditLogAction.channel_delete, 901) is None
    assert await sa.resolve_voce(g, discord.AuditLogAction.role_delete, 900) is None


def test_il_blocco_della_punizione_sopravvive_a_una_cache_piena():
    from cogs.security.anti_nuke import AntiNukeCog

    cog = AntiNukeCog(bot=SimpleNamespace())
    chiave = (1, 2)
    blocco = cog._blocchi_punizione.prendi(chiave)
    for i in range(5000):  # prima: una cache da 500 voci sfrattava il blocco e se ne creava un altro
        cog._blocchi_punizione.prendi((9, i))
    gc.collect()
    assert cog._blocchi_punizione.prendi(chiave) is blocco
    del blocco
    gc.collect()
    assert len(cog._blocchi_punizione) < 5000  # senza nessuno che li tiene spariscono da soli


def test_il_cog_ascolta_il_registro_di_controllo():
    from cogs.security.anti_nuke import AntiNukeCog

    assert hasattr(AntiNukeCog, "on_audit_log_entry_create")
