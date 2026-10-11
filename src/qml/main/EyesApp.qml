import QtQuick

Item {
    id: root
    property color accent: controller.tarsState === "THINKING" ? "#ffc857" : "#ff3852"
    property real uiScale: 1.0
    property real gaze: 0
    property bool blinking: false

    Timer {
        interval: 2800
        running: true
        repeat: true
        onTriggered: {
            root.blinking = true
            blinkEnd.restart()
            root.gaze = (Math.random() - 0.5) * 18 * root.uiScale
        }
    }
    Timer { id: blinkEnd; interval: 180; onTriggered: root.blinking = false }

    Row {
        anchors.centerIn: parent
        spacing: 22 * root.uiScale

        Repeater {
            model: 2
            Rectangle {
                width: Math.min(root.width * 0.34, 145 * root.uiScale)
                height: root.blinking ? 8 * root.uiScale : Math.min(root.height * 0.32, 105 * root.uiScale)
                radius: root.blinking ? height / 2 : 23 * root.uiScale
                color: root.accent
                border.width: 2 * root.uiScale
                border.color: "#ffd6dc"
                Behavior on height { NumberAnimation { duration: 90 } }

                Rectangle {
                    visible: !root.blinking
                    width: 23 * root.uiScale
                    height: width
                    radius: width / 2
                    anchors.verticalCenter: parent.verticalCenter
                    x: Math.max(8 * root.uiScale, Math.min(parent.width - width - 8 * root.uiScale,
                        parent.width / 2 - width / 2 + root.gaze))
                    color: "#071014"
                    Behavior on x { NumberAnimation { duration: 280; easing.type: Easing.InOutQuad } }
                }
            }
        }
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 10 * root.uiScale
        text: "OPTICAL EXPRESSION  ·  " + controller.tarsState
        color: "#81949d"
        font.family: monoFontFamily
        font.pixelSize: 7 * root.uiScale
        font.letterSpacing: 1.2 * root.uiScale
    }
}
