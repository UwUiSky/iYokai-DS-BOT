"""
core/captcha_image.py
=====================
Captcha a immagine: genera il codice, lo disegna storto con un po' di
disturbo e dice se la risposta e' giusta, scaduta o se i tentativi sono finiti.
Funzioni coperte: SPEC §22 (NF-18), VER-002 (lunghezza, misura e colore regolabili), VER-003 (codice nuovo a richiesta, con i tentativi già usati)

Limiti: immagine piccola (200x80, PNG di pochi KB), codice di 5 caratteri
senza lettere ambigue (0/O, 1/I/L), tempo massimo e tentativi contati dalla sfida.
"""

from __future__ import annotations

import io
import math
import random
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LUNGHEZZA_CODICE = 5
LUNGHEZZE = (4, 8)  # VER-002: minimo e massimo del codice
MISURE = {"piccola": 0.8, "media": 1.0, "grande": 1.3}
MAX_LUNGHEZZA_RISPOSTA = LUNGHEZZE[1] + 3
LUMINOSITA_MASSIMA = 150  # un colore più chiaro di così non si legge sullo sfondo chiaro
ALFABETO = "ACDEFGHJKMNPQRSTUVWXYZ2345679"  # niente 0/O, 1/I/L, 8/B
LARGHEZZA = 200
ALTEZZA = 80
TEMPO_MASSIMO_SECONDI = 180
TENTATIVI_MASSIMI = 3
RINNOVI_MASSIMI = 3  # VER-003: quante volte si può chiedere un codice nuovo nella stessa prova
ETICHETTA_MAX = 45  # il campo del modulo accetta al massimo 45 caratteri di etichetta

TIPO_TESTO = "testo"
TIPO_IMMAGINE = "immagine"
TIPI = (TIPO_TESTO, TIPO_IMMAGINE)


def lunghezza_valida(valore) -> int:
    """La lunghezza scelta dal server, riportata entro i limiti (valori strani: quella di base)."""
    if not isinstance(valore, int) or isinstance(valore, bool):
        return LUNGHEZZA_CODICE
    return max(LUNGHEZZE[0], min(LUNGHEZZE[1], valore))


def colore_leggibile(rgb: int) -> bool:
    """VER-002: il colore delle lettere deve restare scuro abbastanza da leggersi."""
    r, g, b = (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255
    return 0 <= rgb <= 0xFFFFFF and 0.299 * r + 0.587 * g + 0.114 * b <= LUMINOSITA_MASSIMA


def genera_codice(rng: secrets.SystemRandom | random.Random | None = None, lunghezza: int = LUNGHEZZA_CODICE) -> str:
    """Un codice casuale di `lunghezza` caratteri (4-8) presi da ALFABETO."""
    rng = rng or secrets.SystemRandom()
    return "".join(rng.choice(ALFABETO) for _ in range(lunghezza_valida(lunghezza)))


def normalizza_risposta(testo: str) -> str:
    """Maiuscole e senza spazi: l'utente puo' scrivere «ab c12»."""
    return "".join(testo.split()).upper()


def risposta_giusta(atteso: str, data: str) -> bool:
    # compare_digest su str accetta solo ASCII: una «e» accentata nella risposta darebbe TypeError.
    return secrets.compare_digest(normalizza_risposta(data).encode("utf-8"), atteso.upper().encode("utf-8"))


def disegna_immagine(
    codice: str, rng: random.Random | None = None, misura: str = "media", colore: int | None = None
) -> bytes:
    """
    PNG con le lettere ruotate e spostate, linee e punti di disturbo, leggero sfocato. VER-002: `misura`
    (piccola, media, grande) scala l'immagine; `colore` (scuro abbastanza) tinge le lettere.
    """
    rng = rng or random.Random()
    scala = MISURE.get(misura, 1.0)
    larghezza = max(LARGHEZZA, 33 * (len(codice) + 1))  # più lettere, più largo: le lettere non si sovrappongono
    if colore is not None and not colore_leggibile(colore):
        colore = None
    base = Image.new("RGB", (larghezza, ALTEZZA), (rng.randint(215, 245),) * 3)
    disegno = ImageDraw.Draw(base)
    for _ in range(6):  # linee sotto le lettere
        disegno.line(
            [(rng.randint(0, larghezza), rng.randint(0, ALTEZZA)), (rng.randint(0, larghezza), rng.randint(0, ALTEZZA))],
            fill=tuple(rng.randint(120, 200) for _ in range(3)), width=rng.randint(1, 2),
        )
    font = ImageFont.load_default(size=44)
    passo = larghezza // (len(codice) + 1)
    for i, carattere in enumerate(codice):
        lettera = Image.new("RGBA", (60, 70), (0, 0, 0, 0))
        ImageDraw.Draw(lettera).text(
            (12, 8), carattere, font=font, fill=_tinta(colore, rng) + (255,)
        )
        lettera = lettera.rotate(rng.uniform(-28, 28), resample=Image.BICUBIC, expand=False)
        base.paste(lettera, (passo // 2 + i * passo - 6, rng.randint(-2, 8)), lettera)
    for _ in range(180):  # punti di disturbo
        disegno.point((rng.randint(0, larghezza - 1), rng.randint(0, ALTEZZA - 1)), fill=(rng.randint(0, 150),) * 3)
    for _ in range(3):  # linee sopra le lettere
        y = rng.randint(10, ALTEZZA - 10)
        disegno.line(
            [(0, y), (larghezza, y + rng.randint(-15, 15))], fill=tuple(rng.randint(40, 120) for _ in range(3)), width=1
        )
    base = _onda(base, rng).filter(ImageFilter.GaussianBlur(0.6))
    if scala != 1.0:
        base = base.resize((int(base.width * scala), int(base.height * scala)), Image.LANCZOS)
    uscita = io.BytesIO()
    base.save(uscita, format="PNG", optimize=True)
    return uscita.getvalue()


def _tinta(colore: int | None, rng: random.Random) -> tuple[int, int, int]:
    """Il colore di una lettera: quello scelto con poca variazione, oppure un grigio-scuro casuale."""
    if colore is None:
        return tuple(rng.randint(10, 110) for _ in range(3))
    base = ((colore >> 16) & 255, (colore >> 8) & 255, colore & 255)
    return tuple(max(0, min(255, c + rng.randint(-15, 15))) for c in base)


def _onda(immagine: Image.Image, rng: random.Random) -> Image.Image:
    """Piega l'immagine con un'onda leggera: le lettere restano leggibili ma non uguali tra loro."""
    ampiezza, fase = rng.uniform(2.0, 3.5), rng.uniform(0, math.tau)
    risultato = Image.new("RGB", immagine.size, (235, 235, 235))
    for x in range(immagine.width):
        scarto = int(ampiezza * math.sin(x / 14 + fase))
        risultato.paste(immagine.crop((x, 0, x + 1, immagine.height)), (x, scarto))
    return risultato


@dataclass
class Sfida:
    """Una prova aperta per un utente: il codice, quando scade, quanti tentativi restano."""

    codice: str
    scade_il: datetime
    tentativi_rimasti: int = TENTATIVI_MASSIMI
    chiusa: bool = field(default=False)
    rinnovi: int = 0

    def rinnova(self, adesso: datetime | None = None, rng=None) -> "Sfida | None":
        """
        VER-003: un codice nuovo con una nuova scadenza. I tentativi già usati restano usati (un codice nuovo non
        è una scorciatoia per riprovare all'infinito) e i rinnovi sono pochi. None se non si può più.
        """
        adesso = adesso or datetime.now(timezone.utc)
        if self.chiusa or self.rinnovi >= RINNOVI_MASSIMI or self.tentativi_rimasti <= 0:
            return None
        self.chiusa = True  # il vecchio codice non vale più
        return Sfida(
            genera_codice(rng, len(self.codice)), adesso + timedelta(seconds=TEMPO_MASSIMO_SECONDI),
            self.tentativi_rimasti, False, self.rinnovi + 1,
        )

    def scaduta(self, adesso: datetime | None = None) -> bool:
        return (adesso or datetime.now(timezone.utc)) >= self.scade_il

    def prova(self, risposta: str, adesso: datetime | None = None) -> str:
        """'ok' | 'sbagliata' (ne restano altre) | 'esaurita' | 'scaduta'. Chiude la sfida a ok, esaurita, scaduta."""
        if self.chiusa or self.scaduta(adesso):
            self.chiusa = True
            return "scaduta"
        if risposta_giusta(self.codice, risposta):
            self.chiusa = True
            return "ok"
        self.tentativi_rimasti -= 1
        if self.tentativi_rimasti <= 0:
            self.chiusa = True
            return "esaurita"
        return "sbagliata"


def nuova_sfida(adesso: datetime | None = None, rng=None, lunghezza: int = LUNGHEZZA_CODICE) -> Sfida:
    adesso = adesso or datetime.now(timezone.utc)
    return Sfida(genera_codice(rng, lunghezza), adesso + timedelta(seconds=TEMPO_MASSIMO_SECONDI))
