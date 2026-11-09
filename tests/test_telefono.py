"""Il telefono tra server (#131, B12, FUN-079/080): regole, centralino, inoltro, blocchi e registro."""
import asyncio
import random
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from core import telefono_logic as tl
from core.repositories.telefono_repo import TIPO_SERVER, TIPO_UTENTE, telefono_repo


def test_nome_senza_discord_clyde_e_entro_80():
    assert "discord" not in tl.pulisci_nome("MioDiscordBot").lower()
    assert "clyde" not in tl.pulisci_nome("Clyde ClYdE").lower()
    assert tl.pulisci_nome("Discord") == "Utente"
    assert 1 <= len(tl.pulisci_nome("x" * 300)) <= 80
    assert len(tl.nome_mittente("a" * 100, "b" * 100)) <= 80


def test_link_e_inviti_tolti_allegati_solo_indirizzi_e_tetto():
    t = tl.prepara_testo("guarda https://x.it/a discord.gg/abc www.foo.it ok", ["https://cdn.discordapp.com/a.png", "http://no"])
    assert "x.it" not in t and "discord.gg" not in t and "foo.it" not in t
    assert "📎 https://cdn.discordapp.com/a.png" in t and "http://no" not in t
    assert tl.prepara_testo("   ", []) is None
    assert len(tl.prepara_testo("a" * 5000, [])) == 1900


def test_effetti():
    assert tl.applica_effetto("nessuno", "ciao") == "ciao"
    assert tl.applica_effetto("capovolto", "ab") != "ab"
    m = tl.applica_effetto("mescolato", "programmazione", random.Random(1))
    assert m[0] == "p" and m[-1] == "e" and sorted(m) == sorted("programmazione")
    assert tl.applica_effetto("owo", "ciao") != "ciao"
    assert tl.applica_effetto("emoji", "ab") != "ab"
    assert set(tl.EFFETTI) == {"nessuno", "capovolto", "mescolato", "owo", "emoji"}


def test_adulti_mai_verso_canali_senza_limite():
    assert tl.adulti_bloccato(True, False)
    assert not tl.adulti_bloccato(True, True) and not tl.adulti_bloccato(False, False) and not tl.adulti_bloccato(False, True)


def test_pausa_utente_due_secondi():
    t = [0.0]
    p = tl.PausaUtenti(lambda: t[0])
    assert p.passa(1) and not p.passa(1) and p.passa(2)
    t[0] = 2.1
    assert p.passa(1)


async def test_centralino_squillo_risposta_e_scadenze():
    t = [0.0]
    c = tl.Centralino(ora=lambda: t[0], rng=random.Random(1))
    canali = {1: 10, 2: 20, 3: 30}
    assert await c.suona(1, [], canali, "nessuno", 5) is None
    s = await c.suona(1, [1, 2, 3], canali, "owo", 5)
    assert s.chiamato in (2, 3) and c.occupato(1) and c.occupato(s.chiamato)
    assert await c.suona(1, [2, 3], canali, "nessuno", 5) is None  # già in squillo
    altro = ({2, 3} - {s.chiamato}).pop()
    assert await c.suona(altro, [s.chiamato], canali, "nessuno", 6) is None  # il chiamato è occupato
    ch = await c.risposto(1, s.chiamato)
    assert ch.effetti[1] == "owo" and c.chiamata_di(s.chiamato) is ch and await c.risposto(1, s.chiamato) is None
    t[0] = tl.SILENZIO_MAX_SECONDI - 1
    assert c.scadute() == []
    c.tocca(ch)
    t[0] += tl.SILENZIO_MAX_SECONDI
    assert c.scadute() == [(ch, tl.FINE_SILENZIO)]
    c.tocca(ch)
    t[0] = tl.DURATA_MAX_SECONDI
    assert c.scadute() == [(ch, tl.FINE_DURATA)]
    assert await c.termina(1) is ch and not c.occupato(1) and not c.occupato(s.chiamato)


async def test_centralino_rifiuto_e_riavvio_chiudono_pulito():
    c = tl.Centralino(rng=random.Random(2))
    canali = {1: 10, 2: 20, 3: 30, 4: 40}
    await c.suona(1, [2], canali, "nessuno", 1)
    assert (await c.annulla_squillo(1)).chiamato == 2 and not c.occupato(2)
    await c.suona(1, [2], canali, "nessuno", 1)
    await c.risposto(1, 2)
    await c.suona(3, [4], canali, "nessuno", 1)
    chiamate, squilli = await c.svuota()
    assert len(chiamate) == 1 and len(squilli) == 1 and not c.occupato(1) and not c.occupato(3)


async def test_centralino_due_chiamate_insieme_non_si_sovrappongono():
    canali = {i: i * 10 for i in range(1, 5)}
    c = tl.Centralino(rng=random.Random(3))
    r = await asyncio.gather(*(c.suona(g, [1, 2, 3, 4], canali, "nessuno", g) for g in (1, 2, 3, 4)))
    coinvolti = [x for s in r if s for x in (s.chiamante, s.chiamato)]
    assert len(coinvolti) == len(set(coinvolti))


async def test_repo_blocchi_registro_canale_webhook(clean_db, monkeypatch):
    from core import database as dm
    monkeypatch.setattr(dm.db, "_pool", clean_db)
    db_pool = clean_db
    await telefono_repo.imposta_canale(1, 11)
    await telefono_repo.imposta_canale(1, 12)
    assert await telefono_repo.canale(1) == 12 and (await telefono_repo.canali())[1] == 12
    await telefono_repo.segna_webhook(1, 99)
    assert (1, 99) in await telefono_repo.webhook_rimasti()
    await telefono_repo.segna_webhook(1, None)
    assert (1, 99) not in await telefono_repo.webhook_rimasti()
    assert await telefono_repo.blocca(1, TIPO_UTENTE, 7) and not await telefono_repo.blocca(1, TIPO_UTENTE, 7)
    await telefono_repo.blocca(1, TIPO_SERVER, 2)
    assert await telefono_repo.bloccato(1, TIPO_UTENTE, 7) and not await telefono_repo.bloccato(1, TIPO_SERVER, 7)
    assert await telefono_repo.server_che_bloccano(2) == {1}
    assert len(await telefono_repo.elenco_blocchi(1)) == 2
    assert await telefono_repo.sblocca(1, TIPO_UTENTE, 7) and not await telefono_repo.bloccato(1, TIPO_UTENTE, 7)
    await telefono_repo.registra(1, 2, datetime.now(timezone.utc), 120, "durata", True)
    r = (await telefono_repo.registro(2))[0]
    assert r["altro"] == 1 and r["durata_secondi"] == 120 and r["segnalata"]
    colonne = {x["column_name"] for x in await db_pool.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='telefono_registro'")}
    assert not ({"testo", "messaggio", "autore", "user_id"} & colonne)


def _cog(monkeypatch, parola_vietata=None, blacklist=False):
    import discord
    from cogs.fun import telefono as tel

    cog = tel.TelefonoCog(MagicMock())
    chiamata = tl.Chiamata(a=1, b=2, canali={1: 10, 2: 20}, effetti={1: "nessuno", 2: "nessuno"}, chi_chiama=5, inizio=0, ultimo=0, pronta=True)
    chiamata.code[2] = asyncio.Queue(maxsize=3)
    dest = MagicMock(spec=discord.TextChannel)
    dest.is_nsfw.return_value = False
    cog._canale = lambda g, c: dest
    monkeypatch.setattr(tel, "trova_nel_testo", AsyncMock(return_value=parola_vietata))
    monkeypatch.setattr(tel.blacklist_repo, "is_user_blacklisted", AsyncMock(return_value=blacklist))
    monkeypatch.setattr(tel.telefono_repo, "bloccato", AsyncMock(return_value=False))
    msg = MagicMock()
    msg.guild.id, msg.guild.name = 1, "Casa"
    msg.author.id, msg.author.display_name = 7, "Discord Mario"
    msg.author.display_avatar.url = "https://x/a.png"
    msg.content, msg.attachments = "ciao @everyone https://x.it", []
    msg.channel.is_nsfw.return_value = False
    return cog, chiamata, msg, dest


async def test_inoltro_testo_pulito_nome_pulito(monkeypatch):
    cog, ch, msg, dest = _cog(monkeypatch)
    await cog._inoltra(msg, ch)
    testo, nome, avatar, _ = ch.code[2].get_nowait()
    assert "x.it" not in testo and "discord" not in nome.lower() and len(nome) <= 80 and avatar.startswith("https://")


@pytest.mark.parametrize("caso", ["adulti", "automod", "blacklist", "bloccato", "pausa", "minori", "minori_con_effetto"])
async def test_inoltro_scartato(monkeypatch, caso):
    from cogs.fun import telefono as tel
    cog, ch, msg, dest = _cog(monkeypatch, parola_vietata="x" if caso == "automod" else None, blacklist=caso == "blacklist")
    if caso == "adulti":
        msg.channel.is_nsfw.return_value = True
    if caso == "minori":
        msg.content = "cerco una teen di 13 anni"
    if caso == "minori_con_effetto":  # l'effetto non deve nascondere il testo al filtro
        msg.content = "13 year old"
        ch.effetti[1] = "mescolato"
    if caso == "bloccato":
        monkeypatch.setattr(tel.telefono_repo, "bloccato", AsyncMock(return_value=True))
    if caso == "pausa":
        await cog._inoltra(msg, ch)
        ch.code[2].get_nowait()
    await cog._inoltra(msg, ch)
    assert ch.code[2].empty()


async def test_nsfw_verso_nsfw_passa(monkeypatch):
    cog, ch, msg, dest = _cog(monkeypatch)
    msg.channel.is_nsfw.return_value = True
    dest.is_nsfw.return_value = True
    await cog._inoltra(msg, ch)
    assert not ch.code[2].empty()


async def test_webhook_cancellato_chiude_la_chiamata_senza_riprovare(monkeypatch):
    import discord
    cog, ch, msg, dest = _cog(monkeypatch)
    chiusure = []
    cog.chiudi = AsyncMock(side_effect=lambda g, f: chiusure.append((g, f)))
    wh = MagicMock()
    wh.send = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), "x"))
    coda = asyncio.Queue()
    await coda.put(("a", "n", "https://x", False))
    await asyncio.wait_for(cog._lavora(ch, 2, wh, coda), 2)
    await asyncio.sleep(0)
    assert wh.send.await_count == 1 and chiusure == [(2, tl.FINE_ERRORE)]


async def test_nsfw_cambia_mentre_il_messaggio_aspetta_non_passa(monkeypatch):
    cog, ch, msg, dest = _cog(monkeypatch)
    wh = MagicMock()
    wh.send = AsyncMock()
    coda = asyncio.Queue()
    await coda.put(("x", "n", "https://x", True))  # veniva da un canale per adulti
    cog._canale = lambda g, c: dest  # il destinatario ora è senza limite d'età
    task = asyncio.create_task(cog._lavora(ch, 2, wh, coda))
    await asyncio.sleep(0.05)
    task.cancel()
    assert wh.send.await_count == 0


async def test_allegati_solo_verso_canali_con_limite_d_eta(monkeypatch):
    cog, ch, msg, dest = _cog(monkeypatch)
    allegato = MagicMock()
    allegato.url = "https://cdn.discordapp.com/attachments/1/2/a.png"
    msg.attachments, msg.content = [allegato], "ciao"
    await cog._inoltra(msg, ch)
    assert "cdn.discordapp" not in ch.code[2].get_nowait()[0]
    dest.is_nsfw.return_value = True
    cog._pausa = tl.PausaUtenti()
    await cog._inoltra(msg, ch)
    testo, _, _, solo_adulti = ch.code[2].get_nowait()
    assert "cdn.discordapp" in testo and solo_adulti


def test_nome_non_torna_discord_dopo_la_pulizia():
    assert "discord" not in tl.pulisci_nome("disdiscordcord").lower()
    assert "clyde" not in tl.nome_mittente("cclydelyde", "Server").lower()


def test_testo_su_minori():
    assert tl.testo_su_minori("cerco una teen di 13 anni")
    assert not tl.testo_su_minori("ciao a tutti, che bella giornata")


async def test_vecchio_squillo_non_collega_un_altro_server():
    c = tl.Centralino(rng=random.Random(1))
    await c.suona(1, [2], {1: 10, 2: 20, 3: 30}, "nessuno", 5)
    await c.annulla_squillo(1)
    await c.suona(1, [3], {1: 10, 2: 20, 3: 30}, "nessuno", 5)
    assert await c.risposto(1, 2) is None  # il bottone vecchio del server 2
    assert await c.annulla_squillo(1, 2) is None
    assert (await c.risposto(1, 3)).b == 3
