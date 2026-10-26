# Game intake and publication

Use the live [Firstplay site](https://theplaytest.io) and [creator workspace](https://theplaytest.io/#workspace).

## Turn “get this playtested” into a usable brief

First inspect the game/build information the owner gave you. Ask only for unresolved items, for example:

> I have the game name and browser build. What do you most need to learn, how many players should test it, and what is your total budget including Firstplay’s fee? Is a 20-minute session appropriate, or do you want another length?

If a total budget is supplied, propose tester count/reward combinations within it; do not treat that as a per-tester budget. If no budget is supplied, ask before creating a funded campaign. A free poll is available only for an eligible previously published game, not a substitute way to unlock a first paid listing for free.

The current listing form has **Your game → The playtest → Your budget**:

| Field | Current rules / useful guidance |
|---|---|
| Title | 1–80 characters; actual game name |
| Tagline | Optional, up to 160 characters |
| Description | 1–3,000 characters; genre, premise and build scope |
| Genres | 1–4 relevant tags |
| Platform | The actual supported platform; not an assumed browser build |
| Play URL | Public HTTPS access link without embedded credentials; participants receive private build access after acceptance |
| Cover | Approved image/upload, or Firstplay’s existing default cover |
| Brief | 1–2,000 characters: tasks, build version, success observations, accessibility/content notes and access requirements |
| Creator questions | 1–5, each up to 200 characters; do not duplicate every built-in question |
| Session length | 5–240 minutes |
| Reward | USD $1–$1,000 per tester |
| Slots | 1–100 |

The description, brief and questions are listing material. Do not put reusable build passwords, private personal data or secrets into those fields. If access requires credentials or a key, clarify the supported private handoff with the owner and current site support; do not assume an attachment/secret-delivery feature exists.

A useful brief is specific without steering sentiment: “Play the tutorial from a new save, attempt the first puzzle, and note where you got stuck. Report the platform and build version. We especially want to understand the goal prompt and control mapping.”

Possible additional questions: “Which puzzle instruction was least clear, and what did you expect it to mean?” or “At what moment did you first understand the objective?” Do not demand a positive recommendation or public store review.

## Accounts and pricing

1. Sign in through Firstplay’s Google or email/password flow; create a real profile and verify email.
2. Complete adult/country eligibility and current terms through the site. The user controls legal acceptance.
3. Check current `/api/config` or the live UI. `paidEnabled: false` means new paid work is unavailable even if health says its feature flag is enabled. Do not override or route around this.
4. Calculate an **estimate** in cents: reward budget = reward × slots; fee per slot = round(reward cents × 15%); total = reward budget + slot fees. Five $20 rewards currently quote $100 + $15 = $115. The quote returned by the server is authoritative.
5. Confirm a concrete total against the user’s already-approved spending limit. A fee/rate change or total above that limit requires a decision before checkout.

## Save, fund, verify

Use **Post a playtest** from discovery or the workspace, complete the three form stages, and save the draft. Record its ID and quote. Draft creation does not make it public. Use the site’s funding control and Stripe Checkout when authorized; the user handles financial completion whenever the host requires it.

After Checkout, refresh the workspace/game page. Publication requires the successful signed payment webhook: confirm the game is paid and open, not just a success URL. If the result is uncertain, inspect the same draft/payment before retrying. Return the actual share link `https://theplaytest.io/#game/GAME_ID`.

Recruitment normally ends after 30 days. Accepted tests retain their reservations. Uncommitted rewards plus their corresponding fee are refundable through the original payment; processing is not a promise of instant bank credit. Pausing, reopening, closing/refunding and a new funded round are distinct operations. Ask which outcome is wanted if “stop this” is ambiguous.

A new build can be linked to an existing campaign only if the UI supports the requested edit and it does not silently change accepted work. The current API has no general game-edit command. Do not fabricate one. Plan a clearly identified new round if necessary, with fresh budget authorization.
