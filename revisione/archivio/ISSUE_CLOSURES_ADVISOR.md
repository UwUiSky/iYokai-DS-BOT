# Chiusure verificate — iYokai Advisor Bot

Registro delle issue chiuse dopo verifica **statica sul source** `main`.

- Senza pallino: fix meccanico ad alta confidenza (smoke live comunque utile).
- **🟡 Test live ancora necessario:** codice presente e coerente, ma va provato su Discord/DB reali.

---

## Lotto 1 (chiusure precedenti)

### Cod. Issue #2 — Tickets
- **Descrizione:** `/ticket close` crash: `delete(delay=)` invalido.
- **Commit fix:** `6c724d3994a61e9f348b3c6dcf1c7762b7da3e96`
- **Codice:** `cogs/tickets/tickets.py` — `_elimina_dopo` / `_pianifica_eliminazione`.

### Cod. Issue #42 — Tickets
- **Descrizione:** Re-conferma crash #2.
- **Commit fix:** `6c724d3994a61e9f348b3c6dcf1c7762b7da3e96`
- **Codice:** `cogs/tickets/tickets.py`.

### Cod. Issue #5 — Core / main (SEC-7)
- **Descrizione:** Nessun `allowed_mentions` globale.
- **Commit fix:** `cb05eff1`
- **Codice:** `main.py` — `AllowedMentions(...)`.

### Cod. Issue #8 — Restore OAuth (SEC-3)
- **Descrizione:** State OAuth in chiaro.
- **Commit fix:** `4d5e4a46`
- **Codice:** `core/restore_oauth_logic.py` — HMAC.

### Cod. Issue #9 — Feed SSRF (SEC-8)
- **Descrizione:** GET non filtrato su URL feed.
- **Commit fix:** `a28f817a`
- **Codice:** `core/safe_http.py` + `feed_watcher.py`.

### Cod. Issue #17 — Templates (SEC-6)
- **Descrizione:** `str.format` DoS.
- **Commit fix:** `25c3cdcf`
- **Codice:** `core/template_renderer.py`.

### Cod. Issue #7 — Music radio (SEC-5)
- **Descrizione:** path traversal + playlist globale.
- **Commit fix:** `bde6f004`
- **Codice:** `cogs/music/player.py`.

---

## Lotto 2 — 🟡 test live ancora necessario

### Cod. Issue #10 — Leveling / Shop hierarchy (SEC-4)
- **🟡 Test live ancora necessario**
- **Descrizione:** shop / level-roles potevano assegnare ruoli sopra bot o caller.
- **Commit fix:** `599a2d497ed0f045ea59146af7211a32e4784030`
- **Codice:** `core/role_safety.py` + shop / level-roles.

### Cod. Issue #14 — Role menu hierarchy (SEC-4)
- **🟡 Test live ancora necessario**
- **Descrizione:** rolemenu senza controllo gerarchia.
- **Commit fix:** `599a2d497ed0f045ea59146af7211a32e4784030`
- **Codice:** `core/role_safety.py` + rolemenu.

### Cod. Issue #29 — Voice-temp platform roles (SEC-17)
- **🟡 Test live ancora necessario**
- **Descrizione:** ruolo piattaforma senza hierarchy check.
- **Commit fix:** `599a2d497ed0f045ea59146af7211a32e4784030`
- **Codice:** `core/role_safety.py` + voicetemp platform.

### Cod. Issue #32 — Verify hierarchy
- **🟡 Test live ancora necessario**
- **Descrizione:** `verified_role` potenzialmente sopra gerarchia bot.
- **Commit fix:** `599a2d497ed0f045ea59146af7211a32e4784030`
- **Codice:** `core/role_safety.py` + verify.

### Cod. Issue #11 — Spam trap staff (SEC-8b)
- **🟡 Test live ancora necessario**
- **Descrizione:** ban anche staff; bottoni appello senza permesso.
- **Commit fix:** `e24059ffefa64c81a14462f536588b32860a68f5`
- **Codice:** `cogs/security/spam_trap.py`.

### Cod. Issue #15 — Restore-users source guild (SEC-2)
- **🟡 Test live ancora necessario**
- **Descrizione:** accettava qualsiasi server di origine.
- **Commit fix:** `15ddf7d6`
- **Codice:** `cogs/utility/restore.py` — check pair backup.
- **Nota:** E2E dipende ancora da **#26** (pair non scritta a fine job).

### Cod. Issue #25 — Database migrations (DB-1)
- **🟡 Test live ancora necessario**
- **Descrizione:** schema senza versioning.
- **Commit fix:** `659d9fa8ea3a336e66e4d743ea086e8e5715b8b1`
- **Codice:** `core/migrations/` (+ `database.py` / conftest).

---

*Firmato: iYokai Advisor Bot. Nessuna modifica al codice applicativo in questi commit di chiusura (i fix erano già su main).*
