"""
cogs/automod/automod.py
==========================
Ponte tra la configurazione salvata (core/repositories/automod_repo.py)
e le regole AutoMod native di Discord (core/automod_sync.py per la
logica di decisione). Modulo SEMPRE GRATUITO (MODULE_AUTOMOD), come
da schema — "Filtri base" è [Free]; eventuali filtri avanzati lato
bot (zalgo, caps...) sarebbero un modulo separato futuro, non questo.

Ogni comando che cambia la configurazione richiama subito
`_sync_guild()`: l'esperienza voluta è "plug and play" — l'admin
aggiunge una parola e la regola Discord viene aggiornata all'istante,
senza un comando /automod sync separato da ricordarsi di lanciare.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from core.automod_sync import DesiredRule, ExistingRule, SyncActionType, compute_sync_plan
from core.repositories.automod_repo import automod_repo
from core.premium import PremiumModule, registry
from cogs.moderation._shared import ensure_module_enabled

logger = logging.getLogger("iyokai.automod")

MODULE_AUTOMOD = "automod"

# Nomi delle regole che iYokai gestisce, sempre con il prefisso
# convenzionale (vedi core/automod_sync.py) così non vengono mai
# confuse con regole create a mano dall'admin.
RULE_NAME_BADWORDS = "iYokai — Parole Vietate"
RULE_NAME_INVITES = "iYokai — Anti-Invite"

# Pattern regex per riconoscere inviti Discord in ogni loro forma
# comune. Discord AutoMod applica i regex ai messaggi in arrivo.
INVITE_REGEX_PATTERNS = (
    r"discord\.gg/\S+",
    r"discord\.com/invite/\S+",
    r"discordapp\.com/invite/\S+",
)


def _build_desired_rules(
    custom_badwords: tuple[str, ...],
    block_invites: bool,
    last_synced_badwords: tuple[str, ...],
    last_synced_invite_regex: tuple[str, ...],
) -> list[DesiredRule]:
    """
    Costruisce le regole desiderate SEMPRE, anche quando il
    contenuto è vuoto (es. l'admin ha rimosso l'ultima parola): il
    merge a tre vie in core/automod_sync.py deve comunque poter
    valutare se restano parole "dell'admin" da preservare o se la
    regola va eliminata — vedi compute_sync_plan().
    """
    return [
        DesiredRule(
            name=RULE_NAME_BADWORDS,
            keywords=custom_badwords,
            previously_synced_keywords=last_synced_badwords,
        ),
        DesiredRule(
            name=RULE_NAME_INVITES,
            regex_patterns=INVITE_REGEX_PATTERNS if block_invites else (),
            previously_synced_regex=last_synced_invite_regex,
        ),
    ]


async def _sync_guild(guild: discord.Guild) -> str | None:
    """
    Esegue davvero la sincronizzazione: legge le regole esistenti da
    Discord, calcola il piano (logica pura, testata separatamente in
    tests/test_automod_sync.py), ed esegue create/edit/delete per le
    azioni che lo richiedono. Dopo ogni azione riuscita, aggiorna
    anche `automod_last_synced` — è quello che permette al PROSSIMO
    sync di distinguere correttamente "parole nostre" da "parole
    dell'admin" (vedi core/automod_sync.py per il perché serve).

    Restituisce un messaggio di avviso se qualcosa è stato troncato
    per un limite di Discord, altrimenti None.
    """
    try:
        rules = await guild.fetch_automod_rules()
    except discord.Forbidden:
        return (
            "Non ho i permessi per leggere/gestire le regole AutoMod "
            "di questo server (serve Manage Server)."
        )

    existing = [
        ExistingRule(
            name=rule.name,
            keywords=tuple(rule.trigger.keyword_filter or ()),
            regex_patterns=tuple(rule.trigger.regex_patterns or ()),
        )
        for rule in rules
    ]
    # Indicizzato per nome, serve per recuperare l'oggetto AutoModRule
    # vero su cui chiamare .edit()/.delete() quando il piano lo richiede.
    rules_by_name = {rule.name: rule for rule in rules}

    config = await automod_repo.get_config(guild.id)
    last_synced_badwords, _ = await automod_repo.get_last_synced(guild.id, RULE_NAME_BADWORDS)
    _, last_synced_invite_regex = await automod_repo.get_last_synced(guild.id, RULE_NAME_INVITES)

    desired = _build_desired_rules(
        config.custom_badwords,
        config.block_invites,
        last_synced_badwords,
        last_synced_invite_regex,
    )

    plan = compute_sync_plan(existing, desired)

    truncated_any = False
    for action in plan:
        truncated_any = truncated_any or action.truncated

        if action.action == SyncActionType.SKIP:
            continue

        if action.action == SyncActionType.DELETE:
            existing_rule = rules_by_name.get(action.name)
            if existing_rule is not None:
                await existing_rule.delete(reason="Nessun contenuto residuo da mantenere")
            await automod_repo.clear_last_synced(guild.id, action.name)
            continue

        actions_payload = [
            discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
        ]

        if action.name == RULE_NAME_BADWORDS:
            trigger = discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                keyword_filter=list(action.final_keywords),
            )
        else:
            trigger = discord.AutoModTrigger(
                type=discord.AutoModRuleTriggerType.keyword,
                regex_patterns=list(action.final_regex),
            )

        if action.action == SyncActionType.CREATE:
            await guild.create_automod_rule(
                name=action.name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions_payload,
                enabled=True,
                reason="Sincronizzazione automatica iYokai AutoMod",
            )
        elif action.action == SyncActionType.UPDATE:
            existing_rule = rules_by_name[action.name]
            await existing_rule.edit(
                trigger=trigger,
                reason="Sincronizzazione automatica iYokai AutoMod",
            )

        # Registra cosa abbiamo scritto DAVVERO, solo dopo che la
        # chiamata a Discord è andata a buon fine — se fosse fallita,
        # l'eccezione avrebbe già interrotto il ciclo prima di questa
        # riga, e last_synced resterebbe correttamente quello vecchio.
        await automod_repo.set_last_synced(
            guild.id, action.name, action.final_keywords, action.final_regex
        )

    if truncated_any:
        return (
            "Attenzione: una o più regole hanno superato il limite di "
            "Discord (1000 parole o 10 pattern regex per regola) e "
            "sono state troncate. Le voci in eccesso non sono state "
            "applicate."
        )
    return None


class AutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    automod_group = app_commands.Group(
        name="automod", description="Configura il filtro automatico dei messaggi."
    )

    @automod_group.command(name="badword-add", description="Aggiunge una parola vietata.")
    @app_commands.describe(word="La parola da vietare")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def badword_add(self, interaction: discord.Interaction, word: str) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        await automod_repo.add_badword(interaction.guild.id, word)
        avviso = await _sync_guild(interaction.guild)

        messaggio = f"Parola `{word}` aggiunta alla lista vietata."
        if avviso:
            messaggio += f"\n⚠️ {avviso}"
        await interaction.followup.send(messaggio, ephemeral=True)

    @automod_group.command(name="badword-remove", description="Rimuove una parola vietata.")
    @app_commands.describe(word="La parola da rimuovere")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def badword_remove(self, interaction: discord.Interaction, word: str) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        await automod_repo.remove_badword(interaction.guild.id, word)
        avviso = await _sync_guild(interaction.guild)

        messaggio = (
            f"Parola `{word}` rimossa: la regola AutoMod su Discord è "
            f"stata aggiornata subito. Eventuali parole aggiunte a mano "
            f"dallo staff direttamente dal pannello Discord non vengono "
            f"toccate."
        )
        if avviso:
            messaggio += f"\n⚠️ {avviso}"
        await interaction.followup.send(messaggio, ephemeral=True)

    @automod_group.command(name="badword-list", description="Mostra le parole vietate configurate.")
    async def badword_list(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        config = await automod_repo.get_config(interaction.guild.id)
        if not config.custom_badwords:
            await interaction.response.send_message(
                "Nessuna parola vietata configurata.", ephemeral=True
            )
            return

        lista = ", ".join(f"`{w}`" for w in config.custom_badwords)
        await interaction.response.send_message(
            f"Parole vietate configurate ({len(config.custom_badwords)}): {lista}",
            ephemeral=True,
        )

    @automod_group.command(
        name="invites", description="Attiva o disattiva il blocco automatico degli inviti Discord."
    )
    @app_commands.describe(enabled="True per bloccare gli inviti, False per consentirli")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def invites(self, interaction: discord.Interaction, enabled: bool) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        await automod_repo.set_block_invites(interaction.guild.id, enabled)
        avviso = await _sync_guild(interaction.guild)

        stato = "attivato" if enabled else "disattivato"
        messaggio = f"Blocco automatico degli inviti Discord {stato}."
        if avviso:
            messaggio += f"\n⚠️ {avviso}"
        await interaction.followup.send(messaggio, ephemeral=True)

    @automod_group.command(
        name="sync", description="Forza una sincronizzazione manuale delle regole AutoMod."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sync(self, interaction: discord.Interaction) -> None:
        if not await ensure_module_enabled(interaction, MODULE_AUTOMOD):
            return

        await interaction.response.defer(ephemeral=True)
        avviso = await _sync_guild(interaction.guild)
        await interaction.followup.send(avviso or "Sincronizzazione completata.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_AUTOMOD,
            display_name="AutoMod",
            description="Filtri base: parole vietate e blocco inviti, sincronizzati con l'AutoMod nativo di Discord.",
            premium_capable=False,
        )
    )
    await bot.add_cog(AutomodCog(bot))
