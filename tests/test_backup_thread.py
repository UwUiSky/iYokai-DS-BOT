"""
tests/test_backup_thread.py
===========================
Thread pubblici e post dei forum nel backup (BKP-002): lettura, controllo del file, ricarica senza doppioni.
Funzioni coperte: BKP-002
"""

from __future__ import annotations

import discord

from core import backup_struttura_logic as st
from tests.test_backup_struttura import _Guild


class _Thread:
    def __init__(self, tid, nome, archiviato=False, privato=False, primo="ciao"):
        self.id, self.name, self.archived, self.slowmode_delay = tid, nome, archiviato, 0
        self._privato, self._primo = privato, primo
        self.modifiche = []

    def is_private(self):
        return self._privato

    async def fetch_message(self, _id):
        return type("M", (), {"content": self._primo})()

    async def edit(self, **kw):
        self.modifiche.append(kw)


class _Con:
    def __init__(self, nome, tipo, attivi=(), archiviati=()):
        self.id, self.name, self.type = hash(nome) % 10_000, nome, tipo
        self.threads, self._arch = list(attivi), list(archiviati)
        self.creati = []

    async def archived_threads(self, limit=None):
        for t in self._arch[:limit]:
            yield t

    async def create_thread(self, **kw):
        self.creati.append(kw)
        t = _Thread(1, kw["name"])
        self.threads.append(t)
        return type("TM", (), {"thread": t})() if "content" in kw else t


async def test_si_leggono_attivi_e_archiviati_ma_non_i_privati():
    forum = _Con("domande", discord.ChannelType.forum, attivi=[_Thread(1, "Come si fa", primo="Aiuto")],
                 archiviati=[_Thread(2, "Vecchio", archiviato=True)])
    testo = _Con("chat", discord.ChannelType.text, attivi=[_Thread(3, "segreto", privato=True), _Thread(4, "idee")])
    g = _Guild()
    g.channels = [forum, testo]
    righe = await st.leggi_thread(g)
    assert {(r["canale"], r["nome"], r["archiviato"], r["primo"]) for r in righe} == {
        ("domande", "Come si fa", False, "Aiuto"), ("domande", "Vecchio", True, "ciao"), ("chat", "idee", False, None),
    }


def test_file_con_thread_sbagliati_si_rifiuta():
    assert st.valida_struttura({"versione": 1, "thread": [{"canale": "c", "nome": "n", "primo": None}]}) == []
    for sbagliato in ({"canale": "c", "nome": ""}, {"canale": "c", "nome": "n", "primo": "x" * 2001}, "testo"):
        assert st.valida_struttura({"versione": 1, "thread": [sbagliato]})
    assert st.valida_struttura({"versione": 1, "thread": [{"canale": "c", "nome": "n"}] * (st.MAX_THREAD + 1)})
    assert "thread" in st.parti_presenti({"versione": 1, "thread": [{"canale": "c", "nome": "n"}]})
    assert "thread" not in st.senza_dati_personali({"versione": 1, "thread": [{"canale": "c", "nome": "n"}]})


async def test_ricarica_crea_thread_e_post_senza_doppioni_e_senza_menzioni():
    forum = _Con("domande", discord.ChannelType.forum)
    testo = _Con("chat", discord.ChannelType.text, attivi=[_Thread(9, "gia-qui")])
    g = _Guild()
    g.channels = [forum, testo]
    dati = {"versione": 1, "thread": [
        {"canale": "domande", "nome": "Come si fa", "primo": "@everyone aiuto", "archiviato": True},
        {"canale": "chat", "nome": "idee"}, {"canale": "chat", "nome": "gia-qui"}, {"canale": "assente", "nome": "x"},
    ]}

    async def pausa(_s):
        return None

    r = await st.Caricatore(g, dati, {"thread"}, pausa=pausa).esegui()
    assert (r.creati, r.riusati, r.saltati) == (2, 1, 1)
    assert forum.creati[0]["allowed_mentions"].everyone is False and forum.creati[0]["content"] == "@everyone aiuto"
    assert [t.name for t in testo.threads] == ["gia-qui", "idee"]
    assert forum.threads[0].modifiche == [{"archived": True, "reason": st.MOTIVO}]
