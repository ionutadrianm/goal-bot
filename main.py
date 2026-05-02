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

    # 🔥 KEY CHECK
    if not data:
        return None   # instead of empty stats

    stats = {"shots": 0, "sot": 0, "corners": 0}

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
# RESULT TRACKER (STEP 2)
# =========================
def check_finished_matches():
    print("📊 Checking finished matches...")

    for match_id, data in list(seen_matches.items()):
        try:
            url = f"{BASE_URL}/fixtures?id={match_id}"
            r = requests.get(url, headers=HEADERS)
            res = r.json().get("response", [])

            if not res:
                continue

            fixture = res[0]["fixture"]
            goals = res[0]["goals"]

            status = fixture["status"]["short"]

            if status not in ["FT", "AET", "PEN"]:
                continue

            final_home = goals["home"] or 0
            final_away = goals["away"] or 0
            final_total = final_home + final_away

            initial_total = sum(map(int, data["initial_score"].split("-")))

            if final_total >= initial_total + 2:
                result = "✅ WIN"
            else:
                result = "❌ LOSS"

            print(f"{result} → Match {match_id}")

            send_telegram(f"""
📊 RESULT UPDATE

Match ID: {match_id}
Result: {result}

Start Score: {data['initial_score']}
Final Score: {final_home}-{final_away}

Shots: {data['stats']['shots']}
SOT: {data['stats']['sot']}
Corners: {data['stats']['corners']}
""")

            del seen_matches[match_id]

        except Exception as e:
            print("Result check error:", e)
            
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

            for m in matches[:50]:
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
                    # ❌ skip dead games (no comeback potential)
                    if total >= 3 and diff >= 2:
                        continue
    
                    # =========================
                    # FILTER (TIME FIRST)
                    # =========================
                    if minute < 35 or minute > 60:
                        continue

                    # if stats["shots"] < 7 and stats["corners"] < 4:
                    #    continue

                    # =========================
                    # EVENTS
                    # =========================
                    if minute >= 55:
                        events = get_events(match_id)
                        if second_half_goals(events) > 1:
                            continue

                    # =========================
                    # STATS
                    # =========================
                    stats = get_stats(match_id)

                    # ❌ no stats available at all
                    if stats is None:
                        continue
                    print(f"DEBUG → {home} vs {away} | min:{minute} | stats:{stats}")
                    
                    # ❌ no stats available
                    if stats["shots"] == 0 and stats["sot"] == 0 and stats["corners"] == 0:
                        continue

                    # ❌ weak activity
                    if stats["shots"] < 2 and stats["corners"] < 1:
                        continue

                    print(f"{home} vs {away} | {minute}' | {home_goals}-{away_goals} | {stats}")

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

                    # 🔥 2ND HALF GOAL SETUP BOOST
                    if minute >= 50:
                        if stats["shots"] >= 6:
                            base += 10
        
                    final_score = base + momentum(stats, minute)

                    # =========================
                    # DYNAMIC THRESHOLD
                    # =========================
                    if minute < 55:
                        if final_score < 45:
                            continue
                    else:
                        if final_score < 65:
                            continue
                            
                    print(f"✅ PASS → {home} vs {away} | min:{minute} | score:{final_score}")
                    candidates.append({
                        "match_id": match_id,
                        "home": home,
                        "away": away,
                        "minute": minute,
                        "score": f"{home_goals}-{away_goals}",
                        "stats": stats,
                        "final_score": final_score,
                        "tier": classify(final_score)
                    })

                except Exception as e:
                    print("Match error:", e)

            print(f"📊 CANDIDATES FOUND: {len(candidates)}")
            
            # =========================
            # SEND TOP 3
            # =========================
            top = sorted(candidates, key=lambda x: x["final_score"], reverse=True)[:5]

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
                seen_matches[game["match_id"]] = {
                    "time": datetime.now(),
                    "minute": game["minute"],
                    "initial_score": game["score"],
                    "stats": game["stats"]
                }
            check_finished_matches()
                
            time.sleep(180)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
