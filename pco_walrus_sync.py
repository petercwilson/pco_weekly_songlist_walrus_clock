import base64
import requests
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta, SU
from midiutil import MIDIFile

# ================= CONFIG =================

PC_APP_ID = "ef6859b2d409c09b0de1df2788d4551ff10d01ae348e079b207cb58fc96ae984"
PC_SECRET = "pco_pat_c99952c219805b5ec88f2c72564e39931a310fcf7620f7f302015b05f35ea77ed2910211"

PERSON_ID = "AC63069036#"  # from Planning Center People profile URL
TARGET_SERVICE_TYPE_NAME = "Celebration Service"

BASE_URL = "https://api.planningcenteronline.com/services/v2"

MIDI_OUTPUT = "weekly_setlist_with_meta.mid"
MIDI_CHANNEL = 0

# ================= HELPERS =================

def auth_header():
    token = f"{PC_APP_ID}:{PC_SECRET}"
    token_b64 = base64.b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {token_b64}"}

# ================= SERVICE TYPE =================

def get_service_type_id():
    headers = auth_header()
    resp = requests.get(f"{BASE_URL}/service_types", headers=headers)
    resp.raise_for_status()

    for svc in resp.json()["data"]:
        if svc["attributes"]["name"].lower() == TARGET_SERVICE_TYPE_NAME.lower():
            print("Using service type:", svc["attributes"]["name"])
            return svc["id"]

    raise Exception("Celebration Service not found.")

# ================= PLAN FINDERS =================

def find_plan_by_date(service_type_id, target_date):
    headers = auth_header()
    url = f"{BASE_URL}/service_types/{service_type_id}/plans"
    params = {"order": "sort_date"}

    while url:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        plans = data.get("data", [])

        for plan in plans:
            sort_date = plan["attributes"]["sort_date"]
            if not sort_date:
                continue

            plan_date = datetime.fromisoformat(
                sort_date.replace("Z", "+00:00")
            ).date().isoformat()

            # DEBUG line (optional but helpful)
            print("Checking plan:", plan_date, "-", plan["attributes"]["title"])

            if plan_date == target_date:
                print("\nSelected plan:", plan["attributes"]["title"], "-", plan["attributes"]["dates"])
                return plan["id"]

        # move to next page if it exists
        url = data.get("links", {}).get("next")
        params = None  # only needed on first request

    return None



def find_next_scheduled_plan(service_type_id):
    headers = auth_header()

    params = {"order": "sort_date"}
    resp = requests.get(
        f"{BASE_URL}/service_types/{service_type_id}/plans",
        headers=headers,
        params=params
    )
    resp.raise_for_status()

    today = datetime.now(timezone.utc).date()

    for plan in resp.json()["data"]:
        sort_date = plan["attributes"]["sort_date"]
        if not sort_date:
            continue

        plan_date = datetime.fromisoformat(sort_date.replace("Z", "+00:00")).date()
        if plan_date < today:
            continue

        plan_id = plan["id"]

        team_resp = requests.get(
            f"{BASE_URL}/service_types/{service_type_id}/plans/{plan_id}/team_members",
            headers=headers
        )
        team_resp.raise_for_status()

        for member in team_resp.json()["data"]:
            rel = member["relationships"].get("person")
            if rel and rel["data"]["id"] == PERSON_ID:
                print("Auto-selected scheduled plan:")
                print(" ", plan["attributes"]["title"], "-", plan["attributes"]["dates"])
                return plan_id

    return None

# ================= SONG FETCH =================

def fetch_plan_songs_with_meta(service_type_id, plan_id):
    headers = auth_header()

    resp = requests.get(
        f"{BASE_URL}/service_types/{service_type_id}/plans/{plan_id}/items",
        headers=headers,
        params={"include": "arrangement,key,song"}
    )
    resp.raise_for_status()

    payload = resp.json()
    included = {f'{i["type"]}:{i["id"]}': i for i in payload.get("included", [])}

    songs_meta = []

    for item in payload["data"]:
        if item["attributes"]["item_type"].lower() != "song":
            continue

        title = item["attributes"]["title"]
        bpm = meter = key_name = None

        arr_rel = item["relationships"].get("arrangement")
        if arr_rel and arr_rel["data"]:
            arr = included.get(f'arrangements:{arr_rel["data"]["id"]}')
            if arr:
                bpm = arr["attributes"].get("bpm")
                meter = arr["attributes"].get("meter")

        key_rel = item["relationships"].get("key")
        if key_rel and key_rel["data"]:
            key = included.get(f'keys:{key_rel["data"]["id"]}')
            if key:
                key_name = key["attributes"].get("name")

        songs_meta.append({
            "title": title,
            "bpm": bpm,
            "meter": meter,
            "key": key_name
        })

    return songs_meta

# ================= MIDI =================

def create_midi(songs_meta):
    midi = MIDIFile(1)
    time = 0

    midi.addTrackName(0, 0, "Celebration Service Setlist")
    midi.addTempo(0, 0, 120)

    print("\nSongs in this set:")

    for i, song in enumerate(songs_meta):
        midi.addProgramChange(0, MIDI_CHANNEL, time, i)
        print(f'{i+1}. {song["title"]} | BPM:{song["bpm"]} | TS:{song["meter"]} | Key:{song["key"]}')
        time += 1

    with open(MIDI_OUTPUT, "wb") as f:
        midi.writeFile(f)

    print("\nMIDI file created:", MIDI_OUTPUT)

# ================= MAIN =================

if __name__ == "__main__":
    print("\n--- Celebration Service → Walrus Clock Sync ---\n")

    svc_id = get_service_type_id()

    print("\nChoose mode:")
    print("1 - Next plan I am scheduled for")
    print("2 - Pick a specific Sunday date")

    choice = input("\nEnter 1 or 2: ").strip()

    plan_id = None

    if choice == "2":
        date_input = input("Enter Sunday date (YYYY-MM-DD): ").strip()
        plan_id = find_plan_by_date(svc_id, date_input)
        if not plan_id:
            print("No Celebration Service plan found for that date.")
            exit()
    else:
        plan_id = find_next_scheduled_plan(svc_id)
        if not plan_id:
            print("No upcoming Celebration Service plans found where you are scheduled.")
            exit()

    songs_meta = fetch_plan_songs_with_meta(svc_id, plan_id)

    if not songs_meta:
        print("No songs found in this plan.")
        exit()

    create_midi(songs_meta)