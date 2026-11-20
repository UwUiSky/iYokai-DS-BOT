"""
core/web_panel_vocali.py
========================
Configurazione dei vocali temporanei dal pannello web (VOC-020): nome dei nuovi canali, blocco alla nascita,
registro, tetto per categoria, copia del generatore e aspetto del pannello. Valida con le stesse funzioni di
`/admin-vocali opzioni` e `/admin-vocali cap` (`core/voice_temp_logic.py`) e scrive con lo stesso repository.
Generatore e categoria si scelgono con `/admin-vocali` (servono i canali veri di Discord).
Funzioni coperte: SPEC §24.8 (VOC-020, issue #127)
Dipende da: core/voice_temp_logic.py, core/repositories/voice_temp_repo.py
"""

from __future__ import annotations

from core.config_schema import ImpostazioneNonValida
from core.voice_temp_logic import (
    MAX_MODELLO_NOME,
    MAX_PANNELLO_TESTO,
    MAX_PANNELLO_TITOLO,
    colore_da_testo,
    errore_modello_nome,
)

CAP_MASSIMO = 50  # limite di Discord per canali in una categoria


class VocaliNonConfigurati(ImpostazioneNonValida):
    """Manca il generatore o la categoria: prima il comando di impianto."""


async def leggi(guild) -> dict:
    """Stato per la pagina. Il colore torna come testo esadecimale (senza #)."""
    from core.repositories.voice_temp_repo import voice_temp_repo

    c = await voice_temp_repo.get_config(guild.id)
    extra = await voice_temp_repo.lista_generatori(guild.id)
    return {
        "configurato": c.category_id is not None,
        "generatore": c.generator_channel_id,
        "categoria": c.category_id,
        "extra": len(extra),
        "nome_modello": c.nome_modello or "",
        "nasce_bloccato": c.nasce_bloccato,
        "registro": c.canale_registro_id,
        "cap": c.category_cap,
        "clona": c.clona_generatore,
        "titolo": c.pannello_titolo or "",
        "testo": c.pannello_testo or "",
        "colore": f"{c.pannello_colore:06X}" if c.pannello_colore is not None else "",
    }


def _testo(valore, massimo: int, nome: str) -> str | None:
    pulito = str(valore or "").strip()
    if len(pulito) > massimo:
        raise ImpostazioneNonValida(f"{nome}: al massimo {massimo} caratteri.")
    return pulito or None


async def applica(guild, campi: dict, changed_by: int | None) -> bool:
    """
    Salva tutti i campi della pagina. True se qualcosa è cambiato. Storto = ImpostazioneNonValida e niente scritto.
    `campi`: nome, bloccati ("0"/"1"), registro (id canale di testo o vuoto), cap (1-50 o vuoto), clona ("0"/"1"),
    titolo, testo, colore.
    """
    from core.repositories.voice_temp_repo import voice_temp_repo

    prima = await voice_temp_repo.get_config(guild.id)
    if prima.category_id is None:
        raise VocaliNonConfigurati("Prima scegli generatore e categoria con il comando di impianto dei vocali.")

    modello = _testo(campi.get("nome"), MAX_MODELLO_NOME, "Nome")
    if modello is not None and (errore := errore_modello_nome(modello)):
        raise ImpostazioneNonValida(errore)
    for chiave in ("bloccati", "clona"):
        if campi.get(chiave) not in ("0", "1"):
            raise ImpostazioneNonValida("Scegli sì o no.")
    registro = None
    testo_registro = str(campi.get("registro") or "").strip()
    if testo_registro:
        if not testo_registro.isascii() or not testo_registro.isdigit() or len(testo_registro) > 20:
            raise ImpostazioneNonValida("Canale non valido.")
        canale = guild.get_channel(int(testo_registro))
        if canale is None or not hasattr(canale, "send"):
            raise ImpostazioneNonValida("Il canale del registro deve essere un canale di testo di questo server.")
        registro = canale.id
    cap = None
    testo_cap = str(campi.get("cap") or "").strip()
    if testo_cap:
        if not testo_cap.isascii() or not testo_cap.isdigit() or not 1 <= int(testo_cap) <= CAP_MASSIMO:
            raise ImpostazioneNonValida(f"Il tetto va da 1 a {CAP_MASSIMO} (vuoto = nessun tetto).")
        cap = int(testo_cap)
    titolo = _testo(campi.get("titolo"), MAX_PANNELLO_TITOLO, "Titolo")
    testo = _testo(campi.get("testo"), MAX_PANNELLO_TESTO, "Testo")
    colore = None
    testo_colore = str(campi.get("colore") or "").strip()
    if testo_colore:
        colore = colore_da_testo(testo_colore)
        if colore is None:
            raise ImpostazioneNonValida("Il colore va scritto in esadecimale a 6 cifre (es. 5865F2).")

    bloccati = campi["bloccati"] == "1"
    clona = campi["clona"] == "1"
    cambiato = (
        (prima.nome_modello, prima.nasce_bloccato, prima.canale_registro_id, prima.category_cap, prima.clona_generatore,
         prima.pannello_titolo, prima.pannello_testo, prima.pannello_colore)
        != (modello, bloccati, registro, cap, clona, titolo, testo, colore)
    )
    if cambiato:
        await voice_temp_repo.set_opzioni(guild.id, modello, bloccati, registro)
        await voice_temp_repo.set_aspetto(guild.id, titolo, testo, colore, clona)
        await voice_temp_repo.set_category_cap(guild.id, cap)
        from core.database import db

        await db._record_config_change(guild.id, changed_by, "setting", "vocali_temporanei", None, "pannello")
    return cambiato
