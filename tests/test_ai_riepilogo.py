"""
tests/test_ai_riepilogo.py
==========================
Riepilogo a orario e avvisi su parole (§25.41-§25.43, §25.92): orari, numeri veri dal database, prenotazione unica,
testo senza AI, parole seguite e soglia dei 10 messaggi.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.ai import riepilogo as cog
from core import riepilogo_logic as logica
from core.ai_servizio import imposta_servizio_ai
from core.database import db
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_riepilogo_repo import ai_riepilogo_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, U1, U2 = 8901, 8902, 8903
UTC = timezone.utc


def test_slot_giornaliero_e_settimanale_in_ora_di_roma():
    # 28/10/2026 12:00 UTC = 13:00 a Roma (ora solare): lo slot delle 9 è oggi alle 9 locali = 08:00 UTC
    adesso = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert logica.inizio_slot(9, "giorno", adesso) == datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
    assert logica.inizio_slot(15, "giorno", adesso) == datetime(2026, 10, 27, 14, 0, tzinfo=UTC)
    assert logica.inizio_slot(9, "settimana", adesso) == datetime(2026, 10, 26, 8, 0, tzinfo=UTC)  # lunedì


def test_da_pubblicare_una_sola_volta_per_slot():
    adesso = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert logica.da_pubblicare(9, "giorno", None, adesso)
    assert logica.da_pubblicare(9, "giorno", datetime(2026, 10, 27, 8, 5, tzinfo=UTC), adesso)
    assert not logica.da_pubblicare(9, "giorno", datetime(2026, 10, 28, 8, 1, tzinfo=UTC), adesso)


def test_testo_di_soli_numeri():
    n = logica.Numeri(messaggi=40, minuti_voce=15, attivi=((U1, 30),), canale=(77, 25), meme=(77, 5, 4, U2), clan=("Volpi", 3))
    t = logica.testo_numeri(n, "giorno", G)
    assert "40 messaggi e 15 minuti" in t and f"<@{U1}> (30)" in t and "<#77>" in t and f"/{G}/77/5" in t and "Volpi (+3" in t
    assert "tranquillo" in logica.testo_numeri(logica.Numeri(), "settimana", G)


def test_parole_intere_e_contatore_con_soglia_e_silenzio():
    assert logica.parola_valida("  Boss ") == "boss" and logica.parola_valida("a") is None and logica.parola_valida("x!y") is None
    assert logica.parole_nel_testo("Il Boss è qui, bossy no", {"boss", "qui", "altro"}) == {"boss", "qui"}
    c = logica.ContatoreParole()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    assert not any(c.conta(1, "boss", t0 + timedelta(seconds=i)) for i in range(10))
    assert c.conta(1, "boss", t0 + timedelta(seconds=11))
    assert c.da_avvisare(1, "boss", U1, t0) and not c.da_avvisare(1, "boss", U1, t0 + timedelta(minutes=30))
    assert c.da_avvisare(1, "boss", U1, t0 + timedelta(minutes=61))
    assert not c.conta(2, "boss", t0 + timedelta(minutes=30))  # un altro canale parte da zero


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_riepilogo_repo, ai_repo, activity_stats_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield clean_db
    imposta_servizio_ai(None)


async def test_config_e_prenotazione_unica(repo):
    assert (await ai_riepilogo_repo.config(G)).attivo is False
    await ai_riepilogo_repo.imposta(G, attivo=True, canale_id=5, ora=7, frequenza="settimana")
    [c] = await ai_riepilogo_repo.attivi()
    assert (c.canale_id, c.ora, c.frequenza) == (5, 7, "settimana")
    with pytest.raises(ValueError):
        await ai_riepilogo_repo.imposta(G, sconosciuto=1)
    adesso = datetime.now(UTC)
    slot = adesso - timedelta(hours=1)
    assert await ai_riepilogo_repo.prenota_invio(G, adesso, slot) is True
    assert await ai_riepilogo_repo.prenota_invio(G, adesso, slot) is False
    await ai_riepilogo_repo.salva_testo(G, "ciao")
    assert (await ai_riepilogo_repo.config(G)).ultimo_testo == "ciao"


async def test_numeri_veri_e_pubblicazione_senza_ai(repo):
    await repo.execute("INSERT INTO activity_member_daily (guild_id, day, user_id, messages, voice_seconds) VALUES ($1, current_date, $2, 30, 900)", G, U1)
    await repo.execute("INSERT INTO activity_hour_daily (guild_id, day, hour, messages, voice_seconds) VALUES ($1, current_date, 10, 30, 900)", G)
    await repo.execute("INSERT INTO activity_channel_daily (guild_id, day, channel_id, messages, voice_seconds) VALUES ($1, current_date, 77, 30, 0)", G)
    await repo.execute("INSERT INTO starboard_posts (source_message_id, guild_id, source_channel_id, author_id, stars) VALUES (5, $1, 77, $2, 4)", G, U2)
    n = await cog.raccogli_numeri(G, datetime.now(UTC) - timedelta(days=1))
    assert (n.messaggi, n.minuti_voce, n.canale, n.attivi) == (30, 15, (77, 30), ((U1, 30),))
    assert n.meme == (77, 5, 4, U2)
    canale = fake_text_channel(channel_id=5)
    guild = fake_guild(G)
    guild.get_channel.return_value = canale
    cfg = await ai_riepilogo_repo.imposta(G, attivo=True, canale_id=5)
    assert await cog.pubblica(guild, cfg) is True
    emb = canale.send.call_args.kwargs["embed"]
    assert "30 messaggi" in emb.description
    assert "30 messaggi" in (await ai_riepilogo_repo.config(G)).ultimo_testo


async def test_il_tono_dell_ai_non_deve_perdere_le_menzioni(repo):
    await repo.execute("INSERT INTO activity_member_daily (guild_id, day, user_id, messages) VALUES ($1, current_date, $2, 30)", G, U1)
    await repo.execute("INSERT INTO activity_hour_daily (guild_id, day, hour, messages, voice_seconds) VALUES ($1, current_date, 10, 30, 900)", G)
    servizio, _ = servizio_finto(ai_repo, fornitori=[fornitore()], trasporto=TrasportoFinto(risposte={"alfa": "Che giornata! (numeri persi)"}))
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U1, True)
    cfg = await ai_riepilogo_repo.config(G)
    testo, _ = await cog.componi_riepilogo(fake_guild(G), cfg)
    assert f"<@{U1}>" in testo  # il testo dell'AI non teneva la menzione: resta quello di soli numeri


async def test_avviso_aggiungi_togli_e_tetto(repo):
    c = cog.AiRiepilogoCog(MagicMock())
    def inter(u):
        i = fake_interaction(guild=fake_guild(G), user=fake_member(u)); i.guild_id = G; return i
    for p in ("uno", "due", "tre"):
        await c.avviso.callback(c, inter(U1), "aggiungi", p)
    i = inter(U1)
    await c.avviso.callback(c, i, "aggiungi", "quattro")
    assert "al massimo" in i.response.send_message.call_args.args[0]
    assert await ai_riepilogo_repo.parole_di(G, U1) == ["uno", "due", "tre"]
    await c.avviso.callback(c, inter(U1), "togli", "due")
    assert await ai_riepilogo_repo.parole_di(G, U1) == ["uno", "tre"]
    assert (await ai_riepilogo_repo.parole_del_server(G)) == {"uno": [U1], "tre": [U1]}


async def test_listener_avvisa_solo_chi_vede_il_canale_e_dopo_la_soglia(repo):
    await ai_repo.registra_consenso(G, U1, True)
    await ai_riepilogo_repo.parole_aggiungi(G, U2, "boss", 3)
    await ai_riepilogo_repo.parole_aggiungi(G, U1 + 100, "boss", 3)
    c = cog.AiRiepilogoCog(MagicMock())
    vede, non_vede = fake_member(U2), fake_member(U1 + 100)
    vede.send, non_vede.send = AsyncMock(), AsyncMock()
    canale = MagicMock(id=9, mention="<#9>")
    canale.permissions_for = lambda m: MagicMock(view_channel=m.id == U2)
    guild = MagicMock(id=G)
    guild.name = "S"
    guild.get_member = lambda uid: {U2: vede, U1 + 100: non_vede}.get(uid)
    def msg():
        m = MagicMock(guild=guild, channel=canale, content="il boss arriva")
        m.author = MagicMock(id=U1, bot=False)
        m.jump_url = "https://x"
        return m
    for _ in range(10):
        await c.on_message(msg())
    vede.send.assert_not_awaited()
    await c.on_message(msg())
    vede.send.assert_awaited_once()
    non_vede.send.assert_not_awaited()
    await c.on_message(msg())
    vede.send.assert_awaited_once()  # un solo avviso all'ora
