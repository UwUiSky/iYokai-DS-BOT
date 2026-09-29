# VERIFICA_LIVE.md — Test da fare con il bot vero

Qui finiscono i fix che i test automatici non possono certificare
(servono Discord, il database reale o Lavalink). Li esegue l'owner sul
suo PC con il `.env` locale, seguendo `CLAUDE_MANDATORY_TEST_RULES.md`.

**Mai** scrivere qui token, password, `DATABASE_URL` o log che li
contengono.

## Preparazione (una volta)

- Server Discord di test con il bot invitato e con ruoli sopra e sotto
  quello del bot.
- Un secondo account Discord **senza** permessi, per le prove negative.
- `.env` locale compilato da `.env.example`, con `DATABASE_URL` di Aiven
  (`sslmode=require`).
- Per la musica: Lavalink in locale (`deploy/lavalink/`, quando esiste).

## Voci da verificare

Formato: `- [ ] CODICE (#issue) — commit SHA — passi — risultato atteso`.
Quando l'owner ha provato: `[x]` con data ed esito, poi l'issue si può
chiudere.

Vedi history git commit `585d1450` per il contenuto completo originale se questa versione risultasse incompleta.

- [ ] SEC-4/SEC-17 (#10, #14, #29, #32) — commit 599a2d4
- [ ] SEC-3 (#8) — commit 4d5e4a4
- [ ] SEC-5 (#7) — commit bde6f00
- [ ] SEC-8b (#11) — commit e24059f
- [ ] SEC-10 (#20) — commit 9d52a82
- [ ] SEC-11 — commit ac11f7a
- [ ] SEC-12 — commit 647b680
- [ ] SEC-13 — commit 8a96320
- [ ] SEC-14 — commit 0e9eb3b
- [ ] SEC-15 — commit bf2a772
- [ ] #41 — commit 576f155
- [ ] DB-1/#25 — commit 659d9fa
- [ ] BUG-1/#2/#42 — commit 6c724d3

*Ripristino in corso — contenuto esteso in `git show 585d1450:VERIFICA_LIVE.md`*
