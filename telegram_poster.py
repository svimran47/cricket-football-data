import os
import re
import json
import time
import html
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "@sportzfyplay")
HISTORY_FILE = "posted_matches.json"

# Source timezone used by sportzfyplay.com for matchDate and startTime (UK time Europe/London)
SOURCE_TZ = ZoneInfo(os.getenv("SOURCE_TIMEZONE", "Europe/London"))
MYT_TZ = ZoneInfo("Asia/Kuala_Lumpur")

# Six capital-city timezones retained for every fixture
DISPLAY_TIMEZONES = [
    ("🇧🇩", "Dhaka", "Asia/Dhaka"),
    ("🇮🇳", "New Delhi", "Asia/Kolkata"),
    ("🇺🇸", "Washington DC", "America/New_York"),
    ("🇮🇩", "Jakarta", "Asia/Jakarta"),
    ("🇳🇬", "Abuja", "Africa/Lagos"),
    ("🇸🇬", "Singapore", "Asia/Singapore"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DISCORD_WEBHOOK_URL = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip().strip('"').strip("'")

# Known clubs belonging to the top European leagues for cross-referencing and fallback UEFA detection
TOP_EUROPEAN_CLUBS = {
    "england": {
        "arsenal", "aston villa", "bournemouth", "brentford", "brighton", "chelsea", "crystal palace",
        "everton", "fulham", "ipswich", "ipswich town", "leicester", "leicester city", "liverpool",
        "manchester city", "man city", "manchester united", "man utd", "newcastle", "newcastle united",
        "nottingham forest", "southampton", "tottenham", "tottenham hotspur", "spurs", "west ham",
        "west ham united", "wolverhampton", "wolves", "leeds", "leeds united", "burnley", "sheffield united",
        "sunderland", "middlesbrough", "coventry", "coventry city", "norwich", "norwich city", "west brom"
    },
    "spain": {
        "alaves", "alavés", "athletic bilbao", "athletic club", "atletico madrid", "atlético madrid",
        "barcelona", "celta vigo", "espanyol", "getafe", "girona", "las palmas", "leganes", "leganés",
        "mallorca", "osasuna", "rayo vallecano", "real betis", "betis", "real madrid", "real sociedad",
        "sevilla", "valencia", "valladolid", "real valladolid", "villarreal"
    },
    "italy": {
        "atalanta", "bologna", "cagliari", "como", "empoli", "fiorentina", "genoa", "hellas verona", "verona",
        "inter", "internazionale", "juventus", "lazio", "lecce", "milan", "ac milan", "monza", "napoli",
        "parma", "roma", "torino", "udinese", "venezia", "sassuolo", "sampdoria", "palermo", "salernitana"
    },
    "germany": {
        "augsburg", "bayer leverkusen", "leverkusen", "bayern munich", "bayern munchen", "bayern münchen",
        "bochum", "borussia dortmund", "dortmund", "borussia monchengladbach", "mönchengladbach",
        "eintracht frankfurt", "frankfurt", "freiburg", "heidenheim", "hoffenheim", "holstein kiel",
        "mainz", "rb leipzig", "leipzig", "st pauli", "stuttgart", "union berlin", "werder bremen",
        "wolfsburg", "schalke", "hamburg", "hertha berlin", "hannover", "koln", "köln"
    },
    "france": {
        "angers", "auxerre", "brest", "le havre", "lens", "lille", "lyon", "olympique lyonnais",
        "marseille", "olympique de marseille", "monaco", "as monaco", "montpellier", "nantes",
        "nice", "paris saint-germain", "psg", "reims", "rennes", "saint-etienne", "strasbourg", "toulouse"
    },
    "portugal": {
        "benfica", "porto", "fc porto", "sporting cp", "sporting lisbon", "braga", "sporting braga",
        "vitoria guimaraes", "vitória de guimarães", "boavista", "famalicao", "gil vicente", "rio ave"
    },
    "netherlands": {
        "ajax", "az alkmaar", "feyenoord", "feyenoord rotterdam", "psv", "psv eindhoven", "twente",
        "fc twente", "utrecht", "vitesse", "heerenveen", "sparta rotterdam", "nec nijmegen"
    }
}

ALL_TOP_CLUBS = {}
for country, clubs in TOP_EUROPEAN_CLUBS.items():
    for c in clubs:
        ALL_TOP_CLUBS[c] = country

TOP_NATIONAL_TEAMS = {
    "argentina", "brazil", "france", "england", "spain", "germany", "italy", "portugal",
    "netherlands", "belgium", "croatia", "uruguay", "colombia", "usa", "united states",
    "mexico", "japan", "south korea", "morocco", "senegal", "nigeria", "australia",
    "switzerland", "denmark", "austria", "sweden", "norway", "poland", "scotland", "wales"
}

# ---------------------------------------------------------------- CREDENTIALS & API ---

def get_clean_token():
    token = (BOT_TOKEN or "").strip().strip('"').strip("'")
    if token.lower().startswith("bot"):
        token = token[3:].strip()
    return token

def get_clean_channel():
    channel = (CHANNEL_ID or "").strip().strip('"').strip("'")
    if "t.me/" in channel:
        channel = "@" + channel.split("t.me/")[-1].strip("/")
    if channel and not channel.startswith("@") and not channel.startswith("-") and not channel.replace("-", "").isdigit():
        channel = "@" + channel
    return channel

def verify_bot():
    token = get_clean_token()
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN is empty!")
        return False
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        r = requests.get(url, timeout=15)
        res = r.json()
        if res.get("ok"):
            bot_info = res["result"]
            print(f"🤖 Connected successfully as Bot: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            return True
        else:
            print(f"❌ Telegram Bot Token Invalid! Response: {res}")
            return False
    except Exception as e:
        print(f"❌ Failed to reach Telegram API: {e}")
        return False

def send_telegram_request(endpoint, payload):
    token = get_clean_token()
    url = f"https://api.telegram.org/bot{token}/{endpoint}"
    payload["chat_id"] = get_clean_channel()
    try:
        resp = requests.post(url, json=payload, timeout=25)
        res_json = resp.json()
        if not resp.ok or not res_json.get("ok"):
            print(f"❌ Telegram API Error on {endpoint}: {resp.status_code} - {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"❌ Request Exception on {endpoint}: {e}")
        return False

def send_discord_webhook(payload, retries=3):
    """POST to Discord webhook, honouring rate limits."""
    for attempt in range(retries):
        try:
            resp = requests.post(f"{DISCORD_WEBHOOK_URL}?wait=true", json=payload, timeout=25)
        except Exception as e:
            print(f"❌ Discord request exception: {e}")
            return False
        if resp.status_code == 429:
            try:
                wait = float(resp.json().get("retry_after", 2))
            except Exception:
                wait = 2.0
            print(f"⏳ Discord rate limited, retrying in {wait:.1f}s")
            time.sleep(wait + 0.5)
            continue
        if resp.ok:
            return True
        print(f"❌ Discord API Error: {resp.status_code} - {resp.text}")
        return False
    return False

# ---------------------------------------------------------------- HISTORY ---

def load_posted():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception as e:
            print(f"Warning: Could not read history file: {e}")
            return set()
    return set()

def save_posted(posted_set):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(posted_set)), f, indent=2)

# ---------------------------------------------------------------- DATA FETCHING ---

def get_watch_url(match):
    """Build the /watch?v=... player link for the match."""
    slug = str(match.get("slug") or match.get("id") or "").strip()
    if "watch?v=" in slug:
        video_id = slug.split("watch?v=")[-1]
        return f"https://sportzfyplay.com/watch?v={video_id}"
    for prefix in ("/matches/", "matches/", "/watch/", "watch/"):
        if slug.startswith(prefix):
            slug = slug[len(prefix):]
    slug = slug.strip("/")
    return f"https://sportzfyplay.com/watch?v={slug}"

def fetch_page_matches(url):
    """Extracts all matches from both single-match and array props on SportzfyPlay Astro islands."""
    matches = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        print(f"GET {url} -> Status {resp.status_code}")
        if not resp.ok:
            return matches

        islands = re.findall(r'<astro-island[^>]*props="([^"]*)"', resp.text)
        for props in islands:
            clean = props.replace('&quot;', '"')
            try:
                data = json.loads(clean)
                # Single match prop
                if "match" in data:
                    raw = data["match"]
                    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[1], dict):
                        m = {k: v[1] if isinstance(v, list) and len(v) > 1 else v for k, v in raw[1].items()}
                        matches.append(m)
                # List of matches prop
                if "matches" in data:
                    raw_list = data["matches"]
                    if isinstance(raw_list, list) and len(raw_list) > 1 and isinstance(raw_list[1], list):
                        for item in raw_list[1]:
                            if isinstance(item, list) and len(item) > 1 and isinstance(item[1], dict):
                                m = {k: v[1] if isinstance(v, list) and len(v) > 1 else v for k, v in item[1].items()}
                                matches.append(m)
            except Exception:
                continue
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return matches

def fetch_upstream_football_matches():
    """Fetch upstream streamed.pk matches to enrich competition & source identifiers."""
    url = "https://streamed.pk/api/matches/football"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.ok:
            data = resp.json()
            lookup = {}
            for item in data:
                lookup[item.get("id")] = item
                # Also index normalized title
                title = (item.get("title") or "").lower().replace(" - ", " vs ")
                lookup[title] = item
            return lookup
    except Exception as e:
        print(f"Warning: Upstream metadata fetch failed ({e}), continuing with page data.")
    return {}

# ---------------------------------------------------------------- ELIGIBILITY FILTER ---

def normalize_text(text):
    return re.sub(r'[^a-z0-9]+', ' ', (text or "").lower()).strip()

def get_match_datetime(match, upstream_info=None):
    """Parse canonical kickoff datetime with timezone."""
    # 1. Try matchDate and startTime (SportzfyPlay format in Europe/London)
    md = match.get("matchDate")
    st = match.get("startTime")
    if md and st:
        try:
            return datetime.strptime(f"{md} {st}".strip(), "%Y-%m-%d %H:%M").replace(tzinfo=SOURCE_TZ)
        except Exception:
            pass

    # 2. Try upstream timestamp (ms since epoch UTC)
    if upstream_info and "date" in upstream_info:
        try:
            ts = float(upstream_info["date"]) / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    return None

def is_eligible_football_match(match, upstream_lookup=None):
    """
    Evaluates whether a match meets the strict eligibility criteria:
    - Association football (soccer) only.
    - Europe's top 7 domestic league systems (England, Spain, Italy, Germany, France, Portugal, Netherlands + recognized sub-tiers).
    - Approved domestic cups: The FA Cup & Copa del Rey.
    - Major continental club tournaments: UEFA Champions League, Europa League, Conference League.
    - Major international senior national team competitions (World Cup, Euro, Copa América, Asian Cup, AFCON, Gold Cup, Nations League).
    - Explicit exclusions: Friendlies, youth/reserves/amateurs, unapproved domestic cups, non-football sports, foreign leagues outside top 7.

    Returns:
        (canonical_competition_title, is_eligible_bool)
    """
    sport = (match.get("sport") or "").lower().strip()
    if sport not in ("football", "soccer"):
        return None, False

    home = (match.get("homeTeam") or "").strip()
    away = (match.get("awayTeam") or "").strip()
    event_name = (match.get("eventName") or f"{home} vs {away}").strip()
    mid = str(match.get("id") or "").strip()
    slug = str(match.get("slug") or "").strip()
    comp = str(match.get("competition") or "").strip()

    # Collect upstream metadata hints
    hints = []
    upstream_info = None
    if upstream_lookup:
        upstream_info = upstream_lookup.get(mid)
        if not upstream_info:
            upstream_info = upstream_lookup.get(event_name.lower().replace(" - ", " vs "))
        if upstream_info:
            for s in upstream_info.get("sources", []):
                hints.append(str(s.get("id", "")))

    raw_blob = f"{event_name} {comp} {mid} {slug} {' '.join(hints)}"
    norm = normalize_text(raw_blob)

    # 1. EXCLUSIONS FIRST: Youth, reserves, academies, amateurs
    if re.search(r'\b(u\d{2}|u-\d{2}|under \d{2}|youth|reserves|academy|amateur|women|feminin)\b', norm):
        return None, False

    # 2. EXCLUSIONS: Friendlies & Pre-season
    if re.search(r'\b(friendly|friendlies|club friendly|pre season|preseason)\b', norm):
        return None, False

    # 3. EXCLUSIONS: Unapproved domestic cups (Carabao, DFB-Pokal, Coppa Italia, etc.)
    if re.search(r'\b(carabao|efl cup|league cup|dfb pokal|coppa italia|coupe de france|taca de portugal|ta a de portugal|knvb|copa do brasil)\b', norm):
        return None, False

    # 4. APPROVED CUPS: The FA Cup & Copa del Rey
    if re.search(r'\b(fa cup|the fa cup|emirates fa cup)\b', norm) or any('fa-cup' in h.lower() for h in hints):
        return "FA CUP", True
    if re.search(r'\b(copa del rey)\b', norm) or any('copa-del-rey' in h.lower() for h in hints):
        return "COPA DEL REY", True

    # 5. UEFA CONTINENTAL CLUB COMPETITIONS
    if re.search(r'\b(uefa champions league|champions league|ucl)\b', norm) or any('champions-league' in h.lower() for h in hints):
        return "UEFA CHAMPIONS LEAGUE", True
    if re.search(r'\b(uefa europa league|europa league|uel)\b', norm) or any('europa-league' in h.lower() for h in hints):
        return "UEFA EUROPA LEAGUE", True
    if re.search(r'\b(uefa conference league|conference league|uecl|uefa europa conference league)\b', norm) or any('conference-league' in h.lower() for h in hints):
        return "UEFA CONFERENCE LEAGUE", True

    # 6. TOP 7 EUROPEAN DOMESTIC LEAGUE SYSTEMS
    # (1) England
    if re.search(r'\b(premier league|epl)\b', norm) or any('premier-league' in h.lower() for h in hints):
        return "PREMIER LEAGUE", True
    if re.search(r'\b(championship|efl championship)\b', norm) or any('championship' in h.lower() for h in hints):
        return "EFL CHAMPIONSHIP", True
    if re.search(r'\b(league one|efl league one)\b', norm) or any('league-one' in h.lower() for h in hints):
        return "EFL LEAGUE ONE", True
    if re.search(r'\b(league two|efl league two)\b', norm) or any('league-two' in h.lower() for h in hints):
        return "EFL LEAGUE TWO", True
    if re.search(r'\b(national league)\b', norm) or any('national-league' in h.lower() for h in hints):
        return "NATIONAL LEAGUE", True

    # (2) Spain
    if re.search(r'\b(la liga|laliga|primera division)\b', norm) or any('laliga' in h.lower() for h in hints):
        return "LA LIGA", True
    if re.search(r'\b(segunda division|laliga 2|laliga hypermotion)\b', norm) or any('segunda' in h.lower() or 'laliga-2' in h.lower() for h in hints):
        return "LALIGA 2", True

    # (3) Italy
    if re.search(r'\b(serie a)\b', norm) or any('serie-a' in h.lower() for h in hints):
        return "SERIE A", True
    if re.search(r'\b(serie b)\b', norm) or any('serie-b' in h.lower() for h in hints):
        return "SERIE B", True
    if re.search(r'\b(serie c)\b', norm) or any('serie-c' in h.lower() for h in hints):
        return "SERIE C", True

    # (4) Germany
    if re.search(r'\b(bundesliga)\b', norm) or any('bundesliga' in h.lower() for h in hints):
        if '2 bundesliga' in norm or '2-bundesliga' in norm:
            return "2. BUNDESLIGA", True
        return "BUNDESLIGA", True
    if re.search(r'\b(3 liga|3-liga)\b', norm) or any('3-liga' in h.lower() for h in hints):
        return "3. LIGA", True

    # (5) France
    if re.search(r'\b(ligue 1)\b', norm) or any('ligue-1' in h.lower() for h in hints):
        return "LIGUE 1", True
    if re.search(r'\b(ligue 2)\b', norm) or any('ligue-2' in h.lower() for h in hints):
        return "LIGUE 2", True

    # (6) Portugal
    if re.search(r'\b(primeira liga|liga portugal)\b', norm) or any('primeira-liga' in h.lower() or 'liga-portugal' in h.lower() for h in hints):
        if '2' in norm or 'segunda' in norm:
            return "LIGA PORTUGAL 2", True
        return "PRIMEIRA LIGA", True

    # (7) Netherlands
    if re.search(r'\b(eredivisie)\b', norm) or any('eredivisie' in h.lower() for h in hints):
        return "EREDIVISIE", True
    if re.search(r'\b(eerste divisie|keuken kampioen)\b', norm) or any('eerste-divisie' in h.lower() for h in hints):
        return "EERSTE DIVISIE", True

    # 7. MAJOR INTERNATIONAL SENIOR NATIONAL TEAM COMPETITIONS
    if re.search(r'\b(world cup|fifa world cup)\b', norm):
        return "FIFA WORLD CUP", True
    if re.search(r'\b(uefa euro|euro 20\d\d|european championship)\b', norm):
        return "UEFA EURO", True
    if re.search(r'\b(copa america|copa am rica)\b', norm):
        return "COPA AMÉRICA", True
    if re.search(r'\b(uefa nations league|nations league)\b', norm):
        return "UEFA NATIONS LEAGUE", True
    if re.search(r'\b(afcon|africa cup of nations)\b', norm):
        return "AFCON", True
    if re.search(r'\b(asian cup|afc asian cup)\b', norm):
        return "AFC ASIAN CUP", True
    if re.search(r'\b(gold cup|concacaf gold cup)\b', norm):
        return "CONCACAF GOLD CUP", True

    # 8. CROSS-BORDER TOP EUROPEAN CLUB FALLBACK (e.g. UCL/UEL fixture on European nights)
    home_norm = normalize_text(home or (event_name.split("vs")[0] if "vs" in event_name else event_name.split("-")[0]))
    away_norm = normalize_text(away or (event_name.split("vs")[-1] if "vs" in event_name else event_name.split("-")[-1]))
    home_country = ALL_TOP_CLUBS.get(home_norm)
    away_country = ALL_TOP_CLUBS.get(away_norm)

    if home_country and away_country:
        if home_country != away_country:
            # Two top European clubs from different countries playing each other
            return "UEFA CHAMPIONS LEAGUE", True
        else:
            # Two clubs from the same top European country
            country_to_league = {
                "england": "PREMIER LEAGUE",
                "spain": "LA LIGA",
                "italy": "SERIE A",
                "germany": "BUNDESLIGA",
                "france": "LIGUE 1",
                "portugal": "PRIMEIRA LIGA",
                "netherlands": "EREDIVISIE"
            }
            return country_to_league[home_country], True

    # If eligibility cannot be verified with confidence, exclude it
    return None, False

# ---------------------------------------------------------------- TIMEZONE & FORMATTING ---

def format_local_time(dt):
    """Format datetime as e.g. '10:00 PM'."""
    hour = dt.strftime('%I').lstrip('0')
    minute = dt.strftime('%M')
    ampm = dt.strftime('%p')
    return f"{hour}:{minute} {ampm}"

def format_match_card(match, comp_title, is_live, base_date, is_html=True):
    """
    Format a single match block with all 7 timezones and compact layout.
    """
    event_name = (match.get("eventName") or f"{match.get('homeTeam', '')} vs {match.get('awayTeam', '')}").strip()
    kickoff_dt = match["_kickoff_dt"]
    watch_url = get_watch_url(match)

    status_dot = "🔴" if is_live else "⚪"
    safe_name = html.escape(event_name) if is_html else event_name

    myt_dt = kickoff_dt.astimezone(MYT_TZ)
    myt_day = f" ({myt_dt.strftime('%a')})" if myt_dt.date() != base_date else ""
    myt_line = f"🇲🇾 MYT {format_local_time(myt_dt)}{myt_day}"

    # Build 6 city times
    city_times = {}
    for flag, label, iana in DISPLAY_TIMEZONES:
        local_dt = kickoff_dt.astimezone(ZoneInfo(iana))
        suffix = ""
        if local_dt.date() != base_date:
            suffix = f" ({local_dt.strftime('%a')})"
        elif myt_dt.date() != base_date and local_dt.date() != myt_dt.date():
            suffix = f" ({local_dt.strftime('%a')})"
        city_times[label] = f"{flag} {label} {format_local_time(local_dt)}{suffix}"

    lines = [
        f"{status_dot} {safe_name}",
        myt_line,
        f"{city_times['Dhaka']} · {city_times['New Delhi']}",
        f"{city_times['Washington DC']}",
        f"{city_times['Jakarta']} · {city_times['Abuja']}",
        f"{city_times['Singapore']}",
    ]

    if is_html:
        lines.append(f"▶ <a href=\"{watch_url}\">WATCH LIVE IN HD</a>")
    else:
        lines.append(f"▶ [WATCH LIVE IN HD]({watch_url})")

    return "\n".join(lines)

def build_combined_post(matches_by_status, base_date, is_html=True):
    """
    Constructs the complete text of the daily schedule post.
    """
    sep = "━━━━━━━━━━━━━━━━━━━━"
    day_str = base_date.strftime("%A, %d %B").upper()

    header_lines = [
        sep,
        "⚽ SPORTZFYPLAY | DAILY FOOTBALL",
        f"📅 {day_str}",
        "🕗 Published daily at 8:00 PM MYT",
    ]

    body_sections = []

    # 1. LIVE NOW SECTION (if any live matches)
    live_matches = matches_by_status.get("LIVE", [])
    if live_matches:
        live_block = ["\n🔴 LIVE NOW"]
        # Group live matches by competition
        live_groups = {}
        for m in live_matches:
            live_groups.setdefault(m["_comp"], []).append(m)
        for comp, g_matches in live_groups.items():
            live_block.append(f"\n🏆 {comp}\n")
            for m in g_matches:
                live_block.append(format_match_card(m, comp, is_live=True, base_date=base_date, is_html=is_html))
                live_block.append("")  # match spacer
        body_sections.append("\n".join(live_block).strip())

    # 2. UPCOMING SECTION (grouped by competition)
    upcoming_matches = matches_by_status.get("UPCOMING", [])
    if upcoming_matches:
        comp_groups = {}
        for m in upcoming_matches:
            comp_groups.setdefault(m["_comp"], []).append(m)

        for comp, g_matches in comp_groups.items():
            comp_block = [f"\n🏆 {comp}\n"]
            # Sort chronologically
            g_matches.sort(key=lambda x: x["_kickoff_dt"])
            for m in g_matches:
                comp_block.append(format_match_card(m, comp, is_live=False, base_date=base_date, is_html=is_html))
                comp_block.append("")
            body_sections.append("\n".join(comp_block).strip())

    if not live_matches and not upcoming_matches:
        body_sections.append("\nNo qualifying football fixtures scheduled for today.")

    footer = f"\n{sep}\nFree Live Sports | SportzfyPlay"

    full_message = "\n\n".join(header_lines) + "\n\n" + "\n\n".join(body_sections) + footer
    return full_message

def chunk_post_message(message, max_chars=3900):
    """
    Splits a message into valid chunks if it exceeds platform limits, preserving whole lines.
    """
    if len(message) <= max_chars:
        return [message]

    chunks = []
    current_chunk = []
    current_len = 0

    lines = message.split("\n")
    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars and current_chunk:
            chunks.append("\n".join(current_chunk).strip())
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk).strip())

    return chunks

# ---------------------------------------------------------------- MAIN ORCHESTRATION ---

def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ ERROR: TELEGRAM_BOT_TOKEN secret is not set in GitHub repository secrets!")
    if not CHANNEL_ID:
        raise SystemExit("❌ ERROR: TELEGRAM_CHANNEL_ID secret is not set in GitHub repository secrets!")

    if not verify_bot():
        raise SystemExit("❌ ERROR: Could not connect to Telegram bot! Check your TELEGRAM_BOT_TOKEN in GitHub secrets.")

    print(f"🎯 Target channel: {get_clean_channel()}")
    posted = load_posted()

    # 1. Fetch raw matches from SportzfyPlay and upstream streamed.pk
    all_found = []
    all_found.extend(fetch_page_matches("https://sportzfyplay.com/"))
    all_found.extend(fetch_page_matches("https://sportzfyplay.com/schedule"))

    # De-duplicate raw matches by ID/slug
    unique_raw = {}
    for m in all_found:
        key = m.get("slug") or m.get("id")
        if key and key not in unique_raw:
            unique_raw[key] = m
    print(f"Total unique fixtures scraped: {len(unique_raw)}")

    upstream_lookup = fetch_upstream_football_matches()
    print(f"Upstream match lookup loaded: {len(upstream_lookup)} items")

    # 2. Determine schedule window: 8:00 PM MYT today through next 24 hours
    now_myt = datetime.now(MYT_TZ)
    base_date = now_myt.date()
    now_utc = datetime.now(timezone.utc)

    # Window covers matches currently live (~115 min window) through the next 24 hours
    window_start = now_utc - timedelta(minutes=115)
    window_end = now_utc + timedelta(hours=24)
    print(f"📅 Posting date: {base_date.isoformat()} (MYT: {now_myt.strftime('%Y-%m-%d %H:%M')})")
    print(f"⏳ Match window (UTC): {window_start.strftime('%Y-%m-%d %H:%M')} to {window_end.strftime('%Y-%m-%d %H:%M')}")

    # 3. Filter eligible football fixtures within window
    eligible_matches = []
    FORCE_REPOST = os.getenv("FORCE_REPOST", "false").lower() in ("true", "1", "yes")
    TARGET_MATCH = os.getenv("TARGET_MATCH", "").strip()

    for key, match in unique_raw.items():
        comp_title, eligible = is_eligible_football_match(match, upstream_lookup)
        if not eligible:
            continue

        kickoff = get_match_datetime(match, upstream_lookup.get(str(match.get("id") or "")))
        if not kickoff:
            continue

        # If user specified a specific match target in manual dispatch, only include that
        if TARGET_MATCH:
            slug = str(match.get("slug") or match.get("id") or "").strip()
            watch_url = get_watch_url(match)
            if TARGET_MATCH not in (key, slug, watch_url) and TARGET_MATCH not in slug:
                continue

        # Check window
        if not (window_start <= kickoff <= window_end):
            continue

        match["_comp"] = comp_title
        match["_kickoff_dt"] = kickoff
        eligible_matches.append(match)

    print(f"Eligible football fixtures in window: {len(eligible_matches)}")

    # 4. Group matches by LIVE NOW vs UPCOMING
    matches_by_status = {"LIVE": [], "UPCOMING": []}
    for m in eligible_matches:
        kickoff = m["_kickoff_dt"]
        if kickoff <= now_utc:
            matches_by_status["LIVE"].append(m)
        else:
            matches_by_status["UPCOMING"].append(m)

    # Sort live matches chronologically
    matches_by_status["LIVE"].sort(key=lambda x: x["_kickoff_dt"])
    matches_by_status["UPCOMING"].sort(key=lambda x: x["_kickoff_dt"])

    # 5. Build Combined Daily Post
    daily_post_key = f"daily_football_{base_date.isoformat()}"
    discord_post_key = f"discord:daily_football_{base_date.isoformat()}"

    telegram_text = build_combined_post(matches_by_status, base_date, is_html=True)
    discord_text = build_combined_post(matches_by_status, base_date, is_html=False)

    # 6. Publish to Telegram
    if FORCE_REPOST or daily_post_key not in posted:
        print(f"🚀 [Telegram] Publishing combined football schedule for {base_date.isoformat()}...")
        chunks = chunk_post_message(telegram_text, max_chars=3900)
        success = True
        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                print(f"Publishing chunk {idx+1}/{len(chunks)} ({len(chunk)} chars)...")
            res = send_telegram_request("sendMessage", {
                "chat_id": get_clean_channel(),
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            })
            if not res:
                success = False
            time.sleep(1)

        if success:
            posted.add(daily_post_key)
            print(f"✅ [Telegram] Published daily schedule post successfully.")
        else:
            print(f"❌ [Telegram] Failed to publish daily post.")
    else:
        print(f"ℹ️ [Telegram] Daily post for {base_date.isoformat()} already published (use FORCE_REPOST=true to override).")

    # 7. Publish to Discord
    discord_enabled = DISCORD_WEBHOOK_URL.startswith("https://")
    if discord_enabled and (FORCE_REPOST or discord_post_key not in posted):
        print(f"🚀 [Discord] Publishing combined football schedule...")
        discord_chunks = chunk_post_message(discord_text, max_chars=1900)
        d_success = True
        for chunk in discord_chunks:
            res = send_discord_webhook({
                "username": "SportzfyPlay",
                "content": chunk,
                "allowed_mentions": {"parse": []}
            })
            if not res:
                d_success = False
            time.sleep(1)

        if d_success:
            posted.add(discord_post_key)
            print(f"✅ [Discord] Published daily schedule post successfully.")
        else:
            print(f"❌ [Discord] Failed to publish daily post to Discord.")

    save_posted(posted)

    # Update Discord #site-status card
    try:
        from site_status_checker import update_status
        print("🌐 Updating Discord #site-status card...")
        update_status()
    except Exception as e:
        print(f"Note: Site status update skipped: {e}")

if __name__ == "__main__":
    main()
