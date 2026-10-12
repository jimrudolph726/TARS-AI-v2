import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: root
    property real uiScale: 1.0
    property string selectedSsid: ""
    property string selectedSecurity: ""

    Component.onCompleted: controller.refreshRemoteAccess()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 7 * root.uiScale
        spacing: 7 * root.uiScale

        StatusCard {
            Layout.fillWidth: true
            Layout.preferredHeight: 62 * root.uiScale
            label: "REMOTE LINK"
            value: controller.remoteStatus
            detail: controller.remoteUrl.length ? controller.remoteUrl
                : controller.remoteError.length ? controller.remoteError
                : "SECURE WEB CONTROL"
            badgeText: controller.remoteState.toUpperCase()
            accent: controller.remoteState === "active" || controller.remoteState === "hotspot" ? "#2aff8a"
                : controller.remoteState === "error" ? "#ff3852" : "#ffc857"
            labelPixelSize: 6 * root.uiScale
            valuePixelSize: 9 * root.uiScale
            detailPixelSize: 6 * root.uiScale
            uiScale: root.uiScale
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                visible: controller.remoteState === "networks"
                      || controller.remoteState === "scanning"
                spacing: 5 * root.uiScale

                Text {
                    text: "AVAILABLE WI-FI NETWORKS"
                    color: "#91a3ac"
                    font.family: monoFontFamily
                    font.pixelSize: 7 * root.uiScale
                    font.letterSpacing: 1 * root.uiScale
                }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    visible: controller.remoteState === "networks"
                        && controller.wifiNetworks.length > 0
                    Column {
                        width: parent.width
                        spacing: 4 * root.uiScale
                        Repeater {
                            model: controller.wifiNetworks
                            Rectangle {
                                required property var modelData
                                width: parent.width
                                height: 34 * root.uiScale
                                radius: 4 * root.uiScale
                                color: root.selectedSsid === modelData.ssid ? "#24151b" : "#08141a"
                                border.color: root.selectedSsid === modelData.ssid ? "#ff3852" : "#2b414a"
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 7 * root.uiScale
                                    Text {
                                        Layout.fillWidth: true
                                        text: (modelData.in_use ? "●  " : "") + modelData.ssid
                                        color: modelData.in_use ? "#2aff8a" : "#dce6ea"
                                        font.family: monoFontFamily
                                        font.pixelSize: 7.5 * root.uiScale
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        text: modelData.security + "  " + modelData.signal + "%"
                                        color: "#82959e"
                                        font.family: monoFontFamily
                                        font.pixelSize: 6 * root.uiScale
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        root.selectedSsid = modelData.ssid
                                        root.selectedSecurity = modelData.security
                                        passwordField.text = ""
                                    }
                                }
                            }
                        }
                    }
                }
                AppStateView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: controller.remoteState === "scanning"
                        || (controller.remoteState === "networks" && controller.wifiNetworks.length === 0)
                    state: controller.remoteState === "scanning" ? "loading" : "empty"
                    title: controller.remoteState === "scanning" ? "SCANNING WI-FI" : "NO NETWORKS FOUND"
                    detail: controller.remoteState === "scanning"
                        ? "Searching for nearby wireless networks."
                        : "Refresh the scan or check that Wi-Fi is enabled."
                    uiScale: root.uiScale
                }
                TextField {
                    id: passwordField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32 * root.uiScale
                    visible: root.selectedSsid.length > 0 && root.selectedSecurity !== "open"
                    placeholderText: "Password for " + root.selectedSsid
                    echoMode: TextInput.Password
                    color: "#edf3f5"
                    placeholderTextColor: "#667982"
                    font.family: monoFontFamily
                    font.pixelSize: 7 * root.uiScale
                    background: Rectangle { color: "#08141a"; border.color: "#38505a"; radius: 4 * root.uiScale }
                }
                TarsButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38 * root.uiScale
                    Layout.maximumHeight: 38 * root.uiScale
                    text: root.selectedSsid.length ? "CONNECT TO " + root.selectedSsid : "SELECT A NETWORK"
                    iconText: "WIFI"
                    iconPixelSize: 10 * root.uiScale
                    labelPixelSize: 6.5 * root.uiScale
                    enabled: root.selectedSsid.length > 0
                    onClicked: controller.connectWifiNetwork(root.selectedSsid, passwordField.text)
                }
            }

            AppStateView {
                anchors.fill: parent
                visible: controller.remoteState !== "networks"
                      && controller.remoteState !== "scanning"
                state: controller.remoteState === "error" ? "error"
                    : controller.remoteState === "offline" ? "disabled"
                    : controller.remoteState === "connecting"
                        || controller.remoteState === "starting"
                        || controller.remoteState === "stopping" ? "loading"
                    : "empty"
                iconText: controller.remoteState === "active" ? "LINK"
                    : controller.remoteState === "hotspot" ? "WIFI"
                    : controller.remoteState === "error" ? "!"
                    : controller.remoteState === "offline" ? "OFF"
                    : controller.remoteState === "connecting"
                        || controller.remoteState === "starting"
                        || controller.remoteState === "stopping" ? "..."
                    : "--"
                title: controller.remoteState === "active" ? "REMOTE LINK ACTIVE"
                    : controller.remoteState === "hotspot" ? "TARS SETUP NETWORK"
                    : controller.remoteState === "offline" ? "NETWORK REQUIRED"
                    : controller.remoteState === "error" ? "REMOTE LINK ERROR"
                    : controller.remoteState === "connecting" ? "CONNECTING WI-FI"
                    : controller.remoteState === "starting" ? "STARTING REMOTE ACCESS"
                    : controller.remoteState === "stopping" ? "STOPPING REMOTE ACCESS"
                    : "REMOTE ACCESS READY"
                detail: controller.remoteState === "hotspot"
                    ? "Wi-Fi: TARS-Setup  ·  Password: tars1234"
                    : controller.remoteState === "active" ? controller.remoteUrl
                    : controller.remoteState === "error" ? controller.remoteError
                    : controller.remoteState === "offline" ? "Connect TARS to a network before starting remote access."
                    : "Start remote access or scan for a Wi-Fi network."
                accent: controller.remoteState === "active" || controller.remoteState === "hotspot" ? "#2aff8a"
                    : controller.remoteState === "error" ? "#ff3852"
                    : controller.remoteState === "connecting"
                        || controller.remoteState === "starting"
                        || controller.remoteState === "stopping" ? "#ffc857"
                    : "#829199"
                uiScale: root.uiScale
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40 * root.uiScale
            Layout.maximumHeight: 40 * root.uiScale
            spacing: 6 * root.uiScale

            TarsButton {
                Layout.fillWidth: true; Layout.fillHeight: true
                text: "WI-FI"
                iconText: "SCAN"
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                onClicked: controller.scanWifiNetworks()
            }
            TarsButton {
                Layout.fillWidth: true; Layout.fillHeight: true
                text: controller.remoteState === "active" || controller.remoteState === "hotspot" ? "STOP" : "START REMOTE"
                iconText: controller.remoteState === "active" || controller.remoteState === "hotspot" ? "X" : "LINK"
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                selected: controller.remoteState === "active" || controller.remoteState === "hotspot"
                onClicked: {
                    if (controller.remoteState === "active" || controller.remoteState === "hotspot")
                        controller.stopRemoteAccess()
                    else
                        controller.startRemoteAccess()
                }
            }
            TarsButton {
                Layout.fillWidth: true; Layout.fillHeight: true
                text: "REFRESH"
                iconText: "R"
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                onClicked: controller.refreshRemoteAccess()
            }
        }
    }
}
