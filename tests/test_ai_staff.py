"""
tests/test_ai_staff.py
======================
Strumenti dello staff con l'AI (§25.39, §25.40, §25.44): filtri e proposte lette con cura, elenco senza AI,
ricerca nel registro eventi vero, regola applicata solo dopo la conferma.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.ai import staff as cog
from core import ai_staff_logic as logica
from core import automod_assistente_logic as automod
from core.ai_servizio import imposta_servizio_ai
from core.automod_advanced_logic import AutomodAdvancedConfig
from core.database import db
from core.repositories.ai_repo import ai_repo
from core.repositories.ai_staff_repo import ai_staff_repo
from core.repositories.automod_advanced_repo import automod_advanced_repo
from core.repositories.event_log_repo import event_log_repo
from core.repositories.lockdown_repo import lockdown_repo
from core.repositories.security_repo import security_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

G, U1, U2 = 8701, 80000000000000001, 80000000000000002
ORA = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------ logica pura
def test_id_citati_da_menzioni_e_numeri_senza_doppioni():
    d = f"cosa ha fatto <@{U1}> e <@!{U2}> e ancora {U1}?"
    assert logica.id_citati(d) == (U1, U2)


def test_periodo_dalla_domanda():
    assert logica.ore_dalla_domanda("negli ultimi tre giorni") == 72
    assert logica.ore_dalla_domanda("da 2 settimane") == 336
    assert logica.ore_dalla_domanda("oggi") == 24 and logica.ore_dalla_domanda("boh") is None
    assert logica.ore_dalla_domanda("da 99 mesi") == logica.MAX_ORE


def test_filtri_locali_e_filtri_dell_ai_ripuliti():
    f = logica.filtri_locali(f"messaggi cancellati da <@{U1}> ieri")
    assert (f.utenti, f.gruppi, f.ore) == ((U1,), ("message",), 48)
    ai = logica.leggi_filtri(json.dumps({"nomi": ["Mario", 5, " "], "gruppi": ["voice", "tabella_segreta"], "ore": 99999}), f"<@{U2}>")
    assert ai.nomi == ("Mario",) and ai.gruppi == ("voice",) and ai.ore == logica.MAX_ORE and ai.utenti == (U2,)
    assert logica.leggi_filtri("no json", "x") is None
    assert logica.FiltriLog(gruppi=("member", "automod")).prefissi() == ["member_%", "automod%"]


def test_incidente_locale_in_ordine_e_con_conteggi():
    ev = [
        logica.EventoSicurezza(ORA, "raid_join", 5, "account nuovo"),
        logica.EventoSicurezza(ORA - timedelta(minutes=5), "lockdown", None, ""),
        logica.EventoSicurezza(ORA + timedelta(minutes=1), "raid_join", 6, ""),
    ]
    testo = logica.testo_incidente_locale(ev, "panico acceso")
    assert "3 eventi: 2 raid_join, 1 lockdown" in testo and "panico acceso" in testo
    assert testo.index("· lockdown\n") < testo.index("raid_join · utente 5") < testo.index("raid_join · utente 6")
    assert "Non ci sono eventi" in logica.testo_incidente_locale([])


def test_proposta_dell_ai_con_valori_controllati_e_locale_per_parole():
    p = automod.leggi_proposta(json.dumps({"filtro": "anti_spam_messaggi", "massimo": 9999, "secondi": -4, "attivo": True}))
    assert (p.massimo, p.secondi, p.dall_ai) == (50, 1, True)
    assert automod.leggi_proposta(json.dumps({"filtro": "cancella_tutto"})) is None
    assert automod.proposta_locale("niente link dai nuovi").filtro == "anti_link"
    assert automod.proposta_locale("troppi messaggi in raffica").filtro == "anti_spam_messaggi"
    assert automod.proposta_locale("togli il filtro emoji").attivo is False
    assert automod.proposta_locale("ciao") is None


def test_applica_cambia_solo_il_filtro_scelto():
    base = AutomodAdvancedConfig()
    nuova = automod.applica(base, automod.Proposta("anti_spam_emoji", True, massimo=7))
    assert nuova.anti_spam_emoji.enabled and nuova.anti_spam_emoji.max_count == 7
    assert nuova.anti_link == base.anti_link and nuova.anti_caps == base.anti_caps
    assert automod.applica(nuova, automod.Proposta("anti_zalgo", True)).anti_zalgo_enabled


# ------------------------------------------------------------ con il database
@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_staff_repo, ai_repo, security_repo, lockdown_repo, automod_advanced_repo, event_log_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield clean_db
    imposta_servizio_ai(None)


async def test_cerca_eventi_filtra_per_persona_tipo_e_tempo(repo):
    await event_log_repo.log_event(G, "message_delete", actor_id=U1, target_user_id=U2, channel_id=11)
    await event_log_repo.log_event(G, "member_ban", actor_id=U1, target_user_id=U2)
    await event_log_repo.log_event(G, "voice_join", target_user_id=U1)
    await event_log_repo.log_event(G + 1, "member_ban", actor_id=U1, target_user_id=U2)  # altro server
    dal = datetime.now(timezone.utc) - timedelta(hours=1)
    tutti = await ai_staff_repo.cerca_eventi(G, [U2], [], dal)
    assert {e["event_type"] for e in tutti} == {"message_delete", "member_ban"}
    solo_ban = await ai_staff_repo.cerca_eventi(G, [], ["member_%"], dal)
    assert [e["event_type"] for e in solo_ban] == ["member_ban"]
    assert await ai_staff_repo.cerca_eventi(G, [U2], [], datetime.now(timezone.utc) + timedelta(hours=1)) == []


async def test_eventi_recenti_solo_nella_finestra(repo):
    await security_repo.log_action(G, "raid_join", U1, "account nuovo")
    await repo.execute("INSERT INTO security_action_log (guild_id, category, created_at) VALUES ($1, 'vecchio', now() - interval '3 days')", G)
    ev = await cog.eventi_recenti(G, 24)
    assert [e.categoria for e in ev] == ["raid_join"]


async def test_riassunto_senza_ai_e_con_ai(repo):
    inter = fake_interaction(guild=fake_guild(G), user=fake_member(U1))
    inter.guild_id = G
    ev = [logica.EventoSicurezza(ORA, "raid_join", U1, "x")]
    assert "1 eventi: 1 raid_join" in await cog.riassunto_incidente(inter, ev, None)
    servizio, trasporto = servizio_finto(ai_repo, fornitori=[fornitore(fascia="media")], trasporto=TrasportoFinto(risposte={"alfa": "Un raid breve, fermato."}))
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U1, True)
    assert await cog.riassunto_incidente(inter, ev, None) == "Un raid breve, fermato."
    assert "raid_join" in json.dumps(trasporto.chiamate[-1][1])


async def test_regola_si_applica_solo_dopo_il_bottone(repo):
    proposta = automod.Proposta("anti_spam_messaggi", True, massimo=4, secondi=8)
    vista = cog.RegolaView(U1, proposta)
    assert (await automod_advanced_repo.get_settings(G)).config.anti_spam_messages.enabled is False
    altro = fake_interaction(guild=fake_guild(G), user=fake_member(U2))
    assert await vista.interaction_check(altro) is False
    await cog.applica_proposta(G, proposta)
    c = (await automod_advanced_repo.get_settings(G)).config.anti_spam_messages
    assert (c.enabled, c.max_count, c.window_seconds) == (True, 4, 8)


async def test_trova_persone_per_nome():
    mario = fake_member(7)
    mario.display_name, mario.name = "Mario", "mario99"
    guild = MagicMock()
    guild.get_member_named = lambda n: mario if n == "mario99" else None
    guild.members = [mario]
    assert cog.trova_persone(guild, ("mario99", "Mario", "Luca")) == ([7, 7], ["Luca"])
