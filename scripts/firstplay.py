#!/usr/bin/env python3
"""Read-only Firstplay reports and local draft checks. Python 3.10+, standard library only."""
from __future__ import annotations
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib import error, parse, request

ORIGIN = "https://theplaytest.io"
MAX_BYTES = 5_000_000
ID = re.compile(r"^[a-zA-Z0-9_-]{1,140}$")

class FirstplayError(Exception):
    pass

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class Client:
    def __init__(self, token=None):
        self.token = token
        self.opener = request.build_opener(NoRedirect())

    def get(self, route, params=None):
        if route not in {"config", "state", "polls", "ratings"}:
            raise FirstplayError("Only supported read-only endpoints are allowed.")
        url = ORIGIN + "/api/" + route
        if params:
            url += "?" + parse.urlencode(params)
        headers = {"Accept": "application/json", "User-Agent": "theplaytester/1.0"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with self.opener.open(request.Request(url, headers=headers), timeout=15) as res:
                data = res.read(MAX_BYTES + 1)
        except error.HTTPError as exc:
            if exc.code in (401, 403):
                raise FirstplayError("Account access was rejected or expired. Sign in through Firstplay; the previous baseline is unchanged.") from None
            if 300 <= exc.code < 400:
                raise FirstplayError("Firstplay redirected the request. No redirect or credential forwarding was allowed.") from None
            raise FirstplayError(f"Firstplay returned HTTP {exc.code}; the previous baseline is unchanged.") from None
        except (error.URLError, TimeoutError, OSError):
            raise FirstplayError("Firstplay could not be reached; the previous baseline is unchanged.") from None
        if len(data) > MAX_BYTES:
            raise FirstplayError("Response too large; use the signed-in workspace for this report.")
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError):
            raise FirstplayError("Firstplay did not return valid JSON; use the browser and check for a service change.") from None
        if not isinstance(result, dict) or "error" in result:
            raise FirstplayError("Firstplay returned an unexpected response; no baseline was updated.")
        return result

def read_json(path):
    try:
        data = Path(path).read_bytes()
        if len(data) > MAX_BYTES:
            raise FirstplayError("Local JSON exceeds the 5 MB limit.")
        return json.loads(data)
    except (OSError, ValueError, UnicodeError):
        raise FirstplayError("Could not read the local JSON file.") from None

def atomic_json(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".firstplay-", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def cents(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number != number.quantize(Decimal("0.01")):
            raise FirstplayError("Use a USD amount with at most two decimal places.")
        return int(number * 100)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise FirstplayError("Use a finite USD amount with at most two decimal places.") from None

def quote(reward, slots):
    reward_cents = cents(reward)
    if not 100 <= reward_cents <= 100000 or isinstance(slots, bool) or not isinstance(slots, int) or not 1 <= slots <= 100:
        raise FirstplayError("Reward must be $1–$1,000 and slots an integer from 1–100.")
    fee = (reward_cents * 1500 + 5000) // 10000
    return {"currency": "usd", "reward_cents": reward_cents, "slots": slots,
            "reward_budget_cents": reward_cents * slots, "fee_cents": fee * slots,
            "total_cents": (reward_cents + fee) * slots,
            "authoritative": False, "note": "Estimate at the documented 15% rate. Use the site's current server quote before funding."}

def https(value):
    if not isinstance(value, str):
        return False
    try:
        u = parse.urlsplit(value)
        return u.scheme == "https" and bool(u.hostname) and not u.username and not u.password
    except (ValueError, TypeError):
        return False

def prepare_game(data):
    if not isinstance(data, dict):
        raise FirstplayError("Game draft must be a JSON object.")
    prompts = {
        "title": "What is the game's name?", "description": "How should the game and this build be described?",
        "genres": "Which 1–4 genres fit it?", "platform": "Which platform/device can testers use?",
        "playUrl": "What HTTPS build/access URL can accepted testers use?", "brief": "What should testers do and what do you want to learn?",
        "questions": "Which 1–5 additional questions should they answer?", "minutes": "How long should each session last (5–240 minutes)?",
        "reward": "What is the USD reward per tester, or the approved total budget including the fee?",
        "slots": "How many testers do you want (1–100)?",
    }
    missing = [key for key in prompts if data.get(key) in (None, "", []) or (isinstance(data.get(key),str) and not data[key].strip())]
    errors = []
    for field, maximum in {"title":80, "description":3000, "brief":2000, "platform":60, "tagline":160}.items():
        if field in data and (not isinstance(data[field], str) or len(data[field].strip()) > maximum):
            errors.append(f"{field}: use text up to {maximum} characters.")
    genres = data.get("genres")
    if genres is not None and (not isinstance(genres,list) or not 1 <= len(genres) <= 4 or any(not isinstance(x,str) or not x.strip() or len(x.strip()) > 30 for x in genres)):
        errors.append("genres: choose 1–4 nonempty labels of at most 30 characters.")
    questions = data.get("questions")
    if questions is not None and (not isinstance(questions,list) or not 1 <= len(questions) <= 5 or any(not isinstance(q,str) or not q.strip() or len(q.strip()) > 200 for q in questions)):
        errors.append("questions: provide 1–5 nonempty questions of at most 200 characters.")
    if "playUrl" in data and not https(data["playUrl"]):
        errors.append("playUrl: use an HTTPS URL without embedded credentials.")
    if "art" in data and not (https(data["art"]) or data["art"] == "/art/default-cover.svg"):
        errors.append("art: use an approved HTTPS image or the site's default cover.")
    if "minutes" in data and (isinstance(data["minutes"],bool) or not isinstance(data["minutes"],int) or not 5 <= data["minutes"] <= 240):
        errors.append("minutes: use an integer from 5–240.")
    estimate = None
    if "reward" in data and "slots" in data:
        try:
            estimate = quote(data["reward"], data["slots"])
        except FirstplayError as exc:
            errors.append(str(exc))
    return {"ready_for_site_draft": not missing and not errors, "missing":missing,
            "ask": [prompts[k] for k in missing], "errors":errors, "estimate":estimate,
            "submitted":False, "next":"Review the draft with the owner, then use Post a playtest on theplaytest.io. No money has moved."}

def prepare_poll(data):
    if not isinstance(data,dict):
        raise FirstplayError("Poll draft must be a JSON object.")
    errors, missing = [], []
    for key in ("gameId","question","format","options"):
        if not data.get(key):
            missing.append(key)
    if data.get("gameId") and not ID.fullmatch(str(data["gameId"])):
        errors.append("Choose a valid existing owned game's ID.")
    question = data.get("question", "")
    if not isinstance(question,str) or (question and not 5 <= len(question.strip()) <= 240):
        errors.append("question: use 5–240 characters.")
    description = data.get("description", "")
    if not isinstance(description,str) or len(description) > 1000:
        errors.append("description: use up to 1,000 characters.")
    fmt, options = data.get("format"), data.get("options", [])
    if fmt and fmt not in ("text","image","video"):
        errors.append("format: choose text, image or video.")
    if not isinstance(options,list):
        errors.append("options: provide a list.")
        options = []
    if options and not 2 <= len(options) <= 6:
        errors.append("options: provide 2–6 choices.")
    labels, media = [], [data.get("media")]
    for option in options:
        if not isinstance(option,dict) or not isinstance(option.get("text"),str) or not 1 <= len(option["text"].strip()) <= 160:
            errors.append("Each option needs a text label of 1–160 characters.")
            continue
        labels.append(option["text"].strip().casefold())
        media.append(option.get("media"))
    if len(labels) != len(set(labels)):
        errors.append("Use distinct option labels.")
    attachments = [m for m in media if m is not None]
    if fmt == "text" and attachments:
        errors.append("Text polls have no media attachments.")
    if fmt in ("image","video") and not attachments:
        errors.append("Attach matching media to the question or choices.")
    for attachment in attachments:
        if not isinstance(attachment,dict) or attachment.get("type") != fmt or not https(attachment.get("url")):
            errors.append("Media must match the chosen format and use credential-free HTTPS.")
    return {"ready_for_site_draft":not missing and not errors, "missing":missing, "errors":errors,
            "eligibility_verified":False, "submitted":False,
            "next":"Select an owned game previously funded/published on theplaytest.io, check that game's eligibility, review the public question/options/media, then create the poll."}

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def all_polls(client, game_id, max_pages=100):
    polls, cursor, seen = {}, None, set()
    for _ in range(max_pages):
        params = {"gameId":game_id}
        if cursor:
            params["before"] = cursor
        page = client.get("polls",params)
        if not isinstance(page.get("polls"),list):
            raise FirstplayError("Poll response changed; no snapshot updated.")
        for poll in page["polls"]:
            if poll.get("gameId") != game_id or not isinstance(poll.get("id"),str):
                raise FirstplayError("Unexpected poll scope; no snapshot updated.")
            polls[poll["id"]] = poll
        cursor = page.get("nextCursor")
        if not cursor:
            return list(polls.values())
        if cursor in seen:
            raise FirstplayError("Poll pagination repeated a cursor; results are incomplete and no snapshot was updated.")
        seen.add(cursor)
    raise FirstplayError("Poll page limit reached; results are incomplete. Use the browser; no snapshot updated.")

def build_report(state, polls, game_id, config, include_feedback=False, now=None, source_mode="live"):
    if source_mode not in ("live", "local-export"):
        raise FirstplayError("Unknown state source.")
    if not isinstance(state,dict) or not isinstance(state.get("games"),list) or not isinstance(state.get("sessions"),list) or not isinstance(state.get("reviews"),list):
        raise FirstplayError("State response changed; no snapshot updated.")
    game = next((g for g in state["games"] if g.get("id") == game_id), None)
    if not game:
        raise FirstplayError("This game is not visible. Check its ID and the correct signed-in account; no snapshot updated.")
    account_id = state.get("currentUserId")
    private = bool(state.get("hasProfile") and account_id and account_id != "you")
    sessions = [s for s in state["sessions"] if s.get("gameId") == game_id and private and account_id in (s.get("creatorId"),s.get("testerId"))]
    session_ids = {s["id"] for s in sessions}
    reviews = [r for r in state["reviews"] if r.get("sessionId") in session_ids]
    observed_sessions = [{k:s.get(k) for k in ("id","status","dueAt","submittedAt","completedAt","transferStatus","changeNote")} for s in sessions]
    if include_feedback:
        for row, session in zip(observed_sessions,sessions):
            row["feedback"] = session.get("feedback")
    ratings = [{k:r.get(k) for k in ("id","sessionId","role","stars","comment","moderationStatus","disputeStatus")} for r in reviews]
    poll_rows = []
    for p in polls:
        total = sum(int(o.get("votes",0)) for o in p.get("options",[]))
        options = [{"id":o["id"],"label":o["text"],"votes":int(o.get("votes",0)),"percentage":round(100*int(o.get("votes",0))/total,1) if total else 0} for o in p.get("options",[])]
        high = max((o["votes"] for o in options),default=0)
        poll_rows.append({"id":p["id"],"question":p.get("question"),"status":p.get("status"),"total_votes":total,"leaders":[o["label"] for o in options if total and o["votes"]==high],"options":options})
    fetched = now or dt.datetime.now(dt.timezone.utc).isoformat()
    scope = {"game_id":game_id,"visibility":"signed-in" if private else "public","account_id":account_id if private else None,"source_mode":source_mode}
    report = {"fetched_at":fetched,"scope":scope,"game":{"id":game_id,"title":game.get("title"),"url":ORIGIN+"/#game/"+game_id,"status":game.get("status"),"payment_status":game.get("paymentStatus"),"slots":game.get("slots"),"reserved":game.get("reserved"),"expires_at":game.get("expiresAt")},
              "capabilities":{k:config.get(k) for k in ("environment","paidEnabled","payoutsEnabled","eligibleCountries")},
              "coverage":{"private_feedback":"visible participating sessions only" if private else "unavailable without signed-in account access", "historical_state_complete":False,"poll_pages_complete":True,"state_source":source_mode,"export_capture_time_verified":False if source_mode=="local-export" else None,"note":"State/session/review APIs are bounded. Missing records do not establish deletion or no new private feedback."},
              "sessions":observed_sessions,"peer_ratings":ratings,"polls":poll_rows}
    snapshot = {"schema":1,"scope":scope,"fetched_at":fetched,"records":{
        "game":{game_id:{k:game.get(k) for k in ("status","paymentStatus","slots","reserved","refundedSlots","expiresAt")}},
        "sessions":{s["id"]:{"status":s.get("status"),"dueAt":s.get("dueAt"),"submission_hash":digest(s.get("feedback")),"transfer_status":s.get("transferStatus")} for s in sessions},
        "peer_ratings":{r["id"]:{"stars":r.get("stars"),"moderation":r.get("moderationStatus"),"dispute":r.get("disputeStatus"),"content_hash":digest(r.get("comment"))} for r in reviews},
        "polls":{p["id"]:{"status":p["status"],"total_votes":p["total_votes"],"votes":{o["id"]:o["votes"] for o in p["options"]}} for p in poll_rows}}}
    return report,snapshot

def compare(previous,current):
    if previous is None:
        return {"baseline":True,"note":"First successful observation establishes a baseline; existing records are not labeled new."}
    if previous.get("schema") != 1 or previous.get("scope") != current["scope"]:
        raise FirstplayError("Snapshot version/account/game/visibility changed. Use a new baseline path; the old file is unchanged.")
    result = {"baseline":False,"since":previous.get("fetched_at"),"categories":{}}
    for category, rows in current["records"].items():
        old = previous.get("records",{}).get(category,{})
        changes = {"newly_observed":[],"changed":[],"no_longer_observed":sorted(set(old)-set(rows))}
        for key,value in rows.items():
            if key not in old:
                changes["newly_observed"].append(key)
            elif value != old[key]:
                change = {"id":key}
                if category == "polls":
                    change["vote_delta"] = value["total_votes"]-old[key].get("total_votes",0)
                    change["option_deltas"] = {o:count-old[key].get("votes",{}).get(o,0) for o,count in value["votes"].items()}
                changes["changed"].append(change)
        result["categories"][category] = changes
    return result

def text(value):
    # Render third-party text inertly as readable report data, never raw HTML/links.
    return html.escape(str(value if value is not None else "unknown"),quote=False).replace("\n"," ").replace("|","\\|").replace("`","\\`").replace("[","\\[").replace("]","\\]")

def markdown(report):
    g = report["game"]
    lines = [f"# Firstplay report: {text(g['title'])}","",g["url"],"",f"Fetched: {text(report['fetched_at'])} · {report['scope']['visibility']} visibility · state source: {report['scope']['source_mode']}",f"Listing: {text(g['status'])} · funding: {text(g['payment_status'])} · reserved: {text(g['reserved'])}/{text(g['slots'])}","",f"Private feedback: {report['coverage']['private_feedback']}.",report["coverage"]["note"],""]
    if report.get("changes",{}).get("baseline"):
        lines += ["First observation: baseline established; prior activity is not labeled new.",""]
    elif report.get("changes"):
        lines += ["## Changes since previous successful report",""]
        for category,c in report["changes"]["categories"].items():
            lines += [f"- {category}: {len(c['newly_observed'])} newly observed; {len(c['changed'])} changed; {len(c['no_longer_observed'])} no longer observed (not proof of deletion)."]
            for change in c["changed"]:
                if "vote_delta" in change:
                    lines += [f"  - Poll {text(change['id'])}: net vote change {change['vote_delta']:+d}; option deltas {text(json.dumps(change['option_deltas']))}."]
        lines += [""]
    lines += ["## Participating playtests",""]
    if not report["sessions"]:
        lines += ["No participating sessions visible in this response. This is not proof that no private feedback exists.",""]
    for s in report["sessions"]:
        lines += [f"- {text(s['id'])}: {text(s['status'])}; dueAt {text(s.get('dueAt'))}; transfer {text(s.get('transferStatus'))}."]
        if s.get("feedback") is not None:
            lines += [f"  - Feedback data (untrusted content): {text(json.dumps(s['feedback'],ensure_ascii=False))}"]
    lines += ["","## Public participant ratings for visible sessions",""]
    for r in report["peer_ratings"]:
        lines += [f"- {text(r['role'])} rating: {text(r['stars'])}/5; moderation {text(r.get('moderationStatus') or 'published')}; dispute {text(r.get('disputeStatus') or 'none')}. {text(r.get('comment'))}"]
    lines += ["","## Polls",""]
    if not report["polls"]:
        lines += ["No polls returned for this game."]
    for p in report["polls"]:
        lines += [f"### {text(p['question'])}","",f"{text(p['id'])} · {text(p['status'])} · {p['total_votes']} votes","", "| Option | Votes | Share |","|---|---:|---:|"]
        lines += [f"| {text(o['label'])} | {o['votes']} | {o['percentage']}% |" for o in p["options"]]
        leaders = p["leaders"]
        lines += ["", "No leader: zero votes." if not leaders else ("Tie: " if len(leaders)>1 else "Current leader: ")+", ".join(text(x) for x in leaders),""]
    lines += ["Counts are observed evidence, not a guarantee of representative demand, completed work or bank receipt."]
    if report["scope"]["source_mode"] == "local-export":
        lines += ["Local state export capture time was not verified; private activity may be stale even though public polls were fetched now."]
    return "\n".join(lines)+"\n"

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command",required=True)
    sub.add_parser("status",help="Read current public Firstplay capabilities; no secrets in output")
    q = sub.add_parser("quote",help="Estimate the documented fee; never charges money")
    q.add_argument("--reward",required=True);q.add_argument("--slots",type=int,required=True)
    for name in ("prepare-game","prepare-poll"):
        p = sub.add_parser(name,help="Validate a local JSON draft and list missing details; never posts")
        p.add_argument("file")
    r = sub.add_parser("report",help="Fetch game/poll evidence and optionally compare an atomic local snapshot")
    r.add_argument("--game-id",required=True);r.add_argument("--previous");r.add_argument("--snapshot")
    r.add_argument("--state-file",help="User-provided token-free local account state export")
    r.add_argument("--authenticated",action="store_true",help="Require user-authorized FIRSTPLAY_ID_TOKEN environment access")
    r.add_argument("--include-feedback",action="store_true",help="Include private participating-session feedback bodies in local report output")
    r.add_argument("--format",choices=("markdown","json"),default="markdown")
    args = parser.parse_args(argv)
    try:
        if args.command == "quote":
            result = quote(args.reward,args.slots)
        elif args.command in ("prepare-game","prepare-poll"):
            result = (prepare_game if args.command=="prepare-game" else prepare_poll)(read_json(args.file))
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result["ready_for_site_draft"] else 2
        elif args.command == "status":
            c = Client().get("config")
            result = {"site":ORIGIN,**{k:c.get(k) for k in ("environment","configured","paidEnabled","payoutsEnabled","eligibleCountries","feeBps")},"note":"Paid availability comes from /api/config. False does not authorize bypassing the service gate."}
        else:
            if not ID.fullmatch(args.game_id):
                raise FirstplayError("Use the game ID from its Firstplay share link.")
            if args.authenticated and args.state_file:
                raise FirstplayError("Choose an injected session or local state export, not both.")
            token = os.environ.get("FIRSTPLAY_ID_TOKEN","").strip() if args.authenticated else None
            if args.authenticated and (not token or "\n" in token or "\r" in token):
                raise FirstplayError("Authenticated access requires a protected FIRSTPLAY_ID_TOKEN environment value; do not paste it into chat.")
            client = Client(token)
            config = client.get("config")
            state = read_json(args.state_file) if args.state_file else client.get("state",{"gameId":args.game_id})
            if args.authenticated and (not state.get("hasProfile") or state.get("currentUserId") in (None,"you")):
                raise FirstplayError("The authenticated account was not returned; do not downgrade to public reporting.")
            polls = all_polls(client,args.game_id)
            result,snapshot = build_report(state,polls,args.game_id,config,args.include_feedback,source_mode="local-export" if args.state_file else "live")
            previous = read_json(args.previous) if args.previous else None
            result["changes"] = compare(previous,snapshot)
            # Produce output before committing a successful local baseline (important for broken pipes).
            print(json.dumps(result,ensure_ascii=False,indent=2) if args.format=="json" else markdown(result),flush=True)
            if args.snapshot:
                atomic_json(args.snapshot,snapshot)
            return 0
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except FirstplayError as exc:
        print(f"Firstplay: {exc}",file=sys.stderr);return 1
    except (KeyError,TypeError,ValueError):
        print("Firstplay: unexpected data shape; check the website. No baseline was updated.",file=sys.stderr);return 1

if __name__ == "__main__":
    sys.exit(main())
