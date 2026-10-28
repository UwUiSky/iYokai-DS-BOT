"""
tests/test_moneta_server_immagine.py
====================================
D38: nome della moneta solo testo, immagine propria (ridotta e piccola),
moneta di iYokai di base, stessa forma (miniatura) in tutti gli embed.
"""

import io

import discord
import pytest
from PIL import Image

from core.leveling_logic import nome_moneta_valido
from core.moneta_server import (
    LATO_MONETA, MAX_BYTE_MONETA, NOME_FILE_MONETA, MonetaNonValida,
    aggiungi_moneta, moneta_base, prepara_moneta,
)
from core.repositories.leveling_settings_repo import LevelingSettingsRepository


def _png(lato=900, colore=(200, 30, 30, 255)):
    buf = io.BytesIO()
    Image.new("RGBA", (lato, lato // 2), colore).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("nome", ["gemme 💎", "💎", "oro:gold:", "<:x:123>", "@everyone", "☀️ sole"])
def test_il_nome_rifiuta_emoji_e_menzioni(nome):
    with pytest.raises(ValueError):
        nome_moneta_valido(nome)


def test_il_nome_di_testo_passa():
    assert nome_moneta_valido("  gemme   rosse ") == "gemme rosse"


def test_prepara_moneta_riduce_e_resta_piccola():
    png = prepara_moneta(_png())
    img = Image.open(io.BytesIO(png))
    assert img.size == (LATO_MONETA, LATO_MONETA)
    assert img.format == "PNG"
    assert len(png) <= MAX_BYTE_MONETA


def test_prepara_moneta_rifiuta_un_file_che_non_e_un_immagine():
    with pytest.raises(MonetaNonValida):
        prepara_moneta(b"non sono un'immagine")


def test_la_moneta_di_iyokai_e_un_png_valido():
    assert Image.open(io.BytesIO(moneta_base())).format == "PNG"


def test_aggiungi_moneta_usa_la_miniatura_e_il_file_giusto():
    embed = discord.Embed()
    file = aggiungi_moneta(embed, None)
    assert embed.thumbnail.url == f"attachment://{NOME_FILE_MONETA}"
    assert file.filename == NOME_FILE_MONETA
    personale = prepara_moneta(_png())
    assert aggiungi_moneta(discord.Embed(), personale).fp.read() == personale


@pytest.fixture
def repo(clean_db):
    return LevelingSettingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_immagine_salvata_sostituita_e_tolta(repo):
    assert await repo.get_immagine_moneta(4100001) is None
    await repo.set_immagine_moneta(4100001, b"uno")
    await repo.set_immagine_moneta(4100001, b"due")
    assert await repo.get_immagine_moneta(4100001) == b"due"
    await repo.set_immagine_moneta(4100001, None)
    assert await repo.get_immagine_moneta(4100001) is None


@pytest.mark.asyncio
async def test_il_database_rifiuta_un_immagine_troppo_grande(repo):
    with pytest.raises(Exception):
        await repo.set_immagine_moneta(4100002, b"x" * (MAX_BYTE_MONETA + 1))
