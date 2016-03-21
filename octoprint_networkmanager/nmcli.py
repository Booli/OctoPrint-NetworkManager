# coding=utf-8
import subprocess
import logging
import sys
import os
import pprint #REMOVE IN CLEAN
import re

from time import sleep
from pipes import quote #CHECK if used

class Nmcli:

	def __init__(self):

		logging.basicConfig(level=logging.INFO)
		self.logger = logging.getLogger(__name__)
		def exception_logger(exc_type, exc_value, exc_tb):
		    self.logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
		sys.excepthook = exception_logger

		try: 
			self.check_nmcli_version()
		except ValueError as err:
			self.logger.error("Nmcli incorrect version: {version}. Must be higher than 0.9.9.0".format(version=err.args[0]))
			raise Exception


	def _send_command(self, command):
		"""
		Sends command to ncmli with subprocess. 
		Returns (0, output) of the command if succeeded, returns the exit code and output when errors
		"""

		command[:0] = ["nmcli"]
		try:
			result = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			output , error = result.communicate()

			# Error detected, return exit code and output + error
			# Output is returned because nmcli reports error states in output and not in error ><
			if result.returncode != 0:
				self.logger.warn("Error while trying execute command {command}: output: {output}".format(command=command, output=output, error=error))
				#raise subprocess.CalledProcessError(result.returncode, command, output)
				#An error occured, return the return code and one string of the 
				return result.returncode, output

			return result.returncode, output
		except OSError as e:
			self.logger.warn("OSError: {error}, file: {filename}, error: {message}".format(error=e.errno, file=e.filename, message=e.strerror))



	def scan_wifi(self, force=False):
		"""
		Scans wifi acces points and returns list of cells

		TODO: Add rescan option
		"""

		#Force rescan if required
		if force:
			self.rescan_wifi()

		command = ["-t", "-f", "SSID, SIGNAL, SECURITY", "dev", "wifi", "list"]
		# Keys to map the out put to, same as fields describes in the command
		keys = ["ssid", "signal", "security"]

		# Parse command
		parse = self._sanatize_parse(self._send_command(command))

		# Map output to dict with keys[]
		cells = self._map_parse(parse, keys)

		# Convert signal to int
		for cell in cells:
			cell["signal"] = int(cell["signal"])

		# Filter duplicates and return keep only highest signal entry
		cells = self._filter_cells(cells)
		return cells

	def rescan_wifi(self):
		"""
		Rescans the wifi APS
		"""
		command = ["dev", "wifi", "rescan"]

		print("Rescan")

		return self._send_command(command)

	def get_status(self):
		"""
		Return status of connections.
		Returns:
			connection:
				wifi: True/False
				ethernet: True/False
			wifi:
				#Cell object
				ssid:  
				signal:
				type:
		"""
		result = []

		status = {}
		interfaces = self.get_interfaces()
		wifis = self.scan_wifi()

		for interface in interfaces:
			status[interface] = self.is_device_active(interfaces[interface])

		active = {}
		if status["wifi"]:
			connections = self.get_active_connections()
			for connection in connections:
				if connection["device"] == interfaces["wifi"]:
					name = connection["name"]
			for wifi in wifis:
				if wifi["ssid"] == name:
					active = wifi

		return dict(connection=status, wifi=active)

	def get_configured_connections(self):
		"""
		Get all configured connections for wireless and wired configurations
		"""
		command = ["-t", "-f", "name, uuid, type", "c"]
		keys =["name", "uuid", "type"]
		parse = self._sanatize_parse(self._send_command(command))

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
			pprint.pprint("An error occurred deleting a connection") 
			return False
		else:
			pprint.pprint("Connection with uuid: {uuid} deleted".format(uuid=uuid))
			return True

	def clear_configured_connection(self, ssid):
		"""
		Delete all wifi configurations with ssid in name. Might be needed after multiple of the same connetions are created
		"""
		for connection in self.get_configured_connections():
			pprint.pprint(connection)
			if ssid in connection["name"]:
				self.delete_configured_connection(connection["uuid"])


	def disconnect_interface(self, interface):
		"""
		Disconnect either 'wifi' or 'ethernet'. Uses disconnect_device and is_device_active to disconnect an interface.__init__.py
		"""
		interfaces = self.get_interfaces()

		device = interfaces[interface]

		return self._disconnect_device(device)

	def _disconnect_device(self, device):
		""" 
		Disconnect wifi selected. This uses 'nmcli dev disconnect interface' since thats is the recommended method. 
		Using 'nmcli con down SSID' will bring the connection down but will not make it auto connect on the interface any more.
		"""

		if self.is_device_active(device):
				command = ["dev", "disconnect", device]
				return self._send_command(command)
		return False

	def is_wifi_configured(self):
		"""
		Checks if wifi is configured on the machine
		"""

		command = ["-t", "-f", "type", "dev"]
		devices = self._sanatize_parse(self._send_command(command))

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
		devices = self._sanatize_parse(self._send_command(command))

		for elem in devices:
			if device in elem:
				if elem[1] == "connected":
					pprint.pprint("Device is connected, return True")
					return True
				pprint.pprint("Device seems to not be connected return False")
				return False

		# We didnt find any device matching, return False also
		return False 

	def get_active_connections(self):
		"""
		Get active connections

		returns a dict of active connections with key:value, interace: cell
		"""
		command = ["-t", "-f", "NAME, DEVICE, TYPE", "c", "show", "--active"]
		keys = ["name", "device", "type"]

		parse = self._sanatize_parse(self._send_command(command))

		connections = self._map_parse(parse, keys)

		return connections


	def connect_wifi(self, ssid, psk=None):
		"""
		Connect to wifi AP. Should check if configuration of SSID already exists and use that or create a new entry
		"""

		#C Check if connection alredy is configured

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
		pprint.pprint("Trying to create new connection")
		
		return self._send_command(command)


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
		Return list of interfaces with key: value, name: interface

		For example ['ethernet': 'eth0', 'wifi': 'wlan0']
		"""
		command = ["-t","-f","type, device", "dev"]

		parse = self._sanatize_parse(self._send_command(command))

		interfaces = dict((x[0], x[1]) for x in parse)

		return interfaces

	def _map_parse(self, parse, keys):
		cells = []
		for elem in parse:
			cell = dict(zip(keys, elem))
			cells.append(cell)
		return cells

	def _sanatize_parse(self, output):
		"""
		Sanatizes the parse. using the -t command of nmli, ':' is used to split
		"""
		#Check if command executed correctly[returncode 0], otherwise return nothing
		if not output[0]:
			parse = output[1].splitlines()
			parse_split = []
			for line in parse:
				line = line.split(":")
				parse_split.append(line)
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
		response = self._send_command(["--version"])
		parts = response[1].split()
		ver = parts[-1]
		compare = self.vercmp(ver, "0.9.9.0")
		if compare >= 0:
		    return True
		else: 
			raise ValueError(ver)
			return False

	def vercmp(self, actual, test):
	    def normalize(v):
	        return [int(x) for x in re.sub(r'(\.0+)*$', '', v).split(".")]
	    return cmp(normalize(actual), normalize(test))
