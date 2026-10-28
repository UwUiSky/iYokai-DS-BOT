"""
tests/test_ai_dungeon.py
========================
Dungeon di gruppo (§25.53–§25.55, §25.99): libreria comune, AI per i rami mancanti, voto, esito, premi.
Database vero, fornitore AI finto, Discord finto.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs.ai import dungeon
from core import dungeon_logic as logica
from core.ai_servizio import imposta_servizio_ai
from core.database import db
from core.repositories.ai_gioco_repo import ai_gioco_repo
from core.repositories.ai_repo import ai_repo
from core.repositories.leveling_repo import leveling_repo
from core.repositories.leveling_settings_repo import leveling_settings_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, C, U1, U2 = 8201, 8202, 8203, 8204


class Sempre:
    """Sorte truccata: tutto riesce, a pari voti vince la prima scelta."""

    def random(self):
        return 0.0

    def choice(self, x):
        return x[0]

    def randrange(self, n):
        return 0


class Mai(Sempre):
    def random(self):
        return 0.999


@pytest.fixture
def repo(clean_db, monkeypatch):
    for r in (ai_gioco_repo, ai_repo, leveling_repo, leveling_settings_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    dungeon.AGGIORNA.clear()
    yield ai_gioco_repo
    imposta_servizio_ai(None)


def _bot():
    canale = MagicMock()
    messaggio = MagicMock()
    messaggio.edit = AsyncMock()
    canale.fetch_message = AsyncMock(return_value=messaggio)
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=canale)
    bot.messaggio = messaggio
    return bot


STORIA_AI = {
    "titolo": "La torre",
    "inizio": "a",
    "nodi": [
        {"id": "a", "testo": "Una torre.", "scelte": [
            {"testo": "Sali", "prova": "forza", "difficolta": 1, "successo": "b", "fallimento": "c"},
            {"testo": "Aspetta", "prova": "magia", "difficolta": 1, "successo": "mancante", "fallimento": "c"}]},
        {"id": "b", "testo": "Vittoria!", "finale": True, "esito": "vittoria"},
        {"id": "c", "testo": "Sconfitta.", "finale": True, "esito": "sconfitta"},
    ],
}


async def _partita(repo, storia_id, nodo="inizio", stato="in_corso", scaduta=True):
    scade = datetime.now(timezone.utc) + timedelta(seconds=-1 if scaduta else 60)
    pid = await repo.partita_crea(G, C, storia_id, nodo, scade)
    await repo.partita_imposta_messaggio(pid, 900)
    if stato == "in_corso":
        await repo.partita_avanza(pid, nodo, scade, None)
    return pid


async def test_senza_ai_si_usa_la_storia_pronta_e_poi_la_libreria_comune(repo):
    sid, storia = await dungeon.scegli_storia(G, U1, "fantasy", "")
    assert storia.titolo == "La porta nell'ombra" and sid
    # la storia pronta non entra tra quelle scritte dall'AI per il tema
    assert await repo.storie_conta("fantasy") == 0
    # l'AI scrive una storia: finisce nella libreria e un altro server la riusa senza chiamare l'AI
    servizio, trasporto = servizio_finto(ai_repo, fornitori=[fornitore(fascia="media")], trasporto=TrasportoFinto(risposte={"alfa": json.dumps(STORIA_AI)}))
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U1, True)
    sid2, storia2 = await dungeon.scegli_storia(G, U1, "fantasy", "")
    assert storia2.titolo == "La torre" and await repo.storie_conta("fantasy") == 1
    chiamate = len(trasporto.chiamate)
    sid3, storia3 = await dungeon.scegli_storia(G + 7, U2, "fantasy", "")
    assert sid3 == sid2 and len(trasporto.chiamate) == chiamate
    # chi l'ha già giocata di recente ne riceve una nuova
    await _partita(repo, sid2, "a", stato="lobby")
    assert (await repo.storie_giocate(G)) == (sid2,)


async def test_lobby_vuota_si_annulla(repo):
    sid, storia = await dungeon.scegli_storia(G, U1, "yokai", "")
    pid = await _partita(repo, sid, storia.inizio, stato="lobby")
    bot = _bot()
    await dungeon.avanza(bot, await repo.partita(pid))
    assert (await repo.partita(pid)).esito == "annullata"
    bot.messaggio.edit.assert_awaited()


async def test_partita_intera_vittoria_con_premi_e_ramo_scritto_dall_ai(repo):
    servizio, trasporto = servizio_finto(ai_repo, fornitori=[fornitore(fascia="media")], trasporto=TrasportoFinto(risposte={"alfa": json.dumps(STORIA_AI)}))
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U1, True)
    sid, storia = await dungeon.scegli_storia(G, U1, "yokai", "")
    pid = await _partita(repo, sid, storia.inizio, stato="lobby")
    await repo.partita_giocatore(pid, U1, "Samurai")
    await repo.partita_giocatore(pid, U2, "Miko")
    bot = _bot()
    await dungeon.avanza(bot, await repo.partita(pid))  # la lobby parte
    p = await repo.partita(pid)
    assert p.stato == "in_corso" and p.nodo == "a"
    assert bot.messaggio.edit.call_args.kwargs["view"].children[0].custom_id == "aidg:v0"
    await repo.partita_voto(pid, U1, 0)
    await repo.partita_voto(pid, U2, 0)
    await db.pool.execute("UPDATE ai_dungeon_partite SET scade_il = now() - interval '1 second' WHERE id = $1", pid)
    await dungeon.avanza(bot, await repo.partita(pid), Sempre())
    p = await repo.partita(pid)
    assert p.stato == "finita" and p.esito == "vittoria" and p.cronologia == ("Sali (riuscita)",)
    assert (await leveling_repo.get_totals(G, U1)).coins_total == dungeon.PREMIO_MONETE
    assert await repo.frammenti(G, U2) == ["dungeon"]
    assert bot.messaggio.edit.call_args.kwargs["view"] is None


async def test_ramo_mancante_lo_scrive_l_ai_e_resta_in_libreria(repo):
    nodo_ai = {"testo": "Una stanza nuova.", "scelte": [{"testo": "Avanti"}, {"testo": "Indietro"}]}
    servizio, trasporto = servizio_finto(
        ai_repo, fornitori=[fornitore(fascia="media")], trasporto=TrasportoFinto(risposte={"alfa": lambda m: json.dumps(STORIA_AI if "dungeon di gruppo a bivi" in str(m) else nodo_ai)})
    )
    imposta_servizio_ai(servizio)
    await ai_repo.registra_consenso(G, U1, True)
    sid, storia = await dungeon.scegli_storia(G, U1, "yokai", "")
    pid = await _partita(repo, sid, "a")
    await repo.partita_giocatore(pid, U1, "Miko")
    await repo.partita_voto(pid, U1, 1)  # "Aspetta" → ramo "mancante"
    bot = _bot()
    await dungeon.avanza(bot, await repo.partita(pid), Sempre())
    p = await repo.partita(pid)
    assert p.stato == "in_corso" and p.nodo == "mancante"
    salvata = await repo.storia_carica(sid)
    assert salvata.nodo("mancante").testo == "Una stanza nuova." and len(salvata.nodo("mancante").scelte) == 2


async def test_ramo_mancante_senza_ai_chiude_con_un_finale_pronto_non_salvato(repo):
    sid = await repo.storia_salva("yokai", logica.leggi_storia(json.dumps(STORIA_AI)))
    pid = await _partita(repo, sid, "a")
    await repo.partita_giocatore(pid, U1, "Miko")
    await repo.partita_voto(pid, U1, 1)
    await dungeon.avanza(_bot(), await repo.partita(pid), Sempre())
    assert (await repo.partita(pid)).stato == "finita"
    assert (await repo.storia_carica(sid)).nodo("mancante") is None


async def test_la_storia_non_si_allunga_oltre_il_tetto(repo):
    sid = await repo.storia_salva("yokai", logica.leggi_storia(json.dumps(STORIA_AI)))
    pid = await _partita(repo, sid, "a")
    await db.pool.execute(
        "UPDATE ai_dungeon_partite SET cronologia = $2 WHERE id = $1", pid, [f"s{i}" for i in range(logica.MAX_STANZE - 1)]
    )
    await repo.partita_giocatore(pid, U1, "Miko")
    await repo.partita_voto(pid, U1, 1)
    await dungeon.avanza(_bot(), await repo.partita(pid), Sempre())
    p = await repo.partita(pid)
    assert p.stato == "finita" and p.esito == "neutro"


async def test_bottoni_classe_e_voto(repo):
    sid = await repo.storia_salva("yokai", logica.leggi_storia(json.dumps(STORIA_AI)))
    pid = await _partita(repo, sid, "a", stato="lobby", scaduta=False)

    def inter(uid):
        i = fake_interaction(guild=fake_guild(G), user=fake_member(uid))
        i.message = MagicMock()
        i.message.id = 900
        return i

    i = inter(U1)
    await dungeon.scelta_classe(i, 1)
    assert "Ninja" in i.response.send_message.call_args.args[0]
    assert (await repo.partita_giocatori(pid)) == [(U1, "Ninja", None)]
    i = inter(U1)
    await dungeon.voto(i, 0)
    assert "non è aperto" in i.response.send_message.call_args.args[0]
    await repo.partita_avanza(pid, "a", datetime.now(timezone.utc) + timedelta(seconds=60), None)
    await dungeon.voto(inter(U1), 1)
    await dungeon.voto(inter(U2), 0)  # arriva in corsa: entra con la prima classe
    assert sorted(await repo.partita_giocatori(pid)) == [(U1, "Ninja", 1), (U2, "Samurai", 0)]
    i = inter(U1)
    i.message.id = 12345
    await dungeon.scelta_classe(i, 0)
    assert "già cominciata" in i.response.send_message.call_args.args[0]


async def test_avvia_partita_scrive_la_lobby_con_le_classi_del_tema(repo):
    await ai_repo.imposta(G, lore_tema="fantasy")
    canale = fake_text_channel(C)
    messaggio = MagicMock()
    messaggio.id = 901
    canale.send = AsyncMock(return_value=messaggio)
    pid, motivo = await dungeon.avvia_partita(MagicMock(), fake_guild(G), canale, U1)
    assert pid and not motivo
    vista = canale.send.call_args.kwargs["view"]
    assert [b.label for b in vista.children] == ["Guerriero", "Ladro", "Mago"]
    assert (await repo.partita_per_messaggio(901)).id == pid
    assert (await dungeon.avvia_partita(MagicMock(), fake_guild(G), canale, U1))[0] is None


def test_vista_registrata_all_avvio_ha_tutti_i_bottoni():
    ids = [b.custom_id for b in dungeon.DungeonView().children]
    assert ids == ["aidg:c0", "aidg:c1", "aidg:c2", "aidg:v0", "aidg:v1", "aidg:v2"]
