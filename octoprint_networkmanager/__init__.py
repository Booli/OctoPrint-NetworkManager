# coding=utf-8
from __future__ import absolute_import

__author__ = "Pim Rutgers <p.rutgers@lpfrg.com>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2014 The OctoPrint Project - Released under terms of the AGPLv3 License"

import octoprint.plugin
import sys

from octoprint.server import admin_permission
from flask import jsonify, make_response
from .nmcli import Nmcli


class NetworkManagerPlugin(octoprint.plugin.SettingsPlugin,
                           octoprint.plugin.AssetPlugin,
                           octoprint.plugin.TemplatePlugin,
                           octoprint.plugin.SimpleApiPlugin):


    ##~~ Init
    def __init__(self):
        self.ncmli = None

    def initialize(self):
        self.nmcli = Nmcli()


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

    ##~~ SimpleApiPlugin mixin

    def get_api_commands(self):
        return dict(
            scan_wifi=[],
            configure_wifi=["ssid"],
            disconnect_wifi=[],
            reset=[]
        )

    def is_api_adminonly(self):
        return False

    def on_api_get(self, request):
        try:
            status = self._get_status()
            if status:
                wifis = self._get_wifi_list()  
            else:
                wifis = []
        except Exception as e:
            self._logger.warning(e.message)
            return jsonify(dict(error=e.message))


        return jsonify(dict(
            wifis=wifis,
            status=status
        ))

    def on_api_command(self, command, data):
        self._logger.info("Command {command} with {data} ".format(command=command, data=data))
        if command == "scan_wifi":
            wifis = self._get_wifi_list(force=True)
            self._logger.info("Wifi scan initiated")
            return jsonify(dict(wifis=wifis))

        # any commands processed after this check require admin permissions
        if not admin_permission.can():
            return make_response("Insufficient rights", 403)

        if command == "configure_wifi":
            if "psk" in data:
                self._logger.info("Configuring wifi {ssid} and psk...".format(**data))
            else:
                self._logger.info("Configuring wifi {ssid}...".format(**data))
                data['psk'] = None

            return self._configure_and_select_wifi(ssid=data["ssid"], psk=data["psk"])

        elif command == "disconnect_wifi":
            return self._disconnect_wifi()

        elif command == "reset":
            self._reset()



    ##~~ Private functions to retrieve info

    def _get_status(self):
        if sys.platform == "win32" or sys.platform == "darwin":
            return dict(connection = dict(wifi = True, ethernet = True), ip = dict(wifi = "127.0.0.1", ethernet = "127.0.0.1"), wifi = dict(ssid = None, signal = None, security = None))
        else:
            return self.nmcli.get_status()

    def _get_wifi_list(self, force=False):
        result = []

        if sys.platform == "win32" or sys.platform == "darwin":
            for i in range(0,20):
                result.append(dict(ssid="Leapfrog%d" % (i+1), signal=(20-i)*5, security=(i%2==0)))
        else:
            content = self.nmcli.scan_wifi(force=force)
            
            for wifi in content:
                result.append(dict(ssid=wifi["ssid"], signal=wifi["signal"], security=wifi["security"] if "security" in wifi else None))
        
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
        if (returncode != 0):
            return make_response("An error occured while disconnecting: {output}".format(output=output), 400)
        return make_response("Succesful disconnect: {output}".format(output=output), 200)


    def _delete_configured_connection(self, uuid):
        return self.nmcli.delete_configured_connection(uuid)

    def _configure_and_select_wifi(self, ssid, psk):
        returncode, output = self.nmcli.connect_wifi(ssid, psk)
        if (returncode != 0):
            return make_response("An error occured with text{output}".format(output=output), 400)
        return make_response("Succesful connection: {output}".format(output=output), 200)


    def _reset(self):
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

