"""
core/moderazione_traduci.py
===========================
Bottone «Traduci» sui messaggi pubblici di moderazione (D110, #115). Un solo punto: `vista_traduci(guild)` dà il
bottone persistente (custom_id fisso, si registra con `bot.add_view(VistaTraduci())`); chi lo preme riceve una
risposta effimera con il testo già pubblico nella lingua del SUO client. Se la lingua è una di quelle del bot
(it, en) i testi fissi tornano dal catalogo; il resto passa dallo snodo AI (traduzione, con la sua cache). Il
bottone non dà permessi, non menziona nessuno, vale 5 volte al minuto per persona.
Funzioni coperte: SPEC §5.13 (#115, D110)
Dipende da: core/ai_servizio.py (snodo AI), core/i18n.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

import discord

from core import i18n
from core.ai_servizio import AINonDisponibile, RichiestaAI, servizio_ai
from core.ai_testi_logic import nome_lingua
from core.bounded_cache import BoundedCache
from core.ui_base import BaseView

logger = logging.getLogger("iyokai.moderazione_traduci")

CUSTOM_ID = "iyokai:modtraduci"
MAX_AL_MINUTO = 5
MAX_EMBED = 3
MAX_CAMPI = 25
MAX_TESTI = 40
MAX_CARATTERI_AI = 4000
MAX_TOTALE_EMBED = 5500
MIN_LETTERE_MODELLO = 8

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_usi: BoundedCache[int, deque] = BoundedCache(20_000)
_inversi: dict[str, tuple[dict[str, str], list[tuple[re.Pattern, str]]]] = {}


@dataclass
class Contenuto:
    """Il testo pubblico di un messaggio: contenuto semplice e fino a 3 embed (titolo, descrizione, campi, piede)."""

    content: str = ""
    embed: list[dict] = field(default_factory=list)


def scomponi(message) -> Contenuto:
    """Legge il testo di un messaggio; senza embed vale il contenuto. Mai allegati né componenti."""
    embed = []
    for e in list(getattr(message, "embeds", None) or [])[:MAX_EMBED]:
        embed.append({
            "title": e.title or "",
            "description": e.description or "",
            "fields": [(f.name or "", f.value or "", bool(f.inline)) for f in list(e.fields)[:MAX_CAMPI]],
            "footer": (e.footer.text or "") if e.footer else "",
            "color": e.color,
        })
    return Contenuto(content="" if embed else (getattr(message, "content", "") or ""), embed=embed)


def testi_di(c: Contenuto) -> list[str]:
    """Tutti i pezzi di testo non vuoti, nell'ordine in cui `con_testi` li rimette."""
    pezzi = [c.content]
    for e in c.embed:
        pezzi += [e["title"], e["description"], e["footer"]]
        for nome, valore, _ in e["fields"]:
            pezzi += [nome, valore]
    return [p for p in pezzi if p.strip()]


def con_testi(c: Contenuto, nuovi: list[str]) -> Contenuto:
    """Lo stesso contenuto con i pezzi non vuoti sostituiti, nell'ordine di `testi_di`."""
    coda = iter(nuovi)

    def prossimo(originale: str) -> str:
        return next(coda) if originale.strip() else originale

    contenuto = prossimo(c.content)
    embed = []
    for e in c.embed:
        titolo, descr, piede = prossimo(e["title"]), prossimo(e["description"]), prossimo(e["footer"])
        campi = []
        for nome, valore, inline in e["fields"]:
            campi.append((prossimo(nome), prossimo(valore), inline))
        embed.append({"title": titolo, "description": descr, "footer": piede, "fields": campi, "color": e["color"]})
    return Contenuto(content=contenuto, embed=embed)


def a_embed(c: Contenuto, nota: str = "") -> list[discord.Embed]:
    """Gli embed da mostrare, con i tetti di Discord; `nota` va nel piede dell'ultimo."""
    risultato: list[discord.Embed] = []
    totale = 0
    for e in c.embed:
        embed = discord.Embed(title=e["title"][:256] or None, description=e["description"][:3000] or None,
                              color=e["color"] or discord.Color.blurple())
        totale += len(e["title"][:256]) + len(e["description"][:3000])
        for nome, valore, inline in e["fields"][:MAX_CAMPI]:
            n, v = nome[:256] or "-", valore[:1024] or "-"
            if totale + len(n) + len(v) > MAX_TOTALE_EMBED:
                break
            totale += len(n) + len(v)
            embed.add_field(name=n, value=v, inline=inline)
        if e["footer"] and totale + len(e["footer"]) <= MAX_TOTALE_EMBED:
            embed.set_footer(text=e["footer"][:2048])
        risultato.append(embed)
    if nota and risultato:
        piede = risultato[-1].footer.text if risultato[-1].footer else ""
        risultato[-1].set_footer(text=((piede + " · ") if piede else "") + nota[:200])
    return risultato


# ---------------------------------------------------------------- testi del bot
def _inverso(lingua: str) -> tuple[dict[str, str], list[tuple[re.Pattern, str]]]:
    """Dal testo alla chiave, nella lingua del server: testi fissi esatti e modelli con segnaposto."""
    if lingua in _inversi:
        return _inversi[lingua]
    esatti: dict[str, str] = {}
    modelli: list[tuple[re.Pattern, str]] = []
    for chiave, testo in (i18n.carica_catalogo().get(lingua) or {}).items():
        if not isinstance(testo, str):
            continue
        if not _PLACEHOLDER.search(testo):
            esatti.setdefault(testo, chiave)
            continue
        fisso = _PLACEHOLDER.sub("", testo)
        if sum(c.isalpha() for c in fisso) < MIN_LETTERE_MODELLO:
            continue
        pezzi = _PLACEHOLDER.split(testo)  # testo, nome, testo, nome, ...
        regola = ""
        for i, p in enumerate(pezzi):
            regola += re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)"
        try:
            modelli.append((re.compile(regola, re.DOTALL), chiave))
        except re.error:  # segnaposto ripetuto: il modello si salta
            continue
    _inversi[lingua] = (esatti, modelli)
    return _inversi[lingua]


def riconosci(testo: str, lingua_server: str) -> tuple[str, dict[str, str]] | None:
    """(chiave, valori) se `testo` e' un testo del bot nella lingua del server, altrimenti None."""
    esatti, modelli = _inverso(lingua_server)
    if testo in esatti:
        return esatti[testo], {}
    for regola, chiave in modelli:
        m = regola.fullmatch(testo)
        if m:
            return chiave, m.groupdict()
    return None


def lingua_del_bot(codice: str | None) -> str | None:
    """La lingua del client se il bot ha i suoi testi (it, en-US), altrimenti None."""
    lingua = i18n.normalizza_lingua(codice)
    return lingua if lingua and i18n.carica_catalogo().get(lingua) else None


# ---------------------------------------------------------------- AI
ISTRUZIONI_AI = (
    "Traduci in {lingua} ogni testo dell'elenco JSON. Lascia identici menzioni (<@...>, <#...>, <@&...>), numeri, "
    "link, emoji e codici tra apici inversi. Rispondi SOLO con un array JSON di stringhe, della stessa lunghezza "
    "e nello stesso ordine dell'elenco."
)


def leggi_traduzioni(risposta: str | None, quanti: int) -> list[str] | None:
    """L'array di stringhe della risposta dell'AI, o None se non e' come richiesto."""
    if not risposta:
        return None
    inizio, fine = risposta.find("["), risposta.rfind("]")
    if inizio < 0 or fine <= inizio:
        return None
    try:
        dati = json.loads(risposta[inizio : fine + 1])
    except ValueError:
        return None
    if not isinstance(dati, list) or len(dati) != quanti or not all(isinstance(x, str) for x in dati):
        return None
    return [x.strip() for x in dati]


async def traduci_con_ai(interaction: discord.Interaction, testi: list[str], codice: str) -> list[str]:
    """Traduce `testi` con lo snodo AI. Solleva AINonDisponibile (con il motivo) se non si puo'."""
    elenco = json.dumps(testi, ensure_ascii=False)
    if len(elenco) > MAX_CARATTERI_AI:
        raise AINonDisponibile("vietata", "")
    risposta = await servizio_ai().richiedi(RichiestaAI(
        user_id=interaction.user.id, funzione="traduci", tipo="traduzione", testo=elenco,
        guild_id=interaction.guild_id, channel_id=interaction.channel_id,
        istruzioni=ISTRUZIONI_AI.format(lingua=f"{nome_lingua(codice)} ({codice})"), messaggi_utenti=True,
    ))
    risultato = leggi_traduzioni(risposta.testo, len(testi))
    if risultato is None:
        raise AINonDisponibile("fornitori_fermi")
    return risultato


# ---------------------------------------------------------------- tetto per persona
def consenti(user_id: int, ora: float | None = None) -> bool:
    """Al massimo 5 pressioni al minuto per persona."""
    ora = time.monotonic() if ora is None else ora
    coda = _usi.get(user_id)
    if coda is None:
        coda = deque(maxlen=MAX_AL_MINUTO)
    while coda and coda[0] <= ora - 60:
        coda.popleft()
    if len(coda) >= MAX_AL_MINUTO:
        return False
    coda.append(ora)
    _usi.set(user_id, coda)
    return True


def azzera_tetti() -> None:
    _usi._data.clear()


# ---------------------------------------------------------------- bottone
async def rispondi_traduzione(interaction: discord.Interaction) -> None:
    """Il clic sul bottone: risposta effimera, nessuna menzione, nessun permesso in piu'."""
    nessuna = discord.AllowedMentions.none()
    codice = str(getattr(interaction.locale, "value", interaction.locale) or "en-US")
    lingua_bot = lingua_del_bot(codice)
    lingua_msg = lingua_bot or i18n.LINGUA_RIPIEGO  # la lingua dei testi del bot nella risposta
    if interaction.guild is None or interaction.message is None:
        await interaction.response.send_message(i18n.t("modtrad_non_disponibile", lingua_msg), ephemeral=True)
        return
    if not consenti(interaction.user.id):
        await interaction.response.send_message(i18n.t("modtrad_troppe", lingua_msg), ephemeral=True)
        return
    contenuto = scomponi(interaction.message)
    testi = testi_di(contenuto)[:MAX_TESTI]
    if not testi:
        await interaction.response.send_message(i18n.t("modtrad_niente", lingua_msg), ephemeral=True)
        return
    lingua_server = await i18n.lingua_server(interaction.guild.id)
    lingua_server = i18n.normalizza_lingua(lingua_server) or i18n.DEFAULT_LANGUAGE
    if lingua_bot == lingua_server:
        await interaction.response.send_message(i18n.t("modtrad_gia_tua", lingua_msg), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    nuovi: list[str | None] = [None] * len(testi)
    da_tradurre: list[int] = []
    for i, testo in enumerate(testi):
        trovato = riconosci(testo, lingua_server) if lingua_bot else None
        if trovato is not None:
            nuovi[i] = i18n.t(trovato[0], lingua_bot, **trovato[1])
        else:
            da_tradurre.append(i)
    nota = ""
    if da_tradurre:
        try:
            tradotti = await traduci_con_ai(interaction, [testi[i] for i in da_tradurre], codice)
        except AINonDisponibile as errore:
            await interaction.followup.send(
                f"{i18n.t('modtrad_ai_no', lingua_msg)}\n{errore.testo}"[:1900], ephemeral=True, allowed_mentions=nessuna
            )
            return
        except Exception:  # noqa: BLE001 - database o motore in errore: lo si dice, senza fermare nulla
            logger.warning("Traduzione del messaggio di moderazione non riuscita.", exc_info=True)
            await interaction.followup.send(i18n.t("modtrad_ai_no", lingua_msg), ephemeral=True, allowed_mentions=nessuna)
            return
        for i, t in zip(da_tradurre, tradotti):
            nuovi[i] = t
        nota = i18n.t("modtrad_nota_ai", lingua_msg)
    risultato = con_testi(contenuto, [n if n is not None else testi[i] for i, n in enumerate(nuovi)])
    embed = a_embed(risultato, nota)
    corpo = risultato.content[:1900] or None
    await interaction.followup.send(content=corpo, embeds=embed, ephemeral=True, allowed_mentions=nessuna)


class VistaTraduci(BaseView):
    """Il bottone persistente: stesso custom_id per tutti i messaggi, vive anche dopo un riavvio."""

    def __init__(self, etichetta: str = "Traduci") -> None:
        super().__init__(timeout=None)
        bottone = discord.ui.Button(
            label=etichetta[:80], style=discord.ButtonStyle.secondary, custom_id=CUSTOM_ID, emoji="🌐"
        )
        bottone.callback = self._premuto
        self.add_item(bottone)

    async def _premuto(self, interaction: discord.Interaction) -> None:
        await rispondi_traduzione(interaction)


async def traducibile(guild, **kw) -> dict:
    """Gli argomenti di un invio con il bottone «Traduci» in piu' (se non c'e' gia' una vista). Mai solleva."""
    if kw.get("view") is None:
        try:
            kw["view"] = await vista_traduci(guild)
        except Exception:  # noqa: BLE001 - il bottone e' un'aggiunta: il messaggio parte comunque
            logger.warning("Bottone Traduci non aggiunto.", exc_info=True)
    return kw


async def vista_traduci(guild) -> VistaTraduci:
    """Il bottone con l'etichetta nella lingua del server."""
    return VistaTraduci(await i18n.testo_guild(guild, "modtrad_bottone"))
