"""
tests/test_entertainment_image_commands.py
================================================
Comandi immagine di /fun (grayscale, invert, blur, pixelate, meme —
SPEC.md §16.2/§16.3): priorità allegato > utente menzionato > autore,
validazione dell'allegato, e (SEC-20) ordine delle operazioni: prima
`defer()`, poi download ed elaborazione, risposta con followup; un
allegato troppo grande viene rifiutato PRIMA di scaricarlo.

Interaction, allegati e avatar sono finti fedeli (autospec); le
immagini sono vere e l'elaborazione Pillow gira davvero.
"""

import io
from unittest.mock import create_autospec

import aiohttp
import discord
import pytest
from PIL import Image

from cogs.fun.entertainment import MODULE_FUN, EntertainmentCog
from core.database import db
from core.safe_image import MAX_IMAGE_BYTES
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

ID_SERVER = 100

NON_UN_IMMAGINE = b"non e' un'immagine"


def _png(colore=(10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), colore).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
async def _modulo_fun_attivo(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, MODULE_FUN, True)
    yield
    database_module.db._modules_cache.clear()


@pytest.fixture
def cog() -> EntertainmentCog:
    return EntertainmentCog(bot=None)


class _Scena:
    """
    Un'interazione finta che annota l'ORDINE di ciò che succede:
    "defer", "download", "followup", "risposta" (send_message diretto).
    """

    def __init__(self, avatar_autore: bytes = NON_UN_IMMAGINE) -> None:
        self.ordine: list[str] = []
        self.interazione = fake_interaction(guild=fake_guild(ID_SERVER))
        self.interazione.user = self.membro(avatar_autore)
        self.interazione.response.defer.side_effect = self._annota("defer")
        self.interazione.response.send_message.side_effect = self._annota("risposta")
        self.interazione.followup.send.side_effect = self._annota("followup")

    def _annota(self, nome: str, risultato=None):
        async def _effetto(*args, **kwargs):
            self.ordine.append(nome)
            return risultato

        return _effetto

    def membro(self, avatar: bytes):
        membro = fake_member()
        membro.display_avatar = create_autospec(discord.Asset, instance=True)
        membro.display_avatar.read.side_effect = self._annota("download", avatar)
        return membro

    def allegato(self, contenuto: bytes, content_type: str = "image/png", size: int | None = None):
        allegato = create_autospec(discord.Attachment, instance=True)
        allegato.content_type = content_type
        allegato.size = len(contenuto) if size is None else size
        allegato.read.side_effect = self._annota("download", contenuto)
        return allegato

    @property
    def file_inviato(self) -> discord.File:
        return self.interazione.followup.send.await_args.kwargs["file"]

    @property
    def testo_followup(self) -> str:
        return self.interazione.followup.send.await_args.args[0]

    @property
    def testo_risposta(self) -> str:
        return self.interazione.response.send_message.await_args.args[0]

    @property
    def risposta_effimera(self) -> bool:
        return self.interazione.response.send_message.await_args.kwargs.get("ephemeral") is True


async def _lancia(cog: EntertainmentCog, comando: str, scena: _Scena, **opzioni) -> None:
    opzioni.setdefault("image", None)
    opzioni.setdefault("utente", None)
    await getattr(cog, comando).callback(cog, scena.interazione, **opzioni)


COMANDI = [
    ("grayscale", {}, "grayscale.png"),
    ("invert", {}, "invert.png"),
    ("blur", {"raggio": 5}, "blur.png"),
    ("pixelate", {"dimensione_blocco": 8}, "pixelate.png"),
    ("meme", {"top_text": "Ciao", "bottom_text": "Mondo"}, "meme.png"),
]


class TestDeferPrimaDiTutto:
    @pytest.mark.parametrize("comando,opzioni,nome_file", COMANDI)
    async def test_defer_poi_download_poi_followup(self, cog, comando, opzioni, nome_file):
        scena = _Scena(avatar_autore=_png())

        await _lancia(cog, comando, scena, **opzioni)

        assert scena.ordine == ["defer", "download", "followup"]
        assert scena.file_inviato.filename == nome_file
        assert Image.open(scena.file_inviato.fp).size == (50, 50)

    @pytest.mark.parametrize("comando,opzioni,nome_file", COMANDI)
    async def test_anche_con_un_allegato_il_defer_viene_prima_del_download(
        self, cog, comando, opzioni, nome_file
    ):
        scena = _Scena()

        await _lancia(cog, comando, scena, image=scena.allegato(_png()), **opzioni)

        assert scena.ordine == ["defer", "download", "followup"]


class TestSceltaDellImmagine:
    async def test_senza_allegato_usa_l_avatar_dell_autore(self, cog):
        scena = _Scena(avatar_autore=_png())

        await _lancia(cog, "grayscale", scena)

        assert scena.file_inviato.filename == "grayscale.png"

    async def test_con_allegato_usa_l_allegato_non_l_avatar(self, cog):
        # Avatar non valido apposta: se venisse usato, non ci sarebbe file.
        scena = _Scena(avatar_autore=NON_UN_IMMAGINE)

        await _lancia(cog, "grayscale", scena, image=scena.allegato(_png()))

        assert scena.file_inviato.filename == "grayscale.png"
        scena.interazione.user.display_avatar.read.assert_not_awaited()

    async def test_con_utente_menzionato_usa_il_suo_avatar(self, cog):
        scena = _Scena(avatar_autore=NON_UN_IMMAGINE)
        altro = scena.membro(_png())

        await _lancia(cog, "grayscale", scena, utente=altro)

        assert scena.file_inviato.filename == "grayscale.png"
        altro.display_avatar.read.assert_awaited_once()


class TestAllegatoRifiutatoSenzaScaricarlo:
    async def test_allegato_non_immagine(self, cog):
        scena = _Scena()
        allegato = scena.allegato(b"pdf-finto", content_type="application/pdf")

        await _lancia(cog, "grayscale", scena, image=allegato)

        assert scena.ordine == ["risposta"]
        assert "non è un'immagine" in scena.testo_risposta
        assert scena.risposta_effimera

    async def test_allegato_oltre_8_mb(self, cog):
        scena = _Scena()
        allegato = scena.allegato(_png(), size=MAX_IMAGE_BYTES + 1)

        await _lancia(cog, "blur", scena, image=allegato)

        assert scena.ordine == ["risposta"], "non deve né scaricare né fare defer"
        assert "troppo grande" in scena.testo_risposta
        assert "8 MB" in scena.testo_risposta
        assert scena.risposta_effimera

    async def test_allegato_di_8_mb_esatti_viene_accettato(self, cog):
        scena = _Scena()
        allegato = scena.allegato(_png(), size=MAX_IMAGE_BYTES)

        await _lancia(cog, "invert", scena, image=allegato)

        assert scena.ordine == ["defer", "download", "followup"]

    def test_il_limite_e_8_mb(self):
        assert MAX_IMAGE_BYTES == 8 * 1024 * 1024


class TestErroriDopoIlDefer:
    async def test_immagine_non_elaborabile_avvisa_con_followup(self, cog):
        scena = _Scena(avatar_autore=NON_UN_IMMAGINE)

        await _lancia(cog, "pixelate", scena)

        assert scena.ordine == ["defer", "download", "followup"]
        assert "Non sono riuscito a elaborare" in scena.testo_followup

    async def test_download_fallito_avvisa_con_followup(self, cog):
        scena = _Scena()
        risposta_http = create_autospec(aiohttp.ClientResponse, instance=True)
        risposta_http.status = 503
        risposta_http.reason = "Service Unavailable"
        allegato = scena.allegato(_png())
        allegato.read.side_effect = discord.HTTPException(risposta_http, "errore del CDN")

        await _lancia(cog, "grayscale", scena, image=allegato)

        assert scena.ordine == ["defer", "followup"]
        assert "Non sono riuscito a scaricare" in scena.testo_followup


class TestRifiutiImmediati:
    async def test_modulo_disattivato(self, cog):
        await db.set_module_active_for_guild(ID_SERVER, MODULE_FUN, False)
        scena = _Scena(avatar_autore=_png())

        await _lancia(cog, "grayscale", scena)

        assert scena.ordine == ["risposta"]
        assert "non è attivo" in scena.testo_risposta

    async def test_fuori_da_un_server(self, cog):
        scena = _Scena(avatar_autore=_png())
        scena.interazione.guild = None

        await _lancia(cog, "grayscale", scena)

        assert scena.ordine == ["risposta"]
        assert "solo dentro un server" in scena.testo_risposta

    async def test_meme_senza_testo(self, cog):
        scena = _Scena(avatar_autore=_png())

        await _lancia(cog, "meme", scena, top_text="", bottom_text="")

        assert scena.ordine == ["risposta"]
        assert "almeno un testo" in scena.testo_risposta
