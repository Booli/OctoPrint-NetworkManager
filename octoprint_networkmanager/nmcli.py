# coding=utf-8
import subprocess
import logging
import re

from time import sleep

class Nmcli(object):

    def __init__(self, mocking=False):

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("octoprint.plugins.networkmanager.nmcli")
        self.mocking = mocking

        try:
            self.check_nmcli_version()
        except ValueError as err:
            self.logger.error("Nmcli incorrect version: {version}. Must be higher than 0.9.9.0".format(version=err.args[0]))
            raise Exception

        self.ip_regex = re.compile('(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)')

    def _send_command(self, command):
        """
        Sends command to ncmli with subprocess.
        Returns (0, output) of the command if succeeded, returns the exit code and output when errors
        """

        self._log_command(command)

        if self.mocking:
            return 1, None

        command[:0] = ["nmcli"]
        try:
            result = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            output, _ = result.communicate()

            # Error detected, return exit code and output + error
            # Output is returned because nmcli reports error states in output and not in error ><
            if result.returncode != 0:
                self.logger.warn("Error while trying execute command {command}: output: {output}".format(command=command, output=output))

            self._log_command_output(result.returncode, output)

            return result.returncode, output
        except OSError as err:
            self.logger.warn("OSError: {error}, file: {filename}, error: {message}".format(error=err.errno, filename=err.filename, message=err.strerror))
            return 1, err.strerror

    def scan_wifi(self, force=False):
        """
        Scans wifi acces points and returns list of cells

        TODO: Add rescan option
        """

        #Force rescan if required
        if force:
            self.rescan_wifi()

        command = ["-t", "-f", "ssid, signal, security", "dev", "wifi", "list"]
        # Keys to map the out put to, same as fields describes in the command
        keys = ["ssid", "signal", "security"]

        # Parse command
        returncode, output = self._send_command(command)

        if self.mocking:
            result = []
            for i in range(0, 20):
                result.append(dict(ssid="Leapfrog%d" % (i+1), signal=(20-i)*5, security=(i%2 == 0), connection_uuid=None))
            return result

        if returncode != 0:
            return None

        if not output:
            return None

        parse = self._sanatize_parse(output)

        # Map output to dict with keys[]
        cells = self._map_parse(parse, keys)

        configured_connections = self.get_configured_connections()

        for cell in cells:
            # Ensure signal is an int
            cell["signal"] = int(cell["signal"])

            # Extend cells with connection properties
            cell["connection_uuid"] = None
            if configured_connections:
                for connection in configured_connections:
                    if cell["ssid"] == connection["name"]:
                        cell["connection_uuid"] = connection["uuid"]
                        break

        # Filter duplicates and return keep only highest signal entry
        cells = self._filter_cells(cells)
        return cells

    def rescan_wifi(self):
        """
        Rescans the wifi APS
        """
        command = ["dev", "wifi", "rescan"]

        return self._send_command(command)

    def get_status(self):
        """
        Return status of connections.
        Returns:
            ethernet:
                connection_uuid: string
                connected: bool
                ip: string
            wifi:
                connection_uuid: string
                connected: bool
                ip: string
                ssid: string
                enabled: bool
        """
        if self.mocking:
            return {
                "ethernet" : {
                    "connection_uuid" : "1234",
                    "connected" : True,
                    "ip" : "127.0.0.1"
                   },
                "wifi" : {
                    "connection_uuid" : "5678",
                    "connected" : True,
                    "ssid" : "Leapfrog2",
                    "ip" : "127.0.0.2",
                    "enabled": True
                    } 
                }

        result = {}

        interfaces = self.get_interfaces()
        if interfaces:
            for key, interface in interfaces.iteritems():
                props = {}

                if interface["connection_uuid"]:
                    details = self.get_configured_connection_details(interface["connection_uuid"])
                    props["ssid"] = details["ssid"] if "ssid" in details else None
                    props["ip"] = details["ipv4"]["ip"]

                # Copy properties from interface
                props["connection_uuid"] = interface["connection_uuid"]
                props["connected"] = interface["connected"]
                props["enabled"] = interface["enabled"]
                props["mac_address"] = interface["mac_address"]

                result[key] = props

        return result

    def get_configured_connections(self):
        """
        Get all configured connections for wireless and wired configurations
        """
        command = ["-t", "-f", "name, uuid, type", "c"]
        keys = ["name", "uuid", "type"]

        returncode, output = self._send_command(command)

        if returncode != 0:
            return None

        parse = self._sanatize_parse(output)

        configured_connections = self._map_parse(parse, keys)

        # Sanatize the connection name a bit
        for connection in configured_connections:
            if "wireless" in connection["type"]:
                connection["type"] = "Wireless"
            if "ethernet" in connection["type"]:
                connection["type"] = "Wired"

        return configured_connections

    def delete_configured_connection(self, uuid):
        """
        Deletes a configured connection. Takes uuid as input
        """

        command = ["con", "delete", "uuid", uuid]
        
        result = self._send_command(command)

        if result[0]:
            self.logger.warn("An error occurred deleting a connection")
            return False
        else:
            self.logger.info("Connection with uuid: {uuid} deleted".format(uuid=uuid))
            return True


    def get_configured_connection_details(self, uuid):
        command = ["-t", "con", "show", uuid]

        if self.mocking:
            if uuid == "1234":
                # Ethernet
                details = {
                    "connection.type": "802-3-ethernet",
                    "802-3-ethernet.mac-address": "12:34:56:WI:RE:D0:00",
                    "ipv4.method" : "manual",
                    "ipv4.addresses" : "ip = 127.0.0.1/24",
                    "ipv4.routes" : "dst = 192.168.0.1/24",
                    "ipv4.dns" : "1.1.1.1 2.2.2.2"
                }
            elif uuid == "5678":
                # Wifi
                details = {
                    "connection.type": "802-11-wireless",
                    "802-11-wireless.ssid": "Leapfrog2",
                    "802-11-wireless.mac-address": "12:34:56:WI:RE:LE:SS",
                    "ipv4.method" : "auto",
                    "ipv4.addresses" : "ip = 127.0.0.2/24",
                    "ipv4.routes" : "dst = 192.168.0.1/24",
                    "ipv4.dns" : "8.8.8.8 4.4.4.4"
                    }
        else:
            returncode, output = self._send_command(command)
            if returncode == 0:
                details = self._sanatize_parse_key_value(output)
            else:
                return None

        result = {
            "uuid": uuid,
            "name": self._get_connection_name(details),
            "isWireless": "wireless" in details["connection.type"],
            "ssid": self._get_connection_ssid(details),
            "psk": "",
            "ipv4": {
                "method": details["ipv4.method"],
                "ip": self._get_ipv4_address(details["IP4.ADDRESS[1]"]),
                "gateway": self._get_gateway_ipv4_address(details["ipv4.routes"]),
                "dns": details["ipv4.dns"].split()
                }
            }

        return result

    def set_configured_connection_details(self, interface, connection_details, uuid = None):
                
        new_settings = {}

        if not "psk" in connection_details:
            connection_details["psk"] = None

        if uuid:
            # Check if UUID exists, if not, create a new connection
            returncode, _ = self._send_command(["-t", "con", "show", uuid])

            if returncode == 10: # Connection does not exist
                if interface == "wifi":
                    uuid = self.add_wifi_connection(connection_details["ssid"], connection_details["psk"])

                    if not uuid:
                        self.logger.error("Could not add wifi connection")
                        return False
                else:
                    self.logger.error("Cannot add connection for interface {0}. Only wifi is supported.".format(interface))
                    return False
        else:
            # If no UUID was provided, create a new connection
            if interface == "wifi":
                uuid = self.add_wifi_connection(connection_details["ssid"], connection_details["psk"])

                if not uuid:
                    self.logger.error("Could not add wifi connection")
                    return False
            else:
                self.logger.error("Cannot add connection for interface {0}. Only wifi is supported.".format(interface))
                return False

        command = ["-t", "con", "modify", uuid ]

        if connection_details["isWireless"]:
            if "psk" in connection_details and connection_details["psk"]:
                new_settings["802-11-wireless-security.psk"] = connection_details["psk"]

        new_settings["ipv4.method"] = connection_details["ipv4"]["method"]

        if new_settings["ipv4.method"] == "manual":
            new_settings["ipv4.addresses"] = connection_details["ipv4"]["ip"] if connection_details["ipv4"]["ip"] else ""
            new_settings["ipv4.routes"] = connection_details["ipv4"]["gateway"] if connection_details["ipv4"]["gateway"] else ""
            new_settings["ipv4.dns"] = " ".join(connection_details["ipv4"]["dns"]) if connection_details["ipv4"]["dns"] else ""

        for setting, value in new_settings.iteritems():
            command.append(setting)
            command.append(value)


        # Save changes to connection
        exitcode, _ = self._send_command(command)

        # Apply changes
        command = [ "con", "up", uuid ]
        exitcode, _ = self._send_command(command)

        return exitcode == 0

    def clear_configured_connection(self, ssid):
        """
        Delete all wifi configurations with ssid in name. Might be needed after multiple of the same connetions are created
        """
        for connection in self.get_configured_connections():
            if ssid in connection["name"]:
                self.logger.info("Deleting connection {0}".format(connection["name"])) 
                self.delete_configured_connection(connection["uuid"])


    def set_wifi_radio(self, enabled):
        """
        Sets the wifi radio on or off
        """
        command = ["radio", "wifi", "on" if enabled else "off"]
        returncode, output = self._send_command(command)

        return returncode == 0

    def disconnect_interface(self, interface):
        """
        Disconnect either 'wifi' or 'ethernet'. Uses disconnect_device and is_device_active to disconnect an interface.
        """
        interfaces = self.get_interfaces()

        if interface in interfaces:
            device = interfaces[interface]["device"]
            return self._disconnect_device(device)
        else:
            self.logger.error("Could not find interface {0}".format(interface))


    def connect_interface(self, interface):
        """
        Connect either 'wifi' or 'ethernet'. Uses connect_device and is_device_active to connect an interface.
        """
        interfaces = self.get_interfaces()

        if interface in interfaces:
            device = interfaces[interface]["device"]
            return self._connect_device(device)
        else:
            self.logger.error("Could not find interface {0}".format(interface))

    def _disconnect_device(self, device):
        """
        Disconnect wifi selected. This uses 'nmcli dev disconnect interface' since thats is the recommended method.
        Using 'nmcli con down SSID' will bring the connection down but will not make it auto connect on the interface any more.
        """

        if self.is_device_active(device):
            command = ["dev", "disconnect", device]
            
            return self._send_command(command)
        return (1, "Device not active")

    def _connect_device(self, device):

        if not self.is_device_active(device):
            command = ["dev", "connect", device]

            return self._send_command(command)
        return (1, "Device not active")

    def is_wifi_configured(self):
        """
        Checks if wifi is configured on the machine
        """

        command = ["-t", "-f", "type", "dev"]

        returncode, output = self._send_command(command)

        if returncode != 0:
            return None

        devices = self._sanatize_parse(output)

        for device in devices:
            if "wifi" in device:
                return True
        return False

    def is_device_active(self, device):
        """
        Checks if device(wlan0, eth0, etc) is active
        Returns True if active, falls if not active
        """
        command = ["-t", "-f", "device, state", "device", "status"]

        returncode, output = self._send_command(command)

        if returncode != 0:
            return None

        devices = self._sanatize_parse(output)

        if self.mocking:
            return True

        if devices:
            for elem in devices:
                if elem[0] == device:
                    return elem[1] == "connected"

        # We didnt find any device matching, return False also
        return False

    def get_active_connections(self):
        """
        Get active connections

        returns a dict of active connections with key:value, interace: cell
        """
        command = ["-t", "-f", "NAME, DEVICE, TYPE", "c", "show", "--active"]
        keys = ["name", "device", "type"]

        returncode, output = self._send_command(command)

        if returncode != 0:
            return None

        parse = self._sanatize_parse(output)

        connections = self._map_parse(parse, keys)

        return connections


    def add_wifi_connection(self, ssid, psk=None):
        """
        Connect to wifi AP. Should check if configuration of SSID already exists and use that or create a new entry
        """

        #Check if connection alredy is configured

        configured_connections = self.get_configured_connections()
        for connection in configured_connections:
            if ssid in connection.values():
                # The ssid we are trying to connect to already has a configuration file.
                # Delete it and all it's partial configuration files before trying to set up a new connection
                self.clear_configured_connection(ssid)

        # The connection does not seem to be configured yet, so lets add it
        command = ["dev", "wifi", "connect", ssid]
        if psk:
            command.extend(["password", psk])

        self.logger.info("Trying to create new connection for {0}".format(ssid))
        
        returncode, output = self._send_command(command)

        if returncode == 0:
            # Extract the UUID from the output
            search = re.search("UUID '([a-zA-Z0-9-]*)'", output)
            if search:
                found = search.group(1)
                return found
            else:
                self.logger.error("Could not extract UUID from wifi connect response")
                return None
        else:
            return None

    def reset_wifi(self):
        """
        Resets the wifi by turning it on and off with sleep of 5 seconds
        """
        self._send_command(["radio", "wifi", "off"])
        sleep(5)
        self._send_command(["radio", "wifi", "on"])
        self.logger.info("Wifi reset")

    def get_interfaces(self):
        """
        Return list of interfaces
        For example {'ethernet': { 'device': 'eth0', 'connection_uuid' : '1234-ab-..' }, 'wifi': { 'device': 'wlan0', 'connection_uuid' : '1234-ab-..' }}
        """
        command = ["-t", "-f", "type, device, con-uuid, state", "dev"]

        returncode, output = self._send_command(command)

        if returncode != 0:
            return None

        parse = self._sanatize_parse(output)

        if self.mocking:
            return {
                    'ethernet': {
                        'device': 'eth0',
                        'connection_uuid' : '1234',
                        'enabled': True
                        }, 
                    'wifi': {
                        'device': 'wlan0',
                        'connection_uuid' : '5678',
                        'enabled': True
                        }
                    }

        interfaces = {}

        if parse:
            for x in parse:
                if len(x) != 4:
                    self.logger.warning("Unparsable NMCLI output detected")
                    continue
                if x[0] == "loopback":
                    continue

                # Retrieve mac address
                command = ['-t', '-f', 'GENERAL.HWADDR', 'd', 'show', x[1]]
                returncode, output = self._send_command(command)

                if returncode == 0 and ':' in output:
                    mac_address = output.split(':', 1)[1].strip()
                else:
                    mac_address = None

                # Combine data into nice dicts
                interfaces[x[0]] = { 
                    "device": x[1], 
                    "connection_uuid": x[2] if x[2] != "--" else None,
                    "enabled": x[3] != "unavailable" and x[3] != "unmanaged",
                    "connected": x[3] == "connected",
                    "mac_address":  mac_address
                    }

        return interfaces

    def _get_interface_ip(self, device):
        """
        Get the ip of the connection
        """

        command = ["-t", "-f", "IP4.ADDRESS", "d", "show", device] 

        returncode, output = self._send_command(command)

        if returncode != 0:
            return None

        parse = self._sanatize_parse(output)

        ip = None
        for elem in parse[0]:
            match = self.ip_regex.search(elem)
            if match:
                ip = match.group()

        return ip

    def _map_parse(self, parse, keys):
        cells = []
        if parse:
            for elem in parse:
                cell = dict(zip(keys, elem))
                cells.append(cell)
        return cells

    def _sanatize_parse(self, output):
        """
        Sanatizes the parse. using the -t command of nmli, ':' is used to split
        """
        if output:
            parse = output.splitlines()
            parse_split = []
            for line in parse:
                results = list(self._split_nmcli_output(line))
                parse_split.append(results)
            return parse_split
    
    def _sanatize_parse_key_value(self, output):
        """
        Sanatizes the parse. using the -t command of nmli, ':' is used to split. Returns key-value pairs
        """
        #Check if command executed correctly[returncode 0], otherwise return nothing
        if output:
            parse = output.splitlines()
            parse_split = {}
            for line in parse:
                line = line.split(":", 1)
                if len(line) == 2:
                    parse_split[line[0]] = line[1]
            return parse_split

    def _filter_cells(self, cells):
        """
        Filter cells dictionary to remove duplicates and only keep the entry with the highest signal value
        """
        filtered = {}
        for cell in cells:
            ssid = cell["ssid"]
            if ssid in filtered:
                if cell["signal"] > filtered[ssid]["signal"]:
                    filtered[ssid] = cell
            else:
                filtered[ssid] = cell 

        return filtered.values()

    def check_nmcli_version(self):
        """
        Check the nmcli version value as this wrapper is only compatible with 0.9.9.0 and up.
        """
        exit_code, response = self._send_command(["--version"])
        
        if exit_code == 0:
            parts = response.split()
            ver = parts[-1]
            compare = self.vercmp(ver, "0.9.9.0")
            if compare >= 0:
                return True
            else: 
                raise ValueError(ver)
                return False
        else:
            return False

    def _get_connection_ssid(self, connection_details):
        if "802-11-wireless.ssid" in connection_details:
            return connection_details["802-11-wireless.ssid"]
        else:
            return None

    def _get_connection_name(self, connection_details):
        if "802-11-wireless.ssid" in connection_details:
            return connection_details["802-11-wireless.ssid"]
        else:
            return "Wired"

    def _get_ipv4_address(self, ip_details):
        look_for_start = "ip = "
        look_for_end = "/"

        start_idx = ip_details.find(look_for_start)
        end_idx = ip_details.find(look_for_end, start_idx+len(look_for_start))

        if start_idx > -1 and end_idx > -1:
            return ip_details[start_idx+len(look_for_start):end_idx]

    def _get_gateway_ipv4_address(self, ip_details):
        look_for_start = "dst = "
        look_for_end = "/"

        start_idx = ip_details.find(look_for_start)
        end_idx = ip_details.find(look_for_end, start_idx+len(look_for_start))

        if start_idx > -1 and end_idx > -1:
            return ip_details[start_idx+len(look_for_start):end_idx]

    def _log_command(self, command):
        command_str = " ".join(command)
        self.logger.debug("NMCLI Sending command: {0}".format(command_str))

    def _log_command_output(self, returncode, output):
        self.logger.debug("NMCLI Exitcode: {0} Output: {1}".format(returncode, output))

    def vercmp(self, actual, test):
        def normalize(v):
            return [int(x) for x in re.sub(r'(\.0+)*$', '', v).split(".")]
        return cmp(normalize(actual), normalize(test))

    def _split_nmcli_output(self, line):
        result = []
        for item in self._split_esc(line, ":"):
            result.append(item.replace("\:",":").replace("\\\\", "\\"))

        return result

    def _split_esc(self, string, delimiter):
        """Helper method that allows to split with an escaped character (nmcli escapes the : if needed)"""
        if len(delimiter) != 1:
            raise ValueError('Invalid delimiter: ' + delimiter)
        ln = len(string)
        i = 0
        j = 0
        
        while j < ln:
            if string[j] == '\\':
                if j + 1 >= ln:
                    yield string[i:j]
                    return
                j += 1
            elif string[j] == delimiter:
                yield string[i:j]
                i = j + 1
            j += 1
        yield string[i:j]

