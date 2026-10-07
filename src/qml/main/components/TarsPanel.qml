import QtQuick

Rectangle {
    id: root

    default property alias contentData: content.data
    property color accent: "#ff3852"
    property bool strongBorder: false
    property bool showCornerMarks: false

    color: "#071014"
    radius: 7
    border.width: strongBorder ? 2 : 1
    border.color: strongBorder ? accent : "#26363d"

    Rectangle {
        anchors.fill: parent
        anchors.margins: 5
        radius: Math.max(2, parent.radius - 2)
        color: "transparent"
        border.width: 1
        border.color: "#13242b"
        opacity: 0.9
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.margins: 7
    }

    Repeater {
        model: root.showCornerMarks ? 4 : 0

        Item {
            required property int index
            width: 18
            height: 18
            x: index % 2 === 0 ? 10 : root.width - width - 10
            y: index < 2 ? 10 : root.height - height - 10

            Rectangle {
                width: 13
                height: 2
                color: root.accent
                anchors.left: parent.index % 2 === 0 ? parent.left : undefined
                anchors.right: parent.index % 2 === 1 ? parent.right : undefined
                anchors.top: parent.index < 2 ? parent.top : undefined
                anchors.bottom: parent.index >= 2 ? parent.bottom : undefined
            }
            Rectangle {
                width: 2
                height: 13
                color: root.accent
                anchors.left: parent.index % 2 === 0 ? parent.left : undefined
                anchors.right: parent.index % 2 === 1 ? parent.right : undefined
                anchors.top: parent.index < 2 ? parent.top : undefined
                anchors.bottom: parent.index >= 2 ? parent.bottom : undefined
            }
        }
    }
}
