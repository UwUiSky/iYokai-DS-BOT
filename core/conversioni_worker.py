"""
core/conversioni_worker.py
==========================
Processo figlio della sandbox per la copia sicura di PDF, audio, video e testo (D74): converte UN file della
quarantena e scrive l'esito su stdout (lunghezza + JSON, poi lunghezza + byte della copia). Parte con
`python3 -I -B <tipo> <nome>` con i limiti di `core/immagini_sandbox.py`. PDF: ricostruito con pypdf (niente
JavaScript, azioni, file incorporati, moduli, metadati). Audio: Opus in Ogg, al massimo 10 minuti. Video: H.264 + AAC
in MP4, al massimo 2 minuti e 720p. Testo: lo stesso testo in UTF-8, senza caratteri di controllo, al massimo 256 KiB.
ffmpeg parte sempre con una lista di argomenti, formato in entrata esplicito (lo dicono i byte, non il nome) e
protocolli ristretti a file e pipe. Non parla con Discord ne' col database. Qualunque errore e' un esito «errore».
Funzioni coperte: SPEC §8.16 (D74, #160)
Dipende da: core/allegati_tipo_logic.py (tipo dai byte), pypdf, ffmpeg e ffprobe di sistema
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import unicodedata
from pathlib import Path

RADICE = str(Path(__file__).resolve().parent.parent)
if RADICE not in sys.path:  # con -I la cartella non c'e' di suo
    sys.path.insert(0, RADICE)

from core.allegati_tipo_logic import riconosci  # noqa: E402

NOME = re.compile(r"^[0-9a-f]{32}$")
MAX_USCITA_BYTE = int(9.5 * 1024 * 1024)
MAX_PAGINE = 200
MAX_TESTO_USCITA = 256 * 1024
MAX_TESTO_ENTRATA = 1024 * 1024
MAX_SECONDI_AUDIO = 600
MAX_SECONDI_VIDEO = 120
MAX_LATO_INGRESSO = 8192  # oltre, il decoder potrebbe chiedere troppa memoria
CATEGORIA_DEL_TIPO = {"pdf": "pdf", "audio": "audio", "video": "video", "testo": "testo"}
SECONDI_SONDA = 15

# Parole che in un PDF rifatto non devono comparire: se restano, nessuna copia.
_PROIBITE = re.compile(
    rb"/(?:JavaScript|JS|OpenAction|AA|A|Launch|URI|EmbeddedFiles?|EmbeddedFile|AcroForm|XFA|RichMedia|SubmitForm|"
    rb"ImportData|GoToR|GoToE|Metadata|Names|FileAttachment|Encrypt)(?![A-Za-z0-9_])"
)
_PAGINA_TENUTE = (
    "/Type", "/MediaBox", "/CropBox", "/BleedBox", "/TrimBox", "/ArtBox", "/Rotate", "/Resources", "/Contents",
    "/Annots", "/UserUnit", "/Group",
)
_ANNOTAZIONI_SICURE = frozenset({
    "/Text", "/Highlight", "/Underline", "/StrikeOut", "/Squiggly", "/FreeText", "/Line", "/Square", "/Circle",
    "/Polygon", "/PolyLine", "/Ink", "/Stamp", "/Caret",
})
_ANNOTAZIONE_TENUTE = (
    "/Type", "/Subtype", "/Rect", "/Contents", "/AP", "/F", "/C", "/CA", "/QuadPoints", "/L", "/Vertices", "/InkList",
    "/BS", "/Border", "/IC", "/LE", "/DA", "/Q", "/RC", "/T", "/Name",
)


class Errore(Exception):
    """Un motivo breve per cui la conversione non da' nessuna copia."""


def _scrivi(esito: dict, corpo: bytes = b"") -> None:
    json_ = json.dumps(esito, separators=(",", ":")).encode()
    out = sys.stdout.buffer
    out.write(struct.pack(">I", len(json_)) + json_ + struct.pack(">I", len(corpo)) + corpo)
    out.flush()


# --------------------------------------------------------------------------- testo
def converti_testo(dati: bytes) -> tuple[bytes, dict]:
    """Lo stesso testo in UTF-8: righe con \\n, niente caratteri di controllo ne' invisibili, tetto 256 KiB."""
    testo = dati[:MAX_TESTO_ENTRATA].decode("utf-8", errors="replace")
    pulito = []
    for c in testo.replace("\r\n", "\n").replace("\r", "\n"):
        if c in "\n\t" or (unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")):
            pulito.append(c)
    uscita = "".join(pulito).encode("utf-8")
    tagliato = len(dati) > MAX_TESTO_ENTRATA or len(uscita) > MAX_TESTO_USCITA
    if len(uscita) > MAX_TESTO_USCITA:
        uscita = uscita[:MAX_TESTO_USCITA].decode("utf-8", errors="ignore").encode("utf-8")
    return uscita, {"estensione": "txt", "tagliato": tagliato}


# --------------------------------------------------------------------------- PDF
def _pulisci_annotazioni(pagina) -> None:
    from pypdf.generic import ArrayObject, NameObject

    annotazioni = pagina.get("/Annots")
    if annotazioni is None:
        return
    tenute = ArrayObject()
    for riferimento in annotazioni.get_object():
        a = riferimento.get_object()
        if str(a.get("/Subtype")) not in _ANNOTAZIONI_SICURE or "/A" in a or "/AA" in a:
            continue  # moduli, link con azione, file incorporati, multimedia, 3D: via
        for chiave in [k for k in list(a.keys()) if k not in _ANNOTAZIONE_TENUTE]:
            del a[NameObject(chiave)]
        tenute.append(riferimento)
    if tenute:
        pagina[NameObject("/Annots")] = tenute
    else:
        del pagina["/Annots"]


def converti_pdf(dati: bytes) -> tuple[bytes, dict]:
    """Documento nuovo con le sole pagine (copiate e ripulite). Cifrato, troppo lungo o storto = niente copia."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject

    lettore = PdfReader(io.BytesIO(dati), strict=False)
    if lettore.is_encrypted:
        raise Errore("cifrato")
    pagine = len(lettore.pages)
    if pagine == 0 or pagine > MAX_PAGINE:
        raise Errore("pagine")
    scrittore = PdfWriter()
    for pagina in lettore.pages:
        for chiave in [k for k in list(pagina.keys()) if k not in _PAGINA_TENUTE]:
            if chiave != "/Parent":
                del pagina[NameObject(chiave)]
        _pulisci_annotazioni(pagina)
        scrittore.add_page(pagina)
    buf = io.BytesIO()
    scrittore.write(buf)
    corpo = buf.getvalue()
    if len(corpo) > MAX_USCITA_BYTE:
        raise Errore("troppo_grande")
    if _PROIBITE.search(corpo):
        raise Errore("resti_pericolosi")
    if len(PdfReader(io.BytesIO(corpo), strict=True).pages) != pagine:
        raise Errore("verifica")
    return corpo, {"estensione": "pdf", "tagliato": False, "pagine": pagine}


# --------------------------------------------------------------------------- ffmpeg
def _formato_ingresso(dati: bytes, tipo: str) -> str:
    """Il demuxer di ffmpeg scelto dai byte (mai dal nome): lista chiusa, niente playlist, concat, hls o dash."""
    testa = dati[:16]
    if dati[4:8] == b"ftyp":
        return "mov"
    if tipo == "audio":
        if testa.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
            return "mp3"
        if testa.startswith((b"\xff\xf1", b"\xff\xf9")):
            return "aac"
        for firma, nome in ((b"OggS", "ogg"), (b"fLaC", "flac"), (b"#!AMR", "amr")):
            if testa.startswith(firma):
                return nome
        if testa[:4] == b"RIFF" and testa[8:12] == b"WAVE":
            return "wav"
        if testa[:4] == b"FORM" and testa[8:12] in (b"AIFF", b"AIFC"):
            return "aiff"
    else:
        if testa.startswith(b"\x1a\x45\xdf\xa3"):
            return "matroska"
        if testa[:4] == b"RIFF" and testa[8:12] == b"AVI ":
            return "avi"
        if testa.startswith(b"FLV\x01"):
            return "flv"
        if testa.startswith(b"\x00\x00\x01\xba"):
            return "mpeg"
    raise Errore("formato")


def _comando(nome: str) -> str:
    percorso = shutil.which(nome)
    if percorso is None:
        raise FileNotFoundError(nome)
    return percorso


def _esegui(argv: list[str], secondi: float, cartella: Path, catturare: bool = False) -> bytes:
    try:
        r = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if catturare else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=secondi, cwd=cartella, env={"PATH": os.environ.get("PATH", "")}, check=False,
        )
    except subprocess.TimeoutExpired as errore:
        raise Errore("tempo") from errore
    if r.returncode != 0:
        raise Errore("ffmpeg")
    return r.stdout or b""


def _sonda(formato: str, ingresso: Path, cartella: Path) -> dict:
    argv = [
        _comando("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe", "-f", formato, "-print_format", "json",
        "-show_entries", "format=duration:stream=codec_type,width,height,channels", "-i", str(ingresso),
    ]
    try:
        return json.loads(_esegui(argv, SECONDI_SONDA, cartella, catturare=True))
    except json.JSONDecodeError as errore:
        raise Errore("sonda") from errore


def _durata(sonda: dict) -> float:
    try:
        return float((sonda.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        return 0.0


def _base(formato: str, ingresso: Path) -> list[str]:
    return [
        _comando("ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file,pipe",
        "-f", formato, "-i", str(ingresso),
    ]


def _leggi_uscita(percorso: Path) -> bytes:
    if not percorso.is_file() or percorso.stat().st_size == 0 or percorso.stat().st_size > MAX_USCITA_BYTE:
        raise Errore("uscita")
    return percorso.read_bytes()


def converti_audio(dati: bytes, ingresso: Path, cartella: Path, secondi: float) -> tuple[bytes, dict]:
    formato = _formato_ingresso(dati, "audio")
    sonda = _sonda(formato, ingresso, cartella)
    flussi = [s for s in sonda.get("streams", []) if s.get("codec_type") == "audio"]
    if not flussi:
        raise Errore("senza_audio")
    canali = 2 if int(flussi[0].get("channels") or 1) >= 2 else 1
    uscita = cartella / "uscita.ogg"
    argv = _base(formato, ingresso) + [
        "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", "-t", str(MAX_SECONDI_AUDIO),
        "-ac", str(canali), "-c:a", "libopus", "-b:a", "64k", "-fflags", "+bitexact", "-flags:a", "+bitexact",
        "-threads", "1", "-f", "ogg", "-y", str(uscita),
    ]
    _esegui(argv, secondi, cartella)
    return _leggi_uscita(uscita), {"estensione": "ogg", "tagliato": _durata(sonda) > MAX_SECONDI_AUDIO + 0.5}


def converti_video(dati: bytes, ingresso: Path, cartella: Path, secondi: float) -> tuple[bytes, dict]:
    formato = _formato_ingresso(dati, "video")
    sonda = _sonda(formato, ingresso, cartella)
    video = [s for s in sonda.get("streams", []) if s.get("codec_type") == "video"]
    if not video:
        raise Errore("senza_video")
    if int(video[0].get("width") or 0) > MAX_LATO_INGRESSO or int(video[0].get("height") or 0) > MAX_LATO_INGRESSO:
        raise Errore("troppo_grande")
    uscita = cartella / "uscita.mp4"
    filtro = "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,format=yuv420p"
    argv = _base(formato, ingresso) + [
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
        "-t", str(MAX_SECONDI_VIDEO), "-vf", filtro, "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
        "-maxrate", "450k", "-bufsize", "900k", "-profile:v", "main", "-c:a", "aac", "-b:a", "64k", "-ac", "2",
        "-movflags", "+faststart", "-fflags", "+bitexact", "-flags", "+bitexact", "-threads", "2", "-f", "mp4",
        "-y", str(uscita),
    ]
    _esegui(argv, secondi, cartella)
    return _leggi_uscita(uscita), {"estensione": "mp4", "tagliato": _durata(sonda) > MAX_SECONDI_VIDEO + 0.5}


# --------------------------------------------------------------------------- ingresso
def converti(tipo: str, percorso: Path, cartella: Path, secondi: float) -> tuple[bytes, dict]:
    dati = percorso.read_bytes()
    vero = riconosci(dati)
    if vero.categoria != CATEGORIA_DEL_TIPO[tipo]:
        raise Errore("tipo")
    if tipo == "testo":
        return converti_testo(dati)
    if tipo == "pdf":
        return converti_pdf(dati)
    if tipo == "audio":
        return converti_audio(dati, percorso, cartella, secondi)
    return converti_video(dati, percorso, cartella, secondi)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in CATEGORIA_DEL_TIPO or not NOME.fullmatch(argv[2]):
        _scrivi({"esito": "errore", "motivo": "argomenti"})
        return 2
    base = Path(os.environ.get("IYOKAI_QUARANTENA_DIR") or "/var/lib/iyokai/quarantena")
    cartella = Path(os.environ.get("IYOKAI_CONV_TMP") or "")
    secondi = float(os.environ.get("IYOKAI_CONV_SECONDI") or 60)
    try:
        if not cartella.is_dir():
            raise Errore("cartella")
        corpo, info = converti(argv[1], base / argv[2], cartella, secondi)
    except FileNotFoundError:
        _scrivi({"esito": "non_disponibile", "motivo": "ffmpeg"})
        return 0
    except ImportError:
        _scrivi({"esito": "non_disponibile", "motivo": "pypdf"})
        return 0
    except Errore as errore:
        _scrivi({"esito": "errore", "motivo": str(errore)})
        return 0
    except Exception as errore:  # decoder o parser: qualunque cosa e' un rifiuto
        _scrivi({"esito": "errore", "motivo": "conversione", "dettaglio": type(errore).__name__})
        return 0
    _scrivi({"esito": "ok", **info}, corpo)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
