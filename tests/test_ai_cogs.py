"""
tests/test_ai_cogs.py
=====================
I comandi dell'AI con un fornitore finto e il database vero (SPEC §25):
consenso prima dell'accensione, risposta locale senza AI, -chiedi con
l'assistente e ritorno alla ricerca per parole, traduzione, immagine con i
bottoni, ingrandimento, pacchetti, ticket, costruzione del server, e le
funzioni pure dei cog.
"""


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


def test_risposte_ai_strane_non_rompono_i_cog():
    """JSON con tipi sbagliati: niente eccezioni, niente campi oltre 1024 caratteri, 'false' è falso."""
    assert leggi_proposta_server('{"ruoli": "admin", "categorie": {"a": 1}}').ruoli == ("admin",)
    assert leggi_proposta_server('{"categorie": [{"nome": "x", "canali": 5}]}') is not None
    assert not leggi_giudizio('{"violazione": "false", "gravita": 3}').violazione
    assert leggi_giudizio('{"violazione": "true", "gravita": 3}').violazione
    lungo = ticket_ai.testo_smistamento({"categoria": "a", "urgenza": "9" * 3000, "ruolo": "r" * 3000})
    assert len(lungo) <= 1024


async def test_chiedi_con_motore_in_errore_torna_alla_ricerca(repo, monkeypatch):
    """Errore imprevisto dopo il defer (es. database): -chiedi risponde con la ricerca per parole."""
    from cogs.utility import command_search

    cog = command_search.CommandSearchCog(bot=None)

    async def accessibili(interaction):
        return []

    monkeypatch.setattr(cog, "_comandi_accessibili", accessibili)
    _usa(repo)
    await repo.registra_consenso(G, U, True)

    async def rotto(*a, **kw):
        raise RuntimeError("database giù")

    monkeypatch.setattr(repo, "prenota", rotto)
    ricerche = []

    async def ricerca(interaction, query, nota=None, *, gia_differita=False):
        ricerche.append((query, gia_differita))

    monkeypatch.setattr(cog, "_ricerca", ricerca)
    await cog.chiedi.callback(cog, _inter(), "come si banna")
    assert ricerche == [("come si banna", True)]


async def _quota_persona_finita(repo):
    """La persona U ha già usato l'unica richiesta del giorno."""
    from core.ai_servizio import RichiestaAI, servizio_ai

    await repo.registra_consenso(G, U, True)
    await repo.imposta(G, quota_utente_giorno=1)
    await servizio_ai().richiedi(RichiestaAI(user_id=U, funzione="chiedi", tipo="chat", testo="prima", guild_id=G))


def _messaggio(testo, canale_id=4242):
    from tests.support.discord_fakes import fake_message

    autore = fake_member(U)
    autore.bot = False
    return fake_message(author=autore, channel=fake_text_channel(canale_id), guild=fake_guild(G), content=testo)


async def test_moderazione_ai_non_usa_la_quota_di_chi_scrive(repo):
    """Il controllo lo chiede il server: parte anche se l'autore ha finito le sue richieste, e non gliele conta."""
    from cogs.ai import moderazione

    trasporto = _usa(repo, fornitori=[fornitore("alfa", fascia="media")], risposte={"alfa": '{"violazione": false}'})
    await _quota_persona_finita(repo)
    await repo.imposta(G, moderazione_canali=[4242])
    cog = moderazione.AiModerazioneCog(bot=None)
    await cog.on_message(_messaggio("messaggio da controllare"))
    assert len(trasporto.chiamate) == 2
    assert (await repo.uso(G, U, "moderazione")).utente_oggi == 1


async def test_traduzione_automatica_non_usa_la_quota_di_chi_scrive(repo, monkeypatch):
    monkeypatch.setattr(traduzione, "ATTESA_SECONDI", 0)
    trasporto = _usa(repo, risposte={"alfa": "the cat is with you"})
    await _quota_persona_finita(repo)
    cog = traduzione.AiTraduzioneCog(bot=None)
    cog.canali = {4242: "en"}
    messaggio = _messaggio("il gatto è con te")
    await cog.on_message(messaggio)
    assert len(trasporto.chiamate) == 2
    assert "the cat is with you" in messaggio.channel.send.call_args.args[0]
    assert (await repo.uso(G, U, "traduzione_auto")).utente_oggi == 1


async def test_traduzione_automatica_unisce_i_messaggi_di_fila(repo, monkeypatch):
    """Tre messaggi della stessa persona nell'attesa: una sola richiesta con tutto il testo (AI-R-084)."""
    import asyncio

    monkeypatch.setattr(traduzione, "ATTESA_SECONDI", 0.2)
    trasporto = _usa(repo, risposte={"alfa": "the cat is with you and the dog too"})
    await repo.registra_consenso(G, U, True)
    cog = traduzione.AiTraduzioneCog(bot=None)
    cog.canali = {4242: "en"}
    m1, m2, m3 = (_messaggio(t) for t in ("il gatto è con te", "e anche il cane", "buona giornata a tutti"))
    m2.id, m3.id = 778, 779
    await asyncio.gather(cog.on_message(m1), cog.on_message(m2), cog.on_message(m3))
    assert len(trasporto.chiamate) == 2
    assert m1.channel.send.await_count == 1
    contenuto = trasporto.chiamate[0][1][-1]["content"]
    assert "il gatto" in contenuto and "il cane" in contenuto and "buona giornata" in contenuto


async def test_spiega_non_svela_un_thread_privato(repo):
    """Il thread privato eredita i permessi dal padre: senza iscrizione il messaggio non si legge."""
    from unittest.mock import AsyncMock, MagicMock

    trasporto = _usa(repo)
    await repo.registra_consenso(G, U, True)
    thread = MagicMock(spec=discord.Thread)
    thread.is_private.return_value = True
    thread.permissions_for.return_value = discord.Permissions(view_channel=True, read_message_history=True)
    thread.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "no"))
    thread.fetch_message = AsyncMock(return_value=MagicMock(content="segreto del thread"))
    i = _inter()
    i.guild.get_channel_or_thread = MagicMock(return_value=thread)
    cog = summaries.AiRiassuntiCog(bot=None)
    await cog.spiega.callback(cog, i, f"https://discord.com/channels/{G}/1/2")
    assert i.followup.send.call_args.args[0] == "Non puoi leggere quel messaggio."
    assert trasporto.chiamate == [] and not thread.fetch_message.await_count

    thread.fetch_member = AsyncMock(return_value=MagicMock())
    i2 = _inter()
    i2.guild.get_channel_or_thread = MagicMock(return_value=thread)
    await cog.spiega.callback(cog, i2, f"https://discord.com/channels/{G}/1/2")
    assert len(trasporto.chiamate) == 1
