require 'base64'
require 'rest-client'
require 'json'
require 'date'
require 'midi-file'

# ================= CONFIG =================

PC_APP_ID = "YOUR_APP_ID"
PC_SECRET = "YOUR_SECRET"

PERSON_ID = "YOUR_PERSON_ID"
TARGET_SERVICE_TYPE_NAME = "Celebration Service"

BASE_URL = "https://api.planningcenteronline.com/services/v2"
MIDI_OUTPUT = "weekly_setlist_with_meta.mid"
MIDI_CHANNEL = 0

# ================= HELPERS =================

def auth_header
  token = Base64.strict_encode64("#{PC_APP_ID}:#{PC_SECRET}")
  { Authorization: "Basic #{token}" }
end

def get_json(url, params = {})
  response = RestClient.get(url, { params: params }.merge(auth_header))
  JSON.parse(response.body)
end

# ================= SERVICE TYPE =================

def get_service_type_id
  data = get_json("#{BASE_URL}/service_types")

  svc = data["data"].find do |s|
    s["attributes"]["name"].downcase == TARGET_SERVICE_TYPE_NAME.downcase
  end

  raise "Celebration Service not found." unless svc

  puts "Using service type: #{svc["attributes"]["name"]}"
  svc["id"]
end

# ================= PLAN FINDERS =================

def find_plan_by_date(service_type_id, target_date)
  url = "#{BASE_URL}/service_types/#{service_type_id}/plans"
  params = { order: "sort_date" }

  while url
    data = get_json(url, params)
    params = nil

    data["data"].each do |plan|
      sort_date = plan.dig("attributes", "sort_date")
      next unless sort_date

      plan_date = Date.parse(sort_date)

      puts "Checking plan: #{plan_date} - #{plan["attributes"]["title"]}"

      if plan_date.to_s == target_date
        puts "\nSelected plan: #{plan["attributes"]["title"]} - #{plan["attributes"]["dates"]}"
        return plan["id"]
      end
    end

    url = data.dig("links", "next")
  end

  nil
end

def find_next_scheduled_plan(service_type_id)
  today = Date.today
  data = get_json("#{BASE_URL}/service_types/#{service_type_id}/plans", { order: "sort_date" })

  data["data"].each do |plan|
    sort_date = plan.dig("attributes", "sort_date")
    next unless sort_date

    plan_date = Date.parse(sort_date)
    next if plan_date < today

    plan_id = plan["id"]

    team = get_json("#{BASE_URL}/service_types/#{service_type_id}/plans/#{plan_id}/team_members")

    team["data"].each do |member|
      person = member.dig("relationships", "person", "data", "id")
      if person == PERSON_ID
        puts "\nAuto-selected scheduled plan:"
        puts " #{plan["attributes"]["title"]} - #{plan["attributes"]["dates"]}"
        return plan_id
      end
    end
  end

  nil
end

# ================= SONG FETCH =================

def fetch_plan_songs_with_meta(service_type_id, plan_id)
  data = get_json(
    "#{BASE_URL}/service_types/#{service_type_id}/plans/#{plan_id}/items",
    { include: "arrangement,key,song" }
  )

  included = {}
  (data["included"] || []).each do |i|
    included["#{i["type"]}:#{i["id"]}"] = i
  end

  songs = []

  data["data"].each do |item|
    next unless item["attributes"]["item_type"].downcase == "song"

    title = item["attributes"]["title"]

    bpm = meter = key_name = nil

    arr_id = item.dig("relationships", "arrangement", "data", "id")
    if arr_id
      arr = included["arrangements:#{arr_id}"]
      bpm = arr.dig("attributes", "bpm")
      meter = arr.dig("attributes", "meter")
    end

    key_id = item.dig("relationships", "key", "data", "id")
    if key_id
      key = included["keys:#{key_id}"]
      key_name = key.dig("attributes", "name")
    end

    songs << { title: title, bpm: bpm, meter: meter, key: key_name }
  end

  songs
end

# ================= MIDI =================

def create_midi(songs)
  seq = MIDI::Sequence.new
  track = MIDI::Track.new(seq)
  seq.tracks << track

  track.events << MIDI::MetaEvent.new(MIDI::META_SEQ_NAME, "Celebration Service Setlist")
  track.events << MIDI::Tempo.new(MIDI::Tempo.bpm_to_mpq(120))

  puts "\nSongs in this set:\n"

  time = 0

  songs.each_with_index do |song, i|
    track.events << MIDI::ProgramChange.new(MIDI_CHANNEL, i, time)
    puts "#{i + 1}. #{song[:title]} | BPM:#{song[:bpm]} | TS:#{song[:meter]} | Key:#{song[:key]}"
    time += 480
  end

  File.open(MIDI_OUTPUT, 'wb') { |f| seq.write(f) }

  puts "\nMIDI file created: #{MIDI_OUTPUT}"
end

# ================= MAIN =================

puts "\n--- Celebration Service → Walrus Clock Sync (Ruby) ---\n"

svc_id = get_service_type_id

puts "\nChoose mode:"
puts "1 - Next plan I am scheduled for"
puts "2 - Pick a specific Sunday date"

print "\nEnter 1 or 2: "
choice = gets.strip

plan_id =
  if choice == "2"
    print "Enter Sunday date (YYYY-MM-DD): "
    date_input = gets.strip
    find_plan_by_date(svc_id, date_input)
  else
    find_next_scheduled_plan(svc_id)
  end

if plan_id.nil?
  puts "\nNo Celebration Service plan found."
  exit
end

songs = fetch_plan_songs_with_meta(svc_id, plan_id)

if songs.empty?
  puts "\nNo songs found in this plan."
  exit
end

create_midi(songs)
