import signup
import PySimpleGUI as sg
from threading import Thread

slots = list(map(lambda x : "%02d:00" % x, range(5, 21+1)))
refresh_rates = list(range(5, 120+1, 5))
day_of_weeks = ["Today", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

layout = [
    [sg.Text("Username/ID:", size=(12,1)), sg.InputText(key="user")],
    [sg.Text("Password:", size=(12,1)), sg.InputText(key="pass", password_char="*")],
    [sg.Text("Browser:"),
     sg.Radio("Chrome", "browser", default=True, key="chrome"),
     sg.Radio("Safari", "browser", key="safari")],
    [sg.Text("Time slot:"), sg.Combo(slots, default_value="10:00", key="slot")],
    [sg.Text("Day of Week:"), sg.Combo(day_of_weeks, default_value="Today", key="dow")],
    [sg.Text("Refresh rate(s):"), sg.Combo(refresh_rates, default_value="15", key="refresh_rate")],
    [sg.Column([[sg.Button("Begin"), sg.Button("Stop", disabled=True)]], justification="center")],
    [sg.Text("Console output:")],
    [sg.Column([[sg.Multiline(key="log", size=(45,15))]], justification="center")]

]

window = sg.Window("UofC fitness booking - VN", layout)

tracker = signup.Tracker()
tracker.addLogObserver(lambda s : window["log"].print(s))

task = None
stateChanged = False
def background_task(user, pwd, time_slot, dow, refresh_rate, browser):
    tracker.begin(browser, user, pwd, time_slot, dow, refresh_rate)
    tracker.stop()
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


while True:
    event, values = window.read(timeout=10)

    if event == sg.WIN_CLOSED:
        break

    elif event == "Begin":
        if task != None:
            window["log"].print("Tracker is already running!")
            continue

        window["Begin"].update(disabled=True)
        window["Stop"].update(disabled=False)

        window["log"].update("")
        user = values["user"]
        pwd = values["pass"]
        time_slot = values["slot"]
        dow = values["dow"]
        refresh_rate = values["refresh_rate"]

        browser = None
        if values["chrome"]:
            browser = "chrome"
        elif values["safari"]:
            browser = "safari"
        else:
            raise ValueError("Unknown browser: %s" % browser)

        start_task(user, pwd, time_slot, dow if dow != "Today" else None, refresh_rate, browser)


    elif event == "Stop":
        if task == None:
            window["log"].print("Tracker is currently not running!")
            continue
        window["log"].print("Stopping...")

        window["Begin"].update(disabled=False)
        window["Stop"].update(disabled=True)

        stop_task()

        window["log"].print("Stopped")

    elif event == "__TIMEOUT__":
        if stateChanged:
            stateChanged = False
            window["Begin"].update(disabled=Thread==None)
            window["Stop"].update(disabled=Thread!=None)


window.close()

