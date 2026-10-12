import QtQuick
import QtQuick.Layouts
import "components"

Item {
    id: root
    property color accent: "#ff3852"
    property real uiScale: 1.0

    GridLayout {
        anchors.fill: parent
        anchors.margins: 7 * root.uiScale
        columns: 2
        rowSpacing: 7 * root.uiScale
        columnSpacing: 7 * root.uiScale

        Repeater {
            model: [
                { label: "SYSTEM STATE", value: controller.tarsState, color: root.accent, detail: controller.stateDetail },
                { label: "BATTERY", value: controller.batteryAvailable ? controller.batteryPercent + "%" : "--", color: "#2aff8a", detail: "POWER RESERVE" },
                { label: "PROCESSOR", value: controller.cpuAvailable ? controller.cpuTemperature + "°C" : "--", color: controller.cpuTemperature >= 70 ? root.accent : "#2aff8a", detail: "CORE TEMPERATURE" },
                { label: "NETWORK", value: controller.wifiOnline ? "ONLINE" : "OFFLINE", color: controller.wifiOnline ? "#2aff8a" : root.accent, detail: controller.wifiSsid.length ? controller.wifiSsid : "NO CONNECTION" }
            ]

            StatusCard {
                required property var modelData
                Layout.fillWidth: true
                Layout.fillHeight: true
                label: modelData.label
                value: modelData.value
                detail: modelData.detail
                accent: modelData.color
                uiScale: root.uiScale
            }
        }
    }
}
