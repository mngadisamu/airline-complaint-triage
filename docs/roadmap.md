# Tower: roadmap and future integrations

What Tower does today, and what is deliberately left for later stages. Nothing on this page is built yet.

## Today (prototype)
- Complaints arrive through a customer web form, or from a simulated feed (a replay of public airline tweets, demo airline only).
- Staff work a queue. A person approves every reply. Replies are shown to the customer on a status page, and the customer can reply back there.
- Several airlines share one app, each with its own links, accounts and data.

## Later stages
| Stage | What it adds | What it needs |
|---|---|---|
| **Social channels, live** | Complaints and comments from Facebook and Instagram pages arrive in the queue as they are posted, and approved replies are posted back on the same channel | A Meta developer app and its review, each airline connecting its own page, webhooks into Tower, tokens stored securely |
| **X (Twitter)** | Mentions of the airline arrive in the queue | A paid X API plan, and the airline's authorisation |
| **WhatsApp Business** | Customers complain and get replies by WhatsApp | A business account and approved message templates |
| **Email in** | Messages sent to an airline's support address appear in its queue | A mailbox Tower can read, and matching replies to the right conversation |
| **Notifications** | The customer is told by email or SMS when a reply is ready | Optional email or phone on the form, and consent |
| **Team queues and assignment** | Complaints go to the suggested team's own queue and to a named person | Team accounts and ownership rules |
| **Live accuracy** | Agents correct the suggested reason, urgency or team, and Insights shows accuracy on real decisions | A correction control in the detail view |
| **Hosted database** | Data survives restarts and several app instances | A managed database in place of the single SQLite file |
| **Real accounts** | Email-based sign-in and password reset, central lockout, session policy | An email service and an identity provider |
| **Data retention** | Complaints are deleted or anonymised after a set period, and on request | A retention policy and a deletion step (POPIA) |
| **Reply deadlines** | Time limits per urgency, with alerts for late complaints | Agreed service levels per airline |

## Rules every integration must keep
1. A person approves every reply before it leaves the system.
2. Personal details are masked before the text reaches the model or the screen.
3. An airline can only ever see its own data, whatever channel the complaint came from.
4. Every action is written to the activity log without recording complaint text, passwords or keys.
5. Each channel's rules and rate limits are respected, and the airline can switch a channel off.
