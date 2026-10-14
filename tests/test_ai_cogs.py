"""
tests/test_ai_cogs.py
=====================
I comandi dell'AI con un fornitore finto e il database vero (SPEC §25):
consenso prima dell'accensione, risposta locale senza AI, -chiedi con
l'assistente e ritorno alla ricerca per parole, traduzione, immagine con i
bottoni, ingrandimento, pacchetti, ticket, costruzione del server, e le
funzioni pure dei cog.
"""

import io

import discord
import pytest
from PIL import Image

from cogs.ai import config as cfg_mod
from cogs.ai import images, summaries, ticket_ai, traduzione
from core.ai_servizio import imposta_servizio_ai
from core.ai_testi_logic import ComandoNoto, comandi_citati, leggi_giudizio, leggi_proposta_server, riconosci_lingua
from core.repositories.ai_repo import ai_repo
from tests.support.ai_finto import TrasportoFinto, fornitore, servizio_finto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

G, U = 666, 555


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_repo, "_pool_provider", lambda: clean_db)
    yield ai_repo
    imposta_servizio_ai(None)


def _inter(user_id=U, permessi=None):
    i = fake_interaction(guild=fake_guild(G), user=fake_member(user_id, guild_permissions=permessi))
    i.guild_id = G
    i.channel_id = i.channel.id
    return i


def _usa(repo, fornitori=None, risposte=None):
    servizio, trasporto = servizio_finto(repo, fornitori=fornitori, trasporto=TrasportoFinto(risposte=risposte))
    imposta_servizio_ai(servizio)
    return trasporto


async def test_attiva_chiede_il_consenso_poi_accende(repo):
    _usa(repo)
    cog = cfg_mod.AiConfigCog(bot=None)
    i = _inter()
    await cog.attiva.callback(cog, i, True)
    kwargs = i.response.send_message.call_args.kwargs
    assert "non addestrare" in kwargs["embed"].description
    assert not (await repo.get_config(G)).attivo
    view = kwargs["view"]
    clic = _inter()
    await view.conferma.callback(clic)
    cfg = await repo.get_config(G)
    assert cfg.attivo and cfg.consenso_da == U
    await cog.attiva.callback(cog, _inter(), False)
    assert not (await repo.get_config(G)).attivo


async def test_limiti_privacy_lore_vietate(repo):
    _usa(repo)
    cog = cfg_mod.AiConfigCog(bot=None)
    i = _inter()
    await cog.limiti.callback(cog, i, 500, 3, None, None, 2, 100)
    assert i.response.send_message.call_args.args[0] == "Limiti salvati.", i.response.send_message.call_args
    assert (await repo.get_config(G)).tetto_mensile_cent == 500
    await cog.privacy.callback(cog, _inter(), "senza_messaggi", 0, "corta")
    assert (await repo.get_config(G)).tetto_mensile_cent == 500, "dopo privacy"
    await cog.lore.callback(cog, _inter(), "pirati", "Isola di Tortuga")
    assert (await repo.get_config(G)).tetto_mensile_cent == 500, "dopo lore"
    await cog.vietate.callback(cog, _inter(), "aggiungi", "Politica")
    righe = await repo._pool.fetch("SELECT guild_id, tetto_mensile_cent, aggiornato_il FROM ai_config")
    cfg = await repo.get_config(G)
    assert cfg.tetto_mensile_cent == 500, righe
    assert (cfg.tetto_mensile_cent, cfg.quota_utente_giorno, cfg.quota_immagini_settimana, cfg.prezzo_pacchetto_immagini) == (500, 3, 2, 100)
    assert (cfg.privacy, cfg.conservazione_minuti, cfg.lunghezza) == ("senza_messaggi", 0, "corta")
    assert cfg.lore_tema == "pirati" and cfg.parole_vietate == ("politica",)


async def test_traduci_senza_ai_spiega_come_attivarla(repo):
    _usa(repo, fornitori=[])
    cog = traduzione.AiTraduzioneCog(bot=None)
    i = _inter()
    await cog.traduci.callback(cog, i, "ciao", "en")
    testo = i.followup.send.call_args.args[0]
    assert ".env" in testo


async def test_traduci_con_ai(repo):
    trasporto = _usa(repo, risposte={"alfa": "hello"})
    await repo.registra_consenso(G, U, True)
    cog = traduzione.AiTraduzioneCog(bot=None)
    i = _inter()
    await cog.traduci.callback(cog, i, "ciao", "en")
    assert i.followup.send.call_args.args[0] == "hello"
    assert "inglese" in trasporto.chiamate[0][1][0]["content"]


async def test_immagina_con_bottoni_e_ingrandisci(repo):
    _usa(repo, fornitori=[fornitore("img", tipi=("immagine",))])
    await repo.registra_consenso(G, U, True)
    cog = images.AiImmaginiCog(bot=None)
    i = _inter()
    await cog.immagina.callback(cog, i, "un gatto")
    kwargs = i.followup.send.call_args.kwargs
    assert isinstance(kwargs["file"], discord.File) and kwargs["view"].prompt == "un gatto"
    clic = _inter()
    await kwargs["view"].ingrandisci.callback(clic)
    file = clic.followup.send.call_args.kwargs["file"]
    assert Image.open(file.fp).size == (2, 2)
    altro = _inter(user_id=1)
    assert not await kwargs["view"].interaction_check(altro)


async def test_ingrandisci_rifiuta_un_file_non_immagine(repo):
    cog = images.AiImmaginiCog(bot=None)
    allegato = fake_interaction()  # oggetto qualsiasi con attributi
    allegato.content_type = "application/pdf"
    allegato.size = 10
    i = _inter()
    await cog.ingrandisci.callback(cog, i, allegato)
    assert "PNG" in i.response.send_message.call_args.args[0]


async def test_pacchetto_non_in_vendita(repo):
    cog = images.AiImmaginiCog(bot=None)
    i = _inter()
    await cog.pacchetto.callback(cog, i)
    assert "non sono in vendita" in i.response.send_message.call_args.args[0]


async def test_ticket_assistente_fuori_da_un_ticket(repo, monkeypatch):
    async def nessun_ticket(channel_id):
        return None
    monkeypatch.setattr(ticket_ai.ticket_repo, "get_ticket_by_channel", nessun_ticket)
    cog = ticket_ai.AiTicketCog(bot=None)
    i = _inter()
    await cog.assistente.callback(cog, i)
    assert "dentro un ticket" in i.response.send_message.call_args.args[0]


async def test_costruisci_mostra_la_proposta_e_non_crea_senza_conferma(repo):
    proposta = '{"ruoli": ["Admin"], "categorie": [{"nome": "Info", "canali": [{"nome": "Regole!!", "tipo": "testo"}]}]}'
    _usa(repo, fornitori=[fornitore("alfa", fascia="media")], risposte={"alfa": proposta})
    await repo.registra_consenso(G, U, True)
    cog = cfg_mod.AiConfigCog(bot=None)
    i = _inter()
    await cog.costruisci.callback(cog, i, "server per un clan di gioco")
    kwargs = i.followup.send.call_args.kwargs
    assert "embed" in kwargs, i.followup.send.call_args
    assert "#regole" in kwargs["embed"].description
    i.guild.create_role.assert_not_called()
    clic = _inter()
    await kwargs["view"].crea.callback(clic)
    clic.guild.create_role.assert_awaited_once()
    clic.guild.create_text_channel.assert_awaited_once()


def test_funzioni_pure_dei_cog():
    assert summaries.numeri_del_canale(["a", "b", "a"]).startswith("3 messaggi da 2 persone")
    assert summaries.numeri_del_canale([]) == "Nessun messaggio da riassumere."
    assert not traduzione.serve_tradurre("https://x.y", "en")
    assert not traduzione.serve_tradurre("the cat is with you", "en")
    assert traduzione.serve_tradurre("il gatto è con te", "en")
    assert "urgenza 4/5" in ticket_ai.testo_smistamento({"categoria": "pagamenti", "urgenza": 4, "ruolo": "amministratore"})
    assert riconosci_lingua("hello how are you") == "en" and riconosci_lingua("xyz") == "it"


def test_comandi_citati_e_proposte():
    comandi = [ComandoNoto("mod timeout", "Timeout"), ComandoNoto("modban ban", "Ban"), ComandoNoto("ticket add", "Aggiungi")]
    citati = comandi_citati("Usa /mod timeout utente: Mario durata: 10m, poi /modban ban o /inventato", comandi)
    assert [c.percorso for c in citati] == ["mod timeout", "modban ban"]
    assert leggi_proposta_server("niente json") is None
    p = leggi_proposta_server('```{"ruoli": ' + str(list(map(str, range(20)))).replace("'", '"') + "}```")
    assert len(p.ruoli) == 10
    g = leggi_giudizio('{"violazione": true, "motivo": "insulti", "gravita": 9}')
    assert g.violazione and g.gravita == 5
    assert leggi_giudizio("boh") is None


async def test_chiedi_con_assistente_ai_e_ritorno_alla_ricerca(repo, monkeypatch):
    from cogs.utility import command_search
    from core.command_search_logic import ComandoInfo

    comandi = [ComandoInfo("mod timeout", "Mette in timeout un membro", "mod", ())]
    cog = command_search.CommandSearchCog(bot=None)

    async def accessibili(interaction):
        return comandi

    async def ids(interaction, serve=()):
        return {"mod": 42}

    monkeypatch.setattr(cog, "_comandi_accessibili", accessibili)
    monkeypatch.setattr(cog, "_ids", ids)
    _usa(repo, risposte={"alfa": "Usa /mod timeout con utente Mario e durata 10m."})
    await repo.registra_consenso(G, U, True)
    i = _inter()
    await cog.chiedi.callback(cog, i, "metti in timeout Mario per 10 minuti")
    embed = i.followup.send.call_args.kwargs["embed"]
    assert embed.title == "Assistente" and "</mod timeout:42>" in embed.description

    # AI spenta nel server: si torna alla ricerca per parole, senza errori
    await repo.registra_consenso(G, U, False)
    ricerche = []

    async def ricerca(interaction, query, nota=None, *, gia_differita=False):
        ricerche.append(query)

    monkeypatch.setattr(cog, "_ricerca", ricerca)
    await cog.chiedi.callback(cog, _inter(), "timeout")
    assert ricerche == ["timeout"]
