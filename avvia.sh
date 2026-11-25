#!/usr/bin/env bash
# avvia.sh
# ========
# Avvio completo di iYokai su Linux e macOS, nell'ordine giusto:
#   1. controlla il file .env;
#   2. prepara l'ambiente Python e installa i requisiti (solo se sono cambiati);
#   3. controlla che il database PostgreSQL risponda (se è locale e DB_DOCKER=1 lo accende con Docker);
#   4. accende il Lavalink locale (Docker) e aspetta che risponda, ma Lavalink è FACOLTATIVO: se manca
#      o non risponde c'è solo un avviso, il bot parte lo stesso e la musica si riattiva da sola quando Lavalink torna;
#   5. avvia il bot.
# Uso: ./avvia.sh            (con --senza-lavalink salta il punto 4)
# Su Windows: avvia.ps1. Nessun segreto qui: password e chiavi si leggono dal .env.

set -euo pipefail
cd "$(dirname "$0")"

ATTESA_LAVALINK=90    # secondi al massimo: poi il bot parte lo stesso (Lavalink è facoltativo)
ATTESA_DB=60          # secondi
SENZA_LAVALINK=0
[[ "${1:-}" == "--senza-lavalink" ]] && SENZA_LAVALINK=1

info()  { printf '[avvio] %s\n' "$1"; }
errore() { printf '[avvio] ERRORE: %s\n' "$1" >&2; exit 1; }
avviso() { printf '[avvio] AVVISO: %s\n' "$1" >&2; }

# Legge una variabile dal .env senza eseguirne il contenuto.
leggi_env() {
    local riga
    riga=$(grep -E "^$1=" .env | tail -n 1 || true)
    riga=${riga#*=}
    riga=${riga%$'\r'}
    riga=${riga#\"}; riga=${riga%\"}
    riga=${riga#\'}; riga=${riga%\'}
    printf '%s' "$riga"
}

# 1. Il file .env
[[ -f .env ]] || errore "manca il file .env. Copia .env.example in .env e compilalo."

# 2. Ambiente Python e requisiti
PYTHON=${PYTHON:-python3}
if [[ ! -x .venv/bin/python ]]; then
    info "Creo l'ambiente Python in .venv"
    "$PYTHON" -m venv .venv || errore "non riesco a creare .venv: serve Python 3.11."
fi
IMPRONTA=$(cksum requirements.lock | cut -d' ' -f1)
if [[ "$(cat .venv/.requisiti 2>/dev/null || true)" != "$IMPRONTA" ]]; then
    info "Installo i requisiti (requirements.lock)"
    .venv/bin/python -m pip install --upgrade pip >/dev/null
    .venv/bin/python -m pip install -r requirements.lock
    printf '%s' "$IMPRONTA" > .venv/.requisiti
fi

# 3. Database
DB_URL=$(leggi_env DATABASE_URL)
[[ -n "$DB_URL" ]] || errore "manca DATABASE_URL nel .env."
export DB_URL
db_risponde() {
    .venv/bin/python - <<'PY' >/dev/null 2>&1
import asyncio, os, asyncpg
async def prova():
    c = await asyncpg.connect(os.environ["DB_URL"], timeout=5)
    await c.fetchval("SELECT 1")
    await c.close()
asyncio.run(prova())
PY
}
if db_risponde; then
    info "Database pronto"
else
    if [[ "$(leggi_env DB_DOCKER)" == "1" ]]; then
        command -v docker >/dev/null || errore "DB_DOCKER=1 ma Docker non c'è."
        info "Accendo PostgreSQL (Docker)"
        POSTGRES_PASSWORD=$(.venv/bin/python -c 'import os,urllib.parse as u;print(u.unquote(u.urlsplit(os.environ["DB_URL"]).password or ""))')
        export POSTGRES_PASSWORD
        (cd deploy/postgres && docker compose up -d) || errore "docker compose del database non è partito."
    else
        info "Il database non risponde ancora: aspetto (PostgreSQL deve essere acceso, vedi deploy/postgres/README.md)"
    fi
    inizio=$SECONDS
    until db_risponde; do
        (( SECONDS - inizio < ATTESA_DB )) || errore "il database non risponde dopo ${ATTESA_DB}s. Controlla che PostgreSQL sia acceso e che DATABASE_URL sia giusta."
        sleep 2
    done
    info "Database pronto in $(( SECONDS - inizio ))s"
fi
unset DB_URL POSTGRES_PASSWORD

# 4. Lavalink locale
HOST=$(leggi_env LAVALINK_HOST)
PORTA=$(leggi_env LAVALINK_PORT); PORTA=${PORTA:-2333}
PASSWORD=$(leggi_env LAVALINK_PASSWORD)

# La password NON va sulla riga di comando (si vedrebbe con `ps`): curl la legge da stdin con --config.
# printf è un comando interno della shell: gli argomenti non diventano un processo visibile.
lavalink_risponde() {
    local pw=${PASSWORD//\\/\\\\}; pw=${pw//\"/\\\"}
    printf 'header = "Authorization: %s"\n' "$pw" \
        | curl -fsS -o /dev/null -m 3 --config - "http://$HOST:$PORTA/version" 2>/dev/null
}

if [[ $SENZA_LAVALINK -eq 1 ]]; then
    info "Lavalink saltato (--senza-lavalink)"
elif [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" ]]; then
    info "Nessun Lavalink locale nel .env (LAVALINK_HOST=$HOST): uso i nodi indicati lì"
else
    if [[ -z "$PASSWORD" || "$PASSWORD" == "CAMBIAMI" ]]; then
        avviso "LAVALINK_PASSWORD non è impostata nel .env: salto Lavalink. Il bot parte lo stesso, senza musica."
    elif lavalink_risponde; then
        info "Lavalink è già acceso"
    elif ! command -v docker >/dev/null; then
        avviso "Lavalink locale non risponde e Docker non c'è. Il bot parte lo stesso: la musica si riattiva da sola quando Lavalink torna."
    else
        info "Accendo Lavalink (Docker)"
        export LAVALINK_PASSWORD="$PASSWORD"
        for nome in MAIN_RADIO_LOCAL_FOLDER MUSICA_CARTELLA_OWNER SPOTIFY_CLIENT_ID SPOTIFY_CLIENT_SECRET \
                    APPLE_MUSIC_TOKEN TIDAL_TOKEN YANDEX_MUSIC_TOKEN; do
            valore=$(leggi_env "$nome")
            [[ -n "$valore" ]] && export "$nome=$valore"
        done
        if ! (cd deploy/lavalink && docker compose up -d); then
            avviso "docker compose non è partito. Il bot parte lo stesso, senza musica per ora."
        else
            info "Aspetto che Lavalink risponda (al massimo ${ATTESA_LAVALINK}s)"
            inizio=$SECONDS
            until lavalink_risponde; do
                if (( SECONDS - inizio >= ATTESA_LAVALINK )); then
                    avviso "Lavalink non risponde dopo ${ATTESA_LAVALINK}s (guarda: cd deploy/lavalink && docker compose logs lavalink). Il bot parte lo stesso: la musica si riattiva da sola quando Lavalink risponde."
                    break
                fi
                sleep 3
            done
            lavalink_risponde && info "Lavalink pronto in $(( SECONDS - inizio ))s"
        fi
    fi
fi

# 5. Il bot
info "Avvio il bot"
exec .venv/bin/python main.py
