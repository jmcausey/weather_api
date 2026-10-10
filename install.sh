#!/usr/bin/env bash
# Interactive first-run installer for weather_api.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

OPENWEATHER_SIGNUP_URL="https://home.openweathermap.org/users/sign_up"
OPENWEATHER_KEYS_URL="https://home.openweathermap.org/api_keys"

say() { printf '\n%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

read_env_value() {
    local key="$1"
    [[ -f .env ]] || return 0
    awk -v key="$key" '
        index($0, "=") > 0 {
            name = substr($0, 1, index($0, "=") - 1)
            if (name == key) {
                value = substr($0, index($0, "=") + 1)
                if (value ~ /^".*"$/ || value ~ /^\047.*\047$/) {
                    value = substr(value, 2, length(value) - 2)
                }
                print value
                exit
            }
        }
    ' .env
}

prompt_default() {
    local label="$1" default="$2" answer
    read -r -p "$label [$default]: " answer
    printf '%s' "${answer:-$default}"
}

open_url() {
    local url="$1"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 || true
    else
        say "Open this URL in your browser: $url"
    fi
}

command -v docker >/dev/null 2>&1 || fail "Docker is not installed or not on PATH."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 ('docker compose') is required."
command -v curl >/dev/null 2>&1 || fail "curl is required."
command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate a database password."

say "weather_api interactive installer"
say "This installer will configure .env and then run: docker compose up -d --build"
say "It will not remove containers, volumes, or existing database data."

if [[ ! -f docker-compose.yml || ! -f Dockerfile ]]; then
    fail "Run this installer from the weather_api repository; docker-compose.yml or Dockerfile is missing."
fi

say "Step 1 of 3: OpenWeatherMap account and API key"
say "OpenWeatherMap requires you to complete its own account registration and any email verification."
say "For security and because the site may require verification/CAPTCHA, this installer does not submit signup forms or access your account for you."
if [[ -f .env ]]; then
    account_answer="$(prompt_default "Do you already have an OpenWeatherMap account? (y/n)" "y")"
else
    account_answer="$(prompt_default "Do you already have an OpenWeatherMap account? (y/n)" "n")"
fi
case "$account_answer" in
    [Yy]*)
        open_url "$OPENWEATHER_KEYS_URL"
        say "Sign in if prompted, then open the API keys page."
        ;;
    [Nn]*)
        open_url "$OPENWEATHER_SIGNUP_URL"
        say "Complete registration and email verification in the browser."
        read -r -p "When your account is ready, press Enter to open the API keys page..." _
        open_url "$OPENWEATHER_KEYS_URL"
        ;;
    *)
        fail "Please answer y or n."
        ;;
esac

say "Create or copy an OpenWeatherMap API key from the API keys page."
say "New keys can take a little time to become active. You can rerun this installer later to update the key."
read -r -s -p "Paste the API key (input is hidden): " OPENWEATHER_API_KEY
printf '\n'
[[ -n "$OPENWEATHER_API_KEY" ]] || fail "The API key cannot be blank."
[[ "$OPENWEATHER_API_KEY" != *$'\n'* && "$OPENWEATHER_API_KEY" != *$'\r'* ]] || fail "The API key must be a single line."

say "Step 2 of 3: Configure .env"

if [[ -f .env ]]; then
    say "An existing .env was found. Existing database credentials are preserved to avoid accidentally disconnecting from an initialized database."
    old_user="$(read_env_value POSTGRES_USER)"
    old_password="$(read_env_value POSTGRES_PASSWORD)"
    old_db="$(read_env_value POSTGRES_DB)"
    old_port="$(read_env_value APP_PORT)"
    POSTGRES_USER="${old_user:-cl}"
    POSTGRES_PASSWORD="${old_password:-}"
    POSTGRES_DB="${old_db:-cl}"
    APP_PORT="${old_port:-5002}"

    if [[ -z "$POSTGRES_PASSWORD" ]]; then
        fail "Existing .env has no POSTGRES_PASSWORD. Add it manually before rerunning this installer; changing credentials can prevent an existing database volume from starting."
    fi
    say "Current database settings: user=$POSTGRES_USER, database=$POSTGRES_DB, host port=$APP_PORT"
    say "The database username, database name, and password will be kept as-is."
    APP_PORT="$(prompt_default "Host port for the API" "$APP_PORT")"
else
    say "No .env exists. A new database password will be generated automatically."
    POSTGRES_USER="$(prompt_default "PostgreSQL username" "cl")"
    POSTGRES_DB="$(prompt_default "PostgreSQL database name" "cl")"
    APP_PORT="$(prompt_default "Host port for the API" "5002")"
    POSTGRES_PASSWORD="$(openssl rand -hex 24)"
fi

[[ "$POSTGRES_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || fail "PostgreSQL username must contain only letters, numbers, and underscores, and cannot start with a number."
[[ "$POSTGRES_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || fail "PostgreSQL database name must contain only letters, numbers, and underscores, and cannot start with a number."
[[ "$APP_PORT" =~ ^[0-9]+$ ]] && (( APP_PORT >= 1 && APP_PORT <= 65535 )) || fail "APP_PORT must be a port number from 1 to 65535."

if [[ -f .env ]]; then
    backup=".env.backup.$(date +%Y%m%d%H%M%S)"
    cp -p .env "$backup"
    say "Backed up the previous .env to $backup"
fi

umask 077
cat > .env <<EOF
POSTGRES_USER=$POSTGRES_USER
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=$POSTGRES_DB
OPENWEATHER_API_KEY=$OPENWEATHER_API_KEY
APP_PORT=$APP_PORT
EOF
chmod 600 .env
unset OPENWEATHER_API_KEY

say "Configuration saved to .env (permissions restricted to the current user)."

say "Step 3 of 3: Validate configuration and start services"
docker compose config --quiet || fail "Docker Compose configuration validation failed. Review .env and docker-compose.yml."

docker compose up -d --build

API_URL="http://localhost:$APP_PORT/api/v1/health"
say "Waiting for the API health endpoint at $API_URL"
for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error "$API_URL" >/tmp/weather_api_health.json 2>/dev/null; then
        cat /tmp/weather_api_health.json
        printf '\n'
        say "Installation complete."
        say "API: http://localhost:$APP_PORT"
        say "Health: $API_URL"
        say "Try: curl -sS 'http://localhost:$APP_PORT/api/v1/locations?q=Seattle&limit=5'"
        say "Logs: docker compose logs --tail=100 api scheduler"
        exit 0
    fi
    sleep 2
done

say "Containers were started, but the API did not become healthy within 60 seconds."
say "Recent logs:"
docker compose logs --tail=80 api scheduler postgres || true
exit 1
