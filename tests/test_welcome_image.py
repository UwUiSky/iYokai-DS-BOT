"""
tests/test_welcome_image.py
===========================
NF-11 (#82): immagine di benvenuto con avatar, nome e numero del membro; modelli
pronti e sfondo caricabile (regole di core/safe_image.py: 16 megapixel, file sotto 3 MB).
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

import cogs.utility.greetings as modulo
from cogs.utility.greetings import GreetingsCog
from core.repositories.greetings_repo import GreetingsConfig, GreetingsRepository
from core.safe_image import ImmagineTroppoGrande
from core.welcome_image import (
    ALTEZZA,
    LARGHEZZA,
    MAX_SFONDO_BYTE,
    MODELLI,
    DatiBenvenuto,
    prepara_sfondo,
    render_welcome_image,
)
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel
from tests.support.percorsi import comando_nel_gruppo


def _png(w=64, h=64, colore=(200, 30, 30), formato="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colore).save(buf, format=formato)
    return buf.getvalue()


def _dati(**kw):
    base = dict(nome="Mario", numero=1234, titolo="Benvenuto", modello="scuro", forma="tondo", colore_testo="#FFFFFF")
    base.update(kw)
    return DatiBenvenuto(**base)


def _apri(png):
    img = Image.open(io.BytesIO(png))
    img.load()
    return img


# ---------------------------------------------------------------- disegno
@pytest.mark.parametrize("modello", sorted(MODELLI))
@pytest.mark.parametrize("forma", ["tondo", "quadrato"])
def test_ogni_modello_e_forma_da_un_png_della_misura_giusta(modello, forma):
    img = _apri(render_welcome_image(_dati(modello=modello, forma=forma), _png(), None))
    assert img.format == "PNG" and img.size == (LARGHEZZA, ALTEZZA)


def test_i_modelli_pronti_sono_da_tre_a_quattro():
    assert 3 <= len(MODELLI) <= 4


def test_senza_avatar_non_solleva():
    assert _apri(render_welcome_image(_dati(), None, None)).size == (LARGHEZZA, ALTEZZA)


def test_avatar_rotto_non_solleva():
    assert _apri(render_welcome_image(_dati(), b"non e un'immagine", None)).size == (LARGHEZZA, ALTEZZA)


def test_nome_lunghissimo_ed_emoji_non_rompono_il_disegno():
    dati = _dati(nome="😀" * 40 + "x" * 200, titolo="T" * 300)
    assert _apri(render_welcome_image(dati, None, None)).size == (LARGHEZZA, ALTEZZA)


def test_sfondo_personalizzato_cambia_l_immagine():
    senza = render_welcome_image(_dati(), None, None)
    sfondo = prepara_sfondo(_png(300, 120, (10, 200, 10)))
    con = render_welcome_image(_dati(), None, sfondo)
    assert senza != con


def test_sfondo_rotto_si_ignora_senza_errori():
    assert _apri(render_welcome_image(_dati(), None, b"xx")).size == (LARGHEZZA, ALTEZZA)


def test_colore_del_testo_non_valido_usa_il_bianco():
    assert _apri(render_welcome_image(_dati(colore_testo="rosso"), None, None)).size == (LARGHEZZA, ALTEZZA)


# ---------------------------------------------------------------- sfondo
def test_prepara_sfondo_porta_alla_misura_e_sotto_il_tetto():
    pronto = prepara_sfondo(_png(1500, 900))
    img = _apri(pronto)
    assert img.size == (LARGHEZZA, ALTEZZA)
    assert len(pronto) <= MAX_SFONDO_BYTE


def test_prepara_sfondo_rifiuta_oltre_16_megapixel():
    with pytest.raises(ImmagineTroppoGrande):
        prepara_sfondo(_png(5000, 4000, formato="PNG"))


def test_prepara_sfondo_rifiuta_un_file_non_immagine():
    with pytest.raises(Exception):
        prepara_sfondo(b"%PDF-1.4 non immagine")


# --------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return GreetingsRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_impostazioni_dell_immagine(repo):
    config = await repo.get_config(1)
    assert config.welcome_image_enabled is False and config.welcome_image_template == "scuro"
    await repo.set_welcome_image(1, enabled=True, template="viola", shape="quadrato", color="#112233", title="Ciao")
    config = await repo.get_config(1)
    assert (config.welcome_image_enabled, config.welcome_image_template, config.welcome_image_shape,
            config.welcome_image_color, config.welcome_image_title) == (True, "viola", "quadrato", "#112233", "Ciao")


@pytest.mark.asyncio
async def test_impostare_l_immagine_non_cancella_il_messaggio(repo):
    await repo.set_welcome(1, enabled=True, channel_id=9, message="Ciao {user}", dm=False)
    await repo.set_welcome_image(1, enabled=True, template="scuro", shape="tondo", color="#FFFFFF", title="B")
    config = await repo.get_config(1)
    assert config.welcome_message == "Ciao {user}" and config.welcome_enabled


@pytest.mark.asyncio
async def test_sfondo_salvato_letto_e_tolto(repo):
    assert await repo.get_welcome_background(1) is None
    await repo.set_welcome_background(1, b"abc")
    assert await repo.get_welcome_background(1) == b"abc"
    assert (await repo.get_config(1)).welcome_image_has_background is True
    await repo.clear_welcome_background(1)
    assert await repo.get_welcome_background(1) is None
    assert (await repo.get_config(1)).welcome_image_has_background is False


# -------------------------------------------------------------------- cog
class _Scena:
    def __init__(self, monkeypatch, *, immagine=True, raid=False):
        self.cog = GreetingsCog(MagicMock())
        self.canale = fake_text_channel(55)
        self.canale.send = AsyncMock()
        self.server = fake_guild()
        self.server.member_count = 1234
        self.server.get_channel = lambda cid: self.canale
        config = GreetingsConfig(
            guild_id=666, welcome_enabled=True, welcome_channel_id=55, welcome_message="Ciao {user}", welcome_dm=False,
            goodbye_enabled=False, goodbye_channel_id=None, goodbye_message="", boost_enabled=False,
            boost_channel_id=None, boost_message="", welcome_image_enabled=immagine,
        )
        self.repo = MagicMock()
        self.repo.get_config = AsyncMock(return_value=config)
        self.repo.get_welcome_background = AsyncMock(return_value=None)
        self.repo.set_welcome_image = AsyncMock()
        self.repo.set_welcome_background = AsyncMock()
        self.repo.clear_welcome_background = AsyncMock()
        monkeypatch.setattr(modulo, "greetings_repo", self.repo)
        db_finto = MagicMock()
        db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db_finto)
        monkeypatch.setattr(modulo, "raid_in_corso", lambda gid: raid)
        self.membro = fake_member(5, "mario")
        self.membro.guild = self.server
        self.membro.display_name = "Mario"
        self.membro.display_avatar = SimpleNamespace(replace=lambda **kw: SimpleNamespace(read=AsyncMock(return_value=_png())))


@pytest.mark.asyncio
async def test_ingresso_manda_testo_e_immagine(monkeypatch):
    s = _Scena(monkeypatch)
    await s.cog.on_member_join(s.membro)
    kw = s.canale.send.await_args.kwargs
    assert isinstance(kw["file"], discord.File)
    assert kw["file"].filename == "benvenuto.png"


@pytest.mark.asyncio
async def test_immagine_spenta_nessun_file(monkeypatch):
    s = _Scena(monkeypatch, immagine=False)
    await s.cog.on_member_join(s.membro)
    assert "file" not in s.canale.send.await_args.kwargs


@pytest.mark.asyncio
async def test_durante_un_raid_solo_testo(monkeypatch):
    s = _Scena(monkeypatch, raid=True)
    await s.cog.on_member_join(s.membro)
    assert "file" not in s.canale.send.await_args.kwargs
    s.canale.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_errore_nel_disegno_non_blocca_il_testo(monkeypatch):
    s = _Scena(monkeypatch)
    monkeypatch.setattr(modulo, "render_welcome_image", MagicMock(side_effect=RuntimeError("boom")))
    await s.cog.on_member_join(s.membro)
    s.canale.send.assert_awaited_once()
    assert "file" not in s.canale.send.await_args.kwargs


def _allegato(size=1000, content_type="image/png", dati=None):
    a = MagicMock(spec=discord.Attachment)
    a.size = size
    a.content_type = content_type
    a.filename = "sfondo.png"
    a.read = AsyncMock(return_value=dati if dati is not None else _png(300, 100))
    return a


@pytest.mark.asyncio
async def test_comando_sfondo_troppo_grande_non_viene_scaricato(monkeypatch):
    s = _Scena(monkeypatch)
    a = _allegato(size=MAX_SFONDO_BYTE + 1)
    i = fake_interaction(guild=s.server)
    await s.cog.immagine.callback(s.cog, i, True, "scuro", a, "tondo", None, None)
    a.read.assert_not_awaited()
    s.repo.set_welcome_background.assert_not_awaited()
    assert "3 MB" in i.response.send_message.await_args.args[0] or "3 MiB" in i.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_comando_sfondo_non_immagine_rifiutato(monkeypatch):
    s = _Scena(monkeypatch)
    a = _allegato(content_type="application/pdf")
    i = fake_interaction(guild=s.server)
    await s.cog.immagine.callback(s.cog, i, True, "scuro", a, "tondo", None, None)
    s.repo.set_welcome_background.assert_not_awaited()


@pytest.mark.asyncio
async def test_comando_ok_salva_sfondo_e_impostazioni(monkeypatch):
    s = _Scena(monkeypatch)
    i = fake_interaction(guild=s.server)
    await s.cog.immagine.callback(s.cog, i, True, "viola", _allegato(), "quadrato", "#ff8800", "Ciao!")
    s.repo.set_welcome_background.assert_awaited_once()
    kw = s.repo.set_welcome_image.await_args.kwargs
    assert kw["template"] == "viola" and kw["shape"] == "quadrato" and kw["color"] == "#FF8800"


@pytest.mark.asyncio
async def test_comando_colore_non_valido(monkeypatch):
    s = _Scena(monkeypatch)
    i = fake_interaction(guild=s.server)
    await s.cog.immagine.callback(s.cog, i, True, "scuro", None, "tondo", "rosso", None)
    s.repo.set_welcome_image.assert_not_awaited()


@pytest.mark.asyncio
async def test_il_comando_sta_sotto_gestione_benvenuto():
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    cmd = comando_nel_gruppo("gestione", "benvenuto immagine")
    opzioni = {o["name"]: o for o in cmd.to_dict(bot.tree)["options"]}
    assert len(opzioni["modello"]["choices"]) == len(MODELLI)
    assert opzioni["titolo"]["max_length"] <= 100
