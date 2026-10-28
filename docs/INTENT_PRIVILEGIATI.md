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

## MESSAGE_CONTENT

Message content is needed by features that read what is written: AutoMod filters, anti-spam and spam-trap, XP for levelling, ticket and spam-trap transcripts, message logs for edits and deletions, snipe, auto-responders, custom commands, opt-in personal keyword alerts, the backup mirror, the music request channel and the optional AI features. Without it Discord delivers empty text and these features would look active but do nothing.

| Feature | File | Why |
|---|---|---|
| AutoMod filters | `cogs/automod/automod.py` | Read text to apply the server rules |
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

## GUILD_PRESENCES

Not requested. iYokai never enables the presences intent and does not read online status or activities.

No feature uses this intent.
