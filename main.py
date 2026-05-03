from dotenv import load_dotenv
load_dotenv()

import requests
import time
import os
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import csv

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
RESULTS_CSV = "results.csv"

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

def get_odds(fixture_id):
    try:
        r = requests.get(f"{BASE_URL}/odds?fixture={fixture_id}", headers=HEADERS)
        data = r.json().get("response", [])

        if not data:
            return None

        for book in data[0].get("bookmakers", []):
            for bet in book.get("bets", []):
                if bet["name"] == "Goals Over/Under":
                    return bet["values"]

        return None

    except Exception as e:
        logging.error(f"Odds error: {e}")
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

def estimate_probability(stats, delta, minute):
    prob = 0.45

    if stats["shots"] >= 10:
        prob += 0.10

    if stats["sot"] >= 4:
        prob += 0.15

    if delta["shots"] >= 3:
        prob += 0.10

    if minute >= 60:
        prob += 0.05

    return min(prob, 0.85)

def prob_to_odds(prob):
    if prob == 0:
        return None
    return round(1 / prob, 2)

def get_target_odds(odds_data, total_goals):
    if not odds_data:
        return None

    target = float(total_goals) + 1.5

    for o in odds_data:
        try:
            val = o["value"].replace("Over ", "").strip()
            if abs(float(val) - target) < 0.01:
                return float(o["odd"])
        except:
            continue

    return None
    
def calculate_value(book_odds, fair_odds):
    try:
        return round(((book_odds / fair_odds) - 1) * 100, 2)
    except:
        return None
        
# =========================
# SAVE RESULTS
# =========================
def save_result_to_file(data):
    try:
        with open("results.json", "a") as f:
            f.write(json.dumps(data, default=str) + "\n")
    except Exception as e:
        logging.error(f"Save JSON error: {e}")

def save_result_to_csv(data):
    try:
        file_exists = os.path.isfile(RESULTS_CSV)

        with open(RESULTS_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "match",
                "result",
                "signal_tier",
                "model_score",

                # 🔥 ODDS + VALUE
                "book_odds",
                "fair_odds",
                "model_prob",
                "value",

                # SCORES
                "track_score",
                "signal_score",
                "final_score",

                # TIME
                "track_minute",
                "signal_minute",
                "signal_time",
                
                # TRACK STATS
                "track_shots",
                "track_sot",
                "track_corners",

                # SIGNAL STATS
                "signal_shots",
                "signal_sot",
                "signal_corners",

                # DELTA
                "delta_shots",
                "delta_sot",
                "delta_corners",

                "goals_at_signal"
            ])

            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "match": data.get("match"),
                "result": data.get("result"),
                "signal_tier": data.get("signal_tier"),
                "model_score": data.get("model_score"),

                # 🔥 NEW DATA
                "book_odds": data.get("book_odds"),
                "fair_odds": data.get("fair_odds"),
                "model_prob": round(data.get("model_prob", 0), 3) if data.get("model_prob") else None,
                "value": data.get("value"),

                # SCORES
                "track_score": data.get("track_score"),
                "signal_score": data.get("signal_score"),
                "final_score": data.get("final_score"),

                # TIME
                "track_minute": data.get("track_minute"),
                "signal_minute": data.get("signal_minute"),
                "signal_time": data.get("signal_time"),
                
                # TRACK STATS
                "track_shots": data.get("track_stats", {}).get("shots"),
                "track_sot": data.get("track_stats", {}).get("sot"),
                "track_corners": data.get("track_stats", {}).get("corners"),

                # SIGNAL STATS
                "signal_shots": data.get("signal_stats", {}).get("shots"),
                "signal_sot": data.get("signal_stats", {}).get("sot"),
                "signal_corners": data.get("signal_stats", {}).get("corners"),

                # DELTA
                "delta_shots": data.get("delta", {}).get("shots"),
                "delta_sot": data.get("delta", {}).get("sot"),
                "delta_corners": data.get("delta", {}).get("corners"),

                "goals_at_signal": data.get("goals_at_signal")
            })

    except Exception as e:
        logging.error(f"CSV save error: {e}")

def generate_performance_report():
    try:
        if not os.path.exists("results.json"):
            logging.warning("No results file yet")
            return

        total = 0
        wins = 0

        tiers = {
            "🔥 ELITE": {"total": 0, "wins": 0},
            "🔥 STRONG": {"total": 0, "wins": 0},
            "⚡ MEDIUM": {"total": 0, "wins": 0},
        }

        today = datetime.now().date()
        today_total = 0
        today_wins = 0

        with open("results.json", "r") as f:
            for line in f:
                try:
                    r = json.loads(line)

                    total += 1

                    if r["result"] == "✅ WIN":
                        wins += 1

                    tier = r.get("signal_tier", "⚡ MEDIUM")

                    if tier not in tiers:
                        tiers[tier] = {"total": 0, "wins": 0}

                    tiers[tier]["total"] += 1

                    if r["result"] == "✅ WIN":
                        tiers[tier]["wins"] += 1

                    # DAILY FILTER (optional future upgrade: store date)
                    today_total += 1
                    if r["result"] == "✅ WIN":
                        today_wins += 1

                except:
                    continue

        if total == 0:
            return

        winrate = round((wins / total) * 100, 2)

        report = f"📊 PERFORMANCE REPORT\n\n"
        report += f"Total Signals: {total}\n"
        report += f"Winrate: {winrate}%\n\n"

        report += "📈 By Tier:\n"

        for tier, data in tiers.items():
            if data["total"] == 0:
                continue

            tier_wr = round((data["wins"] / data["total"]) * 100, 2)
            report += f"{tier}: {data['wins']}/{data['total']} ({tier_wr}%)\n"

        report += "\n📅 Today:\n"
        if today_total > 0:
            today_wr = round((today_wins / today_total) * 100, 2)
            report += f"{today_wins}/{today_total} ({today_wr}%)\n"
        else:
            report += "No data yet\n"

        logging.info(report)

        # 🔥 SEND TO TELEGRAM
        send_telegram(report)

    except Exception as e:
        logging.error(f"Report error: {e}")
        
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

            result_data = {
                "match": data["teams"],
                "result": result,
            
                # SCORES
                "track_score": data.get("track_score"),
                "signal_score": data.get("signal_score"),
                "final_score": f"{final_home}-{final_away}",
            
                # TIME
                "track_minute": data.get("track_minute"),
                "signal_minute": data.get("signal_minute"),
                "signal_time": data.get("signal_time"),
                
                # STATS
                "track_stats": data.get("track_stats"),
                "signal_stats": data.get("signal_stats"),
                "delta": data.get("delta"),
            
                # MODEL
                "model_score": data.get("model_score"),
                "signal_tier": data.get("signal_tier"),
            
                # ODDS + VALUE
                "book_odds": data.get("book_odds"),
                "fair_odds": data.get("fair_odds"),
                "model_prob": data.get("model_prob"),
                "value": data.get("value"),
            
                # EXTRA
                "goals_at_signal": data.get("goals_at_signal")
            }
            
            save_result_to_file(result_data)
            save_result_to_csv(result_data)

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
                                    "score": f"{home_goals}-{away_goals}",
                                    "time": datetime.now()
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

                        # =========================
                        # NEW SCORING ENGINE
                        # =========================
                        score = 40
                        
                        # draw = strong factor
                        if home_goals == away_goals:
                            score += 20
                        
                        # shots pressure
                        if stats["shots"] >= 12:
                            score += 15
                        elif stats["shots"] >= 9:
                            score += 10
                        
                        # shots on target = key signal
                        if stats["sot"] >= 5:
                            score += 20
                        elif stats["sot"] >= 3:
                            score += 10
                        
                        # momentum boost
                        delta_shots = stats["shots"] - first["track_stats"]["shots"]
                        if delta_shots >= 4:
                            score += 10

                        tier = classify(score)

                        # =========================
                        # ODDS + VALUE SYSTEM
                        # =========================
                        odds_data = get_odds(match_id)
                        
                        book_odds = get_target_odds(odds_data, total)
                        
                        delta = {
                            "shots": stats["shots"] - first["track_stats"]["shots"],
                            "sot": stats["sot"] - first["track_stats"]["sot"],
                            "corners": stats["corners"] - first["track_stats"]["corners"]
                        }
                        
                        prob = estimate_probability(stats, delta, minute)
                        fair_odds = prob_to_odds(prob)
                        
                        value = calculate_value(book_odds, fair_odds) if book_odds else None

                        if value is None or value < 5:
                        logging.info(
                            f"⛔ SKIPPED → {home} vs {away} | "
                            f"book:{book_odds} fair:{fair_odds} value:{value}"
                        )
                        continue

                        send_telegram(f"""{tier} VALUE SIGNAL

{home} vs {away}
Min: {minute}'
Score: {home_goals}-{away_goals}

🎯 Market: Over {total + 1.5}
💰 Book Odds: {book_odds}
🧠 Fair Odds: {fair_odds}
📊 Model Prob: {round(prob*100)}%
🔥 Value: {value}%

Shots: {stats['shots']}
SOT: {stats['sot']}
Corners: {stats['corners']}
""")

                        seen_matches[match_id] = {
                            "time": datetime.now(),
                            "teams": f"{home} vs {away}",
                        
                            # SCORES
                            "track_score": first["score"],
                            "signal_score": f"{home_goals}-{away_goals}",
                            "initial_score": f"{home_goals}-{away_goals}",
                        
                            # TIME
                            "track_minute": first["track_minute"],
                            "signal_minute": minute,
                            "signal_time": datetime.now().isoformat(),
                            
                            # STATS
                            "track_stats": first["track_stats"],
                            "signal_stats": stats,
                        
                            # MOMENTUM
                            "delta": delta,
                        
                            # MODEL
                            "model_score": score,
                            "signal_tier": tier,
                        
                            # ODDS + VALUE
                            "book_odds": book_odds,
                            "fair_odds": fair_odds,
                            "model_prob": prob,
                            "value": value,
                        
                            # EXTRA
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
                generate_performance_report()   # 👈 ADD THIS
                last_result_check = current_time

            # =========================
            # CLEANUP OLD TRACKED MATCHES
            # =========================
            # CLEANUP OLD TRACKED MATCHES
            now = datetime.now()
            
            for mid, t in list(tracked_matches.items()):
                try:
                    age = (now - datetime.fromisoformat(t["time"]) if isinstance(t["time"], str) else now - t["time"]).total_seconds()
            
                    if age > 3600:  # 1 hour
                        del tracked_matches[mid]
                except:
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
