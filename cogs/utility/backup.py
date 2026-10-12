"""
cogs/utility/backup.py
======================
Comandi /admin backup main, crea, collega e promuovi del Backup System (D8).
/admin backup restore-utenti è in cogs/utility/restore.py.
Funzioni coperte: SPEC §11.12, §11.13, M 12.1, M 12.9
"""

# DA FARE (issue #110, fase F13): NF-39, Modelli di server e sincronia
#   tra server. Vedi revisione/02-piano/NUOVE_FUNZIONI.md.

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.backup_link_logic import (
    ESITO_GIA_COLLEGATO,
    ESITO_GIA_USATO,
    ESITO_NON_AUTORIZZATO,
    ESITO_OK,
    ESITO_SCADUTO,
    ESITO_STESSO_SERVER,
    collega_backup,
    crea_codice_collegamento,
    link_invito,
    permessi_invito_creator,
    permessi_invito_main,
)

from core.command_groups import CogConGruppi, comando_di_gruppo
from core.repositories.backup_repo import backup_repo


class BackupCog(CogConGruppi, commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @comando_di_gruppo(
        "admin",
        nome="main",
        descrizione="Registra questo server come 'main' per il Backup System.",
        sottogruppo=("backup", "Backup e ripristino del server"),
    )
    async def define_main(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        await backup_repo.define_main(guild.id)
        await interaction.response.send_message(
            "✅ Questo server è ora registrato come 'main' per il Backup System. "
            "Usa /admin backup crea per collegare un server di backup.",
            ephemeral=True,
        )

    async def _link_modello(self, guild: discord.Guild) -> str | None:
        """Link del modello di server (riusa quello esistente). None se Discord rifiuta."""
        try:
            modelli = await guild.templates()
            if modelli:
                await modelli[0].sync()
                return modelli[0].url
            modello = await guild.create_template(
                name=guild.name[:100], description="Modello per il server di backup (iYokai)"
            )
            return modello.url
        except discord.HTTPException:
            return None

    @comando_di_gruppo(
        "admin",
        nome="crea",
        descrizione="Prepara il backup: codice di collegamento e link per il nuovo server.",
        sottogruppo=("backup", "Backup e ripristino del server"),
    )
    @app_commands.describe(modello="Crea anche un link modello di server (ruoli e canali già pronti)")
    async def define_backup(self, interaction: discord.Interaction, modello: bool = False) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Serve il permesso Amministratore.", ephemeral=True
            )
            return

        coppia = await backup_repo.get_pair(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                "Devi prima registrare questo server con /admin backup main.", ephemeral=True
            )
            return

        if await backup_repo.has_active_job(guild.id):
            await interaction.response.send_message(
                "⏳ C'è già una copia in coda o in corso per questo server: "
                "attendi che finisca prima di prepararne un'altra.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        codice, scadenza = await crea_codice_collegamento(
            backup_repo, guild.id, creato_da=interaction.user.id
        )
        creator = getattr(self.bot, "backup_creator_client", None)
        link_creator = (
            link_invito(creator.user.id, permessi_invito_creator())
            if creator is not None and creator.user is not None
            else None
        )
        link_main = link_invito(self.bot.user.id, permessi_invito_main())
        url_modello = await self._link_modello(guild) if modello else None

        passi = [
            "1. Crea un server nuovo (anche da un modello).",
            f"2. Invita **iYokai** con [questo link]({link_main})."
            + (f" Invita anche **iYokai Creator** con [questo link]({link_creator})." if link_creator else " (Il Creator non è attivo: avvisa l'owner del bot.)"),
            f"3. Nel server nuovo lancia `/admin backup collega` con il codice `{codice}`.",
        ]
        if modello:
            passi.insert(
                1,
                f"   Modello: {url_modello}" if url_modello else "   Modello non creato: Discord ha rifiutato.",
            )
        embed = discord.Embed(
            title="📦 Collegamento del backup",
            description="\n".join(passi)[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Il codice vale fino a {scadenza:%d/%m %H:%M} UTC e si usa una volta sola.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @comando_di_gruppo(
        "admin",
        nome="collega",
        descrizione="Collega QUESTO server come backup, con il codice ricevuto dal server principale.",
        sottogruppo=("backup", "Backup e ripristino del server"),
    )
    @app_commands.describe(codice="Codice dato da /admin backup crea nel server principale")
    async def collega(
        self, interaction: discord.Interaction, codice: app_commands.Range[str, 4, 24]
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Serve il permesso Amministratore.", ephemeral=True
            )
            return

        creator = getattr(self.bot, "backup_creator_client", None)
        if creator is None or creator.get_guild(guild.id) is None:
            await interaction.response.send_message(
                "⚠️ **iYokai Creator** non è in questo server: invitalo (il link è in "
                "`/admin backup crea`) e rilancia il comando.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        async def e_admin_del_main(main_guild_id: int) -> bool:
            main = self.bot.get_guild(main_guild_id)
            membro = main.get_member(interaction.user.id) if main is not None else None
            return membro is not None and (
                membro.guild_permissions.administrator or main.owner_id == membro.id
            )

        esito = await collega_backup(
            backup_repo, codice, guild.id,
            utente_id=interaction.user.id, puo_collegare=e_admin_del_main,
        )
        if esito.esito == ESITO_OK:
            await interaction.followup.send(
                f"✅ Server collegato come backup (job `#{esito.job_id}`). Il Creator copia "
                "struttura e messaggi: riceverai un DM quando ha finito, poi lo tiene aggiornato.",
                ephemeral=True,
            )
            return
        messaggi = {
            ESITO_SCADUTO: "⌛ Il codice è scaduto: creane uno nuovo con /admin backup crea.",
            ESITO_GIA_USATO: "⚠️ Il codice è già stato usato: creane uno nuovo con /admin backup crea.",
            ESITO_GIA_COLLEGATO: (
                "⚠️ Collegamento non possibile: o questo server fa già parte di un'altra coppia, "
                "o il server principale ha già un backup o una copia in corso."
            ),
            ESITO_NON_AUTORIZZATO: (
                "⛔ Il codice lo può usare solo chi lo ha creato, e deve essere ancora "
                "amministratore del server principale."
            ),
            ESITO_STESSO_SERVER: "⚠️ Il server principale non può essere il proprio backup.",
        }
        await interaction.followup.send(
            messaggi.get(esito.esito, "❌ Codice non valido."), ephemeral=True
        )

    @comando_di_gruppo(
        "admin",
        nome="promuovi",
        descrizione="Promuove QUESTO server (finora backup) a nuovo main, se il main originale è perso.",
        sottogruppo=("backup", "Backup e ripristino del server"),
    )
    async def promuovi_backup(self, interaction: discord.Interaction) -> None:
        """
        SPEC.md §11.13 — il backup promosso diventa main senza backup:
        un admin ne crea uno nuovo con /admin backup crea (un bot non può
        creare server, D8). La coppia storica resta per /admin backup restore-utenti.

        Va lanciato DENTRO al server che finora era il backup — non
        serve altro ID: lo troviamo risalendo da backup_guild_id a
        chi era il suo main tramite get_pair_by_backup_guild_id.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Questo comando è disponibile solo dentro un server.", ephemeral=True
            )
            return

        coppia = await backup_repo.get_pair_by_backup_guild_id(guild.id)
        if coppia is None:
            await interaction.response.send_message(
                "⚠️ Questo server non risulta registrato come backup di nessun main — "
                "non c'è nulla da promuovere.",
                ephemeral=True,
            )
            return

        await backup_repo.promote_backup_to_main(
            old_main_guild_id=coppia.main_guild_id, new_main_guild_id=guild.id
        )

        await interaction.response.send_message(
            "👑 Questo server è stato promosso a **main**. Il vecchio main "
            f"(`{coppia.main_guild_id}`) non è più abbinato a questo backup. "
            "Per avere un nuovo backup: crea un server nuovo e lancia qui `/admin backup crea`.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupCog(bot))
