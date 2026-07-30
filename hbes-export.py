import os
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from markdown import markdown
from jinja2 import Template

if os.getenv("API_TOKEN") is None:
    from dotenv import load_dotenv

    # Load variables from the .env file into the system environment
    load_dotenv()
API_TOKEN = os.environ.get("API_TOKEN")
EVENT_ID = os.environ.get("EVENT_ID")


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


# Define the Indico server and the specific event ID you want to fetch
server_url = "https://indico.global"
endpoint = f"/export/event/{EVENT_ID}.json"

# Complete URL
url = f"{server_url}{endpoint}"

# Set up the standard Authorization header
headers = {"Authorization": f"Bearer {API_TOKEN}", "Accept": "application/json"}

# Optional parameters (e.g., to include daily occurrences or details)
params = {
    "occ": "yes",  # Includes daily event times
    "detail": "sessions",
}

try:
    response = requests.get(url, headers=headers, params=params)

    # Check if the request was successful
    if response.status_code == 200:
        data = response.json()
    else:
        print(f"Failed to fetch event. Status code: {response.status_code}")
        print(response.text)

except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")

conference = data["results"][0]
tz = conference["timezone"]
conference_title = conference["title"]

# Ensure that sessions & talks are sorted by datetime
conference["sessions"].sort(key=startDatekey)

for session in conference["sessions"]:
    session["contributions"].sort(key=startDatekey)


# Create presentations list
def format_authors_and_affiliations(primaryauthors, coauthors):
    authors = primaryauthors + coauthors
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
        full_name = f"{author['first_name']} {author['last_name']}"

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


def format_abstract(title, primaryauthors, coauthors, description):
    authors_affiliations = format_authors_and_affiliations(primaryauthors, coauthors)
    abstract = markdown(description)
    return f"""<p class = \"title\"><strong>{title}</strong></p>
    {authors_affiliations}
    <div class = \"abstract\" style = \"margin-top: 10px;\">
    {abstract}
    </div>
    """


def sub_dict(d, keys):
    return {k: d[k] for k in keys}


sessions = {
    "Wed": {"Morning": [], "Afternoon": []},
    "Thu": {"Morning": [], "Afternoon": []},
    "Fri": {"Morning": [], "Afternoon": []},
    "Sat": {"Morning": [], "Afternoon": []},
}

author_keys = ["first_name", "last_name", "affiliation", "person_id", "email"]
authors = {}

for session in conference["sessions"]:
    session["startdatetime"] = dict2datetime(session["startDate"], new_tz=tz)
    session["enddatetime"] = dict2datetime(session["endDate"], new_tz=tz)
    session["start_time"] = session["startdatetime"].strftime("%I:%M %p")
    session["end_time"] = session["enddatetime"].strftime("%I:%M %p")
    session["day"] = session["startdatetime"].strftime("%a")
    session["morning_afternoon"] = (
        "Morning" if session["startdatetime"].hour < 12 else "Afternoon"
    )
    session["location"] = session.pop("room")
    for contribution in session["contributions"]:
        contribution["session_id"] = session["id"]
        contribution["startdatetime"] = dict2datetime(
            contribution["startDate"], new_tz=tz
        )
        contribution["start_time"] = contribution["startdatetime"].strftime("%I:%M %p")
        contribution["day"] = contribution["startdatetime"].strftime("%a")
        contribution["location"] = contribution.pop("room")  # Rename to match template
        contribution["email"] = contribution["primaryauthors"][0][
            "email"
        ]  # Assume one primary author
        contribution["abstract"] = format_abstract(
            contribution["title"],
            contribution["primaryauthors"],
            contribution["coauthors"],
            contribution["description"],
        )
        contribution["primaryauthors"] = [
            sub_dict(author, author_keys) for author in contribution["primaryauthors"]
        ]
        contribution["coauthors"] = [
            sub_dict(author, author_keys) for author in contribution["coauthors"]
        ]
        for author in contribution["primaryauthors"] + contribution["coauthors"]:
            if author["person_id"] not in authors:
                authors[author["person_id"]] = author
                authors[author["person_id"]]["presentations"] = [contribution["id"]]
            else:
                authors[author["person_id"]]["presentations"].append(contribution["id"])
    session["talks"] = session.pop("contributions")
    sessions[session["day"]][session["morning_afternoon"]].append(session)

authors = dict(
    sorted(
        authors.items(), key=lambda item: (item[1]["last_name"], item[1]["first_name"])
    )
)

talks = {
    int(talk["id"]): talk
    for session in conference["sessions"]
    for talk in session["talks"]
}

talks = dict(sorted(talks.items()))

talk_keys = [
    "id",
    "session_id",
    "title",
    "primaryauthors",
    "coauthors",
    "abstract",
    "location",
    "type",
    "startdatetime",
    "start_time",
    "day",
    "email",
]
talks = {k: sub_dict(talks[k], talk_keys) for k in talks.keys()}


with open("index.indico.template", "r", encoding="utf-8") as file:
    template = Template(file.read())
with open("docs/index.indico.html", "w", encoding="utf-8") as file:
    file.write(
        template.render(
            conference_title=conference_title,
            sessions=sessions,
            talks=json.dumps(talks, default=str),
            authors=json.dumps(authors, default=str),
        )
    )
