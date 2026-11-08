import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/UiTokens.js" as Ui

Item {
    id: root
    property real uiScale: 1.0
    property string selectedSsid: ""
    property string selectedSecurity: ""
    readonly property real touchTarget: Math.max(Ui.touchMin, Ui.touchMin * uiScale)

    Component.onCompleted: controller.refreshRemoteAccess()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Ui.spaceSm * root.uiScale
        spacing: Ui.spaceSm * root.uiScale

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
                                height: root.touchTarget
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
                    actionText: controller.remoteState === "scanning" ? "" : "SCAN AGAIN"
                    actionIcon: "SCAN"
                    uiScale: root.uiScale
                    onActionTriggered: controller.scanWifiNetworks()
                }
                TextField {
                    id: passwordField
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.touchTarget
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
                    uiScale: root.uiScale
                    dense: true
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.touchTarget
                    Layout.maximumHeight: root.touchTarget
                    text: root.selectedSsid.length ? "CONNECT TO " + root.selectedSsid : "SELECT A NETWORK"
                    iconText: "WIFI"
                    iconPixelSize: 10 * root.uiScale
                    labelPixelSize: 6.5 * root.uiScale
                    enabled: root.selectedSsid.length > 0
                    onClicked: controller.connectWifiNetwork(root.selectedSsid, passwordField.text)
                }
            }

            Rectangle {
                anchors.fill: parent
                visible: controller.remoteState === "active"
                    || controller.remoteState === "hotspot"
                    || controller.remoteState === "ready"
                    || controller.remoteState === "idle"
                radius: Ui.radiusMd * root.uiScale
                color: "#071116"
                border.width: 1
                border.color: controller.remoteState === "active"
                    || controller.remoteState === "hotspot" ? "#2a6f50" : "#30464f"

                Column {
                    anchors.centerIn: parent
                    width: Math.max(0, parent.width - 2 * Ui.spaceXl * root.uiScale)
                    spacing: Ui.spaceMd * root.uiScale

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: controller.remoteState === "active" ? "LINK"
                            : controller.remoteState === "hotspot" ? "WIFI" : "READY"
                        color: controller.remoteState === "active"
                            || controller.remoteState === "hotspot" ? "#2aff8a" : "#829199"
                        font.family: displayFontFamily
                        font.pixelSize: 22 * root.uiScale
                        font.bold: true
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: controller.remoteState === "active" ? "REMOTE LINK ACTIVE"
                            : controller.remoteState === "hotspot" ? "TARS SETUP NETWORK"
                            : "REMOTE ACCESS READY"
                        color: controller.remoteState === "active"
                            || controller.remoteState === "hotspot" ? "#2aff8a" : "#829199"
                        font.family: displayFontFamily
                        font.pixelSize: Math.max(Ui.textBody, 11 * root.uiScale)
                        font.bold: true
                        font.letterSpacing: 1.1 * root.uiScale
                    }
                    Text {
                        width: parent.width
                        text: controller.remoteState === "hotspot"
                            ? "Wi-Fi: TARS-Setup  ·  Password: tars1234"
                            : controller.remoteState === "active" ? controller.remoteUrl
                            : "Start remote access or scan for a Wi-Fi network."
                        color: Ui.textSecondary
                        font.family: monoFontFamily
                        font.pixelSize: Math.max(Ui.textCaption, 6.5 * root.uiScale)
                        wrapMode: Text.Wrap
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }

            AppStateView {
                anchors.fill: parent
                visible: controller.remoteState === "error"
                    || controller.remoteState === "offline"
                    || controller.remoteState === "connecting"
                    || controller.remoteState === "starting"
                    || controller.remoteState === "stopping"
                state: controller.remoteState === "error" ? "error"
                    : controller.remoteState === "offline" ? "disabled"
                    : controller.remoteState === "connecting"
                        || controller.remoteState === "starting"
                        || controller.remoteState === "stopping" ? "loading"
                    : "content"
                iconText: controller.remoteState === "error" ? "!"
                    : controller.remoteState === "offline" ? "OFF"
                    : controller.remoteState === "connecting"
                        || controller.remoteState === "starting"
                        || controller.remoteState === "stopping" ? "..."
                    : "--"
                title: controller.remoteState === "offline" ? "NETWORK REQUIRED"
                    : controller.remoteState === "error" ? "REMOTE LINK ERROR"
                    : controller.remoteState === "connecting" ? "CONNECTING WI-FI"
                    : controller.remoteState === "starting" ? "STARTING REMOTE ACCESS"
                    : controller.remoteState === "stopping" ? "STOPPING REMOTE ACCESS"
                    : ""
                detail: controller.remoteState === "error" ? controller.remoteError
                    : controller.remoteState === "offline" ? "Connect TARS to a network before starting remote access."
                    : "Please wait while the network state changes."
                accent: controller.remoteState === "error" ? "#ff3852"
                    : controller.remoteState === "connecting"
                        || controller.remoteState === "starting"
                        || controller.remoteState === "stopping" ? "#ffc857"
                    : "#829199"
                actionText: controller.remoteState === "error" ? "RETRY STATUS"
                    : controller.remoteState === "offline" ? "SCAN WI-FI" : ""
                actionIcon: controller.remoteState === "offline" ? "SCAN" : "R"
                uiScale: root.uiScale
                onActionTriggered: {
                    if (controller.remoteState === "offline")
                        controller.scanWifiNetworks()
                    else
                        controller.refreshRemoteAccess()
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: root.touchTarget
            Layout.maximumHeight: root.touchTarget
            spacing: Ui.spaceSm * root.uiScale

            TarsButton {
                uiScale: root.uiScale; dense: true
                Layout.fillWidth: true; Layout.fillHeight: true
                text: "WI-FI"
                iconText: "SCAN"
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                enabled: controller.remoteState !== "scanning"
                    && controller.remoteState !== "connecting"
                    && controller.remoteState !== "starting"
                    && controller.remoteState !== "stopping"
                onClicked: controller.scanWifiNetworks()
            }
            TarsButton {
                uiScale: root.uiScale; dense: true
                Layout.fillWidth: true; Layout.fillHeight: true
                text: controller.remoteState === "active" || controller.remoteState === "hotspot" ? "STOP" : "START REMOTE"
                iconText: controller.remoteState === "active" || controller.remoteState === "hotspot" ? "X" : "LINK"
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                selected: controller.remoteState === "active" || controller.remoteState === "hotspot"
                enabled: controller.remoteState !== "scanning"
                    && controller.remoteState !== "connecting"
                    && controller.remoteState !== "starting"
                    && controller.remoteState !== "stopping"
                onClicked: {
                    if (controller.remoteState === "active" || controller.remoteState === "hotspot")
                        controller.stopRemoteAccess()
                    else
                        controller.startRemoteAccess()
                }
            }
            TarsButton {
                uiScale: root.uiScale; dense: true
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
