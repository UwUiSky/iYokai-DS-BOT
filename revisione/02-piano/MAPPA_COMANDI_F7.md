# MAPPA_COMANDI_F7.md — Dai comandi di oggi all'albero della fase F7

Controllo del disegno di `guardiano-limiti`, 05/10/2026 (decisione D24).
Dati misurati sull'albero VERO del bot (97 comandi di primo livello,
253 comandi foglia), non su `COMMAND_LIST.md` che non elenca le opzioni.

**Verdetto: REGGE CON QUESTE MODIFICHE.** Con 13 gruppi `/admin` NON
regge: i dati di oggi superano gli **8000 caratteri** (9241).

## 1. Limiti: numeri di oggi e del disegno

Fonte: documentazione ufficiale Discord
(`docs.discord.com/developers/interactions/application-commands`),
letta il 05/10/2026. Regola degli 8000: somma di nome, descrizione e
valore di comando, opzioni, sotto-gruppi, sotto-comandi e scelte.

| Limite | Numero | Albero a 13 gruppi | Albero proposto (16) |
|---|---|---|---|
| Comandi di primo livello | 100 | 13 | 16 (84 liberi) |
| Figli per gruppo | 25 | max 22 (`/admin`) | max 13 (`/clan`, `/music`), `/mod` 12 con `blocco` |
| Sotto-gruppi | 1 livello | `/config language set` oggi è a 3 livelli: da appiattire | rispettato |
| Opzioni per comando | 25 | oggi max 13 | invariato |
| Nomi / descrizioni | 32 / 100 | nuovi nomi tutti 32 o meno | invariato |
| **8000 caratteri** | 8000 | **`/admin` 9241 (116%), `/security` 6973 (87%)** | tutti sotto 4989 (62%) |

Il tetto dei figli (25) si risolve con i sotto-gruppi, **il tetto degli
8000 no**: i caratteri contano tutti i figli, anche quelli nei
sotto-gruppi. Per questo i gruppi si dividono, non basta annidare.

## 2. Caratteri per comando di primo livello (dati di oggi, nomi nuovi)

Descrizione di un sotto-gruppo stimata 50 caratteri. "Riserva" = stima
delle funzioni nuove ancora senza disegno (600 per gruppo nuovo, 300-800
per i più grossi). Soglia di allarme consigliata: 6800 (85%).

| Gruppo | Oggi | Riserva nuove | Totale stimato | Margine | Figli oggi |
|---|---|---|---|---|---|
| `/admin` | 2920 | comandi, premium, ai, musica: 2200 | 5120 | 36% | 5 (+3 nuovi = 8) |
| `/gestione` | 4989 | nessuna (ticket/voice/economia/ruoli/benvenuto) | 4989 | 38% | 5 |
| `/moduli` | 1446 | starboard, contatori, compleanni, statistiche: 2400 | 3846 | 52% | 1 (+4 = 5) |
| `/security` | 3876 | alt, panico: 600 | 4476 | 44% | 8 (+2 = 10) |
| `/automod` | 3153 | 0 | 3153 | 61% | 7 |
| `/owner` | 3611 | privacy, ai: 700 | 4311 | 46% | 5 (+2 = 7) |
| `/clan` | 2383 | accetta: 150 | 2533 | 68% | 13 (+1 = 14) |
| `/fun` | 1774 | 6 nuovi: 900 | 2674 | 67% | 16 (+4 = 20) |
| `/utility` | 1533 | 7 nuovi: 1000 | 2533 | 68% | 9 (+7 = 16) |
| `/mod` | 1718 | blocco: 200 | 1918 | 76% | 11 (+1 = 12) |
| `/music` | 1130 | playlist: 300 | 1430 | 82% | 13 (+1 = 14) |
| `/level` | 745 | 3 nuovi: 500 | 1245 | 84% | 8 (+3 = 11) |
| `/log` | 683 | 3 nuovi: 400 | 1083 | 86% | 4 (+3 = 7) |
| `/modban`, `/ticket`, `/voice` | 440-728 | 0 | sotto 800 | oltre 90% | 5 / 7 / 6 |

Per `/admin` come nella tabella di D24 (22 figli, tutto dentro): 9241
caratteri con i soli 59 comandi di oggi (116%), prima delle 8 funzioni
nuove. **Non regge.** Nemmeno accorciare le descrizioni basta
(servirebbero 1241 + nuove, circa 2500 in meno).

## 3. Modifiche richieste a D24 / NUOVE_FUNZIONI.md

1. **Da 13 a 16 gruppi** (84 liberi su 100, nessun rischio sul tetto):
   `/admin` si divide in `/admin` (impianto: `setup`, `config`, `lingua`,
   `backup`, `messaggi`, più `comandi`, `premium`, `ai`, `musica`),
   `/gestione` (`ticket`, `voice`, `economia`, `ruoli`, `benvenuto`) e
   `/moduli` (`alert`, più `starboard`, `contatori`, `compleanni`,
   `statistiche`). `/security` cede `automod`, `parole`, `esenzioni` a
   `/automod` (resta un comando di primo livello come oggi).
2. `/admin`: i figli diventano al massimo 9 (margine 16 su 25). Il
   sotto-gruppo `restore` si fonde in `backup`; `embed` e `moduli`
   (tabella D24) si fondono: `embed` in `messaggi`, `moduli` in
   `setup attiva`. Tabella D24 aveva `setup` e `moduli`: chiarire.
3. `/config language set|show` è già a 3 livelli: sotto `/admin` non
   può esserlo. Diventa il sotto-gruppo `/admin lingua set|show`.
4. Mancano nella tabella D24: `request-custom-command` (va in
   `/utility richiedi-comando`, `/utility` sale a 16), `sticky` e
   `schedule-message` (`/admin messaggi`), `giveaway`, `assegna-*`,
   `level-roles`, `monthly-winners`, `rolemenu`, `alerts`, `greetings`,
   `voicetemp-*`, `ticket-*`, `report-setup`, `suggestion-setup`.
5. Togliere il prefisso `[Admin] `/`[OWNER] ` dalle descrizioni (con
   `default_permissions` il comando è nascosto a chi non può): -8
   caratteri per comando.
6. Aggiungere un test `tests/test_command_tree_invariants.py`:
   caratteri per comando di primo livello (<= 8000, allarme a 6800),
   nomi unici tra fratelli, regex dei nomi, `default_permissions` solo
   sul primo livello.

## 4. Mappa `comando oggi → nuovo percorso`

Tutti i 97 comandi di primo livello (253 foglie) hanno posto. Nessun
gruppo supera 25 figli. Nomi: nessun conflitto tra fratelli, tranne
`/log canale` (fusione voluta di `logs-setup` e `mod-log-setup`, serve
l'opzione `tipo`). Le frecce `a→b` sono i nomi che cambiano.

### /owner

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/owner` premium-list→list, premium-toggle→toggle, premium-grant→grant, premium-revoke→revoke, premium-subscriptions→subscriptions, premium-status-all→status-all, premium-panel→panel, whitelist-add, whitelist-remove, whitelist-list | `/owner premium` | |
| `/owner` blacklist-user-add→utente-add, blacklist-guild-add→server-add, blacklist-user-remove→utente-remove, blacklist-guild-remove→server-remove, blacklist-user-list→utente-list, blacklist-guild-list→server-list | `/owner blacklist` | |
| `/owner` cog-load→load, cog-unload→unload, cog-reload→reload | `/owner cog` | |
| `/owner` eval, shell, memory-status, leave-guild, announce, stats | `/owner system` | |
| `/custom-command-requests-setup` | `/owner system richieste-canale` | |
| `/nonstop-main` add-track, add-local, remove-track, list-tracks, start, stop | `/owner radio` | |

### /admin

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/report-setup` | `/admin config canale-report` | |
| `/suggestion-setup` | `/admin config canale-suggerimenti` | |
| `/setup` | `/admin setup attiva` | |
| `/setup-wizard` | `/admin setup wizard` | |
| `/config` history, rollback, reset, export, import | `/admin config` | |
| `/config language` show, set | `/admin lingua` | |
| `/define-main` | `/admin backup main` | |
| `/define-backup` | `/admin backup crea` | |
| `/promuovi-backup` | `/admin backup promuovi` | |
| `/restore-users` | `/admin backup restore-utenti` | |
| `/configura-restore` | `/admin backup restore-modo` | |
| `/schedule-message` set→programma, list→programmati, cancel→annulla | `/admin messaggi` | |
| `/sticky` set→sticky-set, remove→sticky-togli | `/admin messaggi` | |

### /gestione

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/shop` add-item→shop-add, remove-item→shop-remove | `/gestione economia` | |
| `/cassa` sblocca-premium→cassa-premium | `/gestione economia` | |
| `/assegna-lobby` | `/gestione economia assegna-lobby` | |
| `/assegna-winner` | `/gestione economia assegna-winner` | |
| `/giveaway` | `/gestione economia giveaway` | |
| `/monthly-winners` set→vincitori-set, disable→vincitori-off | `/gestione economia` | |
| `/level-roles` add→livello-add, remove→livello-remove, list→livello-list | `/gestione ruoli` | |
| `/rolemenu` create→menu-crea, add-option→menu-aggiungi, remove-option→menu-togli, delete→menu-elimina | `/gestione ruoli` | |
| `/ticket-setup` | `/gestione ticket setup` | |
| `/ticket-panel` | `/gestione ticket panel` | |
| `/ticket-stats` | `/gestione ticket stats` | |
| `/ticket-category` add→categoria-add, remove→categoria-remove, list→categoria-list | `/gestione ticket` | |
| `/ticket-support-role` add→ruolo-add, remove→ruolo-remove, list→ruolo-list | `/gestione ticket` | |
| `/voicetemp-setup` | `/gestione voice setup` | |
| `/voicetemp-panel` | `/gestione voice panel` | |
| `/voicetemp-cap` | `/gestione voice cap` | |
| `/voicetemp-platform-setup` | `/gestione voice piattaforme` | |
| `/greetings` welcome-setup→benvenuto, goodbye-setup→addio, boost-setup→boost, preview→anteprima | `/gestione benvenuto` | |

### /moduli

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/alerts` add→feed, webhook-create→webhook, remove→rimuovi, add-twitch→twitch, add-youtube-live→youtube-live, list→elenco | `/moduli alert` | |

### /mod

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/warn` | `/mod warn` | |
| `/timeout` | `/mod timeout` | |
| `/untimeout` | `/mod untimeout` | |
| `/clear` | `/mod clear` | |
| `/lock` | `/mod lock` | |
| `/unlock` | `/mod unlock` | |
| `/slowmode` | `/mod slowmode` | |
| `/mute-role` | `/mod mute` | |
| `/unmute-role` | `/mod unmute` | |
| `/modcase` history→storico, view→vedi | `/mod caso` | |
| `/modnote` add→aggiungi, list→elenca | `/mod nota` | |

### /modban

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/ban` | `/modban ban` | |
| `/tempban` | `/modban tempban` | |
| `/softban` | `/modban softban` | |
| `/kick` | `/modban kick` | |
| `/unban` | `/modban unban` | |

### /security

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/escalation` enable, disable, set-reset-days, set-step, remove-step, reset, status | `/security escalation` | |
| `/anti-nuke` enable, limits, trusted-add, trusted-remove, punish-action, recovery, status | `/security antinuke` | |
| `/anti-raid` enable, join-rate, account-age, username-check, avatar-check, lockdown-action, alert-channel, status | `/security antiraid` | |
| `/global-ban` enable, disable, status | `/security globalban` | |
| `/verify` setup, panel, whitelist-add, whitelist-remove, blacklist-add, blacklist-remove | `/security verify` | |
| `/permission-heatmap` | `/security heatmap` | |
| `/security-score` | `/security score` | |
| `/spamtrap-setup` | `/security spamtrap` | |

### /automod

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/automod` invites, anti-link-mode, anti-link-domain, anti-spam-messages, anti-spam-emoji, anti-spam-sticker, anti-caps, anti-zalgo, anti-mention, anti-attachment, actions-set | `/automod filtri` | |
| `/automod` sync, mute-duration, log-channel, status | `/automod` | |
| `/automod` badword-add→add, badword-remove→remove, badword-list→list | `/automod parole` | |
| `/automod` exempt-channel-add→channel-add, exempt-channel-remove→channel-remove, exempt-role-add→role-add, exempt-role-remove→role-remove | `/automod esenzioni` | |

### /log

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/logs-setup` | `/log canale` | |
| `/mod-log-setup` | `/log canale` | Si fonde con `logs-setup`: opzione `tipo` con scelte (8-12, max 25) |
| `/logs-status` | `/log stato` | |
| `/logs` user→utente, channel→canale | `/log cerca` | |
| `/logs` export→esporta | `/log esporta` | |

### /ticket

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/ticket` claim, add, remove, rename, priority, close, forceclose | `/ticket` | |

### /voice

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/voice` rename, limit, lock, unlock, kick, transfer | `/voice` | |

### /music

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/play` | `/music play` | |
| `/skip` | `/music skip` | |
| `/stop` | `/music stop` | |
| `/pause` | `/music pause` | |
| `/resume` | `/music resume` | |
| `/queue` | `/music queue` | |
| `/clear-queue` | `/music clear-queue` | |
| `/shuffle` | `/music shuffle` | |
| `/nowplaying` | `/music nowplaying` | |
| `/disconnect` | `/music disconnect` | |
| `/loop` track, queue | `/music loop` | |
| `/nonstop` on, off | `/music nonstop` | |
| `/volume` set, up, down | `/music volume` | |

### /level

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/rank` | `/level rank` | |
| `/balance` | `/level balance` | |
| `/daily` | `/level daily` | |
| `/work` | `/level work` | |
| `/pay` | `/level pay` | |
| `/leaderboard` | `/level leaderboard` | |
| `/shop` list, buy | `/level shop` | |
| `/cassa` saldo | `/level cassa` | |

### /clan

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/clan` crea, info, membri, classifica, sciogli, invita, lascia, espelli, promuovi, compra-canale | `/clan` | |
| `/clan bacheca` set, disable | `/clan bacheca` | |
| `/clan tesoreria` dona, trasferisci | `/clan tesoreria` | |
| `/clan boost` individuale, gilda | `/clan boost` | |

### /fun

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/fun` coinflip, dice, rps, 8ball, joke, quote, fact, grayscale, invert, blur, pixelate, meme, animal, search-image | `/fun` | |
| `/ship` | `/fun ship` | |
| `/rate` | `/fun rate` | |

### /utility

| Comando oggi | Nuovo percorso | Note |
|---|---|---|
| `/report` | `/utility report` | |
| `/suggest` | `/utility suggest` | |
| `/search` | `/utility cerca-comando` | |
| `/request-custom-command` | `/utility richiedi-comando` | |
| `/ping` | `/utility ping` | |
| `/poll` | `/utility poll` | |
| `/serverstats` | `/utility serverstats` | |
| `/reactionsnipe` | `/utility reactionsnipe` | |
| `/reminder` set, list, cancel | `/utility reminder` | |

## 5. Permessi e contesto per gruppo

`default_member_permissions` vale **solo sul comando di primo livello**
(LIM-57) e decide solo chi lo **vede**: non è un'autorizzazione. Resta
il controllo nel codice per ogni sotto-comando (D24: ruolo admin e ruolo
mod del bot). Un admin può cambiarlo in Integrazioni.

| Gruppo | `default_permissions` | `guild_only` | Controllo nel codice |
|---|---|---|---|
| `/owner` | `administrator` | sì, e registrato solo nel server dell'owner | `user.id == OWNER_ID` |
| `/admin`, `/gestione`, `/moduli` | `manage_guild` | sì | ruolo admin del bot |
| `/security` | `administrator` | sì | ruolo admin del bot |
| `/automod` | `manage_guild` | sì | ruolo admin del bot |
| `/mod` | `moderate_members` | sì | per sotto-comando: `manage_messages` (clear), `manage_channels` (lock, slowmode) |
| `/modban` | `ban_members` | sì | `kick_members` per `kick` |
| `/log` | `manage_guild` | sì | `view_audit_log` per `cerca` e `esporta` |
| `/ticket`, `/voice`, `/music`, `/level`, `/clan`, `/fun`, `/utility` | nessuno (tutti) | sì | `forceclose` e le azioni staff nel codice |

Oggi nessun comando ha `default_permissions` e nessuno è `guild_only`:
tutti e 97 compaiono anche in DM (la tabella `contexts` è vuota).
`default_member_permissions = "0"` nasconde a tutti salvo gli admin.

**`/owner`**: va aggiunto con `tree.add_command(gruppo, guild=Object(MAIN_GUILD_ID))`
e sincronizzato con `tree.sync(guild=...)`. I comandi di un server hanno
un tetto di 100 per conto loro, separato dai 100 globali. Da 25 su 25 si
passa a 7 figli (`premium`, `blacklist`, `cog`, `system`, `radio`,
`privacy`, `ai`); i sotto-gruppi più pieni: `premium` 10, `system` 7.
Trappola: in sviluppo `main.py:300-303` copia l'albero globale sul server
con `copy_global_to`: un `/owner` rimasto globale compare due volte.

## 6. Cambio di nomi e sincronizzazione (Discord, letto il 05/10/2026)

- `tree.sync()` è una sovrascrittura in blocco: Discord sostituisce
  **tutti** i comandi dell'app. I nomi non nel nuovo elenco spariscono
  subito, i 97 vecchi insieme. Non c'è un periodo di convivenza: avvisare
  gli utenti prima (annuncio con `/owner system announce`).
- I comandi globali hanno "read-repair": se un client usa un comando
  vecchio, Discord lo rifiuta e ricarica l'elenco. Possibile qualche
  errore "comando sconosciuto" per chi ha la finestra aperta.
- Tetto: "200 creazioni di comandi al giorno, per server". Contano gli
  oggetti di primo livello, non i sotto-comandi: F7 ne crea al massimo
  16. La documentazione non dice se la sovrascrittura conta ogni nome
  nuovo; anche nel caso peggiore 16 << 200. Rischio vero: sincronizzare
  a ogni avvio durante lo sviluppo (`main.py:300-306`). Sincronizzare
  solo se l'impronta dell'albero cambia.
- Nomi dei comandi: regex `^[-_\u02BC\p{L}\p{N}\p{sc=Deva}\p{sc=Thai}]{1,32}$`,
  minuscolo. Non esistono nomi riservati per i bot: i comandi del client
  (`/giphy`, `/tenor`, `/shrug`...) convivono con quelli dell'app.
- Migrazione dati: gli ID dei vecchi comandi cambiano. Messaggi con
  menzioni `</nome:id>` salvate nel database (guide, `/setup`, errori)
  vanno rigenerati; cercare `</` nei testi.
