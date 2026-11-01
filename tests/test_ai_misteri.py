"""
tests/test_ai_misteri.py
========================
Misteri (§25.56): impronta del codice, tentativi, premio XP e canale segreto. Database vero, Discord finto.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.ai import misteri
from core import misteri_logic as logica
from core.database import db
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_gioco_repo import ai_gioco_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, U1, U2 = 8301, 8302, 8303


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_gioco_repo, leveling_repo, leveling_settings_repo, activity_stats_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    misteri.TENTATIVI._dati.clear()
    return ai_gioco_repo


def test_codice_senza_maiuscole_accenti_e_segni():
    assert logica.normalizza_codice("Il  Corvò!") == "ilcorvo"
    assert logica.impronta_codice(1, "Il Corvo") == logica.impronta_codice(1, "il-corvo")
    assert logica.impronta_codice(1, "corvo") != logica.impronta_codice(2, "corvo")
    assert logica.impronta_codice(1, "a!") is None


def test_tentativi_uno_ogni_cinque_secondi_e_dieci_all_ora():
    lim = logica.LimiteTentativi()
    assert lim.consenti(1, 1, 0) is None and lim.consenti(1, 1, 2) == "attesa"
    for i in range(1, 10):
        assert lim.consenti(1, 1, 10 * i) is None
    assert lim.consenti(1, 1, 200) == "troppi"
    assert lim.consenti(1, 1, 3700) is None and lim.consenti(1, 2, 3) is None


async def _crea(repo, premio="xp", valore=100, ore=24, codice="il corvo"):
    return await repo.mistero_crea(G, "Il corvo", "Guarda in alto", logica.impronta_codice(G, codice), premio, valore, ore, U1)


def _inter(uid):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(uid))
    i.guild_id = G
    return i


async def test_modal_salva_solo_l_impronta(repo):
    modal = misteri._MisteroModal("xp", 50, 24)
    modal.titolo._value, modal.indizio._value, modal.codice._value = "Il corvo", "Guarda in alto", "Corvo Nero"
    i = _inter(U1)
    await modal.on_submit(i)
    [m] = await repo.misteri(G)
    riga = await db.pool.fetchrow("SELECT codice_hash FROM ai_misteri WHERE id = $1", m.id)
    assert riga["codice_hash"] == logica.impronta_codice(G, "corvonero") and "corvo" not in riga["codice_hash"]
    modal.codice._value = "a"
    i = _inter(U1)
    await modal.on_submit(i)
    assert "almeno 3" in i.response.send_message.call_args.args[0]


async def test_risposta_giusta_dà_xp_ai_membri_attivi_una_volta_sola(repo):
    await _crea(repo, "xp", 80)
    oggi = datetime.now(timezone.utc).date()
    await db.pool.execute(
        "INSERT INTO activity_member_daily (guild_id, user_id, day, messages) VALUES ($1, $2, $3, 5), ($1, $4, $3, 0)", G, U2, oggi, 9999
    )
    cog = misteri.AiMisteriCog(MagicMock())
    sbagliata = _inter(U1)
    await cog.rispondi.callback(cog, sbagliata, "gufo")
    assert "Non è il codice" in sbagliata.response.send_message.call_args.args[0]
    misteri.TENTATIVI._dati.clear()
    giusta = _inter(U1)
    await cog.rispondi.callback(cog, giusta, "IL CORVO")
    assert "80 XP a 1 membri" in giusta.followup.send.call_args.args[0]
    assert (await leveling_repo.get_totals(G, U2)).xp_total == 80
    assert (await repo.misteri(G))[0].risolto_da == U1
    misteri.TENTATIVI._dati.clear()
    seconda = _inter(U2)
    await cog.rispondi.callback(cog, seconda, "il corvo")
    assert "Non è il codice" in seconda.response.send_message.call_args.args[0]


async def test_canale_segreto_aperto_a_tutti_e_richiuso(repo, monkeypatch):
    await _crea(repo, "canale", 4321, 3)
    canale = fake_text_channel(4321)
    canale.set_permissions = AsyncMock()
    canale.overwrites_for = MagicMock(return_value=MagicMock(view_channel=False))
    guild = fake_guild(G)
    guild.get_channel = MagicMock(return_value=canale)
    pianificate = []
    monkeypatch.setattr(misteri.scheduler, "schedule", AsyncMock(side_effect=lambda *a: pianificate.append(a)))
    [m] = await repo.misteri(G)
    testo = await misteri.premia_server(guild, m)
    assert "aperto a tutti per 3 ore" in testo
    assert canale.set_permissions.call_args.kwargs["view_channel"] is True
    assert pianificate[0][2] == misteri.AZIONE_CANALE and pianificate[0][4] == {"channel_id": 4321, "prima": False}
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    cog = misteri.AiMisteriCog(bot)
    await cog.chiudi_canale(G, 0, pianificate[0][4])
    assert canale.set_permissions.call_args.kwargs["view_channel"] is False  # com'era prima


async def test_elenco_e_togli(repo):
    mid = await _crea(repo)
    cog = misteri.AiMisteriCog(MagicMock())
    i = _inter(U1)
    await cog.mistero_elenco.callback(cog, i)
    assert "Il corvo" in i.response.send_message.call_args.args[0] and "codice" not in i.response.send_message.call_args.args[0].lower()
    i = _inter(U1)
    await cog.mistero_togli.callback(cog, i, mid)
    assert await repo.misteri(G) == []
