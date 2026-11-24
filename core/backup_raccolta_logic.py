"""
core/backup_raccolta_logic.py
=============================
Raccolta pubblica dei modelli di server (BKP-022/023, D127): un server propone la sua struttura (ruoli, categorie, canali,
permessi), l'owner del bot la approva o la rifiuta, i modelli approvati si votano e si usano. Qui la parte senza rete né
Discord: la struttura si RICOSTRUISCE campo per campo (niente ID, membri, messaggi, ban né altro dato personale), i nomi si
puliscono, i tetti si controllano e si dice quali ruoli hanno permessi pericolosi (servono la conferma del proprietario
del server al momento dell'uso) e che cosa manca in un server.
Funzioni coperte: BKP-022, BKP-023 (D127, D130)
Dipende da: core/backup_struttura_logic.py
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import discord

from core import backup_struttura_logic as st

MAX_RUOLI_RACCOLTA = 100
MAX_CATEGORIE_RACCOLTA = 50
MAX_CANALI_RACCOLTA = 200
NOME_MIN, NOME_MAX = 3, 60
DESCRIZIONE_MAX = 300
RICERCA_MAX = 40
MAX_IN_REVISIONE_PER_SERVER = 3
LINGUE = ("it", "en-US", "es-ES", "fr", "de", "ja", "ko", "ru", "uk", "zh-CN")
STATI = ("revisione", "approvato", "rifiutato")

_MENZIONE = re.compile(r"<[@#][^>]{0,40}>|@(?:everyone|here)", re.IGNORECASE)
_LINK = re.compile(r"(?:https?://|discord\.gg/|discord\.com/invite/|www\.)\S+", re.IGNORECASE)
_SPAZI = re.compile(r"\s+")


def pulisci_testo(testo, massimo: int, *, a_capo: bool = False) -> str:
    """Un testo libero senza caratteri di controllo né invisibili, menzioni, link o invii; spazi ridotti. Vuoto se non resta niente."""
    if not isinstance(testo, str):
        return ""
    testo = unicodedata.normalize("NFKC", testo)
    testo = "".join(c for c in testo if c in ("\n",) and a_capo or unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    testo = _LINK.sub("", _MENZIONE.sub("", testo))
    testo = _SPAZI.sub(" ", testo) if not a_capo else "\n".join(_SPAZI.sub(" ", r).strip() for r in testo.split("\n"))
    return testo.strip()[:massimo].strip()


def nome_modello(testo) -> str | None:
    """Il nome di un modello nella raccolta (3-60 caratteri puliti) o None."""
    nome = pulisci_testo(testo, NOME_MAX)
    return nome if len(nome) >= NOME_MIN else None


def descrizione_modello(testo) -> str:
    return pulisci_testo(testo, DESCRIZIONE_MAX, a_capo=True)


def lingua_valida(lingua) -> str | None:
    return lingua if lingua in LINGUE else None


def ricerca_pulita(testo) -> str:
    """Il testo da cercare: senza i caratteri jolly di LIKE."""
    return pulisci_testo(testo, RICERCA_MAX).replace("%", "").replace("_", "").replace("\\", "")


def _int(valore, massimo: int, ripiego: int = 0) -> int:
    return valore if isinstance(valore, int) and not isinstance(valore, bool) and 0 <= valore < massimo else ripiego


def _overwrite_puliti(righe, nomi_ruoli: set[str]) -> list[dict]:
    """Solo @everyone e ruoli della stessa struttura; mai un membro; mai un permesso pericoloso concesso."""
    risultato = []
    for ow in righe if isinstance(righe, list) else []:
        if not isinstance(ow, dict) or "membro" in ow:
            continue
        allow, deny = _int(ow.get("allow"), st.MAX_PERMESSI), _int(ow.get("deny"), st.MAX_PERMESSI)
        allow &= ~st.PERMESSI_PERICOLOSI
        if ow.get("everyone") is True:
            risultato.append({"everyone": True, "allow": allow, "deny": deny})
        elif isinstance(ow.get("ruolo"), str) and ow["ruolo"] in nomi_ruoli:
            risultato.append({"ruolo": ow["ruolo"], "allow": allow, "deny": deny})
    return risultato[:25]


def prepara_struttura(dati) -> tuple[dict | None, list[str]]:
    """
    (struttura pulita, errori). La struttura nuova è costruita da zero con i soli campi noti: ciò che non è nell'elenco
    (ID, membri, messaggi, ban, emoji, impostazioni, campi sconosciuti) non passa. Errori: tetti, nomi vuoti o doppi, formato.
    """
    if not isinstance(dati, dict):
        return None, ["la struttura non è un oggetto"]
    if dati.get("versione") != st.VERSIONE:
        return None, [f"versione non supportata (serve {st.VERSIONE})"]
    if dati.get("tipo") == "chat":
        return None, ["una chat salvata non è un modello"]
    errori: list[str] = []
    grezzi = {k: dati.get(k, []) for k in ("ruoli", "categorie", "canali")}
    for chiave, tetto in (("ruoli", MAX_RUOLI_RACCOLTA), ("categorie", MAX_CATEGORIE_RACCOLTA), ("canali", MAX_CANALI_RACCOLTA)):
        if not isinstance(grezzi[chiave], list):
            errori.append(f"«{chiave}» deve essere un elenco")
        elif len(grezzi[chiave]) > tetto:
            errori.append(f"«{chiave}»: {len(grezzi[chiave])} elementi, al massimo {tetto}")
    if errori:
        return None, errori

    ruoli, visti = [], set()
    for r in grezzi["ruoli"]:
        nome = pulisci_testo(r.get("nome") if isinstance(r, dict) else None, st.MAX_NOME)
        if not nome:
            errori.append("un ruolo ha il nome vuoto")
        elif nome.casefold() in visti:
            errori.append(f"ruolo doppio: «{nome}»")
        else:
            visti.add(nome.casefold())
            ruoli.append({
                "nome": nome, "colore": _int(r.get("colore"), 1 << 24), "hoist": r.get("hoist") is True,
                "mentionable": r.get("mentionable") is True, "permessi": _int(r.get("permessi"), st.MAX_PERMESSI),
                "posizione": _int(r.get("posizione"), 1 << 31),
            })
    nomi_ruoli = {r["nome"] for r in ruoli}

    categorie, nomi_categorie = [], set()
    for c in grezzi["categorie"]:
        nome = pulisci_testo(c.get("nome") if isinstance(c, dict) else None, st.MAX_NOME)
        if not nome:
            errori.append("una categoria ha il nome vuoto")
        elif nome.casefold() in nomi_categorie:
            errori.append(f"categoria doppia: «{nome}»")
        else:
            nomi_categorie.add(nome.casefold())
            categorie.append({"nome": nome, "posizione": _int(c.get("posizione"), 1 << 31),
                              "overwrite": _overwrite_puliti(c.get("overwrite"), nomi_ruoli)})
    nomi_categorie_esatti = {c["nome"] for c in categorie}

    canali, chiavi = [], set()
    per_categoria: dict[str | None, int] = {}
    for c in grezzi["canali"]:
        if not isinstance(c, dict) or c.get("tipo") not in st.TIPI_CANALE:
            errori.append("un canale ha il tipo non valido")
            continue
        nome = pulisci_testo(c.get("nome"), st.MAX_NOME)
        categoria = pulisci_testo(c.get("categoria"), st.MAX_NOME) or None
        if not nome:
            errori.append("un canale ha il nome vuoto")
            continue
        if categoria is not None and categoria not in nomi_categorie_esatti:
            categoria = None  # una categoria che non c'è: il canale resta fuori da ogni categoria
        chiave = (nome.casefold(), c["tipo"], categoria)
        if chiave in chiavi:
            errori.append(f"canale doppio: «{nome}»")
            continue
        chiavi.add(chiave)
        per_categoria[categoria] = per_categoria.get(categoria, 0) + 1
        canali.append({
            "nome": nome, "tipo": c["tipo"], "categoria": categoria, "posizione": _int(c.get("posizione"), 1 << 31),
            "topic": pulisci_testo(c.get("topic"), 200) or None, "nsfw": c.get("nsfw") is True,
            "slowmode": _int(c.get("slowmode"), 21601), "bitrate": _int(c.get("bitrate"), 1 << 31, 0) or None,
            "user_limit": _int(c.get("user_limit"), 100) or None,
            "overwrite": _overwrite_puliti(c.get("overwrite"), nomi_ruoli),
        })
    if any(n > st.MAX_PER_CATEGORIA for k, n in per_categoria.items() if k is not None):
        errori.append(f"al massimo {st.MAX_PER_CATEGORIA} canali per categoria")
    if not ruoli and not canali and not categorie:
        errori.append("il modello è vuoto")
    if errori:
        return None, errori[:20]
    pulita = {
        "versione": st.VERSIONE, "everyone": _int(dati.get("everyone"), st.MAX_PERMESSI) & ~st.PERMESSI_PERICOLOSI,
        "ruoli": ruoli, "categorie": categorie, "canali": canali,
    }
    problemi = st.valida_struttura(pulita)
    return (None, problemi) if problemi else (pulita, [])


def ruoli_pericolosi(dati: dict) -> list[str]:
    """I nomi dei ruoli con permessi pericolosi (admin, gestione, ban…): senza la conferma del proprietario nascono senza."""
    return [r["nome"] for r in dati.get("ruoli", []) if int(r.get("permessi", 0)) & st.PERMESSI_PERICOLOSI]


def permessi_pericolosi_di(ruolo: dict) -> list[str]:
    """I nomi dei permessi pericolosi di un ruolo (per dirli al proprietario)."""
    valore = discord.Permissions(int(ruolo.get("permessi", 0)) & st.PERMESSI_PERICOLOSI)
    return sorted(nome for nome, attivo in valore if attivo)


@dataclass
class Mancanti:
    ruoli: list[str] = field(default_factory=list)
    categorie: list[str] = field(default_factory=list)
    canali: list[str] = field(default_factory=list)

    def totale(self) -> int:
        return len(self.ruoli) + len(self.categorie) + len(self.canali)


def mancanti(guild, dati: dict) -> Mancanti:
    """Che cosa del modello NON c'è nel server (stesse chiavi del caricamento: ruolo e categoria per nome, canale per nome, tipo e categoria)."""
    m = Mancanti()
    ruoli = {r.name for r in guild.roles}
    categorie = {c.name for c in guild.categories}
    esistenti = {
        (c.name, st._TIPI.get(c.type), getattr(c.category, "name", None) if c.category is not None else None)
        for c in guild.channels
    }
    m.ruoli = [r["nome"] for r in dati.get("ruoli", []) if r["nome"] not in ruoli]
    m.categorie = [c["nome"] for c in dati.get("categorie", []) if c["nome"] not in categorie]
    m.canali = [c["nome"] for c in dati.get("canali", []) if (c["nome"], c["tipo"], c.get("categoria")) not in esistenti]
    return m
