"""
core/web_editor.py
==================
Editor del pannello web (SPEC §24.5): l'embed salvato del server (stessi controlli, stesso archivio del comando) e il
messaggio di benvenuto (stesso controllo di lunghezza del comando) con l'anteprima. Nessuna logica propria:
si leggono i campi del modulo, si chiamano i controlli già esistenti e si scrive nello stesso archivio.
Funzioni coperte: SPEC §24.5 (NF-20, issue #91)
Dipende da: core/embed_builder_logic.py, core/repositories/saved_embed_repo.py, core/greetings_logic.py
"""

from __future__ import annotations

from dataclasses import dataclass

from core.embed_builder_logic import DatiEmbed, a_json, da_json, valida
from core.greetings_logic import (
    DEFAULT_WELCOME_TEMPLATE,
    MAX_MESSAGE_LENGTH,
    lunghezza_dopo_segnaposto,
    render_template,
)
from core.i18n import lingua_server, t
from core.leveling_logic import colore_valido
from core.nome_logic import normalizza_nome
from core.repositories.greetings_repo import greetings_repo
from core.repositories.saved_embed_repo import saved_embed_repo
from core.safe_http import url_e_sicuro

CAMPI_NEL_MODULO = 3  # il modulo ha 3 campi; per averne di più si usa il comando di modifica


class ErroreEditor(Exception):
    """Un elenco di frasi pronte per la pagina."""

    def __init__(self, messaggi: list[str]) -> None:
        super().__init__("; ".join(messaggi))
        self.messaggi = messaggi


@dataclass(frozen=True)
class AnteprimaEmbed:
    titolo: str
    descrizione: str
    colore: str
    piede: str
    immagine: str
    miniatura: str
    campi: tuple[tuple[str, str, bool], ...]


def dati_da_modulo(form) -> DatiEmbed:
    """I campi del modulo come `DatiEmbed`. I campi con nome e valore vuoti si saltano."""
    def testo(chiave: str) -> str | None:
        valore = str(form.get(chiave, "")).strip()
        return valore or None

    campi = []
    for n in range(1, CAMPI_NEL_MODULO + 1):
        nome, valore = str(form.get(f"campo{n}_nome", "")).strip(), str(form.get(f"campo{n}_valore", "")).strip()
        if nome or valore:
            campi.append((nome, valore, form.get(f"campo{n}_inline") == "1"))
    return DatiEmbed(
        title=testo("titolo"), description=testo("descrizione"), color=testo("colore"), image_url=testo("immagine"),
        thumbnail_url=testo("miniatura"), footer=testo("piede"), fields=tuple(campi),
    )


def anteprima(dati: DatiEmbed) -> AnteprimaEmbed:
    colore = colore_valido(dati.color) if dati.color else None
    return AnteprimaEmbed(
        titolo=dati.title or "", descrizione=dati.description or "", colore=colore or "#5865F2", piede=dati.footer or "",
        immagine=dati.image_url or "", miniatura=dati.thumbnail_url or "", campi=dati.fields,
    )


async def errori_embed(dati: DatiEmbed) -> list[str]:
    """Gli errori del comando (limiti) più gli indirizzi che il bot non può raggiungere in sicurezza."""
    errori = valida(dati)
    for etichetta, url in (("immagine", dati.image_url), ("miniatura", dati.thumbnail_url)):
        if url and not errori and not await url_e_sicuro(url):
            errori.append(f"L'indirizzo della {etichetta} non è ammesso (indirizzo interno o porta non consentita).")
    return errori


async def salva_embed(guild_id: int, nome: str, dati: DatiEmbed, user_id: int) -> str:
    """'creato' o 'aggiornato'. Nome, limiti o tetto per server non rispettati = ErroreEditor."""
    normalizzato = normalizza_nome(nome)
    if normalizzato is None:
        raise ErroreEditor(["Il nome può avere solo lettere minuscole (a-z), cifre, - e _, senza spazi."])
    errori = await errori_embed(dati)
    if errori:
        raise ErroreEditor(errori)
    esito = await saved_embed_repo.create(guild_id, normalizzato, a_json(dati), user_id)
    if esito == "pieno":
        raise ErroreEditor(["Questo server ha già il massimo di embed salvati: eliminane uno."])
    if esito == "esiste":
        await saved_embed_repo.update_data(guild_id, normalizzato, a_json(dati))
        return "aggiornato"
    return "creato"


async def elimina_embed(guild_id: int, nome: str) -> bool:
    return await saved_embed_repo.delete(guild_id, nome)


async def embed_salvati(guild_id: int) -> list[tuple[str, DatiEmbed]]:
    return [(e.name, da_json(e.data)) for e in await saved_embed_repo.list(guild_id)]


# ------------------------------------------------------------------ benvenuto
def errore_benvenuto(guild, testo: str) -> str | None:
    """Lo stesso controllo del comando: il messaggio, a segnaposto espansi, sta in 2000 caratteri."""
    lunghezza = lunghezza_dopo_segnaposto(testo, guild.name, guild.member_count or 0)
    if lunghezza <= MAX_MESSAGE_LENGTH:
        return None
    return f"Con i segnaposto sostituiti il messaggio arriva a {lunghezza} caratteri: Discord ne accetta {MAX_MESSAGE_LENGTH}. Accorcialo."


def anteprima_benvenuto(guild, testo: str) -> str:
    return render_template(testo, "@Nuovo", "nuovo", guild.name, guild.member_count or 0, user_id=1, display_name="Nuovo", server_id=guild.id)


async def stato_benvenuto(guild) -> dict:
    c = await greetings_repo.get_config(guild.id)
    base = c.welcome_message in ("", DEFAULT_WELCOME_TEMPLATE)
    return {
        "attivo": c.welcome_enabled, "canale": c.welcome_channel_id, "dm": c.welcome_dm,
        "messaggio": t("greet_base_welcome", await lingua_server(guild.id)) if base else c.welcome_message,
        "ping_ruoli": getattr(c, "welcome_ping_ruoli", False),
    }


async def salva_benvenuto(guild, attivo: bool, canale_id: int | None, testo: str, dm: bool) -> None:
    """Scrive come il comando. Acceso senza un canale vero, o testo troppo lungo = ErroreEditor."""
    testo = testo.strip()
    if not testo:
        raise ErroreEditor(["Scrivi il messaggio di benvenuto."])
    errore = errore_benvenuto(guild, testo)
    if errore:
        raise ErroreEditor([errore])
    canale = guild.get_channel(canale_id) if canale_id else None
    if attivo and canale is None:
        raise ErroreEditor(["Scegli il canale dove mandare il benvenuto."])
    precedente = await greetings_repo.get_config(guild.id)
    # Dal pannello non si sa se chi scrive ha «Menziona tutti»: i ping di ruolo restano spenti (D12).
    await greetings_repo.set_welcome(
        guild.id, attivo, canale.id if canale else (precedente.welcome_channel_id or 0), testo, dm, False
    )
