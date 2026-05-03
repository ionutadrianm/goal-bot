print("🔑 API KEY LOADED:", API_KEY[:6] if API_KEY else "NONE")
import requests
import time
import os
from datetime import datetime
import json
from dotenv import load_dotenv
load_dotenv()

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
        url = f"{BASE_URL}/fixtures?live=all"
        r = requests.get(url, headers=HEADERS)

        print("🌐 URL:", url)
        print("📡 STATUS:", r.status_code)
        print("📦 RAW RESPONSE:", r.text[:500])  # first 500 chars

        data = r.json()

        print("📊 API RESULTS COUNT:", len(data.get("response", [])))

        return data.get("response", [])

    except Exception as e:
        print("❌ Live matches error:", e)
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

import threading

def heartbeat():
    while True:
        print(f"💓 heartbeat: {datetime.now()}")
        time.sleep(60)

threading.Thread(target=heartbeat, daemon=True).start()

# =========================
# MAIN LOOP
# =========================
def run():
    global last_result_check

    print("🚀 PRO SCANNER RUNNING")

    while True:
        print("🔁 LOOP START")
        try:
            print("\n🔁 NEW SCAN CYCLE")
            print("💓 alive:", datetime.now())

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

                    if minute < 30 or minute > 70:
                        continue

                    home = teams["home"]["name"]
                    away = teams["away"]["name"]

                    home_goals = goals["home"] or 0
                    away_goals = goals["away"] or 0
                    total = home_goals + away_goals

                    if total >= 3:
                        continue

                    stats = get_stats(match_id)

                    if stats is None:
                        continue

                    if 35 <= minute <= 45:
                        print(f"🟡 TRACK WINDOW → {home} | shots:{stats['shots']} sot:{stats['sot']}")
                    
                    if 50 <= minute <= 65:
                        print(f"🔵 CONFIRM WINDOW → {home} | shots:{stats['shots']} sot:{stats['sot']}")

                    # =========================
                    # TRACK PHASE
                    # =========================
                    if 35 <= minute <= 45:

                        print(f"🟡 TRACK CHECK → {home}")

                        if match_id in tracked_matches:
                            continue

                        if stats["shots"] < 6:
                            print(f"❌ TRACK FAIL → {home}")
                            continue

                        tracked_matches[match_id] = {
                            "teams": f"{home} vs {away}",
                            "first_stats": stats,
                            "score": f"{home_goals}-{away_goals}"
                        }

                        print(f"🧠 TRACKED → {home}")

                    # =========================
                    # CONFIRM PHASE
                    # =========================
                    if 50 <= minute <= 65:

                        print(f"🔵 CONFIRM CHECK → {home}")

                        if match_id not in tracked_matches:
                            continue

                        if match_id in seen_matches:
                            continue

                        first_stats = tracked_matches[match_id]["first_stats"]

                        if stats["shots"] <= first_stats["shots"]:
                            print(f"❌ NO MOMENTUM → {home}")
                            continue

                        if stats["sot"] < 2:
                            print(f"❌ LOW SOT → {home}")
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

                        print(f"🚀 SIGNAL SENT → {home}")

                except Exception as e:
                    print("Match error:", e)

            current_time = time.time()

            if seen_matches and current_time - last_result_check > 1800:
                print("🕒 Running result check...")
                check_finished_matches()
                last_result_check = current_time
                
            print("✅ LOOP COMPLETED")
            print("⏳ Sleeping 5 min before next scan...")
            
            print("⏳ Keeping alive...")

            for i in range(300):
                print(f"tick {i}")
                time.sleep(1)

        except Exception as e:
            print("❌ LOOP ERROR:", e)
            time.sleep(60)

# =========================
# START
# =========================
if __name__ == "__main__":
    while True:
        try:
            run()
        except Exception as e:
            print("🔥 Restarting after error:", e)
            time.sleep(10)
