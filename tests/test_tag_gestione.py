"""
tests/test_tag_gestione.py
==========================
D69 B21 (UTL-034, 035, 039, 040, 041, 042): tag propri (modifica, elimina, prendi), sostituzione di un testo con
anteprima, pacchetti con codice (7 giorni) o file, gruppi con regole di canale e ruolo. Archivio su PostgreSQL vero.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.custom_commands as usi
from core.repositories.custom_command_repo import CustomCommandRepository
from core.tag_pacchetti_logic import PacchettoErrato, leggi_pacchetto, nome_gruppo_valido, nuovo_codice, pacchetto_da_tag, pacchetto_in_file
from tests.support.discord_fakes import fake_member


@pytest.fixture
def repo(clean_db):
    return CustomCommandRepository(pool_provider=lambda: clean_db)


async def _crea(repo, guild, nome, testo="Testo", autore=7):
    return await repo.create_tag(guild, nome, response=testo, use_embed=False, role_id=None, role_action="nessuna",
                                 cooldown_seconds=0, ping_ruoli=False, created_by=autore)


def test_pacchetto_andata_e_ritorno_senza_ruoli_ne_canali():
    t = SimpleNamespace(name="regole", response="Ciao", cooldown_seconds=5, permesso="ban_members", invio="altro", reazioni=["👍"],
                        si_cancella_dopo=30, cancella_messaggi=None, gruppo="g", use_embed=True, bersaglio=False,
                        cancella_innesco=True, solo_nsfw=False, anche_modificati=False, role_id=99, canale_id=5)
    dati = pacchetto_da_tag([t], {"regole": [(3, "a"), (1, "b")]})
    assert "role_id" not in json.dumps(dati) and "canale_id" not in json.dumps(dati)
    [v] = leggi_pacchetto(pacchetto_in_file(dati))
    assert v["nome"] == "regole" and v["invio"] == "canale" and v["permesso"] == "ban_members" and v["risposte"] == [(3, "a"), (1, "b")]
    assert v["reazioni"] == ["👍"] and v["use_embed"] is True and v["cancella_innesco"] is True and v["gruppo"] == "g"


def test_pacchetto_scarta_le_righe_sbagliate():
    sporco = {"tag": [1, {"nome": "Bello Nome"}, {"nome": "ok", "testo": "x" * 4001}, {"nome": "ok", "testo": "va", "permesso": "root", "pausa": -4,
                                                                                         "si_cancella_dopo": 2, "invio": "altro", "risposte": [[0, "x"], [2, "y"]]},
              {"nome": "ok", "testo": "doppio"}]}
    [v] = leggi_pacchetto(sporco)
    assert v["permesso"] is None and v["pausa"] == 0 and v["si_cancella_dopo"] is None and v["invio"] == "canale" and v["risposte"] == [(2, "y")]
    for brutto in (b"no", b"[]", json.dumps({"tag": []}), b"x" * (1024 * 1024 + 1)):
        with pytest.raises(PacchettoErrato):
            leggi_pacchetto(brutto)
    assert len(nuovo_codice()) == 8 and nome_gruppo_valido(" Ciao_1 ") == "ciao_1" and nome_gruppo_valido("a b") is None


@pytest.mark.asyncio
async def test_tag_propri_modifica_elimina_e_prendi(repo):
    await _crea(repo, 1, "mio", autore=7)
    assert await repo.conta_di(1, 7) == 1 and await repo.nomi_di(1, 7, "mi") == ["mio"] and await repo.nomi_di(1, 8, "mi") == []
    assert await repo.delete_tag_di(1, "mio", 8) is False and await repo.delete_tag_di(1, "mio", 7) is True
    await _crea(repo, 1, "orfano", autore=7)
    assert await repo.prendi(1, "orfano", 9, lambda uid: True) == "autore_presente"
    assert await repo.prendi(1, "orfano", 7, lambda uid: False) == "tuo"
    assert await repo.prendi(1, "orfano", 9, lambda uid: False) == "ok" and (await repo.get_tag(1, "orfano")).created_by == 9
    assert await repo.prendi(1, "assente", 9, lambda uid: False) == "non_esiste"


@pytest.mark.asyncio
async def test_sostituisci_con_anteprima_e_tetto(repo):
    await _crea(repo, 1, "a", "vai su example.com ora")
    await _crea(repo, 1, "b", "niente")
    await _crea(repo, 1, "c", "x" * 3985 + " example.com")
    assert await repo.sostituisci(1, "example.com", "nuovo-sito-lungo-qui.it", False) == 1  # il terzo non viene toccato se supera i 4000
    assert await repo.sostituisci(1, "example.com", "nuovo-sito-lungo-qui.it", True) == 1
    assert (await repo.get_tag(1, "a")).response == "vai su nuovo-sito-lungo-qui.it ora" and (await repo.get_tag(1, "b")).response == "niente"
    assert await repo.sostituisci(2, "nuovo-sito-lungo-qui.it", "x", True) == 0  # un altro server


@pytest.mark.asyncio
async def test_codice_scade_dopo_sette_giorni_e_importa_salta_i_doppioni(repo, clean_db):
    await _crea(repo, 1, "uno")
    tags, risp = await repo.tutti_con_risposte(1)
    await repo.crea_pacchetto(1, pacchetto_da_tag(tags, risp), 7, "abcd1234")
    dati = await repo.leggi_pacchetto("abcd1234")
    assert dati and await repo.leggi_pacchetto("zzzzzzzz") is None
    await clean_db.execute("UPDATE tag_pacchetti SET scade_il = now() - interval '1 second'")
    assert await repo.leggi_pacchetto("abcd1234") is None
    voci = leggi_pacchetto(dati)
    assert await repo.importa(2, voci, 8) == (1, 0) and await repo.importa(2, voci, 8) == (0, 1)
    assert (await repo.get_tag(2, "uno")).created_by == 8


@pytest.mark.asyncio
async def test_gruppo_regole_di_canale_e_ruolo(repo):
    await repo.imposta_gruppo(1, "staff", 50, 60)
    assert [g["gruppo"] for g in await repo.elenco_gruppi(1)] == ["staff"]
    tag = SimpleNamespace(guild_id=1, gruppo="staff")
    from unittest.mock import patch
    with patch.object(usi, "custom_command_repo", repo):
        membro = fake_member(5)
        membro.guild_permissions = discord.Permissions.none()
        membro.roles = [SimpleNamespace(id=60)]
        assert await usi.CustomCommandsCog._rifiuto_gruppo(tag, membro, SimpleNamespace(id=51)) == "tag_gruppo_canale"
        assert await usi.CustomCommandsCog._rifiuto_gruppo(tag, membro, SimpleNamespace(id=50)) is None
        membro.roles = []
        assert await usi.CustomCommandsCog._rifiuto_gruppo(tag, membro, SimpleNamespace(id=50)) == "tag_gruppo_ruolo"
        assert await usi.CustomCommandsCog._rifiuto_gruppo(SimpleNamespace(guild_id=1, gruppo=None), membro, None) is None
    await _crea(repo, 1, "t")
    await repo.update_tag(1, "t", gruppo="staff")
    assert (await repo.elenco_gruppi(1))[0]["tag"] == 1
    assert await repo.togli_gruppo(1, "staff") is True and (await repo.get_tag(1, "t")).gruppo is None and await repo.togli_gruppo(1, "staff") is False
    await repo.imposta_gruppo(1, "g2", 77, None)
    await repo.canale_cancellato(1, 77)
    assert (await repo.gruppo(1, "g2"))["canale_id"] is None
