import QtQuick
import "UiTokens.js" as Ui

Rectangle {
    id: root

    default property alias contentData: content.data
    property color accent: "#ff3852"
    property bool strongBorder: false
    property bool showCornerMarks: false
    property real uiScale: 1.0

    color: Ui.surface
    radius: Ui.radiusLg * uiScale
    border.width: strongBorder ? 2 : 1
    border.color: strongBorder ? accent : Ui.border

    Rectangle {
        anchors.fill: parent
        anchors.margins: Ui.spaceXs * root.uiScale
        radius: Math.max(2, parent.radius - 2)
        color: "transparent"
        border.width: 1
        border.color: Ui.borderInner
        opacity: 0.9
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.margins: Ui.spaceSm * root.uiScale
    }

    Repeater {
        model: root.showCornerMarks ? 4 : 0

        Item {
            required property int index
            width: 18 * root.uiScale
            height: 18 * root.uiScale
            x: index % 2 === 0 ? 10 * root.uiScale : root.width - width - 10 * root.uiScale
            y: index < 2 ? 10 * root.uiScale : root.height - height - 10 * root.uiScale

            Rectangle {
                width: 13 * root.uiScale
                height: Math.max(1, 2 * root.uiScale)
                color: root.accent
                anchors.left: parent.index % 2 === 0 ? parent.left : undefined
                anchors.right: parent.index % 2 === 1 ? parent.right : undefined
                anchors.top: parent.index < 2 ? parent.top : undefined
                anchors.bottom: parent.index >= 2 ? parent.bottom : undefined
            }
            Rectangle {
                width: Math.max(1, 2 * root.uiScale)
                height: 13 * root.uiScale
                color: root.accent
                anchors.left: parent.index % 2 === 0 ? parent.left : undefined
                anchors.right: parent.index % 2 === 1 ? parent.right : undefined
                anchors.top: parent.index < 2 ? parent.top : undefined
                anchors.bottom: parent.index >= 2 ? parent.bottom : undefined
            }
        }
    }
}
