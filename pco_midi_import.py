import base64
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta, SU
from midiutil import MIDIFile

# ========== CONFIGURATION ==========

# Personal Access Token (Base64)
PC_APP_ID     = "ef6859b2d409c09b0de1df2788d4551ff10d01ae348e079b207cb58fc96ae984"
PC_SECRET     = "pco_pat_c99952c219805b5ec88f2c72564e39931a310fcf7620f7f302015b05f35ea77ed2910211"
PLANNING_HOST = "https://api.planningcenteronline.com/services/v2"

MIDI_OUTPUT   = "weekly_setlist.mid"
MIDI_CHANNEL  = 0   # Most devices use channel 0 or 1
PROGRAM_START = 0   # Program Change starting index

# ========== HELPERS ==========

def auth_header(app_id, secret):
    token = f"{app_id}:{secret}"
    token_b64 = base64.b64encode(token.encode()).decode()
    return {"Authorization": f"Basic {token_b64}"}

def next_sunday(date):
    """Return the next upcoming Sunday from a given date."""
    return date + relativedelta(weekday=SU(+1))

# ========== 1. FETCH NEXT SUNDAY PLAN ==========

def fetch_next_sunday_plan():
    # 1. Find the upcoming Sunday date in YYYY-MM-DD
    today   = datetime.utcnow().date()
    sunday  = next_sunday(today)
    date_str = sunday.strftime("%Y-%m-%d")

    # 2. Get all service types
    headers = auth_header(PC_APP_ID, PC_SECRET)
    r = requests.get(f"{PLANNING_HOST}/service_types", headers=headers)
    r.raise_for_status()
    service_types = r.json()["data"]

    # 3. Pick one service type (customize logic if you have many)
    svc_type_id = service_types[0]["id"]

    # 4. Get plans for the Sunday date
    params = {"filter[date]": date_str}
    r = requests.get(
        f"{PLANNING_HOST}/service_types/{svc_type_id}/plans",
        headers=headers,
        params=params
    )
    r.raise_for_status()
    plans = r.json()["data"]
    if not plans:
        print("No service plan found for", date_str)
        return []

    plan_id = plans[0]["id"]

    # 5. Fetch items for that plan
    r = requests.get(
        f"{PLANNING_HOST}/service_types/{svc_type_id}/plans/{plan_id}/items",
        headers=headers
    )
    r.raise_for_status()
    items = r.json()["data"]

    # 6. Grab songs in order
    songs = []
    for item in items:
        item_type = item["attributes"]["item_type"]
        if item_type.lower() == "song":
            title = item["attributes"]["title"]
            songs.append(title)

    return songs

# ========== 2. GENERATE MIDI FILE ==========

def create_midi_for_songs(songs):
    midi = MIDIFile(1)            # One track
    track = 0
    time  = 0
    midi.addTrackName(track, time, "Service Setlist")
    midi.addTempo(track, time, 120)  # Default; optional

    for i, song in enumerate(songs):
        # Send a Program Change event
        program_number = PROGRAM_START + i
        midi.addProgramChange(track, MIDI_CHANNEL, time, program_number)
        time += 1  # Advance to next tick

        print(f"MIDI PC {program_number} -> {song}")

    # Write the file
    with open(MIDI_OUTPUT, "wb") as out:
        midi.writeFile(out)
    print(f"Saved MIDI file: {MIDI_OUTPUT}")

# ========== MAIN ==========

if __name__ == "__main__":
    print("Fetching next Sunday’s service plan…")
    songs = fetch_next_sunday_plan()
    if not songs:
        print("No songs found — aborting MIDI file creation.")
    else:
        print("Songs:", songs)
        print("Creating MIDI...")
        create_midi_for_songs(songs)
