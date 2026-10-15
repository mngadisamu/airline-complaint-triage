# Tower: who sees and does what, at every stage

## The four roles
| Role | Can | Cannot |
|---|---|---|
| Platform admin | Add and deactivate airlines, add airline admins, deactivate and reset any user, read the platform log, see the System page | Open any airline's complaint queue or customer replies |
| Airline admin | Dashboard, add/deactivate/reset staff of their airline, activity log | Work the queue, or see another airline |
| Team lead | Queue, decide escalations, Insights, activity log | Manage staff |
| Support agent | Queue, draft, approve, escalate | See Insights, logs or staff |

Every page checks the role again on the server side. Every database query is limited to one airline.
A deactivated user, or one whose password was reset by an admin, is signed out on their next click. Everyone is signed out after an hour without a click. A deactivated airline's staff and customer links stop working at once (the data is kept).
The last active admin of an airline or of the platform cannot be deactivated or demoted, and nobody can deactivate themselves or change their own role.
The shared demo accounts (agent.demo, lead.demo, org.demo) can be changed only by the platform admin, and their password cannot be changed, so a visitor cannot lock others out of the demo.
An account is locked for 5 minutes after 10 wrong passwords in a row, counted on the account, so opening new browser windows does not help a guesser.
Unused temporary passwords stop working after 7 days (an admin sends a new one). Email is never sent for the shared demo airline, and is capped at 30 an hour per airline and 200 a day overall, so the system cannot be used to spam strangers; an airline can add at most 20 people an hour. A customer's reference lookups are slowed after 10 misses. Names cannot contain markup or links. Log exports cannot run spreadsheet formulas. One-time passwords are forgotten as soon as the admin leaves the page.

## Customer replies after an answer
A customer who has been answered sees the conversation and a "Reply to us" box on their status page. Sending it puts the complaint back in the queue as **New**, tagged FOLLOW-UP, with the whole conversation visible to the agent and a follow-up template as the starting draft. If the follow-up sounds urgent the complaint is raised to High. A customer can send at most 5 follow-ups per complaint, and none while the complaint is waiting for a person. Every follow-up and every approved reply is logged. "Time to first reply" always counts to the first approved reply, not later ones.

## Logs
An airline's activity log shows only its own people and customers. Platform admin actions (adding an airline, resetting a password) appear in the platform log only, with the airline they concerned.

## Complaint stages

A complaint moves through four stages. This table is the check that nothing is left undecided for any role.
Every action in the right-hand column is written to the activity log (who, what, when).

| Stage | What the customer sees | What a support agent can do | What a team lead can do | Logged as |
|---|---|---|---|---|
| **1. New** (just received) | "Received". Steps: Received done, Reviewed in progress | Read it, edit the draft reply, use the AI draft, approve, or escalate (with a required reason) | Same as an agent, and can approve directly | `received`, `ai_draft`, `approved` or `escalated` |
| **2. Escalated** (an agent passed it up) | "With a senior team member". Steps: Received and Reviewed done | Read only. Sees who escalated it and why. Cannot approve or escalate again | Sees who escalated it and why. Approve the reply, or return it to the queue with an optional note | `escalated` (with the reason), then `approved` or `returned` |
| **3. Returned** (lead sent it back with a note) | "Reviewed". Reviewed done, reply being prepared | Sees the lead's note. Approves, or escalates again with a new reason | Same as an agent | `returned` (with the note) |
| **4. Approved** | "Replied", with the approved reply. All steps done | Read only. Sees who approved it and when | Read only. Sees who approved it and when | `approved` (as drafted or edited) |

## Rules that hold in every stage
- The customer only ever sees the stage, and the reply once it is approved. Never staff names, notes, reasons, the AI summary or the log.
- Two people cannot overwrite each other. A change is saved only if the complaint is still in the stage the person saw. The late person is told who already handled it.
- Only the team lead decides an escalated complaint. Only the team lead can open Insights. The Activity log is open to the team lead and the airline admin.
- The public form accepts at most 5 complaints per visitor and 30 in total per 10 minutes.
- The log records sign-ins, failed sign-ins (the username only when it is a real account, never the password), AI drafts (success or failure), escalations, returns and approvals. It never records complaint text, passwords or API keys.

## Known limitations (deliberate, for a prototype)
| Limit | Why it is acceptable here | What a real version would add |
|---|---|---|
| "Suggested team" is advice on screen. Nothing is routed to a team queue. | Routing needs team accounts and ownership | Team queues and assignment |
| Replies are not sent to the customer. They appear on the status page only. | No Twitter or email integration | Reply by the channel the complaint came from, with a notification |
| The social feed is simulated from a public dataset. | No real inbound channel | A real feed or an email and web-form intake |
| An approved reply cannot be withdrawn or amended. | Scope | "Withdraw" and "Send a correction", both logged |
| Agents cannot correct the suggested reason, urgency or team. | Scope | A correction control, with corrections feeding live accuracy on Insights |
| Insights shows the model's test-set accuracy, not accuracy on live decisions. | Needs the correction control above | Live accuracy from agent corrections |
| No reply deadlines or late warnings. | Scope | Time limits per urgency, with alerts |
| The same customer can file twice and get two references. | Scope | Duplicate detection |
| A customer who loses the reference and the link cannot get back to the complaint. | No email or phone on the form | Optional email on the form, and a "send me my reference" step |
| English only. | The model was trained on English tweets | Language detection and routing to a person |
| A username is unique across all airlines, so an airline admin can learn that a username exists elsewhere when it is refused. | Sign-in is by username | Usernames scoped to each airline, or sign-in by email |
| An airline's name and sign-off cannot be edited after it is created. | Scope | An edit control for the platform admin |
| A determined attacker can fill an airline's public form quota (30 per 10 minutes) and block real customers. | No captcha in a prototype | Captcha or sign-in-by-email for customers |
| No retention or deletion of complaint data. | Scope | A retention period and a delete-on-request step (POPIA) |
| If every platform admin loses their password, recovery needs `python reset_admin.py <username>` on the machine that holds the database. | No email service | Email-based reset |
| Emailed sign-in details contain a temporary password in plain text. | A temporary password is forced to change at first use and expires after 7 days | Single-use sign-in links instead of passwords |
| Pages load every complaint of an airline on each click. | Fine for hundreds of complaints | Database queries that fetch only what a page shows |
| The customer is not told by email or SMS when a reply is ready. | No contact details are collected | Optional email on the form, and a notification |
| Emails and names of staff are stored as plain text and visible to that airline's admin and the platform admin. | Needed to send sign-in details | A retention and access policy (POPIA) |
| Demo sign-in: published password, lockout resets per browser session, no session timeout. | A demo needs open access | Real accounts, central lockout, session timeout |
| On the hosted version the data and log reset when the app restarts, so old status links stop working. | Free hosting has no permanent disk | A hosted database |
| The log can be edited by anyone with access to the database file. | Single-file demo database | An append-only store, with access controls |
