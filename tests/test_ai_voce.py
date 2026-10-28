"""
tests/test_ai_voce.py
=====================
Voce di Yokai (§25.102-25.105): profili e toni, testo per la voce, cache, servizio con motore finto, corpo del vocale,
saluti raccolti, bottoni sotto il vocale, trascrizione. Database vero, Discord e motore finti.
"""

import io
import math
import struct
import wave
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.ai import voce
from core import voice_saluti_logic as saluti
from core import voice_text_logic as testo_logic
from core.database import db
from core.discord_raw import corpo_vocale
from core.repositories.ai_voce_repo import ai_voce_repo
from core.trascrizione import Trascrittore, leggi_config, imposta_trascrittore, vocale_accettabile
from core.voice_cache import CacheVoce, VocaleSalvato, chiave
from core.voice_client import ServizioVoce, imposta_servizio_voce
from core.voice_engine import leggi_motore
from core.voice_profile import profilo, tono_consentito, tono_valido
from tests.support.discord_fakes import fake_interaction, fake_text_channel

G = 9201


def _wav(secondi: float = 0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(int(22050 * secondi))))
    return buf.getvalue()


class MotoreFinto:
    nome, versione = "finto", "1"

    def __init__(self):
        self.chiamate = 0

    async def sintetizza(self, frasi, profilo):
        self.chiamate += 1
        return _wav()


@pytest.fixture
def repo(clean_db, monkeypatch):
    monkeypatch.setattr(ai_voce_repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(db, "_pool", clean_db, raising=False)
    yield ai_voce_repo
    imposta_servizio_voce(None)
    imposta_trascrittore(None)


def test_tono_piccante_solo_nei_canali_nsfw():
    assert tono_consentito("piccante", False) != "piccante"
    assert tono_consentito("piccante", True) == "piccante"
    assert tono_valido("boh") == tono_valido(None)
    assert profilo("PUBLIC", "piccante", False) != profilo("PUBLIC", "piccante", True)


def test_testo_per_la_voce_toglie_menzioni_link_ed_emoji():
    t = testo_logic.prepara("Ciao **mondo** <@123> https://x.it <:a:5> guarda!")
    assert "http" not in t and "<@" not in t and "**" not in t and "<:" not in t
    assert len(testo_logic.prepara("a " * 500)) <= 400
    assert testo_logic.nome_pronunciabile("x_y_z") is None


def test_cache_rilegge_e_chiave_dipende_dal_profilo(tmp_path):
    c = CacheVoce(tmp_path)
    k = chiave("ciao", "a", "finto", "1")
    assert c.leggi(k) is None
    c.scrivi(k, VocaleSalvato(b"ogg", 1.5, "AAA"))
    assert c.leggi(k) == VocaleSalvato(b"ogg", 1.5, "AAA")
    assert chiave("ciao", "b", "finto", "1") != k


async def test_servizio_genera_poi_usa_la_cache(tmp_path):
    motore = MotoreFinto()
    s = ServizioVoce(motore, CacheVoce(tmp_path))
    v1 = await s.genera("Ciao a tutti", profilo("PUBLIC", "dolce"))
    v2 = await s.genera("Ciao a tutti", profilo("PUBLIC", "dolce"))
    assert v1 and v1.ogg[:4] == b"OggS" and v1.durata > 0 and not v1.da_cache
    assert v2 and v2.da_cache and motore.chiamate == 1


async def test_senza_motore_o_con_errore_si_torna_al_testo(tmp_path):
    assert await ServizioVoce(None, None).genera("Ciao", profilo("PUBLIC")) is None

    class Rotto(MotoreFinto):
        async def sintetizza(self, frasi, profilo):
            raise RuntimeError("no")

    assert await ServizioVoce(Rotto(), None).genera("Ciao", profilo("PUBLIC")) is None


def test_motore_spento_senza_cartella(monkeypatch):
    assert leggi_motore({}) is None
    assert leggi_motore({"VOCE_MODELLO_DIR": "/non/esiste"}) is None
    assert leggi_motore({"VOCE_ATTIVA": "no", "VOCE_MODELLO_DIR": "/tmp"}) is None


def test_corpo_del_vocale_ha_flag_durata_e_onda():
    c = corpo_vocale(2.5, "AAAA", risposta_a=5, canale_id=9)
    assert c["flags"] == 1 << 13 and c["attachments"][0]["duration_secs"] == 2.5 and c["attachments"][0]["waveform"] == "AAAA"
    assert c["message_reference"]["message_id"] == 5


def test_saluti_si_raccolgono_e_poi_pausa():
    assert saluti.riconosci_saluto("ciao a tutti") is not None
    assert saluti.riconosci_saluto("oggi piove forte") is None
    r = saluti.RaccoltaSaluti()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert r.aggiungi(1, "ciao", "Anna", t0) is True
    assert r.aggiungi(1, "ciao", "Luca", t0) is False
    saluto, nomi = r.chiudi(1, t0)
    assert nomi == ["Anna", "Luca"]
    assert r.aggiungi(1, "ciao", "Zoe", t0 + timedelta(seconds=30)) is False
    assert r.aggiungi(1, "ciao", "Zoe", t0 + timedelta(minutes=3)) is True
    frase, _ = saluti.frase_saluto("ciao", ["Anna", "Luca"])
    assert "Anna" in frase and "Luca" in frase


async def test_config_voce_default_spenta_e_tono_valido(repo):
    c = await repo.config(G)
    assert c.attiva is False
    c = await repo.imposta(G, attiva=True, tono="dolce", canali_saluti=[5])
    assert c.attiva and c.tono == "dolce" and c.canali_saluti == (5,) or list(c.canali_saluti) == [5]
    with pytest.raises(ValueError):
        await repo.imposta(G, tono="strano")


async def test_vocale_salvato_si_rilegge(repo):
    await repo.salva_vocale(55, G, 1, "Ciao", "it")
    v = await repo.vocale(55)
    assert v.testo == "Ciao" and v.lingua == "it"
    assert await repo.vocale(56) is None


def _bot_finto():
    bot = MagicMock()
    bot.http = MagicMock()
    return bot


async def test_parla_senza_motore_manda_solo_testo(repo):
    imposta_servizio_voce(ServizioVoce(None, None))
    canale = fake_text_channel()
    canale.send = AsyncMock()
    assert await voce.parla(_bot_finto(), canale, "Ciao a tutti", "PUBLIC", guild_id=G) is False
    canale.send.assert_awaited_once()


async def test_parla_con_motore_invia_vocale_e_salva_testo(repo, monkeypatch):
    imposta_servizio_voce(ServizioVoce(MotoreFinto(), None))
    inviato = AsyncMock(return_value=4001)
    monkeypatch.setattr(voce, "invia_vocale", inviato)
    canale = fake_text_channel()
    sotto = MagicMock(id=4002)
    canale.send = AsyncMock(return_value=sotto)
    assert await voce.parla(_bot_finto(), canale, "Ciao a tutti", "PUBLIC", guild_id=G) is True
    inviato.assert_awaited_once()
    assert (await repo.vocale(4002)).testo.startswith("Ciao")


async def test_bottone_trascrivi_mostra_il_testo_a_chi_preme(repo):
    await repo.salva_vocale(4010, G, 1, "Testo del vocale", "it")
    i = fake_interaction()
    i.message = MagicMock(id=4010)
    await voce.VocaleView().trascrivi.callback(i)
    assert "Testo del vocale" in i.response.send_message.call_args.args[0]
    assert i.response.send_message.call_args.kwargs["ephemeral"] is True


async def test_bottone_lingua_senza_ai_ricade_sul_testo_originale(repo, monkeypatch):
    await repo.salva_vocale(4011, G, 1, "Buongiorno a tutti", "it")
    i = fake_interaction()
    i.message = MagicMock(id=4011)
    i.locale = discord.Locale.american_english
    i.guild_id, i.channel_id = G, 1
    monkeypatch.setattr(voce, "chiedi", AsyncMock(return_value=(None, "AI ferma")))
    await voce.VocaleView().nella_mia_lingua.callback(i)
    assert "Buongiorno a tutti" in i.followup.send.call_args.args[0]


def test_trascrizione_si_accende_solo_senza_addestramento():
    assert leggi_config({}) is None
    assert leggi_config({"VOCE_TRASCRIZIONE_URL": "https://x.it/v1"}) is None
    assert leggi_config({"VOCE_TRASCRIZIONE_URL": "http://x.it", "VOCE_TRASCRIZIONE_ADDESTRA": "no"}) is None
    assert leggi_config({"VOCE_TRASCRIZIONE_URL": "https://x.it/v1", "VOCE_TRASCRIZIONE_ADDESTRA": "no"}).modello
    assert vocale_accettabile(500, 10) and vocale_accettabile(5, 10**9) and vocale_accettabile(5, 100) is None


async def test_trascrittore_con_trasporto_finto():
    async def trasporto(cfg, audio, nome):
        return {"text": "  ciao   mondo "}

    cfg = leggi_config({"VOCE_TRASCRIZIONE_URL": "https://x.it/v1", "VOCE_TRASCRIZIONE_ADDESTRA": "no"})
    assert await Trascrittore(cfg, trasporto).trascrivi(b"x") == "ciao mondo"
    assert await Trascrittore(None).trascrivi(b"x") is None


async def test_menu_trascrivi_spento_lo_dice():
    imposta_trascrittore(Trascrittore(None))
    i = fake_interaction()
    allegato = MagicMock(duration=3.0, size=100)
    allegato.is_voice_message.return_value = True
    m = MagicMock(attachments=[allegato])
    await voce.trascrivi_e_traduci(i, m)
    assert "non è attiva" in i.response.send_message.call_args.args[0]
    m2 = MagicMock(attachments=[])
    await voce.trascrivi_e_traduci(i, m2)
    assert "non è un vocale" in i.response.send_message.call_args.args[0]


def test_raccolta_messaggi_della_stessa_persona():
    from core.traduzione_gruppo_logic import MAX_MESSAGGI, RaccoltaMessaggi

    r = RaccoltaMessaggi()
    assert r.aggiungi(1, 2, 10, "uno") is True
    assert r.aggiungi(1, 2, 11, "due") is False
    assert r.aggiungi(1, 3, 12, "altro") is True  # altra persona: raccolta a parte
    assert r.chiudi(1, 2) == ([10, 11], "uno\ndue")
    assert r.chiudi(1, 2) is None
    for i in range(MAX_MESSAGGI + 3):
        r.aggiungi(5, 5, i, "x")
    assert len(r.chiudi(5, 5)[0]) == MAX_MESSAGGI
