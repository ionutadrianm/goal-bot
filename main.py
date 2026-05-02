import requests
import time
import os
from datetime import datetime

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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
# API CALLS (OPTIMIZED)
# =========================
def get_live_matches():
    url = f"{BASE_URL}/fixtures?live=all"
    r = requests.get(url, headers=HEADERS)
    return r.json().get("response", [])

def get_events(fixture_id):
    url = f"{BASE_URL}/fixtures/events?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS)
    return r.json().get("response", [])

def get_stats(fixture_id):
    url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS)
    data = r.json().get("response", [])

    stats = {"shots":0, "sot":0, "corners":0}

    try:
        for team in data:
            for s in team["statistics"]:
                if s["type"] == "Total Shots":
                    stats["shots"] += int(s["value"] or 0)
                elif s["type"] == "Shots on Goal":
                    stats["sot"] += int(s["value"] or 0)
                elif s["type"] == "Corner Kicks":
                    stats["corners"] += int(s["value"] or 0)
    except:
        pass

    return stats

# =========================
# GOAL LOGIC
# =========================
def second_half_goals(events):
    return sum(1 for e in events if e["type"] == "Goal" and e["time"]["elapsed"] >= 46)

# =========================
# MOMENTUM ENGINE
# =========================
def momentum(stats, minute):
    score = 0

    if stats["shots"] >= 10: score += 10
    if stats["sot"] >= 4: score += 15
    if stats["corners"] >= 5: score += 8

    if minute >= 60:
        if stats["sot"] >= 5: score += 10

    return score

# =========================
# TIER SYSTEM V2
# =========================
def classify(score):
    if score >= 85:
        return "🔥 ELITE"
    elif score >= 70:
        return "🔥 STRONG"
    else:
        return "⚡ MEDIUM"

# =========================
# SMART SCAN WINDOW
# =========================
def should_scan():
    m = datetime.now().minute
    return (38 <= m <= 47) or (55 <= m <= 70)

# =========================
# MAIN LOOP
# =========================
def run():
    print("🚀 API-Football Scanner Running")

    while True:
        try:
            # TEMP: ALWAYS SCAN (TEST MODE)
            print("🧪 TEST MODE - scanning always")

            print("⏱ SCAN WINDOW ACTIVE")

            matches = get_live_matches()
            print(f"Found {len(matches)} matches")

            for m in matches[:5]:  # LIMIT = API SAFETY
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

                    home = teams["home"]["name"]
                    away = teams["away"]["name"]

                    home_goals = goals["home"] or 0
                    away_goals = goals["away"] or 0

                    total = home_goals + away_goals
                    diff = abs(home_goals - away_goals)

                    print(f"{home} vs {away} | {minute}' | {home_goals}-{away_goals}")

                    # =========================
                    # FILTER
                    # =========================
                    if not ((35 <= minute <= 50) or (55 <= minute <= 70)):
                        continue

                    if total > 2 or diff > 1:
                        continue

                    # =========================
                    # EVENTS
                    # =========================
                    events = get_events(match_id)
                    sh_goals = second_half_goals(events)

                    if minute >= 55 and sh_goals > 1:
                        continue

                    # =========================
                    # STATS
                    # =========================
                    stats = get_stats(match_id)

                    # =========================
                    # SCORING
                    # =========================
                    base = 50

                    if total == 0:
                        base += 20
                    elif total == 1:
                        base += 10

                    if diff == 0:
                        base += 15

                    boost = momentum(stats, minute)
                    final_score = base + boost

                    tier = classify(final_score)

                    print(f"✅ SIGNAL: {home} vs {away} | Score: {final_score}")

                    msg = f"""
{tier} SIGNAL

{home} vs {away}
Min: {minute}'
Score: {home_goals}-{away_goals}

Shots: {stats['shots']}
SOT: {stats['sot']}
Corners: {stats['corners']}

Model Score: {final_score}

➡️ Over 1.5 2nd half
"""

                    send_telegram(msg)
                    seen_matches.add(match_id)

                    time.sleep(2)

                except Exception as e:
                    print("Match error:", e)

            time.sleep(180)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
