"""
tests/test_catalogo_r2mod_verifica.py
=====================================
Verifica (#118, r2mod): pannello personalizzato (VER-028), ruolo avvisato a ogni account doppio (VER-023). Database vero.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs.security import alt_detection as cog_alt
from core import alt_detection_logic as logica
from core.database import db
from core.verify_logic import pannello_personalizzato
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role
from tests.test_verify_risposta_subito import GUILD_ID, scenario  # noqa: F401
from tests.test_verify_vpn_flusso import web  # noqa: F401  (fixture della pagina web)


# VER-028
def test_il_pannello_personalizzato_controlla_colore_e_lunghezze():
    ok, errore = pannello_personalizzato("Benvenuto", "Premi per entrare", "#c24a3a", "Entra", "🦊")
    assert errore is None and ok.colore == 0xC24A3A and ok.bottone == "Entra"
    assert pannello_personalizzato(None, None, "rosso", None, None)[1] is not None
    assert pannello_personalizzato("x" * 300, None, None, None, None)[1] is not None
    assert pannello_personalizzato(None, "x" * 2001, None, None, None)[1] is not None
    assert pannello_personalizzato(None, None, None, "x" * 81, None)[1] is not None
    assert pannello_personalizzato(None, None, None, None, "non un emoji lunghissimo")[1] is not None
    vuoto, errore = pannello_personalizzato(None, None, None, None, None)
    assert errore is None and vuoto.titolo is None


# VER-028
async def test_il_pannello_esce_con_titolo_testo_colore_e_bottone_scelti(scenario):
    await scenario.configura(captcha=False)
    i = fake_interaction(guild=scenario.server, user=fake_member(1))
    i.original_response = AsyncMock(return_value=MagicMock(channel=MagicMock(id=5), id=6))
    await scenario.cog.panel_cmd.callback(scenario.cog, i, "Porta del bosco", "Premi per entrare", "#c24a3a", "Entra", "🦊")
    kw = i.response.send_message.call_args.kwargs
    assert kw["embed"].title == "Porta del bosco" and kw["embed"].description == "Premi per entrare"
    assert kw["embed"].colour.value == 0xC24A3A
    assert kw["view"].children[0].label == "Entra" and str(kw["view"].children[0].emoji) == "🦊"
    assert kw["view"].children[0].custom_id  # resta il bottone persistente di sempre
    assert kw["allowed_mentions"].roles is False and kw["allowed_mentions"].everyone is False


# VER-028
async def test_un_pannello_con_colore_sbagliato_non_si_pubblica(scenario):
    await scenario.configura(captcha=False)
    i = fake_interaction(guild=scenario.server, user=fake_member(1))
    await scenario.cog.panel_cmd.callback(scenario.cog, i, None, None, "verde", None, None)
    i.response.send_message.assert_awaited_once()
    assert "embed" not in i.response.send_message.call_args.kwargs


def _canale_e_server(ruolo_id):
    canale = MagicMock(spec=discord.TextChannel)
    canale.send = AsyncMock()
    guild = fake_guild(guild_id=GUILD_ID)
    guild.get_channel = MagicMock(return_value=canale)
    ruolo = fake_role(ruolo_id, "Staff", position=3)
    guild.get_role = lambda rid: ruolo if rid == ruolo_id else None
    return canale, guild


# VER-023
async def test_l_avviso_dell_account_doppio_pinga_solo_il_ruolo_scelto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    canale, guild = _canale_e_server(321)
    await db.set_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT, 321)
    monkeypatch.setattr(cog_alt.verify_repo, "get_config", AsyncMock(return_value=SimpleNamespace(log_channel_id=5)))
    assert await cog_alt.avvisa_staff(guild, fake_member(1), [logica.Doppio(2, "alto")])
    kw = canale.send.await_args.kwargs
    assert kw["content"] == "<@&321>"
    assert kw["allowed_mentions"].everyone is False and kw["allowed_mentions"].users is False
    assert [r.id for r in kw["allowed_mentions"].roles] == [321]


# VER-023
async def test_senza_ruolo_o_con_ruolo_sparito_nessun_ping(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    canale, guild = _canale_e_server(321)
    monkeypatch.setattr(cog_alt.verify_repo, "get_config", AsyncMock(return_value=SimpleNamespace(log_channel_id=5)))
    await cog_alt.avvisa_staff(guild, fake_member(1), [logica.Doppio(2, "alto")])
    assert canale.send.await_args.kwargs["content"] is None
    await db.set_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT, 999)  # il ruolo non esiste più
    await cog_alt.avvisa_staff(guild, fake_member(1), [logica.Doppio(2, "alto")])
    assert canale.send.await_args.kwargs["content"] is None


# VER-023
async def test_il_ruolo_si_sceglie_solo_con_menziona_tutti_e_mai_everyone(scenario):
    ruolo = fake_role(321, "Staff", position=1)
    for permessi, ruolo_scelto, atteso in (
        (discord.Permissions(manage_guild=True), ruolo, None),
        (discord.Permissions(manage_guild=True, mention_everyone=True), ruolo, 321),
        (discord.Permissions(mention_everyone=True), fake_role(0, "@everyone", position=0), None),
    ):
        await db.set_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT, None)
        i = fake_interaction(guild=scenario.server, user=fake_member(55, guild_permissions=permessi))
        await scenario.cog.options_cmd.callback(scenario.cog, i, None, None, None, None, False, None, ruolo_scelto)
        assert await db.get_guild_setting(GUILD_ID, cog_alt.SETTING_RUOLO_AVVISO_ALT) == atteso


# VER-003
def test_il_codice_nuovo_tiene_i_tentativi_usati_e_ha_un_tetto_di_rinnovi():
    from datetime import datetime, timedelta, timezone

    from core import captcha_image

    ora = datetime(2026, 11, 1, tzinfo=timezone.utc)
    prima = captcha_image.nuova_sfida(ora)
    assert prima.prova("zzzzz", ora) == "sbagliata" and prima.tentativi_rimasti == 2
    seconda = prima.rinnova(ora + timedelta(seconds=60))
    assert seconda.codice != "" and seconda.tentativi_rimasti == 2 and seconda.rinnovi == 1
    assert prima.chiusa and prima.prova(prima.codice, ora) == "scaduta"  # il vecchio codice non vale più
    assert seconda.scade_il > prima.scade_il
    attuale = seconda
    for _ in range(captcha_image.RINNOVI_MASSIMI - 1):
        attuale = attuale.rinnova(ora)
    assert attuale.rinnovi == captcha_image.RINNOVI_MASSIMI and attuale.rinnova(ora) is None


# VER-003
async def test_il_bottone_codice_nuovo_rifa_l_immagine_ma_solo_a_chi_l_ha_chiesta(scenario):
    from tests.test_captcha_image import _setup_immagine
    from cogs.security.verify import VerifyPanelView
    from tests.test_verify_risposta_subito import UTENTE_ID

    await _setup_immagine(scenario)
    clic = scenario.clic()
    await VerifyPanelView().verify_click.callback(clic)
    vista = clic.followup.send.call_args.kwargs["view"]
    vecchia = scenario.cog.sfide.get((GUILD_ID, UTENTE_ID))
    estraneo = scenario.clic()
    estraneo.user = fake_member(1234)
    await vista.nuovo.callback(estraneo)
    assert scenario.cog.sfide.get((GUILD_ID, UTENTE_ID)) is vecchia  # un altro non tocca il codice
    mio = scenario.clic()
    mio.edit_original_response = AsyncMock()
    await vista.nuovo.callback(mio)
    nuova = scenario.cog.sfide.get((GUILD_ID, UTENTE_ID))
    assert nuova is not vecchia and nuova.rinnovi == 1
    assert mio.edit_original_response.await_args.kwargs["attachments"][0].filename == "verifica.png"


# VER-007
async def test_il_dm_all_ingresso_parte_solo_se_acceso_e_una_volta(scenario):
    from tests.test_verify_tempi import _tempi

    await scenario.configura(captcha=False)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    scenario.utente.send = AsyncMock()
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.send.assert_not_awaited()  # spento di base
    await _tempi(scenario, dm_ingresso=True)
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.send.assert_awaited_once()
    assert "Per entrare in" in scenario.utente.send.await_args.args[0]


# VER-007
async def test_con_i_dm_chiusi_l_ingresso_non_si_rompe(scenario):
    from tests.test_verify_tempi import _tempi

    await scenario.configura(captcha=False)
    await _tempi(scenario, dm_ingresso=True)
    scenario.utente.guild = scenario.server
    scenario.utente.roles = []
    scenario.utente.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "chiusi"))
    await scenario.cog.on_member_join(scenario.utente)
    scenario.utente.send.assert_awaited_once()


# VER-002
def test_lunghezza_misura_e_colore_del_captcha_stanno_nei_limiti():
    import io
    import random

    from PIL import Image

    from core import captcha_image as ci

    assert [ci.lunghezza_valida(v) for v in (2, 4, 6, 8, 99, "x", True, None)] == [4, 4, 6, 8, 8, 5, 5, 5]
    assert len(ci.genera_codice(None, 8)) == 8 and len(ci.genera_codice(None, 3)) == 4
    assert ci.colore_leggibile(0x3A2A2A) and not ci.colore_leggibile(0xFFFFFF) and not ci.colore_leggibile(0xFFEE00)
    piccola = Image.open(io.BytesIO(ci.disegna_immagine("AC2DK", random.Random(1), "piccola"))).size
    grande = Image.open(io.BytesIO(ci.disegna_immagine("AC2DK", random.Random(1), "grande"))).size
    assert piccola[0] < ci.LARGHEZZA < grande[0] and piccola[1] < ci.ALTEZZA < grande[1]
    otto = Image.open(io.BytesIO(ci.disegna_immagine("ACDEFGHJ", random.Random(1), "media"))).size
    assert otto[0] > ci.LARGHEZZA  # più lettere, immagine più larga
    colorata = Image.open(io.BytesIO(ci.disegna_immagine("AC2DK", random.Random(1), "media", 0x801010)))
    assert colorata.size == (ci.LARGHEZZA, ci.ALTEZZA)
    ci.disegna_immagine("AC2DK", random.Random(1), "enorme", 0xFFFFFF)  # valori strani: quelli di base, nessun errore


# VER-002
async def test_il_server_sceglie_lunghezza_misura_e_colore_e_l_immagine_li_usa(scenario):
    from discord import app_commands

    from cogs.security import verify as modulo
    from tests.test_captcha_image import _setup_immagine
    from tests.test_verify_risposta_subito import UTENTE_ID

    await _setup_immagine(scenario)
    i = fake_interaction(guild=scenario.server, user=fake_member(55, guild_permissions=discord.Permissions(manage_guild=True)))
    await scenario.cog.options_cmd.callback(
        scenario.cog, i, captcha_lunghezza=7, captcha_misura=app_commands.Choice(name="Grande", value="grande"),
        captcha_colore="#802020",
    )
    assert await db.get_guild_setting(GUILD_ID, modulo.SETTING_CAPTCHA_LUNGHEZZA) == 7
    assert await db.get_guild_setting(GUILD_ID, modulo.SETTING_CAPTCHA_COLORE) == 0x802020
    clic = scenario.clic()
    await scenario.cog.manda_captcha_immagine(clic, GUILD_ID)
    assert len(scenario.cog.sfide.get((GUILD_ID, clic.user.id)).codice) == 7
    assert await scenario.cog.aspetto_captcha(GUILD_ID) == ("grande", 0x802020)


# VER-002
async def test_un_colore_troppo_chiaro_o_sbagliato_non_si_salva(scenario):
    from cogs.security import verify as modulo

    for colore in ("#ffffff", "ciao", "#12345"):
        i = fake_interaction(guild=scenario.server, user=fake_member(55, guild_permissions=discord.Permissions(manage_guild=True)))
        await scenario.cog.options_cmd.callback(scenario.cog, i, captcha_colore=colore, captcha_lunghezza=6)
        assert await db.get_guild_setting(GUILD_ID, modulo.SETTING_CAPTCHA_COLORE) is None
        assert await db.get_guild_setting(GUILD_ID, modulo.SETTING_CAPTCHA_LUNGHEZZA) is None  # niente salvato a metà


# VER-006
def test_il_testo_della_pagina_e_ripulito_e_ha_dei_tetti():
    from core.alt_detection_logic import MAX_RIGHE_PAGINA, MAX_TESTO_PAGINA, testo_pagina_pulito

    assert testo_pagina_pulito("Ciao\n\n  entra ‮ qui \x00 ") == ["Ciao", "entra  qui"]
    assert testo_pagina_pulito(None) == [] and testo_pagina_pulito(5) == []
    assert len(testo_pagina_pulito("\n".join(["riga"] * 100))) == MAX_RIGHE_PAGINA
    assert sum(len(r) for r in testo_pagina_pulito("x" * 5000)) <= MAX_TESTO_PAGINA


# VER-006
async def test_la_pagina_web_mostra_il_testo_del_server_senza_html(clean_db, monkeypatch):
    import core.database as database_module
    from core import panel_bridge

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await db.set_guild_setting(GUILD_ID, "verify_testo_pagina", "Benvenuto!\n<script>alert(1)</script>")
    righe = await panel_bridge.testo_pagina_verifica(GUILD_ID)
    assert righe == ["Benvenuto!", "<script>alert(1)</script>"]


# VER-006
async def test_la_pagina_escapa_il_testo_scritto_dal_server(web, monkeypatch):
    from core import panel_bridge

    monkeypatch.setattr(panel_bridge, "testo_pagina_verifica", AsyncMock(return_value=["Benvenuto!", "<script>x</script>"]))
    pagina = await web.client.get(f"/verifica/{web.token}")
    testo = await pagina.text()
    assert "<p>Benvenuto!</p>" in testo and "&lt;script&gt;x&lt;/script&gt;" in testo and "<script>x</script>" not in testo


# VER-006
async def test_il_comando_salva_il_testo_e_azzera_lo_toglie(scenario):
    for kw, atteso in (({"testo_pagina": "  Entra pure  "}, "Entra pure"), ({"azzera": True}, None)):
        i = fake_interaction(guild=scenario.server, user=fake_member(55, guild_permissions=discord.Permissions(manage_guild=True)))
        await scenario.cog.options_cmd.callback(scenario.cog, i, **kw)
        assert await db.get_guild_setting(GUILD_ID, "verify_testo_pagina") == atteso
