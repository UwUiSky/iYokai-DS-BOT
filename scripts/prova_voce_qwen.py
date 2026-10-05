"""
scripts/prova_voce_qwen.py
==========================
Prova a mano la voce di Yokai con Qwen3-TTS VoiceDesign, su un PC con
scheda video NVIDIA (D22, issue #142, revisione/02-piano/VOCE_YOKAI.md).
Non fa parte del bot.

NON ANCORA PROVATO: dove è stato scritto non c'era una scheda video.
I nomi delle funzioni del modello vanno confrontati con il README
ufficiale (https://github.com/QwenLM/Qwen3-TTS); se non coincidono lo
script lo dice ed elenca quelli che trova.

Preparazione, una volta sola (Python 3.10–3.12, torch con CUDA):
    pip install -U qwen-tts soundfile

Uso:
    python scripts/prova_voce_qwen.py "Oooh, guarda chi si è fatto vedere!"
    python scripts/prova_voce_qwen.py --quanti 5 --tono "playful, energetic" "Bentornato nel server."

Scrive yokai_qwen_1.wav, yokai_qwen_2.wav, … nella cartella corrente.
Il campione scelto diventa la voce di riferimento da clonare.
"""

import argparse
import sys

VOCE = (
    "Young adult female voice, clearly adult and mature, approximately "
    "early-twenties in perceived age. Warm, feminine and naturally attractive "
    "timbre with a soft slightly breathy texture. Medium to medium-high pitch, "
    "never childish or overly high-pitched. Smooth vocal resonance, clear "
    "articulation, natural Italian pronunciation, expressive intonation and "
    "realistic conversational rhythm. Confident, playful, elegant and subtly "
    "seductive personality. The voice should feel close, warm and charismatic, "
    "with gentle teasing energy when appropriate, but remain natural and "
    "believable. Avoid anime-style exaggeration, childish qualities, cartoonish "
    "pitch, excessive breathiness, monotone delivery, robotic articulation and "
    "overly dramatic acting. The speaker should sound like a confident young "
    "adult woman speaking naturally to people in a Discord community."
)


def main() -> None:
    p = argparse.ArgumentParser(description="Prova la voce di Yokai con Qwen3-TTS.")
    p.add_argument("testo")
    p.add_argument("--quanti", type=int, default=3, help="quanti campioni generare")
    p.add_argument("--tono", default="", help="tono del contesto, in inglese, aggiunto alla descrizione")
    p.add_argument("--modello", default="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    a = p.parse_args()

    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    if not torch.cuda.is_available():
        sys.exit("Serve una scheda video NVIDIA con CUDA: torch non la vede.")
    modello = Qwen3TTSModel.from_pretrained(a.modello, device_map="cuda:0", dtype=torch.bfloat16)
    if not hasattr(modello, "generate_voice_design"):
        funzioni = [n for n in dir(modello) if n.startswith(("generate", "create"))]
        sys.exit(f"Funzione generate_voice_design non trovata. Disponibili: {funzioni}")

    descrizione = VOCE + (f" Current tone: {a.tono}." if a.tono else "")
    for i in range(1, a.quanti + 1):
        audio, frequenza = modello.generate_voice_design(text=a.testo, language="Italian", instruct=descrizione)
        nome = f"yokai_qwen_{i}.wav"
        sf.write(nome, audio[0], frequenza)
        print("scritto", nome)


if __name__ == "__main__":
    main()
