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


@pytest.mark.parametrize("lungo", ["x" * 200, "😀" * 40 + "y" * 100, "W" * 32])
def test_il_testo_lungo_non_esce_dal_margine_destro(lungo):
    """Il nome si accorcia con «…» per stare nella larghezza: la fascia di margine a destra resta pulita."""
    box = (LARGHEZZA - 45, 150, LARGHEZZA, 250)
    corto = _apri(render_welcome_image(_dati(nome="Mario"), None, None)).crop(box)
    lunga = _apri(render_welcome_image(_dati(nome=lungo, titolo="T" * 40), None, None)).crop(box)
    assert lunga.tobytes() == corto.tobytes()


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
        self.repo.set_welcome_image_extra = AsyncMock()
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
async def test_senza_permesso_di_allegare_parte_il_solo_testo(monkeypatch):
    s = _Scena(monkeypatch)
    s.canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, attach_files=False))
    disegna = MagicMock()
    monkeypatch.setattr(modulo, "render_welcome_image", disegna)
    await s.cog.on_member_join(s.membro)
    s.canale.send.assert_awaited_once()
    assert "file" not in s.canale.send.await_args.kwargs
    disegna.assert_not_called()  # niente lavoro Pillow sprecato


@pytest.mark.asyncio
async def test_se_l_invio_con_il_file_fallisce_il_testo_parte_lo_stesso(monkeypatch):
    s = _Scena(monkeypatch)
    s.canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True, attach_files=True))

    async def invio(testo, **kw):
        if "file" in kw:
            raise discord.Forbidden(MagicMock(status=403, reason="x"), "Missing Permissions")

    s.canale.send = AsyncMock(side_effect=invio)
    await s.cog.on_member_join(s.membro)
    assert s.canale.send.await_count == 2
    assert "file" in s.canale.send.await_args_list[0].kwargs
    assert "file" not in s.canale.send.await_args_list[1].kwargs


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
    cmd = comando_nel_gruppo("admin-benvenuto", "immagine")
    opzioni = {o["name"]: o for o in cmd.to_dict(bot.tree)["options"]}
    assert len(opzioni["modello"]["choices"]) == len(MODELLI)
    assert opzioni["titolo"]["max_length"] <= 100


# ------------------------------------------------- RUO-004, RUO-007, RUO-008, RUO-010 (#123)
def _con(**campi):
    base = dict(nome="Mario", numero=5)
    return render_welcome_image(DatiBenvenuto(**base, **campi), None, _png_sfondo())


def _png_sfondo():
    buf = io.BytesIO()
    Image.new("RGB", (800, 300), (230, 230, 40)).save(buf, "PNG")
    return buf.getvalue()


def test_RUO_004_opacita_dello_sfondo_cambia_la_luminosita():


    # RUO-004
    scuro = Image.open(io.BytesIO(_con(opacita=10))).convert("L").resize((1, 1)).getpixel((0, 0))
    chiaro = Image.open(io.BytesIO(_con(opacita=100))).convert("L").resize((1, 1)).getpixel((0, 0))
    assert chiaro > scuro


def test_RUO_007_allineamento_e_colore_del_nome():


    # RUO-007
    assert _con(allineamento="sinistra") != _con(allineamento="centro")
    assert _con(allineamento="centro") != _con(allineamento="destra")
    assert _con(colore_nome="#FF0000") != _con(colore_nome="#00FF00")
    assert _con(allineamento="inventato")  # un valore strano non rompe il disegno


def test_RUO_008_testo_libero_sull_immagine():


    # RUO-008
    assert _con(testo="Leggi le regole") != _con(testo="")
    assert _con(testo="x" * 500)  # troppo lungo: si taglia, non si rompe


def test_RUO_010_ordine_tra_immagine_e_testo():


    # RUO-010
    from core.welcome_image import ORDINI

    assert ORDINI == ("insieme", "immagine_prima", "solo_immagine")


@pytest.mark.asyncio
async def test_RUO_004_007_008_010_impostazioni_in_piu_salvate_e_riletta(repo):
    # RUO-004, RUO-007, RUO-008, RUO-010
    config = await repo.get_config(1)
    assert (config.welcome_image_opacity, config.welcome_image_order, config.welcome_image_align) == (65, "insieme", "sinistra")
    await repo.set_welcome_image_extra(1, 20, "Leggi {server}", "solo_immagine", "centro", "#FFD700")
    config = await repo.get_config(1)
    assert (config.welcome_image_opacity, config.welcome_image_text, config.welcome_image_order,
            config.welcome_image_align, config.welcome_image_name_color) == (20, "Leggi {server}", "solo_immagine", "centro", "#FFD700")


@pytest.mark.asyncio
async def test_RUO_010_immagine_prima_del_testo_sono_due_messaggi(monkeypatch):
    # RUO-010
    import dataclasses

    s = _Scena(monkeypatch)
    s.repo.get_config.return_value = dataclasses.replace(s.repo.get_config.return_value, welcome_image_order="immagine_prima")
    await s.cog.on_member_join(s.membro)
    prima, seconda = s.canale.send.await_args_list
    assert isinstance(prima.kwargs["file"], discord.File) and not prima.args
    assert seconda.args and "file" not in seconda.kwargs


@pytest.mark.asyncio
async def test_RUO_010_solo_immagine_non_manda_il_testo(monkeypatch):
    # RUO-010
    import dataclasses

    s = _Scena(monkeypatch)
    s.repo.get_config.return_value = dataclasses.replace(s.repo.get_config.return_value, welcome_image_order="solo_immagine")
    await s.cog.on_member_join(s.membro)
    s.canale.send.assert_awaited_once()
    assert not s.canale.send.await_args.args and isinstance(s.canale.send.await_args.kwargs["file"], discord.File)


@pytest.mark.asyncio
async def test_RUO_008_il_testo_libero_usa_i_segnaposto_senza_menzioni(monkeypatch):
    # RUO-008
    import dataclasses

    s = _Scena(monkeypatch)
    s.repo.get_config.return_value = dataclasses.replace(
        s.repo.get_config.return_value, welcome_image_text="Ciao {user} su {server}"
    )
    visto = {}

    def finto(dati, avatar, sfondo):
        visto["testo"] = dati.testo
        return b"x"

    monkeypatch.setattr(modulo, "render_welcome_image", finto)
    await s.cog.on_member_join(s.membro)
    assert visto["testo"].startswith("Ciao Mario su ") and "<@" not in visto["testo"]


@pytest.mark.asyncio
async def test_RUO_004_007_008_010_il_comando_salva_solo_cio_che_si_indica(monkeypatch):
    # RUO-004, RUO-007, RUO-008, RUO-010
    s = _Scena(monkeypatch)
    i = fake_interaction(guild=s.server, user=s.membro)
    await s.cog.immagine.callback(
        s.cog, i, True, opacita=30, testo="Leggi le regole", ordine="solo_immagine", allineamento="centro",
        colore_nome="#FFD700",
    )
    s.repo.set_welcome_image_extra.assert_awaited_once_with(
        s.server.id, 30, "Leggi le regole", "solo_immagine", "centro", "#FFD700"
    )
    s.repo.set_welcome_image_extra.reset_mock()
    await s.cog.immagine.callback(s.cog, i, True, colore_nome="rosso")  # colore non valido
    s.repo.set_welcome_image_extra.assert_not_awaited()
    await s.cog.immagine.callback(s.cog, i, True, testo="togli", colore_nome="predefinito")
    assert s.repo.set_welcome_image_extra.await_args.args[2] == "" and s.repo.set_welcome_image_extra.await_args.args[5] == ""


# ---- RUO-005 (D121): sfondo trasparente e misure a scelta ----
def _dati5(**kw):
    return DatiBenvenuto(nome="Anna", numero=7, **kw)


def test_ruo005_le_misure_scelte_sono_quelle_del_png():
    png = render_welcome_image(_dati5(larghezza=600, altezza=300), None, None)
    assert Image.open(io.BytesIO(png)).size == (600, 300)


def test_ruo005_senza_misure_resta_1024_per_400():
    assert Image.open(io.BytesIO(render_welcome_image(_dati5(), None, None))).size == (LARGHEZZA, ALTEZZA)


def test_ruo005_le_misure_fuori_dai_limiti_si_riportano_dentro():
    png = render_welcome_image(_dati5(larghezza=99999, altezza=1), None, None)
    assert Image.open(io.BytesIO(png)).size == (2048, 64)


def test_ruo005_trasparente_ha_gli_angoli_vuoti_e_il_testo_pieno():
    img = Image.open(io.BytesIO(render_welcome_image(_dati5(trasparente=True, larghezza=800, altezza=400), None, None))).convert("RGBA")
    assert img.getpixel((0, 0))[3] == 0 and img.getpixel((799, 399))[3] == 0
    assert any(p[3] > 200 for p in img.getdata())  # l'avatar e il testo ci sono


def test_ruo005_non_trasparente_e_tutto_opaco():
    img = Image.open(io.BytesIO(render_welcome_image(_dati5(larghezza=900, altezza=300), None, None))).convert("RGBA")
    assert img.getpixel((0, 0))[3] == 255 and img.getpixel((899, 299))[3] == 255


async def test_ruo005_le_misure_si_salvano_e_si_leggono(clean_db):
    repo = GreetingsRepository(lambda: clean_db)
    assert (await repo.get_config(880001)).welcome_image_width == 1024
    await repo.set_welcome_image_misure(880001, 800, 200, True)
    c = await repo.get_config(880001)
    assert (c.welcome_image_width, c.welcome_image_height, c.welcome_image_transparent) == (800, 200, True)
