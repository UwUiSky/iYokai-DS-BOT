"""
tests/test_cog_manager_load_all.py
======================================
Test di regressione per un bug reale trovato in questa sessione:
`/clear-queue` (Music) era stato scritto inizialmente come `/clear`
— nome già usato da `/clear` di moderation (cancellazione messaggi).
Un comando slash con nome duplicato fa fallire la REGISTRAZIONE
dell'intero cog che lo dichiara, non solo di quel comando — e
`core.cog_manager.load_all_cogs` CATTURA e LOGGA ogni eccezione di
`setup()` per singolo cog senza farla risalire (di proposito: un cog
rotto non deve bloccare l'avvio di tutto il resto), quindi l'intero
modulo Music si sarebbe disattivato in silenzio in produzione. Il
bug non è mai stato notato dai test unitari perché ognuno istanzia
il proprio cog da solo, senza mai unire il suo albero comandi a
quello di TUTTI gli altri cog insieme come fa il bot vero — è stato
scoperto solo rilanciando scripts/generate_command_list.py a mano.

Questo test chiude esattamente quel buco: chiama DAVVERO il setup()
di ogni cog scoperto da `discover_cog_modules()` dentro lo STESSO
bot/albero comandi (esattamente come fa il bot in produzione), e
verifica che NESSUNO fallisca — qualunque nome duplicato, in
qualunque cog futuro, lo farebbe fallire qui.

**Nota tecnica importante** (trovata scrivendo questo stesso test):
NON si può usare `bot.load_extension(modulo_path)` per farlo —
`discord.ext.commands.Bot._load_from_module_spec` ricrea ed esegue
da capo il modulo con `importlib.util.module_from_spec` +
`exec_module`, e SOVRASCRIVE `sys.modules[modulo_path]` con questo
nuovo oggetto modulo OGNI VOLTA che viene chiamato — anche se il
modulo era già stato importato altrove. Usarlo qui avrebbe
sostituito silenziosamente, per il resto dell'intera sessione
pytest, i moduli di OGNI cog del progetto (classi, singleton come
`eval_shell_log_repo`, tutto) con una copia fresca — rompendo altri
test che nel frattempo avevano importato le classi/singleton
ORIGINALI a livello di modulo (bug reale trovato e corretto qui
stesso, PRIMA di arrivare a questa versione: causava un fallimento
imprevedibile e apparentemente scorrelato in
`test_owner_blacklist_commands.py`, visibile solo eseguendo i due
file insieme, mai in isolamento). La soluzione corretta: importare
ogni modulo con `importlib.import_module` (che riusa la cache di
sys.modules se già importato, non esegue nulla due volte) e chiamare
`modulo.setup(bot)` direttamente — stesso effetto reale
(registrazione dei comandi sul bot), zero effetti collaterali sugli
altri test.
"""

import importlib

import discord
import pytest
from discord.ext import commands

from core.cog_manager import discover_cog_modules
from core.database import db


@pytest.mark.asyncio
async def test_tutti_i_cog_si_caricano_insieme_senza_collisioni_di_nome():
    """
    Contro PostgreSQL reale: alcuni setup() eseguono query subito
    (es. per registrare un modulo premium o leggere configurazione)
    contro il singleton globale `core.database.db` — lo stesso
    usato da `scripts/generate_command_list.py`, quindi va connesso
    qui esattamente allo stesso modo, non un'istanza `Database()`
    separata che quei moduli non vedrebbero.
    """
    già_connesso = db._pool is not None
    if not già_connesso:
        await db.connect()
    try:
        await db.run_migrations()

        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

        moduli = discover_cog_modules()
        falliti: list[tuple[str, str]] = []

        for modulo_path in sorted(moduli):
            try:
                modulo = importlib.import_module(modulo_path)
                await modulo.setup(bot)
            except Exception as exc:  # stesso comportamento di load_all_cogs
                falliti.append((modulo_path, f"{type(exc).__name__}: {exc}"))

        assert falliti == [], (
            "Uno o più cog non si sono caricati insieme agli altri "
            "(quasi sempre un nome di comando/gruppo duplicato tra "
            "due cog diversi — un doppione fa fallire l'intera "
            f"registrazione del cog che lo dichiara, in silenzio): {falliti}"
        )

        # Sanity aggiuntiva: l'albero comandi risultante non deve
        # avere doppioni di nome tra i comandi TOP-LEVEL (Discord
        # stesso lo impedirebbe, ma verifichiamo esplicitamente per
        # avere un messaggio di errore leggibile invece che
        # un'eccezione generica di discord.py).
        nomi = [c.name for c in bot.tree.get_commands()]
        duplicati = {nome for nome in nomi if nomi.count(nome) > 1}
        assert duplicati == set(), f"Nomi di comando duplicati nell'albero: {duplicati}"
    finally:
        if not già_connesso:
            await db.close()
