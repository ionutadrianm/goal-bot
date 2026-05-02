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

# store match_id -> timestamp
seen_matches = {}

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# API CALLS
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

    stats = {"shots": 0, "sot": 0, "corners": 0}

    if not data:
        return stats

    for team in data:
        for s in team.get("statistics", []):
            val = s.get("value")

            try:
                val = int(val) if val is not None else 0
            except:
                val = 0

            if s["type"] == "Total Shots":
                stats["shots"] += val
            elif s["type"] == "Shots on Goal":
                stats["sot"] += val
            elif s["type"] == "Corner Kicks":
                stats["corners"] += val

    return stats

# =========================
# LOGIC
# =========================
def second_half_goals(events):
    return sum(1 for e in events if e["type"] == "Goal" and e["time"]["elapsed"] >= 46)

def momentum(stats, minute):
    score = 0

    if stats["shots"] >= 8:
        score += 10
    if stats["sot"] >= 3:
        score += 15
    if stats["corners"] >= 5:
        score += 8

    if minute >= 60 and stats["sot"] >= 5:
        score += 10

    return score

def classify(score):
    if score >= 85:
        return "🔥 ELITE"
    elif score >= 70:
        return "🔥 STRONG"
    else:
        return "⚡ MEDIUM"

# =========================
# MAIN LOOP
# =========================
def run():
    print("🚀 API-Football Scanner Running")

    while True:
        try:
            print("🧪 TEST MODE - scanning always")

            matches = get_live_matches()
            print(f"Found {len(matches)} matches")

            candidates = []

            for m in matches[:15]:
                try:
                    fixture = m["fixture"]
                    teams = m["teams"]
                    goals = m["goals"]

                    match_id = fixture["id"]
                    minute = fixture["status"]["elapsed"]

                    if not minute:
                        continue

                    # prevent duplicates (already sent)
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
                    if minute < 30 or minute > 75:
                        continue

                    if total > 3 or diff > 2:
                        continue

                    if minute < 30 and total == 0:
                            continue
                        
                    # =========================
                    # EVENTS
                    # =========================
                    if minute >= 55:
                        events = get_events(match_id)
                        sh_goals = second_half_goals(events)

                        if sh_goals > 1:
                            continue

                    # =========================
                    # STATS
                    # =========================
                    stats = get_stats(match_id)
                    print("STATS:", stats)

                    # ❌ skip fake/no-data matches
                    # 🔥 DATA AVAILABILITY FILTER
                    stats = get_stats(match_id)
                    print("STATS:", stats)
                    
                    # ❌ No data at all → skip
                    if stats["shots"] == 0 and stats["sot"] == 0 and stats["corners"] == 0:
                        continue
                    
                    # ❌ Very low activity → skip (tuneable)
                    if stats["shots"] < 3 and stats["corners"] < 1:
                        continue

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

                    # =========================
                    # DYNAMIC THRESHOLD
                    # =========================
                    if minute < 55:
                        if final_score < 55:
                            continue
                    else:
                        if final_score < 65:
                            continue

                    tier = classify(final_score)

                    candidates.append({
                        "match_id": match_id,
                        "home": home,
                        "away": away,
                        "minute": minute,
                        "score": f"{home_goals}-{away_goals}",
                        "stats": stats,
                        "final_score": final_score,
                        "tier": tier
                    })

                except Exception as e:
                    print("Match error:", e)

            # =========================
            # SEND TOP 3 SIGNALS
            # =========================
            top = sorted(candidates, key=lambda x: x["final_score"], reverse=True)[:3]

            for game in top:
                if game["match_id"] in seen_matches:
                    continue

                msg = f"""{game['tier']} TOP SIGNAL

{game['home']} vs {game['away']}
Min: {game['minute']}'
Score: {game['score']}

Shots: {game['stats']['shots']}
SOT: {game['stats']['sot']}
Corners: {game['stats']['corners']}

Model Score: {game['final_score']}

➡️ Over 1.5 2nd half
"""

                send_telegram(msg)

                # mark as sent (store timestamp)
                seen_matches[game["match_id"]] = datetime.now()

            time.sleep(180)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
