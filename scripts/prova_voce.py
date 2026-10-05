"""
scripts/prova_voce.py
=====================
Prova a mano una voce italiana per i messaggi vocali di Yokai (D22,
issue #142). Non fa parte del bot: serve a scegliere motore e voce.
Usa Piper (voce Paola) tramite sherpa-onnx, tutto sul processore.

Preparazione, una volta sola:
    pip install sherpa-onnx soundfile numpy
    curl -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-it_IT-paola-medium.tar.bz2
    tar xjf vits-piper-it_IT-paola-medium.tar.bz2

Uso (le frasi si separano con "|": tra una e l'altra c'è una pausa):
    python3 scripts/prova_voce.py "Buongiorno. | Come state, oggi?"
    python3 scripts/prova_voce.py --respiri 1 --semitoni 1 "Ehi. | Vieni qui."

Scrive prova.wav e, se c'è ffmpeg, prova.mp3 nella cartella corrente.
"""

import argparse
import shutil
import subprocess
import numpy as np, soundfile as sf, sherpa_onnx

M = "vits-piper-it_IT-paola-medium"

def motore(noise=0.667, noise_w=0.8, length=1.0):
    cfg = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=f"{M}/it_IT-paola-medium.onnx", tokens=f"{M}/tokens.txt",
                data_dir=f"{M}/espeak-ng-data", noise_scale=noise,
                noise_scale_w=noise_w, length_scale=length),
            num_threads=2, provider="cpu"),
        max_num_sentences=1)
    return sherpa_onnx.OfflineTts(cfg)

def silenzio(sr, ms):
    return np.zeros(int(sr * ms / 1000), dtype=np.float32)

def respiro(sr, ms=420, volume=0.035, seme=0):
    """Inspirazione finta: rumore filtrato tra 500 e 3500 Hz, che sale e scende."""
    n = int(sr * ms / 1000)
    rumore = np.random.default_rng(seme).standard_normal(n)
    spettro = np.fft.rfft(rumore); f = np.fft.rfftfreq(n, 1 / sr)
    spettro[(f < 500) | (f > 3500)] = 0
    x = np.fft.irfft(spettro, n)
    inviluppo = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    x = x / (np.abs(x).max() + 1e-9) * inviluppo * volume
    return x.astype(np.float32)

def parla(tts, frasi, pausa=330, respiri=()):
    pezzi, sr = [], None
    for i, frase in enumerate(frasi):
        a = tts.generate(frase, sid=0, speed=1.0)
        sr = a.sample_rate
        if i in respiri:
            pezzi += [respiro(sr, seme=i), silenzio(sr, 60)]
        pezzi += [np.asarray(a.samples, dtype=np.float32), silenzio(sr, pausa)]
    return np.concatenate(pezzi), sr

def salva(nome, audio, sr, semitoni=0.0):
    sf.write(f"{nome}.wav", audio, sr)
    filtri = ["loudnorm=I=-16"]
    if semitoni:
        k = 2 ** (semitoni / 12)
        filtri = [f"asetrate={int(sr * k)}", f"aresample={sr}", f"atempo={1 / k:.5f}"] + filtri
    if shutil.which("ffmpeg") is None:
        print(nome + ".wav scritto (ffmpeg non trovato: niente mp3)")
        return
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{nome}.wav", "-af", ",".join(filtri),
                    "-codec:a", "libmp3lame", "-q:a", "3", f"{nome}.mp3"], check=True)
    print(nome, round(len(audio) / sr, 1), "s")


def main() -> None:
    global M
    p = argparse.ArgumentParser(description="Prova una voce per Yokai.")
    p.add_argument("testo", help='frasi separate da "|"')
    p.add_argument("--modello", default=M, help="cartella del modello scaricato")
    p.add_argument("--variazione", type=float, default=0.8, help="quanto varia l'intonazione (0.3–1.0)")
    p.add_argument("--ritmo", type=float, default=0.95, help="quanto varia la durata dei suoni (0.3–1.0)")
    p.add_argument("--lentezza", type=float, default=1.05, help="1.0 normale, più alto = più lenta")
    p.add_argument("--pausa", type=int, default=350, help="millisecondi tra le frasi")
    p.add_argument("--respiri", type=int, nargs="*", default=[], help="numeri delle frasi (da 0) precedute da un respiro")
    p.add_argument("--semitoni", type=float, default=0.0, help="voce più chiara (+) o più scura (-); restare entro 1.5")
    a = p.parse_args()
    M = a.modello
    frasi = [x.strip() for x in a.testo.split("|") if x.strip()]
    audio, sr = parla(motore(a.variazione, a.ritmo, a.lentezza), frasi, a.pausa, tuple(a.respiri))
    salva("prova", audio, sr, a.semitoni)


if __name__ == "__main__":
    main()
