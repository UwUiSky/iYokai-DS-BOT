"""
tests/test_strumenti_server.py
==============================
D69 B17 (UTL-209, 210, 211, 201): emoji e sticker da un file o da un'emoji, thread, `/voice vai`, esportazione dei
membri per ruolo. Il permesso Discord di chi scrive si controlla; il limite di posti del vocale si controlla a mano.
"""

import csv
import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.strumenti_server as modulo
from core.ruoli_strumenti_logic import FiltroMassa, membri_da_esportare, scrivi_esportazione
from core.strumenti_server_logic import (
    nome_emoji_valido, nome_sticker_valido, posti_emoji_liberi, posti_sticker_liberi, puo_entrare_nel_vocale, trova_emoji,
    troppo_pesante,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


def test_nomi_e_pesi():
    assert nome_emoji_valido("ok_1") and not nome_emoji_valido("a") and not nome_emoji_valido("con spazio")
    assert nome_sticker_valido("ab") and not nome_sticker_valido("x" * 31)
    assert not troppo_pesante("emoji", 256 * 1024) and troppo_pesante("emoji", 256 * 1024 + 1)
    assert not troppo_pesante("sticker", 512 * 1024) and troppo_pesante("sticker", 512 * 1024 + 1)


def test_trova_emoji():
    e = trova_emoji("ciao <a:balla:123456789012345678> e basta")
    assert e.animata and e.nome == "balla" and e.id == 123456789012345678
    assert trova_emoji("<:x:1>") is None and trova_emoji("niente") is None


def test_posti_separati_per_ferme_e_animate():
    g = SimpleNamespace(emoji_limit=50, sticker_limit=5, emojis=[SimpleNamespace(animated=False)] * 50 + [SimpleNamespace(animated=True)] * 3,
                        stickers=[1, 2, 3, 4, 5])
    assert posti_emoji_liberi(g, False) == 0 and posti_emoji_liberi(g, True) == 47 and posti_sticker_liberi(g) == 0


def test_vocale_pieno_lo_decide_il_permesso_di_chi_entra():
    canale = SimpleNamespace(user_limit=2, members=[1, 2])
    base = discord.Permissions(view_channel=True, connect=True)
    assert puo_entrare_nel_vocale(base, canale) == "vai_pieno"
    assert puo_entrare_nel_vocale(discord.Permissions(view_channel=True, connect=True, move_members=True), canale) is None
    assert puo_entrare_nel_vocale(discord.Permissions(view_channel=True), canale) == "vai_vietato"
    assert puo_entrare_nel_vocale(base, SimpleNamespace(user_limit=0, members=[1] * 50)) is None


def _membro(i, nome, ruoli=(), bot=False):
    return SimpleNamespace(id=i, name=nome, display_name=nome.title(), bot=bot, roles=[SimpleNamespace(id=r) for r in ruoli],
                           joined_at=datetime(2024, 1, 2, tzinfo=timezone.utc), top_role=None)


def test_esporta_membri_per_ruolo_nei_tre_formati():
    membri = [_membro(1, "uno", [10]), _membro(2, "=formula", [10]), _membro(3, "tre", [], bot=True)]
    scelti = membri_da_esportare(membri, FiltroMassa(chi="tutti"), 10)
    assert [m.id for m in scelti] == [1, 2]
    dati, nome = scrivi_esportazione(scelti, "csv")
    righe = list(csv.DictReader(io.StringIO(dati.decode())))
    assert nome == "membri.csv" and righe[1]["utente"] == "'=formula" and righe[0]["id"] == "1"
    assert json.loads(scrivi_esportazione(scelti, "json")[0])[0]["entrato_il"].startswith("2024-01-02")
    assert scrivi_esportazione(scelti, "txt")[0].decode().splitlines()[0] == "1 uno"


def _inter(permessi, **kw):
    guild = kw.pop("guild", None) or fake_guild(5)
    inter = fake_interaction(guild=guild, user=fake_member(9))
    inter.permissions = permessi
    return inter


@pytest.mark.asyncio
async def test_espressione_chiede_il_permesso_a_chi_scrive():
    cog = modulo.StrumentiServerCog(MagicMock())
    inter = _inter(discord.Permissions.none())
    scelta = SimpleNamespace(value="emoji")
    await cog.espressione.callback(cog, inter, scelta, "ok", None, None)
    inter.response.send_message.assert_awaited_once()
    assert "create_expressions" in inter.response.send_message.await_args.args[0] or inter.response.send_message.await_args.args


@pytest.mark.asyncio
async def test_vai_rifiuta_chi_non_e_in_vocale_e_chi_non_puo_entrare():
    cog = modulo.StrumentiServerCog(MagicMock())
    inter = fake_interaction(guild=fake_guild(5), user=fake_member(9))
    inter.user = MagicMock(spec=discord.Member)
    inter.user.voice = None
    await cog.vai.callback(cog, inter, MagicMock())
    inter.response.send_message.assert_awaited_once()
    inter.user.move_to = AsyncMock()
    inter.user.voice = SimpleNamespace(channel=object())
    canale = MagicMock()
    canale.user_limit = 1
    canale.members = [1]
    canale.permissions_for.return_value = discord.Permissions(view_channel=True, connect=True)
    inter.response.send_message.reset_mock()
    await cog.vai.callback(cog, inter, canale)
    inter.user.move_to.assert_not_awaited()
