from selenium.common.exceptions import TimeoutException, WebDriverException, NoAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver

import logging

from optparse import OptionParser
from getpass import getpass

from datetime import datetime
import time

import re

import threading
import os
import sys

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

BOOKING_URL = "https://iac01.ucalgary.ca/CamRecWebBooking/Login.aspx"
AUTH_URL = "https://iac01.ucalgary.ca/CamRecWebBooking/default.aspx"


class Tracker:
    running = True
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

        print(output)
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
        #submit_btn.click()
        # more reliable than performing a click
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

    def skipDay(self, driver, dow):
        wait = WebDriverWait(driver, 10)
        for _ in range(0, 7):
            elem = wait.until(EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_ctl00_lblAvailableFitness")))
            if dow in elem.text:
                return True

            driver.execute_script('WebForm_DoPostBackWithOptions(new WebForm_PostBackOptions("ctl00$ContentPlaceHolder1$lnkBtnNext", "", true, "", "", false, true))')
            wait.until(EC.staleness_of(elem))

        return False


    def scan(self, driver, hour, dow, refresh):

        def extractTime(e):
            s = e.text
            return s[10:15] + "(" + s[27:s.index("booked")-1] + ")" # hh:00(spots)

        self.write_console("Starting scan for workout at %s. Refresh rate: %ds" % (hour, refresh))
        wait = WebDriverWait(driver, 10)
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
                if dow != None:
                    res = self.skipDay(driver, dow)
                    if not res:
                        self.write_console("Unable to find day of week")
                        return

            self.write_console("")

            if elem != None:
                js = elem.get_attribute("href")[11:] # remove javascript:
                driver.execute_script(js)
                text = elem.text
                wait.until(EC.staleness_of(elem))
                self.write_console("Clicked link '%s'." % text)
                msg = wait.until(EC.presence_of_element_located((By.ID, "ctl00_lblMessage")))
                self.write_console("Response: %s" % msg.text)


    def loadDriver(self, browser):
        try:
            if browser == "chrome":
                return webdriver.Chrome()
            elif browser == "safari":
                return webdriver.Safari()
            else:
                raise TypeError("Unknown browser name: %s" % browser)
        except WebDriverException as e:
            self.write_console("Cannot find web driver for %s. Contact the developer for more info." % browser)
            logging.error(str(e))
            return None

    def begin(self, browser, user, pwd, time_slot, dow, refresh_sec):
        self.running = True

        self.write_console("===================")
        self.write_console("Browser: %s" % browser)
        self.write_console("Username: %s" % user)
        self.write_console("Time slot: %s" % time_slot)
        self.write_console("Day of week: %s" % dow)
        self.write_console("Refresh time(s): %s" % refresh_sec)
        self.write_console("===================")

        driver = self.loadDriver(browser)
        if driver == None:
            return

        if not self.login(driver, user, pwd):
            driver.close()
            return

        if dow != None:
            res = self.skipDay(driver, dow)
            if not res:
                self.write_console("Unable to find day of week. Please contact the developer.")
                driver.close()
                return

        # Scan for workouts
        self.scan(driver, time_slot, dow, refresh_sec)

        self.e.clear()
        self.e.wait(10)

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

    parser = OptionParser()
    parser.add_option("-u", "--user", dest="user", help="Username or ID")
    parser.add_option("-p", "--password", dest="pwd", help="Password")
    parser.add_option("-t", "--refresh", dest="refresh", help="Refresh time, in seconds", type="int", default=15)
    parser.add_option("-w", "--weekday", dest="dow", help="Day of Week", choices=["tod", "m", "t", "w", "th", "f", "sa", "su"], default="tod")
    parser.add_option(
        "-b",
        "--browser",
        dest="browser",
        help="The browser to run the program with",
        choices = ["chrome", "safari"],
        default="chrome"
    )
    (options, args) = parser.parse_args()

    if len(args) == 0:
        print("Error: specify the hour of workout in the format of [hh:mm]. For example, '09:00', or '22:00'")
        return
    time_slot = args[0]

    timeregex = re.compile("^[0-9][0-9]:[0-9][0-9]$")
    if not timeregex.search(time_slot):
        print("Invalid time entry")
        return

    user = options.user
    pwd = options.pwd
    if not user:
        logging.debug("No username passed as options. Requesting username.")
        print("Enter your username/ID: ", end="")
        user = input()
    if not options.pwd:
        logging.debug("No password passed as options. Requesting password.")
        pwd = getpass("Password for %s:" % user)

    dow = None

    if options.dow != "tod":
        dow = mapDow(options.dow)


    tracker = Tracker()
    tracker.begin(options.browser, user, pwd, time_slot, dow, options.refresh)

if __name__ == '__main__':
    main()
