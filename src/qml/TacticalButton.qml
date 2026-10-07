import QtQuick

Rectangle {
    id: root
    property string text: "BUTTON"
    property string iconText: ""
    property color accent: "#d7e0e4"
    property bool danger: false
    property bool primary: false
    property bool enabled: true
    signal clicked()

    implicitHeight: 42
    implicitWidth: 120
    radius: 5
    color: mouse.pressed ? "#263139"
          : mouse.containsMouse ? "#1a252b"
          : primary ? Qt.rgba(accent.r, accent.g, accent.b, 0.12)
          : "#111b20"
    border.width: primary ? 2 : 1
    border.color: root.enabled ? root.accent : "#445058"
    opacity: root.enabled ? 1.0 : 0.45

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: "transparent"
        border.width: root.primary && mouse.containsMouse ? 1 : 0
        border.color: "#ffffff"
        opacity: 0.35
    }

    Row {
        anchors.centerIn: parent
        spacing: 8
        Text {
            visible: root.iconText.length > 0
            text: root.iconText
            color: root.accent
            font.pixelSize: 20
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.text
            color: root.enabled ? "#edf2f4" : "#7b878d"
            font.family: "Segoe UI"
            font.pixelSize: 11
            font.bold: true
            font.letterSpacing: 0.7
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
