# Tower: responsible AI considerations

## What the AI does, and what it does not
- A text classifier suggests a **reason** for each complaint. Urgency and team come from written rules (`airline.json`), not from the model.
- An optional language model (Gemini) writes a one-line summary and a draft reply.
- **A person approves every reply.** Nothing is sent or shown to a customer until someone approves it. The AI never acts on its own.

## Honest about accuracy
- The classifier picks the right reason about 63% of the time on tweets it had not seen. Guessing the most common reason scores 32%.
- When it is at least 50% sure it is right about 79% of the time, and it makes a suggestion for 60% of complaints. Below that, the complaint is marked "Needs review" and no reason is suggested. A person must tick "I have read this complaint" before approving it.
- These numbers are shown on the platform admin's System page, not hidden.

## Guardrails on generated replies
- The complaint is treated as untrusted data. The prompt tells the model never to follow instructions inside it.
- A reply is rejected, and the fixed template used instead, if it promises a refund, compensation, rebooking or a time frame, contains a link, email address, phone number or "@", is too long, or is not signed as the airline.
- The same blocked-word check runs again on whatever the agent types before the Approve button works, and again on the server when it is clicked.
- If the AI is unavailable or fails any check, the template reply is used. The system still works with no AI at all.

## Privacy
- Handles, email addresses and phone numbers are masked before the text is stored, shown, or sent to the language model.
- The form asks customers not to include card numbers or passwords.
- The activity log records who did what and when, never complaint text, passwords or keys.
- Each airline's data is separate. One airline cannot see another's complaints, users or logs, and the platform admin sees only counts, never complaint text.
- Staff emails are stored so sign-in details can be sent. A real deployment needs a retention policy and deletion on request (POPIA). Not built.

## Fairness and limits
- The model was trained on 2015 English tweets from US airlines. It may work worse on other languages, dialects, South African English, or non-Twitter writing. English is the only supported language.
- Urgency is a rule list, so it can miss an urgent complaint written in unusual words. The team lead can see waiting times and reply time by urgency to spot this.
- Customers cannot see why a complaint was rated as it was, and staff can see the reason but cannot yet correct it (listed in the roadmap).
- The training data comes from a public Kaggle dataset. Check its licence before publishing the repository.

## Security choices that support responsible use
- Passwords are salted and hashed, accounts lock after repeated wrong passwords, and sessions end after an hour without a click.
- Deactivating a person or an airline takes effect on their next click.
- Temporary passwords expire after 7 days, and sign-in emails are capped so the system cannot be used to spam people.
- A prototype uses shared demo accounts with a published password. A live deployment must set its own platform admin password.

## Human oversight in one line
The AI suggests, the agent decides, the team lead handles what the agent escalates, and the customer only ever sees what a person approved.
