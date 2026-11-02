"""
core/immagini_sandbox.py
========================
Esegue l'analisi di un'immagine in quarantena in un processo NUOVO per ogni immagine (D62), con
tetti di memoria (512 MiB), tempo di CPU (4 s) e tempo vero (8 s, poi SIGKILL), niente file
scrivibili e al massimo 6 MiB di uscita. Modo A: servizio di sistema `iyokai-sandbox` su socket
Unix (utente senza permessi, niente rete). Modo B (ripiego, «sandbox ridotta»): stesso processo
figlio avviato dal bot, con `unshare -rn` se il sistema lo permette. Ucciso, scaduto o illeggibile
= sospetta: lo decide chi chiama.
Funzioni coperte: SPEC §6 (D62)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import resource
import shutil
import signal
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("iyokai.immagini.sandbox")

MODO_SERVIZIO = "servizio"
MODO_RIDOTTA = "ridotta"
SOCKET_SERVIZIO = "/run/iyokai-sbx/sock"
VARIABILE_SOCKET = "IYOKAI_SANDBOX_SOCKET"
MAX_USCITA = 6 * 1024 * 1024
NOME = re.compile(r"^[0-9a-f]{32}$")
WORKER = Path(__file__).resolve().with_name("immagini_worker.py")


@dataclass(frozen=True)
class Limiti:
    memoria: int = 512 * 1024 * 1024
    cpu: int = 4
    reale: float = 8.0
    file_aperti: int = 32


@dataclass
class RisultatoSandbox:
    """`esito`: ok, errore (il decoder ha rifiutato), ucciso_tempo, ucciso (memoria o crash), uscita_enorme, non_disponibile."""

    esito: str
    info: dict = field(default_factory=dict)
    png: bytes = b""
    modo: str = MODO_RIDOTTA

    @property
    def riuscita(self) -> bool:
        return self.esito == "ok"


def _imposta_limiti(limiti: Limiti):
    def pre() -> None:
        signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
        resource.setrlimit(resource.RLIMIT_AS, (limiti.memoria, limiti.memoria))
        resource.setrlimit(resource.RLIMIT_CPU, (limiti.cpu, limiti.cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (limiti.file_aperti, limiti.file_aperti))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()

    return pre


_unshare_ok: bool | None = None


async def _unshare_funziona() -> bool:
    """`unshare -rn` toglie la rete al figlio; su alcuni sistemi (AppArmor) non e' permesso."""
    global _unshare_ok
    if _unshare_ok is None:
        _unshare_ok = False
        if shutil.which("unshare"):
            try:
                p = await asyncio.create_subprocess_exec(
                    "unshare", "-rn", "true", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
                )
                _unshare_ok = (await asyncio.wait_for(p.wait(), 5)) == 0
            except (OSError, asyncio.TimeoutError):
                _unshare_ok = False
    return _unshare_ok


def comando_worker(nome: str) -> list[str]:
    return [sys.executable, "-I", "-B", str(WORKER), nome]


def leggi_uscita(grezzo: bytes) -> tuple[dict, bytes]:
    """Scompone `lunghezza + JSON + lunghezza + PNG`. ValueError se non torna."""
    try:
        n = struct.unpack(">I", grezzo[:4])[0]
        info = json.loads(grezzo[4 : 4 + n])
        m = struct.unpack(">I", grezzo[4 + n : 8 + n])[0]
        png = grezzo[8 + n : 8 + n + m]
        if len(png) != m or not isinstance(info, dict):
            raise ValueError("uscita incompleta")
        return info, png
    except (struct.error, json.JSONDecodeError, UnicodeDecodeError) as errore:
        raise ValueError("uscita illeggibile") from errore


async def esegui_locale(
    nome: str, limiti: Limiti | None = None, comando: list[str] | None = None, isola_rete: bool = True
) -> RisultatoSandbox:
    """Avvia il figlio con i limiti e ne legge l'esito. `comando` serve solo ai test."""
    limiti = limiti or Limiti()
    if not NOME.fullmatch(nome):
        raise ValueError("nome di quarantena non valido")
    argv = comando or comando_worker(nome)
    if isola_rete and comando is None and await _unshare_funziona():
        argv = ["unshare", "-rn", *argv]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            preexec_fn=_imposta_limiti(limiti),
            env={"PATH": os.environ.get("PATH", ""), "IYOKAI_QUARANTENA_DIR": os.environ.get("IYOKAI_QUARANTENA_DIR", "")},
        )
    except OSError:
        logger.exception("Sandbox: processo non avviabile")
        return RisultatoSandbox("non_disponibile")

    async def leggi() -> bytes | None:
        pezzi, totale = [], 0
        while True:
            blocco = await proc.stdout.read(65536)
            if not blocco:
                return b"".join(pezzi)
            totale += len(blocco)
            if totale > MAX_USCITA:
                return None
            pezzi.append(blocco)

    def uccidi() -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()

    async def leggi_e_attendi() -> tuple[bytes | None, int | None]:
        # Anche l'attesa della fine sta nel tempo vero: un figlio che chiude stdout e resta vivo non blocca la coda.
        grezzo = await leggi()
        return grezzo, (await proc.wait() if grezzo is not None else None)

    try:
        grezzo, codice = await asyncio.wait_for(leggi_e_attendi(), limiti.reale)
    except asyncio.TimeoutError:
        uccidi()
        await proc.wait()
        return RisultatoSandbox("ucciso_tempo")
    if grezzo is None:
        uccidi()
        await proc.wait()
        return RisultatoSandbox("uscita_enorme")
    if codice != 0 or not grezzo:
        return RisultatoSandbox("ucciso")
    try:
        info, png = leggi_uscita(grezzo)
    except ValueError:
        return RisultatoSandbox("errore", {"motivo": "uscita_illeggibile"})
    if info.get("esito") == "non_disponibile":
        logger.error("Sandbox: il processo figlio non trova Pillow (interprete sbagliato?)")
        return RisultatoSandbox("non_disponibile", info)
    return RisultatoSandbox("ok" if info.get("esito") == "ok" else "errore", info, png)


def socket_servizio() -> str:
    return os.environ.get(VARIABILE_SOCKET) or SOCKET_SERVIZIO


async def _chiedi_al_servizio(nome: str, limiti: Limiti) -> RisultatoSandbox | None:
    """Modo A: il servizio di sistema. None solo se non c'e' o non accetta il lavoro (si passa al modo B)."""
    percorso = socket_servizio()
    if not os.path.exists(percorso):
        return None
    try:
        lettore, scrittore = await asyncio.wait_for(asyncio.open_unix_connection(percorso), 2.0)
    except (OSError, asyncio.TimeoutError):
        return None
    try:
        scrittore.write(nome.encode("ascii") + b"\n")
        await scrittore.drain()
    except OSError:
        scrittore.close()
        return None
    # Da qui il servizio ha il lavoro: se tace o risponde male l'esito e' sospetto. Rifare la stessa immagine
    # nella sandbox ridotta darebbe all'attacco un secondo tentativo con meno isolamento.
    try:
        grezzo = await asyncio.wait_for(lettore.read(MAX_USCITA + 65536), limiti.reale + 5.0)
        # lettore.read puo' dare meno del totale: si legge fino alla chiusura
        while True:
            altro = await asyncio.wait_for(lettore.read(MAX_USCITA + 65536), 2.0)
            if not altro:
                break
            grezzo += altro
            if len(grezzo) > MAX_USCITA + 65536:
                return RisultatoSandbox("uscita_enorme", modo=MODO_SERVIZIO)
        info, png = leggi_uscita(grezzo)
        return RisultatoSandbox(str(info.get("stato", "errore")), info.get("info") or {}, png, MODO_SERVIZIO)
    except asyncio.TimeoutError:
        logger.warning("Sandbox: il servizio non ha risposto in tempo")
        return RisultatoSandbox("ucciso_tempo", modo=MODO_SERVIZIO)
    except (OSError, ValueError):
        logger.warning("Sandbox: il servizio non ha risposto bene", exc_info=True)
        return RisultatoSandbox("errore", {"motivo": "servizio"}, modo=MODO_SERVIZIO)
    finally:
        scrittore.close()


async def analizza(nome: str, limiti: Limiti | None = None) -> RisultatoSandbox:
    """Modo A se il servizio risponde, altrimenti modo B (sandbox ridotta, dichiarata nel log da chi chiama)."""
    limiti = limiti or Limiti()
    if not NOME.fullmatch(nome):
        raise ValueError("nome di quarantena non valido")
    risultato = await _chiedi_al_servizio(nome, limiti)
    if risultato is not None:
        return risultato
    risultato = await esegui_locale(nome, limiti)
    risultato.modo = MODO_RIDOTTA
    return risultato
