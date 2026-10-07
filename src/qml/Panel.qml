import QtQuick

Rectangle {
    id: root
    property string title: ""
    property string subtitle: ""
    property string iconText: "◇"
    property color accent: "#ff3852"
    property alias contentItem: body.data

    color: "#071014"
    radius: 10
    border.width: 1
    border.color: Qt.rgba(accent.r, accent.g, accent.b, 0.85)

    Rectangle {
        anchors.fill: parent
        anchors.margins: 5
        radius: 7
        color: "transparent"
        border.width: 1
        border.color: "#243139"
    }

    Rectangle {
        width: 3
        height: parent.height - 22
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        color: root.accent
        opacity: 0.7
    }

    Item {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        height: 52

        Rectangle {
            width: 40
            height: 40
            radius: 6
            color: "#101a1f"
            border.color: root.accent
            anchors.verticalCenter: parent.verticalCenter

            Text {
                anchors.centerIn: parent
                text: root.iconText
                color: root.accent
                font.pixelSize: 22
                font.bold: true
            }
        }

        Column {
            anchors.left: parent.left
            anchors.leftMargin: 54
            anchors.verticalCenter: parent.verticalCenter
            spacing: 3

            Text {
                text: root.title
                color: "#f1f5f6"
                font.family: "Segoe UI"
                font.pixelSize: 20
                font.bold: true
                font.letterSpacing: 1.7
            }
            Text {
                text: root.subtitle
                color: "#9ca9b0"
                font.family: "Segoe UI"
                font.pixelSize: 10
                font.letterSpacing: 1.8
            }
        }
    }

    Item {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.bottomMargin: 10
    }
}
