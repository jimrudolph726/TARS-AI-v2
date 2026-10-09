import QtQuick

Rectangle {
    id: root
    required property var servoModel
    required property string sideName
    property color panelAccent: "#ff3b52"
    color: "#091115"
    radius: 7
    border.color: "#28353b"

    Rectangle {
        id: sideHeader
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 38
        color: "#0d171b"
        radius: 7
        Rectangle {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 3
            height: 22
            color: root.panelAccent
        }
        Text {
            anchors.left: parent.left
            anchors.leftMargin: 13
            anchors.verticalCenter: parent.verticalCenter
            text: root.sideName + " SIDE"
            color: "#eef3f5"
            font.pixelSize: 13
            font.bold: true
            font.letterSpacing: 1.4
        }
        Text {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: "LEG · ARM"
            color: "#7f8d93"
            font.family: "Consolas"
            font.pixelSize: 9
        }
    }

    Column {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: sideHeader.bottom
        anchors.bottom: parent.bottom
        anchors.margins: 6
        spacing: 4
        Repeater {
            model: root.servoModel
            delegate: ServoControl {
                required property var modelData
                width: parent.width
                height: (parent.height - 16) / 5
                servoId: modelData.id
                label: modelData.label
                servoValue: modelData.value
                minimum: modelData.minimum
                maximum: modelData.maximum
                unit: modelData.unit
                accent: root.panelAccent
                onValueRequested: value => controller.setServoValue(servoId, value)
                onAdjustmentRequested: delta => controller.adjustServo(servoId, delta)
            }
        }
    }
}
