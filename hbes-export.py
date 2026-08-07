import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from jinja2 import Template
from markdown import markdown

if os.getenv("API_TOKEN") is None:
    from dotenv import load_dotenv

    # Load variables from the .env file into the system environment
    load_dotenv()
API_TOKEN = os.environ.get("API_TOKEN")
EVENT_ID = os.environ.get("EVENT_ID")


def fail(message):
    raise SystemExit(message)


def validate_runtime_inputs():
    if not API_TOKEN or API_TOKEN.strip() in {"", "YOUR_INDICO_API_TOKEN"}:
        fail(
            "API_TOKEN is missing or still set to a placeholder. Set a real Indico API token and re-run."
        )

    if not EVENT_ID or EVENT_ID.strip() in {"", "YOUR_EVENT_ID"}:
        fail(
            "EVENT_ID is missing or still set to a placeholder. Set a real event ID and re-run."
        )

    if not EVENT_ID.strip().isdigit():
        fail("EVENT_ID must be numeric (example: 12345).")


def clean_text(text):
    clean = re.sub(r"<[^>]+>", " ", text)  # Strip HTML tags
    return " ".join(clean.lower().split())  # Normalize whitespace & lowercase


def dict2datetime(d, new_tz=None):
    # 1. Combine date and time strings into an ISO format (YYYY-MM-DDTHH:MM:SS)
    iso_string = f"{d['date']}T{d['time']}"
    native_dt = datetime.fromisoformat(iso_string)
    if not new_tz:
        return native_dt
    source_tz = ZoneInfo(d["tz"])
    original_dt = native_dt.replace(tzinfo=source_tz)
    target_tz = ZoneInfo(new_tz)
    return original_dt.astimezone(target_tz)


def startDatekey(item):
    return dict2datetime(item["startDate"])


# Optional parameters (e.g., to include daily occurrences or details)
# These are for the events endpoint (not timetable)
event_params = {
    "occ": "yes",  # Includes daily event times
    "detail": "sessions",
}


def get_response(endpoint, params):
    server_url = "https://indico.global"
    # Complete URL
    url = f"{server_url}{endpoint}"

    # Set up the standard Authorization header
    headers = {"Authorization": f"Bearer {API_TOKEN}", "Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, params=params)

        # Check if the request was successful
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch API response. Status code: {response.status_code}")
            print(f"Request URL: {response.url}")
            print(f"Response body: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")


# Define the specific event ID to fetch
validate_runtime_inputs()

endpoint_events = f"/export/event/{EVENT_ID}.json"
events = get_response(endpoint_events, {})

if not events or "results" not in events or len(events["results"]) == 0:
    fail(
        "Could not load event metadata from Indico. Check API_TOKEN and EVENT_ID, then try again."
    )

conference = events["results"][0]
tz = conference["timezone"]
conference_title = conference["title"]
conference_year = dict2datetime(conference["startDate"]).year

endpoint_timetable = f"/export/timetable/{EVENT_ID}.json"
timetable0 = get_response(endpoint_timetable, {})
if (
    not timetable0
    or "results" not in timetable0
    or EVENT_ID not in timetable0["results"]
):
    fail(
        "Could not load timetable data from Indico. Check permissions and event visibility."
    )
timetable = timetable0["results"][EVENT_ID]

author_keys = ["firstName", "familyName", "affiliation", "person_id", "email"]
authors = {}

# Create presentations list


def format_authors_and_affiliations(presenters, authors):
    authors = presenters + authors
    affiliation_map = {}  # Tracks { "University Name": 1 }
    affiliations_ordered = []

    # 1. Map unique affiliations to sequential numbers
    for author in authors:
        aff = author["affiliation"]
        if aff not in affiliation_map:
            affiliation_map[aff] = len(affiliation_map) + 1
            affiliations_ordered.append(aff)

    # 2. Build the author list with superscripts
    author_entries = []
    for author in authors:
        full_name = f"{author['firstName']} {author['familyName']}"

        # Indico apparently only allows one affiliation per author?
        # Get indices for this author's affiliations
        # indices = [
        #     str(affiliation_map[aff]) for aff in author.get("affiliations", [])
        # ]

        # if indices:
        #     sup_indices = ",".join(indices)
        #     author_entries.append(f"{full_name}<sup>{sup_indices}</sup>")
        # else:
        #     author_entries.append(full_name)
        index = str(affiliation_map[author["affiliation"]])
        if index:
            author_entries.append(f"{full_name}<sup>{index}</sup>")
        else:
            author_entries.append(full_name)

    authors_html = ", ".join(author_entries)

    # 3. Build the numbered affiliations list
    aff_items = "".join(f"  <li>{aff}</li>\n" for aff in affiliations_ordered)
    affiliations_html = f'<ol class="affiliations">\n{aff_items}</ol>'

    # Combined HTML fragment
    return f"""<div class="authors-block">
  <p class="authors">{authors_html}</p>
{affiliations_html}
</div>"""


def format_abstract(title, presenters, authors, description):
    authors_affiliations = format_authors_and_affiliations(presenters, authors)
    abstract = markdown(description)
    return f"""<p class = \"title\"><strong>{title}</strong></p>
    {authors_affiliations}
    <div class = \"abstract\" style = \"margin-top: 10px;\">
    {abstract}
    </div>
    """


def sub_dict(d, keys):
    return {k: d.get(k, "") for k in keys}


def add_day_time(item):
    item["startdatetime"] = dict2datetime(item["startDate"], new_tz=tz)
    item["start_time"] = item["startdatetime"].strftime("%I:%M %p")
    item["morning_afternoon"] = (
        "Morning" if item["startdatetime"].hour < 12 else "Afternoon"
    )
    item["day"] = item["startdatetime"].strftime("%a")
    item["location"] = item.pop("room")  # Rename to match template
    return item


def contribution_add(contribution, session_id=""):
    contribution["session_id"] = session_id
    contribution = add_day_time(contribution)
    contribution["talks"] = []  # Fake
    if len(contribution["presenters"]) > 0:
        contribution["email"] = contribution["presenters"][0].get("email", "")
    else:
        contribution["email"] = ""  # Assume one presenter
    contribution["abstract"] = format_abstract(
        contribution["title"],
        contribution["presenters"],
        contribution["authors"],
        contribution["description"],
    )
    contribution["presenters"] = [
        sub_dict(author, author_keys) for author in contribution["presenters"]
    ]
    contribution["authors"] = [
        sub_dict(author, author_keys) for author in contribution["authors"]
    ]
    for author in contribution["presenters"] + contribution["authors"]:
        if "person_id" not in author or author["person_id"] == "":
            author["person_id"] = re.sub(
                r"[^a-zA-Z]", "", author["firstName"] + author["familyName"]
            )
        if author["person_id"] not in authors:
            authors[author["person_id"]] = author
            authors[author["person_id"]]["presentations"] = [contribution["id"]]
        else:
            authors[author["person_id"]]["presentations"].append(contribution["id"])
    return contribution


def session_add(session):
    session = add_day_time(session)
    session["talks"] = []
    for key in session["entries"]:
        contribution = session["entries"][key]
        contribution = contribution_add(contribution, session_id=session["id"])
        session["talks"].append(contribution)
    # if len(session["talks"]) > 0:
    #     session["item_type"] = "session"
    # else:
    #     session["item_type"] = "other"
    return session


sessions = {
    "Sun": {"Morning": [], "Afternoon": []},
    "Mon": {"Morning": [], "Afternoon": []},
    "Tue": {"Morning": [], "Afternoon": []},
    "Wed": {"Morning": [], "Afternoon": []},
    "Thu": {"Morning": [], "Afternoon": []},
    "Fri": {"Morning": [], "Afternoon": []},
    "Sat": {"Morning": [], "Afternoon": []},
}

for day in timetable:
    for item_key in timetable[day]:
        item = timetable[day][item_key]
        if item == {}:
            continue
        if item["entryType"] == "Session":
            item = session_add(item)
        elif item["entryType"] == "Contribution":
            item = contribution_add(item)
        elif item["entryType"] == "Break":
            item = add_day_time(item)
        sessions[item["day"]][item["morning_afternoon"]].append(item)

# Remove empty days
sessions = {
    key: sessions[key]
    for key in sessions
    if len(sessions[key]["Morning"]) > 0 or len(sessions[key]["Afternoon"]) > 0
}

# Ensure that sessions & talks are sorted by datetime
for day in sessions:
    for morning_afternoon in sessions[day]:
        sessions[day][morning_afternoon].sort(key=startDatekey)
        for session in sessions[day][morning_afternoon]:
            if session["entryType"] != "Session":
                continue
            session["talks"].sort(key=startDatekey)

authors = dict(
    sorted(
        authors.items(), key=lambda item: (item[1]["familyName"], item[1]["firstName"])
    )
)

talks = {
    talk["id"]: talk
    for day in sessions
    for morning_afternoon in sessions[day]
    for session in sessions[day][morning_afternoon]
    for talk in session.get("talks", "")
    if session["entryType"] == "Session"
}

talks = dict(sorted(talks.items()))

talk_keys = [
    "id",
    "session_id",
    "title",
    "presenters",
    "authors",
    "abstract",
    "location",
    "type",
    "startdatetime",
    "start_time",
    "day",
    "email",
]
talks = {k: sub_dict(talks[k], talk_keys) for k in talks.keys()}


with open("index.template", "r", encoding="utf-8") as file:
    template = Template(file.read())
with open("docs/index.html", "w", encoding="utf-8") as file:
    file.write(
        template.render(
            conference_title=conference_title,
            sessions=sessions,
            talks=json.dumps(talks, default=str),
            authors=json.dumps(authors, default=str),
        )
    )

with open("manifest.template", "r", encoding="utf-8") as file:
    template = Template(file.read())
with open("docs/manifest.json", "w", encoding="utf-8") as file:
    file.write(template.render(conference_year=conference_year))
