# Chiusure verificate — iYokai Advisor Bot

Registro delle issue chiuse dopo verifica **statica sul source** `main` (non smoke live Discord).

---

## Cod. Issue #2 — Tickets

- **Descrizione issue:** `/ticket close` crash: `TextChannel.delete()` non accetta `delay=`.
- **Commit fix:** `6c724d3994a61e9f348b3c6dcf1c7762b7da3e96`
- **Codice cambiato:** `cogs/tickets/tickets.py` — `_elimina_dopo` / `_pianifica_eliminazione` (`asyncio.sleep` poi `delete(reason=…)`).

## Cod. Issue #42 — Tickets

- **Descrizione issue:** Re-conferma dello stesso crash di #2.
- **Commit fix:** `6c724d3994a61e9f348b3c6dcf1c7762b7da3e96`
- **Codice cambiato:** `cogs/tickets/tickets.py` (stesso fix).

## Cod. Issue #5 — Core / `main.py` (SEC-7)

- **Descrizione issue:** Nessun `allowed_mentions` globale → rischio ping `@everyone` / `@here`.
- **Commit fix:** `cb05eff1`
- **Codice cambiato:** `main.py` — `AllowedMentions(everyone=False, roles=False, users=True, replied_user=False)`.

## Cod. Issue #8 — Restore OAuth (SEC-3)

- **Descrizione issue:** State OAuth in chiaro, falsificabile.
- **Commit fix:** `4d5e4a46`
- **Codice cambiato:** `core/restore_oauth_logic.py` — HMAC, TTL, nonce monouso.

## Cod. Issue #9 — Feed watcher (SEC-8)

- **Descrizione issue:** SSRF su URL feed scelti dall’admin.
- **Commit fix:** `a28f817a`
- **Codice cambiato:** `core/safe_http.py` + `core/feed_watcher.py` (`safe_get`).

## Cod. Issue #17 — Templates feed/webhook (SEC-6)

- **Descrizione issue:** `str.format` su template utente → DoS memoria.
- **Commit fix:** `25c3cdcf`
- **Codice cambiato:** `core/template_renderer.py` (+ call site feed/webhook).

## Cod. Issue #7 — Music radio (SEC-5)

- **Descrizione issue:** path traversal su `add-local` + playlist globale editabile da admin server.
- **Commit fix:** `bde6f004`
- **Codice cambiato:** `cogs/music/player.py` — `_is_owner`, `Path.resolve` / `is_relative_to`.
- **Nota:** gap radio 24/7 auto-join e self-host Lavalink restano #45 / #47.

---

*Firmato: iYokai Advisor Bot — chiusura issue GitHub + questo registro. Nessuna modifica al codice applicativo in questo commit (i fix erano già su main).*
