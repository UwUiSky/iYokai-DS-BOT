"""
scripts/collaudo.py
===================
Assistente da terminale per le prove dal vivo: propone una per una le voci di
VERIFICA_LIVE.md, salva l'esito e apre un'issue su GitHub per ogni errore.
Uso: `python scripts/collaudo.py` (vedi `collaudo_LEGGIMI.md` e D109).
Funzioni coperte: SPEC §21 (verifica live), #94.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RADICE = Path(__file__).resolve().parent.parent
FILE_PROVE = RADICE / "revisione" / "03-verifica" / "VERIFICA_LIVE.md"
CARTELLA = RADICE / "collaudo"

MAX_TESTO = 4000
MAX_PASSI = 3000
MAX_TITOLO_PASSI = 90
API_GITHUB = "https://api.github.com"
ETICHETTE = ["verifica-live", "bug"]

_RIGA_PROVA = re.compile(r"^- \[( |x|X)\] (.*)$")
_TITOLO = re.compile(r"^(#{2,3}) +(.*?)\s*$")
_REPO_OK = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass
class Prova:
    id: str  # codice, con «~N» se il codice compare più volte
    codice: str
    sezione: str
    passi: str
    fatta: bool  # già spuntata nel file
    riga: int  # numero di riga (da 1) nel file


# ---------------------------------------------------------------- analizzatore


def _estrai_codice(testo: str) -> str:
    m = re.match(r"`([^`]+)`", testo)
    if m:
        return m.group(1).strip()
    testo = re.split(r" — | \(#", testo, maxsplit=1)[0]
    return testo.strip().rstrip(":") or "SENZA-CODICE"


def _pulisci_passi(testo: str) -> str:
    testo = re.sub(r"^`[^`]+`\s*", "", testo)
    testo = re.sub(r"^[—-]\s*", "", testo)
    return re.sub(r"\s+", " ", testo).strip()


def analizza(testo: str) -> list[Prova]:
    """Legge VERIFICA_LIVE.md e ne ricava le prove (righe «- [ ]» e «- [x]»)."""
    righe = testo.splitlines()
    prove: list[Prova] = []
    visti: dict[str, int] = {}
    sezione = ""
    i = 0
    while i < len(righe):
        riga = righe[i]
        t = _TITOLO.match(riga)
        if t:
            sezione = t.group(2)
            i += 1
            continue
        m = _RIGA_PROVA.match(riga)
        if not m:
            i += 1
            continue
        blocco = [m.group(2)]
        j = i + 1
        # righe di continuazione: rientrate (o vuote seguite da righe rientrate)
        while j < len(righe) and righe[j].startswith((" ", "\t")) and righe[j].strip():
            blocco.append(righe[j].strip())
            j += 1
        corpo = " ".join(blocco)
        codice = _estrai_codice(corpo)
        visti[codice] = visti.get(codice, 0) + 1
        id_ = codice if visti[codice] == 1 else f"{codice}~{visti[codice]}"
        prove.append(Prova(id_, codice, sezione, _pulisci_passi(corpo),
                           m.group(1) != " ", i + 1))
        i = j
    return prove


def leggi_prove(percorso: Path = FILE_PROVE) -> list[Prova]:
    return analizza(percorso.read_text(encoding="utf-8"))


def spunta_nel_file(prova: Prova, percorso: Path = FILE_PROVE) -> bool:
    """Cambia «- [ ]» in «- [x]» sulla riga della prova. Non tocca altro."""
    righe = percorso.read_text(encoding="utf-8").splitlines(keepends=True)
    if not (0 < prova.riga <= len(righe)):
        return False
    attuale = righe[prova.riga - 1]
    if not attuale.startswith("- [ ] "):
        return False
    # controllo che sia ancora la stessa prova
    if _estrai_codice(attuale[6:].rstrip("\n")) != prova.codice:
        return False
    righe[prova.riga - 1] = "- [x] " + attuale[6:]
    percorso.write_text("".join(righe), encoding="utf-8")
    return True


def togli_spunta_nel_file(prova: Prova, percorso: Path = FILE_PROVE) -> bool:
    """Il contrario di `spunta_nel_file`: serve a `--ripeti`."""
    righe = percorso.read_text(encoding="utf-8").splitlines(keepends=True)
    if not (0 < prova.riga <= len(righe)):
        return False
    attuale = righe[prova.riga - 1]
    if not attuale.startswith(("- [x] ", "- [X] ")):
        return False
    righe[prova.riga - 1] = "- [ ] " + attuale[6:]
    percorso.write_text("".join(righe), encoding="utf-8")
    return True


# ---------------------------------------------------------------- stato e storico


class Archivio:
    """`stato.json` (codice → esito) e `storico.jsonl` (un evento per riga)."""

    def __init__(self, cartella: Path = CARTELLA, token: str = ""):
        self.cartella = cartella
        self.file_stato = cartella / "stato.json"
        self.file_storico = cartella / "storico.jsonl"
        self._token = token

    def ripulisci(self, testo: str) -> str:
        """Toglie il token da qualunque testo e tronca."""
        testo = str(testo)
        if self._token:
            testo = testo.replace(self._token, "***")
        return testo[:MAX_TESTO]

    def carica(self) -> dict:
        try:
            dati = json.loads(self.file_stato.read_text(encoding="utf-8"))
            return dati if isinstance(dati, dict) else {}
        except (OSError, ValueError):
            return {}

    def salva(self, stato: dict) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        tmp = self.file_stato.with_suffix(".tmp")
        tmp.write_text(json.dumps(stato, ensure_ascii=False, indent=1, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, self.file_stato)

    def evento(self, tipo: str, id_: str, **extra) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        riga = {"data": _adesso(), "evento": tipo, "codice": id_}
        riga.update({k: (self.ripulisci(v) if isinstance(v, str) else v)
                     for k, v in extra.items()})
        with self.file_storico.open("a", encoding="utf-8") as f:
            f.write(json.dumps(riga, ensure_ascii=False) + "\n")

    def imposta(self, id_: str, esito: str, **extra) -> None:
        stato = self.carica()
        voce = {"esito": esito, "data": _adesso()}
        voce.update({k: (self.ripulisci(v) if isinstance(v, str) else v)
                     for k, v in extra.items()})
        stato[id_] = voce
        self.salva(stato)

    def storico(self) -> list[dict]:
        try:
            testo = self.file_storico.read_text(encoding="utf-8")
        except OSError:
            return []
        righe = []
        for r in testo.splitlines():
            try:
                righe.append(json.loads(r))
            except ValueError:
                continue
        return righe


def _adesso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- GitHub


def versione(radice: Path = RADICE) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=radice,
                           capture_output=True, text=True, timeout=5, check=False)
        return r.stdout.strip() or "sconosciuta"
    except (OSError, subprocess.SubprocessError):
        return "sconosciuta"


def titolo_issue(prova: Prova) -> str:
    passi = prova.passi[:MAX_TITOLO_PASSI].rstrip()
    if len(prova.passi) > MAX_TITOLO_PASSI:
        passi += "…"
    return f"Prova live fallita: {prova.codice} — {passi}"


def corpo_issue(prova: Prova, descrizione: str, data: str, ver: str) -> str:
    return (
        f"## Prova live fallita: {prova.codice}\n\n"
        f"**Sezione:** {prova.sezione or '-'}\n\n"
        f"### Passi\n\n{prova.passi[:MAX_PASSI]}\n\n"
        f"### Errore descritto dall'owner\n\n{descrizione[:MAX_TESTO]}\n\n"
        f"---\nData: {data}\nVersione: `{ver}`\n"
        "Aperta da `scripts/collaudo.py`."
    )


def invia_a_github(url: str, token: str, payload: dict) -> dict:
    """POST reale. Alza OSError/ValueError in caso di problemi."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
                 "User-Agent": "iyokai-collaudo"})
    with urllib.request.urlopen(req, timeout=15) as risposta:  # noqa: S310 (host fisso)
        return json.loads(risposta.read().decode("utf-8"))


def crea_issue(prova: Prova, descrizione: str, repo: str, token: str,
               post: Callable[[str, str, dict], dict] = invia_a_github,
               ver: str | None = None) -> tuple[int | None, str]:
    """Crea l'issue. Ritorna (numero, errore): numero None se non riuscita."""
    if not token:
        return None, "GITHUB_TOKEN mancante"
    if not _REPO_OK.match(repo or ""):
        return None, "COLLAUDO_REPO mancante o non valido (serve owner/repo)"
    payload = {"title": titolo_issue(prova),
               "body": corpo_issue(prova, descrizione, _adesso(), ver or versione()),
               "labels": ETICHETTE}
    try:
        risposta = post(f"{API_GITHUB}/repos/{repo}/issues", token, payload)
        numero = int(risposta["number"])
    except urllib.error.HTTPError as e:
        return None, f"GitHub ha risposto {e.code}"
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, f"GitHub non raggiungibile ({type(e).__name__})"
    return numero, ""


# ---------------------------------------------------------------- domande


class Esci(Exception):
    pass


def _chiedi(domanda: str, valide: dict[str, str], leggi: Callable[[str], str]) -> str:
    """Chiede finché la risposta è valida. `valide`: risposta breve → valore."""
    while True:
        try:
            r = leggi(domanda).strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise Esci from None
        if r in valide:
            return valide[r]
        print("Risposta non valida.")


_FATTA = {"s": "si", "si": "si", "sì": "si", "y": "si", "salta": "salta", "n": "salta",
          "esci": "esci", "e": "esci", "q": "esci"}
_SINO = {"s": "si", "si": "si", "sì": "si", "y": "si", "n": "no", "no": "no"}


def _chiedi_descrizione(leggi: Callable[[str], str]) -> str:
    while True:
        try:
            testo = leggi("Descrivi l'errore (una riga): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise Esci from None
        if testo:
            return testo[:MAX_TESTO]
        print("La descrizione non può essere vuota.")


def gestisci_errore(prova: Prova, descrizione: str, arch: Archivio, repo: str,
                    token: str, post=invia_a_github, ver: str | None = None) -> int | None:
    """Salva l'errore e prova a creare l'issue. Il salvataggio viene sempre prima."""
    arch.imposta(prova.id, "errore", sezione=prova.sezione, descrizione=descrizione,
                 issue=None)
    arch.evento("errore", prova.id, sezione=prova.sezione, descrizione=descrizione)
    numero, motivo = crea_issue(prova, descrizione, repo, token, post, ver)
    if numero is None:
        motivo = arch.ripulisci(motivo)
        arch.evento("issue_non_creata", prova.id, motivo=motivo)
        print(f"Issue non creata ({motivo}). L'errore è salvato: usa --invia-in-sospeso.")
        return None
    arch.imposta(prova.id, "errore", sezione=prova.sezione, descrizione=descrizione,
                 issue=numero)
    arch.evento("issue_creata", prova.id, issue=numero)
    print(f"Issue #{numero} creata.")
    return numero


# ---------------------------------------------------------------- flusso


def da_proporre(prove: list[Prova], stato: dict, sezione: str | None = None) -> list[Prova]:
    """Prove non fatte, né nel file né nello stato (le «saltate» tornano)."""
    risultato = []
    for p in prove:
        if p.fatta:
            continue
        if stato.get(p.id, {}).get("esito") in ("superata", "errore"):
            continue
        if sezione and sezione.lower() not in p.sezione.lower():
            continue
        risultato.append(p)
    return risultato


def esegui(prove: list[Prova], arch: Archivio, *, repo: str, token: str,
           file_prove: Path | None = FILE_PROVE, sezione: str | None = None,
           leggi: Callable[[str], str] = input, post=invia_a_github,
           ver: str | None = None) -> None:
    coda = da_proporre(prove, arch.carica(), sezione)
    if not coda:
        print("Nessuna prova da fare.")
        return
    print(f"Prove da fare: {len(coda)}. In ogni momento puoi scrivere «esci».")
    try:
        for n, p in enumerate(coda, 1):
            print(f"\n[{n}/{len(coda)}] {p.codice}  (sezione: {p.sezione or '-'})")
            print(p.passi[:1500])
            scelta = _chiedi("Hai fatto la prova? [s]ì / [n] salta / [e]sci: ", _FATTA, leggi)
            if scelta == "esci":
                break
            if scelta == "salta":
                arch.evento("saltata", p.id)
                continue
            errori = _chiedi("Ci sono stati errori? [s]ì / [n]o: ", _SINO, leggi)
            if errori == "no":
                arch.imposta(p.id, "superata", sezione=p.sezione)
                arch.evento("superata", p.id)
                if file_prove is not None and not spunta_nel_file(p, file_prove):
                    print("(Riga del file non aggiornata: non l'ho trovata.)")
                continue
            gestisci_errore(p, _chiedi_descrizione(leggi), arch, repo, token, post, ver)
    except Esci:
        pass
    print("\nCollaudo interrotto o finito. Riepilogo con --stato.")


def invia_in_sospeso(arch: Archivio, prove: list[Prova], repo: str, token: str,
                     post=invia_a_github, ver: str | None = None) -> int:
    """Crea le issue degli errori salvati senza numero. Ritorna quante ne ha create."""
    per_id = {p.id: p for p in prove}
    create = 0
    for id_, voce in sorted(arch.carica().items()):
        if voce.get("esito") != "errore" or voce.get("issue") is not None:
            continue
        prova = per_id.get(id_) or Prova(id_, id_.split("~")[0], voce.get("sezione", ""),
                                         "(prova non più nel file)", False, 0)
        if gestisci_errore(prova, voce.get("descrizione", ""), arch, repo, token, post,
                           ver) is not None:
            create += 1
    print(f"Issue create: {create}.")
    return create


def ripeti(codice: str, prove: list[Prova], arch: Archivio,
           file_prove: Path | None = FILE_PROVE) -> bool:
    """Rimette in coda una prova: toglie l'esito e, se serve, la spunta nel file."""
    stato = arch.carica()
    prova = next((p for p in prove if p.id == codice), None)
    if codice not in stato and not (prova and prova.fatta):
        print("Quella prova non ha un esito salvato.")
        return False
    stato.pop(codice, None)
    arch.salva(stato)
    if prova and prova.fatta and file_prove is not None:
        togli_spunta_nel_file(prova, file_prove)
    arch.evento("ripetuta", codice)
    print("Prova rimessa in coda.")
    return True


def riepilogo(prove: list[Prova], stato: dict) -> str:
    sezioni: dict[str, dict[str, int]] = {}
    for p in prove:
        s = sezioni.setdefault(p.sezione or "-", {"fatte": 0, "errori": 0, "da fare": 0})
        esito = stato.get(p.id, {}).get("esito")
        if esito == "errore":
            s["errori"] += 1
        elif p.fatta or esito == "superata":
            s["fatte"] += 1
        else:
            s["da fare"] += 1
    tot = {"fatte": 0, "errori": 0, "da fare": 0}
    righe = []
    for nome, c in sezioni.items():
        for k in tot:
            tot[k] += c[k]
        righe.append(f"  {nome[:60]:<60} fatte {c['fatte']:>3}  errori {c['errori']:>3}  "
                     f"da fare {c['da fare']:>3}")
    testata = (f"Totale: fatte {tot['fatte']}, errori {tot['errori']}, "
               f"da fare {tot['da fare']} (su {len(prove)})")
    return "\n".join([testata, *righe])


def testo_storico(eventi: list[dict]) -> str:
    righe = []
    for e in eventi:
        if e.get("evento") in ("errore", "issue_creata", "issue_non_creata"):
            extra = e.get("descrizione") or e.get("motivo") or (
                f"issue #{e['issue']}" if e.get("issue") else "")
            righe.append(f"{e['data']}  {e['evento']:<17} {e['codice']}  {extra}")
    return "\n".join(righe) or "Nessun errore nello storico."


# ---------------------------------------------------------------- avvio


def _carica_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(RADICE / ".env")
    except ImportError:  # pragma: no cover
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Assistente per le prove dal vivo.")
    ap.add_argument("--sezione", help="solo le prove di questa sezione (parte del titolo)")
    ap.add_argument("--stato", action="store_true", help="riepilogo")
    ap.add_argument("--storico", action="store_true", help="elenco degli errori")
    ap.add_argument("--ripeti", metavar="CODICE", help="riproponi una prova")
    ap.add_argument("--invia-in-sospeso", action="store_true",
                    help="crea le issue degli errori non ancora inviati")
    ap.add_argument("--non-modificare", action="store_true",
                    help="non spuntare le righe di VERIFICA_LIVE.md")
    a = ap.parse_args(argv)

    _carica_env()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("COLLAUDO_REPO", "").strip()
    arch = Archivio(token=token)
    prove = leggi_prove()

    if a.stato:
        print(riepilogo(prove, arch.carica()))
        return 0
    if a.storico:
        print(testo_storico(arch.storico()))
        return 0
    if a.ripeti:
        ripeti(a.ripeti, prove, arch, None if a.non_modificare else FILE_PROVE)
        return 0
    if a.invia_in_sospeso:
        invia_in_sospeso(arch, prove, repo, token)
        return 0
    esegui(prove, arch, repo=repo, token=token,
           file_prove=None if a.non_modificare else FILE_PROVE, sezione=a.sezione)
    return 0


if __name__ == "__main__":
    sys.exit(main())
