"""
core/command_groups.py
======================
I gruppi di primo livello della mappa F7 (più quelli nati con D25 e D26), definiti una volta sola e
usati da tutti i cog. Nomi e descrizioni italiani, `guild_only`,
permessi predefiniti e livello di accesso (core/command_access.py).
In più il MODO UNICO per mettere il comando di un cog in un gruppo:
`@comando_di_gruppo`, `CogConGruppi`.
Funzioni coperte: SPEC §20 (NF-05)
Dipende da: core/command_access.py;
revisione/02-piano/MAPPA_COMANDI_F7.md §5

Come si sposta un comando (ricetta)
-----------------------------------
1. Il cog eredita `CogConGruppi` PRIMA di `commands.Cog`.
2. Al posto di `@app_commands.command(name=..., description=...)` scrivi
   `@comando_di_gruppo("admin-bot", nome=..., descrizione=..., sottogruppo=None)`:
   deve essere il decoratore PIÙ ESTERNO; describe, choices, rename,
   autocomplete, checks.cooldown restano sotto, come oggi.
3. Togli i check di permesso (`has_permissions`, `richiedi`): li dà il
   gruppo. Tolto anche il prefisso `[Admin] ` dalla descrizione.
4. Un `Group` definito dentro il cog (`/clan`, `/ticket`, `/voice`,
   `/music`) sparisce: ogni suo comando diventa `@comando_di_gruppo("clan", ...)`
   sul gruppo condiviso; un sotto-livello è `sottogruppo=("nome", "descrizione")`.
   Un Group del cog con lo stesso nome del gruppo condiviso dà ValueError.
5. Gli autocomplete sotto un gruppo protetto usano `autocomplete_protetto`.
6. Nei test il comando resta `cog.metodo.callback(cog, interaction, ...)`.
Esempio: cogs/logging/basic_logs.py (`/admin-log canale`). Se il cog ha un suo
`cog_load`/`cog_unload`, deve chiamare `await super().cog_load()` / `cog_unload()`.

Nessun gruppo entra da solo nell'albero del bot: i gruppi vuoti non si
sincronizzano. `registra_comandi_del_cog` aggiunge il gruppo all'albero
quando il primo comando arriva e lo toglie quando l'ultimo se ne va;
`registra_gruppi_usati` è una funzione di appoggio (oggi usata solo dai test,
main.py non la chiama). `/owner` non entra mai da qui: va aggiunto a parte, solo nel server dell'owner (`registra_owner`, mappa §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import discord
from discord import app_commands

from core.command_access import GruppoYokai, Livello

# I due comandi di primo livello fuori dai gruppi (D24, 06/10/2026). Il trattino
# davanti li fa salire in lista; la regex dei nomi di Discord lo ammette.
NOME_CERCA_COMANDO = "-cerca-comando"
NOME_CHIEDI = "-chiedi"

# nome: (descrizione, permesso predefinito di Discord o None, livello)
_DEFINIZIONI: dict[str, tuple[str, str | None, Livello | None]] = {
    "owner": ("Comandi riservati al proprietario del bot", "administrator", Livello.OWNER),
    "admin-bot": ("Impianto del bot: setup, configurazione, lingua, politica dei comandi, premium", "manage_guild", Livello.ADMIN),
    "admin-musica": ("Musica del server (admin): canale delle richieste, impostazioni, riepilogo", "manage_guild", Livello.ADMIN),
    "admin-ai": ("AI del server (admin): consenso, limiti, lore, conoscenza, funzioni, staff", "manage_guild", Livello.ADMIN),
    "admin-automod": ("AutoMod (admin): parole vietate, esenzioni, violazioni, odio", "manage_guild", Livello.ADMIN),
    "admin-filtri": ("Filtri automatici sui messaggi (admin) e loro azioni", "manage_guild", Livello.ADMIN),
    "admin-sicurezza": ("Sicurezza (admin): panico, verifica, ban globale, spam-trap, escalation", "administrator", Livello.SECURITY),
    "admin-antinuke": ("Anti-nuke (admin): soglie, fiducia, guardie e casi", "administrator", Livello.SECURITY),
    "admin-antiraid": ("Anti-raid (admin): soglie, filtri all'ingresso, segnali e allarmi", "administrator", Livello.SECURITY),
    "admin-moduli": ("Moduli del server (admin): alert, starboard, contatori, compleanni, inviti", "manage_guild", Livello.ADMIN),
    "admin-economia": ("Economia (admin): negozio, cassa, premi in monete, annunci del mese", "manage_guild", Livello.ADMIN),
    "admin-livelli": ("Livelli e XP (admin): guadagno, annunci, premi, esclusioni, progressi", "manage_guild", Livello.ADMIN),
    "admin-ruoli": ("Ruoli del server (admin): dai e togli, premio, automatici, menu, in massa", "manage_guild", Livello.ADMIN),
    "admin-log": ("Registro degli eventi (admin): canali, stato, ricerca, esportazione", "manage_guild", Livello.LOG),
    "admin-messaggi": ("Messaggi del server (admin): embed, tag, risposte, programmati, fissi", "manage_guild", Livello.ADMIN),
    "admin-giveaway": ("Giveaway del server (admin): avvio, modelli, programmati", "manage_guild", Livello.ADMIN),
    "admin-ticket": ("Ticket (admin): impianto, categorie, ruoli, ModMail, risposte, pannelli", "manage_guild", Livello.ADMIN),
    "admin-ticket-opzioni": ("Opzioni dei pannelli ticket (admin): limiti, orari, accesso, chiusura", "manage_guild", Livello.ADMIN),
    "admin-backup": ("Backup del server (admin): copia, ripristino, modelli, chat, esportazioni", "administrator", Livello.ADMIN),
    "admin-benvenuto": ("Benvenuto, addio e boost (admin): messaggi, immagine, anteprima", "manage_guild", Livello.ADMIN),
    "admin-vocali": ("Vocali temporanei (admin): generatore, pannello, limite, ruoli piattaforma", "manage_guild", Livello.ADMIN),
    "mod-sanzioni": ("Moderazione: avvisi, timeout, silenzio, in massa, opzioni", "moderate_members", Livello.MOD),
    "mod-casi": ("Moderazione: casi, note, avvisi dati, rischio e carico dello staff", "moderate_members", Livello.MOD),
    "mod-canali": ("Moderazione dei canali: blocco, lentezza, pulizia dei messaggi", "moderate_members", Livello.MOD),
    "mod-ban": ("Moderazione dura: ban, kick, softban, sban, in massa, appelli", "ban_members", Livello.MODBAN),
    "founder": ("Solo per il proprietario del server (gli altri admin lo vedono ma sono rifiutati)", "administrator", Livello.FOUNDER),
    "ticket": ("Gestione del ticket in cui ti trovi", None, None),
    "voice": ("Gestione del tuo canale vocale temporaneo", None, None),
    "music": ("Musica nei canali vocali", None, None),
    "level": ("Livelli, classifiche, profilo, collezione e inviti", None, None),
    "monete": ("Le tue monete: saldo, giornaliera, lavoro, pagamenti, negozio", None, None),
    "clan": ("Clan del server: crea, gestisci e fai crescere il tuo clan", None, None),
    "fun": ("Divertimento: dadi, domande, battute, giochi di fortuna", None, None),
    "immagini": ("Immagini: filtri, meme, effetti, animali, ricerca", None, None),
    "giochi": ("Giochi con le monete e contro il bot", None, None),
    "sondaggi": ("Sondaggi del server", None, None),
    "assistente": ("Funzioni AI per tutti: riassunti, traduzioni, immagini, personaggi", None, None),
    "gif": ("GIF di reazione e di azione", None, None),
    "utility": ("Strumenti utili: segnalazioni, suggerimenti, promemoria, schede, snipe", None, None),
}


# I sotto-gruppi dei comandi spostati dai riordini D56 e D60: nome e descrizione in un posto solo.
# Chiave: "gruppo sotto-gruppo". Il cog scrive `sottogruppo=SOTTOGRUPPI["admin-ruoli premio"]`.
SOTTOGRUPPI: dict[str, tuple[str, str]] = {
    "founder backup": ("backup", "Backup: sincronia e chi può creare o caricare"),
    "founder moderazione": ("moderazione", "Moderazione: ruoli immuni"),
    "admin-backup copia": ("copia", "Copia un canale o un ruolo"),
    "admin-backup chat": ("chat", "Chat salvate: salva e ricarica"),
    "admin-backup ripristino": ("ripristino", "Ripristino degli utenti via OAuth2"),
    "admin-ticket pannelli": ("pannelli", "Pannelli dei ticket: crea, pubblica, modulo"),
    "utility snipe": ("snipe", "Messaggi cancellati, modificati e reazioni tolte"),
    "admin-bot politica": ("politica", "Politica dei comandi: spegni, limita, ignora, diagnosi"),
    "admin-messaggi programmati": ("programmati", "Messaggi programmati a orario"),
    "admin-messaggi fissi": ("fissi", "Messaggi fissi in fondo al canale"),
    "admin-messaggi risposte": ("risposte", "Risposte automatiche a parole chiave"),
    "admin-messaggi tag": ("tag", "Tag: comandi personalizzati con testo"),
    "admin-messaggi embed": ("embed", "Embed personalizzati"),
    "admin-ticket categoria": ("categoria", "Categorie dei ticket"),
    "admin-ticket ruolo": ("ruolo", "Ruoli di supporto dei ticket"),
    "admin-ticket modmail": ("modmail", "ModMail: ticket dai messaggi privati"),
    "admin-ticket risposte": ("risposte", "Risposte standard dei ticket"),
    "admin-ruoli premio": ("premio", "Ruoli premio per livello"),
    "admin-ruoli auto": ("auto", "Ruoli automatici all'ingresso"),
    "admin-ruoli menu": ("menu", "Menu per scegliere i ruoli"),
    "monete shop": ("shop", "Negozio del server"),
    "admin-economia annunci": ("annunci", "Annunci di fine mese: vincitori e clan"),
    "owner ai": ("ai", "AI globale: manutenzione, modelli, rete del boss"),
}


def nomi_gruppi() -> tuple[str, ...]:
    """I nomi dei gruppi, nell'ordine della mappa."""
    return tuple(_DEFINIZIONI)


def costruisci_gruppi() -> dict[str, GruppoYokai]:
    """Costruisce un insieme NUOVO di gruppi (per i test; il bot usa GRUPPI)."""
    gruppi: dict[str, GruppoYokai] = {}
    for nome, (descrizione, permesso, livello) in _DEFINIZIONI.items():
        gruppi[nome] = GruppoYokai(
            name=nome,
            description=descrizione,
            guild_only=True,
            default_permissions=discord.Permissions(**{permesso: True}) if permesso else None,
            livello=livello,
        )
    return gruppi


GRUPPI: dict[str, GruppoYokai] = costruisci_gruppi()


def ottieni_gruppo(nome: str) -> GruppoYokai:
    """Il gruppo di primo livello con questo nome (KeyError se non esiste)."""
    return GRUPPI[nome]


def aggiungi_a_gruppo(
    nome: str,
    comando: app_commands.Command | app_commands.Group,
    *,
    sottogruppo: tuple[str, str] | None = None,
    gruppi: dict[str, GruppoYokai] | None = None,
) -> None:
    """
    Aggiunge un comando al gruppo `nome`, o a un suo sotto-gruppo
    (`sottogruppo=("nome", "descrizione")`, creato la prima volta).
    Si può richiamare più volte con lo stesso comando (un cog che si
    ricarica): sostituisce, non duplica.
    """
    tutti = GRUPPI if gruppi is None else gruppi
    destinazione: app_commands.Group = tutti[nome]
    if sottogruppo is not None:
        nome_sotto, descrizione_sotto = sottogruppo
        esistente = destinazione.get_command(nome_sotto)
        if esistente is None:
            esistente = GruppoYokai(name=nome_sotto, description=descrizione_sotto, parent=destinazione)
        destinazione = esistente
    destinazione.add_command(comando, override=True)


def registra_gruppi_usati(
    tree: app_commands.CommandTree,
    *,
    gruppi: dict[str, GruppoYokai] | None = None,
) -> list[str]:
    """Aggiunge all'albero i gruppi che hanno comandi (tranne `owner`). Restituisce i nomi."""
    tutti = GRUPPI if gruppi is None else gruppi
    aggiunti = []
    for nome, gruppo in tutti.items():
        if nome == "owner" or not gruppo.commands:
            continue
        _conflitto_nell_albero(tree, nome, gruppo)
        tree.add_command(gruppo, override=True)
        aggiunti.append(nome)
    return aggiunti


def _conflitto_nell_albero(tree: app_commands.CommandTree, nome: str, gruppo: GruppoYokai) -> None:
    """ValueError se nell'albero c'è già un comando di primo livello con quel nome che non è il gruppo condiviso."""
    esistente = tree.get_command(nome)
    if esistente is not None and esistente is not gruppo:
        raise ValueError(
            f"Nell'albero esiste già '/{nome}' e non è il gruppo condiviso di "
            f"core/command_groups.py: il cog deve smettere di definire il suo Group "
            f"e usare @comando_di_gruppo('{nome}', ...)."
        )


def registra_owner(
    tree: app_commands.CommandTree,
    guild_id: int,
    *,
    gruppi: dict[str, GruppoYokai] | None = None,
) -> bool:
    """
    Aggiunge `/owner` SOLO per il server dell'owner (mappa §5), mai globale:
    `copy_global_to` non lo copia, quindi non compare due volte. True se aggiunto.
    """
    tutti = GRUPPI if gruppi is None else gruppi
    gruppo = tutti["owner"]
    if not gruppo.commands:
        return False
    tree.add_command(gruppo, guild=discord.Object(id=guild_id), override=True)
    return True


# ----------------------------------------------------------------------
# Il modo unico per spostare un comando di un cog in un gruppo
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class _Marca:
    gruppo: str
    nome: str
    descrizione: str
    sottogruppo: tuple[str, str] | None


class ComandoDiGruppo:
    """
    Il metodo marcato da `@comando_di_gruppo`. `.callback` è la funzione
    originale (si chiama `.callback(cog, interaction, ...)` come per un
    `app_commands.Command`). Il vero Command nasce in `registra_comandi_del_cog`.
    """

    def __init__(self, callback, marca: _Marca) -> None:
        self.callback = callback
        self.marca = marca
        self.__doc__ = callback.__doc__
        self.__name__ = callback.__name__

    def __get__(self, istanza, tipo=None):
        return self

    def __set_name__(self, tipo, nome) -> None:
        self.attributo = nome


def comando_di_gruppo(
    gruppo: str,
    *,
    nome: str,
    descrizione: str,
    sottogruppo: tuple[str, str] | None = None,
):
    """
    Marca un metodo di un cog come comando di `gruppo` (o del suo
    `sottogruppo=("nome", "descrizione")`). Va messo come decoratore
    PIÙ ESTERNO. Il comando non entra da solo nell'albero di primo livello.
    """

    def decorator(funzione) -> ComandoDiGruppo:
        if isinstance(funzione, (app_commands.Command, ComandoDiGruppo)):
            raise TypeError("@comando_di_gruppo va messo come decoratore più esterno, sopra describe/choices/checks.")
        return ComandoDiGruppo(funzione, _Marca(gruppo, nome, descrizione, sottogruppo))

    return decorator


def _comandi_marcati(cog) -> list[ComandoDiGruppo]:
    visti: dict[str, ComandoDiGruppo] = {}
    for classe in reversed(type(cog).__mro__):
        for chiave, valore in vars(classe).items():
            if isinstance(valore, ComandoDiGruppo):
                visti[chiave] = valore
            elif chiave in visti:
                del visti[chiave]
    return list(visti.values())


def _stessa_classe(a: object, b: object) -> bool:
    """Stesso cog anche se un reload ha ricreato la classe (stesso modulo e nome)."""
    ta, tb = type(a), type(b)
    return ta is tb or (ta.__module__, ta.__qualname__) == (tb.__module__, tb.__qualname__)


def registra_comandi_del_cog(
    cog,
    *,
    gruppi: dict[str, GruppoYokai] | None = None,
    tree: app_commands.CommandTree | None = None,
) -> list[app_commands.Command]:
    """
    Crea i veri Command dei metodi marcati (callback legato al cog), li
    mette nei gruppi e aggiunge all'albero i gruppi che ne hanno bisogno.
    Richiamarla di nuovo per lo stesso cog sostituisce, non duplica.
    ValueError se il nome è già di un altro cog o di un Group del cog stesso.
    """
    if gruppi is None:
        gruppi = getattr(cog, "gruppi_yokai", None)
    tutti = GRUPPI if gruppi is None else gruppi
    if tree is None:
        tree = getattr(getattr(cog, "bot", None), "tree", None)
    togli_comandi_del_cog(cog)

    marcati = _comandi_marcati(cog)
    for m in marcati:  # prima controlla tutto, poi tocca l'albero
        if m.marca.gruppo not in tutti:
            raise KeyError(f"Gruppo sconosciuto '{m.marca.gruppo}' per il comando '{m.marca.nome}'.")
        if tree is not None and m.marca.gruppo != "owner":
            _conflitto_nell_albero(tree, m.marca.gruppo, tutti[m.marca.gruppo])

    registrati: list[tuple[str, tuple[str, str] | None, app_commands.Command]] = []
    try:
        for m in marcati:
            marca = m.marca
            comando = app_commands.Command(name=marca.nome, description=marca.descrizione, callback=m.callback)
            comando.binding = cog
            radice = tutti[marca.gruppo]
            dove: Any = radice if marca.sottogruppo is None else radice.get_command(marca.sottogruppo[0])
            presente = dove.get_command(marca.nome) if dove is not None else None
            if presente is not None and not _stessa_classe(presente.binding, cog):
                raise ValueError(
                    f"'/{marca.gruppo} {marca.nome}' esiste già, di un altro cog: scegli un altro nome."
                )
            aggiungi_a_gruppo(marca.gruppo, comando, sottogruppo=marca.sottogruppo, gruppi=tutti)
            registrati.append((marca.gruppo, marca.sottogruppo, comando))
    except Exception:
        cog._yokai_registrazioni = (tutti, tree, registrati)
        togli_comandi_del_cog(cog)
        raise
    if tree is not None:
        for nome in {g for g, _, _ in registrati} - {"owner"}:  # /owner: solo registra_owner
            if tree.get_command(nome) is None:
                tree.add_command(tutti[nome], override=True)
    cog._yokai_registrazioni = (tutti, tree, registrati)
    return [c for _, _, c in registrati]


def togli_comandi_del_cog(cog) -> None:
    """Toglie i comandi messi da `registra_comandi_del_cog`, e sotto-gruppi e gruppi rimasti vuoti."""
    stato = getattr(cog, "_yokai_registrazioni", None)
    if stato is None:
        return
    tutti, tree, registrati = stato
    cog._yokai_registrazioni = None
    for nome_gruppo, sottogruppo, comando in registrati:
        radice = tutti[nome_gruppo]
        dove: Any = radice if sottogruppo is None else radice.get_command(sottogruppo[0])
        if dove is not None and dove.get_command(comando.name) is comando:
            dove.remove_command(comando.name)
        if sottogruppo is not None and dove is not None and not dove.commands:
            radice.remove_command(dove.name)
        if not radice.commands and tree is not None and tree.get_command(nome_gruppo) is radice:
            tree.remove_command(nome_gruppo)


class CogConGruppi:
    """
    Mixin per i cog con comandi in un gruppo: `class MioCog(CogConGruppi, commands.Cog)`.
    Registra i comandi in `cog_load` e li toglie in `cog_unload`, così
    `/owner cog reload` non duplica e non lascia comandi orfani.
    """

    async def cog_load(self) -> None:
        registra_comandi_del_cog(self)
        parent = getattr(super(), "cog_load", None)
        if parent is not None:
            await parent()

    async def cog_unload(self) -> None:
        togli_comandi_del_cog(self)
        parent = getattr(super(), "cog_unload", None)
        if parent is not None:
            result = parent()
            if hasattr(result, "__await__"):
                await result
