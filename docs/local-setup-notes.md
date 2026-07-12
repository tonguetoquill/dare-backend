# Local Setup Notes (ttq-spike)

Field notes from standing this stack up from a fresh clone (July 2026). Complements
[INSTALL.md](../INSTALL.md).

## 1. `DB_PASSWORD` is required

`.example.env` ships without a value, and `docker-compose.yml` uses
`${DB_PASSWORD:?set_DB_PASSWORD}` — every `docker compose` command fails until you set
it in `.env` (e.g. `DB_PASSWORD=darelocal`).

## 2. Secrets via `docker-compose.override.yml`

Compose merges `docker-compose.override.yml` automatically, and it is gitignored on
this branch — a convenient place for local secrets instead of editing `.env`:

```yaml
services:
  web:
    environment:
      DJANGO_DEBUG: "True"
      ENVIRONMENT: local
      DJANGO_SECRET_KEY: <generate one>
      DB_PASSWORD: darelocal
      CLAUDE_API_KEY: sk-ant-...
    volumes:
      - .:/app
  worker:
    environment: # same as web
    volumes:
      - .:/app
```

Mounting `.:/app` gives hot reload in both containers. Provider env var names are
`CLAUDE_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` (see `config/env.py` — the
README's `ANTHROPIC_API_KEY`/`GOOGLE_API_KEY` mentions are stale).

## 3. Superuser login requires a verified email

`createsuperuser` alone cannot log in through the frontend — django-allauth rejects
unverified emails and there is no local mail server. After creating the superuser:

```bash
docker compose exec web python manage.py shell -c "
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(email='<your email>')
EmailAddress.objects.update_or_create(user=u, email=u.email, defaults={'verified': True, 'primary': True})
"
```

Note the custom `User` model has no `username` field — look users up by `email`.

## 4. Model catalog

Migration `conversations/0078_fix_claude_model_catalog` deactivates Claude model IDs
that Anthropic has retired and fixes zero-cost token rates. If you only configure one
provider key, consider deactivating the other providers' rows so the picker only
offers models that work:

```bash
docker compose exec web python manage.py shell -c "
from conversations.models import LLM
LLM.objects.filter(provider__in=['openai','gemini']).update(is_active=False)
"
```

(Leaving them active with no key breaks chat sends and conversation titles.)

## 5. Wallet credit

New users start at \$0.00 and billing pre-checks block chat. Top up locally:

```bash
docker compose exec web python manage.py shell -c "
from decimal import Decimal
from django.contrib.auth import get_user_model
from billing.services import WalletService
u = get_user_model().objects.get(email='<your email>')
WalletService.add_topup(u, amount=Decimal('100.00'), message='local dev top-up')
"
```

## 6. Health checks

```bash
curl http://localhost:8000/api/health/   # liveness
curl http://localhost:8000/api/ready/    # DB + Redis
```
