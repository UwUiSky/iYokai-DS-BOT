"""
tests/test_automod_filtri_messaggi.py
=====================================
I filtri AutoMod lato bot provati uno per uno con messaggi che hanno
davvero un contenuto (BUG-5): prima l'intent `message_content` era
spento e i filtri leggevano messaggi vuoti.

Ogni filtro viene acceso con il suo comando `/automod …` (database
vero), poi il messaggio passa da `on_message`. I messaggi sono finti
fedeli (`tests/support/discord_fakes.py`).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import create_autospec

import discord
import pytest
from discord import app_commands

import cogs.automod.automod as modulo_automod
import cogs.moderation._shared as modulo_shared
from core.automod_rate_tracker import AutomodRateTracker
from core.database import Database
from core.repositories.automod_advanced_repo import automod_advanced_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_text_channel,
)

GUILD_ID = 666
AUTORE_ID = 4242


@pytest.fixture
def cog(clean_db, monkeypatch):
    db_finto = create_autospec(Database, instance=True)
    db_finto.is_module_active_for_guild.return_value = True
    db_finto.get_guild_setting.return_value = None
    monkeypatch.setattr(modulo_shared, "db", db_finto)
    monkeypatch.setattr(modulo_automod, "db", db_finto)

    monkeypatch.setattr(automod_advanced_repo, "_pool_provider", lambda: clean_db)
    # Contatore nuovo per ogni test: quello vero è condiviso da tutto il processo.
    monkeypatch.setattr(modulo_automod, "rate_tracker", AutomodRateTracker())
    return modulo_automod.AutomodCog(bot=None)


def _interazione_admin() -> discord.Interaction:
    return fake_interaction(guild=fake_guild(guild_id=GUILD_ID))


def _messaggio(contenuto: str = "", **attributi) -> discord.Message:
    server = fake_guild(guild_id=GUILD_ID)
    autore = fake_member(user_id=AUTORE_ID)
    autore.guild = server
    messaggio = fake_message(author=autore, guild=server, content=contenuto)
    messaggio.channel = fake_text_channel(channel_id=111)
    messaggio.mentions = attributi.get("mentions", [])
    messaggio.role_mentions = []
    messaggio.mention_everyone = False
    messaggio.attachments = attributi.get("attachments", [])
    messaggio.stickers = attributi.get("stickers", [])
    return messaggio


def _scelta(valore: str) -> app_commands.Choice:
    return app_commands.Choice(name=valore, value=valore)


async def _violazioni_registrate() -> list[str]:
    recenti = await automod_advanced_repo.get_recent_actions(GUILD_ID)
    return [riga["violation"] for riga in recenti]


# ====================================================================
# Un test per filtro (M 2.1)
# ====================================================================
async def test_anti_link_blacklist_cancella_il_link_vietato(cog):
    await cog.anti_link_mode.callback(cog, _interazione_admin(), _scelta("blacklist"))
    await cog.anti_link_domain.callback(
        cog, _interazione_admin(), _scelta("add"), _scelta("blacklist"), "evil.com"
    )
    vietato = _messaggio("guardate qui https://evil.com/premio")
    pulito = _messaggio("guardate qui https://esempio.it/pagina")

    await cog.on_message(vietato)
    await cog.on_message(pulito)

    vietato.delete.assert_awaited_once()
    pulito.delete.assert_not_awaited()
    assert await _violazioni_registrate() == ["anti_link"]


async def test_anti_link_dominio_scritto_come_link_blocca_anche_le_varianti(cog):
    # M 2.6: la voce viene salvata come nome host; porta, nome utente e
    # sottodominio non bastano più per aggirare la lista.
    await cog.anti_link_mode.callback(cog, _interazione_admin(), _scelta("blacklist"))
    await cog.anti_link_domain.callback(
        cog, _interazione_admin(), _scelta("add"), _scelta("blacklist"), "https://www.Evil.com/"
    )
    varianti = [
        _messaggio("https://evil.com:443/premio"),
        _messaggio("https://x@evil.com/premio"),
        _messaggio("https://sub.evil.com/premio"),
    ]

    for messaggio in varianti:
        await cog.on_message(messaggio)

    for messaggio in varianti:
        messaggio.delete.assert_awaited_once()
    impostazioni = await automod_advanced_repo.get_settings(GUILD_ID)
    assert impostazioni.config.anti_link.blacklist == ("evil.com",)


async def test_anti_link_whitelist_cancella_il_link_non_ammesso(cog):
    await cog.anti_link_mode.callback(cog, _interazione_admin(), _scelta("whitelist"))
    await cog.anti_link_domain.callback(
        cog, _interazione_admin(), _scelta("add"), _scelta("whitelist"), "esempio.it"
    )
    ammesso = _messaggio("la guida è su https://esempio.it/guida")
    altro = _messaggio("la guida è su https://altro.net/guida")

    await cog.on_message(ammesso)
    await cog.on_message(altro)

    ammesso.delete.assert_not_awaited()
    altro.delete.assert_awaited_once()


async def test_anti_caps_cancella_il_messaggio_urlato(cog):
    await cog.anti_caps.callback(cog, _interazione_admin(), True, 70, 10)
    urlato = _messaggio("COMPRATE SUBITO QUESTO PRODOTTO")
    normale = _messaggio("Comprate pure questo prodotto")

    await cog.on_message(urlato)
    await cog.on_message(normale)

    urlato.delete.assert_awaited_once()
    normale.delete.assert_not_awaited()
    assert await _violazioni_registrate() == ["anti_caps"]


async def test_anti_zalgo_cancella_il_testo_con_segni_anomali(cog):
    await cog.anti_zalgo.callback(cog, _interazione_admin(), True)
    zalgo = _messaggio("c" + "́" * 12 + "iao")
    accentato = _messaggio("perché no, è così")

    await cog.on_message(zalgo)
    await cog.on_message(accentato)

    zalgo.delete.assert_awaited_once()
    accentato.delete.assert_not_awaited()
    assert await _violazioni_registrate() == ["anti_zalgo"]


async def test_anti_spam_emoji_conta_le_emoji_nel_testo(cog):
    await cog.anti_spam_emoji.callback(cog, _interazione_admin(), True, 3)
    troppe = _messaggio("ciao 😀😀 <:yokai:123456789012345678> <a:balla:123456789012345679>")
    poche = _messaggio("ciao 😀 <:yokai:123456789012345678>")

    await cog.on_message(troppe)
    await cog.on_message(poche)

    troppe.delete.assert_awaited_once()
    poche.delete.assert_not_awaited()
    assert await _violazioni_registrate() == ["anti_spam_emoji"]


async def test_anti_mention_cancella_chi_tagga_troppi_utenti(cog):
    await cog.anti_mention.callback(cog, _interazione_admin(), True, 2)
    taggati = [fake_member(user_id=numero) for numero in (1, 2, 3)]
    troppi = _messaggio("<@1> <@2> <@3> venite", mentions=taggati)
    pochi = _messaggio("<@1> vieni", mentions=taggati[:1])

    await cog.on_message(troppi)
    await cog.on_message(pochi)

    troppi.delete.assert_awaited_once()
    pochi.delete.assert_not_awaited()
    assert await _violazioni_registrate() == ["anti_mass_mention"]


async def test_anti_spam_messaggi_scatta_oltre_il_massimo(cog):
    await cog.anti_spam_messages.callback(cog, _interazione_admin(), True, 2, 10)
    messaggi = [_messaggio(f"messaggio numero {numero}") for numero in range(3)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)

    messaggi[0].delete.assert_not_awaited()
    messaggi[1].delete.assert_not_awaited()
    messaggi[2].delete.assert_awaited_once()
    assert await _violazioni_registrate() == ["anti_spam_messages"]


async def test_anti_spam_sticker_scatta_oltre_il_massimo(cog):
    await cog.anti_spam_sticker.callback(cog, _interazione_admin(), True, 1, 30)
    sticker = create_autospec(discord.StickerItem, instance=True)
    messaggi = [_messaggio("", stickers=[sticker]) for _ in range(2)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)

    messaggi[0].delete.assert_not_awaited()
    messaggi[1].delete.assert_awaited_once()
    assert await _violazioni_registrate() == ["anti_spam_sticker"]


async def test_anti_attachment_scatta_oltre_il_massimo(cog):
    await cog.anti_attachment.callback(cog, _interazione_admin(), True, 1, 30)
    allegato = create_autospec(discord.Attachment, instance=True)
    messaggi = [_messaggio("ecco la foto", attachments=[allegato]) for _ in range(2)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)

    messaggi[0].delete.assert_not_awaited()
    messaggi[1].delete.assert_awaited_once()
    assert await _violazioni_registrate() == ["anti_attachment_spam"]


# ====================================================================
# La finestra `seconds=` salvata viene usata davvero (M 2.5)
# ====================================================================
@pytest.fixture
def orologio(monkeypatch):
    """Orologio finto: il test decide che ore sono a ogni messaggio."""
    stato = {"adesso": datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(discord.utils, "utcnow", lambda: stato["adesso"])

    def avanti(secondi: int) -> None:
        stato["adesso"] += timedelta(seconds=secondi)

    return avanti


async def test_finestra_messaggi_di_5_secondi_rispettata(cog, orologio):
    # Massimo 2 messaggi ogni 5 secondi. Tre messaggi a 4 secondi l'uno
    # dall'altro: con la vecchia finestra fissa di 10 secondi il terzo
    # veniva cancellato, con quella di 5 no.
    await cog.anti_spam_messages.callback(cog, _interazione_admin(), True, 2, 5)
    messaggi = [_messaggio(f"messaggio {numero}") for numero in range(3)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)
        orologio(4)

    for messaggio in messaggi:
        messaggio.delete.assert_not_awaited()


async def test_finestra_messaggi_di_30_secondi_rispettata(cog, orologio):
    # Tre messaggi a 12 secondi l'uno dall'altro stanno tutti in 30
    # secondi: il terzo supera il massimo di 2.
    await cog.anti_spam_messages.callback(cog, _interazione_admin(), True, 2, 30)
    messaggi = [_messaggio(f"messaggio {numero}") for numero in range(3)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)
        orologio(12)

    messaggi[2].delete.assert_awaited_once()


async def test_finestra_sticker_salvata_rispettata(cog, orologio):
    await cog.anti_spam_sticker.callback(cog, _interazione_admin(), True, 1, 5)
    sticker = create_autospec(discord.StickerItem, instance=True)
    messaggi = [_messaggio("", stickers=[sticker]) for _ in range(2)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)
        orologio(10)

    messaggi[1].delete.assert_not_awaited()


async def test_finestra_allegati_salvata_rispettata(cog, orologio):
    await cog.anti_attachment.callback(cog, _interazione_admin(), True, 1, 5)
    allegato = create_autospec(discord.Attachment, instance=True)
    messaggi = [_messaggio("foto", attachments=[allegato]) for _ in range(2)]

    for messaggio in messaggi:
        await cog.on_message(messaggio)
        orologio(10)

    messaggi[1].delete.assert_not_awaited()


@pytest.mark.parametrize(
    "nome_comando", ["anti-spam-messages", "anti-spam-sticker", "anti-attachment"]
)
def test_seconds_ha_un_minimo_e_un_massimo(nome_comando):
    from discord.ext import commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    gruppo = modulo_automod.AutomodCog(bot).automod_group.to_dict(bot.tree)
    comando = next(c for c in gruppo["options"] if c["name"] == nome_comando)
    opzione = next(o for o in comando["options"] if o["name"] == "seconds")

    assert opzione["min_value"] == 1
    assert opzione["max_value"] == modulo_automod.MAX_FINESTRA_SECONDI
