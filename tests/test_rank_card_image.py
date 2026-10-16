"""
tests/test_rank_card_image.py
=================================
NF-12 (#83): la rank card come immagine. Disegno (dimensioni, nome lungo,
livello massimo, avatar rotto o troppo grande), preferenze di colore e
tema, posizione in classifica e comando `/level rank`.
Funzioni coperte: SPEC §22.8
"""

import io
from unittest.mock import AsyncMock

import discord
import pytest
from PIL import Image

import cogs.leveling.leveling as modulo
from core.rank_card_image import (
    COLORE_DI_BASE,
    LARGHEZZA,
    ALTEZZA,
    TEMI,
    DatiRankCard,
    colore_valido,
    render_rank_card,
)
from core.repositories.leveling_repo import LevelingRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member


def _dati(**campi) -> DatiRankCard:
    base = dict(
        nome="Yokai",
        livello=7,
        xp_nel_livello=120,
        xp_richiesti=400,
        xp_totale=1500,
        posizione=3,
        coin=250,
        colore=COLORE_DI_BASE,
        tema="scuro",
    )
    base.update(campi)
    return DatiRankCard(**base)


def _png(lato: int = 64, colore=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (lato, lato), colore).save(buffer, format="PNG")
    return buffer.getvalue()


def _apri(dati_png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(dati_png))


# ----------------------------------------------------------------------
# Disegno
# ----------------------------------------------------------------------
def test_la_card_ha_sempre_le_stesse_dimensioni():
    immagine = _apri(render_rank_card(_dati(), _png()))

    assert immagine.format == "PNG"
    assert immagine.size == (LARGHEZZA, ALTEZZA)


def test_nome_lunghissimo_non_rompe_il_disegno():
    immagine = _apri(render_rank_card(_dati(nome="W" * 300), _png()))

    assert immagine.size == (LARGHEZZA, ALTEZZA)


def test_livello_massimo_senza_xp_richiesti_non_divide_per_zero():
    immagine = _apri(render_rank_card(_dati(xp_nel_livello=0, xp_richiesti=0), _png()))

    assert immagine.size == (LARGHEZZA, ALTEZZA)


def test_progresso_oltre_il_richiesto_resta_dentro_la_barra():
    immagine = _apri(render_rank_card(_dati(xp_nel_livello=9999, xp_richiesti=400), _png()))

    assert immagine.size == (LARGHEZZA, ALTEZZA)


def test_senza_posizione_o_con_numeri_enormi():
    render_rank_card(_dati(posizione=None, xp_totale=10**12, coin=10**12, livello=10**6), _png())


@pytest.mark.parametrize("tema", sorted(TEMI))
def test_ogni_tema_si_disegna_e_cambia_lo_sfondo(tema):
    immagine = _apri(render_rank_card(_dati(tema=tema), None)).convert("RGB")

    assert immagine.getpixel((5, 5)) == TEMI[tema].sfondo


def test_il_colore_scelto_colora_la_barra():
    rosso = _apri(render_rank_card(_dati(colore="#FF0000", xp_nel_livello=400), None)).convert("RGB")

    # Barra piena: un punto dentro la barra ha il colore scelto.
    pixel = rosso.getpixel((300, 195))
    assert pixel == (255, 0, 0)


def test_avatar_mancante_rotto_o_enorme_la_card_si_disegna_lo_stesso():
    render_rank_card(_dati(), None)
    render_rank_card(_dati(), b"questo non e' un'immagine")
    enorme = io.BytesIO()
    Image.new("1", (5000, 5000)).save(enorme, format="PNG")  # 25 MP: oltre il limite
    render_rank_card(_dati(), enorme.getvalue())


@pytest.mark.parametrize(
    "testo, atteso",
    [
        ("#FF8800", "#FF8800"),
        ("ff8800", "#FF8800"),
        ("  #00aa11 ", "#00AA11"),
        ("#FFF", None),
        ("rosso", None),
        ("#GG0000", None),
        ("", None),
    ],
)
def test_colore_valido(testo, atteso):
    assert colore_valido(testo) == atteso


def test_un_colore_malformato_nei_dati_ricade_su_quello_di_base():
    render_rank_card(_dati(colore="zzz"), None)


# ----------------------------------------------------------------------
# Archivio: posizione e preferenze
# ----------------------------------------------------------------------
@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_posizione_in_classifica(repo, clean_db):
    await clean_db.executemany(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total) VALUES ($1, $2, $3)",
        [(100, 1, 500), (100, 2, 900), (100, 3, 100), (200, 4, 9999)],
    )

    assert await repo.get_xp_position(100, 2) == 1
    assert await repo.get_xp_position(100, 1) == 2
    assert await repo.get_xp_position(100, 3) == 3


@pytest.mark.asyncio
async def test_posizione_a_pari_xp_non_salta_nessuno(repo, clean_db):
    await clean_db.executemany(
        "INSERT INTO leveling_totals (guild_id, user_id, xp_total) VALUES ($1, $2, $3)",
        [(100, 1, 500), (100, 2, 500), (100, 3, 100)],
    )

    # Stesso XP: stessa posizione (nessuno è "davanti" all'altro).
    assert await repo.get_xp_position(100, 1) == await repo.get_xp_position(100, 2) == 1
    assert await repo.get_xp_position(100, 3) == 3


@pytest.mark.asyncio
async def test_posizione_di_chi_non_ha_xp_e_none(repo):
    assert await repo.get_xp_position(100, 999) is None


@pytest.mark.asyncio
async def test_preferenze_della_card(repo):
    assert await repo.get_rank_card_prefs(1) == (None, None)

    await repo.set_rank_card_prefs(1, colore="#FF0000")
    await repo.set_rank_card_prefs(1, tema="chiaro")  # non cancella il colore

    assert await repo.get_rank_card_prefs(1) == ("#FF0000", "chiaro")
    assert await repo.get_rank_card_prefs(2) == (None, None)


@pytest.mark.asyncio
async def test_preferenze_con_valori_non_validi_sono_rifiutate(repo):
    with pytest.raises(ValueError):
        await repo.set_rank_card_prefs(1, colore="rosso")
    with pytest.raises(ValueError):
        await repo.set_rank_card_prefs(1, tema="inventato")


@pytest.mark.asyncio
async def test_ripristino_delle_preferenze(repo):
    await repo.set_rank_card_prefs(1, colore="#FF0000", tema="notte")

    await repo.reset_rank_card_prefs(1)

    assert await repo.get_rank_card_prefs(1) == (None, None)


# ----------------------------------------------------------------------
# Comando /level rank
# ----------------------------------------------------------------------
@pytest.fixture
async def cog_rank(monkeypatch, clean_db):
    from tests.support.moduli import attiva_livelli

    await attiva_livelli(monkeypatch, clean_db, 100)
    repo = LevelingRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(modulo, "leveling_repo", repo)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    return cog, repo


def _bersaglio(user_id=1):
    membro = fake_member(user_id=user_id, name="Yokai")
    membro.display_name = "Yokai"
    membro.display_avatar = AsyncMock()
    membro.display_avatar.read = AsyncMock(return_value=_png())
    membro.display_avatar.url = "https://cdn.example/avatar.png"
    return membro


@pytest.mark.asyncio
async def test_rank_risponde_subito_con_defer_e_poi_manda_l_immagine(cog_rank):
    cog, repo = cog_rank
    await repo.add_text_xp(100, 1)
    utente = _bersaglio(1)
    interazione = fake_interaction(guild=fake_guild(100), user=utente)
    ordine = []
    interazione.response.defer.side_effect = lambda *a, **k: ordine.append("defer")
    interazione.followup.send.side_effect = lambda *a, **k: ordine.append("invio")

    await cog.rank.callback(cog, interazione, member=None, colore=None, tema=None, reimposta=None)

    assert ordine == ["defer", "invio"]
    file_inviato = interazione.followup.send.await_args.kwargs["file"]
    assert isinstance(file_inviato, discord.File)
    assert file_inviato.filename == "rank.png"
    assert _apri(file_inviato.fp.read()).size == (LARGHEZZA, ALTEZZA)


@pytest.mark.asyncio
async def test_rank_se_l_avatar_non_si_scarica_la_card_c_e_lo_stesso(cog_rank):
    cog, _ = cog_rank
    utente = _bersaglio(1)
    utente.display_avatar.read.side_effect = discord.HTTPException(AsyncMock(status=500, reason="x"), "boom")
    interazione = fake_interaction(guild=fake_guild(100), user=utente)

    await cog.rank.callback(cog, interazione, member=None, colore=None, tema=None, reimposta=None)

    assert isinstance(interazione.followup.send.await_args.kwargs["file"], discord.File)


@pytest.mark.asyncio
async def test_rank_se_il_disegno_fallisce_ricade_sull_embed(cog_rank, monkeypatch):
    cog, _ = cog_rank

    def rotto(*_):
        raise RuntimeError("Pillow rotto")

    monkeypatch.setattr(modulo, "render_rank_card", rotto)
    interazione = fake_interaction(guild=fake_guild(100), user=_bersaglio(1))

    await cog.rank.callback(cog, interazione, member=None, colore=None, tema=None, reimposta=None)

    assert isinstance(interazione.followup.send.await_args.kwargs["embed"], discord.Embed)


@pytest.mark.asyncio
async def test_rank_salva_colore_e_tema_solo_per_se_stessi(cog_rank):
    cog, repo = cog_rank
    utente = _bersaglio(1)
    interazione = fake_interaction(guild=fake_guild(100), user=utente)

    await cog.rank.callback(cog, interazione, member=None, colore="ff0000", tema=None, reimposta=None)
    assert await repo.get_rank_card_prefs(1) == ("#FF0000", None)

    # Sulla card di un altro non si cambiano le sue preferenze.
    altro = _bersaglio(2)
    interazione = fake_interaction(guild=fake_guild(100), user=utente)
    await cog.rank.callback(cog, interazione, member=altro, colore="00ff00", tema=None, reimposta=None)
    assert await repo.get_rank_card_prefs(2) == (None, None)
    assert "solo la tua" in interazione.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_rank_colore_non_valido_dice_errore_e_non_salva(cog_rank):
    cog, repo = cog_rank
    interazione = fake_interaction(guild=fake_guild(100), user=_bersaglio(1))

    await cog.rank.callback(cog, interazione, member=None, colore="rosso", tema=None, reimposta=None)

    assert await repo.get_rank_card_prefs(1) == (None, None)
    assert "#RRGGBB" in interazione.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_rank_reimposta_toglie_le_preferenze(cog_rank):
    cog, repo = cog_rank
    await repo.set_rank_card_prefs(1, colore="#FF0000", tema="notte")
    interazione = fake_interaction(guild=fake_guild(100), user=_bersaglio(1))

    await cog.rank.callback(cog, interazione, member=None, colore=None, tema=None, reimposta=True)

    assert await repo.get_rank_card_prefs(1) == (None, None)


# ----------------------------------------------------------------------
# Sfondo con immagine propria (NF-12, resto di #83)
# ----------------------------------------------------------------------
from core.rank_card_image import (  # noqa: E402
    ALTEZZA_PROFILO,
    MAX_BYTE_SFONDO,
    DatiProfilo,
    SfondoNonValido,
    prepara_sfondo,
    render_profile_card,
)


def _immagine(larghezza, altezza, colore=(10, 200, 10), formato="PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (larghezza, altezza), colore).save(buffer, format=formato)
    return buffer.getvalue()


def test_prepara_sfondo_ritaglia_e_comprime():
    pronto = prepara_sfondo(_immagine(3000, 500))
    assert len(pronto) <= MAX_BYTE_SFONDO
    aperto = _apri(pronto)
    assert (aperto.format, aperto.size) == ("JPEG", (LARGHEZZA, ALTEZZA_PROFILO))


def test_prepara_sfondo_rifiuta_un_file_che_non_e_un_immagine_o_troppo_grande():
    with pytest.raises(SfondoNonValido):
        prepara_sfondo(b"non sono un'immagine")
    enorme = io.BytesIO()
    Image.new("1", (5000, 5000)).save(enorme, format="PNG")  # 25 MP, oltre il limite di 16
    with pytest.raises(SfondoNonValido):
        prepara_sfondo(enorme.getvalue())


def test_rumore_casuale_resta_sotto_il_tetto_di_byte():
    import os

    rumore = Image.frombytes("RGB", (1600, 720), os.urandom(1600 * 720 * 3))
    buffer = io.BytesIO()
    rumore.save(buffer, format="PNG")
    assert len(prepara_sfondo(buffer.getvalue())) <= MAX_BYTE_SFONDO


def test_card_con_sfondo_mostra_l_immagine_fuori_dal_pannello():
    sfondo = prepara_sfondo(_immagine(800, 360))
    card = _apri(render_rank_card(_dati(), _png(), sfondo)).convert("RGB")
    assert card.size == (LARGHEZZA, ALTEZZA)
    assert card.getpixel((4, 4))[1] > 150
    senza = _apri(render_rank_card(_dati(), _png())).convert("RGB")
    assert senza.getpixel((4, 4)) == TEMI["scuro"].sfondo


def test_sfondo_rotto_non_rompe_la_card():
    assert _apri(render_rank_card(_dati(), None, b"rotto")).size == (LARGHEZZA, ALTEZZA)


def test_profilo_con_presentazione_lunga_e_numeri_enormi():
    dati = DatiProfilo(
        nome="N" * 200, presentazione="parola " * 40 + "x" * 300, livello=10**9,
        xp_totale=10**15, posizione=None, coin=10**12, collezione=3, collezione_totale=14,
    )
    assert _apri(render_profile_card(dati, None)).size == (LARGHEZZA, ALTEZZA_PROFILO)


@pytest.mark.asyncio
async def test_sfondo_salvato_e_tolto_con_reimposta(repo):
    await repo.set_sfondo_card(1, b"jpeg")
    await repo.set_rank_card_prefs(1, colore="#FF0000")
    assert await repo.get_sfondo_card(1) == b"jpeg"
    await repo.reset_rank_card_prefs(1)
    assert await repo.get_sfondo_card(1) is None


def _allegato(dati: bytes, tipo="image/png"):
    allegato = AsyncMock(spec=discord.Attachment)
    allegato.size = len(dati)
    allegato.content_type = tipo
    allegato.read = AsyncMock(return_value=dati)
    return allegato


@pytest.mark.asyncio
async def test_rank_con_sfondo_lo_salva_e_lo_usa(cog_rank, monkeypatch):
    cog, repo = cog_rank
    usati = []
    vero = modulo.render_rank_card
    monkeypatch.setattr(modulo, "render_rank_card", lambda d, a, s=None: usati.append(s) or vero(d, a, s))
    interazione = fake_interaction(guild=fake_guild(100), user=_bersaglio(1))

    await cog.rank.callback(cog, interazione, sfondo=_allegato(_immagine(900, 400)))

    salvato = await repo.get_sfondo_card(1)
    assert salvato is not None and usati == [salvato]


@pytest.mark.asyncio
async def test_rank_sfondo_non_immagine_e_rifiutato(cog_rank):
    cog, repo = cog_rank
    interazione = fake_interaction(guild=fake_guild(100), user=_bersaglio(1))

    await cog.rank.callback(cog, interazione, sfondo=_allegato(b"%PDF", tipo="application/pdf"))

    assert await repo.get_sfondo_card(1) is None
    assert interazione.followup.send.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_server_con_sfondi_spenti_mostra_solo_il_tema(cog_rank, monkeypatch):
    from core.repositories.leveling_settings_repo import leveling_settings_repo

    cog, repo = cog_rank
    await repo.set_sfondo_card(1, prepara_sfondo(_immagine(800, 360)))
    await leveling_settings_repo.set_options(100, card_images=False)
    usati = []
    vero = modulo.render_rank_card
    monkeypatch.setattr(modulo, "render_rank_card", lambda d, a, s=None: usati.append(s) or vero(d, a, s))
    interazione = fake_interaction(guild=fake_guild(100), user=_bersaglio(1))

    try:
        await cog.rank.callback(cog, interazione)
    finally:
        leveling_settings_repo._cache.clear()  # la cache di 60 s non deve passare ad altri test

    assert usati == [None]
