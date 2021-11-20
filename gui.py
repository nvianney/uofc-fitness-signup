import signup
import PySimpleGUI as sg
from threading import Thread
import webbrowser

from cryptography.fernet import Fernet
import pickle

import requests

import logging

from datetime import datetime, timedelta

VERSION = signup.VERSION

slots = list(map(lambda x : "%02d:00" % x, range(5, 21+1)))
refresh_rates = list(range(5, 120+1, 5))
day_of_weeks = ["Today"]

date = datetime.today() + timedelta(days=1)
for i in range(0, 7):
    day_of_weeks.append(date.strftime("%A, %b. %d"))
    date = date + timedelta(days=1)

layout = [
    [sg.Text("Username/ID:", size=(12,1)), sg.InputText(key="user")],
    [sg.Text("Password:", size=(12,1)), sg.InputText(key="pass", password_char="*")],
    [sg.Text("Browser:"),
     sg.Radio("Chrome", "browser", default=True, key="chrome"),
     sg.Radio("Safari", "browser", key="safari"),
     sg.Radio("Edge", "browser", key="edge")
     ],
    [sg.Text("Time slot:"), sg.Combo(slots, default_value="10:00", key="slot")],
    [sg.Text("Day of Week:"), sg.Combo(day_of_weeks, default_value="Today", key="dow")],
    [sg.Text("Refresh rate(s):"), sg.Combo(refresh_rates, default_value="15", key="refresh_rate")],
    [sg.Column([[sg.Button("Begin"), sg.Button("Stop", disabled=True)]], justification="center")],
    [sg.Text("Console output:")],
    [sg.Column([[sg.Multiline(key="log", size=(45,15))]], justification="center")],
    [sg.Column([[sg.Text(VERSION, font=("Arial", 9, "underline"), enable_events=True, key="version")]], justification="right")],
    [sg.Column([[sg.Text("vianney was here", font=("Arial", 9, "underline"), enable_events=True, key="developer")]], justification="right")]
]

window = sg.Window("UofC Fitness Booking", layout)

tracker = signup.Tracker()
tracker.addLogObserver(lambda s : window["log"].print(s))

task = None
stateChanged = False
def background_task(user, pwd, time_slot, dow, refresh_rate, browser):
    try:
        tracker.begin(browser, user, pwd, time_slot, dow, refresh_rate)
        tracker.stop()
    except Exception as e:
        window["log"].print("\n\nINTERNAL ERROR. PLEASE SEND CONSOLE LOG TO DEVELOPER.\n\n")
        logging.exception("Internal error.")
    global task
    global stateChanged
    task = None
    stateChanged = True

def start_task(user, pwd, time_slot, dow, refresh_rate, browser):
    global task
    task = Thread(target=background_task, args=(user, pwd, time_slot, dow, refresh_rate, browser))
    task.start()

def stop_task():
    global task
    tracker.stop()
    task.join()
    task = None

fernet = Fernet(b'idnmDU6AOXaBDYvagHvH3yjBPR_ZVoKlgNxllUSYWPU=')
output = "ub-state"
def saveCreds(user, pwd):
    obj = {"user": user, "pass": pwd}
    b = pickle.dumps(obj)
    enc = fernet.encrypt(b)
    with open(output, "wb") as f:
        f.write(enc)

def loadCreds():
    try:
        with open(output, "rb") as f:
            data = f.read()
            dec = fernet.decrypt(data)
            obj = pickle.loads(dec)
            return obj
    except:
        return None

initialSetup = False
while True:
    event, values = window.read(timeout=10)

    if not initialSetup:
        initialSetup = True
        try:
            new_version = requests.get("https://api.github.com/repos/nvianney/uofc_fitness_signup/releases/latest", timeout=5).json()["name"]
            if new_version != VERSION:
                window["log"].print("=====")
                window["log"].print("New version available [%s]: https://github.com/nvianney/uofc_fitness_signup/releases" % new_version)
                window["log"].print("=====")

        except Exception as e:
            logging.exception("Error checking version.")

        creds = loadCreds()
        if creds != None:
            window["user"].update(creds["user"])
            window["pass"].update(creds["pass"])


    if event == sg.WIN_CLOSED:
        break

    elif event == "Begin":
        if task != None:
            window["log"].print("Tracker is already running!")
            continue
        
        window["Begin"].update(disabled=True)
        window["Stop"].update(disabled=False)

        user = values["user"]
        pwd = values["pass"]
        time_slot = values["slot"]
        dow = values["dow"]
        refresh_rate = values["refresh_rate"]

        if dow != "Today":
            dow = dow[-2:]

        browser = None
        if values["chrome"]:
            browser = "chrome"
        elif values["safari"]:
            browser = "safari"
        elif values["edge"]:
            browser = "edge"
        else:
            raise ValueError("Unknown browser: %s" % browser)

        start_task(user, pwd, time_slot, dow if dow != "Today" else None, refresh_rate, browser)
        saveCreds(user, pwd)


    elif event == "Stop":
        if task == None:
            window["log"].print("Tracker is currently not running!")
            continue
        window["log"].print("Stopping...")

        window["Begin"].update(disabled=False)
        window["Stop"].update(disabled=True)

        stop_task()

        window["log"].print("Stopped")

    elif event == "version":
        webbrowser.open("https://github.com/nvianney/uofc_fitness_signup/releases")

    elif event == "developer":
        webbrowser.open("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    elif event == "__TIMEOUT__":
        if stateChanged:
            stateChanged = False
            window["Begin"].update(disabled=Thread==None)
            window["Stop"].update(disabled=Thread!=None)

window.close()

