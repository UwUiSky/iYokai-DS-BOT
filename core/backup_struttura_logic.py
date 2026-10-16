"""
core/backup_struttura_logic.py
==============================
La struttura del server come dati: si legge (impostazioni, ruoli, canali con i
permessi, emoji, sticker e, a scelta, ban e membri), si controlla, si esporta in
JSON o CSV e si ricarica scegliendo le parti. Il caricamento riusa per nome ciò
che esiste, crea il resto, una chiamata alla volta, e si può fermare tra un
passo e l'altro (ciò che è già fatto resta).
Con i messaggi: gli ultimi N di ogni canale di testo, ricaricati via webhook
nei canali con lo stesso nome ancora vuoti.
Funzioni coperte: SPEC §11.15, M 12.17, BKP-009, BKP-010, BKP-014, BKP-015,
BKP-032, BKP-033, BKP-034, BKP-036, BKP-037
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable

import discord

from core.backup_clone_logic import _overwrite_consentito, _permessi_consentiti
from core import backup_messages_logic as messaggi_logic
from core.backup_mirror_logic import NOME_CANALE_OFFUSCATO

logger = logging.getLogger("iyokai.backup_struttura")

VERSIONE = 1
MAX_FILE_BYTE = 10 * 1024 * 1024  # LIMITI Parte 4, punto 13
MAX_RUOLI = 250
MAX_CANALI = 500
MAX_PER_CATEGORIA = 50
MAX_EMOJI = 250
MAX_STICKER = 60
MAX_BAN = 100_000
MAX_MEMBRI = 250_000
MAX_NOME = 100
MAX_MOTIVO = 512
MAX_PERMESSI = 1 << 53
MOTIVO = "Caricamento backup iYokai"

# Permessi che un caricamento non AGGIUNGE mai a @everyone né a un ruolo che esiste
# già (e che può avere membri): un file o un modello d'altri non fa admin tutto il server.
PERMESSI_PERICOLOSI = discord.Permissions(
    administrator=True, manage_guild=True, manage_roles=True, manage_channels=True, ban_members=True,
    kick_members=True, moderate_members=True, manage_webhooks=True, mention_everyone=True,
).value

PARTI = ("impostazioni", "ruoli", "canali", "emoji", "messaggi", "ban", "membri")
MAX_MESSAGGI_PER_CANALE = 100

_TIPI = {
    discord.ChannelType.text: "testo",
    discord.ChannelType.news: "annunci",
    discord.ChannelType.voice: "vocale",
    discord.ChannelType.stage_voice: "palco",
    discord.ChannelType.forum: "forum",
}
TIPI_CANALE = frozenset(_TIPI.values())


# ---------------------------------------------------------------- lettura
def _nome_o_none(oggetto) -> str | None:
    return getattr(oggetto, "name", None) if oggetto is not None else None


def _overwrite(canale) -> list[dict]:
    righe = []
    for bersaglio, ow in canale.overwrites.items():
        consentiti, negati = ow.pair()
        if isinstance(bersaglio, discord.Role):
            chi = {"everyone": True} if bersaglio.is_default() else {"ruolo": bersaglio.name}
        else:
            chi = {"membro": bersaglio.id}
        righe.append({**chi, "allow": consentiti.value, "deny": negati.value})
    return righe


def leggi_ruolo(ruolo) -> dict:
    return {
        "nome": ruolo.name,
        "colore": ruolo.colour.value,
        "hoist": ruolo.hoist,
        "mentionable": ruolo.mentionable,
        "permessi": ruolo.permissions.value,
        "posizione": ruolo.position,
    }


def leggi_canale(canale) -> dict:
    return {
        "nome": canale.name,
        "tipo": _TIPI[canale.type],
        "categoria": _nome_o_none(canale.category),
        "posizione": canale.position,
        "topic": getattr(canale, "topic", None),
        "nsfw": bool(getattr(canale, "nsfw", False)),
        "slowmode": getattr(canale, "slowmode_delay", 0) or 0,
        "bitrate": getattr(canale, "bitrate", None),
        "user_limit": getattr(canale, "user_limit", None),
        "overwrite": _overwrite(canale),
    }


def leggi_struttura(guild: discord.Guild) -> dict:
    """Fotografia della struttura. I canali offuscati (LIM-38) e i ruoli gestiti si saltano."""
    canali = [
        c for c in guild.channels
        if c.type in _TIPI and c.name != NOME_CANALE_OFFUSCATO
    ]
    return {
        "versione": VERSIONE,
        "nome": guild.name,
        "creato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "impostazioni": {
            "verification_level": guild.verification_level.value,
            "default_notifications": guild.default_notifications.value,
            "explicit_content_filter": guild.explicit_content_filter.value,
            "afk_timeout": guild.afk_timeout,
            "afk_channel": _nome_o_none(guild.afk_channel),
            "system_channel": _nome_o_none(guild.system_channel),
        },
        "everyone": guild.default_role.permissions.value,
        "ruoli": [leggi_ruolo(r) for r in guild.roles if not r.is_default() and not r.managed],
        "categorie": [
            {"nome": c.name, "posizione": c.position, "overwrite": _overwrite(c)}
            for c in guild.categories if c.name != NOME_CANALE_OFFUSCATO
        ],
        "canali": [leggi_canale(c) for c in canali],
        "emoji": [{"nome": e.name, "url": str(e.url), "animata": e.animated} for e in guild.emojis],
        "sticker": [
            {"nome": s.name, "url": str(s.url), "emoji": getattr(s, "emoji", "") or "⭐"}
            for s in guild.stickers
        ],
    }


async def leggi_ban(guild: discord.Guild, limite: int = MAX_BAN) -> list[dict]:
    """BKP-015/034: la lista dei ban (discord.py legge a pagine da 1000)."""
    return [
        {"user_id": voce.user.id, "nome": voce.user.name, "motivo": (voce.reason or "")[:MAX_MOTIVO]}
        async for voce in guild.bans(limit=limite)
    ]


def leggi_membri(guild: discord.Guild) -> list[dict]:
    """BKP-014: nickname e ruoli (per nome) dei membri presenti, bot esclusi."""
    return [
        {
            "user_id": m.id,
            "nick": m.nick,
            "ruoli": [r.name for r in m.roles if not r.is_default() and not r.managed],
        }
        for m in guild.members if not m.bot
    ][:MAX_MEMBRI]


async def leggi_reazioni(messaggio: discord.Message, limite: int = 5000) -> list[dict]:
    """BKP-036: chi ha reagito, emoji per emoji (lettura a pagine)."""
    righe: list[dict] = []
    for reazione in messaggio.reactions:
        async for utente in reazione.users(limit=limite):
            righe.append({"emoji": str(reazione.emoji), "user_id": utente.id, "nome": utente.name})
    return righe


# ---------------------------------------------------------------- controllo
def _testo_ok(valore, massimo: int = MAX_NOME, vuoto: bool = False) -> bool:
    return isinstance(valore, str) and (vuoto or valore.strip() != "") and len(valore) <= massimo


def _int_ok(valore, massimo: int = MAX_PERMESSI) -> bool:
    return isinstance(valore, int) and not isinstance(valore, bool) and 0 <= valore < massimo


def _testo_o_none(valore, massimo: int = MAX_NOME) -> bool:
    return valore is None or _testo_ok(valore, massimo, vuoto=True)


def _elenco_di_testi(valore) -> bool:
    return isinstance(valore, list) and len(valore) <= MAX_RUOLI and all(_testo_ok(v) for v in valore)


def _messaggio_ok(m) -> bool:
    """Un messaggio salvato: ogni campo letto da ricarica_chat con il tipo giusto."""
    if not isinstance(m, dict) or not _testo_ok(m.get("contenuto", ""), 2000, vuoto=True):
        return False
    if not _testo_o_none(m.get("autore"), 80) or not _testo_o_none(m.get("avatar"), 2000):
        return False
    allegati = m.get("allegati", [])
    return isinstance(allegati, list) and len(allegati) <= 10 and all(
        isinstance(a, dict) and _testo_ok(a.get("url"), 2000) and _testo_o_none(a.get("nome"))
        and (a.get("size") is None or _int_ok(a["size"], 1 << 40))
        for a in allegati
    )


def _controlla_overwrite(righe, dove: str, errori: list[str]) -> None:
    if not isinstance(righe, list):
        errori.append(f"{dove}: «overwrite» deve essere un elenco")
        return
    for ow in righe:
        if not isinstance(ow, dict) or not (_int_ok(ow.get("allow")) and _int_ok(ow.get("deny"))):
            errori.append(f"{dove}: permessi non validi")
        elif not (ow.get("everyone") is True or _testo_ok(ow.get("ruolo")) or _int_ok(ow.get("membro"), 1 << 64)):
            errori.append(f"{dove}: overwrite senza ruolo né membro")


def valida_struttura(dati) -> list[str]:
    """BKP-037: controlla il file PRIMA di toccare il server. Elenco vuoto = valido."""
    if not isinstance(dati, dict):
        return ["il file non contiene un oggetto JSON"]
    errori: list[str] = []
    if dati.get("versione") != VERSIONE:
        errori.append(f"versione non supportata (serve {VERSIONE})")
    limiti = {"ruoli": MAX_RUOLI, "categorie": MAX_CANALI, "canali": MAX_CANALI,
              "emoji": MAX_EMOJI, "sticker": MAX_STICKER, "ban": MAX_BAN, "membri": MAX_MEMBRI}
    for chiave, tetto in limiti.items():
        valore = dati.get(chiave, [])
        if not isinstance(valore, list):
            errori.append(f"«{chiave}» deve essere un elenco")
        elif len(valore) > tetto:
            errori.append(f"«{chiave}»: {len(valore)} elementi, al massimo {tetto}")
    if errori:
        return errori
    if "everyone" in dati and not _int_ok(dati["everyone"]):
        errori.append("permessi di @everyone non validi")
    imp = dati.get("impostazioni", {})
    if not isinstance(imp, dict):
        errori.append("«impostazioni» deve essere un oggetto")
    for i, r in enumerate(dati.get("ruoli", [])):
        if not isinstance(r, dict) or not _testo_ok(r.get("nome")) or not _int_ok(r.get("permessi", 0)) \
                or not _int_ok(r.get("colore", 0), 1 << 24) or not _int_ok(r.get("posizione", 0), 1 << 31):
            errori.append(f"ruolo {i + 1}: nome, colore o permessi non validi")
    for i, c in enumerate(dati.get("categorie", [])):
        if not isinstance(c, dict) or not _testo_ok(c.get("nome")) or not _int_ok(c.get("posizione", 0), 1 << 31):
            errori.append(f"categoria {i + 1}: nome o posizione non validi")
        else:
            _controlla_overwrite(c.get("overwrite", []), f"categoria «{c['nome']}»", errori)
    for i, c in enumerate(dati.get("canali", [])):
        if not isinstance(c, dict) or not _testo_ok(c.get("nome")) or c.get("tipo") not in TIPI_CANALE:
            errori.append(f"canale {i + 1}: nome o tipo non validi")
            continue
        if any(c.get(k) is not None and not _int_ok(c[k], 1 << 31)
               for k in ("posizione", "slowmode", "bitrate", "user_limit")):
            errori.append(f"canale «{c['nome']}»: numeri non validi")
        if c.get("categoria") is not None and not _testo_ok(c["categoria"]):
            errori.append(f"canale «{c['nome']}»: categoria non valida")
        if c.get("topic") is not None and not _testo_ok(c["topic"], 1024, vuoto=True):
            errori.append(f"canale «{c['nome']}»: argomento oltre 1024 caratteri")
        _controlla_overwrite(c.get("overwrite", []), f"canale «{c['nome']}»", errori)
    messaggi = dati.get("messaggi", {})
    if not isinstance(messaggi, dict) or len(messaggi) > MAX_CANALI or any(
        not _testo_ok(nome) or not isinstance(elenco, list) or len(elenco) > MAX_MESSAGGI_PER_CANALE
        or not all(_messaggio_ok(m) for m in elenco)
        for nome, elenco in messaggi.items()
    ):
        errori.append(f"«messaggi»: al massimo {MAX_MESSAGGI_PER_CANALE} per canale, testi entro 2000 caratteri")
    for i, b in enumerate(dati.get("ban", [])):
        if not isinstance(b, dict) or not _int_ok(b.get("user_id"), 1 << 64) \
                or not _testo_o_none(b.get("motivo"), MAX_MOTIVO * 4):
            errori.append(f"ban {i + 1}: ID utente o motivo non validi")
    for i, m in enumerate(dati.get("membri", [])):
        if not isinstance(m, dict) or not _int_ok(m.get("user_id"), 1 << 64) \
                or not _testo_o_none(m.get("nick"), 32) or not _elenco_di_testi(m.get("ruoli", [])):
            errori.append(f"membro {i + 1}: ID, nickname o ruoli non validi")
    for chiave in ("emoji", "sticker"):
        for i, e in enumerate(dati.get(chiave, [])):
            if not isinstance(e, dict) or not _testo_ok(e.get("nome")) or not _testo_ok(e.get("url"), 2000) \
                    or not _testo_o_none(e.get("emoji"), 100):
                errori.append(f"{chiave} {i + 1}: nome o indirizzo non validi")
    if isinstance(imp, dict):
        for chiave in ("verification_level", "default_notifications", "explicit_content_filter", "afk_timeout"):
            if chiave in imp and not _int_ok(imp[chiave], 1 << 31):
                errori.append(f"impostazioni: «{chiave}» non valido")
        for chiave in ("afk_channel", "system_channel"):
            if not _testo_o_none(imp.get(chiave)):
                errori.append(f"impostazioni: «{chiave}» non valido")
    return errori[:20]


def leggi_json(contenuto: bytes) -> tuple[dict | None, list[str]]:
    """Il file caricato dall'admin: (dati, errori)."""
    if len(contenuto) > MAX_FILE_BYTE:
        return None, ["il file supera 10 MiB"]
    try:
        dati = json.loads(contenuto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as errore:
        return None, [f"JSON non leggibile: {str(errore)[:200]}"]
    errori = valida_struttura(dati)
    return (dati if not errori else None), errori


# ---------------------------------------------------------------- esportazione
def in_json(dati) -> bytes:
    return json.dumps(dati, ensure_ascii=False, indent=1).encode("utf-8")


def in_csv(righe: list[dict], colonne: list[str]) -> bytes:
    buffer = io.StringIO()
    scrittore = csv.DictWriter(buffer, fieldnames=colonne, extrasaction="ignore")
    scrittore.writeheader()
    for riga in righe:
        scrittore.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                            for k, v in riga.items()})
    return buffer.getvalue().encode("utf-8")


COLONNE_CSV = {
    "canali": ["nome", "tipo", "categoria", "posizione", "topic", "nsfw", "slowmode", "bitrate", "user_limit", "overwrite"],
    "ruoli": ["nome", "colore", "hoist", "mentionable", "permessi", "posizione"],
    "ban": ["user_id", "nome", "motivo"],
    "reazioni": ["emoji", "user_id", "nome"],
}


def esporta(cosa: str, formato: str, righe) -> tuple[bytes, str]:
    """(contenuto, estensione). `righe`: la struttura intera per «struttura», altrimenti un elenco."""
    if formato == "csv" and cosa in COLONNE_CSV:
        return in_csv(righe, COLONNE_CSV[cosa]), "csv"
    return in_json(righe), "json"


# ---------------------------------------------------------------- caricamento
@dataclass
class RiepilogoCaricamento:
    creati: int = 0
    riusati: int = 0
    saltati: int = 0
    falliti: int = 0
    annullato: bool = False
    note: list[str] = field(default_factory=list)

    def testo(self) -> str:
        righe = [
            f"✅ Creati: {self.creati}", f"♻️ Riusati o aggiornati: {self.riusati}",
            f"⏭️ Saltati (limiti o permessi): {self.saltati}", f"⚠️ Non riusciti: {self.falliti}",
        ]
        if self.annullato:
            righe.insert(0, "⏹️ Caricamento annullato: ciò che era già fatto resta.")
        righe += [f"• {n}" for n in self.note[:10]]
        return "\n".join(righe)[:4000]


class Annullato(Exception):
    """Segnale di stop letto tra un passo e l'altro (BKP-010)."""


Avanzamento = Callable[[str, int, int], Awaitable[bool]]


async def _niente(_passo: str, _fatti: int, _totale: int) -> bool:
    return False


def conta_passi(dati: dict, parti: set[str]) -> int:
    """Quanti passi farà il caricamento (per lo stato, BKP-009)."""
    elenchi = {"ruoli": ("ruoli",), "canali": ("categorie", "canali"), "emoji": ("emoji",),
               "ban": ("ban",), "membri": ("membri",)}
    passi = sum(len(dati.get(e, [])) for p in parti for e in elenchi.get(p, ()))
    if "messaggi" in parti:
        passi += sum(len(m) for m in (dati.get("messaggi") or {}).values())
    return passi


def parti_presenti(dati: dict) -> list[str]:
    """Le parti che il file contiene davvero (ban e membri solo se salvati)."""
    return [p for p in PARTI if p == "impostazioni" and dati.get("impostazioni")
            or p == "ruoli" and (dati.get("ruoli") or "everyone" in dati)
            or p == "canali" and (dati.get("canali") or dati.get("categorie"))
            or p == "emoji" and (dati.get("emoji") or dati.get("sticker"))
            or p in ("ban", "membri", "messaggi") and dati.get(p)]


def senza_dati_personali(dati: dict) -> dict:
    """Un modello (NF-39) si condivide senza ban, membri e permessi dei singoli utenti."""
    pulito = {k: v for k, v in dati.items() if k not in ("ban", "membri", "messaggi")}
    for chiave in ("categorie", "canali"):
        pulito[chiave] = [
            {**c, "overwrite": [o for o in c.get("overwrite", []) if "membro" not in o]}
            for c in dati.get(chiave, [])
        ]
    return pulito


class Caricatore:
    """
    Applica una struttura a un server. `avanza(passo, fatti, totale)` salva lo
    stato (BKP-009) e restituisce True se è stato chiesto di annullare (BKP-010).
    `scarica(url)` legge un'immagine (emoji e sticker); `pausa` tra ban e membri.
    `tetto`: il ruolo più alto di chi carica (None per l'owner del server). I ruoli
    da lì in su non si modificano, non si spostano e non si danno: la gerarchia
    vale per chi lancia il caricamento, non solo per il bot.
    """

    def __init__(
        self,
        guild: discord.Guild,
        dati: dict,
        parti: set[str],
        avanza: Avanzamento = _niente,
        scarica: Callable[[str], Awaitable[bytes | None]] | None = None,
        pausa: Callable[[float], Awaitable[None]] = asyncio.sleep,
        tetto=None,
    ) -> None:
        self.guild = guild
        self.dati = dati
        self.parti = parti
        self._avanza = avanza
        self._scarica = scarica
        self._pausa = pausa
        self._tetto = tetto
        self.r = RiepilogoCaricamento()
        self._fatti = 0
        self._per_categoria: dict[int, int] = {}
        self._canali_creati: dict[str, object] = {}
        self.scarica_file = scarica_file
        self._totale = conta_passi(dati, parti)

    async def _passo(self, nome: str) -> None:
        self._fatti += 1
        if await self._avanza(nome, self._fatti, self._totale):
            raise Annullato

    async def esegui(self) -> RiepilogoCaricamento:
        try:
            if "ruoli" in self.parti:
                await self._ruoli()
            if "canali" in self.parti:
                await self._canali()
            if "impostazioni" in self.parti:
                await self._impostazioni()
            if "emoji" in self.parti:
                await self._emoji()
            if "messaggi" in self.parti:
                await self._messaggi()
            if "membri" in self.parti:
                await self._membri()
            if "ban" in self.parti:
                await self._ban()
        except Annullato:
            self.r.annullato = True
        return self.r

    # ruoli ------------------------------------------------------------
    def _sopra_il_tetto(self, ruolo) -> bool:
        return self._tetto is not None and ruolo >= self._tetto

    def _nota(self, testo: str) -> None:
        if testo not in self.r.note:
            self.r.note.append(testo)

    def _ruolo_per_nome(self, nome: str):
        return discord.utils.get(self.guild.roles, name=nome)

    def _senza_nuovi_pericolosi(self, voluti: discord.Permissions, attuali: discord.Permissions) -> discord.Permissions:
        """I permessi pericolosi restano solo se il ruolo li aveva già."""
        tolti = voluti.value & PERMESSI_PERICOLOSI & ~attuali.value
        if tolti:
            self._nota("permessi pericolosi (admin, gestione, ban…) non aggiunti a @everyone né a ruoli esistenti")
        return discord.Permissions(voluti.value & ~tolti)

    async def _ruoli(self) -> None:
        if "everyone" in self.dati:
            try:
                everyone = self.guild.default_role
                await everyone.edit(
                    permissions=self._senza_nuovi_pericolosi(
                        _permessi_consentiti(self.guild, discord.Permissions(self.dati["everyone"])),
                        everyone.permissions,
                    ),
                    reason=MOTIVO,
                )
            except discord.HTTPException:
                self.r.falliti += 1
        ordine = {}
        for indice, dato in enumerate(sorted(self.dati.get("ruoli", []), key=lambda r: r.get("posizione", 0)), 1):
            await self._passo("ruoli")
            permessi = _permessi_consentiti(self.guild, discord.Permissions(dato.get("permessi", 0)))
            esistente = self._ruolo_per_nome(dato["nome"])
            try:
                if esistente is not None and self._sopra_il_tetto(esistente):
                    self.r.saltati += 1
                    self._nota("ruoli pari o sopra il tuo ruolo più alto: non toccati")
                    continue
                if esistente is not None and not esistente.managed:
                    permessi = self._senza_nuovi_pericolosi(permessi, esistente.permissions)
                    if esistente.permissions != permessi:
                        await esistente.edit(permissions=permessi, reason=MOTIVO)
                    self.r.riusati += 1
                    ordine[esistente] = indice
                    continue
                if len(self.guild.roles) >= MAX_RUOLI:
                    self.r.saltati += 1
                    continue
                nuovo = await self.guild.create_role(
                    name=dato["nome"][:MAX_NOME], permissions=permessi,
                    colour=discord.Colour(dato.get("colore", 0)), hoist=bool(dato.get("hoist")),
                    mentionable=bool(dato.get("mentionable")), reason=MOTIVO,
                )
                self.r.creati += 1
                ordine[nuovo] = indice
            except discord.HTTPException:
                self.r.falliti += 1
        if self._tetto is not None:
            # Nessun ruolo portato all'altezza di chi carica o sopra.
            alti = [r for r, p in ordine.items() if p >= self._tetto.position]
            for r in alti:
                del ordine[r]
            if alti:
                self._nota("alcuni ruoli lasciati sotto il tuo ruolo più alto")
        if ordine:
            try:
                await self.guild.edit_role_positions(ordine, reason=MOTIVO)
            except discord.HTTPException:
                self.r.note.append("ordine dei ruoli non impostato: sposta in alto il ruolo del bot")

    # canali -----------------------------------------------------------
    def _overwrites(self, righe: list[dict]) -> dict:
        risultato = {}
        for ow in righe:
            allow = ow["allow"]
            if ow.get("everyone"):
                bersaglio = self.guild.default_role
                allow &= ~PERMESSI_PERICOLOSI  # @everyone non gestisce canali, webhook o menzioni di massa
            elif "ruolo" in ow:
                bersaglio = self._ruolo_per_nome(ow["ruolo"])
            else:
                bersaglio = self.guild.get_member(ow["membro"])
            if bersaglio is None:
                continue
            pieno = discord.PermissionOverwrite.from_pair(
                discord.Permissions(allow), discord.Permissions(ow["deny"])
            )
            risultato[bersaglio] = _overwrite_consentito(self.guild, pieno)
        return risultato

    async def _canali(self) -> None:
        categorie = {c.name: c for c in self.guild.categories}
        totale = len(self.guild.channels)
        for dato in sorted(self.dati.get("categorie", []), key=lambda c: c.get("posizione", 0)):
            await self._passo("categorie")
            if dato["nome"] in categorie:
                self.r.riusati += 1
                continue
            if totale >= MAX_CANALI:
                self.r.saltati += 1
                continue
            try:
                categorie[dato["nome"]] = await self.guild.create_category(
                    name=dato["nome"][:MAX_NOME], overwrites=self._overwrites(dato.get("overwrite", [])), reason=MOTIVO
                )
                totale += 1
                self.r.creati += 1
            except discord.HTTPException:
                self.r.falliti += 1
        esistenti = {(c.name, _TIPI.get(c.type), _nome_o_none(c.category)) for c in self.guild.channels}
        for dato in sorted(self.dati.get("canali", []), key=lambda c: c.get("posizione", 0)):
            await self._passo("canali")
            if await self._crea_canale(dato, categorie, esistenti, totale):
                totale += 1

    async def _crea_canale(self, dato: dict, categorie: dict, esistenti: set, totale: int) -> bool:
        """True se ha creato il canale."""
        chiave = (dato["nome"], dato["tipo"], dato.get("categoria"))
        if chiave in esistenti:
            self.r.riusati += 1
            return False
        categoria = categorie.get(dato.get("categoria")) if dato.get("categoria") else None
        nella_categoria = self._per_categoria.get(categoria.id, len(categoria.channels)) if categoria else 0
        if totale >= MAX_CANALI or nella_categoria >= MAX_PER_CATEGORIA:
            self.r.saltati += 1
            return False
        kw = {"name": dato["nome"][:MAX_NOME], "category": categoria,
              "overwrites": self._overwrites(dato.get("overwrite", [])), "reason": MOTIVO}
        try:
            if dato["tipo"] in ("vocale", "palco"):
                kw["bitrate"] = min(dato.get("bitrate") or 64000, int(self.guild.bitrate_limit))
                kw["user_limit"] = dato.get("user_limit") or 0
                crea = self.guild.create_stage_channel if dato["tipo"] == "palco" else self.guild.create_voice_channel
                if dato["tipo"] == "palco":
                    kw.pop("user_limit")
            elif dato["tipo"] == "forum":
                kw["topic"] = dato.get("topic") or None
                kw["nsfw"] = bool(dato.get("nsfw"))
                crea = self.guild.create_forum
            else:
                kw["topic"] = dato.get("topic") or None
                kw["nsfw"] = bool(dato.get("nsfw"))
                kw["slowmode_delay"] = dato.get("slowmode") or 0
                kw["news"] = dato["tipo"] == "annunci"
                crea = self.guild.create_text_channel
            nuovo = await crea(**kw)
            if dato["tipo"] in ("testo", "annunci"):
                self._canali_creati[dato["nome"]] = nuovo
            if categoria is not None:
                self._per_categoria[categoria.id] = nella_categoria + 1
            esistenti.add(chiave)
            self.r.creati += 1
            return True
        except discord.HTTPException:
            self.r.falliti += 1
            return False

    # impostazioni -----------------------------------------------------
    async def _impostazioni(self) -> None:
        imp = self.dati.get("impostazioni") or {}
        kw = {}
        try:
            if "verification_level" in imp:
                kw["verification_level"] = discord.VerificationLevel(imp["verification_level"])
            if "default_notifications" in imp:
                kw["default_notifications"] = discord.NotificationLevel(imp["default_notifications"])
            if "explicit_content_filter" in imp:
                kw["explicit_content_filter"] = discord.ContentFilter(imp["explicit_content_filter"])
        except ValueError:
            self.r.note.append("impostazioni con valori sconosciuti: saltate")
            return
        if imp.get("afk_timeout") in (60, 300, 900, 1800, 3600):
            kw["afk_timeout"] = imp["afk_timeout"]
        for chiave, campo in (("afk_channel", "afk_channel"), ("system_channel", "system_channel")):
            if imp.get(chiave):
                canale = discord.utils.get(self.guild.channels, name=imp[chiave])
                if canale is not None:
                    kw[campo] = canale
        if not kw:
            return
        try:
            await self.guild.edit(reason=MOTIVO, **kw)
            self.r.riusati += 1
        except discord.HTTPException:
            self.r.falliti += 1

    # emoji e sticker --------------------------------------------------
    async def _emoji(self) -> None:
        if self._scarica is None:
            return
        presenti = {e.name for e in self.guild.emojis}
        for dato in self.dati.get("emoji", []):
            await self._passo("emoji")
            if dato["nome"] in presenti:
                self.r.riusati += 1
                continue
            if len(presenti) >= self.guild.emoji_limit:
                self.r.saltati += 1
                continue
            immagine = await self._scarica(dato["url"])
            if immagine is None:
                self.r.falliti += 1
                continue
            try:
                await self.guild.create_custom_emoji(name=dato["nome"][:32], image=immagine, reason=MOTIVO)
                presenti.add(dato["nome"])
                self.r.creati += 1
            except discord.HTTPException:
                self.r.falliti += 1
        presenti_s = {s.name for s in self.guild.stickers}
        for dato in self.dati.get("sticker", []):
            if dato["nome"] in presenti_s:
                self.r.riusati += 1
                continue
            if len(presenti_s) >= self.guild.sticker_limit:
                self.r.saltati += 1
                continue
            immagine = await self._scarica(dato["url"])
            if immagine is None:
                self.r.falliti += 1
                continue
            try:
                await self.guild.create_sticker(
                    name=dato["nome"][:30], description="", emoji=dato.get("emoji") or "⭐",
                    file=discord.File(io.BytesIO(immagine), filename="sticker.png"), reason=MOTIVO,
                )
                presenti_s.add(dato["nome"])
                self.r.creati += 1
            except discord.HTTPException:
                self.r.falliti += 1

    # messaggi (M 12.17) -----------------------------------------------
    async def _messaggi(self) -> None:
        """Gli ultimi messaggi salvati, nei canali di testo con lo stesso nome ancora vuoti."""
        for nome, elenco in (self.dati.get("messaggi") or {}).items():
            canale = self._canali_creati.get(nome) or discord.utils.get(
                getattr(self.guild, "text_channels", []), name=nome
            )
            if canale is None or not await messaggi_logic._destinazione_vuota(canale):
                self.r.saltati += len(elenco)
                self._fatti += len(elenco)
                continue
            try:
                webhook = await messaggi_logic.webhook_chat(canale)
            except discord.HTTPException:
                webhook = None
            if webhook is None:
                self.r.saltati += len(elenco)
                self._fatti += len(elenco)
                continue

            async def avanza(_passo, _fatti, _totale) -> bool:
                self._fatti += 1
                return await self._avanza("messaggi", self._fatti, self._totale)

            esito = await messaggi_logic.ricarica_chat(elenco, webhook, canale, avanza, self.scarica_file)
            self.r.creati += esito.copiati
            self.r.falliti += esito.falliti
            if esito.annullato:
                raise Annullato

    # membri e ban -----------------------------------------------------
    async def _membri(self) -> None:
        """BKP-014: nickname e ruoli ridati a chi è nel server; ruoli sopra il bot o gestiti saltati."""
        me = self.guild.me
        for dato in self.dati.get("membri", []):
            await self._passo("membri")
            membro = self.guild.get_member(dato["user_id"])
            if membro is None:
                self.r.saltati += 1
                continue
            ruoli = [
                r for r in (self._ruolo_per_nome(n) for n in dato.get("ruoli", []))
                if r is not None and not r.managed and r < me.top_role and r not in membro.roles
                and not self._sopra_il_tetto(r)
            ]
            puo_nick = membro.top_role < me.top_role and not self._sopra_il_tetto(membro.top_role)
            try:
                if ruoli:
                    await membro.add_roles(*ruoli, reason=MOTIVO)
                if dato.get("nick") and membro.nick != dato["nick"] and puo_nick:
                    await membro.edit(nick=dato["nick"][:32], reason=MOTIVO)
                self.r.riusati += 1
            except discord.HTTPException:
                self.r.falliti += 1
            await self._pausa(0.5)

    async def _ban(self) -> None:
        """BKP-015: ban ricaricati uno alla volta, con il motivo (≤ 512)."""
        for dato in self.dati.get("ban", []):
            await self._passo("ban")
            try:
                await self.guild.ban(
                    discord.Object(id=dato["user_id"]),
                    reason=(dato.get("motivo") or MOTIVO)[:MAX_MOTIVO],
                    delete_message_seconds=0,
                )
                self.r.creati += 1
            except discord.NotFound:
                self.r.saltati += 1  # account cancellato
            except discord.HTTPException:
                self.r.falliti += 1
            await self._pausa(1.0)


# ---------------------------------------------------------------- immagini
HOST_IMMAGINI = ("cdn.discordapp.com", "media.discordapp.net")
MAX_IMMAGINE_BYTE = 512 * 1024


def url_immagine_ammesso(url: str) -> bool:
    """Solo immagini di Discord: un file importato non fa scaricare indirizzi qualsiasi."""
    from urllib.parse import urlparse

    parti = urlparse(url) if isinstance(url, str) else None
    return parti is not None and parti.scheme == "https" and parti.hostname in HOST_IMMAGINI


async def scarica_immagine(url: str) -> bytes | None:
    """Emoji o sticker da ricreare (≤ 512 KiB). None se non ammesso o non leggibile."""
    return await scarica_file(url, MAX_IMMAGINE_BYTE)


async def scarica_file(url: str, massimo: int) -> bytes | None:
    """Un file dalla CDN di Discord (≤ `massimo` byte). None se non ammesso, scaduto o troppo grande."""
    if not url_immagine_ammesso(url) or massimo <= 0:
        return None
    import aiohttp

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as sessione:
            async with sessione.get(url, allow_redirects=False) as risposta:
                if risposta.status != 200:
                    return None
                dati = await risposta.content.read(massimo + 1)
                return dati if len(dati) <= massimo else None
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None
