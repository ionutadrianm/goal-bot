import requests
import time
import random

# =========================
# CONFIG
# =========================
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

BASE_URL = "https://api.sofascore.com/api/v1/sport/football/events/live"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

seen = set()

# =========================
# TELEGRAM
# =========================
def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# SAFE REQUEST
# =========================
def safe_get(url):
    try:
        time.sleep(random.uniform(1.5, 3))
        r = requests.get(url, headers=HEADERS)

        if r.status_code != 200:
            print("Bad:", r.status_code)
            return None

        return r.json()
    except:
        return None

# =========================
# LIVE MATCHES
# =========================
def get_live():
    data = safe_get(BASE_URL)

    if not data or "events" not in data:
        return []

    return data["events"]

# =========================
# STATS
# =========================
def get_stats(match_id):
    url = f"https://api.sofascore.com/api/v1/event/{match_id}/statistics"
    data = safe_get(url)

    if not data:
        return None

    try:
        stats = data["statistics"][0]["groups"][0]["statisticsItems"]

        def get(name):
            for s in stats:
                if s["name"] == name:
                    return float(s["home"]) + float(s["away"])
            return 0

        return {
            "shots": get("Total shots"),
            "sot": get("Shots on target"),
            "corners": get("Corner kicks"),
            "xg": get("Expected goals")
        }

    except:
        return None

# =========================
# EVENTS
# =========================
def get_events(match_id):
    url = f"https://api.sofascore.com/api/v1/event/{match_id}/incidents"
    data = safe_get(url)

    if not data:
        return []

    return data.get("incidents", [])

def count_2h(events):
    count = 0
    for e in events:
        if e.get("incidentType") == "goal":
            if e.get("time", 0) >= 46:
                count += 1
    return count

# =========================
# LOGIC
# =========================
def momentum(stats, minute):
    score = 0

    if stats["shots"] >= 10: score += 10
    if stats["sot"] >= 4: score += 15
    if stats["corners"] >= 5: score += 8

    if minute >= 60:
        if stats["sot"] >= 5: score += 10

    return score

def classify(score):
    if score >= 85:
        return "🔥 ELITE"
    elif score >= 70:
        return "🔥 STRONG"
    return "⚡ MEDIUM"

# =========================
# MAIN LOOP
# =========================
def run():
    print("⚽ SofaScore bot running...")

    while True:
        try:
            matches = get_live()
            print(f"Matches: {len(matches)}")

            for m in matches[:8]:
                try:
                    match_id = m["id"]
                    minute = m.get("time", {}).get("played")

                    if not minute or match_id in seen:
                        continue

                    home = m["homeTeam"]["name"]
                    away = m["awayTeam"]["name"]

                    # =========================
                    # MAIN FILTER
                    # =========================
                    if not (
                        (35 <= minute <= 50) or
                        (55 <= minute <= 80)
                    ):
                        continue

                    events = get_events(match_id)
                    goals_2h = count_2h(events)

                    if minute >= 55 and goals_2h > 1:
                        continue

                    stats = get_stats(match_id)

                    if not stats:
                        continue

                    score = 50 + momentum(stats, minute)
                    tier = classify(score)

                    print(f"✅ {home} vs {away} | {minute}")

                    msg = f"""
{tier} SIGNAL

{home} vs {away}
Min: {minute}'

Shots: {stats['shots']}
SOT: {stats['sot']}
Corners: {stats['corners']}
xG: {round(stats['xg'],2)}

➡️ Over 1.5 2nd half
"""

                    send(msg)
                    seen.add(match_id)

                except Exception as e:
                    print("Match error:", e)

            time.sleep(300)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
