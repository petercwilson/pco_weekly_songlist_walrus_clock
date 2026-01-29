import base64
import requests
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta, SU
from midiutil import MIDIFile

# ========== CONFIGURATION ==========

# Personal Access Token (Base64)
PC_APP_ID     = "ef6859b2d409c09b0de1df2788d4551ff10d01ae348e079b207cb58fc96ae984"
PC_SECRET     = "pco_pat_c99952c219805b5ec88f2c72564e39931a310fcf7620f7f302015b05f35ea77ed2910211"
BASE_URL = "https://api.planningcenteronline.com/services/v2"
PERSON_ID = "AC63069036#"

MIDI_OUTPUT = "weekly_setlist_with_meta.mid"
MIDI_CHANNEL = 0

def auth_header():
    token = f"{PC_APP_ID}:{PC_SECRET}"
    token_b64 = base64.b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {token_b64}"}

def next_sunday(date):
    return date + relativedelta(weekday=SU(+1))

# ===== FETCH PLAN & METADATA =====

def fetch_plan_songs_with_meta():
    today = datetime.now(timezone.utc).date()
    sunday = next_sunday(today).strftime("%Y-%m-%d")

    headers = auth_header()

    # fetch service types
    svc_resp = requests.get(f"{BASE_URL}/service_types", headers=headers)
    svc_resp.raise_for_status()
    svc_types = svc_resp.json()["data"]
    if not svc_types:
        return []

# ===== ID FOR CELEBRATION SERVICE =====
    svc_id = "257965"   

# ===== RETRIEVE SERVICE TYPES ===== 
    # print("\nAvailable Service Types:")
    # for svc in svc_types:  
    #    print(f'ID: {svc["id"]} | Name: {svc["attributes"]["name"]}')

    print("\nAvailable Plans:")
    for p in plans:
        print(f'ID: {p["id"]} | Date: {p["attributes"]["dates"]} | Title: {p["attributes"]["title"]}')


    # fetch plans for upcoming Sunday
    params = {"filter[date]": sunday}
    plans_resp = requests.get(
        f"{BASE_URL}/service_types/{svc_id}/plans",
        headers=headers,
        params=params,
    )
    plans_resp.raise_for_status()
    plans = plans_resp.json()["data"]
    if not plans:
        return []

    plan_id = plans[0]["id"]

    # fetch items and include song/arrangement/key relationships
    items_resp = requests.get(
        f"{BASE_URL}/service_types/{svc_id}/plans/{plan_id}/items",
        headers=headers,
        params={"include": "arrangement,key,song"},
    )
    items_resp.raise_for_status()
    data = items_resp.json()

    # map included resources by type/id
    included = {f'{item["type"]}:{item["id"]}': item for item in data.get("included", [])}

    songs_meta = []
    for item in data["data"]:
        if item["attributes"]["item_type"].lower() == "song":
            title = item["attributes"]["title"]

            # get arrangement and key
            arr_rel = item["relationships"].get("arrangement")
            key_rel = item["relationships"].get("key")

            bpm = meter = key_name = None

            if arr_rel and arr_rel["data"]:
                arr = included.get(f'arrangements:{arr_rel["data"]["id"]}')
                if arr:
                    bpm = arr["attributes"].get("bpm")
                    meter = arr["attributes"].get("meter")

            if key_rel and key_rel["data"]:
                key = included.get(f'keys:{key_rel["data"]["id"]}')
                if key:
                    key_name = key["attributes"].get("name")

            songs_meta.append({
                "title": title,
                "bpm": bpm,
                "meter": meter,
                "key": key_name,
            })

    return songs_meta

def create_midi(songs_meta):
    midi = MIDIFile(1)
    track, time = 0, 0
    midi.addTrackName(track, time, "Service Setlist")
    midi.addTempo(track, time, 120)

    for i, song in enumerate(songs_meta):
        midi.addProgramChange(track, MIDI_CHANNEL, time, i)
        meta_info = f"{song['title']} | BPM: {song['bpm']} | TS: {song['meter']} | Key: {song['key']}"
        print(meta_info)
        time += 1

    with open(MIDI_OUTPUT, "wb") as f:
        midi.writeFile(f)
    print("MIDI generated:", MIDI_OUTPUT)

if __name__ == "__main__":
    songs_meta = fetch_plan_songs_with_meta()
    if songs_meta:
        create_midi(songs_meta)
    else:
        print("No songs found for upcoming Sunday.")