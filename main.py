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
                "initial_score": data["initial_score"],
                "final_score": f"{final_home}-{final_away}",
                "track_minute": data["track_minute"],
                "signal_minute": data["signal_minute"],
                "track_stats": data["track_stats"],
                "signal_stats": data["signal_stats"],
                "delta": data["delta"],
                "goals_at_signal": data["goals_at_signal"],
                "model_score": data["model_score"]
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
                            "initial_score": f"{home_goals}-{away_goals}",
                            "goals_at_signal": total,
                            "track_minute": first["track_minute"],
                            "track_stats": first["track_stats"],
                            "signal_minute": minute,
                            "signal_stats": stats,
                            "delta": {
                                "shots": stats["shots"] - first["track_stats"]["shots"],
                                "sot": stats["sot"] - first["track_stats"]["sot"],
                                "corners": stats["corners"] - first["track_stats"]["corners"]
                            },
                            "model_score": score
                        }

                        save_signals()

                        logging.info(f"🚀 SIGNAL → {home} vs {away} | min:{minute}")

                except Exception as e:
                    logging.error(f"Match error: {e}")

            current_time = time.time()

            if seen_matches and current_time - last_result_check > 1800:
                check_finished_matches()
                last_result_check = current_time

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
    run()
