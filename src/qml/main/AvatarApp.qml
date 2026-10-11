import QtQuick

Item {
    id: root
    property real uiScale: 1.0

    Rectangle {
        anchors.fill: parent
        color: "#020608"

        Image {
            anchors.fill: parent
            anchors.margins: 5 * root.uiScale
            source: controller.avatarFrameSource
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
        }

        Text {
            visible: controller.avatarFrameSource.length === 0
            anchors.centerIn: parent
            text: "NO AVATAR SPRITES FOUND"
            color: "#ff3852"
            font.family: monoFontFamily
            font.pixelSize: 9 * root.uiScale
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 25 * root.uiScale
            color: "#cc03080a"
            Text {
                anchors.centerIn: parent
                text: controller.avatarCharacter.toUpperCase() + "  ·  " + controller.avatarEmotion + "  ·  " + controller.tarsState
                color: "#d6e0e4"
                font.family: monoFontFamily
                font.pixelSize: 6.5 * root.uiScale
                font.letterSpacing: 1.1 * root.uiScale
            }
        }
    }
}
