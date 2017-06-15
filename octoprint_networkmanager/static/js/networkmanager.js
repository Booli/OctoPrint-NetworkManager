/*
 * View model for OctoPrint-NetworkManager
 *
 * Author: Pim Rutgers
 * License: AGPLv3
 *
 * Lots of credit to Gina Häußge <osd@foosel.net> for OctoPrint-Netconnectd implementation. 
 * Many ideas and code orignates from that plugin.
 *
 */
$(function() {
    function NetworkmanagerViewModel(parameters) {
        var self = this;

        self.loginState = parameters[0];

        self.pollingEnabled = false;
        self.pollingTimeoutId = undefined;

        self.statusCurrentWifi = ko.observable();
        self.enableSignalSorting = ko.observable(false);

        self.connectionDetails = {
            newConnection: ko.observable(false),
            uuid: ko.observable(),
            name: ko.observable(),
            ssid: ko.observable(),
            psk: ko.observable(),
            isWireless: ko.observable(),
            targetInterface: ko.observable('ethernet'),
            ipv4:
            {
                method: ko.observable(),
                autoSettings: ko.pureComputed({
                    read: function () { return self.connectionDetails.ipv4.method() == "auto"; },
                    write: function (value) { self.connectionDetails.ipv4.method(value ? "auto" : "manual"); }
                }),
                ip: ko.observable(),
                gateway: ko.observable(),
                dns: ko.observableArray(),
                dns1: ko.pureComputed({
                    read: function () { return self.connectionDetails.ipv4.dns()[0]; },
                    write: function (value) { self.connectionDetails.ipv4.dns()[0] = value; }
                }),
                dns2: ko.pureComputed({
                    read: function () { return self.connectionDetails.ipv4.dns()[1]; },
                    write: function (value) { self.connectionDetails.ipv4.dns()[1] = value; }
                })
            }
        };

        self.connectionDetailsEditorVisible = ko.observable(false);

        self.status = {
            wifi:
                {
                    uuid: ko.observable(),
                    connected: ko.observable(),
                    ip: ko.observable(),
                    ssid: ko.observable(),
                    enabled: ko.observable(),
                    macAddress: ko.observable()
                },
            ethernet:
                {
                    uuid: ko.observable(),
                    connected: ko.observable(),
                    ip: ko.observable(),
                    enabled: ko.observable(),
                    macAddress: ko.observable()
                }
        };

        self.ethernetIp = ko.computed(function(){
            var ip = self.status.ethernet.ip();
            return ip || "";
        });

        self.wifiIp = ko.computed(function(){
            var ip = self.status.wifi.ip();
            return ip || "";
        });

        self.working = ko.observable(false);
        self.statusUpdate = false;
        self.error = ko.observable(false);

        self.ethernetConnectionText = ko.computed(function() {
            if(self.status.ethernet.connected()){
                return "Connected";
            }
            return "Disconnected";
        });

        // initialize list helper
        self.listHelper = new ItemListHelper(
            "wifis",
            {
                "ssid": function (a, b) {
                    // sorts ascending
                    if (a["ssid"].toLocaleLowerCase() < b["ssid"].toLocaleLowerCase()) return -1;
                    if (a["ssid"].toLocaleLowerCase() > b["ssid"].toLocaleLowerCase()) return 1;
                    return 0;
                },
                "signal": function (a, b) {
                    // sorts descending
                    if (a["signal"] > b["signal"]) return -1;
                    if (a["signal"] < b["signal"]) return 1;
                    return 0;
                }
            },
            {
            },
            "signal",
            [],
            [],
            5
        );

        self.getSignalClasses = function(data)
        {
            n = Math.ceil(data.signal / 20);
            return "fa fa-signal fa-signal-" + n;
        }

        self.refresh = function() {
            self.requestData(true);
        };

        self.editConnectionDetails = function(targetInterface, uuid, newConnection)
        {
            if (!self.loginState.isAdmin()) return; // Maybe do something with this return 

            newConnection = newConnection || false;

            if (!uuid) newConnection = true;

            self.working(true);
            var url = OctoPrint.getBlueprintUrl("networkmanager") + "connection_details/" + (uuid || targetInterface);
            OctoPrint.get(url)
                .done(function (response) {
                    if (response.details)
                        ko.mapping.fromJS(response.details, {}, self.connectionDetails);
                    else
                        self.setDefaultConnectionDetails();

                    self.connectionDetails.psk(undefined);
                    self.connectionDetails.newConnection(newConnection);
                    self.connectionDetails.targetInterface(targetInterface);

                    self.connectionDetailsEditorVisible(true);
                }).always(function () {
                    self.working(false);
                });
        }

        self.saveConnectionDetails = function () {

            self.working(true);

            data = ko.mapping.toJS(self.connectionDetails);

            self._postCommand("connection_details/" + (self.connectionDetails.uuid() || self.connectionDetails.targetInterface()), { "details": data, "interface": self.connectionDetails.targetInterface() })
            .done(function () {

                self.connectionDetailsEditorVisible(false);

                $.notify({
                    title: "Connection settings saved",
                    text: "The new connection settings have been saved."
                },
                   "success"
                );

                self.requestData(true);

            }).fail(function () {
                if (self.connectionDetails.newConnection() && self.connectionDetails.targetInterface() == "wifi") {
                    $.notify({
                        title: "Connection failed",
                        text: "The printer was unable to connect to the wifi network \"" + self.connectionDetails.ssid() + "\". " + (self.connectionDetails.psk() ? ' Please check if you entered the correct password.' : '')
                    },
                           "error"
                       );
                }
                else if (self.connectionDetails.newConnection()) {
                    $.notify({
                        title: "Connection failed",
                        text: "The printer was unable to connect to the wired network."
                    },
                           "error"
                       );
                }
                else {
                    $.notify({
                        title: "Could not save connection settings",
                        text: "Please verify the settings you have entered and try again."
                    },
                      "error"
                    );
                }

                self.working(false);

            });
        };

        self.cancelConnectionDetails = function () {
            self.connectionDetailsEditorVisible(false);
        };

        self.configureWifi = function(data) {
            if (!self.loginState.isAdmin()) return; // Maybe do something with this return 

            

            if (data.connectionUuid) {
                // We have seen this connection previously
                // Give user opportunity to edit some settings
                self.editConnectionDetails("wifi", data.connectionUuid, true);
            }
            else if(!data.security)
            {
                // Try and connect straight away
                self.sendWifiConfig(data.ssid)
            }
            else {
                // Its a new connection that may require a PSK
                self.setDefaultConnectionDetails();
                self.connectionDetails.targetInterface('wifi');
                self.connectionDetails.newConnection(true);
                self.connectionDetails.isWireless(true);
                self.connectionDetails.ssid(data.ssid);
                self.connectionDetailsEditorVisible(true);
            }
        };

        self.sendWifiConfig = function(ssid, psk) {
            if (!self.loginState.isAdmin()) return; // Do something with error again?

            self.working(true);
            return self._postCommand("wifi/configure", { ssid: ssid, psk: psk }, 15000)
                .done(function () { self.requestData(true); }) // Will hide the loading icon
                .fail(function () { self.working(false); });
        };

        self.sendWifiDisconnect = function () {
            if (!self.loginState.isAdmin()) return;

            self.working(true);
            self._postCommand("wifi/disconnect").done(function () {
                $.notify({
                    title: "Disconnected success",
                    text: "You have successfully disconnected the wifi connection"
                },
                    "success"
                );
            }).fail(function () {
                $.notify({
                    title: "Disconnect error",
                    text: "An error occured while disconnecting from wifi. Please try again."
                },
                    "error"
                );
            }).always(function () {
                self.requestData(true);
            });
        };

        self.sendReset = function() {
            if (!self.loginState.isAdmin()) return;

            self._postCommand("wifi/reset");
        };

        self.requestData = function (showWorker) {
            if (showWorker)
                self.working(true);

            if (self.pollingTimeoutId !== undefined) {
                clearTimeout(self.pollingTimeoutId);
                self.pollingTimeoutId = undefined;
            }

            var url = OctoPrint.getBlueprintUrl("networkmanager");
            OctoPrint.get(url).done(self.fromResponse).always(function()
            {
                if (showWorker)
                    self.working(false);
            })
        };

        self.sendWifiRefresh = function() {
            self.working(true);

            self._postCommand("wifi/scan")
                .done(function (response) {
                    self.fromResponse(response);
                })
                .fail(function () {
                    $.notify({
                        title: "Refresh error!",
                        text: "Can't refresh more than once every minute."
                    },
                        "warning"
                    );
                })
                .always(function () {
                    self.working(false);
                });
        };

        self.setDefaultConnectionDetails = function()
        {
            self.connectionDetails.ipv4.method("auto");
            self.connectionDetails.ipv4.dns1(undefined);
            self.connectionDetails.ipv4.dns2(undefined);
            self.connectionDetails.ipv4.gateway(undefined);
            self.connectionDetails.ipv4.ip(undefined);
            self.connectionDetails.isWireless(false);
            self.connectionDetails.name(undefined);
            self.connectionDetails.newConnection(false);
            self.connectionDetails.psk(undefined);
            self.connectionDetails.ssid(undefined);
            self.connectionDetails.uuid(undefined);
            self.connectionDetails.targetInterface('ethernet');
        }

        self.onAfterBinding = function () {
            self.status.wifi.enabled.subscribe(self.onWifiEnabledChanged);
        }

        self.onWifiEnabledChanged = function (wifiEnabled)
        {
            if(!self.statusUpdate)
            {
                // If this isn't an automated status update, but a user's action: notify the back-end
                if (wifiEnabled) {
                    self.working(true);
                    self._postCommand('wifi/enable');
                    // Wait with the refresh
                    window.setTimeout(self.sendWifiRefresh, 3000);
                }
                else {
                    self.working(true);
                    self._postCommand('wifi/disable');
                    self.requestData(true); // Reset the ip address etc
                }
            }
        }

        self.onUserLoggedIn = function (user) {
            if (user.admin) {
                self.requestData();
            }
        };

        self.onWirelessSettingsShown = function() {
            self.pollingEnabled = true;
            self.requestData();
        };

        self.onSettingsHidden = function() {
            if (self.pollingTimeoutId !== undefined) {
                self.pollingTimeoutId = undefined;
            }
            self.pollingEnabled = false;
        };

        self.getEntryId = function(data) {
            return "settings_plugin_networkmanager_wifi_" + md5(data.ssid);
        };

        self.isActive = function(data) {
            if (self.getEntryId(data) === self.statusCurrentWifi()) {
                return "fa-check";
            }
        };

        self.isEncrypted = function(data) {
            if (data.security){
                return "fa-lock";
            }
        };

        self._postCommand = function (endpoint, data, timeout) {
            var url = OctoPrint.getBlueprintUrl("networkmanager") + endpoint;
            var params = {};
            if (timeout !== undefined) {
                params.timeout = timeout;
            }

            return OctoPrint.postJson(url, data, params);
        };

        self.fromResponse = function (response) {
            if (response.error !== undefined) {
                self.error(true);
                return;
            } else {
                self.error(false);
            }


            if (response.status) {

                self.statusUpdate = true;

                self.status.ethernet.connected(response.status.ethernet.connected);
                self.status.ethernet.ip(response.status.ethernet.ip);
                self.status.ethernet.uuid(response.status.ethernet.connection_uuid);
                self.status.ethernet.enabled(response.status.ethernet.enabled);
                self.status.ethernet.macAddress(response.status.ethernet.mac_address);

                self.status.wifi.connected(response.status.wifi.connected);
                self.status.wifi.ip(response.status.wifi.ip);
                self.status.wifi.ssid(response.status.wifi.ssid);
                self.status.wifi.uuid(response.status.wifi.connection_uuid);
                self.status.wifi.enabled(response.status.wifi.enabled);
                self.status.wifi.macAddress(response.status.wifi.mac_address);

                self.statusCurrentWifi(undefined);
                if (response.status.wifi.ssid) {
                    _.each(response.wifis, function(wifi) {
                        if (wifi.ssid === response.status.wifi.ssid) {
                            self.statusCurrentWifi(self.getEntryId(wifi));
                        }
                    });
                }

                self.statusUpdate = false;
            }

            if (response.wifis) {
                var enableSignalSorting = false;
                _.each(response.wifis, function(wifi) {
                    if (wifi.signal !== undefined) {
                        enableSignalSorting = true;
                    }
                });
                self.enableSignalSorting(enableSignalSorting);

                var wifis = [];
                _.each(response.wifis, function(wifi) {
                    wifis.push({
                        ssid: wifi.ssid,
                        signal: wifi.signal,
                        security: wifi.security,
                        connectionUuid: wifi.connectionUuid
                    });
                });

                self.listHelper.updateItems(wifis);
                if (!enableSignalSorting) {
                    self.listHelper.changeSorting("ssid");
                }
            }

            if (self.pollingEnabled) {
                self.pollingTimeoutId = setTimeout(function() {
                    self.requestData();
                }, 30000);
            }
        };

    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        NetworkmanagerViewModel,

        [ "loginStateViewModel"],

        // e.g. #settings_plugin_networkmanager, #tab_plugin_networkmanager, ...
        ["#settings_plugin_networkmanager", "#ethernet_connectivity", "#wifi_connectivity"]
    ]);
});
