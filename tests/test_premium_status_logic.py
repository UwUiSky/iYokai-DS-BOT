"""
tests/test_premium_status_logic.py
======================================
Test di core/premium_status_logic.py — logica pura, nessun DB/bot.
"""

from datetime import datetime, timezone

from core.premium_status_logic import format_guild_status_line, format_whitelist_entry


class TestFormatWhitelistEntry:
    def test_con_motivo(self):
        riga = format_whitelist_entry(
            guild_id=123,
            added_by=456,
            reason="server partner",
            added_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        assert riga == (
            "`123` — aggiunto da `456` il `2026-01-15` — motivo: server partner"
        )

    def test_senza_motivo(self):
        riga = format_whitelist_entry(
            guild_id=123,
            added_by=456,
            reason=None,
            added_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        assert riga == "`123` — aggiunto da `456` il `2026-01-15`"
        assert "motivo" not in riga


class TestFormatGuildStatusLine:
    def test_nessuno_sblocco(self):
        riga = format_guild_status_line(
            guild_id=1, guild_name="Server X",
            whitelisted=False, boosts_main_guild=False,
            cassa_active=False, subscription_count=0,
        )
        assert riga == "`1` (Server X) — nessuno sblocco proprio"

    def test_whitelist(self):
        riga = format_guild_status_line(
            guild_id=1, guild_name="Server X",
            whitelisted=True, boosts_main_guild=False,
            cassa_active=False, subscription_count=0,
        )
        assert riga == "`1` (Server X) — whitelist"

    def test_boost(self):
        riga = format_guild_status_line(
            guild_id=1, guild_name="Server X",
            whitelisted=False, boosts_main_guild=True,
            cassa_active=False, subscription_count=0,
        )
        assert riga == "`1` (Server X) — nitro boost"

    def test_cassa(self):
        riga = format_guild_status_line(
            guild_id=1, guild_name="Server X",
            whitelisted=False, boosts_main_guild=False,
            cassa_active=True, subscription_count=0,
        )
        assert riga == "`1` (Server X) — premium via cassa"

    def test_abbonamenti(self):
        riga = format_guild_status_line(
            guild_id=1, guild_name="Server X",
            whitelisted=False, boosts_main_guild=False,
            cassa_active=False, subscription_count=3,
        )
        assert riga == "`1` (Server X) — 3 abbonamento/i per modulo"

    def test_piu_meccanismi_insieme(self):
        riga = format_guild_status_line(
            guild_id=1, guild_name="Server X",
            whitelisted=True, boosts_main_guild=True,
            cassa_active=True, subscription_count=2,
        )
        assert riga == (
            "`1` (Server X) — whitelist, nitro boost, premium via cassa, "
            "2 abbonamento/i per modulo"
        )
