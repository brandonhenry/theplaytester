# The Playtester

**Tell your agent to get your game playtested on [theplaytest.io](https://theplaytest.io).**

An open agent skill for **Firstplay**, the app at theplaytest.io. It guides a game from a playable build and an idea for what to learn through a funded listing, recruiting, written feedback, polls and results. It asks for missing details instead of inventing them.

## Install

Tell your agent:

> Install the `theplaytester` skill from https://github.com/brandonhenry/theplaytester and use it to help me get my game playtested on https://theplaytest.io.

Or use the [open agent skills CLI](https://github.com/vercel-labs/skills):

```sh
npx skills add brandonhenry/theplaytester --skill theplaytester
```

Choose your agent in the installer. This installs to the current project; add `-g` if you want it available across projects. Use the CLI's supported Node.js version. You can inspect the skill before installing:

```sh
npx skills add brandonhenry/theplaytester --list
```

For an agent with a different skill installer, point it at this repository. For manual installation, clone/download the repository and place the complete folder—including `SKILL.md`, `references/` and `scripts/`—in the agent's supported skills directory. The Markdown workflow is portable; UI tools, scheduling and approval behavior depend on the host agent. If it has no browser, the skill can prepare drafts and reports but cannot operate the website for you.

## Ask it naturally

- “Get my browser game playtested. Here is the build. I want to understand whether the tutorial is clear. My total budget including fees is $115.”
- “Help me find five testers who have reviewed puzzle games. Show me the candidates before hiring.”
- “Create a free image poll for my latest eligible game comparing these two cover images.”
- “Show me new playtest feedback and poll results since the last report. Separate bugs, usability issues and preferences.”
- “Check every weekday morning for new submissions or votes, and alert me when a review deadline is near.”
- “How do I get a playtester? Can I post polls after my game closes? How do I dispute a rating?”

An agent that supports explicit skill invocation can use `$theplaytester`.

## What it covers

| Workflow | How it helps |
|---|---|
| Intake | Finds missing build, platform, goal, session, questions and budget details; drafts a focused brief |
| Publication | Guides account setup, eligibility, draft creation, server quote, authorized funding and verified publication |
| Recruitment | Reviews actual applications, relevant history/coverage, invitations, hiring confirmations and reserved slots |
| Feedback | Reads real private submissions, summarizes evidence, tracks deadlines, and guides fair approval/correction/dispute decisions |
| Polls | Eligible-game selection, text/image/video choices, public media, publishing, results, pagination and closing |
| Reporting | New/changed applications, submissions, peer ratings, disputes and poll vote deltas, with visibility limits stated |
| Tester help | Onboarding, real gameplay/notes, required written answers, ratings and payout-status guidance |
| Profiles and help | Websites/social coverage, rating disputes, practical Firstplay answers and troubleshooting |
| Follow-up | Uses an actual host scheduler when requested; stays quiet on unchanged runs and preserves authorization limits |

The skill is **100% focused on theplaytest.io**. It does not route people to another testing marketplace. It is open source under the [MIT license](LICENSE); using the Firstplay service still follows its own [terms](https://theplaytest.io/#terms).

## Access and honest limits

Use your own Firstplay account in your agent's supported browser. You do **not** need a platform API key for the browser workflow. You control sign-in, verification, checkout, legal acceptance and Stripe-hosted identity/banking steps under your agent's rules. Installing a skill does not grant access to an account or authorize unlimited spending.

- Firstplay's current funded listings add a 15% fee to the reward budget. The live server quote and availability are authoritative. Free polls require an owned game that was funded/published at least once; it can now be closed.
- Actual people must apply and test; this skill cannot guarantee recruitment or fabricate gameplay, votes, ratings or feedback. Listing publication is not completed playtesting.
- Written game feedback, public participant star ratings and poll votes are separate evidence. Private feedback requires authorized account access.
- An agent must have an actual scheduler to check back later. The repository does not start a background service or send messages by itself.
- The site's current endpoints are not a promised versioned public API. There is no agent-specific key or OAuth-device login to invent. Use the browser when an endpoint changes.
- Automatic recent Twitch/YouTube coverage depends on Firstplay's provider configuration; featured profile videos work separately. Do not infer that linking a channel enables its feed.

## Optional reporting helper

Python **3.10+**, standard library only, no package install required. This helper **never posts to Firstplay or moves money** (it can save local report snapshots):

```sh
python3 scripts/firstplay.py status
python3 scripts/firstplay.py quote --reward 20 --slots 5
python3 scripts/firstplay.py prepare-game /path/to/game.json
python3 scripts/firstplay.py prepare-poll /path/to/poll.json
python3 scripts/firstplay.py report --game-id GAME_ID --snapshot .firstplay/current.json
python3 scripts/firstplay.py report --game-id GAME_ID --previous .firstplay/current.json --snapshot .firstplay/current.json
```

Missing draft fields produce questions; local validation does not submit anything. `report` defaults to public evidence and Markdown; add `--format json` for structured output. The first successful run establishes a baseline rather than calling old activity “new”. Errors leave the last baseline unchanged. Snapshots omit raw feedback and tokens, and are ignored by Git.

For private reporting, use the signed-in website, a deliberately provided token-free `--state-file`, or an existing sanctioned protected `FIRSTPLAY_ID_TOKEN` environment with `--authenticated`. **Do not paste tokens/passwords into chat or pass them on a command line.** The helper does not obtain or refresh tokens or scrape browser storage. See [access](references/access.md) and [reporting](references/reporting.md). Private reports should remain in your chosen private destination.

## Maintain and verify

The skill's website behavior was checked against Firstplay on **2026-10-26**. Live UI/configuration takes precedence over documented defaults. [Verification](VERIFICATION.md) records what was actually tested and what was not.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/firstplay.py --help
```

The CI workflow is configured for Python 3.10 and 3.13; hosted execution was unavailable during publication, so no hosted pass is claimed. Tests are offline; they do not create production games, users, polls or payments. Report behavior changes or improvements through this public repository, without posting private game builds, submissions or account credentials.
