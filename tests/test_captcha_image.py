"""
tests/test_captcha_image.py
===========================
Captcha a immagine (NF-18, #89): il codice, l'immagine, le prove, e il
percorso completo dal clic sul pannello al ruolo (database vero).
"""

import io
import random
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import discord
from discord import app_commands
from PIL import Image

from cogs.security.verify import (
    SETTING_CAPTCHA_TIPO,
    CaptchaImmagineModal,
    CaptchaImmagineView,
    VerifyPanelView,
)
from core import captcha_image
from core.captcha_image import Sfida, TENTATIVI_MASSIMI, TEMPO_MASSIMO_SECONDI
from tests.support.discord_fakes import fake_interaction
from tests.test_verify_risposta_subito import GUILD_ID, UTENTE_ID, Scenario, scenario  # noqa: F401


def test_il_codice_ha_la_lunghezza_giusta_e_niente_lettere_ambigue():
    for _ in range(200):
        codice = captcha_image.genera_codice()
        assert len(codice) == captcha_image.LUNGHEZZA_CODICE
        assert not set(codice) & set("0O1ILB8")


def test_l_immagine_e_un_png_piccolo_della_misura_giusta():
    png = captcha_image.disegna_immagine("AC2DK", random.Random(1))
    immagine = Image.open(io.BytesIO(png))
    assert immagine.format == "PNG"
    assert immagine.size == (captcha_image.LARGHEZZA, captcha_image.ALTEZZA)
    assert len(png) < 30_000


def test_due_immagini_dello_stesso_codice_sono_diverse():
    assert captcha_image.disegna_immagine("AC2DK", random.Random(1)) != captcha_image.disegna_immagine(
        "AC2DK", random.Random(2)
    )


def test_la_risposta_ignora_maiuscole_e_spazi():
    assert captcha_image.risposta_giusta("AC2DK", " ac 2dk ")
    assert not captcha_image.risposta_giusta("AC2DK", "AC2DJ")
    assert not captcha_image.risposta_giusta("AC2DK", "")


def test_la_sfida_finisce_dopo_tre_errori():
    sfida = Sfida("AC2DK", datetime.now(timezone.utc) + timedelta(seconds=60))
    esiti = [sfida.prova("xxxxx") for _ in range(TENTATIVI_MASSIMI)]
    assert esiti == ["sbagliata", "sbagliata", "esaurita"]
    assert sfida.prova("AC2DK") == "scaduta"  # chiusa: anche la risposta giusta non vale piu'


def test_la_sfida_scade_col_tempo():
    ora = datetime.now(timezone.utc)
    sfida = captcha_image.nuova_sfida(ora)
    assert sfida.prova(sfida.codice, ora + timedelta(seconds=TEMPO_MASSIMO_SECONDI + 1)) == "scaduta"
    assert captcha_image.nuova_sfida(ora).prova("zzzzz", ora) in ("sbagliata",)


def test_l_etichetta_del_modulo_sta_nel_limite():
    modulo = CaptchaImmagineModal(MagicMock(), GUILD_ID, UTENTE_ID)
    assert len(modulo.children[0].text) <= captcha_image.ETICHETTA_MAX
    assert modulo.answer_input.max_length == captcha_image.LUNGHEZZA_CODICE + 3


async def _setup_immagine(scenario, tipo="immagine"):
    from core.database import db

    from tests.support.discord_fakes import fake_member

    interazione = fake_interaction(guild=scenario.server, user=fake_member(user_id=1, name="owner"))
    await scenario.cog.setup_cmd.callback(
        scenario.cog, interazione, app_commands.Choice(name="Button", value="button"), scenario.ruolo,
        0, 0, False, None, app_commands.Choice(name="Immagine", value=tipo),
    )
    return db, interazione


async def test_setup_con_immagine_accende_il_captcha_e_salva_il_tipo(scenario):
    db, interazione = await _setup_immagine(scenario)
    from core.repositories.verify_repo import verify_repo

    assert (await verify_repo.get_config(GUILD_ID)).captcha_enabled is True
    assert await db.get_guild_setting(GUILD_ID, SETTING_CAPTCHA_TIPO) == "immagine"


async def test_setup_reaction_con_immagine_e_rifiutato(scenario):
    from tests.support.discord_fakes import fake_member

    interazione = fake_interaction(guild=scenario.server, user=fake_member(user_id=1, name="owner"))
    await scenario.cog.setup_cmd.callback(
        scenario.cog, interazione, app_commands.Choice(name="Reaction", value="reaction"), scenario.ruolo,
        0, 0, False, None, app_commands.Choice(name="Immagine", value="immagine"),
    )
    assert "non è supportato" in interazione.response.send_message.call_args.args[0]


async def test_clic_con_immagine_manda_file_e_bottone_poi_modulo_poi_ruolo(scenario, clean_db):
    await _setup_immagine(scenario)
    clic = scenario.clic()

    await VerifyPanelView().verify_click.callback(clic)

    assert scenario.ordine == ["defer", "followup"]
    invio = clic.followup.send.call_args.kwargs
    assert isinstance(invio["file"], discord.File) and invio["file"].filename == "verifica.png"
    assert isinstance(invio["view"], CaptchaImmagineView) and invio["ephemeral"] is True
    sfida = scenario.cog.sfide.get((GUILD_ID, UTENTE_ID))
    assert sfida is not None

    # Il bottone apre il modulo come prima risposta.
    bottone = scenario.clic()
    await invio["view"].scrivi.callback(bottone)
    modulo = bottone.response.send_modal.call_args.args[0]
    assert isinstance(modulo, CaptchaImmagineModal)

    # Risposta giusta: ruolo dato, sfida chiusa.
    modulo.answer_input._value = sfida.codice.lower()
    invio_modulo = scenario.clic()
    scenario.ordine.clear()
    await modulo.on_submit(invio_modulo)
    assert scenario.ordine == ["defer", "ruolo", "followup"]
    assert scenario.cog.sfide.get((GUILD_ID, UTENTE_ID)) is None
    assert await clean_db.fetchval("SELECT count(*) FROM verify_attempts WHERE success") == 1


async def test_risposta_sbagliata_lascia_riprovare_e_la_terza_blocca(scenario, clean_db):
    await _setup_immagine(scenario)
    await VerifyPanelView().verify_click.callback(scenario.clic())
    modulo = CaptchaImmagineModal(scenario.cog, GUILD_ID, UTENTE_ID)
    modulo.answer_input._value = "ZZZZZ"

    for restano in (2, 1):
        scenario.ordine.clear()
        interazione = scenario.clic()
        await modulo.on_submit(interazione)
        assert scenario.ordine == ["defer", "followup"]  # nessun ruolo, nessun tentativo scritto
        assert f"{restano} tentativi" in interazione.followup.send.call_args.args[0]
    assert await clean_db.fetchval("SELECT count(*) FROM verify_attempts") == 0

    await modulo.on_submit(scenario.clic())  # terzo errore
    assert scenario.cog.sfide.get((GUILD_ID, UTENTE_ID)) is None
    assert await clean_db.fetchval("SELECT count(*) FROM verify_attempts WHERE NOT success") == 1
    assert "ruolo" not in scenario.ordine


async def test_il_bottone_e_solo_di_chi_ha_ricevuto_il_codice(scenario):
    await _setup_immagine(scenario)
    vista = CaptchaImmagineView(scenario.cog, GUILD_ID, 7777)
    altro = scenario.clic()
    await vista.scrivi.callback(altro)
    altro.response.send_modal.assert_not_called()
    altro.response.send_message.assert_called_once()


async def test_sfida_scaduta_non_apre_il_modulo(scenario):
    await _setup_immagine(scenario)
    await VerifyPanelView().verify_click.callback(scenario.clic())
    scenario.cog.sfide.get((GUILD_ID, UTENTE_ID)).scade_il = datetime.now(timezone.utc) - timedelta(seconds=1)
    vista = CaptchaImmagineView(scenario.cog, GUILD_ID, UTENTE_ID)
    interazione = scenario.clic()
    await vista.scrivi.callback(interazione)
    interazione.response.send_modal.assert_not_called()


async def test_captcha_testo_resta_il_default(scenario):
    from tests.test_verify_risposta_subito import CaptchaModal

    await scenario.configura(captcha=True)
    interazione = scenario.clic()
    await VerifyPanelView().verify_click.callback(interazione)
    assert isinstance(interazione.response.send_modal.call_args.args[0], CaptchaModal)
