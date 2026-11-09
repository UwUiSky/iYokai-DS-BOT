"""
tests/test_giveaway_extra.py
============================
D69 B9-B10 (UTL-116, 119, 120, 126, 128, 129, 130, 131, 132, 133): partecipanti, riepilogo, opzioni del server,
ruolo escluso e ruolo premio, immagine, fine del giveaway con ruolo/messaggi/log, modifica e riestrazione.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.utility.giveaway_extra as modulo
from core.giveaway_fine import concludi
from core.giveaway_fine import testo_annuncio as _annuncio
from core.giveaway_logic import (
    colore_annuncio,
    embed_annuncio,
    motivo_immagine_non_valida,
    motivo_ruolo_non_assegnabile,
    pagine_partecipanti,
    parse_colore,
    riempi,
    righe_requisiti,
    ruoli_esclusi_di,
)
from core.repositories.giveaway_repo import GiveawayOpzioni, GiveawayRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.support.percorsi import comando_nel_gruppo

ORA = datetime.now(timezone.utc)


@pytest.fixture
def repo(clean_db):
    return GiveawayRepository(pool_provider=lambda: clean_db)


async def _nuovo(repo, **extra):
    return await repo.create_giveaway(
        1, 500, "Nitro", 1, 0, None, ORA + timedelta(hours=1), 9, **extra
    )


# ------------------------------------------------------------------ logica pura
def test_colore_e_precedenze():
    assert parse_colore("#5865F2") == 0x5865F2 and parse_colore("ff0000") == 0xFF0000
    assert parse_colore("rosso") is None and parse_colore("#12345") is None
    g = SimpleNamespace(colore=None)
    assert colore_annuncio(g, SimpleNamespace(colore=0x123456)) == 0x123456
    assert colore_annuncio(SimpleNamespace(colore=1), SimpleNamespace(colore=2)) == 1


def test_embed_annuncio_con_immagine_e_righe():
    g = SimpleNamespace(
        prize="Nitro", winners_count=1, ends_at=ORA, min_level=0, required_role_id=None, min_messages=0,
        bypass_role_id=None, bonus_role_id=None, bonus_entries=0, ruolo_escluso=7, ruolo_premio=8,
        immagine_id=3, colore=None,
    )
    embed = embed_annuncio(g, GiveawayOpzioni(guild_id=1))
    assert embed.image.url == "attachment://giveaway.png"  # mai l'URL del CDN: scade
    assert "<@&7>" in embed.description and "<@&8>" in embed.description
    assert len(righe_requisiti(g)) == 2


def test_esclusi_del_giveaway_e_del_server():
    assert ruoli_esclusi_di(SimpleNamespace(ruolo_escluso=3), SimpleNamespace(ruoli_esclusi=(4, 5))) == {3, 4, 5}
    assert ruoli_esclusi_di(SimpleNamespace(ruolo_escluso=None), SimpleNamespace(ruoli_esclusi=())) == set()


def test_riempi_non_usa_format():
    assert riempi("Ciao {utente}, {premio} {altro} {0}", utente="Anna", premio="Nitro") == "Ciao Anna, Nitro {altro} {0}"


def test_pagine_e_limiti():
    assert [pagine_partecipanti(n) for n in (0, 1, 20, 21)] == [1, 1, 1, 2]
    base = dict(posizione_ruolo=1, gestito=False, di_base=False, posizione_bot=5, bot_puo_gestire_ruoli=True)
    assert motivo_ruolo_non_assegnabile(**base) is None
    assert motivo_ruolo_non_assegnabile(**{**base, "posizione_ruolo": 5}) == "giveaway_ruolo_premio_troppo_alto"
    assert motivo_ruolo_non_assegnabile(**{**base, "bot_puo_gestire_ruoli": False}) == "giveaway_ruolo_premio_manca_permesso"
    assert motivo_ruolo_non_assegnabile(**{**base, "gestito": True}) == "giveaway_ruolo_premio_non_valido"
    assert motivo_immagine_non_valida("image/png", 100, 100, 1000) is None
    assert motivo_immagine_non_valida("text/plain", 1, 1, 1) == "giveaway_immagine_non_valida"
    assert motivo_immagine_non_valida("image/png", 5000, 5000, 1000) == "giveaway_immagine_troppo_grande"
    assert motivo_immagine_non_valida("image/png", 10, 10, 9 * 1024 * 1024) == "giveaway_immagine_troppo_grande"


# ------------------------------------------------------------------ archivio
@pytest.mark.asyncio
async def test_campi_nuovi_del_giveaway_e_del_modello(repo):
    gid = await _nuovo(repo, ruolo_escluso=7, ruolo_premio=8, immagine_id=11, colore=0xABCDEF)
    g = await repo.get_giveaway(gid)
    assert (g.ruolo_escluso, g.ruolo_premio, g.immagine_id, g.colore) == (7, 8, 11, 0xABCDEF)
    await repo.save_template(1, "m", prize="P", winners_count=1, duration_minutes=5, ruolo_escluso=7, ruolo_premio=8,
                             immagine_id=12)
    m = await repo.get_template(1, "m")
    assert (m.ruolo_escluso, m.ruolo_premio, m.immagine_id) == (7, 8, 12)


@pytest.mark.asyncio
async def test_opzioni_del_server(repo):
    assert (await repo.get_opzioni(1)) == GiveawayOpzioni(guild_id=1)
    await repo.set_opzioni(1, colore=0x112233, bottone_testo="Entra", ruoli_esclusi=(5, 6), canale_log=70)
    o = await repo.get_opzioni(1)
    assert (o.colore, o.bottone_testo, o.ruoli_esclusi, o.canale_log) == (0x112233, "Entra", (5, 6), 70)
    await repo.set_opzioni(1, msg_dm="ciao")  # gli altri campi restano
    assert (await repo.get_opzioni(1)).bottone_testo == "Entra"
    await repo.set_opzioni(1, bottone_testo=None)
    assert (await repo.get_opzioni(1)).bottone_testo is None
    await repo.togli_canale(1, 99)
    assert (await repo.get_opzioni(1)).canale_log == 70
    await repo.togli_canale(1, 70)
    assert (await repo.get_opzioni(1)).canale_log is None
    with pytest.raises(ValueError):
        await repo.set_opzioni(1, sconosciuto=1)
    with pytest.raises(Exception):
        await repo.set_opzioni(1, ruoli_esclusi=tuple(range(26)))


@pytest.mark.asyncio
async def test_vincitori_ripescaggio_e_partecipanti(repo):
    gid = await _nuovo(repo)
    for uid in (1, 2, 3, 4):
        await repo.add_entry(gid, uid)
    await repo.segna_vincitori(gid, [2])
    assert await repo.get_vincitori(gid) == [2]
    assert {u for u, _ in await repo.get_entries_ripescabili(gid)} == {1, 3, 4}
    await repo.segna_vincitori(gid, [3])  # riestrazione: il 2 non si ripesca più
    assert await repo.get_vincitori(gid) == [3]
    assert {u for u, _ in await repo.get_entries_ripescabili(gid)} == {1, 4}
    assert await repo.list_partecipanti(gid, 2, 0) == [1, 2]
    assert await repo.list_partecipanti(gid, 2, 2) == [3, 4]


@pytest.mark.asyncio
async def test_modifica_in_corso_e_programmato_e_ricerca(repo):
    gid = await _nuovo(repo)
    nuova_fine = ORA + timedelta(hours=5)
    g = await repo.modifica(1, gid, prize="Altro", winners_count=3, ends_at=nuova_fine, duration_seconds=999)
    assert (g.prize, g.winners_count, g.ends_at) == ("Altro", 3, nuova_fine) and g.duration_seconds is None
    prog = await _nuovo(repo, starts_at=ORA + timedelta(days=1), duration_seconds=60)
    p = await repo.modifica(1, prog, ends_at=nuova_fine, duration_seconds=7200)
    assert p.duration_seconds == 7200 and p.ends_at != nuova_fine
    assert await repo.modifica(2, gid, prize="x") is None  # altro server
    assert [x.id for x in await repo.list_modificabili(1, "altro")] == [gid]
    assert len(await repo.list_modificabili(1)) == 2
    await repo.mark_ended(gid)
    assert await repo.modifica(1, gid, prize="x") is None
    assert (await repo.get_by_message(1, 1)) is None
    await repo.set_message_id(prog, 1234)
    assert (await repo.get_by_message(1, 1234)).id == prog and await repo.get_by_message(2, 1234) is None


@pytest.mark.asyncio
async def test_il_completamento_ha_al_massimo_25(repo):
    for _ in range(30):
        await _nuovo(repo)
    assert len(await repo.list_modificabili(1, "", 100)) == 25


# ------------------------------------------------------------------ fine del giveaway
def _scena_fine(*, ruolo_premio=None):
    giveaway = SimpleNamespace(id=4, prize="Nitro", channel_id=500, ruolo_premio=ruolo_premio)
    ruolo = MagicMock()
    membro = MagicMock(spec=discord.Member)
    membro.add_roles = AsyncMock()
    membro.send = AsyncMock()
    guild = MagicMock()
    guild.name = "Server"
    guild.get_role = MagicMock(return_value=ruolo)
    guild.get_member = MagicMock(return_value=membro)
    canale_log = MagicMock(spec=discord.TextChannel)
    canale_log.send = AsyncMock()
    guild.get_channel = MagicMock(return_value=canale_log)
    canale = MagicMock()
    canale.send = AsyncMock()
    return giveaway, guild, canale, membro, canale_log


@pytest.mark.asyncio
async def test_fine_con_ruolo_messaggio_e_log(monkeypatch):
    monkeypatch.setattr("core.giveaway_fine.PAUSA_TRA_MESSAGGI_PRIVATI", 0)
    giveaway, guild, canale, membro, canale_log = _scena_fine(ruolo_premio=77)
    opzioni = GiveawayOpzioni(guild_id=1, msg_dm="Hai vinto {premio} su {server}", canale_log=9)
    vista = object()
    await concludi(canale, guild, giveaway, [5], opzioni, "it", vista=vista)
    inviato = canale.send.await_args
    assert "<@5>" in inviato.args[0] and inviato.kwargs["view"] is vista
    assert inviato.kwargs["allowed_mentions"].everyone is False and inviato.kwargs["allowed_mentions"].roles is False
    membro.add_roles.assert_awaited_once()
    assert "Hai vinto Nitro su Server" in membro.send.await_args.args[0]
    canale_log.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_fine_senza_testo_nessun_messaggio_privato_e_un_errore_non_ferma_il_resto(monkeypatch):
    monkeypatch.setattr("core.giveaway_fine.PAUSA_TRA_MESSAGGI_PRIVATI", 0)
    giveaway, guild, canale, membro, canale_log = _scena_fine(ruolo_premio=77)
    membro.add_roles.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no")
    await concludi(canale, guild, giveaway, [5], GiveawayOpzioni(guild_id=1, canale_log=9), "it")
    membro.send.assert_not_awaited()
    assert "falliti" not in canale_log.send.await_args.kwargs["embed"].description  # testo del catalogo
    canale_log.send.assert_awaited_once()


def test_testo_annuncio():
    g = SimpleNamespace(prize="Nitro")
    assert "nessuno ha partecipato" in _annuncio(g, [], "it")
    assert "Nuova estrazione" in _annuncio(g, [5], "it", riestrazione=True)
    assert "Congratulazioni" in _annuncio(g, [5], "it") and "Congratulations" in _annuncio(g, [5], "en-US")  # lingua del server
    assert "nobody took part" in _annuncio(g, [], "en-US")


# ------------------------------------------------------------------ comandi e bottoni
@pytest.mark.asyncio
async def test_comandi_e_opzioni_nell_albero():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    for nome in ("partecipanti", "opzioni", "modifica"):
        assert comando_nel_gruppo("admin-giveaway", nome)
    assert any(c.name == "Riestrai giveaway" for c in bot.tree.get_commands(type=discord.AppCommandType.message))


def test_avvia_e_modello_hanno_le_opzioni_nuove():
    from cogs.leveling.leveling import LevelingCog

    avvia = {p.name for p in LevelingCog.giveaway.parameters} if hasattr(LevelingCog.giveaway, "parameters") else set()
    # Le firme sono la prova più semplice: i parametri nuovi esistono nelle funzioni.
    import inspect

    for funzione in (LevelingCog.giveaway, LevelingCog.giveaway_modello):
        nomi = set(inspect.signature(funzione.callback if hasattr(funzione, "callback") else funzione).parameters)
        assert {"ruolo_escluso", "ruolo_premio", "immagine"} <= nomi
    assert avvia is not None


class _Scena:
    def __init__(self, monkeypatch):
        self.repo = MagicMock()
        monkeypatch.setattr(modulo, "giveaway_repo", self.repo)
        db = MagicMock()
        db.is_module_active_for_guild = AsyncMock(return_value=True)
        monkeypatch.setattr(modulo, "db", db)
        self.guild = fake_guild()
        self.cog = modulo.GiveawayExtraCog(MagicMock())


@pytest.mark.asyncio
async def test_partecipanti_a_pagine_da_20(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.get_del_server = AsyncMock(return_value=SimpleNamespace(id=4))
    s.repo.count_entries = AsyncMock(return_value=45)
    s.repo.list_partecipanti = AsyncMock(return_value=list(range(1, 21)))
    i = fake_interaction(guild=s.guild)
    await s.cog.partecipanti.callback(s.cog, i, 4)
    s.repo.list_partecipanti.assert_awaited_with(4, 20, 0)
    inviato = i.response.send_message.await_args
    assert inviato.kwargs["ephemeral"] is True and inviato.kwargs["view"].avanti.disabled is False
    assert inviato.kwargs["view"].indietro.disabled is True
    assert inviato.kwargs["allowed_mentions"].users is False
    assert "pagina 1 di 3" in inviato.args[0]


@pytest.mark.asyncio
async def test_partecipanti_giveaway_di_un_altro_server(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.get_del_server = AsyncMock(return_value=None)
    i = fake_interaction(guild=s.guild)
    await s.cog.partecipanti.callback(s.cog, i, 4)
    s.repo.get_del_server.assert_awaited_once_with(s.guild.id, 4)
    s.repo.count_entries.assert_not_called()


@pytest.mark.asyncio
async def test_la_lista_la_sfoglia_solo_chi_l_ha_aperta(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    vista = modulo.ListaPartecipantiView(4, proprietario=1, totale=50)
    estraneo = fake_interaction(user=fake_member(2))
    assert await vista.interaction_check(estraneo) is False
    assert await vista.interaction_check(fake_interaction(user=fake_member(1))) is True


@pytest.mark.asyncio
async def test_riepilogo_mostra_i_dati_e_non_oltre_il_server(monkeypatch):
    s = _Scena(monkeypatch)
    g = SimpleNamespace(id=4, guild_id=s.guild.id, prize="Nitro", ends_at=ORA)
    s.repo.get_giveaway = AsyncMock(return_value=g)
    s.repo.count_entries = AsyncMock(return_value=12)
    s.repo.get_vincitori = AsyncMock(return_value=[5, 6])
    i = fake_interaction(guild=s.guild)
    await modulo.BottoneRiepilogo(4).callback(i)
    testo = i.response.send_message.await_args.args[0]
    assert "Nitro" in testo and "12" in testo and "<@5>" in testo
    s.repo.get_giveaway = AsyncMock(return_value=SimpleNamespace(id=4, guild_id=999, prize="x", ends_at=ORA))
    i2 = fake_interaction(guild=s.guild)
    await modulo.BottoneRiepilogo(4).callback(i2)
    assert "Nitro" not in i2.response.send_message.await_args.args[0]


@pytest.mark.asyncio
async def test_opzioni_log_senza_permessi_non_salva(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_opzioni = AsyncMock()
    canale = MagicMock(spec=discord.TextChannel)
    canale.mention = "<#5>"
    canale.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True))
    i = fake_interaction(guild=s.guild)
    await s.cog.opzioni.callback(s.cog, i, canale, False)
    s.repo.set_opzioni.assert_not_awaited()


@pytest.mark.asyncio
async def test_finestra_aspetto_rifiuta_colore_ed_emoji_non_validi(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.set_opzioni = AsyncMock()
    testi = {k: "x" for k in ("colore", "emoji", "testo", "conferma", "dm")}
    finestra = modulo.FinestraAspetto(GiveawayOpzioni(guild_id=1), "Titolo", testi)
    finestra.colore._value = "rosso"
    i = fake_interaction(guild=s.guild)
    await finestra.on_submit(i)
    s.repo.set_opzioni.assert_not_awaited()
    finestra.colore._value = "#FF0000"
    finestra.emoji._value = "non-emoji"
    await finestra.on_submit(fake_interaction(guild=s.guild))
    s.repo.set_opzioni.assert_not_awaited()
    finestra.emoji._value = "🎉"
    finestra.testo._value = "Entra"
    await finestra.on_submit(fake_interaction(guild=s.guild))
    s.repo.set_opzioni.assert_awaited_once_with(
        s.guild.id, colore=0xFF0000, bottone_emoji="🎉", bottone_testo="Entra"
    )


def test_i_limiti_dei_testi_liberi():
    testi = {k: "x" for k in ("colore", "emoji", "testo", "conferma", "dm")}
    a = modulo.FinestraAspetto(GiveawayOpzioni(guild_id=1), "T", testi)
    assert (a.colore.max_length, a.emoji.max_length, a.testo.max_length) == (7, 64, 80)
    m = modulo.FinestraMessaggi(GiveawayOpzioni(guild_id=1), "T", testi)
    assert (m.conferma.max_length, m.dm.max_length) == (500, 1000)


@pytest.mark.asyncio
async def test_modifica_senza_nulla_da_cambiare(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.modifica = AsyncMock()
    i = fake_interaction(guild=s.guild)
    await s.cog.modifica.callback(s.cog, i, 4, None, None, None, None)
    s.repo.modifica.assert_not_awaited()


@pytest.mark.asyncio
async def test_modifica_rifiuta_allegato_non_immagine(monkeypatch):
    s = _Scena(monkeypatch)
    s.repo.modifica = AsyncMock()
    allegato = SimpleNamespace(content_type="application/zip", width=None, height=None, size=10, url="u")
    i = fake_interaction(guild=s.guild)
    await s.cog.modifica.callback(s.cog, i, 4, None, None, None, allegato)
    s.repo.modifica.assert_not_awaited()


@pytest.mark.asyncio
async def test_riestrai_solo_su_annuncio_finito_e_ripesca(monkeypatch):
    s = _Scena(monkeypatch)
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=True))
    messaggio = SimpleNamespace(id=900)
    s.repo.get_by_message = AsyncMock(return_value=None)
    i = fake_interaction(guild=s.guild)
    await s.cog.menu_riestrai(i, messaggio)
    s.repo.get_entries_ripescabili.assert_not_called()
    s.repo.get_by_message = AsyncMock(return_value=SimpleNamespace(id=4, ended=False, winners_count=1))
    i = fake_interaction(guild=s.guild)
    await s.cog.menu_riestrai(i, messaggio)
    s.repo.get_entries_ripescabili.assert_not_called()

    s.repo.get_by_message = AsyncMock(
        return_value=SimpleNamespace(id=4, ended=True, winners_count=1, channel_id=500, prize="P", ruolo_premio=None)
    )
    s.repo.get_entries_ripescabili = AsyncMock(return_value=[(7, 1)])
    s.repo.segna_vincitori = AsyncMock()
    s.repo.get_opzioni = AsyncMock(return_value=GiveawayOpzioni(guild_id=1))
    chiamato = AsyncMock()
    monkeypatch.setattr(modulo, "concludi", chiamato)
    monkeypatch.setattr("core.giveaway_worker._canale_del_giveaway", AsyncMock(return_value=MagicMock()))
    i = fake_interaction(guild=s.guild)
    await s.cog.menu_riestrai(i, messaggio)
    s.repo.segna_vincitori.assert_awaited_once_with(4, [7])
    assert chiamato.await_args.kwargs["riestrazione"] is True


@pytest.mark.asyncio
async def test_riestrai_senza_permesso(monkeypatch):
    s = _Scena(monkeypatch)
    monkeypatch.setattr(modulo, "puo_usare", AsyncMock(return_value=False))
    s.repo.get_by_message = AsyncMock()
    await s.cog.menu_riestrai(fake_interaction(guild=s.guild), SimpleNamespace(id=1))
    s.repo.get_by_message.assert_not_called()


# ------------------------------------------------------------------ immagine durevole (non l'URL del CDN)
def _allegato(dati=b"originale-non-controllato"):
    a = MagicMock()
    a.read = AsyncMock(return_value=dati)
    a.filename, a.content_type = "x.png", "image/png"
    return a


@pytest.mark.asyncio
async def test_si_conserva_la_copia_ricodificata_non_l_originale(repo, monkeypatch):
    import core.giveaway_immagine as gi
    from core.immagini_pipeline import EsitoImmagine

    monkeypatch.setattr(gi, "giveaway_repo", repo)
    monkeypatch.setattr(gi, "analizza_immagine", AsyncMock(return_value=EsitoImmagine(png=b"PNG-RICODIFICATO")))
    immagine_id, errore = await gi.conserva_allegato(_allegato(), 1)
    assert errore is None
    assert await repo.get_immagine(immagine_id) == b"PNG-RICODIFICATO"
    file = await gi.file_annuncio(immagine_id)
    assert file.filename == "giveaway.png" and file.fp.read() == b"PNG-RICODIFICATO"


@pytest.mark.asyncio
async def test_immagine_malevola_o_non_analizzata_non_si_conserva(repo, monkeypatch):
    import core.giveaway_immagine as gi
    from core.immagini_byte_logic import MALEVOLA
    from core.immagini_pipeline import EsitoImmagine

    monkeypatch.setattr(gi, "giveaway_repo", repo)
    for esito in (EsitoImmagine(verdetto=MALEVOLA, png=b"x"), EsitoImmagine(png=b"x", non_analizzata="coda_piena"),
                  EsitoImmagine(png=b"")):
        monkeypatch.setattr(gi, "analizza_immagine", AsyncMock(return_value=esito))
        assert await gi.conserva_allegato(_allegato(), 1) == (None, "giveaway_immagine_non_valida")
    assert await repo._pool.fetchval("SELECT count(*) FROM giveaway_immagini") == 0


@pytest.mark.asyncio
async def test_la_stessa_immagine_si_tiene_una_volta_e_le_orfane_si_tolgono(repo):
    a = await repo.salva_immagine(1, "h1", b"A")
    assert await repo.salva_immagine(1, "h1", b"A") == a
    b = await repo.salva_immagine(1, "h2", b"B")
    await repo._pool.execute("UPDATE giveaway_immagini SET created_at = NOW() - INTERVAL '1 hour'")
    gid = await _nuovo(repo, immagine_id=a)
    await repo.pulisci_immagini(1)
    assert await repo.get_immagine(a) == b"A" and await repo.get_immagine(b) is None
    assert await repo.get_giveaway(gid) is not None


@pytest.mark.asyncio
async def test_modifica_salva_la_copia_conservata_non_l_url(monkeypatch):
    s = _Scena(monkeypatch)
    monkeypatch.setattr(modulo, "conserva_allegato", AsyncMock(return_value=(42, None)))
    s.repo.modifica = AsyncMock(return_value=None)
    allegato = SimpleNamespace(content_type="image/png", width=10, height=10, size=10, url="https://cdn.discordapp.com/scade.png")
    await s.cog.modifica.callback(s.cog, fake_interaction(guild=s.guild), 4, None, None, None, allegato)
    assert s.repo.modifica.await_args.kwargs["immagine_id"] == 42
    assert "immagine_url" not in s.repo.modifica.await_args.kwargs


@pytest.mark.asyncio
async def test_modifica_con_immagine_rifiutata_dalla_pipeline_non_cambia_nulla(monkeypatch):
    s = _Scena(monkeypatch)
    monkeypatch.setattr(modulo, "conserva_allegato", AsyncMock(return_value=(None, "giveaway_immagine_non_valida")))
    allegato = SimpleNamespace(content_type="image/png", width=10, height=10, size=10, url="u")
    await s.cog.modifica.callback(s.cog, fake_interaction(guild=s.guild), 4, None, None, None, allegato)
    s.repo.modifica.assert_not_called()
