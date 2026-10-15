# Tower: Airline Complaint Triage Assistant

Week 4 project, CAPACITI x Clickatell AI Bootcamp. A prototype that sorts airline complaints by urgency, suggests a reason, team and draft reply, and leaves every reply to a person.

Tower is the tool. Example Air is the fictional airline it is configured for. Nothing is sent to customers.

## Who uses Tower

Tower serves several airlines from one app. There are four roles:

| Role | Who | Where they sign in | What they do |
| --- | --- | --- | --- |
| **Platform admin** | Whoever runs Tower (the person to contact for technical issues) | The bare web address | Adds airlines and each airline's first administrator, deactivates airlines and users, sees all users, the platform log and a System page |
| **Airline admin** | One or more people at each airline | Their airline's link | Dashboard (complaints by month, reasons, resolved, users), adds and deactivates staff by role, activity log |
| **Team lead** | Senior support staff | Their airline's link | Queue, escalated complaints, Insights, activity log |
| **Support agent** | Support staff | Their airline's link | Queue, draft replies, escalate |

Each airline gets its own links (add them to the app's web address). Airlines never see each other's data.

| Link | What it shows |
| --- | --- |
| `?airline=example-air` | Staff sign-in, branded with the airline's name |
| `?airline=example-air&view=form` | The customer complaint form. The customer gets a reference such as `EX-ABCD2345`. |
| `?airline=example-air&view=status` | The customer enters the reference to see progress and, once a person has approved it, the reply. |

Accounts are created by an administrator, who is shown a temporary password once. The person must choose their own password at first sign-in. Deactivating a person or an airline takes effect on their next click.

### Demo accounts (password: `ExampleAir-2026`)

| Username | Role | Link |
| --- | --- | --- |
| `admin.demo` | Platform admin | Bare address |
| `org.demo` | Airline admin (Example Air) | `?airline=example-air` |
| `lead.demo` | Team lead | `?airline=example-air` |
| `agent.demo` | Support agent | `?airline=example-air` |

Example Air comes with six months of sample complaints so the dashboard has something to show. New airlines start empty.

**Before sharing a live link:** set `PLATFORM_ADMIN_USERNAME` and `PLATFORM_ADMIN_PASSWORD` in the app's secrets (or environment) before the first run, because the demo password is published here. If the database already exists, sign in as `admin.demo` and change the password with the key icon. The platform-admin demo button disappears once the published password is no longer in use. A locked-out platform admin can be recovered with `python reset_admin.py <username>`.

## Email (sign-in details)

When an admin adds a person, the app emails them their sign-in link, username and a temporary password. This needs a mail account. In `.streamlit/secrets.toml` (or the Streamlit Cloud Secrets box) add:

```
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USER = "your.address@gmail.com"
SMTP_PASSWORD = "a Google app password, not your normal password"
SMTP_FROM = "Tower <your.address@gmail.com>"
APP_URL = "https://your-app.streamlit.app"
```

For Gmail, turn on 2-step verification and create an app password. `APP_URL` is the address printed in the emailed links. Without these settings nothing is emailed: the admin is shown the details once, with a button that opens a ready-made email. When an email is sent, the password is not shown on screen.

## What each role sees

| Role | Pages |
| --- | --- |
| Support agent | Queue, with their own numbers (waiting, customers who wrote back, replies they sent) |
| Team lead | Queue (escalations first), **Insights** (the airline's queue, waiting time, reply time by urgency, agents' week, escalations, customers who wrote back), Activity log |
| Airline admin | **Dashboard** (complaints by month, reply time by month, reasons, weekday pattern, team), Staff, Activity log (their own airline only) |
| Platform admin | Overview (all airlines, counts only), Airlines, All users, Platform log, System (including how well the triage model works) |

Customers can reply after they have been answered: the status page keeps the whole conversation, and a reply puts the complaint back in the queue (up to 5 times per complaint).

## How it works

1. A complaint arrives from the form or from replayed tweets (a stand-in for a social feed).
2. Handles, emails and phone numbers are masked.
3. A TF-IDF + logistic regression model suggests the reason with a confidence. Below 50% the complaint is flagged "Needs manual review".
4. Rules set urgency and the suggested team. These are assumptions (see `docs/requirements.md`), not learned from data.
5. A template draft reply is shown. An agent edits and approves it, or escalates.

## Measured results

See the Insights page and `model/metrics.json`. Trained on 7,264 de-duplicated negative tweets and tested on 1,816 unseen ones.

## AI drafts (optional, Gemini)

With a Gemini key, the queue shows an "AI drafts (Gemini)" switch. For a selected complaint, "Summarise and draft with AI" adds a one-sentence summary and a drafted reply. Without a key the switch is off and fixed templates are used, so the app works either way.

1. Create a free key in Google AI Studio (aistudio.google.com, "Get API key").
2. Locally: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste the key. Online: paste the same line into the app's Secrets box. Never commit the key.
3. If the model name stops working, set `GEMINI_MODEL` in the secrets.

Safeguards: the complaint is masked before it is sent; the prompt treats it as untrusted text; replies that promise refunds, compensation or rebooking, give timeframes, contain links or contact details, or are too long are rejected and the template is used; every draft is labelled "Drafted by AI" or "Template"; a person approves every reply.

## Airline settings

Reply templates, urgency rules, team names, blocked words and the confidence threshold are shared by all airlines and live in `airline.json`. Each airline has its own name and sign-off (set when the platform admin adds it). The classifier is not airline-specific.

## Limits

- Data is from 2015, US airlines, English only.
- The reason is wrong about 4 times in 10 overall.
- The sign-in is a prototype: two demo accounts, passwords hashed, no reset or multi-factor.
- Complaints are stored in a SQLite file (`data/complaints.db`). They survive restarts on a laptop, but the file is lost when the app is rebuilt on Streamlit Community Cloud.
- The social media feed is simulated with replayed tweets. Connecting X or Facebook is not built.
- Replies reach customers only through the status page. No email, SMS or social post is sent.

## Documentation
- `docs/journeys.md`: who sees and does what at every stage, and the known limitations
- `docs/responsible-ai.md`: how the AI is kept safe, and its limits
- `docs/roadmap.md`: what is not built yet, including live social channels (Facebook, Instagram, X, WhatsApp), email in, notifications and team queues
- `docs/requirements.md`: requirements and measures

## Run locally

```
pip install -r requirements.txt
streamlit run app.py
python -m pytest tests
```

To retrain: `python train.py path/to/Tweets.csv` (Kaggle "Twitter US Airline Sentiment"; the full file is not in this repo). The sample tweets in `data/replay_sample.csv` come from that public dataset; check its licence on Kaggle before publishing the repository, and note that the tests need a recent Streamlit (they were run on 1.65).

## Activity log and who-did-what
Airline admins and team leads see an **Activity log** page for their airline, and the platform admin sees a Platform log across all airlines. It lists every sign-in, failed sign-in, AI draft, escalation (with the agent's reason), return (with the lead's note) and approval, with who did it and when (UTC). It can be filtered and downloaded as CSV. Each complaint also has a "History of this complaint" panel. The log never records complaint text, passwords or API keys. See `docs/journeys.md` for the table of who sees and does what at each stage, and the list of known limitations.
