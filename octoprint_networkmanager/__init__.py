# coding=utf-8
from __future__ import absolute_import

__author__ = "Pim Rutgers <p.rutgers@lpfrg.com>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2014 The OctoPrint Project - Released under terms of the AGPLv3 License"

import octoprint.plugin
import sys

from octoprint.server import admin_permission
from flask import jsonify, make_response, request
from .nmcli import Nmcli


class NetworkManagerPlugin(octoprint.plugin.SettingsPlugin,
                           octoprint.plugin.AssetPlugin,
                           octoprint.plugin.TemplatePlugin,
                           octoprint.plugin.BlueprintPlugin):


    ##~~ Init
    def __init__(self):
        self.ncmli = None
        self.mocking = sys.platform == "win32" or sys.platform == "darwin"

    def initialize(self):
        self.nmcli = Nmcli(self.mocking)

    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return dict(
            timeout=10
        )

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return dict(
            js=["js/networkmanager.js"],
            css=["css/networkmanager.css"],
            less=["less/networkmanager.less"]
        )


    ##~~ TemplatePlugin mixin

    def get_template_configs(self):
        return [
            dict(type="settings", name="NetworkManager")
        ]

    ##~~ BlueprintPlugin mixin

    @octoprint.plugin.BlueprintPlugin.route("/", methods=["GET"])
    def get_status(self):
        status = None
        wifis = []

        try:
            status = self._get_status()
            if status and "wifi" in status and status["wifi"]["enabled"]:
                wifis = self._get_wifi_list()  
        except Exception as e:
            self._logger.exception(e.message)
            return jsonify(dict(error=e.message))

        return jsonify(dict(
            wifis=wifis,
            status=status
        ))

    @octoprint.plugin.BlueprintPlugin.route("/connection_details/<string:id>", methods=["GET"])
    def get_connection_details(self, id):

        # Override id with an interface name
        if id == "ethernet":
            id = "eth0"
        elif id == "wifi":
            id = "wlan0"

        connection_details = self._get_connection_details(id)
        return make_response(jsonify(details=connection_details), 200)

    @octoprint.plugin.BlueprintPlugin.route("/connection_details/<string:id>", methods=["POST"])
    def set_connection_details(self, id):
        # Override id with an interface name
        if id == "ethernet":
            id = "eth0"
        elif id == "wifi":
            id = "wlan0"

        connection_details = request.json["details"]
        interface = request.json["interface"]
        if self._set_connection_details(id, interface, connection_details):
            return make_response(jsonify(), 200)
        else:
            return make_response(jsonify(), 400)


    @octoprint.plugin.BlueprintPlugin.route("/wifi/enable", methods=["POST"])
    def enable_wifi(self):
        self._set_wifi_enabled(True)
        self._logger.info("Wifi radio enabled")
        return jsonify()

    @octoprint.plugin.BlueprintPlugin.route("/wifi/disable", methods=["POST"])
    def disable_wifi(self):
        self._set_wifi_enabled(False)
        self._logger.info("Wifi radio disabled")
        return jsonify()

    @octoprint.plugin.BlueprintPlugin.route("/wifi/scan", methods=["POST"])
    def scan_wifi(self):
        wifis = self._get_wifi_list(force=True)
        self._logger.info("Wifi scan initiated")
        return jsonify(dict(wifis=wifis))

    @octoprint.plugin.BlueprintPlugin.route("/wifi/configure", methods=["POST"])
    def configure_wifi(self):
        if not admin_permission.can():
            return make_response(jsonify({ "message": "Insufficient rights"}, 403))

        data = request.json
        if "psk" in data:
            self._logger.info("Configuring wifi {ssid} and psk...".format(**data))
        else:
            self._logger.info("Configuring wifi {ssid}...".format(**data))
            data['psk'] = None

        return self.nmcli.add_wifi_connection(ssid=data["ssid"], psk=data["psk"])

    @octoprint.plugin.BlueprintPlugin.route("/wifi/disconnect", methods=["POST"])
    def disconnect_wifi(self):
        if not admin_permission.can():
            return make_response(jsonify({ "message": "Insufficient rights"}, 403))

        return self._disconnect_wifi()

    @octoprint.plugin.BlueprintPlugin.route("/wifi/reset", methods=["POST"])
    def reset_wifi(self):
        if not admin_permission.can():
            return make_response(jsonify({ "message": "Insufficient rights"}, 403))
        self._reset_wifi()
        return make_response(jsonify(), 200)

    ##~~ Private functions to retrieve info

    def _get_status(self):
         return self.nmcli.get_status()

    def _get_connection_details(self, uuid):
        return self.nmcli.get_configured_connection_details(uuid)

    def _set_connection_details(self, uuid, interface, new_settings):
        return self.nmcli.set_configured_connection_details(interface, new_settings, uuid)
        
    def _get_wifi_list(self, force=False):
        result = []

        content = self.nmcli.scan_wifi(force=force)
        if content:
            for wifi in content:
                result.append({ "ssid": wifi["ssid"], 
                               "signal": wifi["signal"], 
                               "security": wifi["security"] if "security" in wifi else None,
                               "connectionUuid": wifi["connection_uuid"]
                               })
        
        return result

    def _get_configured_connections(self):
        content = self.nmcli.get_configured_connections()
        result = []

        for connection in content:
            result.append(dict(name=connection["name"], type=connection["type"], uuid=connection["uuid"]))
        self._logger.info(result)
        return result

    def _disconnect_wifi(self):
        returncode, output = self.nmcli.disconnect_interface('wifi')
        if returncode != 0:
            return make_response(jsonify({"message":"An error occured while disconnecting: {output}".format(output=output)}), 400)
        return make_response(jsonify({"message":"Succesful disconnect: {output}".format(output=output) }), 200)


    def _delete_configured_connection(self, uuid):
        return self.nmcli.delete_configured_connection(uuid)

    def _set_wifi_enabled(self, enabled):
        self.nmcli.set_wifi_radio(enabled)

    def _reset_wifi(self):
        self.nmcli.reset_wifi()
        self.nmcli.rescan_wifi()

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
        # for details.
        return dict(
            networkmanager=dict(
                displayName="Networkmanager Plugin",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="Booli",
                repo="OctoPrint-NetworkManager",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/Booli/OctoPrint-NetworkManager/archive/{target_version}.zip"
            )
        )


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "NetworkManager Plugin"

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = NetworkManagerPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
