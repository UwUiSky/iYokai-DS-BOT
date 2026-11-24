#!/usr/bin/env bash
# avvia.sh
# ========
# Avvio completo di iYokai su Linux e macOS, nell'ordine giusto:
#   1. controlla il file .env;
#   2. prepara l'ambiente Python e installa i requisiti (solo se sono cambiati);
#   3. controlla che il database PostgreSQL risponda (se è locale e DB_DOCKER=1 lo accende con Docker);
#   4. accende il Lavalink locale (Docker) e aspetta che risponda;
#   5. avvia il bot.
# Uso: ./avvia.sh            (con --senza-lavalink salta il punto 4)
# Su Windows: avvia.ps1. Nessun segreto qui: password e chiavi si leggono dal .env.

set -euo pipefail
cd "$(dirname "$0")"

ATTESA_LAVALINK=300   # secondi; al primo avvio Lavalink scarica i plugin
ATTESA_DB=60          # secondi
SENZA_LAVALINK=0
[[ "${1:-}" == "--senza-lavalink" ]] && SENZA_LAVALINK=1

info()  { printf '[avvio] %s\n' "$1"; }
errore() { printf '[avvio] ERRORE: %s\n' "$1" >&2; exit 1; }

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

lavalink_risponde() {
    curl -fsS -o /dev/null -m 3 -H "Authorization: $PASSWORD" "http://$HOST:$PORTA/version" 2>/dev/null
}

if [[ $SENZA_LAVALINK -eq 1 ]]; then
    info "Lavalink saltato (--senza-lavalink)"
elif [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" ]]; then
    info "Nessun Lavalink locale nel .env (LAVALINK_HOST=$HOST): uso i nodi indicati lì"
else
    [[ -n "$PASSWORD" && "$PASSWORD" != "CAMBIAMI" ]] || errore "imposta LAVALINK_PASSWORD nel .env."
    if lavalink_risponde; then
        info "Lavalink è già acceso"
    else
        command -v docker >/dev/null || errore "Lavalink locale non risponde e Docker non c'è. Installa Docker o avvia Lavalink a mano."
        info "Accendo Lavalink (Docker)"
        export LAVALINK_PASSWORD="$PASSWORD"
        for nome in MAIN_RADIO_LOCAL_FOLDER MUSICA_CARTELLA_OWNER SPOTIFY_CLIENT_ID SPOTIFY_CLIENT_SECRET \
                    APPLE_MUSIC_TOKEN TIDAL_TOKEN YANDEX_MUSIC_TOKEN; do
            valore=$(leggi_env "$nome")
            [[ -n "$valore" ]] && export "$nome=$valore"
        done
        (cd deploy/lavalink && docker compose up -d) || errore "docker compose non è partito."
        info "Aspetto che Lavalink risponda (al massimo ${ATTESA_LAVALINK}s)"
        inizio=$SECONDS
        until lavalink_risponde; do
            (( SECONDS - inizio < ATTESA_LAVALINK )) || errore "Lavalink non risponde dopo ${ATTESA_LAVALINK}s. Guarda: cd deploy/lavalink && docker compose logs lavalink"
            sleep 3
        done
        info "Lavalink pronto in $(( SECONDS - inizio ))s"
    fi
fi

# 5. Il bot
info "Avvio il bot"
exec .venv/bin/python main.py
