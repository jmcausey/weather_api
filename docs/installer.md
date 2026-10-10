# Interactive Installer

Run `./install.sh` from the repository root. The script gathers the OpenWeatherMap key, asks for environment settings, writes a private `.env`, validates Compose configuration, and starts the services.

## What it automates

1. Checks Docker Compose, `curl`, and `openssl`.
2. Opens the OpenWeatherMap registration page for a new account, or the API keys page for an existing account.
3. Prompts you to complete account registration/email verification in the browser, when needed, and then paste the API key into the terminal. Key input is hidden.
4. Asks for PostgreSQL username/database name and API host port on a fresh installation. It generates a strong database password automatically.
5. Writes `.env` with restrictive file permissions.
6. Runs `docker compose config --quiet`, then `docker compose up -d --build`, and waits for `/api/v1/health`.

## OpenWeatherMap registration is intentionally user-assisted

OpenWeatherMap owns the account-registration and key-management flow. Registration can involve email verification, account checks, or CAPTCHA, so this installer does not attempt to bypass those controls or sign in to your account. It opens the official pages and pauses for you to complete the steps. API keys may take some time to activate after creation.

- [Create an OpenWeatherMap account](https://home.openweathermap.org/users/sign_up)
- [Manage API keys](https://home.openweathermap.org/api_keys)

## Run it

From a terminal in the repository:

```bash
chmod +x install.sh
./install.sh
```

The script requires Docker Engine with the Compose v2 plugin, `curl`, and `openssl`. It supports Linux desktop browsers via `xdg-open` and macOS via `open`; if neither is available, it prints the URL.

## Existing installations and database safety

If `.env` already exists, the installer preserves its PostgreSQL username, password, and database name, asks only for the API port, and backs up the previous file before updating it. This helps avoid breaking access to an already-initialized PostgreSQL volume.

For a fresh installation, the script generates a random database password. Keep the resulting `.env` private and do not commit it. Changing PostgreSQL environment values later does not automatically change credentials stored inside an already-initialized PostgreSQL data directory.

The installer does not run `docker compose down -v`, remove containers, or delete volumes. It does not automatically verify the API key against OpenWeatherMap before starting; the provider may take time to activate a new key. If weather requests fail, inspect logs and try again after the key activates:

```bash
docker compose logs --tail=100 api scheduler
```

## After installation

```bash
docker compose ps
curl -sS http://localhost:5002/api/v1/health
curl -sS 'http://localhost:5002/api/v1/locations?q=Seattle&limit=5'
```

Use the host port you selected in place of `5002`.
