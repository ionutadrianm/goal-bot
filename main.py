import requests
import time
import os
from datetime import datetime
import json

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
last_result_check = 0

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

def save_result_to_file(data):
    line = json.dumps(data)
    
    print("📦 RESULT:", line)   # 👈 THIS IS KEY
    
    with open("results.json", "a") as f:
        f.write(line + "\n")
        
# =========================
# LOGIC
# =========================
def second_half_goals(events):
    return sum(1 for e in events if e["type"] == "Goal" and e["time"]["elapsed"] >= 46)

def momentum(stats, minute):
    score = 0

    components = {
        "shots_boost": 0,
        "sot_boost": 0,
        "corners_boost": 0,
        "late_sot_boost": 0
    }

    if stats["shots"] >= 8:
        score += 10
        components["shots_boost"] = 10

    if stats["sot"] >= 3:
        score += 15
        components["sot_boost"] = 15

    if stats["corners"] >= 5:
        score += 8
        components["corners_boost"] = 8

    if minute >= 60 and stats["sot"] >= 5:
        score += 10
        components["late_sot_boost"] = 10

    return score, components

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
        # ⏱ Only check matches older than 60 minutes
        time_since_signal = (datetime.now() - data["time"]).total_seconds()
        
        if time_since_signal < 5400:
            print(f"⏳ Too early to check match {match_id} ({int(time_since_signal/60)} min)")
            continue
    
        try:
            url = f"{BASE_URL}/fixtures?id={match_id}"
            r = requests.get(url, headers=HEADERS)
            res = r.json().get("response", [])

            if not res:
                continue

            fixture = res[0]["fixture"]
            goals = res[0]["goals"]

            status = fixture["status"]["short"]
            
            if not any(x in status for x in ["FT", "AET", "PEN"]):
                print(f"⏱ Still live: {status}")
                continue

            final_home = goals["home"] or 0
            final_away = goals["away"] or 0
            final_total = final_home + final_away

            initial_total = sum(map(int, data["initial_score"].split("-")))

            if final_total >= initial_total + 2:
                result = "✅ WIN"
            else:
                result = "❌ LOSS"

            save_result_to_file({
                "match_id": match_id,
                "result": result,
                "initial_score": data["initial_score"],
                "final_score": f"{final_home}-{final_away}",
                "model_score": data["model_score"],
                "stats": data["stats"],
                "goals_at_signal": data["goals_at_signal"],   # ✅ NEW
                "base_components": data["base_components"],
                "momentum_components": data["momentum_components"]
            })
        
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
    global last_result_check
    
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
                    goals_at_signal = total
                    
                    # 🔥 STRICT DEAD GAME FILTER
                    if total >= 3:
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

                    zero_goal_bonus = 20 if total == 0 else 0
                    one_goal_bonus = 10 if total == 1 else 0
                    draw_bonus = 15 if diff == 0 else 0
                    second_half_boost = 10 if (minute >= 50 and stats["shots"] >= 6) else 0
                    
                    # apply once
                    base += zero_goal_bonus + one_goal_bonus + draw_bonus + second_half_boost
                    
                    # ✅ DEFINE base_components (MISSING BEFORE)
                    base_components = {
                        "base": 50,
                        "zero_goal_bonus": zero_goal_bonus,
                        "one_goal_bonus": one_goal_bonus,
                        "draw_bonus": draw_bonus,
                        "second_half_boost": second_half_boost
                    }
                    
                    momentum_score, momentum_components = momentum(stats, minute)
                    final_score = base + momentum_score

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
                        "tier": classify(final_score),
                        "base_components": base_components,
                        "momentum_components": momentum_components,
                        "goals_at_signal": goals_at_signal,
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
                    "stats": game["stats"],
                    "model_score": game["final_score"],
                    "goals_at_signal": game["goals_at_signal"],
                    "base_components": game["base_components"],
                    "momentum_components": game["momentum_components"]
                }

            # ⏱ Run result check every 60 minutes
            # ⏱ Run result check every 60 minutes
            current_time = time.time()
            
            if seen_matches and current_time - last_result_check > 1800:
                print("🕒 Running result check (30 min interval)")
                check_finished_matches()
                last_result_check = current_time
                
            time.sleep(300)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
