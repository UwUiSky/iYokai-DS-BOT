"""
tests/test_automod_parole_logic.py
==================================
AMD-014: filtro delle parole vietate con normalizzazione (core/automod_parole_logic.py).
Logica pura, senza Discord. Le voci vietate si costruiscono dal file dati di base.
"""

import time

import pytest

from core.automod_parole_logic import carica_base, costruisci, normalizza, trova

F = costruisci(True)
N = "nigger"


def _trovato(testo, filtro=F):
    return trova(testo, filtro) is not None


# Una forma per riga: ognuna e' un modo diverso di nascondere la stessa parola.
AGGIRAMENTI = [
    "nigger", "NIGGER", "NiGgEr", "nigg3r", "n1gg3r", "n!gg3r", "n|gg3r", "nigg3rs", "niiiiggggerrr",
    "ñíggér", "ｎｉｇｇｅｒ", "𝐧𝐢𝐠𝐠𝐞𝐫", "ⓃⒾⒼⒼⒺⓇ", "🇳🇮🇬🇬🇪🇷", "🅝🅘🅖🅖🅔🅡",
    "ɴɪɢɢᴇʀ", "nіgger",  # i cirillica
    "nigger", "n​i​g​g​e​r", "ni­gger", "n*i*g*g*e*r", "n_i_g_g_e_r", "||n||igger", "~~nigger~~", "`nigger`",
    "n i g g e r", "n.i.g.g.e.r", "n-i-g-g-e-r", "n🔥i🔥g🔥g🔥e🔥r", "n i gg er", "ni gger",
    "ciaonigger", "niggerlover", "n\ni\ng\ng\ne\nr", "ᶰⁱᵍᵍᵉʳ", "Nlgger",
    "frase normale poi n1gg3r in mezzo", "n̷i̷g̷g̷e̷r̷",
]


@pytest.mark.parametrize("testo", AGGIRAMENTI)
def test_aggiramenti_riconosciuti(testo):
    assert _trovato(testo), normalizza(testo)


@pytest.mark.parametrize(
    "testo",
    ["f4gg0t", "FAGGOTS", "k1k3", "k i k e", "fr0c10", "r1cch10n3", "negr0", "t3rr0n3", "ch1nk", "sp1c", "wetb4ck"],
)
def test_altre_voci_con_cifre_e_separatori(testo):
    assert _trovato(testo)


def test_frase_con_voce_propria_e_unita():
    f = costruisci(False, ("porco dio",))
    assert _trovato("porco dio", f)
    assert _trovato("p0rc0d10", f)
    assert _trovato("p o r c o d i o", f)
    assert not _trovato("il porco mangia", f)


def test_voce_propria_con_normalizzazione():
    f = costruisci(False, ("scemo",))
    assert _trovato("sc3m0", f) and _trovato("s c e m o", f)
    assert not _trovato("nigger", f)  # la base e' spenta


def test_base_spenta_non_scatta():
    assert not _trovato(N, costruisci(False))


def test_parole_lecite_dell_admin():
    f = costruisci(True, (), ("negro",))
    assert not _trovato("rio negro", f)
    assert _trovato("negro", F)


LECITE = [
    "Il Niger e uno Stato africano", "the Niger river", "he started to snigger", "sniggering behind her back",
    "a niggardly offer", "cocoon", "raccoon", "retardant foam", "Montenegro e bellissimo", "Negroni sbagliato",
    "assassin", "classic", "grass", "Scunthorpe", "cockpit", "Dikes and dams", "I am bigger than you",
    "nigeria", "tigger", "digger", "trigger warning", "figure", "faggio",
]


@pytest.mark.parametrize("testo", LECITE)
def test_testi_leciti_non_scattano(testo):
    assert not _trovato(testo), normalizza(testo)


CORPUS_ITALIANO = [
    "Ciao a tutti, stasera giochiamo alle 21 sul server, chi viene?",
    "Ho comprato 3 mele, 4 pere e 10 arance al mercato di Roma.",
    "La partita e finita 2 a 1, ha segnato al 90 minuto.",
    "Domani vado a trovare mia nonna a Napoli, poi passo da Bologna.",
    "Non ho capito la regola del gioco, qualcuno puo spiegarmela?",
    "Il codice di errore 404 significa che la pagina non esiste.",
    "Ti ho mandato 15 euro con il bonifico, controlla il conto.",
    "Che bella giornata, andiamo al mare con gli amici e la famiglia!",
    "Il treno delle 7 e 45 e in ritardo di dieci minuti, che noia.",
    "Per favore leggi il regolamento prima di scrivere nel canale.",
    "Marco Negri ha parlato ieri alla riunione del club.",
    "Una a b c d e f g h i l m n o p q r s t u v z della tastiera.",
    "Vado a fare la spesa: pane, latte, uova, pasta e frutta.",
    "w il re, e un classico del 1999 con 3 premi e 2 candidature",
    "Ho un cane che si chiama Fido e un gatto che si chiama Pippo.",
    "Il cassiere ha detto che costa 12,50 euro, un po troppo.",
]
CORPUS_INGLESE = [
    "Hey everyone, are we playing tonight at 9pm on the usual server?",
    "I bought 3 apples and 4 pears, then went to the gym for an hour.",
    "The final score was 2 to 1, he scored in the 90th minute.",
    "Please read the rules before posting in the general channel.",
    "That was a great game, GG everyone, see you tomorrow!",
    "My cat is in the cocoon of blankets again, what a cutie.",
    "The raccoon got into the garbage, again. Classic.",
    "He started to snigger when the teacher dropped the chalk.",
    "The Niger and the Congo are two of the longest rivers in Africa.",
    "A fog came over the bay and the ferry was late.",
    "Can someone help me with this error? It says exit code 1 and 0 warnings.",
    "Check out this link and tell me what you think about the new update.",
    "I like the new update, the dikes in the map look amazing.",
    "She bought a bigger trigger guard for the toy and a digger for the kid.",
    "We shipped v2.3.1 at 5pm, then rolled back at 7 because of a bug.",
    "Go to Settings > Privacy and turn off 2 of the 3 options, then restart.",
]


@pytest.mark.parametrize("testo", CORPUS_ITALIANO + CORPUS_INGLESE)
def test_corpus_normale_non_scatta(testo):
    assert not _trovato(testo), normalizza(testo)


def test_testo_lungo_4000_caratteri_e_veloce():
    peggiori = [
        "a" * 4000, "n " * 2000, ("n i g " * 800)[:4000], ("nig" * 1333)[:4000], "||" * 2000,
        ("n🔥" * 2000), ("ab12 " * 800)[:4000], "nigge" * 800, ("ni" + "g" * 3998),
    ]
    for testo in peggiori:
        inizio = time.perf_counter()
        trova(testo, F)
        assert time.perf_counter() - inizio < 0.5, testo[:20]
    assert _trovato("x" * 3900 + " n1gg3r")


def test_file_dati_ha_voci_e_lecite():
    voci, lecite = carica_base()
    assert len(voci) > 40 and "niger" in lecite
