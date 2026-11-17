"""
core/allegati_tipo_logic.py
===========================
Tipo vero di un allegato dai primi byte (mai dal nome o dal content-type) e decisione unica su cosa fare:
`immagine` (strada D62: png, jpeg, gif, webp, bmp, tiff, ico, avif; HEIC resta scheda), `scheda` (si tiene solo nome pulito, tipo, dimensione, impronta SHA-256) o `rifiuta`
(travestito, eseguibile, pagina attiva o sconosciuto: nessun file, solo un avviso). Logica pura: nessun file
aperto, nessuna decodifica, nessuna dipendenza nuova.
Funzioni coperte: SPEC §8.16 (D74, #160)
Dipende da: core/immagini_byte_logic.py (riconoscimento delle immagini)
"""

from __future__ import annotations

import hashlib
import re
import struct
import unicodedata
from dataclasses import dataclass

from core.immagini_byte_logic import TIPI, riconosci_tipo

IMMAGINE = "immagine"
SCHEDA = "scheda"
RIFIUTA = "rifiuta"

MAX_NOME = 80
MAX_BYTE_ESAME = 64 * 1024 * 1024  # oltre, il chiamante non scarica: vedi `decidi_senza_byte`

# Modelli di riserva: i testi veri stanno in locales (allegato_riga_scheda, allegato_riga_avviso).
MODELLO_SCHEDA = "`{nome}` ({tipo}, {kib} KiB, SHA-256 {sha}): file non conservato"
MODELLO_AVVISO = "`{nome}`: file non conservato ({motivi})"

# Bidi, isolamenti e caratteri invisibili che nascondono l'estensione vera.
_INVERSIONI = frozenset("؜‎‏‪‫‬‭‮⁦⁧⁨⁩")
# Tolti anche gli accenti gravi e le parentesi: il nome finisce tra `accenti gravi` nei log e non deve
# poter uscire dal blocco, scrivere un link mascherato o una menzione.
_NON_AMMESSI = '"<>|*?:`[]()@'

_ESTENSIONI = {
    "immagine": "png jpg jpeg jfif gif webp bmp tif tiff ico avif heic heif",
    "pdf": "pdf",
    "audio": "mp3 wav ogg oga opus flac m4a aac wma mid midi amr aiff",
    "video": "mp4 m4v mov webm mkv avi flv wmv mpg mpeg 3gp ogv",
    "office": "doc docx xls xlsx ppt pptx odt ods odp rtf docm xlsm pptm",
    "archivio": "zip rar 7z gz tgz tar bz2 xz zst cab iso",
    "testo": "txt md log csv json xml yaml yml ini",
    "web": "html htm xhtml svg svgz",
    "eseguibile": (
        "exe dll scr com pif msi msp mst bat cmd ps1 psm1 vbs vbe js jse wsf wsh hta sh bash py pyw jar apk "
        "appx msix lnk reg url cpl gadget app command elf deb rpm dmg pkg "
        "chm hlp scf inf sct wsc msc jnlp vb vbscript ps1xml psd1 diagcab settingcontent-ms appref-ms library-ms "
        "website webloc desktop action workflow terminal scpt img vhd vhdx"
    ),
}
_PER_ESTENSIONE = {e: c for c, elenco in _ESTENSIONI.items() for e in elenco.split()}
_ESTENSIONI_PERICOLOSE = frozenset(_ESTENSIONI["eseguibile"].split())
_CONTENT_TYPE = (
    ("image/", "immagine"), ("audio/", "audio"), ("video/", "video"), ("application/pdf", "pdf"),
    ("application/zip", "archivio"), ("application/x-rar", "archivio"), ("application/x-7z", "archivio"),
    ("application/gzip", "archivio"), ("application/msword", "office"), ("application/vnd.", "office"),
    ("text/html", "web"), ("text/", "testo"), ("application/json", "testo"),
    ("application/x-msdownload", "eseguibile"), ("application/x-sh", "eseguibile"),
    ("application/x-executable", "eseguibile"),
)
# Coppie che non sono un travestimento: i contenitori si somigliano e restano comunque solo scheda.
_COMPATIBILI = (frozenset({"audio", "video"}), frozenset({"office", "archivio"}))
_ESEGUIBILI_INIZIO = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce",
                      b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"#!")
_LNK = bytes.fromhex("4c00000001140200")
_OLE = bytes.fromhex("d0cf11e0a1b11ae1")
_AUDIO_INIZIO = (b"ID3", b"OggS", b"fLaC", b"MThd", b"#!AMR", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2",
                 b"\xff\xf1", b"\xff\xf9")
_VIDEO_INIZIO = (b"\x1a\x45\xdf\xa3", b"FLV\x01", b"\x00\x00\x01\xba")
_ARCHIVI_INIZIO = (b"Rar!\x1a\x07", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b\x08", b"BZh", b"\xfd7zXZ\x00",
                   b"\x28\xb5\x2f\xfd", b"MSCF")
_MARCHE_AUDIO_FTYP = (b"M4A ", b"M4B ", b"M4P ", b"F4A ")
_MARCHE_IMMAGINE_FTYP = (b"heic", b"heix", b"mif1", b"msf1", b"avif", b"avis")
_PAGINA = re.compile(rb"^\s*(?:<!doctype\s+html|<html|<head|<body|<script|<iframe|<\?php)", re.IGNORECASE)
_SVG = re.compile(rb"<svg[\s>]", re.IGNORECASE)


@dataclass(frozen=True)
class TipoVero:
    categoria: str  # immagine, pdf, audio, video, office, archivio, eseguibile, web, testo, sconosciuto
    formato: str  # nome breve del formato (png, mp4, zip, ...)


@dataclass(frozen=True)
class Decisione:
    azione: str
    tipo: TipoVero
    nome: str
    dimensione: int
    sha256: str
    travestito: bool
    motivi: tuple[str, ...]


def nome_pulito(nome: str | None) -> str:
    """Solo il nome, senza percorsi, caratteri di controllo e inversioni; corto. Non va mai usato come percorso."""
    ultimo = (nome or "").replace("\\", "/").split("/")[-1]
    ultimo = unicodedata.normalize("NFC", ultimo)
    pulito = "".join(
        c for c in ultimo
        if c not in _INVERSIONI and c not in _NON_AMMESSI and c.isprintable() and unicodedata.category(c) != "Cf"
    ).strip(" .")
    if len(pulito) > MAX_NOME:
        radice, punto, estensione = pulito.rpartition(".")
        if punto and 0 < len(estensione) <= 12:
            pulito = radice[: MAX_NOME - len(estensione) - 1] + "." + estensione
        else:
            pulito = pulito[:MAX_NOME]
    return pulito or "file"


def _estensioni(nome: str | None) -> list[str]:
    """Le estensioni del nome, dalla prima all'ultima (`a.png.exe` -> ['png', 'exe'])."""
    # Stessa pulizia di ciò che vedrà la persona: lettere larghe (ｅｘｅ) e caratteri invisibili non nascondono l'estensione.
    base = unicodedata.normalize("NFKC", (nome or "").replace("\\", "/").split("/")[-1])
    base = "".join(c for c in base if c.isprintable() and unicodedata.category(c) != "Cf").strip(" .")
    parti = base.casefold().split(".")
    return [p.strip() for p in parti[1:] if p.strip()]


def _dal_content_type(content_type: str | None) -> str | None:
    tipo = (content_type or "").split(";")[0].strip().lower()
    return next((c for prefisso, c in _CONTENT_TYPE if tipo.startswith(prefisso)), None)


def _zip(dati: bytes) -> TipoVero:
    testa = dati[:4096]
    if b"mimetypeapplication/vnd.oasis.opendocument" in testa:
        return TipoVero("office", "opendocument")
    if b"[Content_Types].xml" in testa or b"word/" in testa or b"xl/" in testa or b"ppt/" in testa:
        return TipoVero("office", "ooxml")
    if b"AndroidManifest.xml" in testa or b"classes.dex" in testa:
        return TipoVero("eseguibile", "apk")
    return TipoVero("archivio", "zip")


def _ftyp(dati: bytes) -> TipoVero | None:
    if dati[4:8] != b"ftyp":
        return None
    marca = dati[8:12]
    if marca in _MARCHE_AUDIO_FTYP:
        return TipoVero("audio", "m4a")
    if marca in _MARCHE_IMMAGINE_FTYP:
        return TipoVero("immagine", "heif")
    return TipoVero("video", "mp4")


def _testo(dati: bytes) -> bool:
    testa = dati[:4096]
    if not testa or b"\0" in testa:
        return False
    try:
        testo = testa.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        if exc.start < len(testa) - 4:  # un taglio a meta' di un carattere in fondo non conta
            return False
        testo = testa[: exc.start].decode("utf-8", errors="ignore")
    strani = sum(1 for c in testo if not c.isprintable() and c not in "\r\n\t")
    return strani <= len(testo) * 0.02


def riconosci(dati: bytes) -> TipoVero:
    """La categoria vera dai primi byte. Non apre ne' decodifica nulla."""
    dati = bytes(dati[:8192]) if dati else b""
    vero = riconosci_tipo(dati)
    if vero is not None:
        return TipoVero("immagine", vero)
    if dati.startswith(_LNK) or dati.startswith(_ESEGUIBILI_INIZIO):
        return TipoVero("eseguibile", "pe" if dati[:2] == b"MZ" else "script" if dati[:2] == b"#!" else "binario")
    if dati[:5] == b"%PDF-" or b"%PDF-" in dati[:1024]:
        return TipoVero("pdf", "pdf")
    if dati.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return _zip(dati)
    if dati.startswith(_OLE):
        return TipoVero("office", "ole")
    if dati.startswith(_ARCHIVI_INIZIO) or dati[257:262] == b"ustar":
        return TipoVero("archivio", "archivio")
    ftyp = _ftyp(dati)
    if ftyp is not None:
        return ftyp
    if dati[:4] == b"RIFF" and dati[8:12] in (b"WAVE", b"AVI "):
        return TipoVero("audio", "wav") if dati[8:12] == b"WAVE" else TipoVero("video", "avi")
    if dati[:4] == b"FORM" and dati[8:12] in (b"AIFF", b"AIFC"):
        return TipoVero("audio", "aiff")
    if dati.startswith(_AUDIO_INIZIO):
        return TipoVero("audio", "audio")
    if dati.startswith(_VIDEO_INIZIO):
        return TipoVero("video", "video")
    if dati.startswith((b"BM", b"II*\x00", b"MM\x00*", b"\x00\x00\x01\x00")) and len(dati) > 14:
        return TipoVero("immagine", "altra")
    if _PAGINA.match(dati.lstrip(b"\xef\xbb\xbf")):
        return TipoVero("web", "html")
    if _testo(dati):
        if _SVG.search(dati[:2048]):
            return TipoVero("web", "svg")
        return TipoVero("testo", "testo")
    return TipoVero("sconosciuto", "sconosciuto")


def _non_coincide(vera: str, dichiarate: list[str]) -> bool:
    for d in dichiarate:
        if d == vera or any(d in g and vera in g for g in _COMPATIBILI):
            continue
        return True
    return False


def _giudica(vero: TipoVero, nome: str | None, content_type: str | None, motivi: list[str]) -> bool:
    """Riempie i motivi; torna True se nome e byte non coincidono (travestito)."""
    travestito = False
    estensioni = _estensioni(nome)
    if any(c in _INVERSIONI for c in (nome or "")):
        motivi.append("inversione_testo")
        travestito = True
    if len(estensioni) >= 2 and estensioni[-1] in _ESTENSIONI_PERICOLOSE and estensioni[-2] in _PER_ESTENSIONE:
        motivi.append("doppia_estensione")
        travestito = True
    dichiarate = [c for c in (_PER_ESTENSIONE.get(estensioni[-1]) if estensioni else None, _dal_content_type(content_type)) if c]
    if _non_coincide(vero.categoria, dichiarate):
        motivi.append("tipo_non_coincide")
        travestito = True
    return travestito


def _azione(vero: TipoVero, nome: str | None, motivi: list[str], travestito: bool) -> str:
    estensioni = _estensioni(nome)
    per_nome = bool(estensioni) and estensioni[-1] in _ESTENSIONI_PERICOLOSE
    if vero.categoria == "eseguibile" or (per_nome and vero.categoria not in ("immagine", "audio", "video", "pdf")):
        motivi.append("eseguibile")
        return RIFIUTA
    if travestito:
        return RIFIUTA
    if vero.categoria == "web":
        motivi.append("pagina_attiva")
        return RIFIUTA
    if vero.categoria == "sconosciuto":
        motivi.append("sconosciuto")
        return RIFIUTA
    if vero.categoria == "immagine" and vero.formato in TIPI:
        return IMMAGINE
    return SCHEDA


def decidi(dati: bytes, nome: str | None, content_type: str | None = None) -> Decisione:
    """L'unica decisione per ogni allegato di un utente (D74). `dati` e' il file intero."""
    dati = dati or b""
    vero = riconosci(dati)
    if vero.formato == "tiff" and struct.unpack("<I" if dati[:2] == b"II" else ">I", dati[4:8])[0] + 2 > len(dati):
        vero = TipoVero("immagine", "altra")  # indirizzo della prima pagina fuori dal file: non e' un TIFF intero
    motivi: list[str] = []
    travestito = _giudica(vero, nome, content_type, motivi)
    azione = _azione(vero, nome, motivi, travestito)
    return Decisione(azione, vero, nome_pulito(nome), len(dati), hashlib.sha256(dati).hexdigest(), travestito, tuple(motivi))


def decidi_senza_byte(nome: str | None, content_type: str | None, dimensione: int) -> Decisione:
    """File troppo grande da scaricare: solo scheda, senza tipo verificato ne' impronta; i nomi pericolosi si rifiutano."""
    motivi: list[str] = []
    vero = TipoVero("non_verificato", "non_verificato")
    _giudica(vero, nome, content_type, motivi)
    motivi = [m for m in motivi if m != "tipo_non_coincide"]
    travestito = bool(motivi)
    estensioni = _estensioni(nome)
    rifiuta = travestito or (bool(estensioni) and estensioni[-1] in _ESTENSIONI_PERICOLOSE)
    if rifiuta and not travestito:
        motivi.append("eseguibile")
    return Decisione(RIFIUTA if rifiuta else SCHEDA, vero, nome_pulito(nome), int(dimensione or 0), "", travestito, tuple(motivi))


def riga_scheda(d: Decisione, modello: str = MODELLO_SCHEDA) -> str:
    """La riga di log di un file tenuto solo come scheda."""
    return modello.format(nome=d.nome, tipo=d.tipo.categoria, kib=max(0, d.dimensione) // 1024, sha=d.sha256[:12] or "n/d")


def riga_avviso(d: Decisione, modello: str = MODELLO_AVVISO) -> str:
    """La riga di avviso di un file rifiutato."""
    return modello.format(nome=d.nome, motivi=", ".join(d.motivi) or d.tipo.categoria)
