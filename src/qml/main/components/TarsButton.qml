import QtQuick
import QtQuick.Controls

Button {
    id: root

    property string iconText: ""
    property color accent: "#ff3852"
    property bool selected: false
    property bool danger: false

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    contentItem: Column {
        spacing: 5

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.iconText
            color: root.enabled ? (root.selected || root.down ? root.accent : "#dce6ea") : "#59666d"
            font.family: displayFontFamily
            font.pixelSize: Math.max(14, root.height * 0.30)
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.text
            color: root.enabled ? "#eef4f6" : "#59666d"
            font.family: displayFontFamily
            font.pixelSize: Math.max(8, root.height * 0.13)
            font.bold: true
            font.letterSpacing: 1.2
            horizontalAlignment: Text.AlignHCenter
        }
    }

    background: Rectangle {
        radius: 7
        color: root.down ? "#24151b"
             : root.hovered ? "#142129"
             : root.selected ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.10)
             : "#0a151b"
        border.width: root.selected || root.visualFocus ? 2 : 1
        border.color: root.enabled ? root.accent : "#37434a"

        Rectangle {
            anchors.fill: parent
            anchors.margins: 5
            radius: 4
            color: "transparent"
            border.width: 1
            border.color: root.hovered || root.visualFocus ? "#485961" : "#1a2b32"
        }
    }

    scale: down ? 0.975 : 1.0
    Behavior on scale { NumberAnimation { duration: 80 } }
}
