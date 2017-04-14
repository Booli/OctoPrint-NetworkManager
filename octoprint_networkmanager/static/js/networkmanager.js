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

        self.connectionsId = undefined;
        self.connectId = undefined;

        self.statusCurrentWifi = ko.observable();
        self.enableSignalSorting = ko.observable(false);

        self.connectionDetails = {
            uuid: ko.observable(),
            name: ko.observable(),
            psk: ko.observable(),
            macaddress: ko.observable(),
            isWireless: ko.observable(),
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
                    ssid: ko.observable()
                },
            ethernet:
                {
                    uuid: ko.observable(),
                    connected: ko.observable(),
                    ip: ko.observable()
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

        self.editorWifi = undefined;
        self.editorWifiSsid = ko.observable();
        self.editorWifiPassphrase1 = ko.observable();
        self.editorWifiPassphrase2 = ko.observable();
        self.editorWifiPassphraseMismatch = ko.computed(function() {
            return self.editorWifiPassphrase1() !== self.editorWifiPassphrase2();
        });

        self.working = ko.observable(false);
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
                "quality": function (a, b) {
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
            self.requestData();
        };

        self.showConnectEditor = function() {
            self.connectionsId.removeClass('active');
            self.connectId.addClass('active');

        };

        self.hideConnectEditor = function () {
            self.connectionsId.addClass('active');
            self.connectId.removeClass('active');

        };

        self.editConnectionDetails = function(uuid)
        {
            if (!self.loginState.isAdmin()) return; // Maybe do something with this return 

            self.working(true);

            $.ajax({
                url: OctoPrint.getBlueprintUrl("networkmanager") + "connection_details/" + uuid,
                type: "GET",
                dataType: "json"
            }).done(function (response) {
                ko.mapping.fromJS(response.details, {}, self.connectionDetails);
                self.connectionDetailsEditorVisible(true);
            }).always(function()
            {
                self.working(false);
            })
        }

        self.saveConnectionDetails = function () {

            self.working(true);

            data = ko.mapping.toJS(self.connectionDetails);

            self._postCommand("connection_details/" + self.connectionDetails.uuid(), { details: data })
            .done(function () {

                self.connectionDetailsEditorVisible(false);

                $.notify({
                    title: "Connection settings saved",
                    text: "The new connection settings have been saved."
                },
                   "success"
                );

            }).fail(function () {

                $.notify({
                    title: "Could not save connection settings",
                    text: "Please verify the settings you have entered and try again."
                },
                  "error"
               );

            }).always(function () {
                self.working(false);
            });
        };

        self.cancelConnectionDetails = function () {
            self.connectionDetailsEditorVisible(false);
        };

        self.configureWifi = function(data) {
            if (!self.loginState.isAdmin()) return; // Maybe do something with this return 

            self.editorWifi = data;
            self.editorWifiSsid(data.ssid);
            self.editorWifiPassphrase1(undefined);
            self.editorWifiPassphrase2(undefined);
            if (data.security) {
                self.showConnectEditor();
            } else {
                self.confirmWifiConfiguration();
            }
        };

        self.confirmWifiConfiguration = function() {
            self.sendWifiConfig(self.editorWifiSsid(), self.editorWifiPassphrase1())
                .done(function () {
                    self.cancelWifiConfiguration();
                }).fail(function () {
                    $.notify({
                        title: "Connection failed",
                        text: "The printer was unable to connect to the wifi network \"" + self.editorWifiSsid() + "\". " + (self.editorWifiPassphrase1() ? ' Please check if you entered the correct password.' : '')
                    },
                       "error"
                   );
                });
        };

        self.cancelWifiConfiguration = function() {
            self.editorWifi = undefined;
            self.editorWifiSsid(undefined);
            self.editorWifiPassphrase1(undefined);
            self.editorWifiPassphrase2(undefined);
            self.hideConnectEditor();
        };

        self.sendWifiConfig = function(ssid, psk) {
            if (!self.loginState.isAdmin()) return; // Do something with error again?

            self.working(true);
            return self._postCommand("configure_wifi", {ssid: ssid, psk: psk}, 15000).always(function() {
                self.working(false);
            });
        };

        self.sendWifiDisconnect = function () {
            if (!self.loginState.isAdmin()) return;

            self.working(true);
            self._postCommand("disconnect_wifi").done(function () {
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
                self.requestData();
                self.working(false);
            });
        };

        self.sendReset = function() {
            if (!self.loginState.isAdmin()) return;

            self._postCommand("reset");
        };

        self.requestData = function () {
            if (self.pollingTimeoutId !== undefined) {
                clearTimeout(self.pollingTimeoutId);
                self.pollingTimeoutId = undefined;
            }

            var url = OctoPrint.getBlueprintUrl("networkmanager")
            OctoPrint.get(url).done(self.fromResponse);
        };

        self.sendWifiRefresh = function() {
            self.working(true);

            self._postCommand("scan_wifi")
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


        self.onBeforeBinding = function() {
            self.connectionsId = $('#networkmanager_connections');
            self.connectId = $('#networkmanager_connect');
        };

        self.onUserLoggedIn = function (user) {
            if (user.admin) {
                self.requestData();
            }
        };

        self.onSettingsShown = function() {
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
                self.status.ethernet.connected(response.status.ethernet.connected);
                self.status.ethernet.ip(response.status.ethernet.ip);
                self.status.ethernet.uuid(response.status.ethernet.connection_uuid);

                self.status.wifi.connected(response.status.wifi.connected);
                self.status.wifi.ip(response.status.wifi.ip);
                self.status.wifi.ssid(response.status.wifi.ssid);
                self.status.wifi.uuid(response.status.wifi.connection_uuid);

                self.statusCurrentWifi(undefined);
                if (response.status.wifi.ssid) {
                    _.each(response.wifis, function(wifi) {
                        if (wifi.ssid === response.status.wifi.ssid) {
                            self.statusCurrentWifi(self.getEntryId(wifi));
                        }
                    });
                }
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
