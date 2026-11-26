"""
tests/test_sandbox_obbligatoria.py
==================================
Blocco B: ogni file degli utenti si apre SOLO nella sandbox. Cricchetti sul codice (AST: nessuna apertura di
immagini, PDF o archivi fuori dai moduli della sandbox; il worker non parte dal bot) e prove del cliente
`apri_in_sandbox`: senza servizio, senza isolamento, dentro l'event loop, file rotti e bombe di pixel.
Funzioni coperte: SPEC §6 (D62), SICUREZZA.md §2
"""

import ast
import asyncio
import io
from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError

from core import immagini_quarantena as q
from core import immagini_sandbox as sb
from core import safe_image as si
from tests.support import immagini_finte as f

RADICE = Path(__file__).resolve().parent.parent
CARTELLE = ("core", "cogs", "scripts")
# Gli unici moduli che aprono i byte di un utente: girano dentro il processo figlio della sandbox.
MODULI_SANDBOX = {"core/immagini_decodifica.py", "core/immagini_worker.py", "core/conversioni_worker.py"}
# Archivi aperti per leggerli: solo la patch a caldo dell'owner (spenta in produzione, D7), mai un file di un utente.
ARCHIVI_NON_UTENTE = {"core/hot_patch.py"}
SOLO_SERVIZIO = {"core/immagini_sandbox.py", "core/immagini_servizio.py"}


def _file_del_bot():
    for cartella in CARTELLE:
        for p in sorted((RADICE / cartella).rglob("*.py")):
            yield p.relative_to(RADICE).as_posix(), ast.parse(p.read_text(encoding="utf-8"))
    yield "main.py", ast.parse((RADICE / "main.py").read_text(encoding="utf-8"))


def _alias_di_pil_image(albero) -> set[str]:
    nomi = set()
    for n in ast.walk(albero):
        if isinstance(n, ast.ImportFrom) and n.module == "PIL":
            nomi |= {a.asname or a.name for a in n.names if a.name == "Image"}
        if isinstance(n, ast.Import):
            nomi |= {a.asname for a in n.names if a.name == "PIL.Image" and a.asname}
    return nomi


def _aperture_vietate(percorso: str, albero) -> list[str]:
    trovate = []
    alias = _alias_di_pil_image(albero)
    for n in ast.walk(albero):
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] in ("pillow_heif", "pypdf", "PyPDF2"):
            trovate.append(f"{percorso}:{n.lineno} import da {n.module}")
        if isinstance(n, ast.ImportFrom) and n.module == "PIL.Image" and any(a.name == "open" for a in n.names):
            trovate.append(f"{percorso}:{n.lineno} from PIL.Image import open")
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in ("pillow_heif", "pypdf", "PyPDF2"):
                    trovate.append(f"{percorso}:{n.lineno} import {a.name}")
        if isinstance(n, ast.Call):
            fn = n.func
            if isinstance(fn, ast.Attribute) and fn.attr == "open" and isinstance(fn.value, ast.Name) and fn.value.id in alias:
                trovate.append(f"{percorso}:{n.lineno} Image.open")
            if isinstance(fn, ast.Attribute) and fn.attr == "open" and isinstance(fn.value, ast.Attribute) and fn.value.attr == "Image":
                trovate.append(f"{percorso}:{n.lineno} PIL.Image.open")
            nome = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if nome in ("safe_open_image", "PdfReader", "register_heif_opener"):
                trovate.append(f"{percorso}:{n.lineno} {nome}")
            if nome == "ZipFile" and percorso not in ARCHIVI_NON_UTENTE:
                modo = n.args[1] if len(n.args) > 1 else next((k.value for k in n.keywords if k.arg == "mode"), None)
                if not (isinstance(modo, ast.Constant) and modo.value == "w"):
                    trovate.append(f"{percorso}:{n.lineno} ZipFile in lettura")
    return trovate


def test_nessuna_apertura_di_file_fuori_dalla_sandbox():
    trovate = []
    for percorso, albero in _file_del_bot():
        if percorso not in MODULI_SANDBOX:
            trovate += _aperture_vietate(percorso, albero)
    assert not trovate, "I byte di un utente si aprono solo nella sandbox:\n" + "\n".join(trovate)


def test_il_cricchetto_vede_le_aperture_vietate():
    albero = ast.parse(
        "from PIL import Image as I\nimport pypdf\nfrom core.x import safe_open_image\n"
        "I.open(b)\nsafe_open_image(b)\nzipfile.ZipFile(b)\nzipfile.ZipFile(b, 'w')\n"
    )
    trovate = _aperture_vietate("x.py", albero)
    assert len(trovate) == 4, trovate


def test_il_decoder_e_il_worker_non_sono_importati_dal_bot():
    for percorso, albero in _file_del_bot():
        if percorso in MODULI_SANDBOX:
            continue
        for n in ast.walk(albero):
            moduli = [n.module or ""] + [a.name for a in n.names] if isinstance(n, ast.ImportFrom) else (
                [a.name for a in n.names] if isinstance(n, ast.Import) else []
            )
            for m in moduli:
                assert not m.endswith(("immagini_decodifica", "immagini_worker", "conversioni_worker")), f"{percorso}:{n.lineno} importa {m}"


def test_il_worker_parte_solo_dal_servizio():
    for percorso, albero in _file_del_bot():
        if percorso in SOLO_SERVIZIO:
            continue
        for n in ast.walk(albero):
            nome = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else ""
            assert nome not in ("esegui_locale", "comando_worker", "comando_conversione", "WORKER", "WORKER_CONVERSIONI"), (
                f"{percorso}:{n.lineno} usa {nome}: il worker lo avvia solo il servizio iyokai-sandbox"
            )


def test_nessun_ripiego_con_unshare():
    for p in (RADICE / "core").glob("*.py"):
        assert "unshare" not in p.read_text(encoding="utf-8").replace("`unshare`", ""), p.name
    assert not hasattr(sb, "MODO_RIDOTTA") and not hasattr(sb, "_unshare_funziona")


# ------------------------------------------------------------------ cliente
@pytest.fixture
def quarantena(tmp_path, monkeypatch):
    monkeypatch.setenv(q.VARIABILE_CARTELLA, str(tmp_path))
    return tmp_path


def test_immagine_vera_torna_come_pixel_senza_lasciare_file(quarantena):
    img = si.apri_in_sandbox(f.png(50, 40))
    assert img.size == (50, 40) and img.format == "PNG" and img.mode in ("RGB", "RGBA")
    assert list(quarantena.iterdir()) == []


def test_il_lato_viene_ridotto_dalla_sandbox(quarantena):
    assert max(si.apri_in_sandbox(f.png(900, 300), max_side=100).size) <= 100


def test_senza_servizio_si_rifiuta(quarantena, tmp_path, monkeypatch):
    monkeypatch.setenv(sb.VARIABILE_SOCKET, str(tmp_path / "non-esiste"))
    with pytest.raises(si.SandboxNonDisponibile):
        si.apri_in_sandbox(f.png())
    assert list(quarantena.iterdir()) == []


def test_senza_isolamento_si_rifiuta(quarantena, monkeypatch):
    monkeypatch.setattr(sb, "_interfacce_di_rete", lambda: ["lo", "eth0"])
    with pytest.raises(si.SandboxNonDisponibile):
        si.apri_in_sandbox(f.png())


def test_file_rotto_e_formato_sbagliato(quarantena):
    with pytest.raises(UnidentifiedImageError):
        si.apri_in_sandbox(b"questo non e' un'immagine" * 10)
    with pytest.raises(UnidentifiedImageError):
        si.apri_in_sandbox(f.jpeg(), formati=("PNG",))  # un JPEG dove si ammette solo PNG


def test_bomba_di_pixel_si_rifiuta(quarantena):
    with pytest.raises(si.ImmagineTroppoGrande):
        si.apri_in_sandbox(f.png_dichiarato(60000, 60000))


def test_oltre_il_tetto_di_byte_non_arriva_nemmeno_alla_sandbox(quarantena):
    with pytest.raises(si.ImmagineTroppoGrande):
        si.apri_in_sandbox(b"\x00" * (si.MAX_IMAGE_BYTES + 1))
    assert list(quarantena.iterdir()) == []


@pytest.mark.asyncio
async def test_dentro_l_event_loop_non_si_blocca_ma_si_rifiuta(quarantena):
    with pytest.raises(RuntimeError):
        si.apri_in_sandbox(f.png())
    img = await asyncio.to_thread(si.apri_in_sandbox, f.png(20, 20))
    assert img.size == (20, 20)


def test_risposta_incoerente_si_rifiuta():
    r = sb.RisultatoSandbox("ok", {"modo": "RGBA", "larghezza": 10, "altezza": 10}, b"\x00" * 7)
    with pytest.raises(si.SandboxNonDisponibile):
        si._immagine_da(r)
    for esito in ("non_disponibile", "non_isolata", "ucciso", "ucciso_tempo", "uscita_enorme"):
        with pytest.raises(si.SandboxNonDisponibile):
            si._immagine_da(sb.RisultatoSandbox(esito))


def test_nessun_posto_libero_si_rifiuta(quarantena, monkeypatch):
    class Pieno:
        def acquire(self, timeout=None):
            return False

        def release(self):
            raise AssertionError("mai preso")

    monkeypatch.setattr(si, "_POSTI_SANDBOX", Pieno())
    with pytest.raises(si.SandboxNonDisponibile):
        si.apri_in_sandbox(f.png())


# ------------------------------------------------------------------ errori che non si nascondono
CHIAMATE_SANDBOX = {"apri_in_sandbox", "run_image_task", "run_spam_trap_image_task"}


# Lavori di solo disegno: nessun byte di un utente (grafici, tabelle, caselle gia' nel database).
SOLO_DISEGNO = {
    "render_cartella", "render_casa", "disegna", "disegna_testo", "disegna_boss", "render_bar_chart",
    "render_growth_chart", "render_line_chart", "disegna_sfondo_pronto",
}


def _chiama(n: ast.AST) -> bool:
    for c in ast.walk(n):
        if isinstance(c, ast.Call):
            fn = c.func
            nome = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if nome in CHIAMATE_SANDBOX:
                primo = c.args[0] if c.args else None
                if nome != "apri_in_sandbox" and isinstance(primo, ast.Name) and primo.id in SOLO_DISEGNO:
                    continue
                return True
    return False


def _nomi_gestiti(h: ast.ExceptHandler) -> set[str]:
    if h.type is None:
        return {"BaseException"}
    tipi = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    return {t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else "" for t in tipi}


def _gestori_che_nascondono(percorso: str, albero) -> list[str]:
    trovati = []
    for n in ast.walk(albero):
        if not isinstance(n, ast.Try) or not any(_chiama(s) for s in n.body):
            continue
        visti = set()
        for h in n.handlers:
            nomi = _nomi_gestiti(h)
            if "SandboxNonDisponibile" in nomi:
                visti.add("sandbox")
            if nomi & {"Exception", "BaseException"} and "sandbox" not in visti:
                trovati.append(f"{percorso}:{h.lineno}")
    return trovati


def test_un_gestore_largo_non_nasconde_la_sandbox_ferma():
    """`except Exception` attorno a un lavoro sandbox deve avere PRIMA un gestore di SandboxNonDisponibile."""
    trovati = []
    for percorso, albero in _file_del_bot():
        if percorso not in MODULI_SANDBOX and percorso != "core/safe_image.py":
            trovati += _gestori_che_nascondono(percorso, albero)
    assert not trovati, "Gestore largo senza SandboxNonDisponibile prima:\n" + "\n".join(trovati)


def test_il_cricchetto_dei_gestori_vede_il_caso_storto():
    storto = ast.parse("try:\n    apri_in_sandbox(b)\nexcept Exception:\n    pass\n")
    giusto = ast.parse("try:\n    apri_in_sandbox(b)\nexcept SandboxNonDisponibile:\n    raise\nexcept Exception:\n    pass\n")
    assert _gestori_che_nascondono("x.py", storto) and not _gestori_che_nascondono("x.py", giusto)


def test_l_unita_systemd_ha_tutte_le_protezioni():
    testo = (RADICE / "deploy" / "systemd" / "iyokai-sandbox.service").read_text(encoding="utf-8")
    righe = {r.strip() for r in testo.splitlines() if r.strip() and not r.startswith("#")}
    richieste = {
        "User=iyokai-sbx", "PrivateNetwork=yes", "RestrictAddressFamilies=AF_UNIX", "IPAddressDeny=any",
        "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateDevices=yes", "NoNewPrivileges=yes",
        "CapabilityBoundingSet=", "RestrictNamespaces=yes", "SystemCallArchitectures=native", "MemorySwapMax=0",
        "LimitCORE=0", "Restart=on-failure",
    }
    assert richieste <= righe, f"mancano: {sorted(richieste - righe)}"
    assert any(r.startswith("MemoryMax=") for r in righe) and any(r.startswith("TasksMax=") for r in righe)
    assert any(r.startswith("SystemCallFilter=") for r in righe)
