from nmcli import Nmcli, CommandTarget
from random import randint

def is_equal_command(command, compare):
    for i in range(len(compare)):
        if not compare[i] in command:
            return False
    return True

def get_fields_from_command(command):
    last = None
    fields = None
    for i in range(len(command)):
        if last == "-f":
            fields = command[i].replace("-","_").replace(",","").lower().split()
            break

        last = command[i]

    if fields:
        return ":".join([ "{" + field + "}" for field in fields])

def get_random_mac():
    return ":".join(["{0:02x}".format(randint(0,255)).upper() for i in range(6)])

def get_random_connection_uuid():
    p1 = "".join(["{0:02x}".format(randint(0,255)) for i in range(4)])
    p2 = "".join(["{0:02x}".format(randint(0,255)) for i in range(2)])
    p3 = "".join(["{0:02x}".format(randint(0,255)) for i in range(2)])
    p4 = "".join(["{0:02x}".format(randint(0,255)) for i in range(2)])
    p5 = "".join(["{0:02x}".format(randint(0,255)) for i in range(4)])

    return "-".join([p1, p2, p3, p4, p5])

class MockingNmcli(Nmcli):
    def  __init__(self):
        super(MockingNmcli, self).__init__()
        self.devices = [ DeviceMock("eth0", "ethernet", True, get_random_mac()), DeviceMock("wlan0", "wifi", True,  get_random_mac()) ] 
        self.wifis = [ WifiMock("Leapfrog " + str(x), randint(0,100), MockingNmcli.SECURITIES[randint(0,3)]) for x in range(20) ]
        self.connections = [ ConnectionMock("eth0", get_random_connection_uuid(), "802-3-ethernet", "yes", "0"),
                             ConnectionMock(self.wifis[0].ssid, get_random_connection_uuid(), "802-11-wireless", "no", "0", ssid=self.wifis[0].ssid, psk="Psk1")
                            ]
        self._auto_connect()


    def _auto_connect(self, device = None):
        # Simulate autoconnect
        for connection in self.connections:
            if connection.autoconnect == "yes" and "ethernet" in connection.type and (not device or device == self.devices[0].device):
                self.devices[0].conn_uuid = connection.uuid
                connection.device = self.devices[0].device
            elif connection.autoconnect == "yes" and "wireless" in connection.type and (not device or device == self.devices[1].device):
                self.devices[1].conn_uuid = connection.uuid
                connection.device = self.devices[1].device

    def _send_command(self, command, target = CommandTarget.NMCLI):
        """
        Sends command to ncmli with subprocess.
        Returns (0, output) of the command if succeeded, returns the exit code and output when errors
        """

        self._log_command(command)

        output = self._mock_command_output(command,  target)

        if isinstance(output, tuple):
            self._log_command_output(*output)
            return output
        else:
            self._log_command_output(0, output)
            return 0, output

    def _mock_command_output(self, command, target):
        if target == CommandTarget.DBUS:

            if "org.freedesktop.NetworkManager.Settings.Connection.GetSecrets" in command:
                return MockingNmcli.GET_SECRETS

        elif target == CommandTarget.NMCLI:

            # TODO: Strip this list to the bare essentials to identify the command, in stead of this copy/paste work
            if is_equal_command(command, ["--version"]):
                return MockingNmcli.NMCLI_VERSION
            elif is_equal_command(command, ["-t", "-f", "name, uuid, type, autoconnect, dbus-path", "con", "show" ]):
                return self._dev_con_list(command)
            elif is_equal_command(command, ["-t", "-f", "NAME, DEVICE, TYPE", "c", "show", "--active"]):
                return self._dev_con_list(command)
            elif is_equal_command(command, ["con", "delete", "uuid"]):
                return MockingNmcli.CON_DELETE
            elif is_equal_command(command, ["-t", "con", "show"]):
                return self._con_show_details(command)
            elif is_equal_command(command, ["-t", "con", "modify"]):
                return self._con_mod(command)
            elif is_equal_command(command, [ "con", "up" ]):
                return self._con_up(command)
            elif is_equal_command(command,  ["radio", "wifi"]):
                return self._radio_wifi(command)
            elif is_equal_command(command, ["-t", "-f", "type", "dev"]):
                return MockingNmcli.DEV_TYPE
            elif is_equal_command(command, ["-t", "-f", "device, state", "device", "status"]):
                return self._dev_status()
            if is_equal_command(command, ["-t", "-f", "ssid, signal, security", "dev", "wifi", "list"]):
                return self._dev_wifi_list()
            elif is_equal_command(command, ["dev", "wifi", "rescan"]):
                return MockingNmcli.DEV_WIFI_RESCAN
            elif is_equal_command(command, ["dev", "wifi", "connect"]):
                return MockingNmcli.DEV_WIFI_CONNECT
            elif is_equal_command(command, ["dev", "connect" ]):
                return MockingNmcli.DEV_CONNECT
            elif is_equal_command(command, ["dev", "disconnect" ]):
                return self._dev_disconnect(command)
            elif is_equal_command(command, ["-t", "-f", "type, device, con-uuid, state", "dev"]):
                return self._dev_state()
            elif is_equal_command(command, ['-t', '-f', 'GENERAL.HWADDR', 'd', 'show']):
                return self._dev_hwaddr(command)
            elif is_equal_command(command, ["-t", "-f", "IP4.ADDRESS", "d", "show"]):
                return MockingNmcli.DEV_SHOW_IP

    def _radio_wifi(self, command):

        if command[-1] == "on":
            self.devices[1].enabled = True
            self._auto_connect(self.devices[1].device)
        else:
            self.devices[1].enabled = False
            conn = self._get_connection(self.devices[1].conn_uuid)
            if conn:
                conn.device = None
            self.devices[1].conn_uuid = None

    def _dev_wifi_list(self):
        result = ""

        for wifi in self.wifis:
            result += "{ssid}:{signal}:{security}\n".format(**wifi.__dict__)

        return result

    def _dev_con_list(self, command):
        result = ""

        fields = get_fields_from_command(command)
        only_active = "--active" in command


        for conn in self.connections:
            #result += "{name}:{uuid}:{type}:{autoconnect}:{dbus_path}\n".format(**conn.__dict__)
            if not only_active or conn.device:
                result += fields.format(**conn.__dict__) + "\n"

        return result

    def _dev_hwaddr(self, command):
        device = command[-1]

        for dev in self.devices:
            if dev.device == device:
                return "GENERAL.HWADDR:{hwaddr}\n".format(**dev.__dict__)

    def _con_show_details(self, command):
        conn = self._get_connection(command[-1])

        if not conn:
            return 10, "Error: {0} - no such connection profile".format(command[-1])

        return """connection.name:{name}
connection.uuid:{uuid}
connection.autoconnect:{autoconnect}
connection.type:{type}
802-11-wireless.ssid:{ssid}
ipv4.method:{ipv4method}
ipv4.addresses:{ipv4addresses}
ipv4.dns:{ipv4dns}
IP4.ADDRESS[1]:{ipv4addresses_active}""".format(ipv4addresses=conn.ipv4addresses, 
                                                ipv4dns=conn.ipv4dns, 
                                                ipv4addresses_active=conn.ipv4addresses_active,
                                                **conn.__dict__)

    def _get_connection(self, uuid):
        for connection in self.connections:
            if connection.uuid == uuid:
                return connection

    def _con_mod(self, command):
        conn = None
        last = None

        mapping = {
            "connection.autoconnect": "autoconnect",
            "802-11-wireless-security.psk": "psk",
            "ipv4.method": "ipv4method"
            }

        for i in range(len(command)):

            if last == "modify" or last == "mod":
                conn = self._get_connection(command[i])

                if not conn:
                    return (10, "Error: Connection not found")
            elif last in mapping:
                conn.__setattr__(mapping[last], command[i])
            #TODO: Parse IP and DNS settings

            last = command[i]

    def _con_up(self, command):
        
        uuid = command[-1]
        target_conn = self._get_connection(uuid)

        for conn in self.connections:
            if target_conn.device == conn.device:
                conn.device = ""
        
        if "ethernet" in target_conn.type:
            target_conn.device = self.devices[0].device
            self.devices[0].conn_uuid = target_conn.uuid
        else:
            target_conn.device = self.devices[1].device
            self.devices[1].conn_uuid = target_conn.uuid


    def _dev_disconnect(self, command):
        for dev in self.devices:
            if dev.device == command[-1]:
                conn = self._get_connection(dev.conn_uuid)
                
                if conn:
                    conn.device = ""

                dev.conn_uuid = ""
                break

    def _dev_status(self):
        result = ""

        for dev in self.devices:
            result += "{device}:{state}\n".format(**dev.__dict__)

        return result

    def _dev_state(self):
        result = ""

        for dev in self.devices:
            result += "{type}:{device}:{conn_uuid}:{state}\n".format(state=dev.state,**dev.__dict__)

        return result

    SECURITIES = [ "WPA2", "WPA", "WEP", "" ]

    NMCLI_VERSION = "Version: 0.9.10.0"

    DEV_WIFI_RESCAN = """
    """

    CON_DELETE = """"""

    CON_SHOW = """"""

    CON_SHOW_DETAILS = """ """

    CON_MODIFY = """ """

    CON_UP = """ """

    RADIO_WIFI = ""

    DEV_CONNECT = """ """

    DEV_TYPE = "ethernet\nwifi"

    DEV_STATUS = """ """

    CON_SHOW_ACTIVE = """ """

    DEV_STATE = """ """

    DEV_SHOW_IP = """ """

    GET_SECRETS = """method return sender=:1.239 -> dest=:1.285 reply_serial=2
   array [
      dict entry(
         string "802-11-wireless"
         array [
         ]
      )
      dict entry(
         string "802-11-wireless-security"
         array [
            dict entry(
               string "psk"
               variant                   string "abcdefg"
            )
         ]
      )
   ]"""

class DeviceMock(object):
    def __init__(self, device, type, enabled, hwaddr):
        self.device = device
        self.type = type
        self.enabled = enabled
        self.hwaddr = hwaddr

        self.conn_uuid = None
        
    @property
    def state(self):
        if self.conn_uuid != None:
            return "connected"
        elif self.enabled:
            return "available"
        else:
            return "unavailable"

class ConnectionMock(object):
    def __init__(self, name, uuid, type, autoconnect, dbus_path, ipv4method = "auto", ipv4addresses=[], ipv4dns=[], ssid = "", psk = ""):

        self.name = name
        self.uuid = uuid
        self.type = type
        self.autoconnect = autoconnect
        self.dbus_path = dbus_path
        self.device = ""
        
        self.ipv4method = ipv4method



        self.ssid = ssid
        self.psk = psk

        self._ipv4address = ""
        self._ipv4gateway = "0.0.0.0"
        self._ipv4dns1 = ""
        self._ipv4dns2 = ""

    @property
    def ipv4addresses_active(self):
        if self.ipv4method == "auto":
            return "{ ip = 192.168.0.2/8, gw = 192.168.0.1 }" if "wireless" in self.type else "{ ip = 192.168.0.3/8, gw = 192.168.0.1 }"
        else:
            return self.ipv4addresses

    @property
    def ipv4addresses(self):
        if self._ipv4address:
            return "{" + " ip = {ip}/32, gw = {gateway}".format(ip=self._ipv4address, gateway=self._ipv4gateway) + " }"
        else:
            return ""

    @property
    def ipv4dns(self):
        return "{dns1}, {dns2}".format(dns1=self._ipv4dns1, dns2=self._ipv4dns2)

class WifiMock(object):
    def __init__(self, ssid, signal, security):
        self.ssid = ssid
        self.signal = signal
        self.security = security
