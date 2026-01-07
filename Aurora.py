# Main Aurora python file, runs the webserver and the Aurora client, configs are loaded from extensions directory
import cherrypy
import os
import multiprocessing
import time
import json
import cherrypy
import configparser
import threading
import glob
import importlib
import inspect
import base64
import logging
from urllib.request import urlopen
import board
import neopixel
import cv2
import sys
from shutil import copyfile

#from jinja2 import Environment, FileSystemLoader
from jinja2 import *


env = Environment(loader=FileSystemLoader("webserver/templates"))


class AuroraManager:
    def __init__(self):
        self.config_file = "./config.ini"
        self.config = {}  # config dict
        self.extensions = {}

        self.extensions_dir = False
        self.current_extension = False
        self.current_extension_name = False
        self.current_extension_meta = False
        self.screenshot_path = False
        self.extension_started = False
        self.loopRunning = False
        self.messages = []
        self.enabled = False
        self.screenshot_b64 = ""
        self.pixel_image_b64 = ""
        self.vid = False
        self.neoPixels = False

        # Ironically we need to load the config to figure out the logging level, so if config fails... S.O.L
        # process config file
        self.loadConfig()

        # Set logging
        logging.basicConfig(
            format="%(asctime)s %(message)s", datefmt="%m/%d/%Y %I:%M:%S %p"
        )
        self.debug = bool(os.environ["AURORA_DEBUG"])
        logging.info(
            "DEBUG OS ENV: {} status: {}".format(
                os.environ["AURORA_DEBUG"], bool(os.environ["AURORA_DEBUG"])
            )
        )
        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
        else:
            logging.info("SET DEBUG OFF")
            logging.getLogger().setLevel(logging.ERROR)

        # Setup NeoPixels
        self.setupNeoPixels()

        # Setup HDMI
        self.setupHDMI()

        # populate extensions
        self.populateExtensions()

        # set/load the extension
        self.setCurrentExtension(self.current_extension_name)

    def setupNeoPixels(self):
        try:
            # this is janky and show() speed is impacted by the number of pixels, but we cant re-init this :(
            self.neoPixels = neopixel.NeoPixel(board.D18, 500, auto_write=False)
            self.neoPixels.fill((0, 0, 0))  # turn them off when we initialise
            self.neoPixels.show()  # ironic.
        except Exception as e:
            # Lets not get here chaps.
            self.log(
                "Error during initialisation of NeoPixel:{}".format(str(e)),
            )
            sys.exit(1)

    def setupHDMI(self):
        self.vid = False
        # Setup HDMI input
        try:
            # Try Setup Video Capture devices
            for i in range(0, 10):
                self.log("Trying video device {}.".format(i))
                testVid = cv2.VideoCapture(i)
                test, frame = testVid.read()
                if test:
                    self.vid = testVid
                    self.log("Using video device {}.".format(i))
                    self.vid.set(cv2.CAP_PROP_SATURATION, 255)
                    break
                else:
                    logging.error("device {} failed".format(i))
            if not self.vid:
                self.log("Failed to initialise video device")
                sys.exit(1)

            self.vid.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            self.vid_w = int(self.vid.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.vid_h = int(self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.log(
                "Initialized Aurora with feed of {} x {}".format(self.vid_w, self.vid_h)
            )

            # Lets save initial values
            self.config["HDMI_INITIAL"]["HDMI_BRIGHTNESS"] = str(
                int(self.vid.get(cv2.CAP_PROP_BRIGHTNESS))
            )
            self.config["HDMI_INITIAL"]["HDMI_SATURATION"] = str(
                int(self.vid.get(cv2.CAP_PROP_SATURATION))
            )
            self.config["HDMI_INITIAL"]["HDMI_CONTRAST"] = str(
                int(self.vid.get(cv2.CAP_PROP_CONTRAST))
            )
            self.config["HDMI_INITIAL"]["HDMI_HUE"] = str(
                int(self.vid.get(cv2.CAP_PROP_HUE))
            )
            self.saveConfig()
            self.log(
                "Default State:\nBrightness:{} Saturation: {} Contrast: {} Hue: {}".format(
                    int(self.vid.get(cv2.CAP_PROP_BRIGHTNESS)),
                    int(self.vid.get(cv2.CAP_PROP_SATURATION)),
                    int(self.vid.get(cv2.CAP_PROP_CONTRAST)),
                    int(self.vid.get(cv2.CAP_PROP_HUE)),
                )
            )
        except Exception as e:
            # Lets not get here either!
            self.log("Error during initialisation of HDMI capture:{}".format(str(e)))
            sys.exit(1)

        # Let set the HDMI input settings
        try:
            self.vid.set(
                cv2.CAP_PROP_SATURATION, int(self.config["HDMI"]["HDMI_SATURATION"])
            )
            self.vid.set(
                cv2.CAP_PROP_BRIGHTNESS, int(self.config["HDMI"]["HDMI_BRIGHTNESS"])
            )
            self.vid.set(
                cv2.CAP_PROP_CONTRAST, int(self.config["HDMI"]["HDMI_CONTRAST"])
            )
            self.vid.set(cv2.CAP_PROP_HUE, int(self.config["HDMI"]["HDMI_HUE"]))

        except Exception as e:
            # Lets not get here chaps.
            self.log("Error during initialisation of HDMI:{}".format(str(e)))
            sys.exit(1)

    def saveConfig(self):
        with open(self.config_file, "w") as configfile:
            self.config.write(configfile)
        self.loadConfig()

    def log(self, message):
        logging.info(message)

    # Load the config file
    def loadConfig(self):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        self.config.read(self.config_file)

        # Lets load the enviroment variables
        for key, val in self.config["AURORA"].items():
            os.environ[key] = val
            self.log("setting key {} to {}".format(key, val))

        # Setup extensions dir
        self.extensions_dir = self.config["EXTENSIONS"]["directory"]

        # Set default extension
        self.current_extension_name = self.config["EXTENSIONS"]["current_extension"]

        # set screenshotpath
        self.screenshot_path = self.config["GENERAL"]["screenshot_path"]

        # set pixel image path
        self.pixel_image_path = self.config["GENERAL"]["pixel_image_path"]

        # set enabled flag
        self.enabled = self.config.getboolean("GENERAL", "enabled")

    # Get a particular extension
    def getExtensionClass(self, extension_name, extension_dir):
        module = importlib.import_module(
            extension_dir + "." + extension_name, package=extension_name
        )
        importlib.reload(module)
        x = False
        try:
            extensionClass = getattr(module, extension_name)
            x = extensionClass(self.neoPixels, self.vid)
            logging.info(
                "Loaded: {} from ./{}/{}.py".format(
                    x.Name, extension_dir, extension_name
                )
            )
        except Exception as e:
            self.addMessage(
                "Could not load module from ./{}/{}.py error: {}".format(
                    extension_dir, extension_name, str(e)
                )
            )
            logging.info(
                "Could not load module from ./{}/{}.py error: {}".format(
                    extension_dir, extension_name, str(e)
                )
            )

        return x

    def fetchMeta(self, extension, filename):
        if extension == False:
            return False
        extension_meta = {}
        extension_meta["Author"] = extension.Author
        extension_meta["Description"] = extension.Description
        extension_meta["Name"] = extension.Name
        extension_meta["FileName"] = filename
        return extension_meta

    # Populate all the extensions from the extensions class
    def populateExtensions(self):
        self.extensions = {}
        extension_dir = self.extensions_dir
        for file in glob.glob("./{}/*.py".format(extension_dir)):
            filename = os.path.splitext(os.path.basename(file))[0]

            # Ignore __ files
            if filename.startswith("__"):
                continue

            if filename not in ["exampleExtension2", "Aurora_Configure"]:
                x = self.getExtensionClass(filename, extension_dir)
                if x != False:
                    extension_meta = self.fetchMeta(x, filename)
                    self.extensions[filename] = extension_meta

    def addMessage(self, msg):

        if msg not in self.messages:
            self.messages.append(msg)

    # Get the current extension to be run
    def getCurrentExtension(self):
        os.environ["AURORA_CURRENT_EXTENSION_NAME"] = self.current_extension_name
        current_extension = self.getExtensionClass(
            self.current_extension_name, self.extensions_dir
        )
        self.current_extension = current_extension
        return current_extension

    def setCurrentExtension(self, new_current_extension):
        tempExt = self.getExtensionClass(new_current_extension, self.extensions_dir)
        if tempExt != False:

            while self.loopRunning == True:
                # lets wait this out or things get REEAAAL funky
                time.sleep(0.001)

            if self.extension_started == True:
                self.tearDownExtension()
                self.extension_started = False

            self.current_extension = tempExt
            self.current_extension_name = new_current_extension

            os.environ["AURORA_CURRENT_EXTENSION_NAME"] = new_current_extension
            self.current_extension_meta = self.fetchMeta(
                self.current_extension, new_current_extension
            )
            self.setupExtension()

            if new_current_extension != "Aurora_Configure":
                self.config.set(
                    "EXTENSIONS", "current_extension", self.current_extension_name
                )
                self.saveConfig()
                self.extension_started = True

    def takeScreenshot(self):
        self.current_extension.takeScreenShot(self.screenshot_path)

    def makePixelImage(self):
        self.current_extension.makePixelFrame(self.pixel_image_path)

    def setupExtension(self):
        self.current_extension.setup()
        self.extension_started = True

    def tearDownExtension(self):
        self.extension_started = False
        self.current_extension.teardown()

    def loop(self):
        if self.enabled == True:  # only if the entire thing is enabled
            if self.extension_started != False:  # only loop if the extension is started
                # lets let other processes know we are in the middle of a loop
                self.loopRunning = True
                try:
                    self.current_extension.visualise()
                except Exception as e:
                    self.log("Error in visualise: {}".format(str(e)))
                self.loopRunning = False


class Aurora_Webserver(object):
    def __init__(self, Manager):
        self.manager = Manager

    @cherrypy.tools.json_out()
    @cherrypy.expose
    def status(self):
        self.manager.loadConfig()
        enabled_status = self.manager.enabled
        current_extension = self.manager.current_extension.Name
        current_extension_class = self.manager.current_extension_name
        with open("VERSION", "r") as f:
            current_version = f.read()
        tmpl = env.get_template("status.json")
        template_variables = {}
        template_variables["current_extension"] = current_extension
        template_variables["current_extension_class"] = current_extension_class
        template_variables["enabled"] = enabled_status
        template_variables["current_version"] = current_version
        return tmpl.render(template_variables)

    @cherrypy.tools.json_out()
    @cherrypy.expose
    def current_status(self):
        """Returns simple on/off status"""
        return {"status": "on" if self.manager.enabled else "off"}

    @cherrypy.tools.json_out()
    @cherrypy.expose
    def current_extension(self):
        """Returns current extension name"""
        extension_map = {
            "Aurora_Ambient_AutoCrop": "autocrop",
            "Aurora_Ambient_NoCrop": "nocrop",
            "Aurora_Ambient_16x9": "16x9",
            "Aurora_Rainbow": "rainbow",
            "Aurora_Meteor": "meteor",
            "Aurora_AudioSpectogram": "audio spectogram"
        }
        extension_class = self.manager.current_extension_name
        extension_friendly = extension_map.get(extension_class, extension_class)
        return {
            "extension": extension_friendly,
            "extension_class": extension_class,
            "extension_name": self.manager.current_extension.Name
        }

    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.expose
    def set_status(self):
        """Set Aurora on or off"""
        input_json = cherrypy.request.json
        if "status" not in input_json:
            return {"status": "error", "message": "Missing 'status' parameter. Use 'on' or 'off'"}
        
        status = input_json["status"].lower()
        if status not in ["on", "off"]:
            return {"status": "error", "message": "Invalid status. Use 'on' or 'off'"}
        
        try:
            enabled_status = (status == "on")
            self.manager.enabled = enabled_status
            
            if enabled_status:
                self.manager.setupExtension()
            else:
                self.manager.tearDownExtension()
            
            self.manager.config.set("GENERAL", "enabled", str(enabled_status))
            self.manager.saveConfig()
            
            return {"status": "success", "current_status": status}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.expose
    def set_extension(self):
        """Set the current extension"""
        input_json = cherrypy.request.json
        if "extension" not in input_json:
            return {"status": "error", "message": "Missing 'extension' parameter"}
        
        extension_input = input_json["extension"].lower()
        
        # Map friendly names to class names
        extension_map = {
            "autocrop": "Aurora_Ambient_AutoCrop",
            "nocrop": "Aurora_Ambient_NoCrop",
            "16x9": "Aurora_Ambient_16x9",
            "rainbow": "Aurora_Rainbow",
            "meteor": "Aurora_Meteor",
            "audio spectogram": "Aurora_AudioSpectogram",
            "audiospectogram": "Aurora_AudioSpectogram"
        }
        
        # Allow direct class name or friendly name
        extension_class = extension_map.get(extension_input, extension_input)
        
        # Validate extension exists
        if extension_class not in self.manager.extensions and extension_class not in extension_map.values():
            available = list(extension_map.keys())
            return {
                "status": "error", 
                "message": f"Invalid extension. Available: {', '.join(available)}"
            }
        
        try:
            self.manager.setCurrentExtension(extension_class)
            return {
                "status": "success", 
                "extension": extension_input,
                "extension_class": extension_class
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @cherrypy.expose
    def about(self):
        self.manager.loadConfig()
        current_version = "Cannot read version"
        with open("VERSION", "r") as f:
            current_version = f.read()
        github_version = "Cannot read from github"
        try:
            githubURL = (
                "https://raw.githubusercontent.com/nick-renard/Aurora/master/VERSION"
            )
            github_page = urlopen(githubURL)
            github_version = github_page.read().decode("utf-8").strip()

        except Exception as e:
            self.manager.log("Exception trying to open github page:{}".format(str(e)))
            # we cant connect to github?
            pass

        tmpl = env.get_template("about.html")
        template_variables = {}
        template_variables["current_version"] = current_version
        template_variables["github_version"] = github_version
        template_variables["extensions_meta"] = self.manager.extensions
        template_variables[
            "current_extension_meta"
        ] = self.manager.current_extension_meta
        template_variables["config"] = {
            section: dict(self.manager.config[section])
            for section in self.manager.config.sections()
        }
        template_variables["page"] = "about"
        template_variables["msg"] = self.manager.messages
        self.manager.messages = []
        return tmpl.render(template_variables)

    @cherrypy.expose
    def index(self):
        if self.manager.current_extension_name == "Aurora_Configure":
            # process config file
            self.manager.loadConfig()
            # set/load the extension
            self.manager.setCurrentExtension(self.manager.current_extension_name)
            self.manager.setupExtension()

        self.manager.populateExtensions()
        tmpl = env.get_template("index.html")

        template_variables = {}

        template_variables["extensions_meta"] = self.manager.extensions
        template_variables[
            "current_extension_meta"
        ] = self.manager.current_extension_meta
        if self.manager.current_extension != False:
            template_variables["fps"] = self.manager.current_extension.FPS_avg
        else:
            template_variables["fps"] = 0
        template_variables["configured"] = self.manager.config.getboolean(
            "GENERAL", "configured"
        )
        template_variables["enabled"] = self.manager.config.getboolean(
            "GENERAL", "enabled"
        )
        template_variables["page"] = "home"
        template_variables["msg"] = self.manager.messages
        self.manager.messages = []
        return tmpl.render(template_variables)

    @cherrypy.expose
    def view(self):
        if self.manager.current_extension_name == "Aurora_Configure":
            # process config file
            self.manager.loadConfig()
            # set/load the extension
            self.manager.setCurrentExtension(self.manager.current_extension_name)
            self.manager.setupExtension()

        self.manager.populateExtensions()
        tmpl = env.get_template("view.html")
        self.screenshot()
        template_variables = {}

        template_variables["extensions_meta"] = self.manager.extensions
        template_variables[
            "current_extension_meta"
        ] = self.manager.current_extension_meta
        if self.manager.current_extension != False:
            template_variables["fps"] = self.manager.current_extension.FPS_avg
        else:
            template_variables["fps"] = 0
        template_variables["configured"] = self.manager.config.getboolean(
            "GENERAL", "configured"
        )
        template_variables["enabled"] = self.manager.config.getboolean(
            "GENERAL", "enabled"
        )
        template_variables["page"] = "view"
        template_variables["msg"] = self.manager.messages
        self.manager.messages = []
        return tmpl.render(template_variables)

    @cherrypy.expose
    def settings(self):
        """Custom settings page for HDMI and Aurora configuration"""
        self.manager.populateExtensions()
        tmpl = env.get_template("settings.html")
        template_variables = {}
        
        # Load current config values
        template_variables["hdmi_brightness"] = self.manager.config.getint("HDMI", "HDMI_BRIGHTNESS")
        template_variables["hdmi_saturation"] = self.manager.config.getint("HDMI", "HDMI_SATURATION")
        template_variables["hdmi_contrast"] = self.manager.config.getint("HDMI", "HDMI_CONTRAST")
        template_variables["hdmi_hue"] = self.manager.config.getint("HDMI", "HDMI_HUE")
        template_variables["aurora_gamma"] = self.manager.config.getfloat("AURORA", "AURORA_GAMMA")
        template_variables["aurora_dark_threshold"] = self.manager.config.getint("AURORA", "AURORA_DARKTHRESHOLD")
        
        template_variables["configured"] = self.manager.config.getboolean("GENERAL", "configured")
        template_variables["enabled"] = self.manager.config.getboolean("GENERAL", "enabled")
        template_variables["extensions_meta"] = self.manager.extensions
        template_variables["current_extension_meta"] = self.manager.current_extension_meta
        if self.manager.current_extension != False:
            template_variables["fps"] = self.manager.current_extension.FPS_avg
        else:
            template_variables["fps"] = 0
        template_variables["timestamp"] = int(time.time())
        template_variables["page"] = "settings"
        template_variables["msg"] = self.manager.messages
        self.manager.messages = []
        return tmpl.render(template_variables)

    @cherrypy.expose
    def configure(self):
        if self.manager.enabled == False:  # Its turned off, we need it on to config
            self.manager.enabled = True
        self.manager.setCurrentExtension("Aurora_Configure")
        # self.manager.setCurrentExtension("Aurora_Ambient_AutoCrop")
        self.manager.extension_started = False  # so it doesnt loop visualise
        self.manager.current_extension.visualise()
        self.screenshot()

        tmpl = env.get_template("configure.html")
        template_variables = {}
        template_variables[
            "pixels_darkthreshold"
        ] = self.manager.current_extension.darkThreshhold
        template_variables["pixels_left"] = self.manager.current_extension.pixelsLeft
        template_variables["pixels_right"] = self.manager.current_extension.pixelsRight
        template_variables["pixels_top"] = self.manager.current_extension.pixelsTop
        template_variables[
            "pixels_bottom"
        ] = self.manager.current_extension.pixelsBottom
        # template_variables["hdmi_saturation"] = self.manager.config.getint(
        #     "HDMI", "HDMI_SATURATION"
        # )
        # template_variables["hdmi_brightness"] = self.manager.config.getint(
        #     "HDMI", "HDMI_BRIGHTNESS"
        # )
        # template_variables["hdmi_hue"] = self.manager.config.getint("HDMI", "HDMI_HUE")
        # template_variables["hdmi_contrast"] = self.manager.config.getint(
        #     "HDMI", "HDMI_CONTRAST"
        # )
        # template_variables["hdmi_brightness_default"] = int(self.manager.config["HDMI_INITIAL"]["HDMI_BRIGHTNESS"])
        # template_variables["hdmi_saturation_default"] = int(self.manager.config["HDMI_INITIAL"]["HDMI_SATURATION"])
        # template_variables["hdmi_contrast_default"] = int(self.manager.config["HDMI_INITIAL"]["HDMI_CONTRAST"])
        # template_variables["hdmi_hue_default"] = int(self.manager.config["HDMI_INITIAL"]["HDMI_HUE"])
        template_variables["hdmi_gamma"] = self.manager.current_extension.gamma
        template_variables["page"] = "configure"
        template_variables["msg"] = self.manager.messages
        self.manager.messages = []

        return tmpl.render(template_variables)

    @cherrypy.tools.json_out()
    @cherrypy.expose
    def toggleEnable(self):
        if self.manager.enabled:
            self.manager.tearDownExtension()
        else:
            self.manager.setupExtension()

        self.manager.enabled = not self.manager.enabled

        return {"status": self.manager.enabled}

    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    @cherrypy.expose
    def update_config(self):
        input_json = cherrypy.request.json
        if "enabled" in input_json:
            try:
                return_json = {"status": "ok"}
                enabled_status = input_json["enabled"]
                self.manager.enabled = enabled_status
                if enabled_status == False:
                    # we are turning it off, tear down the extension
                    self.manager.tearDownExtension()
                    return_json["message"] = "Aurora successfully turned off"
                elif enabled_status == True:
                    # we are turning it on, lets put everything back
                    self.manager.setupExtension()
                    return_json["message"] = "Aurora successfully turned on"

                self.manager.config.set("GENERAL", "enabled", str(enabled_status))
                self.manager.saveConfig()
                return return_json

            except Exception as e:
                return {"status": "error", "error": str(e)}
                pass
        else:
            return {"status": "error", "error": "No setting found in request"}

    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.expose
    def update_HDMI_config(self):
        input_json = cherrypy.request.json
        # saturation = int(input_json["hdmi_saturation"])
        # hue = int(input_json["hdmi_hue"])
        # contrast = int(input_json["hdmi_contrast"])
        # brightness = int(input_json["hdmi_brightness"])

        errors = []
        try:
            gamma = float(input_json["hdmi_gamma"])
            self.manager.current_extension.gamma = gamma
            if "save" in input_json:
                self.manager.config.set("AURORA", "AURORA_GAMMA", str(gamma))
                self.manager.saveConfig()
                self.manager.addMessage("Saved config!")

            # self.manager.vid.set(cv2.CAP_PROP_SATURATION, saturation)
            # self.manager.vid.set(cv2.CAP_PROP_HUE, hue)
            # self.manager.vid.set(cv2.CAP_PROP_BRIGHTNESS, brightness)
            # self.manager.vid.set(cv2.CAP_PROP_CONTRAST, contrast)

            # self.manager.log(
            #     "Brightness:{} Saturation: {} Contrast: {} Hue: {}".format(
            #         int(self.manager.vid.get(cv2.CAP_PROP_BRIGHTNESS)),
            #         int(self.manager.vid.get(cv2.CAP_PROP_SATURATION)),
            #         int(self.manager.vid.get(cv2.CAP_PROP_CONTRAST)),
            #         int(self.manager.vid.get(cv2.CAP_PROP_HUE)),
            #     )
            # )

            # for i in range(5):
            #     self.manager.vid.read()

            self.manager.takeScreenshot()
        except Exception as e:
            errors.append(str(e))
            pass

        if len(errors) == 0:
            return {"status": "ok"}
        else:
            error_string = ",".join(errors)
            return {"status": "error", "error": error_string}

    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.expose
    def update_LED_config(self):
        input_json = cherrypy.request.json
        pixelcount_left = self.manager.current_extension.pixelsLeft
        pixelcount_right = self.manager.current_extension.pixelsRight
        pixelcount_top = self.manager.current_extension.pixelsTop
        pixelcount_bottom = self.manager.current_extension.pixelsBottom
        pixel_darkthreshold = self.manager.current_extension.darkThreshhold

        configChange = False

        errors = []
        if "darkthreshhold" in input_json:
            try:

                dt = int(input_json["darkthreshhold"])
                if dt != pixel_darkthreshold:
                    configChange = True
                    pixel_darkthreshold = dt
            except Exception as e:
                errors.append(str(e))
                pass  # whatever, you are doing bad things with input

        if "pixelcount_left" in input_json:
            try:
                led_input_count = int(input_json["pixelcount_left"])
                if led_input_count != pixelcount_left:
                    configChange = True
                    pixelcount_left = led_input_count
            except Exception as e:
                errors.append(str(e))
                pass  # whatever, you are doing bad things with input

        if "pixelcount_right" in input_json:
            try:
                led_input_count = int(input_json["pixelcount_right"])
                if led_input_count != pixelcount_right:
                    configChange = True
                    pixelcount_right = led_input_count
            except Exception as e:
                errors.append(str(e))
                pass  # whatever, you are doing bad things with input

        if "pixelcount_top" in input_json:
            try:
                led_input_count = int(input_json["pixelcount_top"])
                if led_input_count != pixelcount_top:
                    configChange = True
                    pixelcount_top = led_input_count
            except Exception as e:
                errors.append(str(e))
                pass  # whatever, you are doing bad things with input

        if "pixelcount_bottom" in input_json:
            try:
                led_input_count = int(input_json["pixelcount_bottom"])
                if led_input_count != pixelcount_bottom:
                    configChange = True
                    pixelcount_bottom = led_input_count
            except Exception as e:
                errors.append(str(e))
                pass  # whatever, you are doing bad things with input

        pixelcount_total = (
            pixelcount_left + pixelcount_right + pixelcount_top + pixelcount_bottom
        )

        try:
            self.manager.current_extension.pixelsCount = pixelcount_total
            self.manager.current_extension.pixelsLeft = pixelcount_left
            self.manager.current_extension.pixelsRight = pixelcount_right
            self.manager.current_extension.pixelsTop = pixelcount_top
            self.manager.current_extension.pixelsBottom = pixelcount_bottom
            self.manager.current_extension.setup()
            self.manager.current_extension.visualise()
        except Exception as e:
            errors.append(str(e))

        if "save" in input_json:
            try:
                self.manager.config.set(
                    "AURORA", "AURORA_PIXELCOUNT_LEFT", str(pixelcount_left)
                )
                self.manager.config.set(
                    "AURORA", "AURORA_PIXELCOUNT_RIGHT", str(pixelcount_right)
                )
                self.manager.config.set(
                    "AURORA", "AURORA_PIXELCOUNT_TOP", str(pixelcount_top)
                )
                self.manager.config.set(
                    "AURORA", "AURORA_PIXELCOUNT_BOTTOM", str(pixelcount_bottom)
                )
                self.manager.config.set(
                    "AURORA", "AURORA_PIXELCOUNT_TOTAL", str(pixelcount_total)
                )
                self.manager.config.set(
                    "AURORA", "AURORA_DARKTHRESHOLD", str(pixel_darkthreshold)
                )
                self.manager.config.set("GENERAL", "configured", "True")
                self.manager.saveConfig()
                self.manager.addMessage("Saved config!")
            except Exception as e:
                logging.error(str(e))
                errors.append(str(e))

        if len(errors) == 0:
            return {"status": "ok"}
        else:
            error_string = ",".join(errors)
            return {"status": "error", "error": error_string}

    @cherrypy.tools.json_out()
    @cherrypy.expose
    def get_config(self):
        """Get current Aurora configuration settings"""
        try:
            config_data = {
                "hdmi": {
                    "brightness": self.manager.config.getint("HDMI", "HDMI_BRIGHTNESS"),
                    "saturation": self.manager.config.getint("HDMI", "HDMI_SATURATION"),
                    "contrast": self.manager.config.getint("HDMI", "HDMI_CONTRAST"),
                    "hue": self.manager.config.getint("HDMI", "HDMI_HUE")
                },
                "aurora": {
                    "gamma": self.manager.config.getfloat("AURORA", "AURORA_GAMMA"),
                    "dark_threshold": self.manager.config.getint("AURORA", "AURORA_DARKTHRESHOLD"),
                    "pixel_count_total": self.manager.config.getint("AURORA", "AURORA_PIXELCOUNT_TOTAL"),
                    "pixel_count_left": self.manager.config.getint("AURORA", "AURORA_PIXELCOUNT_LEFT"),
                    "pixel_count_right": self.manager.config.getint("AURORA", "AURORA_PIXELCOUNT_RIGHT"),
                    "pixel_count_top": self.manager.config.getint("AURORA", "AURORA_PIXELCOUNT_TOP"),
                    "pixel_count_bottom": self.manager.config.getint("AURORA", "AURORA_PIXELCOUNT_BOTTOM")
                },
                "general": {
                    "enabled": self.manager.config.getboolean("GENERAL", "enabled"),
                    "configured": self.manager.config.getboolean("GENERAL", "configured")
                }
            }
            return {"status": "success", "config": config_data}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.expose
    def update_aurora_config(self):
        """Update Aurora configuration settings (brightness, contrast, gamma, etc.)"""
        input_json = cherrypy.request.json
        errors = []
        updated_settings = []
        
        try:
            # HDMI Settings
            if "brightness" in input_json:
                try:
                    brightness = int(input_json["brightness"])
                    self.manager.vid.set(cv2.CAP_PROP_BRIGHTNESS, brightness)
                    self.manager.config.set("HDMI", "HDMI_BRIGHTNESS", str(brightness))
                    updated_settings.append(f"brightness={brightness}")
                except Exception as e:
                    errors.append(f"brightness: {str(e)}")
            
            if "saturation" in input_json:
                try:
                    saturation = int(input_json["saturation"])
                    self.manager.vid.set(cv2.CAP_PROP_SATURATION, saturation)
                    self.manager.config.set("HDMI", "HDMI_SATURATION", str(saturation))
                    updated_settings.append(f"saturation={saturation}")
                except Exception as e:
                    errors.append(f"saturation: {str(e)}")
            
            if "contrast" in input_json:
                try:
                    contrast = int(input_json["contrast"])
                    self.manager.vid.set(cv2.CAP_PROP_CONTRAST, contrast)
                    self.manager.config.set("HDMI", "HDMI_CONTRAST", str(contrast))
                    updated_settings.append(f"contrast={contrast}")
                except Exception as e:
                    errors.append(f"contrast: {str(e)}")
            
            if "hue" in input_json:
                try:
                    hue = int(input_json["hue"])
                    self.manager.vid.set(cv2.CAP_PROP_HUE, hue)
                    self.manager.config.set("HDMI", "HDMI_HUE", str(hue))
                    updated_settings.append(f"hue={hue}")
                except Exception as e:
                    errors.append(f"hue: {str(e)}")
            
            # Aurora Settings
            if "gamma" in input_json:
                try:
                    gamma = float(input_json["gamma"])
                    self.manager.current_extension.gamma = gamma
                    self.manager.config.set("AURORA", "AURORA_GAMMA", str(gamma))
                    updated_settings.append(f"gamma={gamma}")
                except Exception as e:
                    errors.append(f"gamma: {str(e)}")
            
            if "dark_threshold" in input_json:
                try:
                    dark_threshold = int(input_json["dark_threshold"])
                    self.manager.current_extension.darkThreshhold = dark_threshold
                    self.manager.config.set("AURORA", "AURORA_DARKTHRESHOLD", str(dark_threshold))
                    updated_settings.append(f"dark_threshold={dark_threshold}")
                except Exception as e:
                    errors.append(f"dark_threshold: {str(e)}")
            
            # Save config if any settings were updated
            if len(updated_settings) > 0:
                self.manager.saveConfig()
            
            if len(errors) == 0:
                return {
                    "status": "success",
                    "message": f"Updated: {', '.join(updated_settings)}"
                }
            else:
                return {
                    "status": "partial",
                    "updated": updated_settings,
                    "errors": errors
                }
        
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    @cherrypy.expose
    def update_extension(self):
        input_json = cherrypy.request.json
        if "extension_name" in input_json:
            extension_name = input_json["extension_name"]
            self.manager.setCurrentExtension(extension_name)

        return {"status": "ok"}

    @cherrypy.tools.json_out()
    @cherrypy.expose
    def screenshot(self):
        self.manager.takeScreenshot()
        self.manager.makePixelImage()

        if self.manager.current_extension != False:
            return {"status": "ok"}
        else:
            return {
                "status": "error",
                "error": "Could not take screenshot and build pixel image",
            }

    @cherrypy.expose
    def load_screenshot(self, **params):
        screenshot_path = self.manager.screenshot_path
        # Its not enabled, it doesnt use HDMI or its got a 1x1 image (ie nothing on)
        if (
            self.manager.enabled == False
            or self.manager.current_extension.noHDMI == True
            or (
                self.manager.current_extension.vid_h == 1
                or self.manager.current_extension.vid_w == 1
            )
        ):
            screenshot_path = os.getcwd() + "/webserver/static/img/emptyimage.jpg"
        try:
            f = open(screenshot_path, "rb")
            contents = f.read()
            f.close()
            return contents
        except Exception as e:
            self.manager.log(
                "Error loading image {}: Err: {}".format(
                    self.manager.screenshot_path, str(e)
                )
            )
            return False

    @cherrypy.expose
    def load_pixel_image(self, **params):
        try:
            f = open(self.manager.pixel_image_path, "rb")
            contents = f.read()
            f.close()
            return contents
        except Exception as e:
            self.manager.log(
                "Error loading image {}: Err: {}".format(
                    self.manager.pixel_image_path, str(e)
                )
            )
            return False


if __name__ == "__main__":

    AuroraManager = AuroraManager()

    if AuroraManager.config.getboolean("WEBSERVER", "enabled") == True:

        conf = {
            "/": {
                "tools.sessions.on": True,
                "tools.staticdir.root": os.path.abspath(os.getcwd()),
            },
            "/assets": {
                "tools.staticdir.on": True,
                "tools.staticdir.dir": "./webserver/static",
            },
            "/favicon.ico": {
                "tools.staticfile.on": True,
                "tools.staticfile.filename": os.path.abspath(os.getcwd())
                + "/webserver/static/favicon/favicon.ico",
            },
        }

        cherrypy.config.update(
            {"log.screen": False, "log.access_file": "", "log.error_file": ""}
        )
        cherrypy.config.update(
            {
                "server.socket_port": AuroraManager.config.getint(
                    "WEBSERVER", "server_port"
                )
            }
        )
        cherrypy.config.update(
            {"server.socket_host": AuroraManager.config.get("WEBSERVER", "listen_host")}
        )
        cherrypy.config.update({"engine.autoreload.on": False})

        cherrypy.tree.mount(Aurora_Webserver(AuroraManager), "/", conf)

        cherrypy.engine.start()

    while True:
        AuroraManager.loop()
        time.sleep(0.001)

    # do other work
