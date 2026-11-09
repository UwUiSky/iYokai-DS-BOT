# Privileged intents: where and why iYokai uses them

Generated from `core/intent_usage.py` (`tests/test_intent_usage.py` keeps it in sync). Used for the privileged intents application to Discord (D11).

## GUILD_MEMBERS

Members are needed to react to joins and leaves (verification, anti-raid, welcome, autoroles, invite tracking, restore), to detect role and nickname changes (logs, anti-nuke, clan and live roles) and to resolve members for moderation. Nothing is stored beyond what each feature needs; user data is listed in the privacy policy and can be exported or erased on request.

| Feature | File | Why |
|---|---|---|
| Join and leave logs, nickname and role changes | `cogs/logging/basic_logs.py` | Audit trail for staff |
| Advanced logs (account age, invite used) | `cogs/logging/advanced_logs.py` | Audit trail for staff |
| Verification gate and captcha | `cogs/security/verify.py` | Give or withhold access on join |
| Anti-raid (join bursts, new accounts) | `cogs/security/anti_raid.py` | Protect the server from raids |
| Anti-nuke (mass removals, permission changes) | `cogs/security/anti_nuke.py` | Protect the server from nukes |
| Permission heatmap and security score | `cogs/security/permission_heatmap.py` | Show who holds risky permissions |
| Spam-trap | `cogs/security/spam_trap.py` | Catch compromised accounts |
| AutoMod rules on joins, leaves, nicknames and roles | `cogs/automod/eventi.py` | Apply the server's own AutoMod rules to member events |
| Autoroles and sticky roles | `cogs/utility/autoroles.py` | Give roles on join, restore on return |
| Welcome and goodbye messages | `cogs/utility/greetings.py` | Greet members |
| Invite tracking | `cogs/utility/invites.py` | Credit the inviter |
| Restore after a server backup | `cogs/utility/restore.py` | Return members to their roles |
| Backup of member roles | `cogs/utility/backup.py` | Keep the role snapshot up to date |
| Birthdays | `cogs/utility/birthdays.py` | Clean up on leave |
| Hate-word moderation | `cogs/automod/parole_odio.py` | Check names of new members |
| Moderation actions and cases | `cogs/moderation/actions.py` | Re-apply mutes and bans on rejoin |
| Case system | `cogs/moderation/case_system.py` | Track rejoin of sanctioned members |
| Softban and mute | `cogs/moderation/softban_mute.py` | Re-apply a mute on rejoin |
| Tickets | `cogs/tickets/tickets.py` | Close the ticket of a member who left |
| Modmail | `cogs/tickets/modmail.py` | Close the thread of a member who left |
| Button polls | `cogs/utility/sondaggi_bottoni.py` | Remove the vote of a member who left or was banned |
| Tag triggers on roles | `cogs/utility/inneschi.py` | Run a tag when the server's chosen role is given or taken |

## MESSAGE_CONTENT

Message content is needed by features that read what is written: AutoMod filters, anti-spam and spam-trap, XP for levelling, ticket and spam-trap transcripts, message logs for edits and deletions, snipe, auto-responders, custom commands, opt-in personal keyword alerts, the backup mirror, the music request channel and the optional AI features. Without it Discord delivers empty text and these features would look active but do nothing.

| Feature | File | Why |
|---|---|---|
| AutoMod filters | `cogs/automod/automod.py` | Read text to apply the server rules |
| Compromised account defence | `cogs/automod/account_rubato.py` | Spot the same scam message sent in many channels and stop it |
| Trap image filter | `cogs/automod/immagini.py` | Check images in a sandbox before members open them |
| Message logs (edits and deletions) | `cogs/logging/message_logs.py` | Audit trail for staff |
| Desktop alerts (opt-in keywords, mentions, replies) | `cogs/utility/desktop_menzioni.py` | Tell the person who turned alerts on that they were mentioned or a chosen word was written |
| Snipe | `cogs/utility/snipe.py` | Show the last deleted or edited message where allowed |
| Levelling (XP per message) | `cogs/leveling/leveling.py` | Count messages, ignore spam |
| Activity statistics | `cogs/utility/activity_stats.py` | Count messages per channel |
| Spam-trap | `cogs/security/spam_trap.py` | Detect messages in the trap channel |
| Tickets (transcripts) | `cogs/tickets/tickets.py` | Save the transcript when the ticket is closed |
| Modmail | `cogs/tickets/modmail.py` | Relay messages between member and staff |
| Auto-responders | `cogs/utility/autoresponder.py` | Reply to triggers set by the server |
| Custom commands | `cogs/utility/custom_commands.py` | Run commands defined by the server |
| Sticky messages | `cogs/utility/sticky_messages.py` | Keep a message at the bottom of a channel |
| Backup mirror | `cogs/utility/backup_mirror.py` | Copy messages to the backup server |
| Coin games | `cogs/fun/coin_games.py` | Count messages for coin rewards |
| Music request channel | `cogs/music/request_channel.py` | Read song requests written in a channel |
| Support threads (iYokai App) | `cogs/user_app/supporto_staff.py` | Forward the staff's replies to the person who asked |
| AI help desk | `cogs/ai/helpdesk.py` | Answer questions, only with the server's consent |
| AI moderation | `cogs/ai/moderazione.py` | Judge flagged messages, only with the server's consent |
| AI translation | `cogs/ai/traduzione.py` | Translate messages, only with the server's consent |
| AI channel summary | `cogs/ai/riepilogo.py` | Summarise a channel the staff chose, only with the server's consent |
| AI ticket assistant | `cogs/ai/ticket_ai.py` | Suggest a first answer inside tickets, only with the server's consent |
| Yokai voice | `cogs/ai/voce.py` | Read or transcribe a message when someone asks, only with the server's consent |
| Counting channel | `cogs/utility/conteggio.py` | Read the number written in the counting channel chosen by the staff |
| Auto-publish and auto-threads | `cogs/utility/messaggi_auto.py` | Act on messages in the channels the staff chose |
| Starboard auto channel | `cogs/utility/starboard.py` | Copy messages of the chosen channel to the board |
| Group games (typing, acronyms) | `cogs/fun/giochi_gruppo.py` | Read answers only in the channel of a running game, only from players |
| Long slowmode | `cogs/moderation/channel_control.py` | Enforce a slowmode longer than 6 hours chosen by the staff; only the time of the last message is kept |

## GUILD_PRESENCES

Not requested by default. Only when the bot owner turns on AUTOMOD_STATO_ATTIVO (off by default) the bot asks for it, so that server AutoMod rules can check a member's custom status text against the server's banned words. Online status and activities are never stored.

| Feature | File | Why |
|---|---|---|
| AutoMod rules on custom status (off by default) | `cogs/automod/eventi.py` | Check the custom status text against the server rules |
