import os
import sys
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup
import re
import warnings
import threading
import atexit

from lcddriver import lcd

DEBUG = False

if not DEBUG:
    warnings.simplefilter(action='ignore', category=FutureWarning) # silence unavoidable pandas warning

# set bounding cube below
COORDS = {
    'LAT': {
        'MIN': 0,
        'MAX': 0
    },
    'LON': {
        'MIN': 0,
        'MAX': -0
    },
    'ALT': {
        'MIN': 0,
        'MAX': 10000
    }
}


def track(dump_file, coords=COORDS):
    global exit_signal  # Declare global variable
    while not exit_signal:
        if os.path.exists(dump_file):
            df = pd.read_json(dump_file)

            aircraft = df.aircraft
            aircraft = pd.DataFrame(aircraft.tolist())

            if 'lat' in aircraft:
                aircraft = aircraft[aircraft['lat'] != '']
                aircraft = aircraft[(aircraft['lat'] > coords['LAT']['MIN']) & (aircraft['lat'] < coords['LAT']['MAX']) & (aircraft['lon'] > coords['LON']['MIN']) & (aircraft['lon'] < coords['LON']['MAX']) & (aircraft['alt_baro'] < coords['ALT']['MAX'])]

                if len(aircraft) > 0:
                    flight_number = aircraft['flight'].iloc[0]

                    if flight_number != display.flight_no:
                        try:
                            flight_data = get_flight_aware_details(flight_number)
                            display.set_details(flight_number, flight_data)
                        except Exception as e:
                            print(e)
                            display.clear_details()
                else:
                    if DEBUG:
                        print("No aircraft in range")
                    display.clear_details()
            else:
                if DEBUG:
                    print("No coords in dump - likely nothing logged yet")
                display.clear_details()

        time.sleep(2)

def get_flight_aware_details(flight_number):
    flightaware_url = f"https://www.flightaware.com/live/flight/{flight_number}"

    try:
        page = requests.get(flightaware_url)
        soup = BeautifulSoup(page.content, 'html.parser')

        script_tags = soup.find_all('script')

        for tag in script_tags:
            if "trackpollGlobals" in tag.text:
                match = re.search('"TOKEN":"(.*?)"', tag.text)
                token = match.group(1)
                api_url = f"https://flightaware.com/ajax/trackpoll.rvt?token={token}&locale=en_US&summary=1"

                page = requests.get(api_url)
                data = page.json()

                flight_details = data.get("flights", {})

                for flight_key, flight_info in flight_details.items():
                    flight = flight_info["activityLog"]["flights"][0]
                    origin_airport = flight["origin"]["friendlyName"]
                    country_of_origin = flight["origin"]["friendlyLocation"]
                    aircraft_type = flight["aircraftTypeFriendly"]
                    airline_name = flight_info['airline']['fullName']

                    data = {
                        "origin_airport": origin_airport,
                        "country_of_origin": country_of_origin,
                        "airline_name": airline_name,
                        "aircraft_type": aircraft_type
                    }

                    return data

    except Exception as e:
        if DEBUG:
            print(f"Error getting FlightAware details: {e}")

    return None


class Display:
    def __init__(self):
        self.LCD = lcd()
        self.flight_no = None
        self.details = None
        self.show_top("Hello, sky!")

    def __del__(self):
        self.show_top("Goodbye, sky!")
        self.show_bottom("Exit at " + time.strftime("%H:%M:%S"))

    def tidy_details(self, details):
        if len(details["airline_name"]) > 16:
            details["airline_name"] = details["airline_name"].replace("Airways", "A.")
            details["airline_name"] = details["airline_name"].replace("Airlines", "A.")

        if details["aircraft_type"] is None:
            details["aircraft_type"] = "?"
        if len(details["aircraft_type"]) > 16:
            if "777" in details["aircraft_type"]:
                details["aircraft_type"] = "Boeing 777"
            elif "A320" in details["aircraft_type"]:
                details["aircraft_type"] = "Airbus A320"
            elif "737 MAX" in details["aircraft_type"]:
                details["aircraft_type"] = "Boeing 737 MAX"
            elif "737" in details["aircraft_type"]:
                details["aircraft_type"] = "Boeing 737"
            elif "A380" in details["aircraft_type"]:
                details["aircraft_type"] = "Airbus A380"
            elif "787" in details["aircraft_type"]:
                details["aircraft_type"] = "Boeing 787"
            elif "A319" in details["aircraft_type"]:
                details["aircraft_type"] = "Airbus A319"
            elif "A350" in details["aircraft_type"]:
                details["aircraft_type"] = "Airbus A350"
        if len(details["origin_airport"]) > 16:
            details["origin_airport"] = details["origin_airport"].replace("International", "Int'l")
            if len(details["origin_airport"]) > 16:
                details["origin_airport"] = details["origin_airport"].replace("Int'l", "Int")
                details["origin_airport"] = details["origin_airport"].replace("Airport", "Apt.")
        return details

    def set_details(self, flight, details):
        if DEBUG:
            print("Setting details")
        self.flight_no = flight
        self.details = self.tidy_details(details)

    def clear_details(self):
        if DEBUG:
            print("Clearing details")
        self.flight_no = None
        self.details = None
        self.splash()

    def splash(self):
        if DEBUG:
            print("Splash")
        self.show_top("AERO")
        self.show_bottom("   PI")

    def show(self, text, line=1):
        if DEBUG:
            print(f"Showing {text} on line {line}")
        if text is None:
            text = "?"
        self.LCD.lcd_display_string((text + " " * (16 - len(text)))[:16], line)

    def show_top(self, text):
        self.show(text, 1)

    def show_bottom(self, text):
        self.show(text, 2)

    def show_page_1(self):
        # show airline on line 1, aircraft type on line 2
        self.show_top(self.details["airline_name"])
        self.show_bottom(self.details["aircraft_type"])

    def show_page_2(self):
        # show origin airport on line 1, country of origin on line 2
        self.show_top(self.details["origin_airport"])
        self.show_bottom(self.details["country_of_origin"])

    def main_loop(self):
        global exit_signal  # Declare global variable
        i = 0
        while not exit_signal:
            if self.details is not None:
                if i < 5:
                    self.show_page_1()
                else:
                    self.show_page_2()
                time.sleep(1)
                i += 1
                if i == 10:
                    i = 0

def graceful_exit():
    global exit_signal  # Declare global variable
    exit_signal = True  # Set the exit signal to True to signal threads to exit
    # Wait for threads to finish
    t1.join()
    t2.join()
    # destroy display class
    display.__del__()
    os.system("pkill -f dump1090")
    print("Goodbye!")

if __name__ == "__main__":
    global exit_signal  # Declare global variable
    exit_signal = False  # Set the exit signal to True to signal threads to exit
    print("Starting up...")
    os.system("rm -rf data")
    os.system("mkdir data")
    os.system("./dump1090/dump1090 --net --quiet --write-json data &")
    display = Display()

    t1 = threading.Thread(target=display.main_loop)
    t2 = threading.Thread(target=track, args=("data/aircraft.json",))
    t1.start()
    t2.start()

    atexit.register(graceful_exit)

    # t1.join()
    # t2.join()

