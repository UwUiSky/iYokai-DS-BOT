"""
scripts/aggiorna_vpn.py
=======================
Scarica gli elenchi per riconoscere VPN e proxy nella verifica web (D64) in `data/vpn/` (o nella
cartella data come primo argomento; è la stessa di `VPN_DATI_CARTELLA`). Lo lancia l'owner, di
solito una volta a settimana; il bot rilegge i file da solo. Fonti e licenze: `docs/verifica_vpn.md`.
Uso: python3 scripts/aggiorna_vpn.py [cartella]   |   --fusi [cartella]  (rigenera fuso_paesi.txt)
Funzioni coperte: SPEC §4.2 (VPN e proxy, D64)
"""

from __future__ import annotations

import os
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import verify_vpn_logic as logica  # noqa: E402

CARTELLA_DI_BASE = "data/vpn"
TETTO_BYTE = 30 * 1024 * 1024  # un file oltre questo non è un elenco di reti
X4B = "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output"


@dataclass(frozen=True)
class Fonte:
    file: str
    indirizzi: tuple[str, ...]
    descrizione: str
    licenza: str
    minimo: int
    conta: Callable[[str], int]


FONTI = (
    Fonte(
        "asn_hosting.txt",
        ("https://raw.githubusercontent.com/brianhama/bad-asn-list/master/bad-asn-list.csv",),
        "ASN di hosting e data center (brianhama/bad-asn-list)", "MIT", 100, lambda t: len(logica.leggi_asn(t)),
    ),
    Fonte(
        "tor_uscita.txt", ("https://check.torproject.org/torbulkexitlist",),
        "nodi di uscita Tor (elenco ufficiale del Tor Project)", "elenco pubblico del Tor Project", 100,
        lambda t: len(logica.leggi_nodi_tor(t)),
    ),
    Fonte(
        "reti_vpn.txt", (f"{X4B}/vpn/ipv4.txt", f"{X4B}/vpn/ipv6.txt"),
        "reti di VPN note (X4BNet/lists_vpn)", "MIT", 100, lambda t: len(logica.ElencoReti.da_testo(t)),
    ),
    Fonte(
        "reti_datacenter.txt", (f"{X4B}/datacenter/ipv4.txt", f"{X4B}/datacenter/ipv6.txt"),
        "reti di data center e VPN (X4BNet/lists_vpn)", "MIT", 1000, lambda t: len(logica.ElencoReti.da_testo(t)),
    ),
)


def _scarica_testo(indirizzo: str) -> str:
    if not indirizzo.startswith("https://"):
        raise ValueError("solo indirizzi https")
    with urllib.request.urlopen(indirizzo, timeout=60) as risposta:
        dati = risposta.read(TETTO_BYTE + 1)
    if len(dati) > TETTO_BYTE:
        raise ValueError("file troppo grande")
    return dati.decode("utf-8")


def intestazione(fonte: Fonte, oggi: date) -> str:
    return (
        f"# {fonte.descrizione}\n# Licenza: {fonte.licenza}. Scaricato il {oggi.isoformat()} da:\n"
        + "".join(f"#   {i}\n" for i in fonte.indirizzi)
    )


def aggiorna(fonte: Fonte, cartella: str, oggi: date | None = None) -> int:
    """Scarica, controlla e sostituisce il file intero. Il file buono di prima resta se qualcosa va storto."""
    testo = ""
    for indirizzo in fonte.indirizzi:
        testo += _scarica_testo(indirizzo).rstrip("\n") + "\n"
    voci = fonte.conta(testo)
    if voci < fonte.minimo:
        raise ValueError(f"{fonte.file}: solo {voci} voci valide (ne servono almeno {fonte.minimo})")
    os.makedirs(cartella, exist_ok=True)
    temporaneo = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=cartella, suffix=".parziale", delete=False
    )
    try:
        with temporaneo:
            temporaneo.write(intestazione(fonte, oggi or date.today()) + testo)
        os.chmod(temporaneo.name, 0o644)  # il bot può girare con un altro utente
        os.replace(temporaneo.name, os.path.join(cartella, fonte.file))  # il bot non legge mai un file a metà
    finally:
        if os.path.exists(temporaneo.name):
            os.remove(temporaneo.name)
    return voci


def genera_fusi(cartella: str, sorgente: str = "/usr/share/zoneinfo/zone.tab") -> int:
    """Rigenera `fuso_paesi.txt` dal file zone.tab del database dei fusi (pubblico dominio)."""
    zone: dict[str, set[str]] = {}
    with open(sorgente, encoding="utf-8") as f:
        for riga in f:
            if riga.startswith("#") or riga.count("\t") < 2:
                continue
            campi = riga.rstrip("\n").split("\t")
            zone.setdefault(campi[2], set()).add(campi[0])
    righe = [
        "# Fusi orari (nome IANA) e paese di ognuno, per la verifica web (D64): un fuso del browser che non",
        "# appartiene al paese dell'IP è un indizio debole di VPN. Fonte: database dei fusi orari IANA (file zone.tab),",
        "# di pubblico dominio. Si rigenera con `python3 scripts/aggiorna_vpn.py --fusi`. Formato: fuso<TAB>paesi.",
        "",
    ] + [f"{nome}\t{','.join(sorted(zone[nome]))}" for nome in sorted(zone)]
    os.makedirs(cartella, exist_ok=True)
    with open(os.path.join(cartella, "fuso_paesi.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
    return len(zone)


if __name__ == "__main__":
    argomenti = [a for a in sys.argv[1:] if not a.startswith("--")]
    cartella_scelta = argomenti[0] if argomenti else CARTELLA_DI_BASE
    if "--fusi" in sys.argv:
        print(f"{genera_fusi(cartella_scelta)} fusi scritti in {cartella_scelta}/fuso_paesi.txt")
        raise SystemExit(0)
    fallite = 0
    for fonte_scelta in FONTI:
        try:
            print(f"{fonte_scelta.file}: {aggiorna(fonte_scelta, cartella_scelta)} voci ({fonte_scelta.licenza})")
        except (urllib.error.URLError, OSError, ValueError, UnicodeDecodeError) as errore:
            fallite += 1
            print(f"{fonte_scelta.file}: NON aggiornato, resta il file di prima ({errore})")
    print("Fonti e licenze: docs/verifica_vpn.md. Il bot rilegge i file da solo entro un minuto.")
    raise SystemExit(1 if fallite else 0)
