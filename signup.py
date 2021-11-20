from selenium.common.exceptions import TimeoutException, WebDriverException, NoAlertPresentException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

import logging

import requests

from argparse import ArgumentParser
from getpass import getpass

from datetime import datetime
import time

import re

import threading
import os
import sys

def base_path():
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return base_path


# https://stackoverflow.com/questions/7674790/bundling-data-files-with-pyinstaller-onefile
def version():
    f = open(os.path.join(base_path(), "VERSION"), "r")
    VERSION = f.readline().rstrip()
    f.close()
    return VERSION

VERSION = version()

# append current path for chromedriver
# https://pyinstaller.readthedocs.io/en/stable/runtime-information.html
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys module by a flag frozen=True and sets the app
    # path into variable _MEIPASS'.
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
os.environ["PATH"] += os.pathsep + application_path

def override_where():
    """ overrides certifi.core.where to return actual location of cacert.pem"""
    # change this to match the location of cacert.pem
    return os.path.join(base_path(), "cacert.pem")

# https://stackoverflow.com/questions/46119901/python-requests-cant-find-a-folder-with-a-certificate-when-converted-to-exe
# is the program compiled?
if hasattr(sys, "frozen"):
    import certifi.core

    os.environ["REQUESTS_CA_BUNDLE"] = override_where()
    certifi.core.where = override_where

    # delay importing until after where() has been replaced
    import requests.utils
    import requests.adapters
    # replace these variables in case these modules were
    # imported before we replaced certifi.core.where
    requests.utils.DEFAULT_CA_BUNDLE_PATH = override_where()
    requests.adapters.DEFAULT_CA_BUNDLE_PATH = override_where()

BOOKING_URL = "https://iac01.ucalgary.ca/CamRecWebBooking/Login.aspx"
AUTH_URL = "https://iac01.ucalgary.ca/CamRecWebBooking/default.aspx"


class Tracker:
    running = True
    simulate_click = False
    log_observers = []
    e = threading.Event()

    def stop(self):
        # TODO: critical section
        self.running = False
        self.e.set()

    def write_console(self, s, stamp = True):
        output = s
        if stamp:
            now = datetime.now()
            output = "[%s] %s" % (now.strftime("%H:%M:%S"), s)

        logging.info(output)
        for observer in self.log_observers:
            observer(output)

    def addLogObserver(self, observer):
        self.log_observers.append(observer)

    def login(self, driver, user, pwd):
        driver.get(BOOKING_URL)
        wait = WebDriverWait(driver, 10)


        # wait for page load
        wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_logCamRec_panLogin")))

        # fill in username + pass
        user_field = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_logCamRec_UserName"))
        )
        pass_field = wait.until(
            EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_logCamRec_Password"))
        )

        user_field.send_keys(user)
        pass_field.send_keys(pwd)
        submit_btn = wait.until(
            EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder1_logCamRec_LoginButton"))
        )

        # safari is buggy when simulating clicks. chrome cannot run JS
        if self.simulate_click:
            submit_btn.click()
        else:
            driver.execute_script('WebForm_DoPostBackWithOptions(new WebForm_PostBackOptions("ctl00$ContentPlaceHolder1$logCamRec$LoginButton", "", true, "logCamRec", "", false, true))')

        try:
            wait.until(EC.staleness_of(submit_btn))
            if driver.current_url != AUTH_URL:
                self.write_console("Incorrect login credentials")
                return False

        except TimeoutException:
            self.write_console("Connection error")
            return False

        return True

    def skipDay(self, driver, day):
        wait = WebDriverWait(driver, 10)
        for _ in range(0, 7):
            elem = wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_ctl00_lblAvailableFitness")))
            if f" {day}," in elem.text:
                return True

            if self.simulate_click:
                btn = wait.until(EC.element_to_be_clickable((By.ID, "ctl00_ContentPlaceHolder1_lnkBtnNext")))
                btn.click()
            else:
                driver.execute_script('WebForm_DoPostBackWithOptions(new WebForm_PostBackOptions("ctl00$ContentPlaceHolder1$lnkBtnNext", "", true, "", "", false, true))')
            wait.until(EC.staleness_of(elem))

        return False


    def scan(self, driver, hour, day, refresh):

        def extractTime(e):
            s = e.text
            return s[10:15] + "(" + s[27:s.index("booked")-1] + ")" # hh:00(spots)

        self.write_console("Starting scan for workout at %s. Refresh rate: %ds" % (hour, refresh))
        wait = WebDriverWait(driver, 10)

        wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_ctl00_pnlWall")))

        try:
            msg = driver.find_element(By.ID, "ctl00_lblMessage")
            self.write_console("System message: %s" % msg.text)
        except NoSuchElementException as e:
            logging.info("No system message")

        query = "Book from %s" % hour

        elem = None
        while elem == None and self.running:
            wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_ctl00_pnlWall")))
            dateElem = driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_ctl00_lblAvailableFitness")
            container = driver.find_element(By.ID, "ctl00_ContentPlaceHolder1_ctl00_pnlWall")
            rows = container.find_elements(By.XPATH, ".//fieldset/ul/li/a")

            for row in rows:
                if query in row.text:
                    elem = row
                    break

            if elem == None:
                self.write_console("No workouts found at %s for %s." % (hour, dateElem.text[12:-1]))
                hours = map(extractTime, rows)
                self.write_console("Available workout times:")
                for t in hours:
                    self.write_console("    %s" % t)

                self.e.clear()
                self.e.wait(refresh)

                # on safari, selenium cannot auto accept resend form. we'll use location.reload() instead
                # and navigate to the day every refresh (*)
                driver.get(AUTH_URL)
                #driver.refresh()

                # accept any resend form dialogs
                try:
                    alert = driver.switch_to.alert
                    alert.accept()
                    driver.switch_to.window(driver.window_handles[0])
                except NoAlertPresentException:
                    pass

                wait.until(EC.staleness_of(container))

                # skip, according to (*)
                if day != None:
                    res = self.skipDay(driver, day)
                    if not res:
                        self.write_console("Unable to find day of week")
                        return

            self.write_console("")

            if elem != None:
                text = elem.text
                if self.simulate_click:
                    elem.click()
                else:
                    js = elem.get_attribute("href")[11:] # remove javascript:
                    driver.execute_script(js)
                wait.until(EC.staleness_of(elem))
                self.write_console("Clicked link '%s'." % text)
                msg = wait.until(EC.presence_of_element_located((By.ID, "ctl00_lblMessage")))
                self.write_console("Response: %s" % msg.text)


    def getDriverLink(self, browser):
        if browser == "chrome":
            return "https://chromedriver.chromium.org/downloads"
        elif browser == "safari":
            return None
        elif browser == "edge":
            return "https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/"
        else:
            return None

    def loadDriver(self, browser):
        try:
            if browser == "chrome":
                options = ChromeOptions()
                options.add_argument("--headless")
                return webdriver.Chrome(options=options)
            elif browser == "safari":
                return webdriver.Safari()
            elif browser == "edge":
                return webdriver.Edge()
            else:
                raise TypeError("Unknown browser name: %s" % browser)
        except WebDriverException as e:
            self.write_console("Cannot find web driver for %s. Download the driver and place the executable in the same folder as this program." % browser)
            self.write_console("For example, if this program is currently located on your Desktop, and you downloaded 'chromedriver.exe', place 'chromedriver.exe' on the Desktop.")
            self.write_console("Contact the developer for more information")
            link = self.getDriverLink(browser)
            if link != None:
                self.write_console("%s driver: %s" % (browser, link))
            logging.error(str(e))
            return None

    def begin(self, browser, user, pwd, time_slot, day, refresh_sec):
        self.running = True

        self.write_console("===================")
        self.write_console("Browser: %s" % browser)
        self.write_console("Username: %s" % user)
        self.write_console("Time slot: %s" % time_slot)
        self.write_console("Day: %s" % day)
        self.write_console("Refresh time(s): %s" % refresh_sec)
        self.write_console("===================")

        # safari is buggy with click simulation, but chrome is buggy with running JS
        if browser == "safari":
            self.simulate_click = False
        else:
            self.simulate_click = True
        driver = self.loadDriver(browser)
        if driver == None:
            return

        if not self.login(driver, user, pwd):
            driver.close()
            return

        if day != None:
            res = self.skipDay(driver, day)
            if not res:
                self.write_console("Unable to find day of week. Please contact the developer.")
                driver.close()
                return

        # Scan for workouts
        self.scan(driver, time_slot, day, refresh_sec)

        driver.close()

def mapDow(s):
    if s == "m":
        return "Monday"
    elif s == "t":
        return "Tuesday"
    elif s == "w":
        return "Wednesday"
    elif s == "th":
        return "Thursday"
    elif s == "f":
        return "Friday"
    elif s == "sa":
        return "Saturday"
    elif s == "su":
        return "Sunday"

def main():
    logging.basicConfig(level=logging.INFO)

    parser = ArgumentParser()
    parser.add_argument("-u", "--user", dest="username", help="Username or ID")
    parser.add_argument("-p", "--password", dest="password", help="Password")
    parser.add_argument(
        "-t",
        "--refresh",
        dest="refresh",
        help="Refresh time, in seconds (default: %(default)s",
        type=int,
        default=15)
    parser.add_argument(
        "-d",
        "--day",
        dest="day",
        help="Day of workout, or 'tod' for today. ex. -d 25 (default: %(default)s)",
        default="tod")
    parser.add_argument(
        "-b",
        "--browser",
        dest="browser",
        help="The browser to run the program with (default: %(default)s",
        choices = ["chrome", "safari", "edge"],
        default="chrome"
    )
    parser.add_argument("time", type=str, help="The time for workout. For example, 09:00 or 22:00")
    args = parser.parse_args()

    time_slot = args.time

    timeregex = re.compile("^[0-9][0-9]:[0-9][0-9]$")
    if not timeregex.search(time_slot):
        print("Invalid time entry. Run with -h for help.")
        return

    user = args.username
    pwd = args.password
    if not user:
        logging.debug("No username passed as options. Requesting username.")
        print("Enter your username/ID: ", end="")
        user = input()
    if not pwd:
        logging.debug("No password passed as options. Requesting password.")
        pwd = getpass("Password for %s:" % user)

    day = None

    if args.day != "tod":
        day = args.day

    try:
        new_version = requests.get("https://api.github.com/repos/nvianney/uofc_fitness_signup/releases/latest", timeout=5).json()["name"]
        if new_version != VERSION:
            print("New version available: https://github.com/nvianney/uofc_fitness_signup/releases")
            print("Current: %s. New: %s." % (VERSION, new_version))

    except Exception as e:
        logging.exception("Error checking version.")

    tracker = Tracker()
    tracker.begin(args.browser, user, pwd, time_slot, day, args.refresh)

if __name__ == '__main__':
    main()
