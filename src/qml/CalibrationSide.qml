import QtQuick

Panel {
    id: root
    required property var servoModel
    required property string sideName
    property color panelAccent: "#ff3852"
    accent: panelAccent
    title: sideName + " SIDE"
    subtitle: sideName + " LEG & " + sideName + " ARM CALIBRATION"
    iconText: sideName === "LEFT" ? "◁" : "▷"

    contentItem: Column {
        anchors.fill: parent
        spacing: 5

        Repeater {
            model: root.servoModel
            delegate: ServoControl {
                required property var modelData
                width: parent.width
                height: (parent.height - 20) / 5
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
