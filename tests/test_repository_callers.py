"""
tests/test_repository_callers.py
====================================
Ogni metodo pubblico dei repository (core/repositories/) deve essere
chiamato da almeno un punto del codice di produzione (cogs/, core/,
main.py). Un metodo di scrittura mai chiamato è quasi sempre una
funzione a metà: è il caso di BUG-3 (`define_backup`), che i test
nascondevano chiamandolo loro stessi.

KNOWN_UNCALLED è un cricchetto: contiene i metodi oggi senza chiamanti
(REVIEW.md §11). Ogni fix toglie il nome; un nome nuovo fa fallire il
test.
"""

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

KNOWN_UNCALLED = frozenset(
    {
        "automod_advanced_repo.AutomodAdvancedRepository.get_recent_actions",
        "backup_mirror_repo.BackupMirrorRepository.delete_for_main_guild",
        "backup_repo.BackupRepository.get_job",
        "backup_user_snapshot_repo.BackupUserSnapshotRepository.get_snapshot_count",
        "backup_user_snapshot_repo.BackupUserSnapshotRepository.delete_for_main_guild",
        "clan_voice_activity_repo.ClanVoiceActivityRepository.get_activity",
        "eval_shell_log_repo.EvalShellLogRepository.get_recent",
        "event_log_repo.EventLogRepository.get_recent_events",
        "event_log_repo.EventLogRepository.prune_old_events",
        "giveaway_repo.GiveawayRepository.has_entered",
        "giveaway_repo.GiveawayRepository.count_entries",
        "guild_clan_repo.GuildClanRepository.list_clans",
        "guild_clan_repo.GuildClanRepository.get_donation_leaderboard",
        "guild_premium_repo.GuildPremiumRepository.purchased_tiers",
        "restore_oauth_repo.RestoreOAuthRepository.delete_token",
        "restore_oauth_repo.RestoreOAuthRepository.purge_expired_voluntary_leaves",
        "security_repo.SecurityRepository.get_recent_actions",
        "spam_trap_repo.SpamTrapRepository.prune_old_index",
        "verify_repo.VerifyRepository.get_recent_attempts",
    }
)


def _production_sources() -> dict[pathlib.Path, str]:
    files = list(ROOT.glob("cogs/**/*.py")) + list(ROOT.glob("core/**/*.py")) + [ROOT / "main.py"]
    return {p: p.read_text(encoding="utf-8") for p in files}


def _uncalled_repository_methods() -> set[str]:
    sources = _production_sources()
    risultato = set()
    for repo_file in sorted((ROOT / "core" / "repositories").glob("*.py")):
        testo = sources[repo_file]
        for nodo in ast.parse(testo).body:
            if not isinstance(nodo, ast.ClassDef):
                continue
            for metodo in nodo.body:
                if not isinstance(metodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if metodo.name.startswith("_"):
                    continue
                chiamata = re.compile(r"\." + re.escape(metodo.name) + r"\(")
                if any(chiamata.search(s) for s in sources.values()):
                    continue
                risultato.add(f"{repo_file.stem}.{nodo.name}.{metodo.name}")
    return risultato


def test_metodi_dei_repository_hanno_un_chiamante():
    senza_chiamanti = _uncalled_repository_methods()

    nuovi = sorted(senza_chiamanti - KNOWN_UNCALLED)
    assert nuovi == [], f"Metodi di repository mai chiamati dal codice di produzione: {nuovi}"

    sistemati = sorted(KNOWN_UNCALLED - senza_chiamanti)
    assert sistemati == [], f"Questi metodi ora hanno un chiamante: toglili da KNOWN_UNCALLED: {sistemati}"
