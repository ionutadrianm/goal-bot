from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_web():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_web).start()

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

seen_matches = {}
tracked_matches = {}
last_result_check = 0

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

# =========================
# API CALLS
# =========================
def get_live_matches():
    try:
        r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=HEADERS)
        return r.json().get("response", [])
    except Exception as e:
        print("Live matches error:", e)
        return []

def get_events(fixture_id):
    try:
        r = requests.get(f"{BASE_URL}/fixtures/events?fixture={fixture_id}", headers=HEADERS)
        return r.json().get("response", [])
    except:
        return []

def get_stats(fixture_id):
    try:
        r = requests.get(f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}", headers=HEADERS)
        data = r.json().get("response", [])

        if not data:
            return None

        stats = {"shots": 0, "sot": 0, "corners": 0}

        for team in data:
            for s in team.get("statistics", []):
                try:
                    val = int(s.get("value") or 0)
                except:
                    val = 0

                if s["type"] == "Total Shots":
                    stats["shots"] += val
                elif s["type"] == "Shots on Goal":
                    stats["sot"] += val
                elif s["type"] == "Corner Kicks":
                    stats["corners"] += val

        return stats

    except Exception as e:
        print("Stats error:", e)
        return None

# =========================
# LOGIC
# =========================
def second_half_goals(events):
    return sum(1 for e in events if e["type"] == "Goal" and e["time"]["elapsed"] >= 46)

def classify(score):
    if score >= 85:
        return "🔥 ELITE"
    elif score >= 70:
        return "🔥 STRONG"
    else:
        return "⚡ MEDIUM"

# =========================
# SAVE RESULTS
# =========================
def save_result_to_file(data):
    try:
        line = json.dumps(data)
        print("📦 RESULT:", line)
        with open("results.json", "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print("Save error:", e)

# =========================
# RESULT CHECKER
# =========================
def check_finished_matches():
    print("📊 Checking finished matches...")

    for match_id, data in list(seen_matches.items()):
        try:
            # wait at least 90 min after signal
            time_since = (datetime.now() - data["time"]).total_seconds()
            if time_since < 5400:
                continue

            r = requests.get(f"{BASE_URL}/fixtures?id={match_id}", headers=HEADERS)
            res = r.json().get("response", [])

            if not res:
                continue

            fixture = res[0]["fixture"]
            goals = res[0]["goals"]
            status = fixture["status"]["short"]

            if status not in ["FT", "AET", "PEN"]:
                print(f"⏱ Still live: {status}")
                continue

            final_home = goals["home"] or 0
            final_away = goals["away"] or 0

            initial_total = sum(map(int, data["initial_score"].split("-")))
            final_total = final_home + final_away

            result = "✅ WIN" if final_total >= initial_total + 2 else "❌ LOSS"

            save_result_to_file({
                "match": data["teams"],
                "result": result,
                "initial_score": data["initial_score"],
                "final_score": f"{final_home}-{final_away}",
                "model_score": data["model_score"],
                "stats": data["stats"]
            })

            send_telegram(f"""
📊 RESULT UPDATE

{data['teams']}
Result: {result}

Start: {data['initial_score']}
Final: {final_home}-{final_away}
""")

            del seen_matches[match_id]

        except Exception as e:
            print("Result check error:", e)

# =========================
# MAIN LOOP
# =========================
def run():
    global last_result_check

    print("🚀 PRO SCANNER RUNNING")

    while True:
        try:
            print("\n🔁 NEW SCAN CYCLE")
            print("💓 alive:", datetime.now())

            # SAFE API CALL
            matches = get_live_matches()

            if not matches:
                print("⚠️ No matches found")
                time.sleep(60)
                continue

            print(f"📊 Found {len(matches)} matches")

            for m in matches[:50]:
                try:
                    fixture = m["fixture"]
                    teams = m["teams"]
                    goals = m["goals"]

                    match_id = fixture["id"]
                    minute = fixture["status"]["elapsed"]

                    if not minute:
                        continue

                    home = teams["home"]["name"]
                    away = teams["away"]["name"]

                    home_goals = goals["home"] or 0
                    away_goals = goals["away"] or 0
                    total = home_goals + away_goals

                    # ❌ skip dead games
                    if total >= 3:
                        continue

                    stats = get_stats(match_id)

                    # ❌ no stats available at all
                    if stats is None:
                        print(f"❌ NO STATS → {home} vs {away}")
                        continue
                    
                    # 🔍 DEBUG SNAPSHOT (KEY LINE)
                    print(f"CHECK → {home} vs {away} | min:{minute} | shots:{stats['shots']} sot:{stats['sot']} corners:{stats['corners']}")

                    print(f"DEBUG → {home} vs {away} | min:{minute} | stats:{stats}")

                    # =========================
                    # PHASE 1 — TRACK
                    # =========================
                    if 35 <= minute <= 45:
                    
                        print(f"🟡 TRACK CHECK → {home} | min:{minute} | shots:{stats['shots']} sot:{stats['sot']}")
                    
                        if match_id in tracked_matches:
                            print(f"❌ ALREADY TRACKED → {home}")
                            continue
                    
                        if stats["shots"] < 6:
                        print(f"❌ TRACK FAIL (LOW SHOTS) → {home}")
                        continue
                    
                        tracked_matches[match_id] = {
                            "teams": f"{home} vs {away}",
                            "first_stats": stats,
                            "score": f"{home_goals}-{away_goals}",
                            "minute": minute
                        }
                    
                        print(f"🧠 TRACKED → {home} vs {away}")

                    # =========================
                    # PHASE 2 — CONFIRM
                    # =========================
                    if 50 <= minute <= 65:

                    print(f"🔵 CONFIRM CHECK → {home} | min:{minute} | shots:{stats['shots']} sot:{stats['sot']}")
                
                    if match_id not in tracked_matches:
                        print(f"❌ NOT TRACKED BEFORE → {home}")
                        continue
                
                    if match_id in seen_matches:
                        print(f"❌ ALREADY SENT → {home}")
                        continue

                        first = tracked_matches[match_id]
                        first_stats = first["first_stats"]

                        # momentum check
                        if stats["shots"] <= first_stats["shots"]:
                            print(f"❌ NO MOMENTUM → {home} | {stats['shots']} <= {first_stats['shots']}")
                            continue

                        if stats["sot"] < 3:
                            print(f"❌ CONFIRM FAIL (LOW SOT) → {home} | sot:{stats['sot']}")
                            continue

                        score = 50

                        if home_goals == away_goals:
                            score += 15
                        if stats["shots"] >= 10:
                            score += 10
                        if stats["sot"] >= 4:
                            score += 15

                        tier = classify(score)

                        msg = f"""{tier} CONFIRMED SIGNAL

{home} vs {away}
Min: {minute}'
Score: {home_goals}-{away_goals}

Shots: {stats['shots']}
SOT: {stats['sot']}
Corners: {stats['corners']}

➡️ Over 1.5 2nd half
"""

                        send_telegram(msg)

                        seen_matches[match_id] = {
                            "time": datetime.now(),
                            "teams": f"{home} vs {away}",
                            "initial_score": f"{home_goals}-{away_goals}",
                            "stats": stats,
                            "model_score": score
                        }

                        print(f"🚀 SIGNAL SENT → {home} vs {away}")

                except Exception as e:
                    print("Match error:", e)

            # =========================
            # RESULT CHECK (30 min)
            # =========================
            current_time = time.time()

            if seen_matches and current_time - last_result_check > 1800:
                print("🕒 Running result check...")
                check_finished_matches()
                last_result_check = current_time

            time.sleep(300)

        except Exception as e:
            print("❌ LOOP ERROR:", e)
            time.sleep(60)

# =========================
# START
# =========================
if __name__ == "__main__":
    run()
