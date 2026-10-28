"""
tests/test_greetings_uscite.py
==============================
D37: messaggi di ban e di addio. Le quattro modalità, l'ordine «prima il martello, poi l'addio»,
il raid, i testi di base, la grafica (link https o file) e le finestre di scelta.
"""

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from PIL import Image

import cogs.utility.greetings as modulo
from core import greetings_uscite_logic as uscite
from core.database import Database
from core.greetings_logic import DEFAULT_GOODBYE_TEMPLATE
from core.repositories.greetings_repo import GreetingsConfig, GreetingsRepository
from tests.support.discord_fakes import fake_guild, fake_member, fake_text_channel


@pytest.fixture(autouse=True)
def _stati_puliti():
    """Lo stato dei ban è globale: un test che banna senza uscita non deve passarlo al successivo."""
    uscite._stati.clear()
    yield
    uscite._stati.clear()


def _png(formato="PNG", dim=(8, 8)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", dim, "red").save(buf, format=formato)
    return buf.getvalue()


def _config(**extra) -> GreetingsConfig:
    base = dict(
        guild_id=666, welcome_enabled=False, welcome_channel_id=None, welcome_message="", welcome_dm=False,
        goodbye_enabled=True, goodbye_channel_id=5151, goodbye_message=DEFAULT_GOODBYE_TEMPLATE,
        boost_enabled=False, boost_channel_id=None, boost_message="",
    )
    return GreetingsConfig(**{**base, **extra})


def _scenario(monkeypatch, grafiche=None, **extra):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    monkeypatch.setattr(modulo, "db", db_finto)
    repo = create_autospec(GreetingsRepository, instance=True)
    config = _config(**extra)
    repo.get_config.return_value = config
    repo.get_grafica.side_effect = lambda _g, tipo: (grafiche or {}).get(tipo)
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    monkeypatch.setattr(modulo, "raid_in_corso", lambda _g: False)
    canale = fake_text_channel(channel_id=5151)
    server = fake_guild()
    server.member_count = 10
    server.get_channel.return_value = canale
    membro = fake_member(user_id=42, bot=False)
    membro.guild = server
    membro.name = "Mario"
    membro.display_name = "Mario"
    utente = MagicMock(spec=discord.User)
    utente.id, utente.name, utente.bot = 42, "Mario", False
    utente.display_name, utente.mention = "Mario", "<@42>"
    monkeypatch.setattr(uscite, "ATTESA_BAN", 0.05)
    return canale, membro, utente, repo


async def _ban_e_uscita(membro, utente, *, prima_ban=True):
    cog = modulo.GreetingsCog(bot=None)
    if prima_ban:
        await cog.on_member_ban(membro.guild, utente)
        await cog.on_member_remove(membro)
    else:
        remove = asyncio.create_task(cog.on_member_remove(membro))
        await asyncio.sleep(0.01)
        await cog.on_member_ban(membro.guild, utente)
        await remove


def _testi(canale):
    return [c.args[0] for c in canale.send.await_args_list]


# ------------------------------------------------------------ le quattro modalità
async def test_di_base_escono_tutti_e_due_prima_il_martello(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch)
    await _ban_e_uscita(membro, utente, prima_ban=False)  # l'uscita arriva prima del ban
    testi = _testi(canale)
    assert len(testi) == 2
    assert "martello" in testi[0] and "Mario" in testi[0]
    assert "è stato bello vederti" in testi[1] and "Mario" in testi[1]


async def test_ordine_giusto_anche_se_il_ban_arriva_prima(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch)
    await _ban_e_uscita(membro, utente, prima_ban=True)
    testi = _testi(canale)
    assert "martello" in testi[0] and "bello vederti" in testi[1]


async def test_solo_ban(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch, leave_mode="solo_ban")
    await _ban_e_uscita(membro, utente)
    assert len(_testi(canale)) == 1 and "martello" in _testi(canale)[0]


async def test_solo_addio(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch, leave_mode="solo_addio")
    await _ban_e_uscita(membro, utente)
    assert len(_testi(canale)) == 1 and "bello vederti" in _testi(canale)[0]


async def test_nessuno(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch, leave_mode="nessuno")
    await _ban_e_uscita(membro, utente)
    canale.send.assert_not_awaited()


async def test_uscita_normale_senza_ban_manda_solo_l_addio(monkeypatch):
    canale, membro, _, _ = _scenario(monkeypatch)
    await modulo.GreetingsCog(bot=None).on_member_remove(membro)
    assert len(_testi(canale)) == 1 and "bello vederti" in _testi(canale)[0]


async def test_testo_di_ban_dell_admin_vince_su_quello_di_base(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch, ban_message="Addio {username}!", leave_mode="solo_ban")
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    assert _testi(canale) == ["Addio Mario!"]


async def test_canale_dell_addio_spento_niente(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch, goodbye_enabled=False)
    await _ban_e_uscita(membro, utente)
    canale.send.assert_not_awaited()


async def test_durante_un_raid_tutto_spento_per_il_bannato(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch)
    monkeypatch.setattr(modulo, "raid_in_corso", lambda _g: True)
    await _ban_e_uscita(membro, utente, prima_ban=False)
    canale.send.assert_not_awaited()


async def test_bot_ignorati(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch)
    membro.bot = True
    utente.bot = True
    await _ban_e_uscita(membro, utente)
    canale.send.assert_not_awaited()


# ------------------------------------------------------------ la grafica
async def test_grafica_con_link_va_in_un_embed(monkeypatch):
    graf = {"ban": ("https://example.com/martello.gif", None, None)}
    canale, membro, utente, _ = _scenario(monkeypatch, grafiche=graf, leave_mode="solo_ban")
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    embed = canale.send.await_args.kwargs["embed"]
    assert embed.image.url == "https://example.com/martello.gif"


async def test_grafica_caricata_va_come_allegato(monkeypatch):
    graf = {"addio": (None, _png("GIF"), "addio.gif")}
    canale, membro, _, _ = _scenario(monkeypatch, grafiche=graf, leave_mode="solo_addio")
    await modulo.GreetingsCog(bot=None).on_member_remove(membro)
    assert canale.send.await_args.kwargs["file"].filename == "addio.gif"


async def test_grafica_rifiutata_da_discord_il_testo_parte_lo_stesso(monkeypatch):
    graf = {"ban": ("https://example.com/x.gif", None, None)}
    canale, membro, utente, _ = _scenario(monkeypatch, grafiche=graf, leave_mode="solo_ban")
    canale.send.side_effect = [discord.HTTPException(MagicMock(status=400), "no"), None]
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    assert canale.send.await_count == 2
    assert "embed" not in canale.send.await_args.kwargs


async def test_i_ruoli_citati_non_fanno_ping_se_il_server_non_li_vuole(monkeypatch):
    canale, membro, utente, _ = _scenario(monkeypatch, leave_mode="solo_ban", ban_message="@everyone {user}")
    await modulo.GreetingsCog(bot=None).on_member_ban(membro.guild, utente)
    menzioni = canale.send.await_args.kwargs["allowed_mentions"]
    assert menzioni.everyone is False


# ------------------------------------------------------------ logica
def test_modi():
    assert [uscite.invia_ban(m) for m in uscite.MODI] == [True, True, False, False]
    assert [uscite.invia_addio(m) for m in uscite.MODI] == [True, False, True, False]
    assert not uscite.modo_valido("boh")


async def test_link_solo_https_e_sicuro(monkeypatch):
    monkeypatch.setattr(uscite, "url_e_sicuro", AsyncMock(return_value=True))
    assert await uscite.valida_link("https://example.com/a.gif") is None
    assert "https" in await uscite.valida_link("http://example.com/a.gif")
    assert "lungo" in await uscite.valida_link("https://e.com/" + "a" * 600)
    monkeypatch.setattr(uscite, "url_e_sicuro", AsyncMock(return_value=False))
    assert "sicurezza" in await uscite.valida_link("https://127.0.0.1/a.gif")


def test_file_validi_e_rifiutati():
    assert uscite.valida_file(_png("PNG")) == ("png", None)
    assert uscite.valida_file(_png("GIF")) == ("gif", None)
    assert uscite.valida_file(b"non e' un'immagine")[0] is None
    assert "3 MB" in uscite.valida_file(b"0" * (uscite.MAX_BYTE_GRAFICA + 1))[1]


def test_file_oltre_16_megapixel_rifiutato():
    dati = _png("PNG", (4100, 4100))
    estensione, errore = uscite.valida_file(dati)
    assert estensione is None and "megapixel" in errore


# ------------------------------------------------------------ finestra
def _finestra_pronta(modo="solo_ban", file_ban=(), link_ban="", file_addio=(), link_addio=""):
    finestra = modulo.UsciteModal(_config())
    finestra.modo._values = [modo]
    finestra.file_ban._values = list(file_ban)
    finestra.link_ban._value = link_ban
    finestra.file_addio._values = list(file_addio)
    finestra.link_addio._value = link_addio
    return finestra


def _interazione():
    i = MagicMock()
    i.guild = fake_guild()
    i.response.defer = AsyncMock()
    i.followup.send = AsyncMock()
    return i


def test_finestra_uscite_entro_i_limiti_di_discord():
    finestra = modulo.UsciteModal(_config())
    assert len(finestra.title) <= 45
    assert len(finestra.children) <= 5
    for campo in finestra.children:
        assert len(campo.text) <= 45, campo.text


async def test_finestra_salva_modo_file_e_link(monkeypatch):
    repo = create_autospec(GreetingsRepository, instance=True)
    repo.get_config.return_value = _config()
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    monkeypatch.setattr(uscite, "url_e_sicuro", AsyncMock(return_value=True))
    allegato = MagicMock(spec=discord.Attachment, size=100)
    allegato.read = AsyncMock(return_value=_png("GIF"))
    finestra = _finestra_pronta("solo_addio", file_addio=[allegato], link_ban="https://example.com/m.gif")
    interazione = _interazione()
    await finestra.on_submit(interazione)
    repo.set_leave_mode.assert_awaited_once_with(interazione.guild.id, "solo_addio")
    repo.set_grafica.assert_any_await(interazione.guild.id, "ban", url="https://example.com/m.gif")
    nomi = [c.kwargs.get("filename") for c in repo.set_grafica.await_args_list]
    assert "addio.gif" in nomi


async def test_finestra_togli_cancella_la_grafica(monkeypatch):
    repo = create_autospec(GreetingsRepository, instance=True)
    repo.get_config.return_value = _config()
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    interazione = _interazione()
    await _finestra_pronta("entrambi", link_ban="Togli").on_submit(interazione)
    repo.clear_grafica.assert_awaited_once_with(interazione.guild.id, "ban")
    repo.set_grafica.assert_not_awaited()


async def test_finestra_campi_vuoti_non_toccano_la_grafica(monkeypatch):
    repo = create_autospec(GreetingsRepository, instance=True)
    repo.get_config.return_value = _config()
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    await _finestra_pronta("nessuno").on_submit(_interazione())
    repo.set_leave_mode.assert_awaited_once()
    repo.set_grafica.assert_not_awaited()
    repo.clear_grafica.assert_not_awaited()


async def test_finestra_link_non_sicuro_non_salva_niente(monkeypatch):
    repo = create_autospec(GreetingsRepository, instance=True)
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    interazione = _interazione()
    await _finestra_pronta("entrambi", link_ban="http://example.com/a.gif").on_submit(interazione)
    repo.set_leave_mode.assert_not_awaited()
    assert "https" in interazione.followup.send.await_args.args[0]


async def test_finestra_file_che_non_e_un_immagine_non_salva_niente(monkeypatch):
    repo = create_autospec(GreetingsRepository, instance=True)
    monkeypatch.setattr(modulo, "greetings_repo", repo)
    allegato = MagicMock(spec=discord.Attachment, size=10)
    allegato.read = AsyncMock(return_value=b"testo")
    interazione = _interazione()
    await _finestra_pronta("entrambi", file_ban=[allegato]).on_submit(interazione)
    repo.set_leave_mode.assert_not_awaited()
    assert "Non riesco" in interazione.followup.send.await_args.args[0]


# ------------------------------------------------------------ database
@pytest.fixture
def repo(clean_db):
    return GreetingsRepository(pool_provider=lambda: clean_db)


async def test_repo_modo_e_grafica(repo):
    assert (await repo.get_config(9)).leave_mode == "entrambi"
    await repo.set_leave_mode(9, "solo_ban")
    assert (await repo.get_config(9)).leave_mode == "solo_ban"
    assert await repo.get_grafica(9, "ban") is None
    await repo.set_grafica(9, "ban", url="https://example.com/a.gif")
    await repo.set_grafica(9, "addio", image=b"abc", filename="addio.png")
    assert await repo.get_grafica(9, "ban") == ("https://example.com/a.gif", None, None)
    assert await repo.get_grafica(9, "addio") == (None, b"abc", "addio.png")
    await repo.set_grafica(9, "ban", image=b"x", filename="b.gif")  # sostituisce il link
    assert await repo.get_grafica(9, "ban") == (None, b"x", "b.gif")
    await repo.clear_grafica(9, "ban")
    assert await repo.get_grafica(9, "ban") is None
    # il resto della riga non si perde
    await repo.set_welcome(9, enabled=True, channel_id=5, message="m", dm=False)
    assert (await repo.get_config(9)).leave_mode == "solo_ban"


async def test_martello_prima_dell_addio_anche_se_il_ban_tarda_a_inviare(monkeypatch):
    """L'addio parte solo dopo che il martello è uscito, non appena il ban è stato visto."""
    canale, membro, utente, repo = _scenario(monkeypatch)

    async def grafica_lenta(_g, tipo):
        if tipo == uscite.TIPO_BAN:
            await asyncio.sleep(0.02)  # lettura dal database: l'addio non deve passare avanti
        return None

    repo.get_grafica.side_effect = grafica_lenta
    await _ban_e_uscita(membro, utente, prima_ban=False)
    testi = _testi(canale)
    assert "martello" in testi[0] and "bello vederti" in testi[1]


def test_png_trasparente_grande_accettato():
    """safe_open_image riduce e converte le immagini RGBA grandi: il formato va letto dal file."""
    buf = io.BytesIO()
    Image.new("RGBA", (3000, 2000)).save(buf, format="PNG")
    assert uscite.valida_file(buf.getvalue()) == ("png", None)


def test_webp_oltre_il_suo_limite_ha_un_messaggio_giusto():
    estensione, errore = uscite.valida_file(_png("WEBP", (3000, 2000)))
    assert estensione is None and "16 megapixel" not in errore and "pixel" in errore
