"""
tests/test_ai_boss.py
=====================
World Boss (§25.49–§25.52, §25.59, §25.64, §25.70): database vero, fornitore AI finto, Discord finto.
"""

import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.ai import boss
from core import boss_logic as logica
from core.ai_servizio import imposta_servizio_ai
from core.database import db
from core.repositories.activity_stats_repo import activity_stats_repo
from core.repositories.ai_gioco_repo import AiGiocoRepository, ai_gioco_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.ai_finto import TrasportoFinto, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, C, U1, U2 = 8101, 8102, 8103, 8104


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_gioco_repo, ai_repo, leveling_repo, leveling_settings_repo, activity_stats_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    boss.AGGIORNA.clear()
    yield ai_gioco_repo
    imposta_servizio_ai(None)


def _mostro():
    return logica.Mostro("Oni", "Un oni.", ("Grr",))


async def _evento(repo, vita=100, scade=None):
    scade = scade or datetime.now(timezone.utc) + timedelta(minutes=30)
    return await repo.boss_crea(G, C, _mostro(), vita, scade)


async def test_un_solo_boss_attivo_per_canale(repo):
    assert await _evento(repo)
    assert await _evento(repo) is None


async def test_azioni_attesa_ferita_contrattacco_e_sconfitta(repo):
    ev = await _evento(repo, vita=1000)
    t0 = datetime.now(timezone.utc)
    ok = await repo.boss_agisci(ev, U1, "attacco", 30, 8, t0)
    assert ok.stato == "ok" and ok.vita == 970 and ok.danno == 30
    attesa = await repo.boss_agisci(ev, U1, "attacco", 30, 8, t0 + timedelta(seconds=2))
    assert attesa.stato == "attesa" and 1 <= attesa.secondi <= 6
    # U2 si mette in guardia; U1 no. Alla decima azione il boss colpisce solo chi non ha la guardia.
    assert (await repo.boss_agisci(ev, U2, "difesa", 0, 8, t0)).stato == "ok"
    t = t0 + timedelta(seconds=10)
    for i in range(7):
        assert (await repo.boss_agisci(ev, 9000 + i, "attacco", 1, 8, t)).stato == "ok"
    decima = await repo.boss_agisci(ev, U1, "attacco", 30, 8, t)
    assert decima.stato == "ok" and decima.contrattacco >= 8  # U1 e i sette passanti; non U2 (guardia)
    ferito = await repo.boss_agisci(ev, U1, "attacco", 30, 8, t + timedelta(seconds=10))
    assert ferito.stato == "ferito" and ferito.secondi > 0
    curato = await repo.boss_agisci(ev, U1, "cura", 0, 8, t + timedelta(seconds=10))
    assert curato.stato == "ok"
    assert (await repo.boss_agisci(ev, U1, "attacco", 30, 8, t + timedelta(seconds=20))).stato == "ok"
    guardia_usata = await repo.boss_agisci(ev, U2, "attacco", 10, 8, t + timedelta(seconds=20))
    assert guardia_usata.stato == "ok"  # U2 non era ferito
    finale = await repo.boss_agisci(ev, U2, "attacco", 5000, 8, t + timedelta(seconds=40))
    assert finale.sconfitto and finale.vita == 0
    assert (await repo.boss_agisci(ev, U1, "attacco", 5, 8, t + timedelta(seconds=60))).stato == "chiuso"
    assert (await repo.boss_evento(ev)).stato == "sconfitto"


async def test_scaduto_non_si_colpisce_e_si_chiude_come_fuggito(repo):
    ev = await _evento(repo, scade=datetime.now(timezone.utc) - timedelta(seconds=1))
    assert (await repo.boss_agisci(ev, U1, "attacco", 5, 8)).stato == "chiuso"
    assert [e.id for e in await repo.boss_scaduti()] == [ev]
    assert await repo.boss_chiudi(ev, "fuggito") and not await repo.boss_chiudi(ev, "fuggito")


async def test_scelta_del_mostro_ai_libreria_e_riserva(repo):
    cfg = await repo.boss_config(G)
    # AI spenta: mostro pronto del tema
    m, rete, extra = await boss.scegli_mostro(G, cfg, "fantasy", random.Random(1))
    assert m in logica.MOSTRI_PRONTI["fantasy"] and rete is None and extra == 0
    # AI accesa: il mostro scritto dall'AI entra nella libreria comune
    json_ai = '{"nome": "Orso di Cenere", "aspetto": "Grande e triste.", "frasi": ["Rawr"]}'
    servizio, _ = servizio_finto(ai_repo, trasporto=TrasportoFinto(risposte={"alfa": json_ai}))
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U1, True)
    m, _, _ = await boss.scegli_mostro(G, cfg, "fantasy", random.Random(0.9))
    assert m.nome == "Orso di Cenere"
    assert (await repo.mostro_libreria("fantasy")).nome == "Orso di Cenere"
    # un altro server (AI spenta) riusa quello della libreria
    visti = {(await boss.scegli_mostro(G + 1, cfg, "fantasy", random.Random(s)))[0].nome for s in range(20)}
    assert "Orso di Cenere" in visti


async def test_boss_di_rete_con_totali_in_comune(repo):
    rete_id = await repo.rete_crea(1, logica.Mostro("Titano", "", ("x",)), 500)
    cfg = await repo.boss_imposta(G, rete=True)
    m, rid, extra = await boss.scegli_mostro(G, cfg, "yokai", random.Random(1))
    assert (m.nome, rid, extra) == ("Titano", rete_id, 500)
    senza = await repo.boss_config(G + 5)
    assert (await boss.scegli_mostro(G + 5, senza, "yokai", random.Random(1)))[1] is None
    await repo.rete_aggiungi_totali(rete_id, G, 900, 4, True)
    await repo.rete_aggiungi_totali(rete_id, G + 1, 100, 2, False)
    assert await repo.rete_totali(rete_id) == (1000, 2, 6, 1)
    assert await repo.rete_chiudi() == 1 and await repo.rete_attiva() is None


async def test_premi_con_tetti_frammento_e_ruolo(repo, monkeypatch):
    ev_id = await _evento(repo, vita=60)
    t = datetime.now(timezone.utc)
    await repo.boss_agisci(ev_id, U1, "attacco", 50, 0, t)
    await repo.boss_agisci(ev_id, U2, "attacco", 10, 0, t)
    cfg = await repo.boss_imposta(G, ruolo_premio_id=77, ruolo_premio_ore=2)
    ruolo = MagicMock(spec=discord.Role)
    ruolo.id, ruolo.mention = 77, "<@&77>"
    membro = fake_member(U1)
    membro.add_roles = AsyncMock()
    guild = fake_guild(G)
    guild.get_role = MagicMock(return_value=ruolo)
    guild.get_member = MagicMock(side_effect=lambda uid: membro if uid == U1 else None)
    monkeypatch.setattr(boss, "check_role_assignable", lambda *a, **k: None)
    pianificate = []
    monkeypatch.setattr(boss.scheduler, "schedule", AsyncMock(side_effect=lambda *a, **k: pianificate.append(a)))
    testo = await boss.assegna_premi(guild, await repo.boss_evento(ev_id), cfg)
    assert "2 partecipanti" in testo and "<@&77>" in testo
    assert (await leveling_repo.get_totals(G, U1)).coins_total > 0 and (await leveling_repo.get_totals(G, U1)).xp_total > 0
    assert (await leveling_repo.get_totals(G, U1)).coins_total <= logica.PREMIO_MONETE_MAX
    assert await repo.frammenti(G, U2) == ["trofeo_boss"]
    membro.add_roles.assert_awaited_once()
    assert pianificate and pianificate[0][2] == boss.AZIONE_RUOLO


def _inter_boss(user_id, message_id):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(user_id))
    i.message = MagicMock()
    i.message.id = message_id
    i.client = MagicMock()
    return i


async def test_bottoni_attacco_magia_e_fine_evento(repo, monkeypatch):
    ev_id = await _evento(repo, vita=40)
    await repo.boss_imposta_messaggio(ev_id, 555)
    chiusure = []
    monkeypatch.setattr(boss, "chiudi_evento", AsyncMock(side_effect=lambda bot, eid, stato: chiusure.append((eid, stato))))
    vista = boss.BossView()
    i = _inter_boss(U1, 555)
    await vista._azione(i, "attacco")
    assert "Hai inflitto" in i.response.send_message.call_args.args[0] and ev_id in boss.AGGIORNA
    # magia senza monete: non parte e non costa nulla
    i2 = _inter_boss(U2, 555)
    await vista._azione(i2, "magia")
    assert "monete" in i2.response.send_message.call_args.args[0]
    await leveling_repo.add_coins(G, U2, 100)
    await vista._azione(i2, "magia")
    assert (await leveling_repo.get_totals(G, U2)).coins_total == 100 - logica.COSTO_MAGIA
    assert chiusure == [(ev_id, "sconfitto")] or (await repo.boss_evento(ev_id)).vita > 0
    # attesa: la magia rifiutata restituisce le monete
    i3 = _inter_boss(U2, 555)
    prima = (await leveling_repo.get_totals(G, U2)).coins_total
    await vista._azione(i3, "magia")
    assert (await leveling_repo.get_totals(G, U2)).coins_total == prima
    # evento inesistente
    i4 = _inter_boss(U1, 99999)
    await vista._azione(i4, "attacco")
    assert "finito" in i4.response.send_message.call_args.args[0]


async def test_avvia_evento_scrive_il_messaggio_con_immagine_e_bottoni(repo):
    canale = fake_text_channel(C)
    messaggio = MagicMock()
    messaggio.id = 4242
    canale.send = AsyncMock(return_value=messaggio)
    guild = fake_guild(G)
    cfg = await repo.boss_config(G)
    ev_id, motivo = await boss.avvia_evento(MagicMock(), guild, canale, cfg, random.Random(3))
    assert ev_id and not motivo
    kw = canale.send.call_args.kwargs
    assert kw["file"].filename == "boss.png" and isinstance(kw["view"], boss.BossView)
    assert kw["embed"].image.url == "attachment://boss.png"
    assert (await repo.boss_per_messaggio(4242)).id == ev_id
    again, motivo = await boss.avvia_evento(MagicMock(), guild, canale, cfg, random.Random(3))
    assert again is None and "già un boss" in motivo


async def test_comparsa_programmata_una_volta_per_giorno(repo, monkeypatch):
    adesso = datetime(2026, 10, 30, 20, 5, tzinfo=timezone.utc)  # venerdì 21:05 a Roma
    await repo.boss_imposta(G, attivo=True, canale_id=C, giorni=(4,), ora=21)
    canale = fake_text_channel(C)
    guild = fake_guild(G)
    guild.get_channel = MagicMock(return_value=canale)
    bot = MagicMock()
    bot.get_guild = MagicMock(return_value=guild)
    avviati = []

    async def finto(bot_, g, c, cfg, rng=None):
        avviati.append(c.id)
        return 1, ""

    monkeypatch.setattr(boss, "avvia_evento", finto)
    cog = boss.AiBossCog(bot)
    await cog._comparse_programmate(adesso)
    await cog._comparse_programmate(adesso + timedelta(minutes=1))
    assert avviati == [C]
    assert (await repo.boss_config(G)).ultimo_giorno.isoformat() == "2026-10-30"


async def test_comando_imposta_valida_i_valori(repo):
    cog = boss.AiBossCog(MagicMock())
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U1))
    i.guild_id = G
    await cog.boss_imposta.callback(cog, i, giorni="pippo")
    assert "Non capisco i giorni" in i.response.send_message.call_args.args[0]
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U1))
    i.guild_id = G
    await cog.boss_imposta.callback(cog, i, canale=fake_text_channel(C), giorni="ven", ora=21, fuso="Europe/Rome", acceso=True)
    cfg = await repo.boss_config(G)
    assert cfg.attivo and cfg.giorni == (4,) and cfg.canale_id == C
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U1))
    i.guild_id = G
    await cog.boss_imposta.callback(cog, i, fuso="Marte/Olympus")
    assert "Fuso orario sconosciuto" in i.response.send_message.call_args.args[0]


async def test_rete_solo_owner(repo, monkeypatch):
    from core.config import config

    cog = boss.AiBossCog(MagicMock())
    i = fake_interaction(guild=fake_guild(G), user=fake_member(U1))
    await cog.boss_rete.callback(cog, i, "Titano", "", 0)
    assert "solo del proprietario" in i.response.send_message.call_args.args[0] and await repo.rete_attiva() is None
    i = fake_interaction(guild=fake_guild(G), user=fake_member(config.OWNER_ID))
    await cog.boss_rete.callback(cog, i, "Titano", "Grande", 100)
    assert (await repo.rete_attiva())[1].nome == "Titano"
