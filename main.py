import requests
import time
import random

# =========================
# CONFIG
# =========================
import os

API_KEY = os.getenv("b798571195msh3c97b8dc956c8bep1c16bbjsna432f73fe40e")
HOST = os.getenv("portapi7.p.rapidapi.com")

BOT_TOKEN = os.getenv("8748189864:AAHw-ud38HMooNiFy_NffvoYLHbDzgeFPB0")
CHAT_ID = os.getenv("5741320219")

BASE_URL = "https://sofascore.p.rapidapi.com/events/live"

HEADERS = {
    "X-RapidAPI-Key": API_KEY,
    "X-RapidAPI-Host": HOST
}

seen_matches = set()

# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# =========================
# GET LIVE MATCHES
# =========================
def get_live_matches():
    try:
        time.sleep(random.uniform(1, 3))

        url = "https://api.sofascore.com/api/v1/sport/football/events/live"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
            "Referer": "https://www.sofascore.com/",
        }

        r = requests.get(url, headers=headers, timeout=10)

        if r.status_code != 200:
            print("Bad response:", r.status_code)
            return []

        data = r.json()

        matches = []

        for event in data.get("events", []):
            try:
                minute = event.get("time", {}).get("played")

                print(
                    event["homeTeam"]["name"],
                    "vs",
                    event["awayTeam"]["name"],
                    "| min:", minute,
                    "| score:",
                    event["homeScore"]["current"],
                    "-",
                    event["awayScore"]["current"]
                )

                if not minute:
                    continue

                total_goals = event["homeScore"]["current"] + event["awayScore"]["current"]

                ht_home = event["homeScore"].get("period1", 0) or 0
                ht_away = event["awayScore"].get("period1", 0) or 0

                ht_goals = ht_home + ht_away
                second_half_goals = total_goals - ht_goals

                print("HT:", ht_goals, "| 2H:", second_half_goals)

                # ✅ CONDITIONS
                ht_window = 38 <= minute <= 47
                second_half_window = 55 <= minute <= 70 and second_half_goals <= 1

                if ht_window or second_half_window:
                    matches.append({
                        "id": event["id"],
                        "home": event["homeTeam"]["name"],
                        "away": event["awayTeam"]["name"],
                        "minute": minute,
                        "homeScore": event["homeScore"]["current"],
                        "awayScore": event["awayScore"]["current"]
                    })

            except:
                continue

        return matches

    except Exception as e:
        print("Error:", e)
        return []

# =========================
# GET STATS
# =========================
def get_stats(match_id):
    try:
        url = f"https://sofascore.p.rapidapi.com/event/statistics"
        params = {"event_id": match_id}

        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        data = r.json()

        stats = data["statistics"][0]["groups"][0]["statisticsItems"]

        def get(name):
            for s in stats:
                if s["name"] == name:
                    return float(s["home"]) + float(s["away"])
            return 0

        return (
            get("Expected goals"),
            get("Total shots"),
            get("Shots on target"),
            get("Corner kicks")
        )

    except:
        return None, None, None, None

# =========================
# SCORING + MOMENTUM
# =========================
def calculate_score(xg, shots, sot, corners, score_diff):
    score = 0

    # xG
    if xg >= 2.2: score += 30
    elif xg >= 1.8: score += 25
    elif xg >= 1.4: score += 20
    elif xg >= 1.0: score += 10

    # shots
    if shots >= 18: score += 20
    elif shots >= 14: score += 15
    elif shots >= 10: score += 10

    # SOT
    if sot >= 8: score += 20
    elif sot >= 6: score += 15
    elif sot >= 4: score += 10

    # corners
    if corners >= 8: score += 10
    elif corners >= 6: score += 8
    elif corners >= 4: score += 5

    # game state
    if score_diff == 0: score += 20
    elif score_diff == 1: score += 15

    # 🔥 MOMENTUM BOOST
    if xg >= 1.8 and sot >= 6 and corners >= 5:
        score += 15

    return score

# =========================
# TIER
# =========================
def classify(score):
    if score >= 80:
        return "🔥 STRONG"
    elif score >= 65:
        return "⚡ MEDIUM"
    return None

# =========================
# MAIN LOOP
# =========================
def run():
    print("RapidAPI SofaScore bot running...")

    while True:
        try:
            matches = get_live_matches()
            print(f"Found {len(matches)} matches")

            for m in matches:
                if m["id"] in seen_matches:
                    continue

                time.sleep(random.uniform(1, 3))

                xg, shots, sot, corners = get_stats(m["id"])

                if xg is None:
                    continue

                score_diff = abs(m["homeScore"] - m["awayScore"])

                score = calculate_score(xg, shots, sot, corners, score_diff)
                tier = classify(score)

                if tier:
                    msg = f"""
{tier} 2H GOAL ALERT

{m['home']} vs {m['away']}
Minute: {m['minute']}'
Score: {m['homeScore']}-{m['awayScore']}

xG: {round(xg,2)}
Shots: {shots}
SOT: {sot}
Corners: {corners}

Model Score: {score}

➡️ Over 1.5 2nd half
"""
                    send_telegram(msg)
                    seen_matches.add(m["id"])

            time.sleep(300)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(60)

if __name__ == "__main__":
    run()
