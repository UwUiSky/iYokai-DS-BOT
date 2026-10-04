# backup-md — Archivio documentazione

I `.md` del progetto (tranne `README.md` in root) vanno qui **senza riscrittura** (stesso blob git).

## Già presenti (upload API)

- `CLAUDE.md` (blob originale)
- `CLAUDE_MANDATORY_TEST_RULES.md` (verificare hash se serve byte-identico)
- questo `INDEX.md`

## Completare lo spostamento byte-identico (consigliato)

Da una clone locale della repo:

```bash
git fetch origin
git checkout main
mkdir -p backup-md

# Estrae i file ESATTI dal commit pre-delete (stessi blob SHA)
for f in \
  BACKLOG.md COMMAND_LIST.md HANDOFF_GROK.md ISSUE_CLOSURES_ADVISOR.md \
  PIANO_FIX.md PROGRESS.md REVIEW.md SPEC.md VERIFICA_LIVE.md \
  CLAUDE_MANDATORY_TEST_RULES.md
do
  git show 585d14509685385d4db1f15ef90a80c920f766f4:"$f" > "backup-md/$f"
done

# CLAUDE.md è già in backup-md/; se serve sovrascrivere dal blob originale:
git show 585d14509685385d4db1f15ef90a80c920f766f4:CLAUDE.md > backup-md/CLAUDE.md

git add backup-md
git status   # solo backup-md/*, nessun rewrite dei contenuti se già identici
git commit -m "chore: backup-md completo byte-identico da 585d145 (solo spostamento)"
git push origin main
```

Verifica blob (esempio):

```bash
git hash-object backup-md/SPEC.md
# atteso: 29f231fb725c76890355362f76dd8febc14ab4bc
```

Commit riferimento root completa: `585d14509685385d4db1f15ef90a80c920f766f4`.

— iYokai Advisor Bot
