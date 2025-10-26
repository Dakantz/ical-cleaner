from os import getenv
from flask import Flask, request, make_response
import requests
import pymongo
from bson import ObjectId
from icalendar import Calendar, Event

# Replace the uri string with your MongoDB deployment's connection string.
conn_str = getenv("MONGODB_CONN", "mongodb://root:devpassword@localhost:27017/")

# set a 5-second connection timeout
client = pymongo.MongoClient(conn_str, serverSelectionTimeoutMS=5000)
try:
    print(client.server_info())
except Exception:
    print("Unable to connect to the server.", conn_str)
    exit(-1)

mdb = client.get_database("ical-wrapper")
calendars = mdb.get_collection("calendars")
app = Flask(__name__)
print("Should be up and running...")


@app.route("/calendar/<id>")
def calendar(id):
    print("Loading calendar for", id)
    calendar_options = calendars.find_one(ObjectId(id))
    if calendar_options:
        cal = Calendar()
        transformed_ical = Calendar()
        print("found options...")
        block_words = calendar_options["blocked_words"]
        urls_to_combine: dict[str, str] = calendar_options.get("urls_combine", {})
        for prefix, url in urls_to_combine.items():
            print("combining from", url)
            web_ical_data = requests.get(url)
            cal = Calendar()
            web_ical: Calendar = cal.from_ical(web_ical_data.text)
            for evt in web_ical.subcomponents:
                if evt.name != "VEVENT":
                    continue
                evt_prefix = prefix + " " if prefix else ""
                
                evt["SUMMARY"] = f"{evt_prefix} {evt['SUMMARY'] if 'SUMMARY' in evt else ''}".strip()
                transformed_ical.add_component(evt)

        web_ical_data = requests.get(calendar_options["url"])
        web_ical: Calendar = cal.from_ical(web_ical_data.text)

        for evt in web_ical.subcomponents:
            is_good = True
            for word in block_words:
                if word in str(evt["SUMMARY"]):
                    is_good = False
                    break
            if is_good:
                transformed_ical.add_component(evt)
        resp = make_response(transformed_ical.to_ical(), 200)
        resp.headers["content-type"] = "text/calendar;charset=UTF-8"
        resp.headers["content-disposition"] = "attachment; filename=calendar.ics"
        return resp
    else:
        return make_response("nope", 404)


@app.route("/calendar-options", methods=["GET", "POST"])
def calendar_options():
    print("got new cal req")
    id = None
    if "id" in request.args:
        id = request.args["id"]
    data = None
    if request.method == "POST" and request.is_json:
        if id:
            data = calendars.find_one_and_replace({"_id": ObjectId(id)}, request.json)
        else:
            inserted = calendars.insert_one(request.json)
            request.json["id"] = str(inserted.inserted_id)
            data = request.json
            del data["_id"]
            return data
    else:
        data = calendars.find_one({"_id": ObjectId(id)})
    
    del data["_id"]
    return data
