"""
tests/test_desktop_prog_cli.py
==============================
SPEC D.1-D.11 (#108): i comandi del programma, con servizio e client Discord finti.
"""

from threading import Event
from types import SimpleNamespace

import pytest

from desktop.iyokai_desktop import cli
from desktop.iyokai_desktop.impostazioni import Impostazioni
from desktop.iyokai_desktop.servizio import ErroreServizio

APP = "123456789012345678"


class _Servizio:
    def __init__(self, base, codice):
        self.base, self.codice = base, codice
        self.staff = []

    def io(self):
        if self.codice == "cattivo":
            raise ErroreServizio("token_non_valido", 401)
        return {}

    def eventi(self, dopo=0, tipo=None, attesa=0, limite=50):
        return [{"id": 1, "tipo": "menzione", "autore": "Ann", "canale": "gen", "testo": "ciao", "quando": "2026-10-28T10:00:00", "link": "https://discord.com/channels/1/2/3"}]

    def storico(self):
        return {"comandi": [{"comando": "promemoria crea", "quando": "2026-10-28T10:00:00"}], "azioni": []}

    def server(self):
        return [{"nome": "Casa", "staff": True, "pannello": "https://p.example/server/1"}]

    def staff_azione(self, server, azione, **dati):
        self.staff.append((server, azione, dati))
        return "ok" if dati.get("minuti", 1) < 100 else "nessun_permesso"

    def staff_azioni(self, server):
        return [{"quando": "2026-10-28T10:00:00", "azione": "timeout", "dettaglio": "x", "esito": "ok"}]

    def traduci(self, testo, lingua):
        return f"[{lingua}]{testo}"

    def risposte(self):
        return [{"nome": "ciao", "testo": "Ciao!"}]

    def radio(self):
        return {"attiva": True, "titolo": "Brano", "numero": 1, "totale": 2}


class _Cliente:
    visti = []

    def __init__(self, app_id):
        self.app_id = app_id

    def connetti(self):
        return {}

    def imposta_attivita(self, a):
        _Cliente.visti.append(a)


@pytest.fixture
def ambiente(tmp_path):
    imp = Impostazioni(tmp_path)
    imp.imposta_servizio("https://p.example")
    imp.imposta_app_id(APP)
    imp.salva_codice("buono")
    _Cliente.visti = []
    out = []

    def esegui(*argv, **k):
        return cli.main(list(argv), uscita=out.append, impostazioni=imp, servizio_di=_Servizio, cliente_di=_Cliente, **k)

    return SimpleNamespace(run=esegui, out=out, imp=imp)


def test_configura_e_collega(tmp_path):
    imp, out = Impostazioni(tmp_path), []

    def run(*argv, codice="buono"):
        return cli.main(list(argv), uscita=out.append, impostazioni=imp, servizio_di=_Servizio, cliente_di=_Cliente, chiedi_codice=lambda _: codice)

    assert run("collega") == 1 and "Manca l'indirizzo" in out[-1]
    assert run("configura", "--servizio", "https://p.example", "--app-id", APP, "--lingua", "en") == 0
    assert run("collega", codice="cattivo") == 1 and "invalid or revoked" in out[-1] and imp.codice() is None
    assert run("collega") == 0 and imp.codice() == "buono"
    assert run("scollega") == 0 and imp.codice() is None
    assert run("configura", "--servizio", "http://p.example") == 1


def test_senza_collegamento(tmp_path):
    out = []
    imp = Impostazioni(tmp_path)
    imp.imposta_servizio("https://p.example")
    assert cli.main(["server"], uscita=out.append, impostazioni=imp, servizio_di=_Servizio) == 1 and "Non sei collegato" in out[-1]


def test_presenza_profili_rotazione(ambiente):
    assert ambiente.run("presenza", "--details", "Ciao mondo", "--bottone", "Sito|https://x.example") == 0
    assert _Cliente.visti[-1] == {"details": "Ciao mondo", "buttons": [{"label": "Sito", "url": "https://x.example"}]}
    assert ambiente.run("presenza", "--ferma") == 0 and _Cliente.visti[-1] is None
    assert ambiente.run("profilo", "salva", "uno", "--details", "Stato uno") == 0
    assert ambiente.run("profilo", "salva", "due", "--details", "Stato due") == 0
    ambiente.run("profilo", "elenco")
    assert ambiente.out[-1] == "due\nuno"
    assert ambiente.run("presenza", "--profilo", "uno") == 0 and _Cliente.visti[-1]["details"] == "Stato uno"
    assert ambiente.run("presenza", "--profilo", "no") == 1
    ferma = Event()
    ferma.set()
    assert ambiente.run("rotazione", "uno", "due", "--ogni", "20", fermati=ferma) == 0
    assert ambiente.run("rotazione", "uno", "due", "--ogni", "5") == 1 and "intervallo_troppo_corto" in ambiente.out[-1]
    assert ambiente.run("profilo", "elimina", "uno") == 0 and ambiente.out[-1] == "ok"
    assert ambiente.run("presenza", "--details", "x") == 1  # testo troppo corto


def test_presenza_senza_app_id(tmp_path):
    out = []
    imp = Impostazioni(tmp_path)
    assert cli.main(["presenza", "--details", "Ciao"], uscita=out.append, impostazioni=imp, cliente_di=_Cliente) == 1
    assert "ID dell'applicazione" in out[-1]


def test_menzioni_storico_server_radio(ambiente, monkeypatch):
    assert ambiente.run("menzioni") == 0 and "Ann ti ha menzionato in #gen: ciao" in ambiente.out[-1]
    aperti = []
    monkeypatch.setattr(cli.notifiche.webbrowser, "open", lambda u: aperti.append(u) or True)
    assert ambiente.run("menzioni", "--apri", "1") == 0 and aperti == ["https://discord.com/channels/1/2/3"]
    assert ambiente.run("menzioni", "--apri", "9") == 0 and "Niente da fare" in ambiente.out[-1]
    ambiente.run("storico")
    assert "promemoria crea" in ambiente.out[-2]
    ambiente.run("server")
    assert ambiente.out[-1] == "Casa  iYokai  staff  https://p.example/server/1"
    ambiente.run("radio")
    assert ambiente.out[-1] == "Brano (1/2)"


def test_traduzione_e_risposte(ambiente, monkeypatch):
    ambiente.run("traduci", "Ciao", "--lingua", "es")
    assert ambiente.out[-1] == "[es]Ciao"
    ambiente.run("risposte")
    assert ambiente.out[-1] == "ciao: Ciao!"
    scritto = []
    monkeypatch.setattr(cli.appunti, "scrivi", lambda t, **k: scritto.append(t))
    assert ambiente.run("incolla", "ciao") == 0 and scritto == ["Ciao!"]
    assert ambiente.run("incolla", "no") == 1


def test_staff(ambiente):
    assert ambiente.run("staff", "blocca", "5", "77") == 0 and ambiente.out[-1] == "Fatto."
    assert ambiente.run("staff", "timeout", "5", "9", "10", "--motivo", "spam") == 0
    assert ambiente.run("staff", "timeout", "5", "9", "500") == 1 and "permesso" in ambiente.out[-1]
    assert ambiente.run("staff", "annuncio", "5", "77", "Ciao a tutti") == 0
    assert ambiente.run("staff", "timeout", "5", "x", "y") == 1 and "Dati non validi" in ambiente.out[-1]
    assert ambiente.run("staff", "azioni", "5") == 0 and "timeout x -> ok" in ambiente.out[-1]


def test_avanzate_sono_da_attivare(ambiente):
    assert ambiente.run("avanzate") == 0
    assert any("rpc.notifications.read" in r for r in ambiente.out) and "Da attivare" in ambiente.out[-1]
