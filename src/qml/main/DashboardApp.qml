import QtQuick
import QtQuick.Layouts

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

            Rectangle {
                required property var modelData
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 5 * root.uiScale
                color: "#071116"
                border.color: "#31444d"

                Column {
                    anchors.centerIn: parent
                    width: parent.width - 16 * root.uiScale
                    spacing: 6 * root.uiScale
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.label
                        color: "#8fa1aa"
                        font.family: monoFontFamily
                        font.pixelSize: 7 * root.uiScale
                        font.letterSpacing: 1.1 * root.uiScale
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.value
                        color: modelData.color
                        font.family: displayFontFamily
                        font.pixelSize: 21 * root.uiScale
                        font.bold: true
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        text: modelData.detail
                        color: "#667b84"
                        font.family: monoFontFamily
                        font.pixelSize: 6 * root.uiScale
                    }
                }
            }
        }
    }
}
