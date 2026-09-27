# Bot Desk – backend

Bot Desk runs WhatsApp AI assistants for local businesses in India (clinics, salons, bakeries, coaching
centres, gyms, real-estate agents). For each client business it:

1. receives customer WhatsApp messages,
2. replies automatically with AI, using only that business's approved knowledge, in the customer's language,
3. captures leads and bookings, and hands the chat to a human when needed,
4. manages clients, packages, payments, renewals and monthly reports.

Stack: Python 3.11+ · FastAPI · SQLAlchemy 2.0 (async, asyncpg) · Alembic · PostgreSQL 16 · Pydantic v2 ·
httpx · APScheduler · OpenRouter (AI) · Meta WhatsApp Cloud API or AiSensy (transport).

---

## 1. Local setup

Uses a local PostgreSQL (no Docker). Create the database once:

```bash
createdb -U postgres bots_db_v1
```

Then:

```bash
cd backend
uv sync                          # creates .venv with Python 3.11+ and dev tools
cp .env.example .env             # DATABASE_URL points at the local bots_db_v1; set the keys below
uv run alembic upgrade head
uv run python -m app.seed        # admin user (ADMIN_EMAIL / ADMIN_PASSWORD from .env), example client, sample knowledge
uv run uvicorn app.main:app --reload
```

API: http://localhost:8000 · OpenAPI docs: http://localhost:8000/docs · health: `GET /health`.

In `.env`, set `FERNET_KEY`, `JWT_SECRET`, `ADMIN_PASSWORD`, `OPENROUTER_API_KEY`, and `META_APP_SECRET` +
`META_WEBHOOK_VERIFY_TOKEN` (for the default `own` provider). Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Tests and lint

Tests need a PostgreSQL database they can wipe (the schema is dropped and rebuilt with the Alembic migrations):

```bash
createdb -U postgres bots_db_v1_test
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bots_db_v1_test
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

All HTTP calls to Meta, AiSensy and OpenRouter are mocked with `respx`. CI runs the same in
`.github/workflows/backend.yml` with a Postgres 16 service.

---

## 2. Environment variables

All settings are read through `app/config.py` (`Settings`). The app **refuses to start** if a key required
by the active default provider or by the AI is missing, and says which.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `dev` | `dev`, `prod` or `test`. In `prod`, `JWT_SECRET=change-me` blocks startup. |
| `APP_BASE_URL` | – | Public HTTPS base URL. Used to build webhook URLs shown in the channel screen. |
| `DATABASE_URL` | – | `postgresql+asyncpg://user:pass@host:5432/db` (**required**) |
| `JWT_SECRET` | `change-me` | HS256 secret for admin tokens (**required**) |
| `JWT_EXPIRE_MINUTES` | `10080` | Token lifetime (7 days) |
| `FERNET_KEY` | – | Encrypts client secrets at rest (**required**). Changing it makes stored tokens unreadable. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | – | First admin, created by `python -m app.seed` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed origins |
| `LOG_LEVEL` | `INFO` | JSON logs with request id; phone numbers masked to the last 4 digits |
| `SCHEDULER_ENABLED` | `true` | Run APScheduler jobs in this process (turn off on extra replicas) |
| `WHATSAPP_PROVIDER` | `own` | Default provider: `own` (Meta Cloud API) or `aisensy`. Per-client override wins. |
| `META_GRAPH_BASE` | `https://graph.facebook.com` | Graph API host |
| `META_GRAPH_VERSION` | `v23.0` | Graph API version – keep current |
| `META_APP_SECRET` | – | Verifies `X-Hub-Signature-256` (**required for `own`**) |
| `META_WEBHOOK_VERIFY_TOKEN` | – | Any random string; also typed into Meta's webhook screen (**required for `own`**) |
| `AISENSY_API_BASE` | `https://apis.aisensy.com/project-apis/v1` | AiSensy Project API base |
| `OPENROUTER_API_KEY` | – | OpenRouter key (**required**) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint |
| `AI_MODEL` | `google/gemini-3.7-flash` | Primary model |
| `AI_FALLBACK_MODEL` | `deepseek/deepseek-v4.1-flash` | Used once when the primary times out, errors, or returns bad JSON |
| `AI_MAX_OUTPUT_TOKENS` | `400` | |
| `AI_TEMPERATURE` | `0.3` | |
| `AI_HISTORY_TURNS` | `12` | Previous messages sent with each request |
| `AI_TIMEOUT_SECONDS` | `25` | Per model call |
| `USD_TO_INR` | `88` | Cost reporting only |
| `BOT_REPLY_MAX_WORDS` | `60` | Replies are trimmed to this, at a sentence end where possible |
| `HANDOFF_AUTO_RELEASE_HOURS` | `12` | Handoff is released after this long without agent/customer messages |
| `NIGHT_START_HOUR` / `NIGHT_END_HOUR` | `22` / `8` | IST window for "night enquiries" |
| `OWNER_ALERT_TEMPLATE` | `new_lead_alert` | Approved utility template for owner alerts outside 24 h |
| `OWNER_ALERT_TEMPLATE_LANG` | `en` | Template language code |
| `TRIAL_DAYS` | `7` | Trial length (for "trial ending" reminders) |
| `WEBHOOK_RATE_PER_SEC` / `WEBHOOK_RATE_BURST` | `20` / `100` | Per-IP token bucket on webhook routes |

Per-client WhatsApp credentials (Meta phone number id, WABA id, access token; AiSensy project id, API
password, webhook secret) are stored **in the database, Fernet-encrypted**, and never returned by the API
(responses show `has_token` and the last 4 characters only).

---

## 3. How a message flows

```
Meta / AiSensy ──POST──▶ /webhooks/...  verify signature ▸ store raw event (webhook_events) ▸ 200 OK
                                              │ background task
                                              ▼
            parse with the provider ▸ route to client/channel ▸ per-contact lock (in order)
                                              ▼
 1 skip duplicates (provider_message_id)      7 parse JSON tolerantly, validate with Pydantic
 2 upsert contact, save message, mark read    8 guardrails: prices, links, phones, 60 words
 3 silent if bot off / paused / opted out /   9 send reply via provider, log model/tokens/cost/latency
   handoff; STOP / START keywords            10 lead ▸ create/update one open lead ▸ alert owner
 4 knowledge approved? (live clients only)   11 handoff ▸ mark contact ▸ alert owner
 5 build prompt + last 12 messages
 6 OpenRouter AI_MODEL ▸ fallback model once ▸ polite fallback + owner alert
```

Non-text messages (image, audio, location) are stored and answered once with "a team member will check
this". Delivery/read/failed statuses update the matching outbound message.

Code map: `app/services/inbound.py` (pipeline), `app/services/ai/` (prompt, OpenRouter, guardrails),
`app/services/providers/` (the only code that knows about Meta or AiSensy), `app/services/alerts.py`,
`app/services/billing.py`, `app/services/reports.py`, `app/jobs/`.

---

## 4. Meta Cloud API setup for one client (`own` provider)

1. **Business portfolio.** At business.facebook.com create (or use) the client's Meta Business portfolio.
   Start business verification early; it raises messaging limits and is needed for a display name.
2. **App.** At developers.facebook.com → *Create app* → use case *Connect with customers through WhatsApp*
   (type *Business*) → link the business portfolio. Copy **App settings → Basic → App secret** into
   `META_APP_SECRET`. Create this app **once**: webhook signatures are checked with a single app secret, so every
   client's WhatsApp account must be connected to this same app (the client's WABA can live in your portfolio,
   or the client adds your business as a partner and shares the WABA with your app).
3. **Phone number.** WhatsApp → *API Setup* → *Add phone number*. Use a number that is **not** active on the
   WhatsApp app (or delete it there first – see known limits). Verify by SMS/voice, set the display name.
   Copy the **Phone number ID** and **WhatsApp Business Account ID**.
4. **Permanent token.** Business settings → *Users → System users* → add an admin system user →
   *Assign assets*: the app and the WhatsApp account (full control) → *Generate token* for the app, expiry
   *Never*, permissions `whatsapp_business_messaging` and `whatsapp_business_management`.
5. **Webhook.** WhatsApp → *Configuration* → Callback URL `{APP_BASE_URL}/webhooks/meta`, Verify token =
   `META_WEBHOOK_VERIFY_TOKEN` → *Verify and save*. Under *Webhook fields* subscribe to **`messages`**.
   Make sure the app is subscribed to the WABA:
   ```bash
   curl -X POST "https://graph.facebook.com/v23.0/<WABA_ID>/subscribed_apps" -H "Authorization: Bearer <TOKEN>"
   ```
6. **Payment method.** Add one in WhatsApp Manager; template messages (owner alerts outside 24 h) are billed.
7. **Owner alert template.** WhatsApp Manager → *Message templates* → *Create*: category **Utility**, name
   **`new_lead_alert`**, language **English (en)**, body with exactly four variables, for example:
   > New enquiry for your business. Customer: {{1}} ({{2}}). Details: {{3}}. Received: {{4}}. Please reply on WhatsApp.

   Bot Desk fills them with [customer name, customer number, need/reason, time in IST]. Wait for approval.
8. **Go live.** Publish the app (needs a privacy-policy URL).
9. **In Bot Desk:** `PUT /api/v1/clients/{id}/channel` with `meta_phone_number_id`, `meta_waba_id`,
   `meta_access_token`, `display_phone`. The response shows the webhook URL to paste in step 5.
   Then `POST /api/v1/clients/{id}/channel/test` – it sends "Bot Desk test message ✅" to the owner's phone.
   (It is a free-form message, so the owner must have messaged the business number in the last 24 hours;
   otherwise Meta returns error 131047. Ask the owner to send "hi" first.)
10. Fill and approve the knowledge (`PUT` then `POST .../knowledge/approve`), try it in the simulator
    (`POST .../test-chat`), then set the client to `trial` or `live`.

---

## 5. AiSensy setup (`aisensy` provider)

The client keeps AiSensy's inbox app (and coexistence with the WhatsApp Business app, if AiSensy set it up);
Bot Desk writes the replies with its own AI through AiSensy's **Project API**. You do **not** need AiSensy's AI
add-on. **The Project API may need a specific AiSensy plan – confirm with AiSensy before selling this.**

1. From AiSensy get the **Project ID** and the **Project API password** (API key) for the client's project.
2. In Bot Desk set the client's `provider_override` to `aisensy` (or set `WHATSAPP_PROVIDER=aisensy` for all),
   then `PUT /api/v1/clients/{id}/channel` with `aisensy_project_id`, `aisensy_api_key` and, if AiSensy gives
   you one, `aisensy_webhook_secret`.
3. `GET /api/v1/clients/{id}/channel` shows `webhook_url` = `{APP_BASE_URL}/webhooks/aisensy/{channel_token}`.
   Register it as the **Project Webhook** in AiSensy and subscribe to incoming messages and message status
   updates (and agent/outgoing message events, if offered – see takeover below).
   The token is random per channel and identifies the client; rotate it with `"rotate_channel_token": true`.
4. `POST /api/v1/clients/{id}/channel/test` to send a test message to the owner.

**Human takeover.** When AiSensy reports a message sent by a human agent from its inbox, Bot Desk logs it as an
`agent` message and sets `handoff_active` for that contact, so the bot stays quiet until the handoff is
released (automatically after `HANDOFF_AUTO_RELEASE_HOURS`, or by hand).

### AiSensy: verified vs assumed

AiSensy's Stoplight docs require a login, so the adapter was built from what their public doc pages expose plus
tolerant parsing. Every path, header and field name is in the constants block at the top of
`app/services/providers/aisensy.py`; adjust there if anything differs.

| Item | Status | Value used |
|---|---|---|
| Send URL | confirmed (public doc snippet) | `POST {AISENSY_API_BASE}/project/{project_id}/messages` |
| Auth header | confirmed | `X-AiSensy-Project-API-Pwd: <project API password>` |
| Send body / response | confirmed as Meta-like | `{"to","type":"text","recipient_type":"individual","text":{"body"}}` → `messages[0].id` |
| Webhook signature | confirmed header name | `X-AiSensy-Signature`: HMAC-SHA256 of the raw body; hex, `sha256=`hex and base64 accepted. Only enforced when a secret is saved. |
| Webhook payload | **assumed**, parsed tolerantly | `{"topic", "data": {"message": {id, phone_number, message_type, message_content.text, sender, status, userName}}}`; Meta-shaped `entry[]` payloads are also accepted |
| Topics | **assumed** | inbound: `message.sender.user`; status: `message.status.updated`; `sender` = `AGENT` means a human agent |
| Mark as read | not available in the documented API | no-op (`MARK_READ_PATH = None`) |
| Templates | **assumed** Meta-like | `{"type":"template","template":{"name","language","components"}}` |

Check the first real webhook in `webhook_events.payload` (kept for 30 days) and adjust the constants if needed.

---

## 6. Switching providers

`effective_provider(client) = client.provider_override or WHATSAPP_PROVIDER`. All sending and receiving goes
through `get_provider(client)`; nothing outside `app/services/providers/` knows which provider is in use.

- Move **one** client: `PATCH /api/v1/clients/{id}` with `{"provider_override": "aisensy"}` (or `"own"`), save
  that provider's credentials in the channel, and point that provider's webhook at the new `webhook_url`.
- Move **everyone** without an override: change `WHATSAPP_PROVIDER` and restart (the startup check then asks for
  the new provider's required keys).

A WhatsApp number can only be connected to one platform at a time, so moving a live number between Meta direct
and AiSensy means re-registering it with the new provider.

---

## 7. Prices and guardrails

The system prompt (`app/services/ai/prompts.py`, tuned wording) restricts the model to the approved knowledge.
After the model replies, and before anything is sent (live and test-chat alike):

1. **Price check.** Every rupee amount in the reply (`₹1,200`, `Rs. 300`, `INR 4500`) must appear as a number
   in the knowledge's *services* or *FAQs*. If one doesn't, the whole reply is replaced with "Let me confirm the
   exact price with the team and get back to you shortly." (in the customer's language) and the chat is handed
   to a human with the reason.
2. **Links** that are not in the knowledge are removed.
3. **Phone numbers** that are not in the knowledge are removed (the customer's own number and numbers they
   typed are allowed, so the bot can repeat booking details back).
4. **Length.** Replies are trimmed to `BOT_REPLY_MAX_WORDS`, cut at a sentence end where possible.

Other rules: knowledge must be **approved** before a `live` client's bot answers (trial/lead clients get
replies in demo mode). Saving changes to services, FAQs or rules resets approval. Every save is a new version
and can be restored. `STOP`, `நிறுத்து`, `रोको` opt a customer out (one confirmation, then silence); `START`
opts back in.

## 8. Billing rules

In `app/services/billing.py` (unit-tested): the first monthly fee is due on `live_date`, then on the same day
every month (clamped to the month's last day: 31 Jan → 28/29 Feb → 31 Mar). For the latest due date P ≤ today
(IST): unpaid → `due` for 0–3 days, then `overdue`; paid → `due` if the next date is within 5 days, else `paid`.
A future `live_date` is `upcoming`. `setup_paid` = any payment of type `setup`.

## 9. Scheduled jobs (IST)

| When | Job |
|---|---|
| every 15 min | release handoffs idle for `HANDOFF_AUTO_RELEASE_HOURS` |
| daily 09:00 | attention items: trials ending in ≤ 2 days, payments due/overdue, channels with no inbound for 3 days |
| nightly 02:30 | drop raw `webhook_events.payload` older than 30 days (rows kept) |

Undelivered owner alerts also appear in the dashboard's `attention` list.

---

## 10. Known limits

- **24-hour window.** Free-form messages (bot replies, agent replies, owner alerts as text) are only allowed
  within 24 hours of the recipient's last message. Agent replies outside it return `409 outside_24h_window`;
  owner alerts fall back to the approved `new_lead_alert` template.
- **Coexistence.** A number registered directly on the Meta Cloud API cannot stay on the WhatsApp Business app.
  Keeping the app and the API on one number ("coexistence") needs AiSensy (or another Meta Tech Provider) or
  Bot Desk becoming a Meta Tech Provider itself.
- **Single process.** Per-contact ordering uses an in-process asyncio lock and the webhook rate limit is in
  memory. Run one API process (or move both to Postgres advisory locks / Redis before scaling out), and keep
  `SCHEDULER_ENABLED=true` on exactly one instance.
- **Background tasks** run inside the API process. If it is killed mid-processing, the event stays in
  `webhook_events` with `processed_at = NULL` for inspection or replay.
- **Media** is not downloaded; the message is stored with its caption or type and a person follows up.
- **AiSensy** payload details are partly assumed (see section 5) and the Project API may need a paid plan.
