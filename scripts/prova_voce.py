"""
scripts/prova_voce.py
=====================
Prova a mano la voce di Yokai: Piper, voce italiana "Paola", con il
filtro e i profili per contesto scelti dall'owner il 05/10/2026 (D22,
issue #142, revisione/02-piano/VOCE_YOKAI.md). Tutto in locale, sul
processore. Non fa parte del bot: serve a regolare i profili.

Preparazione, una volta sola (serve anche ffmpeg):
    pip install sherpa-onnx soundfile numpy
    curl -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-it_IT-paola-medium.tar.bz2
    tar xjf vits-piper-it_IT-paola-medium.tar.bz2

Uso:
    python3 scripts/prova_voce.py                 # un campione per ogni contesto
    python3 scripts/prova_voce.py WELCOME NSFW    # solo quelli indicati

Scrive yokai_<contesto>.wav (senza filtro), _f.wav (filtrato) e .mp3.
"""
import subprocess
from dataclasses import dataclass, replace
import numpy as np
import sherpa_onnx
import soundfile as sf

M = "vits-piper-it_IT-paola-medium"

@dataclass(frozen=True)
class VoiceProfile:
    style: str = "PUBLIC"
    lentezza: float = 1.0      # 1.0 normale; più alto = più lenta
    variazione: float = 0.85   # quanto si muove l'intonazione
    ritmo: float = 1.0         # quanto varia la durata dei suoni
    pause: int = 270           # ms tra le frasi
    calore: float = 2.0        # dB attorno a 220 Hz (corpo, voce calda)
    naso: float = -1.5         # dB attorno a 1 kHz (meno nasale)
    presenza: float = 2.5      # dB attorno a 4,5 kHz (consonanti nitide)
    aria: float = 3.0          # dB sopra 7 kHz (aria, voce vicina)
    vicinanza: float = 3.0     # rapporto di compressione (effetto "vicino al microfono")

BASE = VoiceProfile()
PROFILI = {
    "PUBLIC": replace(BASE, style="PUBLIC", lentezza=0.98, pause=250),
    "WELCOME": replace(BASE, style="WELCOME", lentezza=1.0, calore=2.5, pause=270),
    "MODERATION": replace(BASE, style="MODERATION", lentezza=1.06, variazione=0.6, ritmo=0.8, pause=380, aria=1.0, presenza=2.0, calore=2.5),
    "ANNOUNCEMENT": replace(BASE, style="ANNOUNCEMENT", lentezza=1.03, variazione=0.75, pause=330, presenza=3.0),
    "NSFW": replace(BASE, style="NSFW", lentezza=1.05, pause=340, calore=3.0, presenza=1.5, aria=3.5, vicinanza=4.0),
}

def motore(p):
    cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=f"{M}/it_IT-paola-medium.onnx", tokens=f"{M}/tokens.txt",
            data_dir=f"{M}/espeak-ng-data", noise_scale=p.variazione, noise_scale_w=p.ritmo, length_scale=p.lentezza),
        num_threads=2, provider="cpu"), max_num_sentences=1)
    return sherpa_onnx.OfflineTts(cfg)

def sintetizza(frasi, p):
    tts, pezzi = motore(p), []
    for f in frasi:
        a = tts.generate(f, sid=0, speed=1.0); sr = a.sample_rate
        pezzi += [np.asarray(a.samples, dtype=np.float64), np.zeros(int(sr * p.pause / 1000))]
    x = np.concatenate(pezzi)
    return x, sr

def catena(p):
    return ",".join([
        "highpass=f=80",
        f"equalizer=f=220:t=q:w=0.8:g={p.calore}",
        f"equalizer=f=1000:t=q:w=1.2:g={p.naso}",
        f"equalizer=f=4500:t=q:w=1.0:g={p.presenza}",
        f"highshelf=f=7000:g={p.aria}",
        f"acompressor=threshold=-22dB:ratio={p.vicinanza}:attack=6:release=140:makeup=2",
        "loudnorm=I=-16:TP=-1.5",
    ])

def salva(nome, x, sr, filtri):
    sf.write(nome + ".wav", x.astype(np.float32), sr)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",nome+".wav","-af",filtri,nome+"_f.wav"],check=True)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-i",nome+"_f.wav","-codec:a","libmp3lame","-q:a","3",nome+".mp3"],check=True)
    print(nome, round(len(x)/sr,1), "s")

TESTI = {
    "PUBLIC": ["Oh, guarda chi si è fatto vedere!", "Bentornato nel server.", "Allora, che mi racconti di bello?"],
    "WELCOME": ["Benvenuta nel server!", "Dai, vieni a dare un'occhiata in giro.", "Se ti perdi, chiamami."],
    "MODERATION": ["Attenzione.", "Questo comportamento non è consentito in questo server.", "Ti invito a interromperlo."],
    "ANNOUNCEMENT": ["Annuncio importante.", "Stasera, alle nove, serata giochi nel canale vocale.", "Vi aspetto tutti."],
    "NSFW": ["Sei ancora sveglio, a quest'ora?", "Allora resta un altro po' con me.", "Non ho nessuna fretta."],
}
if __name__ == "__main__":
    import sys

    contesti = sys.argv[1:] or list(TESTI)
    for c in contesti:
        x, sr = sintetizza(TESTI[c], PROFILI[c])
        salva(f"yokai_{c.lower()}", x, sr, catena(PROFILI[c]))
