import QtQuick

Rectangle {
    id: root
    property string text: "BUTTON"
    property string iconText: ""
    property color accent: "#84939a"
    property bool primary: false
    signal clicked()
    implicitHeight: 40
    implicitWidth: 110
    radius: 5
    color: mouse.pressed ? "#28343a"
          : mouse.containsMouse ? "#182329"
          : primary ? Qt.rgba(accent.r, accent.g, accent.b, 0.13)
          : "#10191e"
    border.width: primary ? 2 : 1
    border.color: enabled ? accent : "#39454a"
    opacity: enabled ? 1.0 : 0.42
    Row {
        anchors.centerIn: parent
        spacing: 6
        Text {
            visible: root.iconText.length > 0
            text: root.iconText
            color: root.accent
            font.pixelSize: 14
            font.bold: true
        }
        Text {
            width: Math.min(implicitWidth, root.width - (root.iconText.length > 0 ? 28 : 12))
            text: root.text
            color: root.enabled ? "#e8eef0" : "#778288"
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            font.pixelSize: 10
            font.bold: true
            font.letterSpacing: 0.4
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
