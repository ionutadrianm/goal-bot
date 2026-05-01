import requests
import time
import random
import os

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")

BOT_TOKEN = os.getenv("8748189864:AAHw-ud38HMooNiFy_NffvoYLHbDzgeFPB0")
CHAT_ID = os.getenv("5741320219")

BASE_URL = "https://v3.football.api-sports.io"

HEADERS = {
    "x-apisports-key": API_KEY
}

seen_matches = set()

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# GET LIVE MATCHES
# =========================
def get_live_matches():
    try:
        url = f"{BASE_URL}/fixtures?live=all"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()

        return data.get("response", [])

    except Exception as e:
        print("Live error:", e)
        return []

# =========================
# GET EVENTS (GOALS)
# =========================
def get_events(match_id):
    try:
        url = f"{BASE_URL}/fixtures/events?fixture={match_id}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()

        return data.get("response", [])

    except:
        return []

# =========================
# COUNT 2ND HALF GOALS
# =========================
def count_second_half_goals(events):
    goals_2h = 0

    for e in events:
        if e["type"] == "Goal":
            minute = e["time"]["elapsed"]

            if minute and minute > 45:
                goals_2h += 1

    return goals_2h

# =========================
# MOMENTUM (REAL STATS)
# =========================
def get_stats(match_id):
    try:
        url = f"{BASE_URL}/fixtures/statistics?fixture={match_id}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json()["response"]

        stats = {}

        for team in data:
            for s in team["statistics"]:
                name = s["type"]
                value = s["value"] or 0

                if isinstance(value, str):
                    value = value.replace("%", "")
                    value = int(value) if value.isdigit() else 0

                stats[name] = stats.get(name, 0) + value

        return {
            "shots": stats.get("Total Shots", 0),
            "shots_on": stats.get("Shots on Goal", 0),
            "corners": stats.get("Corner Kicks", 0)
        }

    except:
        return {"shots": 0, "shots_on": 0, "corners": 0}

# =========================
# MOMENTUM SCORE
# =========================
def momentum_score(stats):
    score = 0

    if stats["shots"] >= 12:
        score += 10
    if stats["shots_on"] >= 5:
        score += 15
    if stats["corners"] >= 5:
        score += 10

    return score

# =========================
# MAIN LOOP
# =========================
def run():
    print("API-Football DIRECT bot running...")

    while True:
        try:
            matches = get_live_matches()
            print(f"Found {len(matches)} matches")

            for m in matches:
                try:
                    fixture = m["fixture"]
                    teams = m["teams"]
                    goals = m["goals"]

                    match_id = fixture["id"]
                    minute = fixture["status"]["elapsed"]

                    if not minute:
                        continue

                    if match_id in seen_matches:
                        continue

                    # =========================
                    # EVENTS (GOALS)
                    # =========================
                    events = get_events(match_id)
                    second_half_goals = count_second_half_goals(events)

                    print(
                        teams["home"]["name"],
                        "vs",
                        teams["away"]["name"],
                        "| min:", minute,
                        "| 2H goals:", second_half_goals
                    )

                    # =========================
                    # CONDITIONS
                    # =========================
                    ht_window = 38 <= minute <= 47
                    second_half_window = 55 <= minute <= 80 and second_half_goals <= 3

                    if not (ht_window or second_half_window):
                        continue

                    # =========================
                    # REAL MOMENTUM
                    # =========================
                    stats = get_stats(match_id)
                    boost = momentum_score(stats)

                    score = 50 + boost

                    tier = "⚡ MEDIUM"
                    if score >= 70:
                        tier = "🔥 STRONG"

                    # =========================
                    # ALERT
                    # =========================
                    msg = f"""
{tier} GOAL ALERT

{teams['home']['name']} vs {teams['away']['name']}
Minute: {minute}'

Score: {goals['home']}-{goals['away']}
2H Goals: {second_half_goals}

Shots: {stats['shots']}
SOT: {stats['shots_on']}
Corners: {stats['corners']}

Momentum Score: {score}

➡️ Over 1.5 2nd half
"""
                    send_telegram(msg)

                    seen_matches.add(match_id)

                    time.sleep(random.uniform(1, 2))

                except Exception as e:
                    print("Match error:", e)
                    continue

            time.sleep(180)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
