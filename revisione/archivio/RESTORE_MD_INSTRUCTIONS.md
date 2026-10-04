# Ripristino MD — istruzioni one-shot

I file grandi (SPEC, PROGRESS, REVIEW, PIANO_FIX, BACKLOG, COMMAND_LIST, VERIFICA_LIVE completo)
sono ancora in git history al commit:

`585d14509685385d4db1f15ef90a80c920f766f4`

## Comando unico (clone locale)

```bash
git fetch origin && git checkout main
for f in SPEC.md PROGRESS.md REVIEW.md PIANO_FIX.md BACKLOG.md COMMAND_LIST.md VERIFICA_LIVE.md; do
  git show 585d14509685385d4db1f15ef90a80c920f766f4:"$f" > "$f"
done
git add SPEC.md PROGRESS.md REVIEW.md PIANO_FIX.md BACKLOG.md COMMAND_LIST.md VERIFICA_LIVE.md
git commit -m "restore: MD grandi byte-identici da 585d145"
git push origin main
```

## Già ripristinati in root (blob originali)

- CLAUDE.md
- CLAUDE_MANDATORY_TEST_RULES.md
- HANDOFF_GROK.md
- ISSUE_CLOSURES_ADVISOR.md

## Nota

VERIFICA_LIVE.md attuale in root è uno stub: sovrascriverlo col comando sopra.

— iYokai Advisor Bot
