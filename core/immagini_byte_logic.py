"""
core/immagini_byte_logic.py
===========================
Controlli sui byte di un allegato immagine, senza mai decodificarlo (D61, D62): tipo vero dai
primi byte contro estensione e content-type, dimensioni dichiarate nell'intestazione, struttura
(blocchi PNG e CRC, segmenti JPEG, blocchi GIF, misura RIFF di WEBP, pagine TIFF, voci ICO, intestazione BMP, scatola `ispe` di AVIF) e dati in coda dopo la fine
dell'immagine (file «poliglotti»). Logica pura: niente Discord, niente Pillow, niente database.
Le «foto in movimento» (JPEG + video MP4 in coda) non sono un falso positivo.
Funzioni coperte: SPEC §6 (D62), §8.16 (D74: BMP, TIFF, ICO, AVIF)
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from dataclasses import dataclass, field

from core.safe_image import MAX_IMAGE_BYTES, MAX_PIXELS

PULITA = "pulita"
SOSPETTA = "sospetta"
MALEVOLA = "malevola"
_GRAVITA = {PULITA: 0, SOSPETTA: 1, MALEVOLA: 2}

TIPI = ("png", "jpeg", "gif", "webp", "bmp", "tiff", "ico", "avif")
_ESTENSIONI = {
    "png": "png", "jpg": "jpeg", "jpeg": "jpeg", "jfif": "jpeg", "gif": "gif", "webp": "webp",
    "bmp": "bmp", "tif": "tiff", "tiff": "tiff", "ico": "ico", "avif": "avif",
}
_CONTENT_TYPE = {
    "image/png": "png", "image/jpeg": "jpeg", "image/jpg": "jpeg", "image/gif": "gif", "image/webp": "webp",
    "image/bmp": "bmp", "image/x-ms-bmp": "bmp", "image/x-bmp": "bmp", "image/tiff": "tiff",
    "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/avif": "avif",
}
MAX_PAGINE_TIFF = 200
MAX_IMMAGINI_ICO = 64
_DIB_BMP = (12, 40, 52, 56, 64, 108, 124)
_MARCHE_AVIF = (b"avif", b"avis")

MAX_TESTO_PNG = 1024 * 1024
MAX_EXIF = 256 * 1024
MAX_ICC = 1024 * 1024
SOGLIA_CODA = 0.5  # dati in coda oltre questa parte del file, senza marcatore noto: sospetti
MAX_BLOCCHI = 200_000  # tetto di giri: un file da 8 MiB di blocchi vuoti non deve costare

_FIRME_INIZIO = (
    (b"MZ", "coda_firma_eseguibile"),
    (b"\x7fELF", "coda_firma_eseguibile"),
    (b"#!", "coda_firma_eseguibile"),
    (b"\xcf\xfa\xed\xfe", "coda_firma_eseguibile"),
    (b"\xca\xfe\xba\xbe", "coda_firma_eseguibile"),
    (b"PK\x03\x04", "coda_firma_archivio"),
    (b"PK\x05\x06", "coda_firma_archivio"),
    (b"Rar!", "coda_firma_archivio"),
    (b"7z\xbc\xaf\x27\x1c", "coda_firma_archivio"),
    (b"\x1f\x8b\x08", "coda_firma_archivio"),
    (b"%PDF-", "coda_firma_documento"),
)
_FIRME_OVUNQUE = (
    (b"This program cannot be run", "coda_firma_eseguibile"),
    (b"\x7fELF", "coda_firma_eseguibile"),
    (b"PK\x03\x04", "coda_firma_archivio"),
    (b"Rar!\x1a\x07", "coda_firma_archivio"),
    (b"%PDF-", "coda_firma_documento"),
)
_PAGINA = re.compile(rb"<\s*(?:html|script|iframe|\?php)", re.IGNORECASE)
_MARCATORI_MOVIMENTO = (b"MotionPhoto", b"MicroVideo", b"MotionPhoto_Data", b"GCamera:MicroVideo")
_MARCA_JPEG = re.compile(rb"\xff[\x01-\xcf\xd8-\xfe]")


@dataclass(frozen=True)
class Motivo:
    codice: str
    gravita: str = SOSPETTA


@dataclass(frozen=True)
class EsitoByte:
    sha256: str
    tipo: str | None = None
    larghezza: int | None = None
    altezza: int | None = None
    motivi: tuple[Motivo, ...] = ()
    byte_in_coda: int = 0
    troppo_grande: bool = False
    note: tuple[str, ...] = field(default=())

    @property
    def verdetto(self) -> str:
        peggio = PULITA
        for m in self.motivi:
            if _GRAVITA[m.gravita] > _GRAVITA[peggio]:
                peggio = m.gravita
        return peggio


class _Raccolta:
    """Motivi e note raccolti durante la lettura (uno per codice)."""

    def __init__(self) -> None:
        self.motivi: dict[str, Motivo] = {}
        self.note: list[str] = []
        self.larghezza: int | None = None
        self.altezza: int | None = None
        self.fine: int | None = None  # posizione dove l'immagine finisce davvero
        self.movimento = False

    def motivo(self, codice: str, gravita: str = SOSPETTA) -> None:
        if codice not in self.motivi or _GRAVITA[gravita] > _GRAVITA[self.motivi[codice].gravita]:
            self.motivi[codice] = Motivo(codice, gravita)


def riconosci_tipo(dati: bytes) -> str | None:
    """Il tipo vero dai primi byte, solo dall'elenco chiuso (D61). None se non e' uno di quelli."""
    if dati.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dati.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if dati[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if dati[:4] == b"RIFF" and dati[8:12] == b"WEBP":
        return "webp"
    if _e_bmp(dati):
        return "bmp"
    if _e_tiff(dati):
        return "tiff"
    if _e_ico(dati):
        return "ico"
    if _e_avif(dati):
        return "avif"
    return None


def _e_bmp(dati: bytes) -> bool:
    return len(dati) >= 26 and dati[:2] == b"BM" and struct.unpack("<I", dati[14:18])[0] in _DIB_BMP


def _e_tiff(dati: bytes) -> bool:
    if len(dati) < 8 or dati[:4] not in (b"II*\x00", b"MM\x00*"):
        return False
    return struct.unpack("<I" if dati[:2] == b"II" else ">I", dati[4:8])[0] >= 8


def _e_ico(dati: bytes) -> bool:
    # Tipo 1 (icona), almeno una voce, byte riservato della prima voce a zero, dimensioni e posizione sensate.
    if len(dati) < 22 or dati[:4] != b"\x00\x00\x01\x00":
        return False
    voci = struct.unpack("<H", dati[4:6])[0]
    misura, posizione = struct.unpack("<II", dati[14:22])
    return voci >= 1 and dati[9] == 0 and misura > 0 and posizione >= 6 + 16 * voci


def _e_avif(dati: bytes) -> bool:
    if len(dati) < 16 or dati[4:8] != b"ftyp":
        return False
    misura = min(struct.unpack(">I", dati[:4])[0], len(dati), 256)
    marche = [dati[8:12], *(dati[i:i + 4] for i in range(16, misura - 3, 4))]
    return any(m in _MARCHE_AVIF for m in marche)


def nome_file_sicuro(nome: str) -> str:
    """Solo il nome del file, corto e senza caratteri di controllo ne' virgolette (finisce in log e intestazioni)."""
    pulito = "".join(c for c in (nome or "").replace("\\", "/").split("/")[-1] if c.isprintable() and c not in '"<>')
    return pulito[:80] or "file"


def estensione_di(nome: str) -> str:
    nome = (nome or "").rsplit("/", 1)[-1]
    return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


def tipo_atteso(nome: str, content_type: str | None) -> str | None:
    """Il tipo che l'allegato dice di essere (estensione, poi content-type), solo se e' uno dei nostri."""
    return _ESTENSIONI.get(estensione_di(nome)) or _CONTENT_TYPE.get((content_type or "").split(";")[0].strip().lower())


# ----------------------------------------------------------------------------- lettura per formato


def _leggi_png(dati: bytes, r: _Raccolta) -> None:
    pos, n = 8, len(dati)
    primo = True
    for _ in range(MAX_BLOCCHI):
        if pos + 8 > n:
            r.motivo("png_troncato")
            return
        lunghezza, tipo = struct.unpack(">I4s", dati[pos : pos + 8])
        fine = pos + 8 + lunghezza + 4
        if fine > n:
            r.motivo("png_troncato")
            return
        corpo = dati[pos + 8 : pos + 8 + lunghezza]
        if zlib.crc32(tipo + corpo) != struct.unpack(">I", dati[fine - 4 : fine])[0]:
            r.motivo("png_crc")
        if primo:
            primo = False
            if tipo != b"IHDR" or lunghezza != 13:
                r.motivo("png_intestazione")
            else:
                r.larghezza, r.altezza = struct.unpack(">II", corpo[:8])
        if tipo in (b"tEXt", b"zTXt", b"iTXt") and lunghezza > MAX_TESTO_PNG:
            r.motivo("png_testo_enorme")
        if tipo == b"iCCP" and lunghezza > MAX_ICC:
            r.motivo("png_icc_enorme")
        pos = fine
        if tipo == b"IEND":
            r.fine = pos
            return
    r.motivo("png_troppi_blocchi")


def _leggi_jpeg(dati: bytes, r: _Raccolta) -> None:
    n, pos = len(dati), 2
    for _ in range(MAX_BLOCCHI):
        trovata = _MARCA_JPEG.search(dati, pos)
        if trovata is None:
            return  # niente EOI: JPEG tagliato, succede; non si da' per sospetto
        pos = trovata.end()
        marca = dati[pos - 1]
        if marca == 0xD9:
            r.fine = pos
            return
        if marca in (0x01, 0xD8) or 0xD0 <= marca <= 0xD7:
            continue
        if pos + 2 > n:
            r.motivo("jpeg_troncato")
            return
        lunghezza = struct.unpack(">H", dati[pos : pos + 2])[0]
        if lunghezza < 2 or pos + lunghezza > n:
            r.motivo("jpeg_troncato")
            return
        corpo = dati[pos + 2 : pos + lunghezza]
        if 0xC0 <= marca <= 0xCF and marca not in (0xC4, 0xC8, 0xCC) and len(corpo) >= 5 and r.larghezza is None:
            r.altezza, r.larghezza = struct.unpack(">HH", corpo[1:5])
        if marca == 0xE1 and corpo.startswith(b"Exif") and lunghezza > MAX_EXIF:
            r.motivo("jpeg_exif_enorme")
        if marca == 0xE2 and corpo.startswith(b"ICC_PROFILE") and lunghezza > MAX_ICC:
            r.motivo("jpeg_icc_enorme")
        if marca == 0xE1 and any(m in corpo[:4000] for m in _MARCATORI_MOVIMENTO):
            r.movimento = True
        pos += lunghezza
    r.motivo("jpeg_troppi_segmenti")


def _leggi_gif(dati: bytes, r: _Raccolta) -> None:
    n = len(dati)
    if n < 13:
        r.motivo("gif_troncato")
        return
    r.larghezza, r.altezza = struct.unpack("<HH", dati[6:10])
    flag = dati[10]
    pos = 13 + (3 * (2 ** ((flag & 7) + 1)) if flag & 0x80 else 0)

    def sotto_blocchi(p: int) -> int:
        while p < n:
            dim = dati[p]
            p += 1 + dim
            if dim == 0:
                return p
        return n + 1

    for _ in range(MAX_BLOCCHI):
        if pos >= n:
            return  # niente trailer: GIF tagliata
        codice = dati[pos]
        if codice == 0x3B:
            r.fine = pos + 1
            return
        if codice == 0x21:
            pos = sotto_blocchi(pos + 2)
        elif codice == 0x2C:
            if pos + 10 > n:
                r.motivo("gif_troncato")
                return
            f = dati[pos + 9]
            pos += 10 + (3 * (2 ** ((f & 7) + 1)) if f & 0x80 else 0) + 1
            pos = sotto_blocchi(pos)
        else:
            r.motivo("gif_struttura")
            return
        if pos > n:
            r.motivo("gif_troncato")
            return
    r.motivo("gif_troppi_blocchi")


def _leggi_webp(dati: bytes, r: _Raccolta) -> None:
    n = len(dati)
    if n < 20:
        r.motivo("webp_troncato")
        return
    misura = struct.unpack("<I", dati[4:8])[0] + 8
    if misura > n:
        r.motivo("webp_troncato")
        misura = n
    elif misura < 20:
        r.motivo("webp_struttura")
        return
    else:
        r.fine = misura
    pos = 12
    for _ in range(MAX_BLOCCHI):
        if pos + 8 > misura:
            break
        fourcc, lunghezza = struct.unpack("<4sI", dati[pos : pos + 8])
        corpo = dati[pos + 8 : pos + 8 + min(lunghezza, 40)]
        if pos + 8 + lunghezza > misura:
            r.motivo("webp_struttura")
            return
        if fourcc == b"VP8X" and len(corpo) >= 10:
            r.larghezza = int.from_bytes(corpo[4:7], "little") + 1
            r.altezza = int.from_bytes(corpo[7:10], "little") + 1
        elif fourcc == b"VP8 " and len(corpo) >= 10 and corpo[3:6] == b"\x9d\x01\x2a" and r.larghezza is None:
            r.larghezza, r.altezza = struct.unpack("<HH", corpo[6:10])
            r.larghezza &= 0x3FFF
            r.altezza &= 0x3FFF
        elif fourcc == b"VP8L" and len(corpo) >= 5 and corpo[0] == 0x2F and r.larghezza is None:
            bit = int.from_bytes(corpo[1:5], "little")
            r.larghezza, r.altezza = (bit & 0x3FFF) + 1, ((bit >> 14) & 0x3FFF) + 1
        elif fourcc == b"EXIF" and lunghezza > MAX_EXIF:
            r.motivo("webp_exif_enorme")
        elif fourcc == b"ICCP" and lunghezza > MAX_ICC:
            r.motivo("webp_icc_enorme")
        pos += 8 + lunghezza + (lunghezza & 1)
    else:
        r.motivo("webp_troppi_blocchi")


def _leggi_bmp(dati: bytes, r: _Raccolta) -> None:
    dib = struct.unpack("<I", dati[14:18])[0]
    if dib == 12:
        r.larghezza, r.altezza = struct.unpack("<HH", dati[18:22])
    else:
        larghezza, altezza = struct.unpack("<ii", dati[18:26])
        r.larghezza, r.altezza = abs(larghezza), abs(altezza)
    totale = struct.unpack("<I", dati[2:6])[0]
    if totale > len(dati):
        r.motivo("bmp_troncato")
    elif totale >= 26:
        r.fine = totale


def _leggi_tiff(dati: bytes, r: _Raccolta) -> None:
    f = "<" if dati[:2] == b"II" else ">"
    posizione = struct.unpack(f + "I", dati[4:8])[0]
    visti: set[int] = set()
    pagine = 0
    while posizione:
        if posizione in visti:
            r.motivo("tiff_catena_pagine")
            return
        visti.add(posizione)
        if posizione + 2 > len(dati):
            r.motivo("tiff_troncato")
            return
        voci = struct.unpack(f + "H", dati[posizione:posizione + 2])[0]
        fine_voci = posizione + 2 + voci * 12
        if voci > 4096 or fine_voci + 4 > len(dati):
            r.motivo("tiff_troncato")
            return
        if pagine == 0:
            _dimensioni_tiff(dati, f, posizione + 2, voci, r)
        pagine += 1
        if pagine > MAX_PAGINE_TIFF:
            r.motivo("troppe_pagine")
            return
        posizione = struct.unpack(f + "I", dati[fine_voci:fine_voci + 4])[0]


def _dimensioni_tiff(dati: bytes, f: str, inizio: int, voci: int, r: _Raccolta) -> None:
    for i in range(voci):
        voce = dati[inizio + i * 12: inizio + i * 12 + 12]
        etichetta, tipo, quanti = struct.unpack(f + "HHI", voce[:8])
        if etichetta not in (256, 257) or quanti != 1:
            continue
        valore = struct.unpack(f + "H", voce[8:10])[0] if tipo == 3 else struct.unpack(f + "I", voce[8:12])[0] if tipo == 4 else None
        if valore is not None:
            if etichetta == 256:
                r.larghezza = valore
            else:
                r.altezza = valore


def _leggi_ico(dati: bytes, r: _Raccolta) -> None:
    voci = struct.unpack("<H", dati[4:6])[0]
    if voci > MAX_IMMAGINI_ICO:
        r.motivo("troppe_pagine")
    if 6 + voci * 16 > len(dati):
        r.motivo("ico_troncato")
        return
    lati = [(dati[6 + i * 16] or 256, dati[7 + i * 16] or 256) for i in range(min(voci, MAX_IMMAGINI_ICO))]
    r.larghezza, r.altezza = max(w for w, _ in lati), max(h for _, h in lati)


def _leggi_avif(dati: bytes, r: _Raccolta) -> None:
    # Le dimensioni stanno nelle scatole `ispe` (versione e flag, poi larghezza e altezza): si prende la piu' grande.
    testa = dati[:65536]
    posto = testa.find(b"ispe")
    while posto != -1:
        if posto + 16 <= len(testa):
            larghezza, altezza = struct.unpack(">II", testa[posto + 8: posto + 16])
            r.larghezza = max(r.larghezza or 0, larghezza)
            r.altezza = max(r.altezza or 0, altezza)
        posto = testa.find(b"ispe", posto + 4)


_LETTORI = {
    "png": _leggi_png, "jpeg": _leggi_jpeg, "gif": _leggi_gif, "webp": _leggi_webp,
    "bmp": _leggi_bmp, "tiff": _leggi_tiff, "ico": _leggi_ico, "avif": _leggi_avif,
}


# ----------------------------------------------------------------------------- coda


def _e_video_mp4(coda: bytes) -> bool:
    """La coda comincia con una scatola `ftyp` ben formata: la parte video di una foto in movimento."""
    if len(coda) < 16 or coda[4:8] != b"ftyp":
        return False
    misura = struct.unpack(">I", coda[:4])[0]
    return 8 <= misura <= min(len(coda), 256)


def _giudica_coda(dati: bytes, fine: int, r: _Raccolta, tipo: str) -> int:
    coda = dati[fine:]
    if not coda:
        return 0
    movimento = r.movimento or _e_video_mp4(coda)
    seconda_jpeg = tipo == "jpeg" and coda.startswith(b"\xff\xd8\xff")  # MPF: due immagini nello stesso file
    for firma, codice in _FIRME_INIZIO:
        if coda.startswith(firma):
            r.motivo(codice, MALEVOLA)
    if _PAGINA.search(coda):
        r.motivo("coda_pagina", MALEVOLA)
    if not (movimento or seconda_jpeg):
        for firma, codice in _FIRME_OVUNQUE:
            if firma in coda:
                r.motivo(codice, MALEVOLA)
    if movimento and not r.motivi.get("coda_pagina") and not any(m.gravita == MALEVOLA for m in r.motivi.values()):
        r.note.append("foto_in_movimento")
    elif seconda_jpeg and not any(m.gravita == MALEVOLA for m in r.motivi.values()):
        r.note.append("immagine_multipla")
    elif not movimento and not seconda_jpeg and len(coda) > len(dati) * SOGLIA_CODA:
        r.motivo("coda_troppo_grande")
    return len(coda)


# ----------------------------------------------------------------------------- entrata


def controlla_byte(dati: bytes, nome_file: str = "", content_type: str | None = None) -> EsitoByte:
    """
    Controlla i byte di un allegato. Non solleva mai e non decodifica nulla.
    Il nome e il content-type servono solo a confrontare il tipo dichiarato con quello vero.
    """
    sha = hashlib.sha256(dati).hexdigest()
    if len(dati) > MAX_IMAGE_BYTES:
        return EsitoByte(sha256=sha, troppo_grande=True)
    r = _Raccolta()
    tipo = riconosci_tipo(dati)
    atteso = tipo_atteso(nome_file, content_type)
    estensione = _ESTENSIONI.get(estensione_di(nome_file))
    if tipo is None:
        if estensione:
            r.motivo("tipo_non_riconosciuto")
        return EsitoByte(sha256=sha, motivi=tuple(r.motivi.values()))
    if estensione and estensione != tipo:
        r.motivo("tipo_diverso_estensione")
    tipo_ct = _CONTENT_TYPE.get((content_type or "").split(";")[0].strip().lower())
    if tipo_ct and tipo_ct != tipo:
        r.motivo("tipo_diverso_content_type")
    del atteso
    try:
        _LETTORI[tipo](dati, r)
    except (struct.error, IndexError, ValueError):  # un file storto non deve mai far cadere il filtro
        r.motivo("struttura_illeggibile")
    if r.larghezza is None or r.altezza is None:
        r.motivo("intestazione_illeggibile")
    elif r.larghezza == 0 or r.altezza == 0 or r.larghezza * r.altezza > MAX_PIXELS:
        r.motivo("dimensioni_assurde")
    in_coda = _giudica_coda(dati, r.fine, r, tipo) if r.fine is not None else 0
    return EsitoByte(
        sha256=sha,
        tipo=tipo,
        larghezza=r.larghezza,
        altezza=r.altezza,
        motivi=tuple(r.motivi.values()),
        byte_in_coda=in_coda,
        note=tuple(r.note),
    )
