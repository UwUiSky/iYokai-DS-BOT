# backup-md — Archivio documentazione

I file `.md` del progetto (tranne `README.md` in root) sono stati spostati qui.

## Stato al momento dello spostamento

| File | In `backup-md/` |
|------|-----------------|
| `CLAUDE.md` | Sì (completo) |
| Altri (`SPEC`, `PROGRESS`, `REVIEW`, `PIANO_FIX`, …) | Recuperabili dalla **git history** al commit `585d1450` (ultimo stato root completa prima delle delete) |

## Recovery rapida (owner)

```bash
git checkout 585d1450 -- SPEC.md PROGRESS.md REVIEW.md PIANO_FIX.md BACKLOG.md \
  COMMAND_LIST.md VERIFICA_LIVE.md HANDOFF_GROK.md CLAUDE_MANDATORY_TEST_RULES.md \
  ISSUE_CLOSURES_ADVISOR.md
mkdir -p backup-md
mv SPEC.md PROGRESS.md REVIEW.md PIANO_FIX.md BACKLOG.md COMMAND_LIST.md \
  VERIFICA_LIVE.md HANDOFF_GROK.md CLAUDE_MANDATORY_TEST_RULES.md \
  ISSUE_CLOSURES_ADVISOR.md backup-md/
git add backup-md && git commit -m "chore: completa backup-md con contenuti da history"
```

Oppure: `git show 585d1450:SPEC.md > backup-md/SPEC.md` (ripeti per ogni file).

— iYokai Advisor Bot
