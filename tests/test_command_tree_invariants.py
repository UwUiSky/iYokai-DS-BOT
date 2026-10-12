"""
tests/test_command_tree_invariants.py
=========================================
Verifica sui limiti REALI dell'API Discord applicati all'albero
comandi del bot vero (costruito con tests/support/full_tree.py, non
un albero finto): ogni gruppo entro 25 sotto-comandi, al massimo 1
livello di sotto-gruppi, e i componenti Select costruiti con dati
reali entro 25 opzioni.
Funzioni coperte: RT-2 di PIANO_FIX.md.
"""

from __future__ import annotations

import discord
from discord import app_commands

from tests.support.full_tree import build_full_bot, close_full_bot, connect_db_if_needed

MAX_SUBCOMMANDS_PER_GROUP = 25
MAX_SUBGROUP_DEPTH = 1

# Cricchetto: nomi di Select che OGGI superano il limite di 25 opzioni
# con dati reali. Il test fallisce se compare un nome nuovo qui sopra
# o se uno di questi viene sistemato ma non tolto dall'insieme.
# BUG-2 risolto: /setup ora ha un Select per categoria, il cricchetto è vuoto.
KNOWN_OVERSIZED_SELECTS: set[str] = set()


def _sottogruppi_e_comandi(gruppo: app_commands.Group) -> tuple[list, list]:
    sottogruppi = [c for c in gruppo.commands if isinstance(c, app_commands.Group)]
    comandi = [c for c in gruppo.commands if not isinstance(c, app_commands.Group)]
    return sottogruppi, comandi


async def test_ogni_gruppo_ha_al_massimo_25_sottocomandi_e_1_livello():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, f"Cog falliti nel caricamento: {falliti}"

        gruppi_top_level = [
            c for c in _radici(bot) if isinstance(c, app_commands.Group)
        ]
        assert gruppi_top_level, "Nessun gruppo top-level trovato: l'albero è vuoto?"

        for gruppo in gruppi_top_level:
            sottogruppi, comandi_diretti = _sottogruppi_e_comandi(gruppo)

            assert len(gruppo.commands) <= MAX_SUBCOMMANDS_PER_GROUP, (
                f"Il gruppo '{gruppo.name}' ha {len(gruppo.commands)} elementi "
                f"diretti (comandi + sotto-gruppi): il limite Discord per "
                f"gruppo è {MAX_SUBCOMMANDS_PER_GROUP}."
            )

            for sottogruppo in sottogruppi:
                nipoti_sottogruppi, _ = _sottogruppi_e_comandi(sottogruppo)
                assert not nipoti_sottogruppi, (
                    f"'{gruppo.name} {sottogruppo.name}' ha un ulteriore "
                    f"livello di sotto-gruppi: Discord permette al massimo "
                    f"{MAX_SUBGROUP_DEPTH} livello di annidamento sotto un "
                    f"gruppo top-level."
                )
                assert len(sottogruppo.commands) <= MAX_SUBCOMMANDS_PER_GROUP, (
                    f"'{gruppo.name} {sottogruppo.name}' ha "
                    f"{len(sottogruppo.commands)} sotto-comandi: il limite "
                    f"Discord è {MAX_SUBCOMMANDS_PER_GROUP}."
                )
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()


async def test_select_moduli_setup_per_categoria_entra_nel_limite_di_25():
    """
    BUG-2 risolto: costruisce il vero ModuleSelect per ogni categoria con
    i moduli REALMENTE registrati. Se una categoria supera 25 opzioni il
    test fallisce (servirebbe la paginazione).
    """
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    try:
        assert not falliti, f"Cog falliti nel caricamento: {falliti}"

        from core.premium import CATEGORIE_MODULI, registry
        from cogs.utility.setup import ModuleSelect, MAX_SELECT_OPTIONS

        for categoria in CATEGORIE_MODULI:
            moduli = registry.modules_in_category(categoria)
            select = ModuleSelect([(m, False) for m in moduli])
            assert len(select.options) <= MAX_SELECT_OPTIONS, (
                f"Categoria '{categoria}': {len(select.options)} opzioni, "
                f"oltre il limite di {MAX_SELECT_OPTIONS}."
            )
        assert not KNOWN_OVERSIZED_SELECTS
    finally:
        await close_full_bot(bot)
        if creato_qui:
            from core.database import db as db_singleton

            await db_singleton.close()


# ----------------------------------------------------------------------
# Mappa F7 §3 punto 6: limiti per comando di primo livello (D24)
# ----------------------------------------------------------------------
import re

MAX_CARATTERI_COMANDO = 8000
SOGLIA_ALLARME_CARATTERI = 6800
MAX_COMANDI_PRIMO_LIVELLO = 100
MAX_NOME = 32
MAX_DESCRIZIONE = 100
REGEX_NOME = re.compile(r"^[-_ʼ\w]{1,32}$")  # \w include lettere e cifre unicode


def _len(valore) -> int:
    """Lunghezza del testo; i locale_str contano come la loro stringa base."""
    return len(str(valore))


def conta_caratteri(nodo) -> int:
    """
    Regola ufficiale di Discord: nome, descrizione, nomi e descrizioni
    delle opzioni, valori e nomi delle scelte, sotto-gruppi e
    sotto-comandi (ricorsivo).
    """
    totale = _len(nodo.name) + _len(nodo.description)
    if isinstance(nodo, app_commands.Group):
        return totale + sum(conta_caratteri(c) for c in nodo.commands)
    for param in nodo.parameters:
        totale += _len(param.name) + _len(param.description)
        for scelta in param.choices:
            totale += _len(scelta.name) + len(str(scelta.value))
    return totale


def _radici(bot):
    """Comandi globali più `/owner`, che vive solo nel server dell'owner (gruppo condiviso)."""
    from core.command_groups import GRUPPI

    radici = list(bot.tree.get_commands())
    assert bot.tree.get_command("owner") is None, "/owner non deve stare nell'albero globale"
    if GRUPPI["owner"].commands:
        radici.append(GRUPPI["owner"])
    return radici


def _tutti_i_nodi(radici):
    for nodo in radici:
        yield nodo
        if isinstance(nodo, app_commands.Group):
            yield from _tutti_i_nodi(nodo.commands)


def _percorso(nodo) -> str:
    return nodo.qualified_name


async def _albero_vero():
    creato_qui = await connect_db_if_needed()
    bot, falliti = await build_full_bot()
    assert not falliti, f"Cog falliti nel caricamento: {falliti}"
    return creato_qui, bot


async def _chiudi(creato_qui, bot):
    await close_full_bot(bot)
    if creato_qui:
        from core.database import db as db_singleton

        await db_singleton.close()


def test_conta_caratteri_segue_la_regola_ufficiale():
    @app_commands.choices(c=[app_commands.Choice(name="uno", value="1")])
    @app_commands.describe(c="desc")
    async def cb(interaction: discord.Interaction, c: str):  # pragma: no cover
        pass

    cmd = app_commands.Command(name="abc", description="de", callback=cb)
    # abc + de + (c + desc) + (uno + 1)
    assert conta_caratteri(cmd) == 3 + 2 + 1 + 4 + 3 + 1
    gruppo = app_commands.Group(name="g", description="gg")
    gruppo.add_command(cmd)
    assert conta_caratteri(gruppo) == 1 + 2 + conta_caratteri(cmd)


async def test_caratteri_per_comando_di_primo_livello_sotto_8000():
    creato_qui, bot = await _albero_vero()
    try:
        for cmd in _radici(bot):
            n = conta_caratteri(cmd)
            assert n <= MAX_CARATTERI_COMANDO, (
                f"'/{cmd.name}' pesa {n} caratteri: Discord rifiuta oltre "
                f"{MAX_CARATTERI_COMANDO}. Dividi il gruppo."
            )
    finally:
        await _chiudi(creato_qui, bot)


async def test_allarme_caratteri_oltre_6800():
    """Allarme al 85%: dà tempo di dividere un gruppo prima del limite."""
    creato_qui, bot = await _albero_vero()
    try:
        sopra = {
            c.name: conta_caratteri(c)
            for c in _radici(bot)
            if conta_caratteri(c) > SOGLIA_ALLARME_CARATTERI
        }
        assert not sopra, (
            f"Sopra l'allarme di {SOGLIA_ALLARME_CARATTERI} caratteri: {sopra}. "
            f"Il limite di Discord è {MAX_CARATTERI_COMANDO}."
        )
    finally:
        await _chiudi(creato_qui, bot)


async def test_nomi_unici_tra_fratelli():
    creato_qui, bot = await _albero_vero()
    try:
        def controlla(fratelli, dove):
            nomi = [c.name for c in fratelli]
            doppi = {n for n in nomi if nomi.count(n) > 1}
            assert not doppi, f"Nomi doppi in '{dove}': {sorted(doppi)}"

        controlla(_radici(bot), "primo livello")
        for nodo in _tutti_i_nodi(_radici(bot)):
            if isinstance(nodo, app_commands.Group):
                controlla(nodo.commands, _percorso(nodo))
    finally:
        await _chiudi(creato_qui, bot)


async def test_nomi_e_descrizioni_entro_i_limiti_e_regex():
    creato_qui, bot = await _albero_vero()
    try:
        for nodo in _tutti_i_nodi(_radici(bot)):
            nome = _percorso(nodo)
            assert REGEX_NOME.match(str(nodo.name)), f"Nome non valido: '{nome}'"
            assert str(nodo.name) == str(nodo.name).lower(), f"Nome non minuscolo: '{nome}'"
            assert 1 <= _len(nodo.description) <= MAX_DESCRIZIONE, (
                f"Descrizione di '{nome}': {_len(nodo.description)} caratteri "
                f"(massimo {MAX_DESCRIZIONE})."
            )
            if isinstance(nodo, app_commands.Command):
                for p in nodo.parameters:
                    assert REGEX_NOME.match(str(p.name)), f"Opzione non valida '{p.name}' in '{nome}'"
                    assert 1 <= _len(p.description) <= MAX_DESCRIZIONE, (
                        f"Descrizione dell'opzione '{p.name}' di '{nome}': "
                        f"{_len(p.description)} caratteri."
                    )
    finally:
        await _chiudi(creato_qui, bot)


async def test_dopo_il_setup_di_tutti_i_cog_owner_non_e_nell_albero_globale():
    """/owner lo aggiunge solo main.py (registra_owner) nel server dell'owner."""
    from core.command_groups import GRUPPI

    creato_qui, bot = await _albero_vero()
    try:
        assert bot.tree.get_command("owner") is None
        assert GRUPPI["owner"].commands, "i cog owner devono riempire il gruppo condiviso"
    finally:
        await _chiudi(creato_qui, bot)


SOGLIA_DESCRIZIONE = 95  # sotto il limite di 100: margine per le traduzioni (F8)


async def test_nessuna_descrizione_oltre_95_caratteri():
    creato_qui, bot = await _albero_vero()
    try:
        lunghe = []
        for nodo in _tutti_i_nodi(_radici(bot)):
            if _len(nodo.description) > SOGLIA_DESCRIZIONE:
                lunghe.append(f"{_percorso(nodo)}: {_len(nodo.description)}")
            if isinstance(nodo, app_commands.Command):
                for p in nodo.parameters:
                    if _len(p.description) > SOGLIA_DESCRIZIONE:
                        lunghe.append(f"{_percorso(nodo)} [{p.name}]: {_len(p.description)}")
        assert not lunghe, f"Descrizioni oltre {SOGLIA_DESCRIZIONE} caratteri (limite 100): {lunghe}"
    finally:
        await _chiudi(creato_qui, bot)


async def test_default_permissions_solo_al_primo_livello():
    creato_qui, bot = await _albero_vero()
    try:
        radici = _radici(bot)
        for radice in radici:
            if not isinstance(radice, app_commands.Group):
                continue
            for nodo in _tutti_i_nodi(radice.commands):
                assert nodo.default_permissions is None, (
                    f"'{_percorso(nodo)}' ha default_permissions: Discord li "
                    f"accetta solo sul comando di primo livello (LIM-57)."
                )
    finally:
        await _chiudi(creato_qui, bot)


async def test_primo_livello_entro_100_comandi():
    creato_qui, bot = await _albero_vero()
    try:
        n = len(bot.tree.get_commands())
        assert n <= MAX_COMANDI_PRIMO_LIVELLO, f"{n} comandi di primo livello (massimo 100)."
    finally:
        await _chiudi(creato_qui, bot)


# ----------------------------------------------------------------------
# M 14.1 (LIM-1): ogni opzione di testo libero ha un massimo (max_length).
# Cricchetto: contiene le opzioni che OGGI non lo hanno. Il test fallisce se
# ne compare una nuova o se una viene sistemata e non tolta da qui.
# ----------------------------------------------------------------------
KNOWN_SENZA_MAX_LENGTH: frozenset[str] = frozenset(
    {
    "admin backup restore-utenti:server_di_origine",
    "admin messaggi programma:duration",
    "fun 8ball:domanda",
    "fun meme:bottom_text",
    "fun meme:top_text",
    "fun rate:thing",
    "fun search-image:query",
    "mod timeout:duration",
    "modban tempban:duration",
    "modban unban:user_id",
    "moduli alert feed:feed_url",
    "moduli alert feed:label",
    "moduli alert feed:message_template",
    "moduli alert rimuovi:subscription_id",
    "moduli alert twitch:label",
    "moduli alert twitch:twitch_login",
    "moduli alert webhook:label",
    "moduli alert webhook:message_template",
    "moduli alert youtube-live:label",
    "moduli alert youtube-live:youtube_channel_id",
    "music play:query",
    "owner radio add-local:filename",
    "owner radio add-local:label",
    "owner radio add-track:label",
    "owner radio add-track:query",
    "utility reminder set:duration",
    }
)


async def test_ogni_opzione_di_testo_ha_un_massimo():
    from discord import AppCommandOptionType

    creato_qui, bot = await _albero_vero()
    try:
        senza_massimo = set()
        for nodo in _tutti_i_nodi(_radici(bot)):
            if isinstance(nodo, app_commands.Group):
                continue
            for p in nodo.parameters:
                # Per le stringhe discord.py tiene il massimo in `max_value`.
                if p.type is AppCommandOptionType.string and not p.choices and p.max_value is None:
                    senza_massimo.add(f"{nodo.qualified_name}:{p.name}")
        nuovi = sorted(senza_massimo - KNOWN_SENZA_MAX_LENGTH)
        sistemati = sorted(KNOWN_SENZA_MAX_LENGTH - senza_massimo)
        assert nuovi == [], f"Opzioni di testo senza massimo (usa Range[str, 1, N]): {nuovi}"
        assert sistemati == [], f"Ora hanno un massimo: toglile da KNOWN_SENZA_MAX_LENGTH: {sistemati}"
    finally:
        await _chiudi(creato_qui, bot)


async def test_i_limiti_interi_delle_opzioni_entrano_nei_53_bit_di_discord():
    """Discord rifiuta min/max interi oltre ±(2^53-1): un solo invio sbagliato blocca tutti i /owner."""
    from discord import AppCommandOptionType

    massimo = 2**53 - 1
    creato_qui, bot = await _albero_vero()
    try:
        fuori = []
        for nodo in _tutti_i_nodi(_radici(bot)):
            if isinstance(nodo, app_commands.Group):
                continue
            for p in nodo.parameters:
                if p.type not in (AppCommandOptionType.integer, AppCommandOptionType.number):
                    continue
                for nome, valore in (("min", p.min_value), ("max", p.max_value)):
                    if valore is not None and abs(valore) > massimo:
                        fuori.append(f"{nodo.qualified_name}:{p.name} {nome}={valore}")
        assert fuori == [], f"Limiti interi oltre 2**53-1: {fuori}"
    finally:
        await _chiudi(creato_qui, bot)
