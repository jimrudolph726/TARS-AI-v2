import QtQuick

Item {
    id: root

    property string label: "BATTERY"
    property string value: "81%"
    property string iconText: "▣"
    property color valueColor: "#2aff8a"
    property real uiScale: 1.0

    Rectangle {
        id: iconBox
        width: 34 * root.uiScale
        height: width
        anchors.left: parent.left
        anchors.leftMargin: 8 * root.uiScale
        anchors.verticalCenter: parent.verticalCenter
        radius: 5 * root.uiScale
        color: "#0b171d"
        border.color: "#36505d"

        Text {
            anchors.centerIn: parent
            text: root.iconText
            color: root.valueColor
            font.family: displayFontFamily
            font.pixelSize: 17 * root.uiScale
            font.bold: true
        }
    }

    Column {
        anchors.left: iconBox.right
        anchors.leftMargin: 8 * root.uiScale
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3 * root.uiScale

        Text {
            text: root.label
            color: "#9cacb4"
            font.family: monoFontFamily
            font.pixelSize: 7.5 * root.uiScale
            font.letterSpacing: 1.2 * root.uiScale
        }
        Text {
            text: root.value
            color: root.valueColor
            font.family: displayFontFamily
            font.pixelSize: 14 * root.uiScale
            font.bold: true
        }
    }
}
