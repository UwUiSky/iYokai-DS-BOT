"""
tests/test_ui_base_wiring.py
================================
SEC-10, cricchetto: nessuna classe in cogs/ o core/ deve ereditare
DIRETTAMENTE da discord.ui.View/Modal/LayoutView (deve passare da
core.ui_base.BaseView/BaseModal, che aggiungono il controllo
blacklist), nessun punto deve istanziarle direttamente per una view
costruita dinamicamente, e chi ridefinisce `interaction_check` deve
usare il risultato di `super().interaction_check(...)`.

La scansione legge il codice (AST) e riconosce tutte le forme di
import: `discord.ui.View`, `from discord import ui`, `import
discord.ui as x`, `from discord.ui import View [as Y]`.

KNOWN_RAW_VIEWS contiene i punti che oggi violano questa regola
(REVIEW.md SEC-10). Ogni fix toglie il nome; un nome nuovo fa
fallire il test — stesso principio di KNOWN_UNCALLED in
tests/test_repository_callers.py.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Vuoto: tutte le View/Modal del progetto ereditano già da
# core.ui_base.BaseView/BaseModal (SEC-10). Un nome aggiunto qui
# andrebbe rimosso appena sistemato, mai lasciato per far passare il
# test.
KNOWN_RAW_VIEWS = frozenset()

CLASSI_UI = ("View", "Modal", "LayoutView")

# Le classi che DEFINISCONO il controllo: le due basi (devono per forza
# ereditare da discord.ui) e l'albero dei comandi slash, che ha un
# `interaction_check` suo e non è una View.
DEFINISCONO_IL_CONTROLLO = frozenset(
    {
        "core/ui_base.py::BaseView",
        "core/ui_base.py::BaseModal",
        "core/blacklist_tree.py::BlacklistAwareCommandTree",
    }
)


def _file_da_controllare() -> list[pathlib.Path]:
    return sorted(ROOT.glob("cogs/**/*.py")) + sorted(ROOT.glob("core/**/*.py"))


def _nomi_di_discord_ui(albero: ast.AST) -> tuple[set[str], dict[str, str]]:
    """
    Legge gli import del file e restituisce:
    - i nomi locali che indicano il modulo discord.ui
      (`from discord import ui`, `import discord.ui as dui`);
    - i nomi locali che indicano direttamente una classe UI
      (`from discord.ui import View as Vista` → {"Vista": "View"}).
    """
    moduli_ui: set[str] = set()
    classi: dict[str, str] = {}
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "discord":
            moduli_ui |= {a.asname or a.name for a in nodo.names if a.name == "ui"}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module == "discord.ui":
            classi |= {a.asname or a.name: a.name for a in nodo.names if a.name in CLASSI_UI}
        elif isinstance(nodo, ast.Import):
            moduli_ui |= {a.asname for a in nodo.names if a.name == "discord.ui" and a.asname}
    return moduli_ui, classi


def _classe_ui(espressione: ast.expr, moduli_ui: set[str], classi: dict[str, str]) -> str | None:
    """'View', 'Modal' o 'LayoutView' se l'espressione indica quella
    classe di discord.ui (in qualunque modo sia stata importata),
    altrimenti None."""
    if isinstance(espressione, ast.Name):
        return classi.get(espressione.id)
    if isinstance(espressione, ast.Attribute) and espressione.attr in CLASSI_UI:
        modulo = espressione.value
        if isinstance(modulo, ast.Attribute) and modulo.attr == "ui":
            return espressione.attr  # discord.ui.View
        if isinstance(modulo, ast.Name) and modulo.id in moduli_ui:
            return espressione.attr  # ui.View
    return None


def _chiave(percorso: pathlib.Path, classe: ast.ClassDef) -> str:
    return f"{percorso.relative_to(ROOT).as_posix()}::{classe.name}"


def _violazioni_ereditarieta(percorso: pathlib.Path, testo: str) -> list[str]:
    albero = ast.parse(testo)
    moduli_ui, classi = _nomi_di_discord_ui(albero)
    violazioni = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.ClassDef):
            continue
        if _chiave(percorso, nodo) in DEFINISCONO_IL_CONTROLLO:
            continue
        for base in nodo.bases:
            tipo = _classe_ui(base, moduli_ui, classi)
            if tipo is not None:
                violazioni.append(
                    f"{percorso.relative_to(ROOT)}:{nodo.lineno} class {nodo.name}(discord.ui.{tipo})"
                )
    return violazioni


def _violazioni_istanziazione(percorso: pathlib.Path, testo: str) -> list[str]:
    albero = ast.parse(testo)
    moduli_ui, classi = _nomi_di_discord_ui(albero)
    violazioni = []
    for nodo in ast.walk(albero):
        if not isinstance(nodo, ast.Call):
            continue
        tipo = _classe_ui(nodo.func, moduli_ui, classi)
        if tipo is not None:
            violazioni.append(f"{percorso.relative_to(ROOT)}:{nodo.lineno} discord.ui.{tipo}(...)")
    return violazioni


def _usa_il_risultato_di_super(metodo: ast.AST) -> bool:
    """
    True se dentro `metodo` c'è una chiamata a
    `super().interaction_check(...)` il cui risultato viene usato (in
    un `if`, un `return`, un'assegnazione...). Una chiamata lasciata
    come istruzione a sé butta via il risultato: non conta.
    """
    buttate_via = set()
    for nodo in ast.walk(metodo):
        if isinstance(nodo, ast.Expr):
            valore = nodo.value.value if isinstance(nodo.value, ast.Await) else nodo.value
            buttate_via.add(id(valore))

    for nodo in ast.walk(metodo):
        if not isinstance(nodo, ast.Call) or id(nodo) in buttate_via:
            continue
        func = nodo.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "interaction_check"
            and isinstance(func.value, ast.Call)
            and isinstance(func.value.func, ast.Name)
            and func.value.func.id == "super"
        ):
            return True
    return False


def _violazioni_interaction_check(percorso: pathlib.Path, testo: str) -> list[str]:
    violazioni = []
    for classe in ast.walk(ast.parse(testo)):
        if not isinstance(classe, ast.ClassDef):
            continue
        if _chiave(percorso, classe) in DEFINISCONO_IL_CONTROLLO:
            continue
        for metodo in classe.body:
            if (
                isinstance(metodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                and metodo.name == "interaction_check"
                and not _usa_il_risultato_di_super(metodo)
            ):
                violazioni.append(
                    f"{percorso.relative_to(ROOT)}:{metodo.lineno} "
                    f"{classe.name}.interaction_check senza super()"
                )
    return violazioni


def _tutte_le_violazioni() -> list[str]:
    violazioni = []
    for file in _file_da_controllare():
        testo = file.read_text(encoding="utf-8")
        violazioni += _violazioni_ereditarieta(file, testo)
        violazioni += _violazioni_istanziazione(file, testo)
    return violazioni


def test_nessuna_view_o_modal_raw_in_cogs_e_core():
    trovate = set(_tutte_le_violazioni())

    nuove = sorted(trovate - KNOWN_RAW_VIEWS)
    assert nuove == [], (
        f"View/Modal che ereditano direttamente da discord.ui invece di "
        f"core.ui_base.BaseView/BaseModal (SEC-10): {nuove}"
    )

    sistemate = sorted(KNOWN_RAW_VIEWS - trovate)
    assert sistemate == [], f"Queste non violano più la regola: toglile da KNOWN_RAW_VIEWS: {sistemate}"


def test_le_classi_che_definiscono_il_controllo_esistono_ancora():
    # Un nome rimasto qui dopo una rinomina sarebbe un'esenzione morta.
    esistenti = set()
    for file in _file_da_controllare():
        for nodo in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ClassDef):
                esistenti.add(_chiave(file, nodo))

    assert DEFINISCONO_IL_CONTROLLO <= esistenti


# ============================================================================
# RT-5 — la scansione stessa: deve riconoscere ogni modo di scrivere
# una View/Modal "raw" e ogni interaction_check che scavalca la base.
# ============================================================================

FILE_FINTO = ROOT / "cogs" / "finto.py"


def _violazioni_nel_codice(codice: str) -> list[str]:
    return (
        _violazioni_ereditarieta(FILE_FINTO, codice)
        + _violazioni_istanziazione(FILE_FINTO, codice)
        + _violazioni_interaction_check(FILE_FINTO, codice)
    )


@pytest.mark.parametrize(
    "codice",
    [
        "import discord\nclass V(discord.ui.View): pass",
        "import discord\nclass M(discord.ui.Modal): pass",
        "import discord\nclass L(discord.ui.LayoutView): pass",
        "from discord.ui import View\nclass V(View): pass",
        "from discord.ui import Modal\nclass M(Modal, title='x'): pass",
        "from discord.ui import View as Vista\nclass V(Vista): pass",
        "from discord import ui\nclass V(ui.View): pass",
        "from discord import ui as interfaccia\nclass V(interfaccia.Modal): pass",
        "import discord.ui as dui\nclass V(dui.View): pass",
        "import discord\nvista = discord.ui.View(timeout=None)",
        "from discord.ui import View\nvista = View(timeout=None)",
        "from discord import ui\nvista = ui.View()",
    ],
)
def test_la_scansione_riconosce_view_e_modal_raw(codice):
    assert len(_violazioni_nel_codice(codice)) == 1, codice


@pytest.mark.parametrize(
    "codice",
    [
        "from core.ui_base import BaseView\nclass V(BaseView): pass",
        "from core.ui_base import BaseModal\nvista = BaseModal()",
        # Un'annotazione di tipo non è una View raw.
        "import discord\ndef f() -> discord.ui.View: ...",
        # Una classe che si chiama View ma non viene da discord.ui.
        "from mio_modulo import View\nclass V(View): pass",
        "import discord\nb = discord.ui.Button(label='x')",
    ],
)
def test_la_scansione_non_segnala_il_codice_corretto(codice):
    assert _violazioni_nel_codice(codice) == [], codice


_CON_SUPER = """
from core.ui_base import BaseView
class V(BaseView):
    async def interaction_check(self, interaction):
        if not await super().interaction_check(interaction):
            return False
        return interaction.user.id == 1
"""

_SENZA_SUPER = """
from core.ui_base import BaseView
class V(BaseView):
    async def interaction_check(self, interaction):
        return interaction.user.id == 1
"""

_SUPER_IGNORATO = """
from core.ui_base import BaseView
class V(BaseView):
    async def interaction_check(self, interaction):
        await super().interaction_check(interaction)
        return True
"""

_SUPER_DI_UN_ALTRO_METODO = """
from core.ui_base import BaseModal
class M(BaseModal):
    async def interaction_check(self, interaction):
        await super().on_error(interaction, None)
        return True
"""


def test_interaction_check_che_chiama_super_va_bene():
    assert _violazioni_nel_codice(_CON_SUPER) == []


@pytest.mark.parametrize(
    "codice", [_SENZA_SUPER, _SUPER_IGNORATO, _SUPER_DI_UN_ALTRO_METODO],
    ids=["senza-super", "risultato-di-super-ignorato", "super-di-un-altro-metodo"],
)
def test_interaction_check_che_scavalca_la_blacklist_viene_segnalato(codice):
    violazioni = _violazioni_nel_codice(codice)
    assert len(violazioni) == 1
    assert "interaction_check" in violazioni[0]


def test_ogni_interaction_check_di_cogs_e_core_chiama_super():
    violazioni = []
    for file in _file_da_controllare():
        violazioni += _violazioni_interaction_check(file, file.read_text(encoding="utf-8"))

    assert violazioni == [], (
        "interaction_check ridefinito senza usare super().interaction_check(...): "
        f"il controllo blacklist di BaseView/BaseModal viene saltato (SEC-10): {violazioni}"
    )


def test_la_scansione_guarda_sia_cogs_sia_core():
    cartelle = {file.relative_to(ROOT).parts[0] for file in _file_da_controllare()}
    assert cartelle == {"cogs", "core"}
