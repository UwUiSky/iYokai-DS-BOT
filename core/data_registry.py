"""
core/data_registry.py
=====================
Elenco di tutte le tabelle con dati personali e di server, e di cosa farne:
cancellazione di un utente, esportazione, pulizia di un server uscito da 90
giorni, scadenza delle righe vecchie.
Funzioni coperte: SPEC §19 (NF-04, #75, #19, #37, #46, GDPR-1/2/3)

Una tabella nuova DEVE comparire qui: `tests/test_data_registry.py` legge lo
schema vero e fallisce se ne trova una non dichiarata. Così nessun cog crea una
tabella con dati personali che la cancellazione dimentica.

L'ordine dell'elenco è l'ordine di cancellazione: le tabelle figlie prima
delle madri (voci di un menu prima del menu, iscritti prima del giveaway).
Tutto il testo SQL qui dentro è scritto a mano, mai preso dall'utente.

Regole (decisioni D6 e #46):
- `utente`: che cosa succede alle righe che riguardano la persona quando chiede
  la cancellazione. "cancella" le toglie; "anonimizza" azzera i campi personali
  e tiene il resto (statistiche); "conserva" le lascia (sicurezza, #37);
  "nessuna" se la tabella non riguarda persone.
- `conserva_se`: righe che restano comunque (ban e kick: `retain_for_security`).
- `conserva_server_se`: righe che restano solo alla pulizia di un server (uno sban
  programmato: senza, il tempban diventerebbe permanente).
- `dopo_purga_server`: SQL (con $1) eseguito dopo la cancellazione del server, per
  ricostruire ciò che deve sopravvivere (il contatore dei casi).
- Esportazione: solo le righe DELL'utente (`colonne_utente`), mai quelle dove è solo
  autore di un'azione su altri; i campi di altre persone (staff) escono vuoti.
- `server`: che cosa succede alla tabella 90 giorni dopo l'uscita del bot.
- `scadenza`: righe più vecchie di N giorni, tolte dal lavoro giornaliero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# L'identità di un utente cancellato. Nessun utente vero ha id 0.
UTENTE_CANCELLATO = 0
TESTO_CANCELLATO = "[cancellato]"

# Giorni di conservazione dopo l'uscita del bot da un server (D6).
GIORNI_DOPO_USCITA = 90

# Tabelle da non dichiarare: dell'infrastruttura, senza dati personali né di server.
TABELLE_ESCLUSE = frozenset({"schema_migrations"})

_IDENTIFICATORE = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class Scadenza:
    """Righe più vecchie di `giorni`, giudicate sulla colonna (o espressione) `colonna`."""

    colonna: str
    giorni: int
    solo_se: str | None = None


@dataclass(frozen=True)
class TabellaDati:
    nome: str
    descrizione: str
    colonne_utente: tuple[str, ...] = ()
    colonne_attore: tuple[str, ...] = ()
    colonna_server: str | None = None
    filtro_server: str | None = None  # SQL con $1, se non basta una colonna
    utente: str = "nessuna"  # cancella | anonimizza | conserva | nessuna
    anonimizza: tuple[tuple[str, str], ...] = ()  # (colonna, espressione SQL)
    conserva_se: str | None = None  # righe che restano sia per l'utente sia per il server
    conserva_utente_se: str | None = None  # righe che restano solo alla cancellazione di un utente
    conserva_server_se: str | None = None  # righe che restano solo alla pulizia di un server
    dopo_purga_server: str | None = None  # SQL con $1, dopo la cancellazione del server
    filtro_esportazione: str | None = None  # SQL con $1, se non bastano le colonne dell'utente
    esporta: bool = False
    escludi_dall_esportazione: tuple[str, ...] = ()
    server: str = "cancella"  # cancella | conserva
    scadenza: Scadenza | None = None
    gestita_da: str | None = None  # chi già la pulisce, se non il lavoro giornaliero
    azzera_attore: bool | None = None  # None = sì, tranne nelle tabelle di sicurezza ("conserva")
    nota: str = ""
    # derivato
    colonne_tutte: tuple[str, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        object.__setattr__(self, "colonne_tutte", self.colonne_utente + self.colonne_attore)

    def attori_da_azzerare(self) -> tuple[str, ...]:
        """Colonne in cui l'utente compare come staff, da portare a UTENTE_CANCELLATO."""
        azzera = self.utente != "conserva" if self.azzera_attore is None else self.azzera_attore
        return self.colonne_attore if azzera else ()

    def _conserva_utente(self) -> str | None:
        parti = [p for p in (self.conserva_se, self.conserva_utente_se) if p]
        if not parti:
            return None
        return "(" + ") OR (".join(parti) + ")"

    # ---- SQL (tutto statico: nomi dal registro, valori sempre come parametro) ----
    def _dove_utente(self, colonne: tuple[str, ...]) -> str:
        return " OR ".join(f"{c} = $1" for c in colonne)

    def sql_cancella_utente(self) -> str:
        dove = f"({self._dove_utente(self.colonne_utente)})"
        if self._conserva_utente():
            dove += f" AND NOT COALESCE({self._conserva_utente()}, FALSE)"
        return f"DELETE FROM {self.nome} WHERE {dove}"

    def sql_anonimizza_utente(self) -> str:
        assegnazioni = ", ".join(f"{c} = {valore}" for c, valore in self.anonimizza)
        dove = f"({self._dove_utente(self.colonne_utente)})"
        if self._conserva_utente():
            dove += f" AND NOT COALESCE({self._conserva_utente()}, FALSE)"
        return f"UPDATE {self.nome} SET {assegnazioni} WHERE {dove}"

    def sql_azzera_attore(self, colonna: str) -> str:
        return f"UPDATE {self.nome} SET {colonna} = {UTENTE_CANCELLATO} WHERE {colonna} = $1"

    def sql_conta_conservate(self) -> str:
        if self.utente == "conserva":
            return f"SELECT count(*) FROM {self.nome} WHERE {self._dove_utente(self.colonne_utente)}"
        return (
            f"SELECT count(*) FROM {self.nome} WHERE ({self._dove_utente(self.colonne_utente)}) "
            f"AND COALESCE({self._conserva_utente()}, FALSE)"
        )

    def sql_esporta(self, limite: int, ordine: tuple[str, ...] = ()) -> str:
        """
        Solo le righe dove l'utente è il SOGGETTO. `ordine` (la chiave primaria) rende il
        taglio a `limite` ripetibile; se ne chiede una in più per accorgersi del taglio.
        """
        dove = self.filtro_esportazione or self._dove_utente(self.colonne_utente)
        if not all(_IDENTIFICATORE.match(c) for c in ordine):
            raise ValueError("Colonna d'ordine non valida.")
        ordinamento = ", ".join(ordine) if ordine else "ctid"
        return f"SELECT * FROM {self.nome} WHERE {dove} ORDER BY {ordinamento} LIMIT {int(limite)}"

    def _conserva_server(self) -> str | None:
        parti = [p for p in (self.conserva_se, self.conserva_server_se) if p]
        return "(" + ") OR (".join(parti) + ")" if parti else None

    def _filtro_server(self) -> str | None:
        if self.filtro_server:
            return self.filtro_server
        if self.colonna_server:
            return f"{self.colonna_server} = $1"
        return None

    def sql_cancella_server(self) -> str | None:
        filtro = self._filtro_server()
        if filtro is None or self.server != "cancella":
            return None
        dove = filtro
        if self._conserva_server():
            dove += f" AND NOT COALESCE({self._conserva_server()}, FALSE)"
        return f"DELETE FROM {self.nome} WHERE {dove}"

    def sql_scaduti(self) -> str | None:
        if self.scadenza is None:
            return None
        s = self.scadenza
        dove = f"{s.colonna} < now() - make_interval(days => $1)"
        if s.solo_se:
            dove += f" AND ({s.solo_se})"
        return f"DELETE FROM {self.nome} WHERE {dove}"


def _t(nome: str, descrizione: str, **kw) -> TabellaDati:
    return TabellaDati(nome=nome, descrizione=descrizione, **kw)


# fmt: off
REGISTRO: tuple[TabellaDati, ...] = (
    # ---------------------------------------------------------------- moderazione
    _t("moderation_notes", "Note dello staff su un utente",
       colonne_utente=("user_id",), colonne_attore=("moderator_id",), colonna_server="guild_id",
       utente="cancella", esporta=True),
    _t("moderation_cases", "Casi di moderazione (avvisi, timeout, ban, kick)",
       colonne_utente=("user_id",), colonne_attore=("moderator_id", "revoked_by"), colonna_server="guild_id",
       utente="cancella", conserva_se="retain_for_security", esporta=True,
       nota="ban e kick restano (#37, #46)"),
    _t("moderation_case_counters", "Contatore dei numeri di caso", colonna_server="guild_id",
       dopo_purga_server=(
           "INSERT INTO moderation_case_counters (guild_id, next_number) "
           "SELECT guild_id, max(case_number) + 1 FROM moderation_cases WHERE guild_id = $1 GROUP BY guild_id "
           "ON CONFLICT (guild_id) DO UPDATE SET next_number = "
           "GREATEST(moderation_case_counters.next_number, EXCLUDED.next_number)"
       ),
       nota="ban e kick restano: il contatore riparte dal numero più alto trattenuto"),
    _t("ban_appelli", "Appelli contro i ban manuali (NF-30)",
       colonne_utente=("user_id",), colonne_attore=("deciso_da",), colonna_server="guild_id",
       utente="cancella", esporta=True,
       scadenza=Scadenza("creato_il", 365, solo_se="stato <> 'aperto'"),
       nota="appelli decisi: 365 giorni, poi spariscono; quelli aperti restano"),
    _t("tempban_stato", "Ruoli salvati e invito di un ban temporaneo con rientro o isolamento",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True,
       scadenza=Scadenza("finisce_il", 30),
       nota="serve solo fino al rientro: 30 giorni dopo la fine non serve più a nessuno"),
    _t("automod_action_log", "Azioni dell'automod",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True,
       scadenza=Scadenza("created_at", 180)),
    _t("automod_violations", "Infrazioni contate dall'automod",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("automod_config", "Configurazione dell'automod", colonna_server="guild_id"),
    _t("automod_advanced_config", "Configurazione avanzata dell'automod", colonna_server="guild_id"),
    _t("automod_escalation_config", "Scala delle punizioni: impostazioni", colonna_server="guild_id"),
    _t("automod_escalation_steps", "Scala delle punizioni: gradini", colonna_server="guild_id"),
    _t("automod_last_synced", "Ultima sincronizzazione delle regole automod", colonna_server="guild_id"),
    # ---------------------------------------------------------------- sicurezza
    _t("security_action_log", "Azioni della suite di sicurezza",
       colonne_attore=("actor_id",), colonna_server="guild_id", utente="conserva",
       scadenza=Scadenza("created_at", 365),
       nota="registro di sicurezza: l'attore resta"),
    _t("security_config", "Configurazione della sicurezza", colonna_server="guild_id"),
    _t("nuke_cases", "Casi di anti-nuke",
       colonne_utente=("actor_id",), colonna_server="guild_id", utente="conserva", server="conserva",
       esporta=True, nota="storico di affidabilità al rientro (#46)"),
    _t("anti_raid_lockdown", "Blocco anti-raid in corso", colonna_server="guild_id"),
    _t("global_ban_direction", "Direzione del ban globale per server", colonna_server="guild_id"),
    _t("global_ban_log", "Ban propagati tra server",
       colonne_utente=("user_id",), utente="conserva", server="conserva", esporta=True,
       nota="storico di sicurezza (#46)"),
    _t("spam_trap_config", "Configurazione della trappola spam", colonna_server="guild_id"),
    _t("spam_trap_incidents", "Incidenti della trappola spam con trascrizione",
       colonne_attore=("invite_creator_id",), colonna_server="guild_id", utente="conserva",
       scadenza=Scadenza("created_at", 180), nota="prova di sicurezza; la trascrizione scade a 180 giorni"),
    _t("spam_trap_join_invites", "Inviti usati da chi è entrato",
       colonne_utente=("user_id",), colonne_attore=("invite_creator_id",), colonna_server="guild_id",
       utente="conserva", esporta=True, scadenza=Scadenza("joined_at", 180)),
    _t("spam_trap_message_index", "Indice dei messaggi per la trappola spam",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella",
       gestita_da="core/repositories/spam_trap_repo.py (prune_old_index)"),
    _t("spam_trap_appeals", "Ricorsi alla trappola spam",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="conserva", esporta=True),
    _t("verify_attempts", "Tentativi di verifica",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True,
       scadenza=Scadenza("attempted_at", 90)),
    _t("verify_blacklist", "Utenti esclusi dalla verifica",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="conserva", server="conserva",
       esporta=True),
    _t("verify_whitelist", "Utenti esentati dalla verifica",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("verify_config", "Configurazione della verifica", colonna_server="guild_id"),
    # ---------------------------------------------------------------- log
    _t("event_log", "Registro eventi unificato",
       colonne_utente=("target_user_id", "actor_id"), colonna_server="guild_id", utente="anonimizza",
       anonimizza=(("target_user_id", "CASE WHEN target_user_id = $1 THEN NULL ELSE target_user_id END"),
                   ("actor_id", "CASE WHEN actor_id = $1 THEN NULL ELSE actor_id END"),
                   ("details", "'{}'::jsonb")),
       conserva_se="event_type IN ('ban', 'tempban', 'softban', 'kick', 'spam_trap_ban')",
       filtro_esportazione=("target_user_id = $1 OR (actor_id = $1 AND "
                            "(target_user_id IS NULL OR target_user_id = actor_id))"),
       escludi_dall_esportazione=("details",),
       esporta=True, gestita_da="core/event_log_retention.py (30 giorni, 180 con il premium)"),
    _t("log_ignora", "Canali, utenti e prefissi ignorati dai log", colonna_server="guild_id"),
    _t("output_channels", "Canali di destinazione dei log e degli avvisi", colonna_server="guild_id"),
    _t("guild_config_history", "Storico delle modifiche alla configurazione",
       colonne_attore=("changed_by",), colonna_server="guild_id", scadenza=Scadenza("created_at", 365)),
    _t("command_usage", "Ultimo comando usato per server e utente",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True,
       scadenza=Scadenza("used_at", 90), gestita_da="core/repositories/command_usage_repo.py (anche)"),
    _t("eval_shell_log", "Registro di eval e shell del proprietario",
       colonne_attore=("executor_id",), utente="conserva", server="conserva",
       nota="registro di controllo del proprietario"),
    # ---------------------------------------------------------------- livelli e economia
    _t("leveling_totals", "XP, monete e livello",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("leveling_activity", "XP e monete per periodo",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("leveling_settings", "Impostazioni dei livelli", colonna_server="guild_id"),
    _t("leveling_xp_rules", "Regole dei moltiplicatori XP", colonna_server="guild_id"),
    _t("level_reward_roles", "Ruoli premio per livello", colonna_server="guild_id"),
    _t("rank_card_prefs", "Colore e tema della rank card",
       colonne_utente=("user_id",), utente="cancella", esporta=True),
    _t("shop_purchases", "Acquisti nel negozio",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("shop_items", "Articoli del negozio", colonna_server="guild_id"),
    _t("giveaway_entries", "Iscritti ai giveaway",
       colonne_utente=("user_id",), utente="cancella", esporta=True,
       filtro_server="giveaway_id IN (SELECT id FROM giveaways WHERE guild_id = $1)"),
    _t("giveaways", "Giveaway", colonne_attore=("created_by",), colonna_server="guild_id"),
    _t("guild_chest_ledger", "Movimenti della cassa del server",
       colonna_server="guild_id", scadenza=Scadenza("created_at", 365)),
    _t("guild_chest", "Cassa del server", colonna_server="guild_id"),
    _t("guild_premium_purchases", "Acquisti premium del server", colonna_server="guild_id",
       server="conserva", nota="registro contabile"),
    _t("guild_premium_status", "Scadenza del premium del server", colonna_server="guild_id",
       server="conserva"),
    _t("monthly_winners_config", "Annuncio dei vincitori del mese", colonna_server="guild_id"),
    # ---------------------------------------------------------------- clan
    _t("clan_treasury_ledger", "Movimenti della tesoreria del clan",
       colonne_utente=("user_id",), utente="anonimizza", anonimizza=(("user_id", "NULL"),), esporta=True,
       filtro_server="clan_id IN (SELECT id FROM clans WHERE guild_id = $1)",
       scadenza=Scadenza("created_at", 365)),
    _t("clan_voice_activity", "Attività vocale nel clan",
       colonne_utente=("user_id",), utente="cancella", esporta=True,
       filtro_server="clan_id IN (SELECT id FROM clans WHERE guild_id = $1)"),
    _t("clan_members", "Membri dei clan",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("clan_monthly_xp", "XP mensile dei clan", colonna_server="guild_id"),
    _t("clan_leaderboard_config", "Bacheca dei clan", colonna_server="guild_id"),
    _t("clans", "Clan", colonne_utente=("owner_id",), colonne_attore=("co_owner_id",),
       colonna_server="guild_id", utente="conserva", azzera_attore=False, esporta=True,
       nota="il titolare passa al co-titolare o al membro più anziano, da solo scioglie il clan "
            "(forget_user_service._clan_del_titolare); il co-titolare esce con NULL"),
    # ---------------------------------------------------------------- ticket, suggerimenti, moduli
    _t("tickets", "Ticket", colonne_utente=("user_id",), colonne_attore=("claimed_by", "closed_by"),
       colonna_server="guild_id", utente="anonimizza", anonimizza=(("user_id", str(UTENTE_CANCELLATO)),),
       esporta=True),
    _t("modmail_threads", "Conversazioni ModMail (ticket via messaggio privato)",
       colonne_utente=("user_id",), colonne_attore=("closed_by",), colonna_server="guild_id",
       utente="anonimizza", anonimizza=(("user_id", str(UTENTE_CANCELLATO)),), esporta=True),
    _t("modmail_config", "Categoria del ModMail", colonne_attore=("updated_by",), colonna_server="guild_id"),
    _t("modmail_blocks", "Utenti bloccati dal ModMail", colonne_utente=("user_id",),
       colonne_attore=("blocked_by",), colonna_server="guild_id", utente="cancella"),
    _t("ticket_form_questions", "Domande del modulo dei ticket",
       filtro_server="panel_id IN (SELECT id FROM ticket_panels WHERE guild_id = $1)"),
    _t("ticket_panels", "Pannelli dei ticket", colonna_server="guild_id"),
    _t("ticket_categories", "Categorie dei ticket", colonna_server="guild_id"),
    _t("ticket_counters", "Contatore dei ticket", colonna_server="guild_id"),
    _t("suggestions", "Suggerimenti",
       colonne_utente=("user_id",), colonne_attore=("decided_by",), colonna_server="guild_id",
       utente="anonimizza",
       anonimizza=(("user_id", str(UTENTE_CANCELLATO)), ("suggestion_text", f"'{TESTO_CANCELLATO}'")),
       esporta=True),
    _t("custom_command_requests", "Richieste di comandi personalizzati",
       colonne_utente=("user_id",), colonne_attore=("decided_by",), colonna_server="requester_guild_id",
       utente="anonimizza",
       anonimizza=(("user_id", str(UTENTE_CANCELLATO)), ("username_snapshot", f"'{TESTO_CANCELLATO}'")),
       esporta=True),
    _t("role_menu_options", "Voci dei menu di ruoli",
       filtro_server="menu_id IN (SELECT id FROM role_menus WHERE guild_id = $1)"),
    _t("role_menus", "Menu di ruoli", colonna_server="guild_id"),
    _t("sticky_messages", "Messaggi fissi", colonna_server="guild_id"),
    _t("greetings_config", "Benvenuto, addio e boost", colonna_server="guild_id"),
    _t("voice_temp_channels", "Canali vocali temporanei",
       colonne_utente=("owner_id",), colonna_server="guild_id", utente="cancella", esporta=True),
    _t("voice_temp_config", "Configurazione dei vocali temporanei", colonna_server="guild_id"),
    # ---------------------------------------------------------------- avvisi e feed
    _t("feed_subscriptions", "Feed RSS", colonne_attore=("created_by",), colonna_server="guild_id"),
    _t("twitch_subscriptions", "Avvisi Twitch", colonne_attore=("created_by",), colonna_server="guild_id"),
    _t("youtube_subscriptions", "Avvisi YouTube", colonne_attore=("created_by",), colonna_server="guild_id"),
    _t("custom_webhooks", "Webhook personalizzati", colonne_attore=("created_by",), colonna_server="guild_id"),
    # ---------------------------------------------------------------- backup e ripristino
    _t("backup_user_snapshots", "Nome e avatar degli utenti nel backup",
       colonne_utente=("user_id",), colonna_server="main_guild_id", utente="cancella", esporta=True),
    _t("backup_jobs", "Lavori di backup", colonna_server="main_guild_id"),
    _t("backup_mirror_webhooks", "Webhook dello specchio di backup", colonna_server="main_guild_id"),
    _t("backup_pairs", "Coppie server principale e di backup", colonna_server="main_guild_id"),
    _t("backup_pair_history", "Coppie di backup già promosse (per il ripristino degli utenti)",
       colonna_server="old_main_guild_id"),
    _t("backup_link_codes", "Codici di collegamento del server di backup (solo l'impronta)",
       colonne_attore=("created_by",), colonna_server="main_guild_id",
       scadenza=Scadenza("created_at", 30), nota="il codice vale 24 ore; dopo 30 giorni la riga va via"),
    _t("restore_contacts", "Chi è già stato contattato da un ripristino (niente DM ripetuti)",
       colonne_utente=("user_id",), colonna_server="target_guild_id", utente="cancella",
       scadenza=Scadenza("contacted_at", 30), nota="serve solo per non rimandare i DM entro 7 giorni"),
    _t("command_permission_tokens", "Token OAuth2 dell'admin per scrivere i permessi dei comandi",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella", esporta=True,
       escludi_dall_esportazione=("encrypted_access_token", "encrypted_refresh_token"),
       nota="cancellare il token revoca il consenso"),
    _t("restore_oauth_tokens", "Token OAuth per il ripristino degli utenti",
       colonne_utente=("user_id",), colonna_server="source_guild_id", utente="cancella", esporta=True,
       escludi_dall_esportazione=("encrypted_access_token", "encrypted_refresh_token"),
       nota="cancellare il token revoca il consenso"),
    # ---------------------------------------------------------------- coda e configurazione
    _t("scheduled_actions", "Azioni differite (tempban, promemoria, messaggi)",
       colonne_utente=("user_id",), colonna_server="guild_id", utente="cancella",
       conserva_utente_se="action_type = 'moderation_tempban_expire' AND NOT (executed OR failed_reason IS NOT NULL)",
       conserva_server_se="action_type = 'moderation_tempban_expire' AND NOT (executed OR failed_reason IS NOT NULL)",
       esporta=True,
       scadenza=Scadenza("COALESCE(executed_at, created_at)", 30, "executed OR failed_reason IS NOT NULL"),
       nota="resta solo lo sban programmato (tempban): promemoria e messaggi programmati hanno testo libero e vanno via"),
    _t("guild_config", "Configurazione del server", colonna_server="guild_id"),
    _t("guild_presence", "Quando il bot è entrato e uscito da ogni server", server="conserva",
       nota="serve a contare i 90 giorni"),
    _t("data_deletion_requests", "Richieste di cancellazione e loro esito",
       colonne_utente=("user_id",), utente="conserva", server="conserva", esporta=True,
       scadenza=Scadenza("richiesta_il", 730, "stato <> 'in_attesa'"),
       nota="prova di ciò che è stato fatto, 24 mesi"),
    # ---------------------------------------------------------------- globali: proprietario e bot
    _t("user_blacklist", "Utenti bloccati dal proprietario",
       colonne_utente=("user_id",), colonne_attore=("added_by",), utente="conserva", server="conserva",
       esporta=True),
    _t("guild_blacklist", "Server bloccati dal proprietario", colonne_attore=("added_by",),
       server="conserva"),
    _t("premium_whitelist", "Server in whitelist premium", colonne_attore=("added_by",), server="conserva"),
    _t("premium_module_flags", "Moduli resi premium", colonne_attore=("updated_by",), server="conserva"),
    _t("premium_toggle_history", "Storico dei cambi premium", colonne_attore=("changed_by",), server="conserva"),
    _t("module_subscriptions", "Abbonamenti per modulo", colonne_attore=("granted_by",), colonna_server="guild_id",
       server="conserva", nota="registro contabile"),
    _t("main_radio_state", "Stato della radio principale", server="conserva"),
    _t("main_radio_tracks", "Tracce della radio principale", colonne_attore=("added_by",), server="conserva"),
    _t("music_sessions", "Worker musicale assegnato a un server", colonna_server="guild_id"),
    _t("command_sync_state", "Impronta dell'ultima sincronizzazione dei comandi", server="conserva"),
)
# fmt: on

_PER_NOME = {t.nome: t for t in REGISTRO}


def tabella(nome: str) -> TabellaDati:
    return _PER_NOME[nome]


def nomi_dichiarati() -> frozenset[str]:
    return frozenset(_PER_NOME)


def identificatori_validi() -> bool:
    """True se ogni nome di tabella e di colonna nel registro è un semplice identificatore."""
    for t in REGISTRO:
        nomi = [t.nome, *t.colonne_utente, *t.colonne_attore]
        if t.colonna_server:
            nomi.append(t.colonna_server)
        nomi.extend(c for c, _ in t.anonimizza)
        if not all(_IDENTIFICATORE.match(n) for n in nomi):
            return False
    return True


def tabelle_con_utente() -> tuple[TabellaDati, ...]:
    return tuple(t for t in REGISTRO if t.colonne_utente)


def tabelle_esportabili() -> tuple[TabellaDati, ...]:
    return tuple(t for t in REGISTRO if t.esporta and t.colonne_utente)


def tabelle_con_scadenza() -> tuple[TabellaDati, ...]:
    return tuple(t for t in REGISTRO if t.scadenza is not None)
