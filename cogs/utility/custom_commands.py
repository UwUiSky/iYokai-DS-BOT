"""
cogs/utility/custom_commands.py
===============================
Comandi personalizzati del server, detti tag (NF-09, SPEC §22.5): un nome,
un testo o un embed, un ruolo da dare o togliere, una pausa. Si usano con
`/utility tag` e, se l'admin sceglie un prefisso, anche scrivendo
`<prefisso>nome` (usa guild_config.prefix, M 10.15). Si gestiscono con
`/moduli comandi crea|modifica|elimina|elenco|prefisso`.
Funzioni coperte: SPEC §22 (NF-09)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.admin_mentions_logic import menzioni_ammesse, utente_puo_pingare_ruoli
from core.bounded_cache import BoundedCache
from core.command_access import Livello, autocomplete_protetto
from core.command_groups import CogConGruppi, comando_di_gruppo
from core.custom_command_logic import (
    MAX_ARGOMENTI,
    MAX_NOME,
    MAX_PAUSA,
    MAX_TAG,
    MAX_TESTO,
    azione_ruolo,
    costruisci_risposta,
    nome_da_messaggio,
    normalizza_nome,
    pausa_residua,
    valida_prefisso,
)
from core.database import db
from core.lista_limiti_logic import righe_entro_limite
from core.premium import PremiumModule, registry
from core.repositories.custom_command_repo import custom_command_repo
from core.role_safety import check_role_assignable, motivo_ruolo_automatico_non_assegnabile

logger = logging.getLogger("iyokai.custom_commands")

MODULE_CUSTOM_COMMANDS = "custom_commands"

_SG_COMANDI = ("comandi", "Comandi personalizzati e risposte automatiche")
_TTL_PREFISSO = 60  # secondi: il prefisso si rilegge ogni minuto, non a ogni messaggio

# (server, nome, utente) -> ultimo uso; (server) -> (prefisso, scadenza)
_ultimo_uso: BoundedCache[tuple[int, str, int], datetime] = BoundedCache(max_size=20_000)
_cache_prefissi: BoundedCache[int, tuple[str | None, float]] = BoundedCache(max_size=5_000)

_SCELTE_AZIONE = [
    app_commands.Choice(name="nessuna", value="nessuna"),
    app_commands.Choice(name="dai il ruolo", value="dai"),
    app_commands.Choice(name="togli il ruolo", value="togli"),
    app_commands.Choice(name="alterna", value="alterna"),
]


class CustomCommandsCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ================================================================
    # Uso
    # ================================================================
    async def _prefisso(self, guild_id: int) -> str | None:
        voce = _cache_prefissi.get(guild_id)
        ora = time.monotonic()
        if voce is not None and voce[1] > ora:
            return voce[0]
        prefisso = await custom_command_repo.get_prefix(guild_id)
        _cache_prefissi.set(guild_id, (prefisso, ora + _TTL_PREFISSO))
        return prefisso

    async def _prepara(self, tag, membro: discord.Member, canale, argomenti: str):
        """(testo, nota sul ruolo): applica il ruolo del tag e costruisce la risposta."""
        nota = await self._applica_ruolo(tag, membro)
        valori = {
            "user": membro.mention,
            "username": membro.display_name,
            "server": membro.guild.name,
            "channel": getattr(canale, "mention", ""),
            "args": argomenti,
        }
        return costruisci_risposta(tag.response, valori), nota

    async def _applica_ruolo(self, tag, membro: discord.Member) -> str | None:
        if tag.role_id is None or tag.role_action == "nessuna":
            return None
        motivo = motivo_ruolo_automatico_non_assegnabile(membro.guild, tag.role_id)
        if motivo is not None:
            logger.warning("Tag %s: ruolo %s non assegnabile: %s", tag.name, tag.role_id, motivo)
            return "Il ruolo di questo comando non può essere assegnato: avvisa lo staff."
        ruolo = membro.guild.get_role(tag.role_id)
        mossa = azione_ruolo(tag.role_action, ruolo in membro.roles)
        try:
            if mossa == "dai":
                await membro.add_roles(ruolo, reason=f"Comando personalizzato {tag.name}")
            elif mossa == "togli":
                await membro.remove_roles(ruolo, reason=f"Comando personalizzato {tag.name}")
        except discord.HTTPException:
            return "Non sono riuscito a cambiare il ruolo."
        return None

    @staticmethod
    def _pausa(tag, guild_id: int, user_id: int) -> float:
        chiave = (guild_id, tag.name, user_id)
        ora = datetime.now(timezone.utc)
        residuo = pausa_residua(_ultimo_uso.get(chiave), ora, tag.cooldown_seconds)
        if residuo == 0 and tag.cooldown_seconds > 0:
            _ultimo_uso.set(chiave, ora)
        return residuo

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not message.content:
            return
        if not await db.is_module_active_for_guild(message.guild.id, MODULE_CUSTOM_COMMANDS):
            return
        prefisso = await self._prefisso(message.guild.id)
        trovato = nome_da_messaggio(message.content, prefisso)
        if trovato is None:
            return
        nome, argomenti = trovato
        tag = await custom_command_repo.get_tag(message.guild.id, nome)
        if tag is None:
            return
        if self._pausa(tag, message.guild.id, message.author.id) > 0:
            return  # col prefisso si tace: niente messaggi di servizio nel canale
        testo, nota = await self._prepara(tag, message.author, message.channel, argomenti[:MAX_ARGOMENTI])
        menzioni = menzioni_ammesse(tag.ping_ruoli)
        try:
            if tag.use_embed:
                await message.channel.send(embed=discord.Embed(description=testo), allowed_mentions=menzioni)
            else:
                await message.channel.send(testo, allowed_mentions=menzioni)
        except discord.HTTPException:
            logger.warning("Tag %s: invio fallito nel canale %s", nome, message.channel.id)
            return
        await custom_command_repo.add_use(message.guild.id, nome)

    async def _nomi_per_completamento(self, interaction: discord.Interaction, current: str):
        if interaction.guild is None:
            return []
        nomi = await custom_command_repo.search_names(interaction.guild.id, current.lower(), 25)
        return [app_commands.Choice(name=n, value=n) for n in nomi]

    async def _completa_uso(self, interaction: discord.Interaction, current: str):
        return await self._nomi_per_completamento(interaction, current)

    @autocomplete_protetto(Livello.ADMIN)
    async def _completa_admin(self, interaction: discord.Interaction, current: str):
        return await self._nomi_per_completamento(interaction, current)

    @comando_di_gruppo(
        "utility",
        nome="tag",
        descrizione="Usa un comando personalizzato di questo server.",
    )
    @app_commands.describe(nome="Il comando da usare", argomenti="Testo da passare al comando (facoltativo)")
    @app_commands.autocomplete(nome=_completa_uso)
    async def tag(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        argomenti: app_commands.Range[str, 0, MAX_ARGOMENTI] = "",
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if not await db.is_module_active_for_guild(guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server.", ephemeral=True
            )
            return
        normalizzato = normalizza_nome(nome)
        tag = await custom_command_repo.get_tag(guild.id, normalizzato) if normalizzato else None
        if tag is None:
            await interaction.response.send_message(
                "Questo server non ha un comando con quel nome.", ephemeral=True
            )
            return
        residuo = self._pausa(tag, guild.id, interaction.user.id)
        if residuo > 0:
            await interaction.response.send_message(
                f"Aspetta ancora {int(residuo) + 1} secondi prima di riusarlo.", ephemeral=True
            )
            return
        # Dare o togliere il ruolo sono chiamate a Discord che possono superare i 3 secondi
        # concessi per rispondere: si prenota la risposta prima.
        await interaction.response.defer()
        testo, nota = await self._prepara(tag, interaction.user, interaction.channel, argomenti)
        menzioni = menzioni_ammesse(tag.ping_ruoli)
        if tag.use_embed:
            await interaction.followup.send(embed=discord.Embed(description=testo), allowed_mentions=menzioni)
        else:
            await interaction.followup.send(testo, allowed_mentions=menzioni)
        if nota:
            await interaction.followup.send(nota, ephemeral=True)
        await custom_command_repo.add_use(guild.id, tag.name)

    # ================================================================
    # Gestione (admin)
    # ================================================================
    async def _pronto(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return False
        if not await db.is_module_active_for_guild(interaction.guild.id, MODULE_CUSTOM_COMMANDS):
            await interaction.response.send_message(
                "Questo modulo non è attivo su questo server. "
                "Un amministratore può attivarlo con /admin setup attiva.",
                ephemeral=True,
            )
            return False
        return True

    @staticmethod
    async def _controlla_ruolo(interaction, ruolo, azione) -> bool:
        if (ruolo is None) != (azione == "nessuna"):
            await interaction.response.send_message(
                "Ruolo e azione vanno insieme: scegli un ruolo e un'azione, oppure nessuno dei due.",
                ephemeral=True,
            )
            return False
        if ruolo is not None:
            motivo = check_role_assignable(interaction.guild, ruolo, interaction.user, self_service=True)
            if motivo is not None:
                await interaction.response.send_message(motivo, ephemeral=True)
                return False
        return True

    @comando_di_gruppo("moduli", nome="crea", descrizione="Crea un comando personalizzato.", sottogruppo=_SG_COMANDI)
    @app_commands.describe(
        nome=f"Il nome (lettere minuscole, cifre, - e _; massimo {MAX_NOME})",
        testo="La risposta. Segnaposto: {user} {username} {server} {channel} {args}",
        come_embed="Mandare la risposta come embed?",
        ruolo="Ruolo da dare o togliere a chi lo usa",
        azione="Cosa fare col ruolo",
        pausa_secondi="Pausa tra un uso e l'altro, per ogni utente",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE)
    async def crea(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        testo: app_commands.Range[str, 1, MAX_TESTO],
        come_embed: bool = False,
        ruolo: discord.Role | None = None,
        azione: str = "nessuna",
        pausa_secondi: app_commands.Range[int, 0, MAX_PAUSA] = 0,
    ) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        if normalizzato is None:
            await interaction.response.send_message(
                "Il nome può avere solo lettere minuscole (a-z), cifre, - e _, senza spazi.", ephemeral=True
            )
            return
        if not await self._controlla_ruolo(interaction, ruolo, azione):
            return
        esito = await custom_command_repo.create_tag(
            interaction.guild.id,
            normalizzato,
            response=testo,
            use_embed=come_embed,
            role_id=ruolo.id if ruolo else None,
            role_action=azione,
            cooldown_seconds=pausa_secondi,
            ping_ruoli=utente_puo_pingare_ruoli(interaction.user),
            created_by=interaction.user.id,
        )
        messaggi = {
            "ok": f"Comando `{normalizzato}` creato. Si usa con `/utility tag`.",
            "esiste": f"Esiste già un comando `{normalizzato}`: usa `/moduli comandi modifica`.",
            "pieno": f"Questo server ha già {MAX_TAG} comandi personalizzati: eliminane uno.",
        }
        await interaction.response.send_message(messaggi[esito], ephemeral=True)

    @comando_di_gruppo("moduli", nome="modifica", descrizione="Cambia un comando personalizzato.", sottogruppo=_SG_COMANDI)
    @app_commands.describe(
        nome="Il comando da cambiare",
        testo="Nuova risposta",
        come_embed="Mandare la risposta come embed?",
        ruolo="Nuovo ruolo (serve anche l'azione)",
        azione="Cosa fare col ruolo (\"nessuna\" toglie il ruolo dal comando)",
        pausa_secondi="Nuova pausa tra un uso e l'altro",
    )
    @app_commands.choices(azione=_SCELTE_AZIONE)
    @app_commands.autocomplete(nome=_completa_admin)
    async def modifica(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, MAX_NOME],
        testo: app_commands.Range[str, 1, MAX_TESTO] | None = None,
        come_embed: bool | None = None,
        ruolo: discord.Role | None = None,
        azione: str | None = None,
        pausa_secondi: app_commands.Range[int, 0, MAX_PAUSA] | None = None,
    ) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        campi: dict = {}
        if testo is not None:
            campi["response"] = testo
            campi["ping_ruoli"] = utente_puo_pingare_ruoli(interaction.user)
        if come_embed is not None:
            campi["use_embed"] = come_embed
        if pausa_secondi is not None:
            campi["cooldown_seconds"] = pausa_secondi
        if azione is not None:
            if not await self._controlla_ruolo(interaction, ruolo, azione):
                return
            campi["role_id"] = ruolo.id if ruolo else None
            campi["role_action"] = azione
        elif ruolo is not None:
            await interaction.response.send_message("Se scegli un ruolo, scegli anche l'azione.", ephemeral=True)
            return
        if not campi or normalizzato is None:
            await interaction.response.send_message("Non hai indicato nulla da cambiare.", ephemeral=True)
            return
        fatto = await custom_command_repo.update_tag(interaction.guild.id, normalizzato, **campi)
        await interaction.response.send_message(
            "Comando aggiornato." if fatto else "Non esiste un comando con quel nome.", ephemeral=True
        )

    @comando_di_gruppo("moduli", nome="elimina", descrizione="Elimina un comando personalizzato.", sottogruppo=_SG_COMANDI)
    @app_commands.describe(nome="Il comando da eliminare")
    @app_commands.autocomplete(nome=_completa_admin)
    async def elimina(self, interaction: discord.Interaction, nome: app_commands.Range[str, 1, MAX_NOME]) -> None:
        if not await self._pronto(interaction):
            return
        normalizzato = normalizza_nome(nome)
        fatto = normalizzato is not None and await custom_command_repo.delete_tag(interaction.guild.id, normalizzato)
        await interaction.response.send_message(
            "Comando eliminato." if fatto else "Non esiste un comando con quel nome.", ephemeral=True
        )

    @comando_di_gruppo("moduli", nome="elenco", descrizione="Mostra i comandi personalizzati del server.", sottogruppo=_SG_COMANDI)
    async def elenco(self, interaction: discord.Interaction) -> None:
        if not await self._pronto(interaction):
            return
        tag = await custom_command_repo.list_tags(interaction.guild.id)
        prefisso = await custom_command_repo.get_prefix(interaction.guild.id)
        righe = [f"`{t.name}` — {t.uses} usi" for t in tag] or ["Nessun comando personalizzato."]
        testo, _ = righe_entro_limite(righe, 3800)
        piede = f"\n\nPrefisso: `{prefisso}`" if prefisso else "\n\nPrefisso: nessuno (solo `/utility tag`)."
        embed = discord.Embed(title=f"Comandi personalizzati ({len(tag)}/{MAX_TAG})", description=testo + piede)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @comando_di_gruppo("moduli", nome="prefisso", descrizione="Scegli il prefisso per usare i comandi scrivendo nel canale.", sottogruppo=_SG_COMANDI)
    @app_commands.describe(simbolo="1-3 simboli, per esempio ! — lascia vuoto per spegnere il prefisso")
    async def prefisso(self, interaction: discord.Interaction, simbolo: app_commands.Range[str, 0, 3] = "") -> None:
        if not await self._pronto(interaction):
            return
        if simbolo == "":
            await custom_command_repo.set_prefix(interaction.guild.id, None)
            _cache_prefissi.set(interaction.guild.id, (None, time.monotonic() + _TTL_PREFISSO))
            await interaction.response.send_message("Prefisso spento: i comandi si usano con `/utility tag`.", ephemeral=True)
            return
        errore = valida_prefisso(simbolo)
        if errore is not None:
            await interaction.response.send_message(errore, ephemeral=True)
            return
        await custom_command_repo.set_prefix(interaction.guild.id, simbolo)
        _cache_prefissi.set(interaction.guild.id, (simbolo, time.monotonic() + _TTL_PREFISSO))
        await interaction.response.send_message(
            f"Prefisso `{simbolo}` attivo: scrivendo `{simbolo}nome` parte il comando.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    registry.register(
        PremiumModule(
            name=MODULE_CUSTOM_COMMANDS,
            display_name="Comandi personalizzati",
            category="utility",
            description="Comandi creati dal server: testo o embed, ruolo, pausa; uso con /utility tag o col prefisso.",
            premium_capable=False,
        )
    )
    await bot.add_cog(CustomCommandsCog(bot))
