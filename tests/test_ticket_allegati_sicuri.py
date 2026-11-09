"""
tests/test_ticket_allegati_sicuri.py
====================================
Allegati dei ticket (D61, D62, #152): nomi puliti nel transcript, solo link del CDN di Discord nelle risposte
standard, immagini ricaricate solo ricodificate (sospette, non analizzate e file travestiti restano fuori).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import core.immagini_pipeline as pipeline
from cogs.tickets.risposte import RisposteStandardCog
from core.immagini_byte_logic import PULITA
from core.immagini_pipeline import EsitoImmagine
from core.repositories import ticket_standard_repo as repo
from core.ticket_logic import format_transcript_line
from tests.support import immagini_finte as f


def test_il_transcript_non_porta_caratteri_di_controllo_ne_percorsi_nei_nomi():
    riga = format_transcript_line("12:00", "Mario", "x", ["../../a\r\n[fake].png", 'b"<i>.png'])
    assert "\n" not in riga and "\r" not in riga and "../" not in riga and '"' not in riga and "<" not in riga
    assert "[allegati: a[fake].png, bi.png]" in riga


def test_risposte_standard_tengono_solo_link_del_cdn_di_discord():
    cdn = "https://cdn.discordapp.com/attachments/1/2/a.png"
    voci = [
        {"filename": "a\n.png", "url": cdn},
        {"filename": "b.png", "url": "https://evil.example/b.png"},
        {"filename": "c.png", "url": "http://cdn.discordapp.com/c.png"},
        {"filename": "d.png", "url": "https://cdn.discordapp.com.evil.example/d.png"},
        "non un dizionario",
    ]
    assert repo.allegati_validi(voci) == [{"filename": "a.png", "url": cdn}]
    assert repo.allegati_validi(None) == [] and len(repo.allegati_validi([voci[0]] * 50)) == repo.MAX_ALLEGATI


class _Allegato:
    def __init__(self, nome, dati, tipo=None):
        self.filename, self.content_type, self.size, self._dati = nome, tipo, len(dati), dati

    async def read(self):
        return self._dati


def _messaggio(*allegati):
    return SimpleNamespace(attachments=list(allegati), guild=SimpleNamespace(id=9))


@pytest.mark.asyncio
async def test_copie_per_la_risposta_standard_solo_ricodificate(monkeypatch):
    async def analisi(dati, nome, ct, guild_id):
        return EsitoImmagine(PULITA, "s", png=b"PNG-NUOVO")

    monkeypatch.setattr(pipeline, "analizza_immagine", analisi)
    file = await RisposteStandardCog._copie_allegati(_messaggio(
        _Allegato("foto.jpg", f.jpeg()),
        _Allegato("finta.png", b"<html><script>1</script></html>", "image/png"),
        _Allegato("guida.pdf", b"%PDF-1.4 x"),
    ))
    assert [x.filename for x in file] == ["foto.png", "guida.pdf"]
    assert file[0].fp.read() == b"PNG-NUOVO"


@pytest.mark.asyncio
async def test_immagine_sospetta_non_arriva_nel_canale_dei_log(monkeypatch):
    monkeypatch.setattr(pipeline, "analizza_immagine", AsyncMock(return_value=EsitoImmagine("malevola", "s", ("x",))))
    assert await RisposteStandardCog._copie_allegati(_messaggio(_Allegato("a.png", f.png()))) == []
