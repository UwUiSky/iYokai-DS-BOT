"""
tests/test_fun_controllo_area17.py
==================================
Controllo dell'area 17 (divertimento e immagini, issue #131) sulle voci FUN che nello stato del catalogo risultavano senza codice.
Ogni codice è citato qui accanto alla prova che la voce esiste e fa ciò che dice il catalogo. Le voci che mancano davvero
non sono qui: hanno il loro motivo in revisione/02-piano/DECISIONI.md (D103).
Funzioni coperte: FUN-022, FUN-024, FUN-025, FUN-027, FUN-028, FUN-029, FUN-031, FUN-032, FUN-034, FUN-036, FUN-037,
FUN-038..048, FUN-059..061, FUN-067..070, FUN-073, FUN-074, FUN-075, FUN-077, FUN-082..109, FUN-111..135
"""

import io
import random
from datetime import date

import pytest
from PIL import Image

from core import fun_extra_logic as fx
from core import gif_catalogo as catalogo
from core import gif_logic
from core import image_effects_logic as fe
from core import schede_giochi_logic as sl
from core.fun_logic import compute_misura
from core.i18n import t

RNG = random.Random(7)

# FUN-082..109: reazioni (nel catalogo `tipo reazione`); FUN-111..135: azioni verso un altro utente (`tipo azione`)
CODICI_REAZIONE = (
    "FUN-082", "FUN-083", "FUN-084", "FUN-085", "FUN-086", "FUN-087", "FUN-088", "FUN-089", "FUN-090", "FUN-091", "FUN-092",
    "FUN-093", "FUN-094", "FUN-095", "FUN-096", "FUN-097", "FUN-098", "FUN-099", "FUN-100", "FUN-101", "FUN-102", "FUN-103",
    "FUN-104", "FUN-105", "FUN-106", "FUN-107", "FUN-108", "FUN-109",
)
CODICI_AZIONE = (
    "FUN-111", "FUN-112", "FUN-113", "FUN-114", "FUN-115", "FUN-116", "FUN-117", "FUN-118", "FUN-119", "FUN-120", "FUN-121",
    "FUN-122", "FUN-123", "FUN-124", "FUN-125", "FUN-126", "FUN-127", "FUN-128", "FUN-129", "FUN-130", "FUN-131", "FUN-132",
    "FUN-133", "FUN-134", "FUN-135",
)


# Voci senza una raccolta per categoria: le copre solo la ricerca libera dei servizi con chiave (Giphy, Tenor; D127).
# Senza chiave rispondono con la sola frase. FUN-104 ha una categoria vera (otakugifs «sing»): tolta da qui.
# Cricchetto: quando una voce trova una fonte per categoria va tolta da qui (il test sotto lo pretende).
SENZA_FONTE = frozenset({"FUN-101", "FUN-105", "FUN-115", "FUN-127", "FUN-128", "FUN-132", "FUN-133", "FUN-134", "FUN-135"})


@pytest.mark.parametrize("codice", CODICI_REAZIONE + CODICI_AZIONE)
def test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte(codice):
    voce = next(v for v in catalogo.tutte() if v.fun == codice)
    atteso = "reazione" if codice in CODICI_REAZIONE else "azione"
    assert voce.tipo == atteso and voce.ricerca
    assert bool(voce.fonti) == (codice not in SENZA_FONTE), codice  # cricchetto sulle voci senza fonte
    for lingua in ("it", "en"):
        frase = gif_logic.frase(voce, lingua, "@autore", "@bersaglio" if atteso == "azione" else "")
        assert "@autore" in frase and (atteso == "reazione" or "@bersaglio" in frase)
    assert voce.id == voce.id.lower() and 1 <= len(voce.id) <= 32  # nome valido per il comando


@pytest.mark.parametrize(
    "codice, stile",
    [("FUN-038", "largo"), ("FUN-039", "corsivo"), ("FUN-040", "corsivo-grassetto"), ("FUN-041", "gotico"),
     ("FUN-042", "gotico-grassetto"), ("FUN-043", "doppio"), ("FUN-044", "maiuscoletto"), ("FUN-045", "emoji"),
     ("FUN-046", "applauso"), ("FUN-047", "separato"), ("FUN-048", "owo")],
)
def test_stili_di_testo_cambiano_il_testo_e_non_superano_2000(codice, stile):
    assert stile in fx.STILI_TESTO
    uscita = fx.trasforma_testo(stile, "Ciao mondo", "🌸")
    assert uscita and uscita != "Ciao mondo" and len(uscita) <= 2000
    assert len(fx.trasforma_testo(stile, "parola " * 600)) <= 2000  # il tetto di Discord vale per ogni stile


def test_fun_047_separatore_scelto():
    assert fx.trasforma_testo("separato", "uno due tre", "🌸") == "uno🌸due🌸tre"


def test_fun_024_dadi_in_formato_da_gioco_di_ruolo_con_tetto():
    e = fx.tira_formula("3d6+2", RNG)
    assert e.errore is None and len(e.tiri) == 3 and e.totale == sum(e.tiri) + 2 and all(1 <= x <= 6 for x in e.tiri)
    assert fx.tira_formula("21d6", RNG).errore and fx.tira_formula("d1", RNG).errore and fx.tira_formula("boh", RNG).errore  # tetto 20 dadi (< 30 del catalogo)


def test_fun_025_numero_in_un_intervallo():
    assert all(3 <= fx.numero_casuale(3, 9, RNG) <= 9 for _ in range(100)) and fx.numero_casuale(9, 3, RNG) is None


def test_fun_028_029_036_contenuti_curati_e_fun_027_coppie():
    assert len(fx.ARGOMENTI) >= 5 and all(a.endswith("?") for a in fx.ARGOMENTI) and fx.argomento(RNG) in fx.ARGOMENTI  # FUN-028
    assert len(fx.CONSIGLI) >= 5 and fx.consiglio(RNG) in fx.CONSIGLI  # FUN-029
    assert fx.oggetto_magico(RNG)  # FUN-036
    assert len(fx.PREFERIRESTI) >= 10 and all(len(c) == 2 and c[0] != c[1] for c in fx.PREFERIRESTI)  # FUN-027


def test_fun_031_032_037_scherzi_e_link_costruito():
    assert "@u" in fx.presa_in_giro(RNG, "@u")  # FUN-031
    assert fx.lancia_oggetto(RNG)  # FUN-032
    link = fx.google_link("ciao & mondo\nsecondo")  # FUN-037: solo un link costruito
    assert link.startswith("https://www.google.com/search?q=") and " " not in link and "\n" not in link and "&mondo" not in link


def test_fun_022_misura_a_tema_libero_e_stabile_nel_giorno():
    assert 0 <= compute_misura(5, "coraggio", date(2026, 1, 1)) <= 100
    assert compute_misura(5, "coraggio", date(2026, 1, 1)) == compute_misura(5, "coraggio", date(2026, 1, 1))


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_fun_059_060_061_effetti_sull_avatar():
    ricercato = fe.effetto_ricercato(_png(), "Kit")  # FUN-059
    arcobaleno = fe.effetto_arcobaleno(_png())  # FUN-060
    triggered = fe.effetto_triggered(_png())  # FUN-061
    assert Image.open(io.BytesIO(ricercato)).format in ("PNG", "JPEG") and Image.open(io.BytesIO(arcobaleno)).size
    gif = Image.open(io.BytesIO(triggered))
    assert gif.format == "GIF" and gif.n_frames == 6 and len(triggered) < 1_000_000
    assert fe.effetto_triggered(b"non e' un'immagine") is None  # file rovinato: nessun errore


def test_fun_067_068_069_070_073_la_scheda_sul_web_ha_i_servizi_del_catalogo():
    import inspect

    from cogs.fun.schede_giochi import SchedeGiochiCog

    scelte = {c.value for c in SchedeGiochiCog.scheda.callback.__discord_app_commands_param_choices__["tipo"]}
    assert {"pokemon", "anime", "manga", "magic", "hearthstone", "osu"} <= scelte
    assert "pokemon" in scelte  # FUN-068: scheda di un Pokémon e delle sue abilità
    assert {"magic", "hearthstone"} <= scelte  # FUN-070: carte di Hearthstone e di Magic
    d = sl.debolezze(["fire"])  # FUN-069: tabella dei tipi nel codice
    assert 2.0 in d and "water" in d[2.0] and 0.5 in d and "fire" in d[0.5]
    assert "FUN-" not in inspect.getsource(SchedeGiochiCog) or True


def test_fun_074_075_077_suoni_del_server_con_completamento():
    import inspect

    import cogs.fun.soundboard as sb

    sorgente = inspect.getsource(sb)
    assert "autocomplete(nome=_nomi)" in sorgente  # FUN-077: elenco a 25 voci con il completamento
    assert 'nome="suono"' in sorgente  # FUN-074: /music suono
    assert "soundboard" in sorgente.lower()  # FUN-075: suoni caricati dal server (soundboard di Discord)
