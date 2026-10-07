import QtQuick

Item {
    id: root

    property string state: "LISTENING"
    property color accent: "#ff3852"
    property real uiScale: 1.0
    readonly property bool animated: state !== "IDLE"
    readonly property real energy: state === "SPEAKING" ? 1.0
                                   : state === "LISTENING" ? 0.78
                                   : state === "THINKING" ? 0.48 : 0.18

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 8 * root.uiScale
        anchors.rightMargin: 8 * root.uiScale
        height: 1
        color: root.accent
        opacity: 0.16
    }

    Row {
        id: waveform
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 6 * root.uiScale
        anchors.rightMargin: 6 * root.uiScale
        height: 72 * root.uiScale
        spacing: Math.max(1, 2.2 * root.uiScale)

        Repeater {
            model: 35

            Rectangle {
                required property int index
                readonly property real centerDistance: Math.abs(index - 17) / 17
                readonly property real shape: Math.max(0.18, 1.0 - centerDistance)
                width: Math.max(1.2, (waveform.width - waveform.spacing * 34) / 35)
                height: Math.max(3 * root.uiScale,
                                 (8 + 48 * shape * root.energy * (0.55 + 0.45 * Math.abs(Math.sin(index * 1.71)))) * root.uiScale)
                anchors.verticalCenter: parent.verticalCenter
                radius: width / 2
                color: root.accent
                opacity: 0.24 + 0.72 * shape

                SequentialAnimation on height {
                    running: root.animated
                    loops: Animation.Infinite
                    NumberAnimation {
                        to: Math.max(4 * root.uiScale,
                                     (8 + 42 * root.energy * (0.3 + Math.abs(Math.sin(index * 2.13)))) * root.uiScale)
                        duration: 390 + (index % 6) * 55
                        easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        to: Math.max(4 * root.uiScale,
                                     (7 + 46 * root.energy * (0.24 + Math.abs(Math.cos(index * 1.39)))) * root.uiScale)
                        duration: 430 + (index % 5) * 48
                        easing.type: Easing.InOutSine
                    }
                }
            }
        }
    }

    Item {
        id: rings
        width: 104 * root.uiScale
        height: width
        anchors.centerIn: parent

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "#071014"
            border.width: 1
            border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.50)
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 0.78
            height: width
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.75)
        }
        Rectangle {
            id: pulseRing
            anchors.centerIn: parent
            width: parent.width * 0.53
            height: width
            radius: width / 2
            color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.06)
            border.width: 1
            border.color: root.accent

            SequentialAnimation on scale {
                running: root.animated
                loops: Animation.Infinite
                NumberAnimation { to: 1.12; duration: root.state === "SPEAKING" ? 430 : 720; easing.type: Easing.OutSine }
                NumberAnimation { to: 0.92; duration: root.state === "SPEAKING" ? 430 : 720; easing.type: Easing.InSine }
            }
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 0.23
            height: width
            radius: width / 2
            color: root.accent
            border.width: 5 * root.uiScale
            border.color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.18)
        }

        Repeater {
            model: 8
            Rectangle {
                required property int index
                width: 3 * root.uiScale
                height: 12 * root.uiScale
                radius: width / 2
                color: root.accent
                opacity: index % 2 ? 0.35 : 0.9
                x: rings.width / 2 - width / 2
                y: 4 * root.uiScale
                transformOrigin: Item.Bottom
                rotation: index * 45
            }
        }
    }
}
