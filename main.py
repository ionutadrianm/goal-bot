import requests
import time
import json
import os
from datetime import datetime

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("API_FOOTBALL_KEY")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_URL = "https://v3.football.api-sports.io"
FILE = "data.json"

HEADERS = {
    "x-apisports-key": API_KEY
}

seen_matches = set()

# =========================
# FILE STORAGE
# =========================
def load_data():
    try:
        with open(FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_data(data):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=2)

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    return r.json()["result"]["message_id"]

def send_reply(msg_id, result, score):
    text = f"{'✅ WIN' if result=='WIN' else '❌ LOSS'}\nFinal: {score}"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": text,
        "reply_to_message_id": msg_id
    })

# =========================
# API CALLS
# =========================
def get_live_matches():
    url = f"{BASE_URL}/fixtures?live=all"
    r = requests.get(url, headers=HEADERS)
    return r.json()["response"]

def get_events(fixture_id):
    url = f"{BASE_URL}/fixtures/events?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS)
    return r.json()["response"]

def get_stats(fixture_id):
    url = f"{BASE_URL}/fixtures/statistics?fixture={fixture_id}"
    r = requests.get(url, headers=HEADERS)
    data = r.json()["response"]

    stats = {"shots":0, "shots_on_target":0, "corners":0}

    try:
        for team in data:
            for s in team["statistics"]:
                if s["type"] == "Total Shots":
                    stats["shots"] += int(s["value"] or 0)
                if s["type"] == "Shots on Goal":
                    stats["shots_on_target"] += int(s["value"] or 0)
                if s["type"] == "Corner Kicks":
                    stats["corners"] += int(s["value"] or 0)
    except:
        pass

    return stats

# =========================
# GOAL LOGIC
# =========================
def count_second_half_goals(events):
    count = 0
    for e in events:
        if e["type"] == "Goal" and e["time"]["elapsed"] >= 46:
            count += 1
    return count

# =========================
# MOMENTUM ENGINE ⚡
# =========================
def momentum_engine(stats, minute):
    boost = 0

    shots = stats["shots"]
    sot = stats["shots_on_target"]
    corners = stats["corners"]

    # base momentum
    if shots >= 10: boost += 10
    if sot >= 4: boost += 15
    if corners >= 5: boost += 8

    # spike detection (late game pressure)
    if minute >= 60:
        if sot >= 5: boost += 10
        if corners >= 6: boost += 5

    return boost

# =========================
# TIER SYSTEM V2 🔥
# =========================
def classify(score):
    if score >= 85:
        return "🔥 ELITE"
    elif score >= 70:
        return "🔥 STRONG"
    else:
        return "⚡ MEDIUM"

# =========================
# SAVE MATCH
# =========================
def save_match(match_id, home, away, ht_score, msg_id, odds, score, tier):
    data = load_data()

    data.append({
        "id": match_id,
        "home": home,
        "away": away,
        "ht_score": ht_score,
        "ft_score": None,
        "status": "pending",
        "msg_id": msg_id,
        "score": score,
        "tier": tier,
        "odds": odds,
        "date": str(datetime.now().date())
    })

    save_data(data)

# =========================
# RESULT CHECK
# =========================
def check_results():
    data = load_data()
    updated = False

    for m in data:
        if m["status"] != "pending":
            continue

        try:
            url = f"{BASE_URL}/fixtures?id={m['id']}"
            r = requests.get(url, headers=HEADERS)
            event = r.json()["response"][0]

            if event["fixture"]["status"]["short"] == "FT":
                home = event["goals"]["home"]
                away = event["goals"]["away"]

                ft_goals = home + away
                ht_home, ht_away = map(int, m["ht_score"].split("-"))
                ht_goals = ht_home + ht_away

                second_half_goals = ft_goals - ht_goals

                result = "WIN" if second_half_goals >= 1 else "LOSS"

                m["status"] = result
                m["ft_score"] = f"{home}-{away}"

                send_reply(m["msg_id"], result, m["ft_score"])
                updated = True

        except:
            continue

    if updated:
        save_data(data)

# =========================
# DAILY REPORT 📊
# =========================
def daily_report():
    data = load_data()
    today = str(datetime.now().date())

    matches = [m for m in data if m["date"] == today and m["status"] != "pending"]

    if not matches:
        return

    wins = sum(1 for m in matches if m["status"] == "WIN")
    total = len(matches)

    winrate = round((wins / total) * 100, 2)

    msg = f"""
📊 DAILY REPORT

Signals: {total}
Wins: {wins}
Winrate: {winrate}%
"""
    send_telegram(msg)

# =========================
# MAIN LOOP
# =========================
send_telegram("✅ BOT IS ALIVE")
def run():
    print("API-Football bot running...")

    last_report_day = None

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
            
                    if minute is None:
                        continue
            
                    if match_id in seen_matches:
                        continue
            
                    home = teams["home"]["name"]
                    away = teams["away"]["name"]
            
                    # =========================
                    # EVENTS (GOALS)
                    # =========================
                    events = get_events(match_id)
                    second_half_goals = count_second_half_goals(events)
            
                    print(f"{home} vs {away} | min: {minute} | 2H goals: {second_half_goals}")
            
                    # =========================
                    # MAIN FILTER ONLY
                    # =========================
                    ht_window = 35 <= minute <= 50
                    second_half_window = 55 <= minute <= 80 and second_half_goals <= 3
            
                    # 🔍 DEBUG WHY SKIPPED
                    if not valid_window:
                        print(f"❌ Skipped {home} vs {away} | min: {minute}")
                        continue
            
                    # ✅ DEBUG PASSED
                    print(f"✅ PASSED FILTER: {home} vs {away}")
            
                    # =========================
                    # EXTRA SAFETY (OPTIONAL BUT GOOD)
                    # =========================
                    if goals["home"] is None or goals["away"] is None:
                        print(f"⚠️ Missing score data: {home} vs {away}")
                        continue
            
                    current_goals = goals["home"] + goals["away"]

                    # =========================
                    # MAIN FILTER ONLY
                    # =========================
                    valid_window = (
                        (35 <= minute <= 50) or
                        (55 <= minute <= 90 and second_half_goals <= 1)
                    )

                    if not valid_window:
                        continue

                    # =========================
                    # STATS (NOT FILTER)
                    # =========================
                    stats = get_stats(match_id)
                    boost = momentum_engine(stats, minute)

                    score = 50 + boost
                    tier = classify(score)

                    ht_score = f"{goals['home']}-{goals['away']}"

                    msg = f"""
{tier} SIGNAL

{home} vs {away}
Min: {minute}'
Score: {ht_score}

Shots: {stats['shots']}
SOT: {stats['shots_on_target']}
Corners: {stats['corners']}

Momentum: +{boost}
Model Score: {score}

➡️ Over 1.5 2nd half
"""

                    msg_id = send_telegram(msg)

                    save_match(match_id, home, away, ht_score, msg_id, None, score, tier)

                    seen_matches.add(match_id)

                except Exception as e:
                    print("Match error:", e)

            check_results()

            today = datetime.now().date()
            if last_report_day != today:
                daily_report()
                last_report_day = today

            time.sleep(30)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
