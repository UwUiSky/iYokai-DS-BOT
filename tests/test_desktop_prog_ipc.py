"""
tests/test_desktop_prog_ipc.py
==============================
SPEC D.1, D.2 (#108): collegamento locale con un finto client Discord su socket Unix vero.
"""

import socket
import struct
import sys
import threading

import pytest

from desktop.iyokai_desktop import ipc

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="socket Unix")


class _FintoDiscord:
    def __init__(self, cartella, risposta_handshake=None, errore_attivita=False):
        self.percorso = str(cartella / "discord-ipc-0")
        self.ricevuti = []
        self._hs = risposta_handshake or {"cmd": "DISPATCH", "evt": "READY", "data": {"user": {"id": "1"}}}
        self._errore = errore_attivita
        self._s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._s.bind(self.percorso)
        self._s.listen(1)
        threading.Thread(target=self._servi, daemon=True).start()

    def _servi(self):
        c, _ = self._s.accept()
        with c:
            try:
                while True:
                    op, dati = ipc.leggi_frame(c)
                    self.ricevuti.append((op, dati))
                    if op == ipc.OP_HANDSHAKE:
                        c.sendall(ipc.codifica(ipc.OP_FRAME, self._hs))
                    elif dati.get("cmd") == "SET_ACTIVITY":
                        c.sendall(ipc.codifica(ipc.OP_PING, {"n": 1}))
                        if self._errore:
                            c.sendall(ipc.codifica(ipc.OP_FRAME, {"evt": "ERROR", "data": {"message": "no"}}))
                        else:
                            c.sendall(ipc.codifica(ipc.OP_FRAME, {"cmd": "SET_ACTIVITY", "evt": None, "data": {}}))
            except (ipc.ErroreIPC, OSError):
                pass

    def chiudi(self):
        self._s.close()


def test_percorsi_per_sistema():
    assert ipc.percorsi_candidati({"XDG_RUNTIME_DIR": "/run/u/1"}, "linux")[0] == "/run/u/1/discord-ipc-0"
    assert any("snap.discord" in p for p in ipc.percorsi_candidati({}, "linux"))
    assert ipc.percorsi_candidati({}, "win32")[0] == r"\\?\pipe\discord-ipc-0"


def test_frame_e_limiti():
    dati = ipc.codifica(1, {"a": 1})
    assert struct.unpack("<II", dati[:8]) == (1, len(dati) - 8)

    class Finto:
        def __init__(self, b):
            self.b = b

        def recv(self, n):
            r, self.b = self.b[:n], self.b[n:]
            return r

    assert ipc.leggi_frame(Finto(dati)) == (1, {"a": 1})
    with pytest.raises(ipc.ErroreIPC, match="frame_troppo_grande"):
        ipc.leggi_frame(Finto(struct.pack("<II", 1, ipc.MAX_FRAME + 1)))
    with pytest.raises(ipc.ErroreIPC, match="frame_non_valido"):
        ipc.leggi_frame(Finto(struct.pack("<II", 1, 3) + b"{x}"))
    with pytest.raises(ipc.ErroreIPC, match="canale_chiuso"):
        ipc.leggi_frame(Finto(b""))


@pytest.mark.parametrize("brutto", ["", "abc", None])
def test_client_id_non_valido(brutto):
    with pytest.raises(ipc.ErroreIPC, match="client_id_non_valido"):
        ipc.ClienteIPC(brutto)


def test_connessione_e_stato(tmp_path):
    d = _FintoDiscord(tmp_path)
    c = ipc.ClienteIPC("123456789012345678", [d.percorso])
    assert c.connetti() == {"user": {"id": "1"}}
    risposta = c.imposta_attivita({"details": "ciao"}, pid=42)
    assert risposta["cmd"] == "SET_ACTIVITY"  # il ping di Discord è stato risposto in mezzo
    c.imposta_attivita(None, pid=42)
    c.chiudi()
    hs = d.ricevuti[0]
    assert hs == (ipc.OP_HANDSHAKE, {"v": 1, "client_id": "123456789012345678"})
    attivita = [dati for _, dati in d.ricevuti if dati.get("cmd") == "SET_ACTIVITY"]
    assert attivita[0]["args"] == {"pid": 42, "activity": {"details": "ciao"}} and attivita[1]["args"]["activity"] is None
    d.chiudi()


def test_discord_assente_o_rifiuta(tmp_path):
    with pytest.raises(ipc.ErroreIPC, match="discord_non_trovato"):
        ipc.ClienteIPC("123456789012345678", [str(tmp_path / "niente")]).connetti()
    d = _FintoDiscord(tmp_path, risposta_handshake={"evt": "ERROR"})
    with pytest.raises(ipc.ErroreIPC, match="rifiutato"):
        ipc.ClienteIPC("123456789012345678", [d.percorso]).connetti()
    d.chiudi()


def test_errore_di_discord_e_non_connesso(tmp_path):
    with pytest.raises(ipc.ErroreIPC, match="non_connesso"):
        ipc.ClienteIPC("123456789012345678", []).imposta_attivita({})
    d = _FintoDiscord(tmp_path, errore_attivita=True)
    c = ipc.ClienteIPC("123456789012345678", [d.percorso])
    c.connetti()
    with pytest.raises(ipc.ErroreIPC, match="discord_rifiuta: no"):
        c.imposta_attivita({"details": "x"})
    c.chiudi()
    d.chiudi()
