"""
tests/test_spam_trap_thumbnails.py
======================================
Test end-to-end di SpamTrapCog._build_thumbnails: allegati Discord
finti (espongono solo .filename/.content_type/.size/.read()), ma
byte immagine VERI generati da Pillow — verifica che l'intero
percorso (filtro immagine → limite dimensione → download →
asyncio.to_thread → generate_thumbnail → data URI) funzioni insieme,
non solo i pezzi isolati già testati altrove.
"""

import io

import discord
import pytest
from discord.ext import commands
from PIL import Image

from cogs.security.spam_trap import SpamTrapCog
from core.image_thumbnail_logic import MAX_SOURCE_IMAGE_BYTES


def _real_image_bytes(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FakeAttachment:
    def __init__(
        self, filename: str, content_type: str | None, size: int, content: bytes
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self.size = size
        self._content = content

    async def read(self) -> bytes:
        return self._content


@pytest.fixture
def cog():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    return SpamTrapCog(bot)


@pytest.mark.asyncio
async def test_build_thumbnails_con_immagine_vera_produce_data_uri(cog):
    contenuto = _real_image_bytes()
    allegato = _FakeAttachment("foto.png", "image/png", len(contenuto), contenuto)

    risultato = await cog._build_thumbnails([allegato])

    assert len(risultato) == 1
    assert risultato[0].startswith("data:image/webp;base64,")


@pytest.mark.asyncio
async def test_build_thumbnails_allegato_non_immagine_ignorato(cog):
    allegato = _FakeAttachment("documento.pdf", "application/pdf", 1000, b"non conta")

    risultato = await cog._build_thumbnails([allegato])

    assert risultato == []


@pytest.mark.asyncio
async def test_build_thumbnails_allegato_troppo_grande_ignorato(cog):
    contenuto = _real_image_bytes()
    allegato = _FakeAttachment(
        "gigante.png", "image/png", MAX_SOURCE_IMAGE_BYTES + 1, contenuto
    )

    risultato = await cog._build_thumbnails([allegato])

    assert risultato == []


@pytest.mark.asyncio
async def test_build_thumbnails_piu_allegati_immagine_insieme(cog):
    contenuto1 = _real_image_bytes(50, 50)
    contenuto2 = _real_image_bytes(80, 80)
    allegati = [
        _FakeAttachment("a.png", "image/png", len(contenuto1), contenuto1),
        _FakeAttachment("b.png", "image/png", len(contenuto2), contenuto2),
    ]

    risultato = await cog._build_thumbnails(allegati)

    assert len(risultato) == 2


@pytest.mark.asyncio
async def test_build_thumbnails_immagine_corrotta_non_produce_data_uri(cog):
    # content_type dichiara "immagine" ma i byte non lo sono davvero
    # (es. upload danneggiato): non deve sollevare, solo non produrre
    # nulla per quell'allegato.
    allegato = _FakeAttachment("corrotta.png", "image/png", 100, b"non un'immagine vera")

    risultato = await cog._build_thumbnails([allegato])

    assert risultato == []


@pytest.mark.asyncio
async def test_build_thumbnails_lista_vuota(cog):
    risultato = await cog._build_thumbnails([])
    assert risultato == []


@pytest.mark.asyncio
async def test_build_thumbnails_mix_di_immagini_e_non_immagini(cog):
    contenuto = _real_image_bytes()
    allegati = [
        _FakeAttachment("foto.png", "image/png", len(contenuto), contenuto),
        _FakeAttachment("documento.pdf", "application/pdf", 500, b"pdf finto"),
    ]

    risultato = await cog._build_thumbnails(allegati)

    # Solo l'immagine produce una thumbnail, il PDF viene ignorato
    # silenziosamente — non un errore, solo "non applicabile".
    assert len(risultato) == 1


class _FakeAvatarAsset:
    def __init__(self, content: bytes, fail: bool = False) -> None:
        self._content = content
        self._fail = fail

    async def read(self) -> bytes:
        if self._fail:
            raise discord.HTTPException(response=_FakeHTTPResponse(), message="errore avatar")
        return self._content


class _FakeHTTPResponse:
    status = 500
    reason = "Internal Server Error"


class _FakeUserWithAvatar:
    def __init__(self, avatar_content: bytes, fail: bool = False) -> None:
        self.display_avatar = _FakeAvatarAsset(avatar_content, fail=fail)


@pytest.mark.asyncio
async def test_build_author_avatar_con_avatar_vero_produce_data_uri(cog):
    contenuto = _real_image_bytes()
    utente = _FakeUserWithAvatar(contenuto)

    risultato = await cog._build_author_avatar(utente)

    assert risultato is not None
    assert risultato.startswith("data:image/webp;base64,")


@pytest.mark.asyncio
async def test_build_author_avatar_download_fallito_restituisce_none(cog):
    utente = _FakeUserWithAvatar(b"", fail=True)

    risultato = await cog._build_author_avatar(utente)

    assert risultato is None


@pytest.mark.asyncio
async def test_build_author_avatar_contenuto_corrotto_restituisce_none(cog):
    utente = _FakeUserWithAvatar(b"non e' un'immagine")

    risultato = await cog._build_author_avatar(utente)

    assert risultato is None
