"""
core/intent_usage.py
====================
Elenco delle funzioni che usano ogni intent privilegiato (SPEC §19.8, D11): serve per la domanda a
Discord quando il bot supera i 10.000 utenti. Dati e testo in inglese (la domanda a Discord è in
inglese); `tests/test_intent_usage.py` controlla che ogni cog con un ascoltatore di quegli eventi sia
nell'elenco e che `docs/INTENT_PRIVILEGIATI.md` sia aggiornato (si rigenera con `genera_documento()`).
Funzioni coperte: SPEC §19.8
"""

from __future__ import annotations

from dataclasses import dataclass

INTENT_MEMBERS = "GUILD_MEMBERS"
INTENT_MESSAGE_CONTENT = "MESSAGE_CONTENT"
INTENT_PRESENCES = "GUILD_PRESENCES"

# Eventi che richiedono l'intent: l'AST dei cog si confronta con questi nomi.
EVENTI_MEMBRI = ("on_member_join", "on_member_remove", "on_member_update")
EVENTI_MESSAGGI = ("on_message", "on_message_edit")


@dataclass(frozen=True)
class UsoIntent:
    funzione: str
    file: str
    motivo: str


MOTIVAZIONE = {
    INTENT_MEMBERS: (
        "Members are needed to react to joins and leaves (verification, anti-raid, welcome, autoroles, "
        "invite tracking, restore), to detect role and nickname changes (logs, anti-nuke, clan and live roles) "
        "and to resolve members for moderation. Nothing is stored beyond what each feature needs; user data is "
        "listed in the privacy policy and can be exported or erased on request."
    ),
    INTENT_MESSAGE_CONTENT: (
        "Message content is needed by features that read what is written: AutoMod filters, anti-spam and spam-trap, "
        "XP for levelling, ticket and spam-trap transcripts, message logs for edits and deletions, snipe, "
        "auto-responders, custom commands, the backup mirror, the music request channel and the optional AI "
        "features. Without it Discord delivers empty text and these features would look active but do nothing."
    ),
    INTENT_PRESENCES: (
        "Not requested. iYokai never enables the presences intent and does not read online status or activities."
    ),
}

USI: dict[str, tuple[UsoIntent, ...]] = {
    INTENT_MEMBERS: (
        UsoIntent("Join and leave logs, nickname and role changes", "cogs/logging/basic_logs.py", "Audit trail for staff"),
        UsoIntent("Advanced logs (account age, invite used)", "cogs/logging/advanced_logs.py", "Audit trail for staff"),
        UsoIntent("Verification gate and captcha", "cogs/security/verify.py", "Give or withhold access on join"),
        UsoIntent("Anti-raid (join bursts, new accounts)", "cogs/security/anti_raid.py", "Protect the server from raids"),
        UsoIntent("Anti-nuke (mass removals, permission changes)", "cogs/security/anti_nuke.py", "Protect the server from nukes"),
        UsoIntent("Permission heatmap and security score", "cogs/security/permission_heatmap.py", "Show who holds risky permissions"),
        UsoIntent("Spam-trap", "cogs/security/spam_trap.py", "Catch compromised accounts"),
        UsoIntent("Autoroles and sticky roles", "cogs/utility/autoroles.py", "Give roles on join, restore on return"),
        UsoIntent("Welcome and goodbye messages", "cogs/utility/greetings.py", "Greet members"),
        UsoIntent("Invite tracking", "cogs/utility/invites.py", "Credit the inviter"),
        UsoIntent("Restore after a server backup", "cogs/utility/restore.py", "Return members to their roles"),
        UsoIntent("Backup of member roles", "cogs/utility/backup.py", "Keep the role snapshot up to date"),
        UsoIntent("Birthdays", "cogs/utility/birthdays.py", "Clean up on leave"),
        UsoIntent("Hate-word moderation", "cogs/automod/parole_odio.py", "Check names of new members"),
        UsoIntent("Moderation actions and cases", "cogs/moderation/actions.py", "Re-apply mutes and bans on rejoin"),
        UsoIntent("Case system", "cogs/moderation/case_system.py", "Track rejoin of sanctioned members"),
        UsoIntent("Softban and mute", "cogs/moderation/softban_mute.py", "Re-apply a mute on rejoin"),
        UsoIntent("Tickets", "cogs/tickets/tickets.py", "Close the ticket of a member who left"),
        UsoIntent("Modmail", "cogs/tickets/modmail.py", "Close the thread of a member who left"),
    ),
    INTENT_MESSAGE_CONTENT: (
        UsoIntent("AutoMod filters", "cogs/automod/automod.py", "Read text to apply the server rules"),
        UsoIntent("Message logs (edits and deletions)", "cogs/logging/message_logs.py", "Audit trail for staff"),
        UsoIntent("Snipe", "cogs/utility/snipe.py", "Show the last deleted or edited message where allowed"),
        UsoIntent("Levelling (XP per message)", "cogs/leveling/leveling.py", "Count messages, ignore spam"),
        UsoIntent("Activity statistics", "cogs/utility/activity_stats.py", "Count messages per channel"),
        UsoIntent("Spam-trap", "cogs/security/spam_trap.py", "Detect messages in the trap channel"),
        UsoIntent("Tickets (transcripts)", "cogs/tickets/tickets.py", "Save the transcript when the ticket is closed"),
        UsoIntent("Modmail", "cogs/tickets/modmail.py", "Relay messages between member and staff"),
        UsoIntent("Auto-responders", "cogs/utility/autoresponder.py", "Reply to triggers set by the server"),
        UsoIntent("Custom commands", "cogs/utility/custom_commands.py", "Run commands defined by the server"),
        UsoIntent("Sticky messages", "cogs/utility/sticky_messages.py", "Keep a message at the bottom of a channel"),
        UsoIntent("Backup mirror", "cogs/utility/backup_mirror.py", "Copy messages to the backup server"),
        UsoIntent("Coin games", "cogs/fun/coin_games.py", "Count messages for coin rewards"),
        UsoIntent("Music request channel", "cogs/music/request_channel.py", "Read song requests written in a channel"),
        UsoIntent("AI help desk", "cogs/ai/helpdesk.py", "Answer questions, only with the server's consent"),
        UsoIntent("AI moderation", "cogs/ai/moderazione.py", "Judge flagged messages, only with the server's consent"),
        UsoIntent("AI translation", "cogs/ai/traduzione.py", "Translate messages, only with the server's consent"),
    ),
    INTENT_PRESENCES: (),
}


def file_elencati(intent: str) -> set[str]:
    return {u.file for u in USI[intent]}


def genera_documento() -> str:
    """Il testo di `docs/INTENT_PRIVILEGIATI.md`: motivazione e funzioni per ogni intent."""
    righe = [
        "# Privileged intents: where and why iYokai uses them",
        "",
        "Generated from `core/intent_usage.py` (`tests/test_intent_usage.py` keeps it in sync). "
        "Used for the privileged intents application to Discord (D11).",
    ]
    for intent, usi in USI.items():
        righe += ["", f"## {intent}", "", MOTIVAZIONE[intent], ""]
        if not usi:
            righe.append("No feature uses this intent.")
            continue
        righe += ["| Feature | File | Why |", "|---|---|---|"]
        righe += [f"| {u.funzione} | `{u.file}` | {u.motivo} |" for u in usi]
    return "\n".join(righe) + "\n"
