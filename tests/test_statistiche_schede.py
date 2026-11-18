"""#130 blocco 4: schede (ID, invito, emoji) e elenco membri in file."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.utility.schede import SchedeCog
from core.schede_logic import campi_canale, campi_emoji, campi_invito, campi_ruolo, campi_server, campi_utente, leggi_emoji, righe_membri_csv
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel


# STA-060: l'ID di server, canale, ruolo e utente è nelle schede
def test_sta_060_gli_id_stanno_nelle_schede():
    g = fake_guild(11)
    assert campi_server(g)[0] == ("ID", "`11`")
    assert campi_canale(fake_text_channel(22))[0] == ("ID", "`22`")
    assert campi_ruolo(fake_role(33))[0] == ("ID", "`33`")
    assert campi_utente(fake_member(44))[0] == ("ID", "`44`")


# STA-059: emoji
def test_sta_059_emoji_personalizzata_unicode_e_non_valida():
    assert leggi_emoji("<a:ciao:123456789012345678>") == ("custom", "ciao", 123456789012345678, True)
    assert leggi_emoji("123456789012345678")[0] == "custom"
    assert leggi_emoji("😀")[0] == "unicode"
    for cattivo in ("ciao", "<:x:1>", "", "😀" * 30):
        assert leggi_emoji(cattivo)[0] == "niente"
    campi = dict(campi_emoji("😀"))
    assert campi["Punti Unicode"] == "U+1F600"
    custom = dict(campi_emoji("<a:ciao:123456789012345678>"))
    assert custom["Animata"] == "sì" and custom["Immagine"].endswith("123456789012345678.gif")
    assert "Server" not in custom  # l'emoji non è nota al bot: nessun nome di server
    nota = SimpleNamespace(name="x", animated=False, guild_id=5)
    assert dict(campi_emoji("<:xx:123456789012345678>", nota, 5))["Server"] == "questo"
    assert "Server" not in dict(campi_emoji("<:xx:123456789012345678>", nota, 6))  # mai il server di un altro


# STA-059: invito
def test_sta_059_scheda_invito():
    inv = SimpleNamespace(code="abc", guild=SimpleNamespace(name="Casa"), channel=SimpleNamespace(name="generale"),
                          inviter=SimpleNamespace(name="Mario", id=7), approximate_member_count=100, approximate_presence_count=40,
                          expires_at=None, uses=None)
    campi = dict(campi_invito(inv))
    assert campi["Server"] == "Casa" and campi["Membri"] == "100" and campi["Scade"] == "mai" and "Usi" not in campi


# STA-059
async def test_sta_059_comando_invito_pulisce_il_codice_e_gestisce_gli_errori():
    bot = MagicMock()
    cog = SchedeCog(bot)
    inv = SimpleNamespace(code="abc", guild=None, channel=None, inviter=None, approximate_member_count=None,
                          approximate_presence_count=None, expires_at=None, uses=None)
    bot.fetch_invite = AsyncMock(return_value=inv)
    it = fake_interaction(guild=fake_guild(1))
    await cog.invito.callback(cog, it, "https://discord.gg/abc")
    bot.fetch_invite.assert_awaited_once_with("abc", with_counts=True, with_expiration=True)
    bot.fetch_invite.reset_mock()
    it = fake_interaction(guild=fake_guild(1))
    await cog.invito.callback(cog, it, "../../etc/passwd?x=1")
    bot.fetch_invite.assert_not_awaited()
    bot.fetch_invite.side_effect = discord.NotFound(MagicMock(status=404), "x")
    it = fake_interaction(guild=fake_guild(1))
    await cog.invito.callback(cog, it, "zzzz")
    assert it.followup.send.await_args.kwargs["ephemeral"] is True


# STA-059
async def test_sta_059_comando_emoji():
    bot = MagicMock(); bot.get_emoji = MagicMock(return_value=None)
    cog = SchedeCog(bot)
    it = fake_interaction(guild=fake_guild(1))
    await cog.emoji.callback(cog, it, "😀")
    assert it.response.send_message.await_args.kwargs["embed"].fields
    it = fake_interaction(guild=fake_guild(1))
    await cog.emoji.callback(cog, it, "boh")
    assert "embed" not in it.response.send_message.await_args.kwargs


# STA-058: membri in file
def test_sta_058_righe_con_tetto():
    m = fake_member(1); m.display_name = "=cmd"; m.joined_at = datetime(2026, 1, 1, tzinfo=timezone.utc); m.created_at = m.joined_at
    assert righe_membri_csv([m])[0][:3] == [1, "=cmd", "no"]


# STA-058
async def test_sta_058_il_file_dei_membri_solo_a_chi_gestisce_il_server():
    cog = SchedeCog(MagicMock())
    g = fake_guild(1); g.chunked = True
    m = fake_member(5); m.display_name = "=SOMMA(1)"; m.joined_at = m.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    g.members = [m]
    it = fake_interaction(guild=g)
    it.user.guild_permissions = discord.Permissions.none()
    await cog.membri.callback(cog, it, None, True)
    it.response.defer.assert_not_awaited()  # rifiutato prima di fare altro
    it = fake_interaction(guild=g)
    it.user.guild_permissions = discord.Permissions(manage_guild=True)
    await cog.membri.callback(cog, it, None, True)
    f = it.followup.send.await_args.kwargs["file"]
    assert f.filename == "membri.csv"
    testo = f.fp.read().decode("utf-8-sig")
    assert "'=SOMMA(1)" in testo and testo.startswith("id;nome")  # niente formule nel foglio di calcolo
    it = fake_interaction(guild=g)
    await cog.membri.callback(cog, it, None, False)  # né ruolo né file
    it.response.defer.assert_not_awaited()
