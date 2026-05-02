import requests
import time
import os
from datetime import datetime

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("RAPIDAPI_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_URL = "https://flashscore4.p.rapidapi.com"

HEADERS = {
    "X-RapidAPI-Key": API_KEY,
    "X-RapidAPI-Host": "flashscore4.p.rapidapi.com"
}

seen_matches = set()

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# GET MATCHES
# =========================
def get_live_matches():
    url = f"{BASE_URL}/matches/v1/list"
    params = {"sportId": 1}

    r = requests.get(url, headers=HEADERS, params=params)

    print("STATUS:", r.status_code)
    print("RAW:", r.text[:500])
    
    data = r.json()
    print("KEYS:", data.keys())

    events = data.get("events", [])
    print("EVENT COUNT:", len(events))

    # filter only LIVE matches manually
    live_matches = []

    for e in events:
        if e.get("status", {}).get("type") == "live":
            live_matches.append(e)

    print("LIVE FILTERED:", len(live_matches))

    return live_matches

# =========================
# GET MATCH DETAIL
# =========================
def get_match_detail(event_id):
    url = f"{BASE_URL}/matches/v1/detail"
    params = {"eventId": event_id}
    r = requests.get(url, headers=HEADERS, params=params)
    return r.json()

# =========================
# COUNT 2H GOALS
# =========================
def count_second_half_goals(events):
    goals = 0
    for e in events:
        if e.get("type") == "goal":
            minute = e.get("time", 0)
            if minute >= 46:
                goals += 1
    return goals

# =========================
# MOMENTUM ENGINE
# =========================
def momentum_engine(stats, minute):
    boost = 0

    shots = stats.get("shots", 0)
    sot = stats.get("shots_on", 0)
    corners = stats.get("corners", 0)

    if shots >= 10: boost += 10
    if sot >= 4: boost += 15
    if corners >= 5: boost += 8

    if minute >= 60:
        if sot >= 5: boost += 10
        if corners >= 6: boost += 5

    return boost

# =========================
# VALUE (INFO ONLY)
# =========================
def value_info(score):
    prob = min(0.80, score / 120)
    fair_odds = round(1 / prob, 2)
    return prob, fair_odds

# =========================
# MAIN LOOP
# =========================
def run():
    print("⚡ Flashscore bot running...")

    while True:
        try:
            matches = get_live_matches()
            print(f"Matches: {len(matches)}")

            for m in matches:
                print("TEST MATCH:", m)
                
                try:
                    match_id = m["id"]
                    minute = m.get("time", 0)

                    home = m["home"]["name"]
                    away = m["away"]["name"]

                    if match_id in seen_matches:
                        continue

                    # 🔥 FILTER FIRST
                    if not (
                        (35 <= minute <= 50) or
                        (55 <= minute <= 80)
                    ):
                        continue

                    detail = get_match_detail(match_id)

                    events = detail.get("events", [])
                    stats = detail.get("stats", {})

                    second_half_goals = count_second_half_goals(events)

                    if minute >= 55 and second_half_goals > 1:
                        continue

                    print(f"✅ {home} vs {away} | {minute} | 2H:{second_half_goals}")

                    # =========================
                    # STATS + MODEL
                    # =========================
                    boost = momentum_engine(stats, minute)
                    score = 50 + boost

                    if score >= 85:
                        tier = "🔥 ELITE"
                    elif score >= 70:
                        tier = "🔥 STRONG"
                    else:
                        tier = "⚡ MEDIUM"

                    prob, fair_odds = value_info(score)

                    msg = f"""
{tier} SIGNAL

{home} vs {away}
Min: {minute}'

2H Goals: {second_half_goals}

Shots: {stats.get('shots', 0)}
SOT: {stats.get('shots_on', 0)}
Corners: {stats.get('corners', 0)}

Momentum: +{boost}
Score: {score}

Model Prob: {round(prob,2)}
Fair Odds: {fair_odds}

➡️ Over 1.5 2nd half
"""

                    send_telegram(msg)
                    seen_matches.add(match_id)

                    time.sleep(1.2)

                except Exception as e:
                    print("Match error:", e)

            time.sleep(180)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
