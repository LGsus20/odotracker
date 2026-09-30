# Odotracker

Odotracker is a Django app to track your personal car expenses and maintenance. Currently, it only supports one car, and there are no plans to add support for more.
Use Docker Compose to run it locally or deploy it behind a Cloudflare Tunnel.

## Run locally

You need Docker with the `docker compose` command. From the project directory, create `.env.dev`:

```dotenv
DEBUG=True
SECRET_KEY=replace-with-a-random-secret
ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SUPERUSER_USERNAME=your-username
DJANGO_SUPERUSER_EMAIL=you@example.com
DJANGO_SUPERUSER_PASSWORD=use-a-strong-password
```

Start the app, create the database tables, then restart so the configured superuser is created:

```bash
docker compose -f docker-compose.dev.yml up --build -d
docker compose -f docker-compose.dev.yml exec web python manage.py migrate
docker compose -f docker-compose.dev.yml restart web
```

Open <http://localhost:8000> and sign in with the superuser credentials above. View logs with `docker compose -f docker-compose.dev.yml logs -f`; stop the app with `docker compose -f docker-compose.dev.yml down`.

## Deploy with Cloudflare Tunnel

### 1. Set up the domain and tunnel

Add your domain to [Cloudflare](https://dash.cloudflare.com/) and create a named tunnel under **Zero Trust → Networks → Tunnels**. Copy the Docker connector token for `.env.prod`. If the domain is registered at Porkbun, change its nameservers there to the ones Cloudflare provides. Review the imported DNS records before switching nameservers.

Add a public hostname to the tunnel, for example `app.example.com`, with service type **HTTP** and URL **`http://caddy:80`**. The hostname must point to Caddy; do not point it at Django on port `8000`.

### 2. Configure production

On the server, create `.env.prod` in the project directory. Generate a random `SECRET_KEY` (for example, with `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`) and use it in the file:

```dotenv
DEBUG=False
SECRET_KEY=replace-with-a-long-random-secret
ALLOWED_HOSTS=app.example.com
CSRF_TRUSTED_ORIGINS=https://app.example.com
DJANGO_SUPERUSER_USERNAME=your-username
DJANGO_SUPERUSER_EMAIL=you@example.com
DJANGO_SUPERUSER_PASSWORD=use-a-strong-password
SITE_DOMAIN=app.example.com
TUNNEL_TOKEN=paste-the-cloudflare-tunnel-token-here
```

Replace `app.example.com` everywhere with your tunnel hostname. `ALLOWED_HOSTS` uses the hostname only; `CSRF_TRUSTED_ORIGINS` includes `https://`. Use a strong password.

Protect the file; it is ignored by Git:

```bash
chmod 600 .env.prod
```

### 3. Deploy

Build, apply migrations, and start the services:

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml up -d
```

Check the tunnel and proxy logs:

```bash
docker compose -f docker-compose.prod.yml logs -f cloudflared caddy
```

Open `https://app.example.com`. A `200` or `302` response is expected.

## Troubleshooting

- **Tunnel/origin error:** Check `docker compose -f docker-compose.prod.yml logs cloudflared caddy` and confirm the tunnel hostname routes to `http://caddy:80`.
- **Django rejects the hostname:** Check that `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, and `SITE_DOMAIN` match the public hostname; recreate the services after changing `.env.prod` with `docker compose -f docker-compose.prod.yml up -d`.
