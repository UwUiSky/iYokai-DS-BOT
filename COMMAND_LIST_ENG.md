# Command list (English) — iYokai

Generated automatically by `scripts/generate_command_list.py` on 2026-11-08 12:06 UTC from the REAL command tree. English names and descriptions are the ones Discord shows to users with the client in English (`locales/en-US/comandi.json`); the base names in the code are Italian. Regenerate after every commit that adds, removes or renames a command.

**Total: 679 commands in 41 categories.**

## Admin: AI

- **`/admin-ai banned-words`** — Words or topics the AI must refuse.
- **`/admin-ai boss set`** — Channel, days, time and rewards of the World Boss.
- **`/admin-ai boss start`** — Summons the World Boss right now.
- **`/admin-ai build`** — The AI suggests roles and channels from a description; you confirm.
- **`/admin-ai channel`** — Turns the AI off or back on in a channel.
- **`/admin-ai character`** — Installs, removes or deletes a server AI character.
- **`/admin-ai dungeon start`** — Starts a group dungeon in a channel.
- **`/admin-ai dungeon stories`** — How many dungeon stories are ready for the server theme.
- **`/admin-ai enable`** — Turns the AI on or off in the server (consent required).
- **`/admin-ai features`** — Turns on automatic features: reply to mentions, flags.
- **`/admin-ai knowledge add`** — Adds an entry to the knowledge base.
- **`/admin-ai knowledge list`** — The knowledge base entries.
- **`/admin-ai knowledge remove`** — Removes an entry from the knowledge base.
- **`/admin-ai limits`** — Spending cap and quotas: per user, per feature, images.
- **`/admin-ai lore`** — Server tone and setting used in every AI text.
- **`/admin-ai moderation`** — The AI flags suspicious messages of a channel to the staff.
- **`/admin-ai mystery create`** — Hides a mystery with a code and a prize for the server.
- **`/admin-ai mystery list`** — The server mysteries (the code stays secret).
- **`/admin-ai mystery remove`** — Removes a mystery.
- **`/admin-ai privacy`** — User messages sent to the AI, memory and answer length.
- **`/admin-ai staff first-answer`** — Turns the AI first automatic answer on or off in a ticket panel.
- **`/admin-ai staff incident`** — Summarises the latest security events of the server.
- **`/admin-ai staff rule`** — Tell AutoMod what you want: it proposes the rule, you turn it on.
- **`/admin-ai staff search-log`** — Search the logs with a question (who, what, when).
- **`/admin-ai status`** — AI status in the server: providers, settings and monthly usage.
- **`/admin-ai summary preview`** — Shows you the digest as of now, without publishing it.
- **`/admin-ai summary set`** — Server digest: channel, hour, frequency and channels to read.
- **`/admin-ai translation`** — Automatically translates every message of a channel.
- **`/admin-ai voice set`** — Voice: on or off, tone and greeting channels.
- **`/admin-ai voice speak`** — Yokai says an announcement out loud in a channel.

## Admin: anti-nuke

- **`/admin-antinuke canale-allarmi`** — Choose where Anti-Nuke alarms are sent (channel or forum).
- **`/admin-antinuke cases`** — Log of stopped attacks: list or detail of a case.
- **`/admin-antinuke enable`** — Turns Anti-Nuke on or off.
- **`/admin-antinuke guards`** — Guards on single actions: role permissions, roles to members, links, bots.
- **`/admin-antinuke limits`** — Sets the detection threshold for a category.
- **`/admin-antinuke punish-action`** — What to do to the author of a mass destructive action.
- **`/admin-antinuke recovery`** — Turns automatic re-creation of channels/roles deleted during an attack on or off.
- **`/admin-antinuke release`** — Lifts the quarantine of a case's author and gives their roles back.
- **`/admin-antinuke status`** — Shows the current Anti-Nuke setup.
- **`/admin-antinuke trusted-add`** — Exempts a user, bot or webhook from Anti-Nuke checks.
- **`/admin-antinuke trusted-list`** — Lists who is exempt from Anti-Nuke checks and with which limits.
- **`/admin-antinuke trusted-remove`** — Removes a user, bot or webhook from the Anti-Nuke trusted list.

## Admin: anti-raid

- **`/admin-antiraid account-age`** — Minimum account age to not be considered suspicious.
- **`/admin-antiraid alert-channel`** — Channel for security alerts (Anti-Raid + Anti-Nuke).
- **`/admin-antiraid avatar-check`** — Turns missing-avatar detection on or off.
- **`/admin-antiraid banned-names`** — Words or patterns (with *) banned in the names of new members.
- **`/admin-antiraid enable`** — Turns Anti-Raid on or off.
- **`/admin-antiraid join-filter`** — Action for a join filter (works outside a raid too).
- **`/admin-antiraid join-rate`** — Sets the join limit in a time window.
- **`/admin-antiraid level`** — Alert levels: normal, alert, high, lockdown.
- **`/admin-antiraid list`** — File with every raid account from the last hours.
- **`/admin-antiraid lockdown-action`** — What to do when a raid is detected.
- **`/admin-antiraid ping-roles`** — Staff roles pinged on the first raid alert (empty: none).
- **`/admin-antiraid quarantine-hold`** — Stops untrusted people from lifting quarantine by hand.
- **`/admin-antiraid release`** — Lifts a member's quarantine (the right way, with the lock on).
- **`/admin-antiraid report`** — Report an undetected raid to the bot team.
- **`/admin-antiraid signals`** — Raid signals on the latest joins and action on earlier joiners.
- **`/admin-antiraid status`** — Shows the current Anti-Raid setup.
- **`/admin-antiraid username-check`** — Turns suspicious username pattern detection on or off.

## Admin: AutoMod

- **`/admin-automod exemptions channel-add`** — Exempts a channel from all advanced AutoMod filters.
- **`/admin-automod exemptions channel-remove`** — Removes a channel's exemption.
- **`/admin-automod exemptions role-add`** — Exempts a role from all advanced AutoMod filters.
- **`/admin-automod exemptions role-remove`** — Removes a role's exemption.
- **`/admin-automod gruppo`** — Turns all rules of a group on or off.
- **`/admin-automod images`** — Settings for the suspicious image filter.
- **`/admin-automod liste`** — Opens the AutoMod named lists panel: words and domains.
- **`/admin-automod log-channel`** — Sets the channel for the advanced AutoMod action log.
- **`/admin-automod mute-duration`** — Sets the timeout length used by the AutoMod 'mute' action.
- **`/admin-automod odio base`** — Turns the base list of hate slurs on or off.
- **`/admin-automod odio lockdown`** — Preventive block of hateful phrases.
- **`/admin-automod odio nomi`** — Checks nicknames and display names on join and on change.
- **`/admin-automod odio parola`** — Adds or removes a custom word or an allowed word.
- **`/admin-automod odio prova`** — Tests a text against the banned words without acting.
- **`/admin-automod odio richiami`** — How many warnings for hate words lead to a timeout.
- **`/admin-automod odio status`** — Shows how the banned words are set up.
- **`/admin-automod regole`** — Opens the AutoMod rules panel: conditions and actions.
- **`/admin-automod reset`** — Resets an AutoMod rule counter.
- **`/admin-automod status`** — Shows the current advanced AutoMod filter setup.
- **`/admin-automod summary`** — AutoMod violations summary for the server, in pages.
- **`/admin-automod sync`** — Forces a manual sync of the AutoMod rules.
- **`/admin-automod violazione-togli`** — Removes one violation from the AutoMod log.
- **`/admin-automod violazioni`** — Shows a user's AutoMod violations, in pages.
- **`/admin-automod words add`** — Adds a banned word.
- **`/admin-automod words list`** — Shows the configured banned words.
- **`/admin-automod words remove`** — Removes a banned word.

## Admin: backup

- **`/admin-backup cancel`** — Stops the running load (what is done stays).
- **`/admin-backup chat load`** — Loads a saved chat into a channel, even a different one.
- **`/admin-backup chat save`** — Saves the latest messages of a channel (up to 1000) to load them later.
- **`/admin-backup connect`** — Links THIS server as backup, with the code received from the main server.
- **`/admin-backup copy channel`** — Copies a channel with its permissions; a category with its channels.
- **`/admin-backup copy role`** — Copies a role with its permissions and, optionally, its channel permissions.
- **`/admin-backup create`** — Prepares the backup: link code and link for the new server.
- **`/admin-backup delete`** — Deletes a saved copy.
- **`/admin-backup export`** — Exports structure, channels, roles, bans or reactions to a file.
- **`/admin-backup import`** — Imports the structure from a JSON file, picking what to apply.
- **`/admin-backup list`** — The saved copies of this server, with their date.
- **`/admin-backup load`** — Loads a saved copy into this server, picking the parts.
- **`/admin-backup log`** — Who used backups, templates and syncs (last 20, 365 days).
- **`/admin-backup main`** — Registers this server as 'main' for the Backup System.
- **`/admin-backup promote`** — Promotes THIS server (so far a backup) to new main, if the original main is lost.
- **`/admin-backup restore mode`** — Picks how this server handles user restore via OAuth2.
- **`/admin-backup restore users`** — Restores into THIS server the users of another server's latest snapshot.
- **`/admin-backup save`** — Saves a dated copy of this server structure.
- **`/admin-backup status`** — Progress of the latest load in this server.
- **`/admin-backup template`** — Templates: share a copy with a code or load another server one.

## Admin: welcome

- **`/admin-welcome boost`** — Sets up the boost message.
- **`/admin-welcome extra`** — Welcome: DM text, variants, reactions; ban and goodbye messages.
- **`/admin-welcome goodbye`** — Sets up the goodbye message.
- **`/admin-welcome image`** — Adds to the welcome an image with the member's avatar, name and number.
- **`/admin-welcome message`** — Sets up the welcome message.
- **`/admin-welcome preview`** — Shows a preview of how a message would look.

## Admin: bot setup

- **`/admin-bot config bot-nickname`** — Changes the bot's name in this server.
- **`/admin-bot config cleanup`** — Removes channels and roles that no longer exist from the settings.
- **`/admin-bot config export`** — Exports this server's configuration to a file.
- **`/admin-bot config history`** — Shows the latest configuration changes.
- **`/admin-bot config import`** — Imports a configuration from a file exported with /admin-bot config export.
- **`/admin-bot config report-channel`** — Sets the reports channel.
- **`/admin-bot config reset`** — Resets this server's configuration.
- **`/admin-bot config rollback`** — Restores the previous value of a change.
- **`/admin-bot config suggestions-channel`** — Sets the suggestions channel.
- **`/admin-bot config sync`** — Rewrites this server's command permissions.
- **`/admin-bot language set`** — Sets this server's language.
- **`/admin-bot language show`** — Shows the language set for this server.
- **`/admin-bot policy channels`** — Where the bot answers commands.
- **`/admin-bot policy comando`** — Turns a single command off or on again.
- **`/admin-bot policy diagnosis`** — Finds out why a command does not work here.
- **`/admin-bot policy ignore`** — The bot ignores a role or a user.
- **`/admin-bot policy list`** — Shows the command policy and, if you want, clears a list.
- **`/admin-bot premium appearance`** — The bot's avatar, banner and description in this server (premium).
- **`/admin-bot premium branding`** — Use a bot with your own name and avatar (premium).
- **`/admin-bot premium redeem`** — Redeems a premium code for this server.
- **`/admin-bot premium sblocca`** — Unlocks a premium module for 30 days with coins from the server treasury.
- **`/admin-bot premium status`** — Shows how premium is unlocked in this server.
- **`/admin-bot setup enable`** — Turns the bot's modules on or off, by category.
- **`/admin-bot setup wizard`** — Step-by-step setup of the bot's roles and modules, one category at a time.

## Admin: economy

- **`/admin-economy announcements clan-off`** — Turns off the automatic top 3 guilds announcement.
- **`/admin-economy announcements clan-set`** — Sets the channel for the monthly top 3 guilds announcement.
- **`/admin-economy announcements winners-off`** — Turns off the monthly winners announcement.
- **`/admin-economy announcements winners-set`** — Sets the channel for the monthly winners announcement.
- **`/admin-economy award-lobby`** — Participation prize: gives coins to those in voice NOW, from the server treasury.
- **`/admin-economy award-winner`** — Winner prize: gives coins to a member, from the server treasury.
- **`/admin-economy coins`** — Edits a member's balance.
- **`/admin-economy premium-cashbox`** — Unlocks one month of premium bot by spending from the treasury.
- **`/admin-economy shop-add`** — Adds an item to the shop.
- **`/admin-economy shop-edit`** — Edits a shop item (price, stock, required role...).
- **`/admin-economy shop-remove`** — Removes an item from the shop.

## Admin: filters

- **`/admin-filters actions-set`** — Sets which actions run when an advanced filter triggers.
- **`/admin-filters anti-attachment`** — Configures anti attachment-spam (too many attachments in a short time).
- **`/admin-filters anti-caps`** — Configures anti-caps (too many capital letters).
- **`/admin-filters anti-link-domain`** — Adds or removes a domain from the link whitelist/blacklist.
- **`/admin-filters anti-link-mode`** — Sets the link filter mode.
- **`/admin-filters anti-mention`** — Configures anti mass-mention (too many users tagged in one message).
- **`/admin-filters anti-spam-emoji`** — Configures emoji anti-spam (too many emoji in one message).
- **`/admin-filters anti-spam-messages`** — Configures message anti-spam (too many messages in a short time).
- **`/admin-filters anti-spam-sticker`** — Configures sticker anti-spam (too many stickers in a short time).
- **`/admin-filters anti-zalgo`** — Turns anti-zalgo on or off (text with abnormal diacritics).
- **`/admin-filters content`** — Embeds and forwards checked by filters; banned file types.
- **`/admin-filters invites`** — Turns the automatic Discord invite block on or off.
- **`/admin-filters media-channel`** — Media-only channel, no attachments or normal.
- **`/admin-filters messages`** — Repeated, too short, links and mentions counted over time (0 = off).
- **`/admin-filters phishing`** — Turn the phishing link block on or off (fake gifts, fake logins).
- **`/admin-filters text-shape`** — Limits on message shape: line breaks, length, spoilers (0 = off).

## Admin: giveaways

- **`/admin-giveaway scheduled`** — Scheduled giveaways: list (including failed ones) or cancel.
- **`/admin-giveaway start`** — Starts a giveaway.
- **`/admin-giveaway template`** — Giveaway templates: save, list, delete, start.

## Admin: levels and XP

- **`/admin-levels announcement`** — Where and when to announce level-ups.
- **`/admin-levels card`** — Shows or hides image backgrounds of cards and profiles in this server.
- **`/admin-levels exclude`** — A channel, category or role gives no XP (repeat to undo).
- **`/admin-levels member`** — Edits a member's XP and level.
- **`/admin-levels multiplier`** — XP multiplied in a channel or for a role (factor 1 = removes the rule).
- **`/admin-levels progress`** — Turns missions, streaks, achievements and pass on or off; sets the server goal.
- **`/admin-levels rewards`** — Reward roles: keep them all or only the highest.
- **`/admin-levels shop`** — Asks for confirmation before each shop purchase (can be turned off).
- **`/admin-levels show`** — Shows this server's level settings.
- **`/admin-levels xp`** — How much XP and coins are earned, and how multipliers add up.

## Admin: log

- **`/admin-log channel`** — Sets the server log channel (or forum).
- **`/admin-log channel-archive`** — Download the latest messages of a channel in a file, including just-deleted ones.
- **`/admin-log create-channels`** — Creates a private category with one channel for each log type.
- **`/admin-log create-forum`** — Creates a private forum for logs: one post for each type.
- **`/admin-log events`** — Turn each single log event on or off.
- **`/admin-log export`** — Exports the full server event history as a JSON file.
- **`/admin-log forum-view`** — A forum with one post for each channel or case. Without a forum, the view turns off.
- **`/admin-log ignore`** — What the logs do not record (channels, users, roles; texts only for messages).
- **`/admin-log search channel`** — Shows a channel's event history.
- **`/admin-log search role`** — Shows a role's event history.
- **`/admin-log search user`** — Shows a user's event history.
- **`/admin-log status`** — Shows where the server logs go.
- **`/admin-log webhook`** — Sends logs through a channel webhook, grouped, with its own rate limits.

## Admin: messages

- **`/admin-messages embed create`** — Creates an embed and shows the preview.
- **`/admin-messages embed delete`** — Deletes a saved embed (the published message stays).
- **`/admin-messages embed edit`** — Edits a saved embed (and the already published message).
- **`/admin-messages embed list`** — Shows the saved embeds.
- **`/admin-messages embed publish`** — Sends a saved embed to a channel.
- **`/admin-messages pinned remove`** — Removes a channel's sticky message.
- **`/admin-messages pinned set`** — Sets a channel's sticky message.
- **`/admin-messages reminders`** — For staff: the reminders set in this server.
- **`/admin-messages replies create`** — Creates an automatic reply.
- **`/admin-messages replies delete`** — Deletes an automatic reply.
- **`/admin-messages replies list`** — Shows the server's automatic replies.
- **`/admin-messages scheduled cancel`** — Cancels a scheduled message.
- **`/admin-messages scheduled create`** — Schedules a message.
- **`/admin-messages scheduled list`** — Shows this server's scheduled messages.
- **`/admin-messages tag create`** — Creates a custom command.
- **`/admin-messages tag delete`** — Deletes a custom command.
- **`/admin-messages tag edit`** — Edits a custom command.
- **`/admin-messages tag list`** — Shows the server's custom commands.
- **`/admin-messages tag prefix`** — Picks the prefix to use commands by typing in the channel.

## Admin: modules

- **`/admin-modules alert feed`** — Follows an RSS/Atom feed (YouTube, Reddit, or any other).
- **`/admin-modules alert kick`** — Notify when a Kick channel goes live.
- **`/admin-modules alert list`** — Shows the feeds followed by this server.
- **`/admin-modules alert live-role`** — Role given to members who are live.
- **`/admin-modules alert options`** — Alert options: role, end of stream, button.
- **`/admin-modules alert remove`** — Removes a feed or Twitch subscription, or a webhook.
- **`/admin-modules alert social-guide`** — Alerts for TikTok, Instagram and X.
- **`/admin-modules alert twitch`** — Notifies when a Twitch streamer goes live/offline.
- **`/admin-modules alert webhook`** — Creates a custom webhook: third-party services can post in a channel.
- **`/admin-modules alert youtube-live`** — Notifies when a YouTube channel goes live (needs YOUTUBE_API_KEY on the bot).
- **`/admin-modules applications create`** — Creates a form or application.
- **`/admin-modules applications delete`** — Deletes a form and its answers.
- **`/admin-modules applications list`** — This server's forms.
- **`/admin-modules birthdays channel`** — Picks the wishes channel (empty to turn them off).
- **`/admin-modules birthdays role`** — A role for 24 hours for whoever has a birthday (empty to remove it).
- **`/admin-modules counters create`** — Creates a channel that shows a number.
- **`/admin-modules counters delete`** — Stops updating a counter (the channel stays).
- **`/admin-modules counters list`** — Shows the server's counters.
- **`/admin-modules counting`** — Counting game: pick the channel where people count 1, 2, 3... in turn.
- **`/admin-modules invites`** — Invite log channel and who has the personal link.
- **`/admin-modules starboard disattiva`** — Turns the board off.
- **`/admin-modules starboard set`** — Picks the board channel and the star threshold.
- **`/admin-modules starboard threshold`** — Changes how many stars are needed to reach the board.
- **`/admin-modules statistics diagnosis`** — Why are the statistics not counting?
- **`/admin-modules statistics list`** — Show the statistics rules and exclusions.
- **`/admin-modules statistics ruolo-aggiungi`** — Give a role to active members and remove it when they stop.
- **`/admin-modules statistics ruolo-elimina`** — Delete an activity role rule.
- **`/admin-modules statistics settings`** — Exclude channels or roles from the statistics.

## Admin: music

- **`/admin-music request-channel`** — Channel where typing a title queues it, with the player.
- **`/admin-music settings`** — Changes the server's music settings.
- **`/admin-music summary`** — Shows all the server's music settings.

## Admin: roles

- **`/admin-roles auto add`** — Adds a role given automatically to new members.
- **`/admin-roles auto list`** — Shows the server's automatic roles.
- **`/admin-roles auto remove`** — Removes a role given automatically to new members.
- **`/admin-roles auto ricorda`** — Gives roles back to people who leave and rejoin within a set time.
- **`/admin-roles auto sync`** — Give the automatic roles to members already in the server too.
- **`/admin-roles bulk`** — Give or remove a role to many members at once, with filters.
- **`/admin-roles bulk-stop`** — Stop the bulk operation in progress.
- **`/admin-roles create`** — Create a new role.
- **`/admin-roles diagnosis`** — Find out why the bot cannot give a role.
- **`/admin-roles edit`** — Change name, color and options of a role.
- **`/admin-roles give`** — Give one or more roles to a member, also for a time.
- **`/admin-roles menu access`** — Limits a menu to certain roles or excludes others.
- **`/admin-roles menu add`** — Adds an option to a role menu.
- **`/admin-roles menu create`** — Creates a new role menu.
- **`/admin-roles menu delete`** — Deletes a role menu.
- **`/admin-roles menu edit`** — Changes title, description or behavior of an already published menu.
- **`/admin-roles menu list`** — Shows the server's role menus, with IDs.
- **`/admin-roles menu remove`** — Removes an option from a role menu.
- **`/admin-roles remove`** — Remove one or more roles from a member, also for a time.
- **`/admin-roles reset`** — Remove all roles from a member, with confirmation.
- **`/admin-roles reward add`** — Gives a role to whoever reaches a level.
- **`/admin-roles reward list`** — Shows the reward roles configured on this server.
- **`/admin-roles reward remove`** — Removes a configured reward role.
- **`/admin-roles self-roles`** — Roles members take by themselves with /utility role.

## Admin: security

- **`/admin-security alt list`** — Duplicate accounts found by web verification.
- **`/admin-security escalation disable`** — Turns the escalation ladder off.
- **`/admin-security escalation enable`** — Turns the escalation ladder on.
- **`/admin-security escalation remove-step`** — Removes a step from the custom ladder.
- **`/admin-security escalation reset`** — Resets a member's infraction count.
- **`/admin-security escalation set-reset-days`** — Days of good behaviour needed to reset the count.
- **`/admin-security escalation set-step`** — Sets the action for a step of the ladder.
- **`/admin-security escalation status`** — Shows the configured escalation ladder.
- **`/admin-security globalban check`** — How many servers in the network banned this user via Spam Trap.
- **`/admin-security globalban disable`** — Leaves the global ban network.
- **`/admin-security globalban enable`** — Joins the global ban network (send and receive).
- **`/admin-security globalban status`** — Shows the global ban status and recent history.
- **`/admin-security heatmap`** — Shows which roles have critical permissions and who holds them.
- **`/admin-security panic configura`** — Panic settings: notified roles, excluded categories, unlock, rules.
- **`/admin-security panic enable`** — Turn panic on: full lockdown with the emergency rules.
- **`/admin-security panic remove`** — Turn panic off and reopen the server as it was.
- **`/admin-security panic status`** — Show whether the server is locked and the panic settings.
- **`/admin-security score`** — Computes the server security score with advice.
- **`/admin-security spamtrap`** — Sets up the Spam Trap trap and log channels.
- **`/admin-security verify attempts`** — A user's verification attempts.
- **`/admin-security verify blacklist-add`** — Adds a user to the blacklist.
- **`/admin-security verify blacklist-remove`** — Removes a user from the blacklist.
- **`/admin-security verify manual`** — Verifies a member by hand, with no checks.
- **`/admin-security verify options`** — "Unverified" role and extra roles.
- **`/admin-security verify panel`** — Publishes the verification panel.
- **`/admin-security verify send`** — Sends a member the message to verify again.
- **`/admin-security verify setup`** — Sets up Verify.
- **`/admin-security verify statistics`** — Joins, leaves, captchas and verifications.
- **`/admin-security verify timing`** — Reminder, time limit, action on failures, verification only for suspicious accounts.
- **`/admin-security verify whitelist-add`** — Adds a user to the whitelist.
- **`/admin-security verify whitelist-remove`** — Removes a user from the whitelist.

## Admin: tickets

- **`/admin-tickets auto-close`** — Closes tickets idle for N minutes (0 = off).
- **`/admin-tickets blacklist`** — Users and roles that cannot open tickets.
- **`/admin-tickets category add`** — Adds (or updates) a ticket category.
- **`/admin-tickets category list`** — Lists the configured ticket categories.
- **`/admin-tickets category remove`** — Removes a ticket category.
- **`/admin-tickets close-all`** — Closes the open tickets (up to 25 at a time).
- **`/admin-tickets limite`** — How many open tickets each user can have at once (default 1).
- **`/admin-tickets modmail block`** — Blocks or unblocks a user from ModMail.
- **`/admin-tickets modmail enable`** — Turns ModMail (tickets in DM) on or off.
- **`/admin-tickets panel`** — Publishes the ticket opening panel in this channel.
- **`/admin-tickets panels create`** — Creates a ticket panel.
- **`/admin-tickets panels form-add`** — Adds a question to the form (max 5).
- **`/admin-tickets panels form-remove`** — Removes a question from the form.
- **`/admin-tickets panels form-show`** — Shows the questions of a panel's form.
- **`/admin-tickets panels list`** — Lists the server's ticket panels.
- **`/admin-tickets panels publish`** — Publishes the buttons of one or more panels here.
- **`/admin-tickets panels remove`** — Deletes a panel and its form.
- **`/admin-tickets reminder`** — Reminder after N minutes without staff (0 = off).
- **`/admin-tickets replies delete`** — Deletes a standard reply.
- **`/admin-tickets replies edit`** — Corrects a standard reply.
- **`/admin-tickets replies list`** — Lists the server's standard replies.
- **`/admin-tickets replies standard`** — Standard replies learned by the staff.
- **`/admin-tickets role add`** — Adds a support role.
- **`/admin-tickets role list`** — Lists the configured support roles.
- **`/admin-tickets role remove`** — Removes a support role.
- **`/admin-tickets setup`** — Sets the category (and optionally the support role) for tickets.
- **`/admin-tickets stats`** — Ticket system statistics.
- **`/admin-tickets suspend`** — Suspend ticket opening (no reason: resume).
- **`/admin-tickets vote`** — Star rating in DM at closing.

## Admin: ticket options

- **`/admin-ticket-options access`** — Who can open: per-role rules, read from the top.
- **`/admin-ticket-options alerts`** — Who to ping on opening and pinned first message.
- **`/admin-ticket-options channel`** — Channel name and fallback categories.
- **`/admin-ticket-options claiming`** — Claiming: category, exclusivity, auto-assignment.
- **`/admin-ticket-options closing`** — Confirmation before closing and who can close.
- **`/admin-ticket-options hours`** — Opening hours and what happens outside them.
- **`/admin-ticket-options limits`** — Open-ticket cap, cooldown and exempt roles.
- **`/admin-ticket-options messages`** — DMs to the user and claim/release texts.
- **`/admin-ticket-options permissions`** — User permissions, observers, roles while open, staff team.
- **`/admin-ticket-options show`** — All the options of a panel.

## Admin: temporary voice

- **`/admin-voice cap`** — Sets the maximum number of temporary voice channels per category.
- **`/admin-voice generator`** — Extra generator channels with their own rules.
- **`/admin-voice options`** — Name of new channels, lock, log, copy, panel.
- **`/admin-voice panel`** — Publishes the panel to create a voice channel by hand.
- **`/admin-voice platforms`** — Sets the PC/Console/Mobile info roles for temporary voice channels.
- **`/admin-voice setup`** — Sets the generator channel and category for temporary voice channels.

## Help (top level)

- **`/-ask`** — Ask for help: I will show you the right commands.
- **`/-search-command`** — Searches a command by description.

## iYokai App (separate app, installed on the user)

- **`/Check links`** — “Apps” menu (right click)
- **`/Clean text`** — “Apps” menu (right click)
- **`/Explain or summarize`** — “Apps” menu (right click)
- **`/Meme from this image`** — “Apps” menu (right click)
- **`/Profile`** — “Apps” menu (right click)
- **`/Quote as image`** — “Apps” menu (right click)
- **`/Remind me`** — “Apps” menu (right click)
- **`/Report to iYokai network`** — “Apps” menu (right click)
- **`/Save as saved reply`** — “Apps” menu (right click)
- **`/Save to bookmarks`** — “Apps” menu (right click)
- **`/Transcribe voice message`** — “Apps” menu (right click)
- **`/Translate`** — “Apps” menu (right click)
- **`/assistant`** — AI features for everyone: summaries, translations, images, characters
- **`/bookmarks list`** — Shows your bookmarks, newest first.
- **`/bookmarks remove`** — Removes a bookmark.
- **`/desktop alerts`** — Turns mention and reply alerts on or off.
- **`/desktop connect`** — Creates the personal code for the iYokai Desktop program.
- **`/desktop disconnect`** — Revokes the code: the program can no longer sign in.
- **`/desktop status`** — How iYokai Desktop is connected and which alerts you have.
- **`/desktop words`** — The keywords that alert you (comma separated; empty removes them).
- **`/find`** — Find an iYokai App feature: commands and message menus.
- **`/fun 8ball`** — Ask the magic 8 ball a question.
- **`/fun animal`** — Show a random animal picture.
- **`/fun choose`** — I pick at random among the options you write.
- **`/fun coin`** — Flip a coin: heads or tails.
- **`/fun dice`** — Roll a die, or a formula like 3d6+2.
- **`/fun effect`** — Avatar effect: rainbow, R.I.P., wanted, triggered.
- **`/fun fact`** — Show a random fun fact.
- **`/fun image`** — Search for a family-friendly image on Pixabay.
- **`/fun joke`** — Tell a random joke.
- **`/fun meme`** — A meme with top and bottom text, on an image or an avatar.
- **`/fun number`** — A random number in a range.
- **`/fun quote`** — Show a random quote.
- **`/fun random`** — Would you rather, topic, advice, magic item.
- **`/fun rate`** — Rate something from 0 to 10.
- **`/fun rps`** — Rock, paper, scissors against the bot.
- **`/fun ship`** — Compute the compatibility between two users.
- **`/fun text`** — Write a text in a special style.
- **`/history list`** — Your latest commands.
- **`/history reset`** — Deletes your command history.
- **`/iYokai network status`** — “Apps” menu (right click)
- **`/notes add`** — Adds a note, or an entry to a list.
- **`/notes list`** — Shows your notes, or a list.
- **`/notes remove`** — Removes a note or a list entry.
- **`/playlist add`** — Adds a track to one of your playlists.
- **`/playlist create`** — Creates an empty playlist.
- **`/playlist delete`** — Deletes one of your playlists.
- **`/playlist list`** — Your playlists.
- **`/playlist remove`** — Removes a track from one of your playlists.
- **`/playlist show`** — Shows the tracks of one of your playlists.
- **`/profile`** — A user's card: name, ID, account age, level, clan, avatar.
- **`/radio now`** — What plays now on the iYokai radio, with a lyrics search link.
- **`/reminders cancel`** — Cancels one of your reminders.
- **`/reminders create`** — I will DM you after the time you choose.
- **`/reminders list`** — Shows your pending reminders.
- **`/saved-reply list`** — Your saved replies.
- **`/saved-reply remove`** — Removes a saved reply.
- **`/saved-reply save`** — Save a reply (text, or embed with title, color and image).
- **`/saved-reply use`** — Posts one of your saved replies as an app reply.
- **`/settings dm`** — Can the app DM you (reminders, remind me)?
- **`/settings history`** — Save your latest commands (turning it off deletes the history).
- **`/settings language`** — Italian or English for the replies only you see.
- **`/settings profile`** — Others see your global profile (level, clans, medals).
- **`/settings replies`** — Command replies are seen only by you, or by everyone.
- **`/settings show`** — Your current settings.
- **`/strumenti calcola`** — Calculates an expression, e.g. (2+3)*4 or sqrt(16).
- **`/strumenti colore`** — Shows a colour in HEX, RGB and HSL.
- **`/strumenti converti`** — Converts lengths, weights, volumes, speeds, data and temperatures.
- **`/strumenti fuso`** — What time it is in another time zone.
- **`/strumenti qr`** — Makes a QR code from a text or link.
- **`/support list`** — Your latest support requests.
- **`/support open`** — Open a support request with the iYokai staff.
- **`/support reply`** — Write to the staff in your open request.

## iYokai NSFW (separate app, age-restricted channels only)

- **`/nsfw search`** — Posts here a piece of content with a tag allowed by the server.
- **`/nsfw-admin autopost`** — Posts automatically in an age-restricted channel.
- **`/nsfw-admin autopost-stop`** — Stops automatic posting (empty: all of them).
- **`/nsfw-admin enable`** — Turns the NSFW instance on or off in this server.
- **`/nsfw-admin status`** — Shows the NSFW settings of this server.
- **`/nsfw-admin tag-add`** — Adds a tag to the server allowlist.
- **`/nsfw-admin tag-remove`** — Removes a tag from the server allowlist.

## AI assistant

- **`/assistant alert`** — Follow up to 3 words: I notify you when they are discussed a lot.
- **`/assistant character`** — Talk to a server AI character.
- **`/assistant create-character`** — Creates an AI character to chat with.
- **`/assistant explain`** — Explains a message in simple words (from its link).
- **`/assistant fragments`** — The lore fragments you collected.
- **`/assistant imagine`** — Generates an image from a description.
- **`/assistant lore`** — Lore card about a name, a place or a yokai.
- **`/assistant mystery`** — Answer a server mystery with the code.
- **`/assistant pack`** — Buy 5 extra AI images with server coins.
- **`/assistant preference`** — Your AI choices: replies for you and a style others may imitate.
- **`/assistant speak`** — Yokai says a phrase out loud in this channel.
- **`/assistant spirit`** — Your Yokai spirit: an affinity that grows with your activity.
- **`/assistant style`** — A new message written like you write (or like someone who allows it).
- **`/assistant summarize`** — Summary of the latest messages of a channel.
- **`/assistant translate`** — Translates a text into the language you choose.
- **`/assistant upscale`** — Upscales and cleans up an image you upload.

## Clan

- **`/clan boost guild`** — Buys a x2 boost for 24h for ALL members, from the treasury.
- **`/clan boost individual`** — Buys a personal x2 boost for 24h on your guild voice tick.
- **`/clan buy-channel`** — Unlocks a new extra channel for your guild.
- **`/clan create`** — Creates a new guild/clan.
- **`/clan disband`** — Disbands your guild.
- **`/clan expel`** — Expels a member from your guild.
- **`/clan info`** — Shows a guild's information.
- **`/clan invite`** — Invites a member to your guild.
- **`/clan leaderboard`** — Guild leaderboard by XP (monthly or total).
- **`/clan leave`** — Leaves the guild you belong to.
- **`/clan members`** — Shows a guild's members.
- **`/clan promote`** — Changes the role of a member of your guild.
- **`/clan treasury donate`** — Donates personal coins to your guild's treasury.
- **`/clan treasury transfer`** — Moves coins from the treasury to another guild of YOURS (even on another server).

## Founder (server owner)

- **`/founder backup permissions`** — Who can create and who can load backups (owner only).
- **`/founder backup sync`** — Keeps bans and roles equal with another server of yours.
- **`/founder moderation immune`** — Roles manual moderation can't touch (owner only).

## Fun

- **`/fun 8ball`** — Ask the magic 8-ball a question.
- **`/fun choose`** — I pick at random among the options you write.
- **`/fun coinflip`** — Flips a coin: heads or tails.
- **`/fun dice`** — Rolls a die.
- **`/fun fact`** — Shows a random fun fact.
- **`/fun joke`** — Tells a random joke.
- **`/fun measure`** — Measures from 0 to 100% how much of something you choose.
- **`/fun number`** — A random number in a range.
- **`/fun prank`** — A harmless prank on a user.
- **`/fun quote`** — Shows a random quote.
- **`/fun random`** — Would you rather, topic, advice, magic item.
- **`/fun rate`** — Rates something from 0 to 10.
- **`/fun ship`** — Computes the compatibility between two users.
- **`/fun text`** — Write a text in a special style.

## Games

- **`/games play`** — Play your coins: coin flip, dice or slots.
- **`/games rps`** — Rock, paper, scissors against the bot.

## Images

- **`/images animal`** — Shows a random animal picture.
- **`/images blur`** — Blurs an image.
- **`/images effect`** — Avatar effect: rainbow, R.I.P., wanted, triggered.
- **`/images grayscale`** — Turns an image to grayscale.
- **`/images invert`** — Inverts an image's colors.
- **`/images meme`** — Makes a meme with top/bottom text.
- **`/images pixelate`** — Pixelates an image.
- **`/images search-image`** — Searches a SFW image on Pixabay.

## Levels

- **`/level birthday remove`** — Deletes your birthday.
- **`/level birthday set`** — Saves your birthday (day and month only).
- **`/level birthday show`** — Shows the birthday you saved.
- **`/level calcola`** — How many messages or voice minutes are missing to reach a level.
- **`/level collection buy`** — Buys a badge or background with your coins.
- **`/level collection equip`** — Puts a badge or background on your profile (no item removes it).
- **`/level collection shop`** — Shows badges and backgrounds on sale and the ones you own.
- **`/level invites history`** — Who invited a member and the last people they brought in.
- **`/level invites leaderboard`** — The 10 members who invited the most people.
- **`/level invites link`** — Your personal invite link, served through the bot's website.
- **`/level invites user`** — How many people a member invited.
- **`/level leaderboard`** — Shows the server leaderboard.
- **`/level profile`** — Shows a member's profile; with "presentazione" you change yours.
- **`/level progress`** — Missions, streaks, achievements and the 90-day pass, in a menu.
- **`/level rank`** — Shows the rank card: level, XP, position and coins.
- **`/level recent-levels`** — The last 25 level-ups in the server.
- **`/level rewards`** — Shows level reward roles and active XP multipliers.

## Mod: bans

- **`/mod-ban appeals channel`** — Picks the staff channel for appeals (empty to turn them off).
- **`/mod-ban appeals list`** — Shows the server's latest appeals.
- **`/mod-ban ban`** — Permanently bans a member.
- **`/mod-ban bulk ban`** — Bans several users at once, even outside the server (IDs or mentions).
- **`/mod-ban bulk kick`** — Kicks several members at once (IDs or mentions).
- **`/mod-ban bulk unban`** — Unbans several users at once (IDs).
- **`/mod-ban kick`** — Kicks a member from the server.
- **`/mod-ban softban`** — Bans and unbans a member right away, to delete their recent messages.
- **`/mod-ban tempban`** — Bans a member for a set time.
- **`/mod-ban unban`** — Removes a user's ban.

## Mod: channels

- **`/mod-channels clear`** — Deletes a number of messages, with optional filters.
- **`/mod-channels lock`** — Blocks the ability to write in a channel.
- **`/mod-channels lockdown enable`** — Lock all channels, invites and joins of the server.
- **`/mod-channels lockdown remove`** — Reopen the server as it was before the lockdown.
- **`/mod-channels reazioni`** — Removes reactions from the latest messages of a channel, without deleting them.
- **`/mod-channels slowmode`** — Sets slowmode on a channel.
- **`/mod-channels unlock`** — Unblocks the ability to write in a channel.

## Mod: cases and notes

- **`/mod-cases alerts azzera-tutti`** — Removes the active warns of the whole server (needs Manage Server).
- **`/mod-cases alerts leaderboard`** — Members with the most active warnings.
- **`/mod-cases alerts list`** — All active warns in the server, in pages.
- **`/mod-cases alerts remove`** — Removes a single warning (by case number).
- **`/mod-cases alerts reset`** — Removes all of a member's active warnings (needs "Manage Server").
- **`/mod-cases case active`** — Sanctions still running: tempbans, timeouts, mutes, timed locks.
- **`/mod-cases case delete`** — Deletes a case (needs "Manage Server").
- **`/mod-cases case durata`** — Changes the duration of a tempban, timeout or mute still in progress.
- **`/mod-cases case export`** — Sends a member's cases and notes in a text file.
- **`/mod-cases case hide`** — Hides a case (it stops counting in rankings and alerts) or restores it.
- **`/mod-cases case history`** — Shows a member's case history.
- **`/mod-cases case reason`** — Changes the reason of an already logged case.
- **`/mod-cases case record`** — Logs a case without taking the action (sanction given outside the bot).
- **`/mod-cases case staff-leaderboard`** — Moderator leaderboard by number of actions, or one moderator's cases.
- **`/mod-cases case view`** — Shows the details of a single case.
- **`/mod-cases note add`** — Adds a note on a user.
- **`/mod-cases note clear`** — Deletes all of a member's notes (needs "Manage Server").
- **`/mod-cases note edit`** — Changes a note's text.
- **`/mod-cases note list`** — Lists the notes on a user.
- **`/mod-cases note remove`** — Removes a note (the number is in the notes list).
- **`/mod-cases risk`** — A member's risk score, with the reasons. Only an aid to decide.
- **`/mod-cases workload`** — Staff workload and proposed shifts. Admins only, never public.

## Mod: sanctions

- **`/mod-sanctions bulk timeout`** — Times out several members at once (max 28 days).
- **`/mod-sanctions bulk warn`** — Warns several members at once.
- **`/mod-sanctions mute`** — Mutes a member with a dedicated role (alternative to timeout).
- **`/mod-sanctions options dm`** — Choose whether the user gets a DM for a type of action.
- **`/mod-sanctions options set`** — Ban message cleanup, timeout, external cases, alerts. Empty: shows the options.
- **`/mod-sanctions timeout`** — Times out a member (max 28 days).
- **`/mod-sanctions unmute`** — Removes the mute role from a member.
- **`/mod-sanctions untimeout`** — Removes a member's timeout.
- **`/mod-sanctions warn`** — Gives a member a warning.

## Coins

- **`/coins balance`** — Shows your coins.
- **`/coins cashbox`** — Shows the server treasury balance.
- **`/coins cooldowns`** — When you can use daily and work again.
- **`/coins daily`** — Claims the daily reward.
- **`/coins pay`** — Transfers coins to another user.
- **`/coins shop buy`** — Buys a shop item.
- **`/coins shop list`** — Shows the items available in the shop.
- **`/coins work`** — Work to earn some coins.

## Music

- **`/music clear-queue`** — Clears the queue without touching the track that is playing.
- **`/music disconnect`** — Disconnects the music bot from the voice channel.
- **`/music history`** — Shows the latest tracks already played.
- **`/music join`** — Makes the music bot join your channel without playing.
- **`/music loop queue`** — Turns repeat of the whole queue on or off.
- **`/music loop track`** — Turns repeat of the current track on or off.
- **`/music nonstop off`** — Turns off the continuous loop.
- **`/music nonstop on`** — Turns on the continuous loop on the current queue.
- **`/music nowplaying`** — Shows the playing track with a progress bar.
- **`/music pause`** — Pauses playback.
- **`/music play`** — Plays a song or playlist.
- **`/music playlist delete`** — Deletes one of your saved playlists.
- **`/music playlist export`** — Downloads one of your playlists as a file.
- **`/music playlist import`** — Saves a playlist from an exported file.
- **`/music playlist list`** — Your saved playlists.
- **`/music playlist load`** — Queues one of your saved playlists.
- **`/music playlist save`** — Saves your channel's queue as a playlist.
- **`/music previous`** — Goes back to the previous track.
- **`/music queue`** — Shows the playback queue.
- **`/music resume`** — Resumes paused playback.
- **`/music shuffle`** — Shuffles the order of the queued tracks.
- **`/music skip`** — Skips the track that is playing.
- **`/music skipto`** — Jumps straight to track number N of the queue.
- **`/music sound`** — Plays a sound effect in your voice channel.
- **`/music stop`** — Stops playback and clears the queue.
- **`/music volume down`** — Lowers the volume.
- **`/music volume set`** — Sets the volume to a specific value (0-200).
- **`/music volume up`** — Raises the volume.

## Owner

- **`/owner ai maintenance`** — Owner only: puts the AI in maintenance in every server.
- **`/owner ai network-boss`** — Owner only: publish or close the network boss.
- **`/owner ai template`** — Owner only: a provider model, tier and job types; length cap.
- **`/owner blacklist server-add`** — Globally blocks a server (the bot leaves if already there).
- **`/owner blacklist server-list`** — Shows the globally blocked servers.
- **`/owner blacklist server-remove`** — Removes a server from the global blacklist.
- **`/owner blacklist utente-add`** — Globally blocks a user from using the bot.
- **`/owner blacklist utente-list`** — Shows the globally blocked users.
- **`/owner blacklist utente-remove`** — Removes a user from the global blacklist.
- **`/owner cog load`** — Loads an extension (e.g. cogs.moderation.actions).
- **`/owner cog reload`** — Reloads an extension, optionally updating it from GitHub or a file.
- **`/owner cog unload`** — Unloads an extension.
- **`/owner hate-words`** — Bot owner only: the worldwide library of hate words.
- **`/owner immagini-trappola`** — Bot owner only: the shared library of trap images.
- **`/owner premium grant`** — Grants premium to a server, or creates a code to redeem.
- **`/owner premium list`** — Shows the premium status of all modules.
- **`/owner premium panel`** — Interactive panel to turn premium modules on or off.
- **`/owner premium revoke`** — Revokes a module's subscription for a server.
- **`/owner premium status-all`** — Shows the premium status of ALL servers the bot is in.
- **`/owner premium subscriptions`** — Shows the active per-module subscriptions on a server.
- **`/owner premium toggle`** — Turns a module's premium nature on or off.
- **`/owner premium whitelist-add`** — Adds a server to the premium whitelist.
- **`/owner premium whitelist-list`** — Lists the servers in the premium whitelist.
- **`/owner premium whitelist-remove`** — Removes a server from the premium whitelist.
- **`/owner privacy approva`** — Runs a deletion request and notifies the user.
- **`/owner privacy richieste`** — Lists the pending data deletion requests.
- **`/owner privacy rifiuta`** — Rejects a deletion request and tells the user why.
- **`/owner radio add-local`** — Adds a file from the unreleased folder to the radio playlist.
- **`/owner radio add-track`** — Adds a track to the radio playlist.
- **`/owner radio list-tracks`** — Shows the radio playlist.
- **`/owner radio remove-track`** — Removes a track from the radio playlist.
- **`/owner radio start`** — Joins the shared radio at the point where it is now.
- **`/owner radio stop`** — Leaves the radio on this server.
- **`/owner system announce`** — Sends an announcement to all servers.
- **`/owner system eval`** — Runs Python code (with confirmation).
- **`/owner system leave-guild`** — Forces the bot to leave a specific server (without blocking it).
- **`/owner system memory-status`** — Shows the process's current RAM use.
- **`/owner system richieste-canale`** — Sets the requests channel (main server only).
- **`/owner system shell`** — Runs a shell command (with confirmation).
- **`/owner system stats`** — Global bot statistics.
- **`/owner system storico-vpn`** — Bot owner only: servers that let a person through despite a VPN/proxy flag.

## Polls

- **`/polls create`** — Creates a poll (up to 10 options).

## Tickets

- **`/ticket add`** — Adds a user or role to this ticket.
- **`/ticket ask-close`** — Ask the user whether the ticket can be closed.
- **`/ticket assistant`** — AI assistant answer (for staff: draft and triage).
- **`/ticket claim`** — Takes charge of this ticket.
- **`/ticket close`** — Closes this ticket.
- **`/ticket dm-close`** — Closes this ModMail conversation.
- **`/ticket forceclose`** — Closes this ticket immediately, with no wait.
- **`/ticket notes`** — Private staff thread to discuss the ticket.
- **`/ticket on-call`** — Join or leave the staff notified on every new ticket.
- **`/ticket open`** — Open a ticket (staff also for a user or from a message).
- **`/ticket pass`** — Hands the ticket over to a colleague.
- **`/ticket priority`** — Sets this ticket's priority.
- **`/ticket release`** — Gives up taking charge of this ticket.
- **`/ticket remove`** — Removes a user or role from this ticket.
- **`/ticket rename`** — Renames this ticket.
- **`/ticket reply`** — Replies to the user of this ModMail conversation.
- **`/ticket reset-cooldown`** — Remove a user's cooldown between tickets.
- **`/ticket riapri`** — Reopens this closed ticket (if the panel keeps the channel).
- **`/ticket transcript`** — Get the transcript without closing the ticket.

## Utility

- **`/utility form`** — Fills in a form or application of this server.
- **`/utility info`** — Bot information: version, invite and support.
- **`/utility language`** — Shows or changes your personal language (Italian or English).
- **`/utility lookup channel`** — Channel card.
- **`/utility lookup members`** — Members who have a role.
- **`/utility lookup permissions`** — Permissions of a member or the bot in a channel.
- **`/utility lookup role`** — Role card: members, color, date, permissions.
- **`/utility lookup roles`** — All roles with ID, members and color.
- **`/utility lookup seniority`** — Oldest or newest accounts, first or last to join.
- **`/utility lookup server`** — Server card: owner, date, numbers, boosts.
- **`/utility lookup user`** — Member card: ID, dates and roles.
- **`/utility ping`** — Checks whether iYokai Main is online and its latency.
- **`/utility privacy cancella`** — Request the deletion of your personal data.
- **`/utility privacy export`** — Get a copy of the data the bot keeps about you.
- **`/utility reminder cancel`** — Cancel a reminder, or all of yours.
- **`/utility reminder list`** — Shows your pending reminders.
- **`/utility reminder set`** — Sets a reminder.
- **`/utility report`** — Reports a user to the server staff.
- **`/utility request-command`** — Suggests a new command for the bot.
- **`/utility role`** — Take or leave the server's self-assignable roles.
- **`/utility serverstats`** — Shows the server statistics, with a growth chart.
- **`/utility snipe edit`** — Shows the last edited message in this channel.
- **`/utility snipe message`** — Shows the last deleted message in this channel.
- **`/utility snipe reaction`** — Shows the last removed reaction in this channel.
- **`/utility suggest`** — Suggest an idea for this server.
- **`/utility tag`** — Uses a custom command of this server.
- **`/utility verify`** — Verify yourself in this server (same as the panel button).

## Voice

- **`/voice bitrate`** — Sets the channel's audio quality (kbps).
- **`/voice claim`** — Takes the channel if the owner is gone.
- **`/voice deny`** — Forbids a user from joining the channel.
- **`/voice hide`** — Hides or shows the channel to people who are not in it.
- **`/voice invite`** — Sends a user an invite to your channel.
- **`/voice kick`** — Kicks a user from your channel.
- **`/voice limit`** — Sets the channel's user limit.
- **`/voice lock`** — Locks the channel (no new joins).
- **`/voice permit`** — Lets a user join even if the channel is locked.
- **`/voice rename`** — Renames your voice channel.
- **`/voice status`** — Writes what you are doing in the channel (empty: removes it).
- **`/voice transfer`** — Transfers the channel's ownership.
- **`/voice unlock`** — Unlocks the channel.
