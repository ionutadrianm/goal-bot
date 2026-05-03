from dotenv import load_dotenv
load_dotenv()

import requests
import time
import os
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler

# =========================
# LOGGING
# =========================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler("bot.log", maxBytes=5_000_000, backupCount=3)
console_handler = logging.StreamHandler()

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

logging.info("🔥 Bot started")

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

SIGNALS_FILE = "signals.json"
TRACKED_FILE = "tracked.json"

# =========================
# PERSISTENCE
# =========================
def save_signals():
    try:
        with open(SIGNALS_FILE, "w") as f:
            json.dump(seen_matches, f, default=str)
    except Exception as e:
        logging.error(f"Save signals error: {e}")

def load_signals():
    global seen_matches
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, "r") as f:
                data = json.load(f)

                for k, v in data.items():
                    v["time"] = datetime.fromisoformat(v["time"])

                seen_matches = data
                logging.info(f"📂 Loaded {len(seen_matches)} active signals")
    except Exception as e:
        logging.error(f"Load signals error: {e}")

def save_tracked():
    try:
        with open(TRACKED_FILE, "w") as f:
            json.dump(tracked_matches, f, default=str)
    except Exception as e:
        logging.error(f"Save tracked error: {e}")

def load_tracked():
    global tracked_matches
    try:
        if os.path.exists(TRACKED_FILE):
            with open(TRACKED_FILE, "r") as f:
                tracked_matches = json.load(f)
                logging.info(f"📂 Loaded {len(tracked_matches)} tracked matches")
    except Exception as e:
        logging.error(f"Load tracked error: {e}")

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# =========================
# API
# =========================
def get_live_matches():
    try:
        r = requests.get(f"{BASE_URL}/fixtures?live=all", headers=HEADERS)
        data = r.json()
        return data.get("response", [])
    except Exception as e:
        logging.error(f"Live matches error: {e}")
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
        logging.error(f"Stats error: {e}")
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
        with open("results.json", "a") as f:
            f.write(json.dumps(data) + "\n")
    except Exception as e:
        logging.error(f"Save error: {e}")

# =========================
# RESULT CHECKER
# =========================
def check_finished_matches():
    logging.info("📊 Checking results...")

    for match_id, data in list(seen_matches.items()):
        try:
            time_since = (datetime.now() - data["time"]).total_seconds()

            if time_since < 2400:
                continue

            r = requests.get(f"{BASE_URL}/fixtures?id={match_id}", headers=HEADERS)
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

            initial_total = sum(map(int, data["initial_score"].split("-")))
            final_total = final_home + final_away

            result = "✅ WIN" if final_total >= initial_total + 2 else "❌ LOSS"

            save_result_to_file({
                "match": data["teams"],
                "result": result,
            
                # 🔥 SCORES
                "track_score": data["track_score"],
                "signal_score": data["signal_score"],
                "final_score": f"{final_home}-{final_away}",
            
                # 🔥 TIMING
                "track_minute": data["track_minute"],
                "signal_minute": data["signal_minute"],
            
                # 🔥 STATS
                "track_stats": data["track_stats"],
                "signal_stats": data["signal_stats"],
                "delta": data["delta"],
            
                # 🔥 MODEL
                "model_score": data["model_score"],
                "signal_tier": data["signal_tier"],
            
                # 🔥 EXTRA
                "goals_at_signal": data["goals_at_signal"]
            })

            logging.info(f"✅ RESULT → {data['teams']} | {result} | {final_home}-{final_away}")

            send_telegram(f"""
📊 RESULT UPDATE

{data['teams']}
Result: {result}

Start: {data['initial_score']}
Final: {final_home}-{final_away}
""")

            del seen_matches[match_id]
            save_signals()

        except Exception as e:
            logging.error(f"Result error: {e}")

# =========================
# MAIN LOOP
# =========================
def run():
    global last_result_check

    logging.info("🚀 PRO SCANNER RUNNING")

    while True:
        try:
            logging.info("🔁 NEW SCAN")

            matches = get_live_matches()

            if not matches:
                logging.warning("⚠️ No live matches")
                time.sleep(60)
                continue

            logging.info(f"📊 Matches: {len(matches)}")

            for m in matches[:80]:
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

                    # TRACK
                    if 30 <= minute <= 45:

                        if match_id not in tracked_matches:
                            if stats["shots"] >= 5:
                                tracked_matches[match_id] = {
                                    "teams": f"{home} vs {away}",
                                    "track_minute": minute,
                                    "track_stats": stats,
                                    "score": f"{home_goals}-{away_goals}"
                                }
                                save_tracked()
                                logging.info(f"🧠 TRACKED → {home} vs {away} | min:{minute}")

                    # CONFIRM
                    if 50 <= minute <= 65:

                        if match_id not in tracked_matches:
                            continue

                        if match_id in seen_matches:
                            continue

                        first = tracked_matches[match_id]

                        if stats["shots"] <= first["track_stats"]["shots"]:
                            continue

                        if stats["sot"] < 2:
                            continue

                        score = 50

                        if home_goals == away_goals:
                            score += 15
                        if stats["shots"] >= 10:
                            score += 10
                        if stats["sot"] >= 4:
                            score += 15

                        tier = classify(score)

                        send_telegram(f"""{tier} SIGNAL

{home} vs {away}
Min: {minute}'
Score: {home_goals}-{away_goals}

Shots: {stats['shots']}
SOT: {stats['sot']}
Corners: {stats['corners']}

➡️ Over 1.5 2nd half
""")

                        seen_matches[match_id] = {
                            "time": datetime.now(),
                        
                            "teams": f"{home} vs {away}",
                        
                            # 🔥 SCORES
                            "track_score": first["score"],
                            "signal_score": f"{home_goals}-{away_goals}",
                            "initial_score": f"{home_goals}-{away_goals}",
                        
                            # 🔥 MINUTES
                            "track_minute": first["track_minute"],
                            "signal_minute": minute,
                        
                            # 🔥 STATS
                            "track_stats": first["track_stats"],
                            "signal_stats": stats,
                        
                            # 🔥 MOMENTUM
                            "delta": {
                                "shots": stats["shots"] - first["track_stats"]["shots"],
                                "sot": stats["sot"] - first["track_stats"]["sot"],
                                "corners": stats["corners"] - first["track_stats"]["corners"]
                            },
                        
                            # 🔥 MODEL INFO
                            "model_score": score,
                            "signal_tier": tier,
                        
                            # 🔥 EXTRA
                            "goals_at_signal": total
                        }
                        del tracked_matches[match_id]
                        save_tracked()
                        save_signals()

                        logging.info(f"🚀 SIGNAL → {home} vs {away} | min:{minute}")

                except Exception as e:
                    logging.error(f"Match error: {e}")

            current_time = time.time()

            if seen_matches and current_time - last_result_check > 1800:
                check_finished_matches()
                last_result_check = current_time

            # =========================
            # CLEANUP OLD TRACKED MATCHES
            # =========================
            active_ids = [m["fixture"]["id"] for m in matches]
            
            for mid in list(tracked_matches.keys()):
                if mid not in active_ids:
                    del tracked_matches[mid]
            
            save_tracked()

            save_signals()

            time.sleep(300)

        except Exception as e:
            logging.error(f"LOOP ERROR: {e}")
            time.sleep(60)

# =========================
# START
# =========================
if __name__ == "__main__":
    load_signals()
    load_tracked()   # ✅ ADD THIS
    run()
