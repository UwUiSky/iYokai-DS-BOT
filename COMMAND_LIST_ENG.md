# Command list (English) — iYokai

Generated automatically by `scripts/generate_command_list.py` on 2026-10-27 21:51 UTC from the REAL command tree. English names and descriptions are the ones Discord shows to users with the client in English (`locales/comandi.en.json`); the base names in the code are Italian. Regenerate after every commit that adds, removes or renames a command.

**Total: 548 commands in 25 categories.**

## Admin

- **`/admin config bot-nickname`** — Changes the bot's name in this server.
- **`/admin config cleanup`** — Removes channels and roles that no longer exist from the settings.
- **`/admin config export`** — Exports this server's configuration to a file.
- **`/admin config history`** — Shows the latest configuration changes.
- **`/admin config import`** — Imports a configuration from a file exported with /admin config export.
- **`/admin config report-channel`** — Sets the reports channel.
- **`/admin config reset`** — Resets this server's configuration.
- **`/admin config rollback`** — Restores the previous value of a change.
- **`/admin config suggestions-channel`** — Sets the suggestions channel.
- **`/admin config sync`** — Rewrites this server's command permissions.
- **`/admin language set`** — Sets this server's language.
- **`/admin language show`** — Shows the language set for this server.
- **`/admin messages cancel`** — Cancels a scheduled message.
- **`/admin messages schedule`** — Schedules a message.
- **`/admin messages scheduled`** — Shows this server's scheduled messages.
- **`/admin messages sticky-set`** — Sets a channel's sticky message.
- **`/admin messages sticky-togli`** — Removes a channel's sticky message.
- **`/admin music request-channel`** — Channel where typing a title queues it, with the player.
- **`/admin music settings`** — Changes the server's music settings.
- **`/admin music summary`** — Shows all the server's music settings.
- **`/admin premium appearance`** — The bot's avatar, banner and description in this server (premium).
- **`/admin premium branding`** — Use a bot with your own name and avatar (premium).
- **`/admin premium redeem`** — Redeems a premium code for this server.
- **`/admin premium status`** — Shows how premium is unlocked in this server.
- **`/admin setup enable`** — Turns the bot's modules on or off, by category.
- **`/admin setup wizard`** — Step-by-step setup of the bot's main modules.
- **`/admin ticket auto-close`** — Closes tickets idle for N minutes (0 = off).
- **`/admin ticket close-all`** — Closes the open tickets (up to 25 at a time).
- **`/admin ticket dm`** — Turns ModMail (tickets in DM) on or off.
- **`/admin ticket dm-block`** — Blocks or unblocks a user from ModMail.
- **`/admin ticket form-add`** — Adds a question to the form (max 5).
- **`/admin ticket form-remove`** — Removes a question from the form.
- **`/admin ticket form-show`** — Shows the questions of a panel's form.
- **`/admin ticket panel-create`** — Creates a ticket panel.
- **`/admin ticket panel-list`** — Lists the server's ticket panels.
- **`/admin ticket panel-publish`** — Publishes the buttons of one or more panels here.
- **`/admin ticket panel-remove`** — Deletes a panel and its form.
- **`/admin ticket reminder`** — Reminder after N minutes without staff (0 = off).
- **`/admin ticket replies-list`** — Lists the server's standard replies.
- **`/admin ticket reply-delete`** — Deletes a standard reply.
- **`/admin ticket reply-edit`** — Corrects a standard reply.
- **`/admin ticket standard`** — Standard replies learned by the staff.
- **`/admin ticket vote`** — Star rating in DM at closing.

## Ai

- **`/ai banned-words`** — Words or topics the AI must refuse.
- **`/ai build`** — The AI suggests roles and channels from a description; you confirm.
- **`/ai channel`** — Turns the AI off or back on in a channel.
- **`/ai character`** — Installs, removes or deletes a server AI character.
- **`/ai enable`** — Turns the AI on or off in the server (consent required).
- **`/ai features`** — Turns on automatic features: reply to mentions, flags.
- **`/ai knowledge add`** — Adds an entry to the knowledge base.
- **`/ai knowledge list`** — The knowledge base entries.
- **`/ai knowledge remove`** — Removes an entry from the knowledge base.
- **`/ai limits`** — Spending cap and quotas: per user, per feature, images.
- **`/ai lore`** — Server tone and setting used in every AI text.
- **`/ai moderation`** — The AI flags suspicious messages of a channel to the staff.
- **`/ai privacy`** — User messages sent to the AI, memory and answer length.
- **`/ai status`** — AI status in the server: providers, settings and monthly usage.
- **`/ai translation`** — Automatically translates every message of a channel.

## Help (top level)

- **`/-ask`** — Ask for help: I will show you the right commands.
- **`/-search-command`** — Searches a command by description.

## Antinuke

- **`/antinuke canale-allarmi`** — Choose where Anti-Nuke alarms are sent (channel or forum).
- **`/antinuke cases`** — Log of stopped attacks: list or detail of a case.
- **`/antinuke enable`** — Turns Anti-Nuke on or off.
- **`/antinuke guards`** — Guards on single actions: role permissions, roles to members, links, bots.
- **`/antinuke limits`** — Sets the detection threshold for a category.
- **`/antinuke punish-action`** — What to do to the author of a mass destructive action.
- **`/antinuke recovery`** — Turns automatic re-creation of channels/roles deleted during an attack on or off.
- **`/antinuke release`** — Lifts the quarantine of a case's author and gives their roles back.
- **`/antinuke status`** — Shows the current Anti-Nuke setup.
- **`/antinuke trusted-add`** — Exempts a user, bot or webhook from Anti-Nuke checks.
- **`/antinuke trusted-list`** — Lists who is exempt from Anti-Nuke checks and with which limits.
- **`/antinuke trusted-remove`** — Removes a user, bot or webhook from the Anti-Nuke trusted list.

## Antiraid

- **`/antiraid account-age`** — Minimum account age to not be considered suspicious.
- **`/antiraid alert-channel`** — Channel for security alerts (Anti-Raid + Anti-Nuke).
- **`/antiraid avatar-check`** — Turns missing-avatar detection on or off.
- **`/antiraid banned-names`** — Words or patterns (with *) banned in the names of new members.
- **`/antiraid enable`** — Turns Anti-Raid on or off.
- **`/antiraid join-filter`** — Action for a join filter (works outside a raid too).
- **`/antiraid join-rate`** — Sets the join limit in a time window.
- **`/antiraid list`** — File with every raid account from the last hours.
- **`/antiraid lockdown-action`** — What to do when a raid is detected.
- **`/antiraid ping-roles`** — Staff roles pinged on the first raid alert (empty: none).
- **`/antiraid quarantine-hold`** — Stops untrusted people from lifting quarantine by hand.
- **`/antiraid release`** — Lifts a member's quarantine (the right way, with the lock on).
- **`/antiraid report`** — Report an undetected raid to the bot team.
- **`/antiraid signals`** — Raid signals on the latest joins and action on earlier joiners.
- **`/antiraid status`** — Shows the current Anti-Raid setup.
- **`/antiraid username-check`** — Turns suspicious username pattern detection on or off.

## iYokai App (separate app, installed on the user)

- **`/Clean text`** — “Apps” menu (right click)
- **`/Profile`** — “Apps” menu (right click)
- **`/profile`** — A user's card: name, ID, account age, avatar.
- **`/reminders cancel`** — Cancels one of your reminders.
- **`/reminders create`** — I will DM you after the time you choose.
- **`/reminders list`** — Shows your pending reminders.

## iYokai NSFW (separate app, age-restricted channels only)

- **`/nsfw search`** — Posts here a piece of content with a tag allowed by the server.
- **`/nsfw-admin autopost`** — Posts automatically in an age-restricted channel.
- **`/nsfw-admin autopost-stop`** — Stops automatic posting (empty: all of them).
- **`/nsfw-admin enable`** — Turns the NSFW instance on or off in this server.
- **`/nsfw-admin status`** — Shows the NSFW settings of this server.
- **`/nsfw-admin tag-add`** — Adds a tag to the server allowlist.
- **`/nsfw-admin tag-remove`** — Removes a tag from the server allowlist.

## AutoMod

- **`/automod exemptions channel-add`** — Exempts a channel from all advanced AutoMod filters.
- **`/automod exemptions channel-remove`** — Removes a channel's exemption.
- **`/automod exemptions role-add`** — Exempts a role from all advanced AutoMod filters.
- **`/automod exemptions role-remove`** — Removes a role's exemption.
- **`/automod filters actions-set`** — Sets which actions run when an advanced filter triggers.
- **`/automod filters anti-attachment`** — Configures anti attachment-spam (too many attachments in a short time).
- **`/automod filters anti-caps`** — Configures anti-caps (too many capital letters).
- **`/automod filters anti-link-domain`** — Adds or removes a domain from the link whitelist/blacklist.
- **`/automod filters anti-link-mode`** — Sets the link filter mode.
- **`/automod filters anti-mention`** — Configures anti mass-mention (too many users tagged in one message).
- **`/automod filters anti-spam-emoji`** — Configures emoji anti-spam (too many emoji in one message).
- **`/automod filters anti-spam-messages`** — Configures message anti-spam (too many messages in a short time).
- **`/automod filters anti-spam-sticker`** — Configures sticker anti-spam (too many stickers in a short time).
- **`/automod filters anti-zalgo`** — Turns anti-zalgo on or off (text with abnormal diacritics).
- **`/automod filters content`** — Embeds and forwards checked by filters; banned file types.
- **`/automod filters invites`** — Turns the automatic Discord invite block on or off.
- **`/automod filters media-channel`** — Media-only channel, no attachments or normal.
- **`/automod filters messages`** — Repeated, too short, links and mentions counted over time (0 = off).
- **`/automod filters phishing`** — Turn the phishing link block on or off (fake gifts, fake logins).
- **`/automod filters text-shape`** — Limits on message shape: line breaks, length, spoilers (0 = off).
- **`/automod log-channel`** — Sets the channel for the advanced AutoMod action log.
- **`/automod mute-duration`** — Sets the timeout length used by the AutoMod 'mute' action.
- **`/automod status`** — Shows the current advanced AutoMod filter setup.
- **`/automod sync`** — Forces a manual sync of the AutoMod rules.
- **`/automod words add`** — Adds a banned word.
- **`/automod words list`** — Shows the configured banned words.
- **`/automod words remove`** — Removes a banned word.

## Backup

- **`/backup cancel`** — Stops the running load (what is done stays).
- **`/backup chat-load`** — Loads a saved chat into a channel, even a different one.
- **`/backup chat-save`** — Saves the latest messages of a channel (up to 1000) to load them later.
- **`/backup copy-channel`** — Copies a channel with its permissions; a category with its channels.
- **`/backup copy-role`** — Copies a role with its permissions and, optionally, its channel permissions.
- **`/backup create`** — Prepares the backup: link code and link for the new server.
- **`/backup delete`** — Deletes a saved copy.
- **`/backup export`** — Exports structure, channels, roles, bans or reactions to a file.
- **`/backup import`** — Imports the structure from a JSON file, picking what to apply.
- **`/backup link`** — Links THIS server as backup, with the code received from the main server.
- **`/backup list`** — The saved copies of this server, with their date.
- **`/backup load`** — Loads a saved copy into this server, picking the parts.
- **`/backup log`** — Who used backups, templates and syncs (last 20, 365 days).
- **`/backup main`** — Registers this server as 'main' for the Backup System.
- **`/backup permissions`** — Who can create and who can load backups (owner only).
- **`/backup promote`** — Promotes THIS server (so far a backup) to new main, if the original main is lost.
- **`/backup restore-modo`** — Picks how this server handles user restore via OAuth2.
- **`/backup restore-utenti`** — Restores into THIS server the users of another server's latest snapshot.
- **`/backup save`** — Saves a dated copy of this server structure.
- **`/backup status`** — Progress of the latest load in this server.
- **`/backup sync`** — Keeps bans and roles equal with another server of yours.
- **`/backup template`** — Templates: share a copy with a code or load another server one.

## Clan

- **`/clan board disable`** — Turns off the automatic top 3 guilds announcement.
- **`/clan board set`** — Sets the channel for the monthly top 3 guilds announcement.
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

## Economy

- **`/economy award-lobby`** — Participation prize: gives coins to those in voice NOW, from the server treasury.
- **`/economy award-winner`** — Winner prize: gives coins to a member, from the server treasury.
- **`/economy coins`** — Edits a member's balance.
- **`/economy giveaway`** — Starts a giveaway.
- **`/economy giveaway-modello`** — Giveaway templates: save, list, delete, start.
- **`/economy giveaway-programmati`** — Scheduled giveaways: list (including failed ones) or cancel.
- **`/economy premium-cashbox`** — Unlocks one month of premium bot by spending from the treasury.
- **`/economy shop-add`** — Adds an item to the shop.
- **`/economy shop-edit`** — Edits a shop item (price, stock, required role...).
- **`/economy shop-remove`** — Removes an item from the shop.
- **`/economy winners-off`** — Turns off the monthly winners announcement.
- **`/economy winners-set`** — Sets the channel for the monthly winners announcement.
- **`/economy xp`** — Edits a member's XP and level.

## Fun

- **`/fun 8ball`** — Ask the magic 8-ball a question.
- **`/fun animal`** — Shows a random animal picture.
- **`/fun blur`** — Blurs an image.
- **`/fun choose`** — I pick at random among the options you write.
- **`/fun coinflip`** — Flips a coin: heads or tails.
- **`/fun counting`** — Counting game: pick the channel where people count 1, 2, 3... in turn.
- **`/fun dice`** — Rolls a die.
- **`/fun effect`** — Avatar effect: rainbow, R.I.P., wanted, triggered.
- **`/fun fact`** — Shows a random fun fact.
- **`/fun grayscale`** — Turns an image to grayscale.
- **`/fun invert`** — Inverts an image's colors.
- **`/fun joke`** — Tells a random joke.
- **`/fun measure`** — Measures from 0 to 100% how much of something you choose.
- **`/fun meme`** — Makes a meme with top/bottom text.
- **`/fun number`** — A random number in a range.
- **`/fun pixelate`** — Pixelates an image.
- **`/fun play`** — Play your coins: coin flip, dice or slots.
- **`/fun prank`** — A harmless prank on a user.
- **`/fun quote`** — Shows a random quote.
- **`/fun random`** — Would you rather, topic, advice, magic item.
- **`/fun rate`** — Rates something from 0 to 10.
- **`/fun rps`** — Rock, paper, scissors against the bot.
- **`/fun search-image`** — Searches a SFW image on Pixabay.
- **`/fun ship`** — Computes the compatibility between two users.
- **`/fun text`** — Write a text in a special style.

## Management

- **`/management roles auto-add`** — Adds a role given automatically to new members.
- **`/management roles auto-list`** — Shows the server's automatic roles.
- **`/management roles auto-remember`** — Gives roles back to people who leave and rejoin within a set time.
- **`/management roles auto-remove`** — Removes a role given automatically to new members.
- **`/management roles auto-sync`** — Give the automatic roles to members already in the server too.
- **`/management roles level-add`** — Gives a role to whoever reaches a level.
- **`/management roles level-list`** — Shows the reward roles configured on this server.
- **`/management roles level-remove`** — Removes a configured reward role.
- **`/management roles menu-access`** — Limits a menu to certain roles or excludes others.
- **`/management roles menu-add`** — Adds an option to a role menu.
- **`/management roles menu-create`** — Creates a new role menu.
- **`/management roles menu-delete`** — Deletes a role menu.
- **`/management roles menu-edit`** — Changes title, description or behavior of an already published menu.
- **`/management roles menu-list`** — Shows the server's role menus, with IDs.
- **`/management roles menu-remove`** — Removes an option from a role menu.
- **`/management ticket category-add`** — Adds (or updates) a ticket category.
- **`/management ticket category-list`** — Lists the configured ticket categories.
- **`/management ticket category-remove`** — Removes a ticket category.
- **`/management ticket limite`** — How many open tickets each user can have at once (default 1).
- **`/management ticket panel`** — Publishes the ticket opening panel in this channel.
- **`/management ticket role-list`** — Lists the configured support roles.
- **`/management ticket ruolo-add`** — Adds a support role.
- **`/management ticket ruolo-remove`** — Removes a support role.
- **`/management ticket setup`** — Sets the category (and optionally the support role) for tickets.
- **`/management ticket stats`** — Ticket system statistics.
- **`/management voice cap`** — Sets the maximum number of temporary voice channels per category.
- **`/management voice options`** — Name of new channels, channels born locked, log channel.
- **`/management voice panel`** — Publishes the panel to create a voice channel by hand.
- **`/management voice platforms`** — Sets the PC/Console/Mobile info roles for temporary voice channels.
- **`/management voice setup`** — Sets the generator channel and category for temporary voice channels.
- **`/management welcome boost`** — Sets up the boost message.
- **`/management welcome extra`** — Welcome: DM text, variants, reactions, ban message.
- **`/management welcome goodbye`** — Sets up the goodbye message.
- **`/management welcome image`** — Adds to the welcome an image with the member's avatar, name and number.
- **`/management welcome preview`** — Shows a preview of how a message would look.
- **`/management welcome welcome`** — Sets up the welcome message.

## Levels

- **`/level balance`** — Shows your coins.
- **`/level birthday remove`** — Deletes your birthday.
- **`/level birthday set`** — Saves your birthday (day and month only).
- **`/level birthday show`** — Shows the birthday you saved.
- **`/level calcola`** — How many messages or voice minutes are missing to reach a level.
- **`/level cashbox`** — Shows the server treasury balance.
- **`/level collection buy`** — Buys a badge or background with your coins.
- **`/level collection equip`** — Puts a badge or background on your profile (no item removes it).
- **`/level collection shop`** — Shows badges and backgrounds on sale and the ones you own.
- **`/level cooldowns`** — When you can use daily and work again.
- **`/level daily`** — Claims the daily reward.
- **`/level invites leaderboard`** — The 10 members who invited the most people.
- **`/level invites user`** — How many people a member invited.
- **`/level leaderboard`** — Shows the server leaderboard.
- **`/level pay`** — Transfers coins to another user.
- **`/level profile`** — Shows a member's profile; with "presentazione" you change yours.
- **`/level rank`** — Shows the rank card: level, XP, position and coins.
- **`/level recent-levels`** — The last 25 level-ups in the server.
- **`/level rewards`** — Shows level reward roles and active XP multipliers.
- **`/level settings announcement`** — Where and when to announce level-ups.
- **`/level settings card`** — Shows or hides image backgrounds of cards and profiles in this server.
- **`/level settings exclude`** — A channel, category or role gives no XP (repeat to undo).
- **`/level settings multiplier`** — XP multiplied in a channel or for a role (factor 1 = removes the rule).
- **`/level settings rewards`** — Reward roles: keep them all or only the highest.
- **`/level settings shop`** — Asks for confirmation before each shop purchase (can be turned off).
- **`/level settings show`** — Shows this server's level settings.
- **`/level settings xp`** — How much XP and coins are earned, and how multipliers add up.
- **`/level shop buy`** — Buys a shop item.
- **`/level shop list`** — Shows the items available in the shop.
- **`/level work`** — Work to earn some coins.

## Log

- **`/log channel`** — Sets the server log channel (or forum).
- **`/log channel-archive`** — Download the latest messages of a channel in a file, including just-deleted ones.
- **`/log create-channels`** — Creates a private category with one channel for each log type.
- **`/log create-forum`** — Creates a private forum for logs: one post for each type.
- **`/log events`** — Turn each single log event on or off.
- **`/log export`** — Exports the full server event history as a JSON file.
- **`/log ignore`** — What the message log does not record (channels, users, roles, texts).
- **`/log search channel`** — Shows a channel's event history.
- **`/log search user`** — Shows a user's event history.
- **`/log status`** — Shows where the server logs go.

## Moderation

- **`/mod bulk timeout`** — Times out several members at once (max 28 days).
- **`/mod bulk warn`** — Warns several members at once.
- **`/mod case active`** — Timed sanctions still running: tempbans, timeouts, timed locks.
- **`/mod case delete`** — Deletes a case (needs "Manage Server").
- **`/mod case history`** — Shows a member's case history.
- **`/mod case reason`** — Changes the reason of an already logged case.
- **`/mod case staff-leaderboard`** — Moderator leaderboard by number of actions, or one moderator's cases.
- **`/mod case view`** — Shows the details of a single case.
- **`/mod clear`** — Deletes a number of messages, with optional filters.
- **`/mod lock`** — Blocks the ability to write in a channel.
- **`/mod lockdown enable`** — Lock all channels, invites and joins of the server.
- **`/mod lockdown remove`** — Reopen the server as it was before the lockdown.
- **`/mod mute`** — Mutes a member with a dedicated role (alternative to timeout).
- **`/mod note add`** — Adds a note on a user.
- **`/mod note clear`** — Deletes all of a member's notes (needs "Manage Server").
- **`/mod note edit`** — Changes a note's text.
- **`/mod note list`** — Lists the notes on a user.
- **`/mod note remove`** — Removes a note (the number is in the notes list).
- **`/mod options dm`** — Choose whether the user gets a DM for a type of action.
- **`/mod options immune`** — Roles manual moderation can't touch (owner only).
- **`/mod options set`** — Messages deleted on ban and default timeout length. Empty: shows the options.
- **`/mod slowmode`** — Sets slowmode on a channel.
- **`/mod timeout`** — Times out a member (max 28 days).
- **`/mod unlock`** — Unblocks the ability to write in a channel.
- **`/mod unmute`** — Removes the mute role from a member.
- **`/mod untimeout`** — Removes a member's timeout.
- **`/mod warn`** — Gives a member a warning.
- **`/mod warnings leaderboard`** — Members with the most active warnings.
- **`/mod warnings remove`** — Removes a single warning (by case number).
- **`/mod warnings reset`** — Removes all of a member's active warnings (needs "Manage Server").

## Bans (modban)

- **`/modban appeals channel`** — Picks the staff channel for appeals (empty to turn them off).
- **`/modban appeals list`** — Shows the server's latest appeals.
- **`/modban ban`** — Permanently bans a member.
- **`/modban bulk ban`** — Bans several users at once, even outside the server (IDs or mentions).
- **`/modban bulk kick`** — Kicks several members at once (IDs or mentions).
- **`/modban bulk unban`** — Unbans several users at once (IDs).
- **`/modban kick`** — Kicks a member from the server.
- **`/modban softban`** — Bans and unbans a member right away, to delete their recent messages.
- **`/modban tempban`** — Bans a member for a set time.
- **`/modban unban`** — Removes a user's ban.

## Modules

- **`/modules alert feed`** — Follows an RSS/Atom feed (YouTube, Reddit, or any other).
- **`/modules alert kick`** — Notify when a Kick channel goes live.
- **`/modules alert list`** — Shows the feeds followed by this server.
- **`/modules alert live-role`** — Role given to members who are live.
- **`/modules alert options`** — Alert options: role, end of stream, button.
- **`/modules alert remove`** — Removes a feed or Twitch subscription, or a webhook.
- **`/modules alert social-guide`** — Alerts for TikTok, Instagram and X.
- **`/modules alert twitch`** — Notifies when a Twitch streamer goes live/offline.
- **`/modules alert webhook`** — Creates a custom webhook: third-party services can post in a channel.
- **`/modules alert youtube-live`** — Notifies when a YouTube channel goes live (needs YOUTUBE_API_KEY on the bot).
- **`/modules applications create`** — Creates a form or application.
- **`/modules applications delete`** — Deletes a form and its answers.
- **`/modules applications list`** — This server's forms.
- **`/modules birthdays channel`** — Picks the wishes channel (empty to turn them off).
- **`/modules birthdays role`** — A role for 24 hours for whoever has a birthday (empty to remove it).
- **`/modules commands create`** — Creates a custom command.
- **`/modules commands delete`** — Deletes a custom command.
- **`/modules commands edit`** — Edits a custom command.
- **`/modules commands list`** — Shows the server's custom commands.
- **`/modules commands prefix`** — Picks the prefix to use commands by typing in the channel.
- **`/modules commands replies`** — Shows the server's automatic replies.
- **`/modules commands reply-create`** — Creates an automatic reply.
- **`/modules commands reply-delete`** — Deletes an automatic reply.
- **`/modules counters create`** — Creates a channel that shows a number.
- **`/modules counters delete`** — Stops updating a counter (the channel stays).
- **`/modules counters list`** — Shows the server's counters.
- **`/modules embed create`** — Creates an embed and shows the preview.
- **`/modules embed delete`** — Deletes a saved embed (the published message stays).
- **`/modules embed edit`** — Edits a saved embed (and the already published message).
- **`/modules embed list`** — Shows the saved embeds.
- **`/modules embed publish`** — Sends a saved embed to a channel.
- **`/modules starboard disattiva`** — Turns the board off.
- **`/modules starboard set`** — Picks the board channel and the star threshold.
- **`/modules starboard threshold`** — Changes how many stars are needed to reach the board.
- **`/modules statistics diagnosis`** — Why are the statistics not counting?
- **`/modules statistics list`** — Show the statistics rules and exclusions.
- **`/modules statistics ruolo-aggiungi`** — Give a role to active members and remove it when they stop.
- **`/modules statistics ruolo-elimina`** — Delete an activity role rule.
- **`/modules statistics settings`** — Exclude channels or roles from the statistics.

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

- **`/owner blacklist server-add`** — Globally blocks a server (the bot leaves if already there).
- **`/owner blacklist server-list`** — Shows the globally blocked servers.
- **`/owner blacklist server-remove`** — Removes a server from the global blacklist.
- **`/owner blacklist utente-add`** — Globally blocks a user from using the bot.
- **`/owner blacklist utente-list`** — Shows the globally blocked users.
- **`/owner blacklist utente-remove`** — Removes a user from the global blacklist.
- **`/owner cog load`** — Loads an extension (e.g. cogs.moderation.actions).
- **`/owner cog reload`** — Reloads an extension, optionally updating it from GitHub or a file.
- **`/owner cog unload`** — Unloads an extension.
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

## Roles

- **`/roles bulk`** — Give or remove a role to many members at once, with filters.
- **`/roles bulk-stop`** — Stop the bulk operation in progress.
- **`/roles create`** — Create a new role.
- **`/roles diagnosis`** — Find out why the bot cannot give a role.
- **`/roles edit`** — Change name, color and options of a role.
- **`/roles give`** — Give one or more roles to a member, also for a time.
- **`/roles remove`** — Remove one or more roles from a member, also for a time.
- **`/roles reset`** — Remove all roles from a member, with confirmation.
- **`/roles self-roles`** — Roles members take by themselves with /utility role.

## Security

- **`/security alt list`** — Duplicate accounts found by web verification.
- **`/security escalation disable`** — Turns the escalation ladder off.
- **`/security escalation enable`** — Turns the escalation ladder on.
- **`/security escalation remove-step`** — Removes a step from the custom ladder.
- **`/security escalation reset`** — Resets a member's infraction count.
- **`/security escalation set-reset-days`** — Days of good behaviour needed to reset the count.
- **`/security escalation set-step`** — Sets the action for a step of the ladder.
- **`/security escalation status`** — Shows the configured escalation ladder.
- **`/security globalban check`** — How many servers in the network banned this user via Spam Trap.
- **`/security globalban disable`** — Leaves the global ban network.
- **`/security globalban enable`** — Joins the global ban network (send and receive).
- **`/security globalban status`** — Shows the global ban status and recent history.
- **`/security heatmap`** — Shows which roles have critical permissions and who holds them.
- **`/security panic configura`** — Panic settings: notified roles, excluded categories, unlock, rules.
- **`/security panic enable`** — Turn panic on: full lockdown with the emergency rules.
- **`/security panic remove`** — Turn panic off and reopen the server as it was.
- **`/security panic status`** — Show whether the server is locked and the panic settings.
- **`/security score`** — Computes the server security score with advice.
- **`/security spamtrap`** — Sets up the Spam Trap trap and log channels.
- **`/security verify attempts`** — A user's verification attempts.
- **`/security verify blacklist-add`** — Adds a user to the blacklist.
- **`/security verify blacklist-remove`** — Removes a user from the blacklist.
- **`/security verify manual`** — Verifies a member by hand, with no checks.
- **`/security verify options`** — "Unverified" role and extra roles.
- **`/security verify panel`** — Publishes the verification panel.
- **`/security verify setup`** — Sets up Verify.
- **`/security verify statistics`** — Successful and failed verifications.
- **`/security verify timing`** — Reminder, time limit, action on failures, verification only for suspicious accounts.
- **`/security verify whitelist-add`** — Adds a user to the whitelist.
- **`/security verify whitelist-remove`** — Removes a user from the whitelist.

## Tickets

- **`/ticket add`** — Adds a user or role to this ticket.
- **`/ticket ask-close`** — Ask the user whether the ticket can be closed.
- **`/ticket assistant`** — AI assistant answer (for staff: draft and triage).
- **`/ticket blacklist`** — Users and roles that cannot open tickets.
- **`/ticket claim`** — Takes charge of this ticket.
- **`/ticket close`** — Closes this ticket.
- **`/ticket dm-close`** — Closes this ModMail conversation.
- **`/ticket forceclose`** — Closes this ticket immediately, with no wait.
- **`/ticket notes`** — Private staff thread to discuss the ticket.
- **`/ticket on-call`** — Join or leave the staff notified on every new ticket.
- **`/ticket open`** — Open a ticket (staff also for a user or from a message).
- **`/ticket options access`** — Who can open: per-role rules, read from the top.
- **`/ticket options channel`** — Channel name and fallback categories.
- **`/ticket options claiming`** — Claiming: category, exclusivity, auto-assignment.
- **`/ticket options closing`** — Confirmation before closing and who can close.
- **`/ticket options hours`** — Opening hours and what happens outside them.
- **`/ticket options limits`** — Open-ticket cap, cooldown and exempt roles.
- **`/ticket options messages`** — DMs to the user and claim/release texts.
- **`/ticket options permissions`** — User permissions, observers, roles while open, staff team.
- **`/ticket options show`** — All the options of a panel.
- **`/ticket options warnings`** — Who to ping on opening and pinned first message.
- **`/ticket pass`** — Hands the ticket over to a colleague.
- **`/ticket priority`** — Sets this ticket's priority.
- **`/ticket release`** — Gives up taking charge of this ticket.
- **`/ticket remove`** — Removes a user or role from this ticket.
- **`/ticket rename`** — Renames this ticket.
- **`/ticket reply`** — Replies to the user of this ModMail conversation.
- **`/ticket reset-cooldown`** — Remove a user's cooldown between tickets.
- **`/ticket suspend`** — Suspend ticket opening (no reason: resume).
- **`/ticket transcript`** — Get the transcript without closing the ticket.

## Utility

- **`/utility ai character`** — Talk to a server AI character.
- **`/utility ai create-character`** — Creates an AI character to chat with.
- **`/utility ai explain`** — Explains a message in simple words (from its link).
- **`/utility ai imagine`** — Generates an image from a description.
- **`/utility ai lore`** — Lore card about a name, a place or a yokai.
- **`/utility ai pack`** — Buy 5 extra AI images with server coins.
- **`/utility ai style`** — A new message written the way you write.
- **`/utility ai summarize`** — Summary of the latest messages of a channel.
- **`/utility ai translate`** — Translates a text into the language you choose.
- **`/utility ai upscale`** — Upscales and cleans up an image you upload.
- **`/utility editsnipe`** — Shows the last edited message in this channel.
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
- **`/utility policy channels`** — Where the bot answers commands.
- **`/utility policy comando`** — Turns a single command off or on again.
- **`/utility policy diagnosis`** — Finds out why a command does not work here.
- **`/utility policy ignore`** — The bot ignores a role or a user.
- **`/utility policy list`** — Shows the command policy and, if you want, clears a list.
- **`/utility poll`** — Creates a poll (up to 10 options).
- **`/utility privacy cancella`** — Request the deletion of your personal data.
- **`/utility privacy export`** — Get a copy of the data the bot keeps about you.
- **`/utility reactionsnipe`** — Shows the last removed reaction in this channel.
- **`/utility reminder cancel`** — Cancel a reminder, or all of yours.
- **`/utility reminder list`** — Shows your pending reminders.
- **`/utility reminder server`** — For staff: the reminders set in this server.
- **`/utility reminder set`** — Sets a reminder.
- **`/utility report`** — Reports a user to the server staff.
- **`/utility request-command`** — Suggests a new command for the bot.
- **`/utility role`** — Take or leave the server's self-assignable roles.
- **`/utility serverstats`** — Shows the server statistics, with a growth chart.
- **`/utility snipe`** — Shows the last deleted message in this channel.
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
