"""
desktop/iyokai_desktop/ipc.py
=============================
Collegamento locale con il client Discord (IPC): `discord-ipc-N` su socket Unix o pipe di Windows. Serve la
rich presence (stato «sta giocando a…»), permessa a tutti. Gli altri comandi RPC (notifiche del client, voce)
richiedono l'approvazione di Discord e qui non ci sono (vedi `rpc_avanzato.py`).
Funzioni coperte: SPEC D.1, D.2
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import uuid

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4
MAX_FRAME = 64 * 1024
INTESTAZIONE = struct.Struct("<II")
PROVE = 10  # discord-ipc-0 … discord-ipc-9


class ErroreIPC(Exception):
    """Il client Discord non c'è, non risponde o ha rifiutato."""


def percorsi_candidati(ambiente: dict | None = None, piattaforma: str | None = None) -> list[str]:
    """Dove può stare il canale del client Discord (normale, snap, flatpak, pipe di Windows)."""
    ambiente = os.environ if ambiente is None else ambiente
    piattaforma = piattaforma or sys.platform
    if piattaforma.startswith("win"):
        return [rf"\\?\pipe\discord-ipc-{n}" for n in range(PROVE)]
    cartelle = [ambiente.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")] + ["/tmp"]
    cartelle = list(dict.fromkeys(c for c in cartelle if c))
    percorsi = []
    for n in range(PROVE):
        for c in cartelle:
            percorsi += [f"{c}/discord-ipc-{n}", f"{c}/snap.discord/discord-ipc-{n}", f"{c}/app/com.discordapp.Discord/discord-ipc-{n}"]
    return percorsi


def codifica(opcode: int, dati: dict) -> bytes:
    corpo = json.dumps(dati, separators=(",", ":")).encode("utf-8")
    return INTESTAZIONE.pack(opcode, len(corpo)) + corpo


def _leggi_esatto(canale, n: int) -> bytes:
    pezzi = b""
    while len(pezzi) < n:
        pezzo = canale.recv(n - len(pezzi))
        if not pezzo:
            raise ErroreIPC("canale_chiuso")
        pezzi += pezzo
    return pezzi


def leggi_frame(canale) -> tuple[int, dict]:
    """Un messaggio dal client: (opcode, dati). Lunghezze assurde o testo storto = ErroreIPC."""
    opcode, lunghezza = INTESTAZIONE.unpack(_leggi_esatto(canale, INTESTAZIONE.size))
    if lunghezza > MAX_FRAME:
        raise ErroreIPC("frame_troppo_grande")
    try:
        return opcode, json.loads(_leggi_esatto(canale, lunghezza) or b"{}")
    except ValueError as errore:
        raise ErroreIPC("frame_non_valido") from errore


class _CanaleWindows:
    """La pipe di Windows come file binario senza buffer."""

    def __init__(self, percorso: str) -> None:
        self._f = open(percorso, "r+b", buffering=0)  # noqa: SIM115 - chiuso da chiudi()

    def sendall(self, dati: bytes) -> None:
        self._f.write(dati)

    def recv(self, n: int) -> bytes:
        return self._f.read(n)

    def close(self) -> None:
        self._f.close()


def apri_canale(percorso: str):
    if sys.platform.startswith("win"):
        return _CanaleWindows(percorso)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect(percorso)
    except OSError:
        s.close()
        raise
    return s


class ClienteIPC:
    """`client_id`: l'ID pubblico dell'applicazione Discord della rich presence (non è un segreto)."""

    def __init__(self, client_id: str, percorsi: list[str] | None = None, apri=apri_canale) -> None:
        if not client_id or not client_id.isdigit():
            raise ErroreIPC("client_id_non_valido")
        self.client_id = client_id
        self._percorsi = percorsi
        self._apri = apri
        self._canale = None

    def connetti(self) -> dict:
        """Si presenta al client Discord. Ritorna i dati dell'evento READY (l'utente collegato)."""
        for percorso in self._percorsi if self._percorsi is not None else percorsi_candidati():
            try:
                canale = self._apri(percorso)
            except OSError:
                continue
            try:
                canale.sendall(codifica(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id}))
                opcode, dati = leggi_frame(canale)
            except (OSError, ErroreIPC):
                canale.close()
                continue
            if opcode == OP_CLOSE or dati.get("evt") != "READY":
                canale.close()
                raise ErroreIPC("rifiutato")
            self._canale = canale
            return dati.get("data", {})
        raise ErroreIPC("discord_non_trovato")

    def imposta_attivita(self, attivita: dict | None, pid: int | None = None) -> dict:
        """`attivita` None toglie lo stato. Ritorna la risposta di Discord."""
        if self._canale is None:
            raise ErroreIPC("non_connesso")
        richiesta = {
            "cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
            "args": {"pid": pid if pid is not None else os.getpid(), "activity": attivita},
        }
        try:
            self._canale.sendall(codifica(OP_FRAME, richiesta))
            while True:
                opcode, dati = leggi_frame(self._canale)
                if opcode == OP_PING:
                    self._canale.sendall(codifica(OP_PONG, dati))
                    continue
                if opcode == OP_CLOSE:
                    raise ErroreIPC("chiuso_da_discord")
                break
        except OSError as errore:
            self.chiudi()
            raise ErroreIPC("canale_chiuso") from errore
        if dati.get("evt") == "ERROR":
            raise ErroreIPC("discord_rifiuta: " + str(dati.get("data", {}).get("message", ""))[:200])
        return dati

    def chiudi(self) -> None:
        canale, self._canale = self._canale, None
        if canale is not None:
            try:
                canale.close()
            except OSError:
                pass
