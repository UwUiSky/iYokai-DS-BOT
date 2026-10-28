"""
scripts/genera_moneta_iyokai.py
===============================
Disegna la moneta di iYokai (assets/moneta_iyokai.png), usata quando un
server non ha scelto un'immagine per la sua moneta.
Funzioni coperte: D38

Uso: python3 scripts/genera_moneta_iyokai.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

LATO = 128
SS = 4  # si disegna 4 volte più grande e poi si riduce, per bordi lisci


def disegna() -> Image.Image:
    n = LATO * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 4 * SS
    d.ellipse((m, m, n - m, n - m), fill=(176, 120, 20, 255))  # bordo scuro
    d.ellipse((m + 5 * SS, m + 5 * SS, n - m - 5 * SS, n - m - 5 * SS), fill=(245, 192, 52, 255))
    d.ellipse((m + 14 * SS, m + 14 * SS, n - m - 14 * SS, n - m - 14 * SS), outline=(200, 140, 30, 255), width=3 * SS)
    # una «Y» stilizzata al centro
    c, w = n // 2, 9 * SS
    col = (120, 78, 10, 255)
    d.line((c - 20 * SS, c - 24 * SS, c, c + 2 * SS), fill=col, width=w)
    d.line((c + 20 * SS, c - 24 * SS, c, c + 2 * SS), fill=col, width=w)
    d.line((c, c + 2 * SS, c, c + 28 * SS), fill=col, width=w)
    return img.resize((LATO, LATO), Image.LANCZOS)


if __name__ == "__main__":
    percorso = Path(__file__).resolve().parent.parent / "assets" / "moneta_iyokai.png"
    disegna().save(percorso, format="PNG", optimize=True)
    print(percorso, percorso.stat().st_size, "byte")
