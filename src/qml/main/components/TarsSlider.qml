import QtQuick
import QtQuick.Controls

Slider {
    id: root

    property color accent: "#ff3852"
    property real uiScale: 1.0
    property string valueText: Math.round(value).toString()

    implicitWidth: 150 * uiScale
    implicitHeight: 30 * uiScale
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    live: true

    background: Rectangle {
        x: root.leftPadding
        y: root.topPadding + root.availableHeight / 2 - height / 2
        width: root.availableWidth
        height: 4 * root.uiScale
        radius: height / 2
        color: root.enabled ? "#263940" : "#1b282d"

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: parent.radius
            color: root.enabled ? root.accent : "#4d5a60"
        }
    }

    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: root.topPadding + root.availableHeight / 2 - height / 2
        width: 17 * root.uiScale
        height: width
        radius: width / 2
        color: root.enabled ? "#dfe8ec" : "#66747a"
        border.width: 3 * root.uiScale
        border.color: root.enabled ? root.accent : "#3c494f"

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.top
            anchors.bottomMargin: 2 * root.uiScale
            visible: root.pressed && root.valueText.length > 0
            text: root.valueText
            color: root.accent
            font.family: monoFontFamily
            font.pixelSize: 6 * root.uiScale
            font.bold: true
        }
    }
}

