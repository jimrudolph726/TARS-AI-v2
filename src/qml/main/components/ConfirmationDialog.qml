import QtQuick

Item {
    id: root

    property string iconText: "!"
    property string title: "CONFIRM ACTION"
    property string message: ""
    property string confirmText: "CONFIRM"
    property string cancelText: "CANCEL"
    property color accent: "#ff3852"
    property real uiScale: 1.0
    signal accepted()
    signal rejected()

    implicitWidth: 310 * uiScale
    implicitHeight: content.implicitHeight

    Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 13 * root.uiScale

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.iconText
            color: root.accent
            font.family: displayFontFamily
            font.pixelSize: 30 * root.uiScale
            font.bold: true
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.title
            color: "#edf3f5"
            font.family: displayFontFamily
            font.pixelSize: 13 * root.uiScale
            font.bold: true
            font.letterSpacing: 1.3 * root.uiScale
        }
        Text {
            width: parent.width - 24 * root.uiScale
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.message
            color: "#97a7ae"
            font.family: monoFontFamily
            font.pixelSize: 7 * root.uiScale
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 9 * root.uiScale

            TarsButton {
                width: 120 * root.uiScale
                height: 48 * root.uiScale
                text: root.cancelText
                iconText: "<"
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                accent: "#829199"
                onClicked: root.rejected()
            }
            TarsButton {
                width: 150 * root.uiScale
                height: 48 * root.uiScale
                text: root.confirmText
                iconText: root.iconText
                iconPixelSize: 10 * root.uiScale
                labelPixelSize: 6.5 * root.uiScale
                accent: root.accent
                selected: true
                onClicked: root.accepted()
            }
        }
    }
}

