import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: root

    property real uiScale: 1.0
    property string diagnosticGroup: "hardware"

    function stateColor(state) {
        if (state === "ok") return "#2aff8a"
        if (state === "error") return "#ff3852"
        if (state === "warning") return "#ffc857"
        if (state === "disabled") return "#66757c"
        return "#64b5f6"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 5 * root.uiScale
        spacing: 5 * root.uiScale

        GridLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 68 * root.uiScale
            Layout.maximumHeight: 68 * root.uiScale
            columns: 4
            rowSpacing: 5 * root.uiScale
            columnSpacing: 5 * root.uiScale

            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "SYSTEM STATE"
                value: controller.tarsState
                detail: controller.stateDetail
                accent: "#ff3852"
                valuePixelSize: 13 * root.uiScale
                uiScale: root.uiScale
            }
            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "BATTERY"
                value: controller.batteryAvailable ? controller.batteryPercent + "%" : "--"
                detail: controller.batteryAvailable ? controller.batteryVoltage.toFixed(2) + " V" : "SENSOR UNAVAILABLE"
                accent: controller.batteryAvailable ? "#2aff8a" : "#66757c"
                valuePixelSize: 15 * root.uiScale
                uiScale: root.uiScale
            }
            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "PROCESSOR"
                value: controller.cpuAvailable ? controller.cpuTemperature + "°C" : "--"
                detail: "CORE TEMPERATURE"
                accent: !controller.cpuAvailable ? "#66757c"
                    : controller.cpuTemperature >= 70 ? "#ff3852" : "#2aff8a"
                valuePixelSize: 15 * root.uiScale
                uiScale: root.uiScale
            }
            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "NETWORK"
                value: controller.wifiOnline ? "ONLINE" : "OFFLINE"
                detail: controller.wifiSsid.length ? controller.wifiSsid : "NO CONNECTION"
                accent: controller.wifiOnline ? "#2aff8a" : "#ff3852"
                valuePixelSize: 13 * root.uiScale
                uiScale: root.uiScale
            }
        }

        GridLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 43 * root.uiScale
            Layout.maximumHeight: 43 * root.uiScale
            columns: 4
            rowSpacing: 5 * root.uiScale
            columnSpacing: 5 * root.uiScale

            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "MEMORY"; value: controller.memoryPercent + "%"; detail: "RAM IN USE"
                accent: controller.memoryPercent >= 85 ? "#ff3852" : "#64b5f6"
                valuePixelSize: 12 * root.uiScale; labelPixelSize: 6 * root.uiScale
                uiScale: root.uiScale
            }
            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "STORAGE"; value: controller.diskPercent + "%"; detail: "DISK IN USE"
                accent: controller.diskPercent >= 90 ? "#ff3852" : "#64b5f6"
                valuePixelSize: 12 * root.uiScale; labelPixelSize: 6 * root.uiScale
                uiScale: root.uiScale
            }
            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "UPTIME"; value: controller.uptimeText; detail: "SYSTEM ONLINE"
                accent: "#64b5f6"
                valuePixelSize: 11 * root.uiScale; labelPixelSize: 6 * root.uiScale
                uiScale: root.uiScale
            }
            StatusCard {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
                label: "THREADS"; value: controller.processThreads.toString(); detail: "ACTIVE WORKERS"
                accent: "#64b5f6"
                valuePixelSize: 12 * root.uiScale; labelPixelSize: 6 * root.uiScale
                uiScale: root.uiScale
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumHeight: 0
            Layout.preferredHeight: 25 * root.uiScale
            Layout.maximumHeight: 25 * root.uiScale
            spacing: 5 * root.uiScale

            TarsButton {
                Layout.fillWidth: true; Layout.fillHeight: true
                text: "HARDWARE"
                iconText: "HW"
                iconPixelSize: 8 * root.uiScale
                labelPixelSize: 6 * root.uiScale
                selected: root.diagnosticGroup === "hardware"
                accent: "#ff3852"
                onClicked: root.diagnosticGroup = "hardware"
            }
            TarsButton {
                Layout.fillWidth: true; Layout.fillHeight: true
                text: "SOFTWARE"
                iconText: "SW"
                iconPixelSize: 8 * root.uiScale
                labelPixelSize: 6 * root.uiScale
                selected: root.diagnosticGroup === "software"
                accent: "#ff3852"
                onClicked: root.diagnosticGroup = "software"
            }
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 4 * root.uiScale
            model: root.diagnosticGroup === "hardware"
                ? controller.hardwareDiagnostics
                : controller.softwareDiagnostics

            delegate: SettingsRow {
                required property var modelData
                width: ListView.view.width
                height: 39 * root.uiScale
                label: modelData.label
                statusText: modelData.value
                description: modelData.detail
                accent: root.stateColor(modelData.state)
                uiScale: root.uiScale
            }
        }
    }
}

