import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    required property string servoId
    required property string label
    required property real servoValue
    required property real minimum
    required property real maximum
    required property string unit
    property color accent: "#ff3852"
    property real previewValue: servoValue
    signal valueRequested(real value)
    signal adjustmentRequested(int delta)

    onServoValueChanged: {
        if (!trackInteraction.pressed)
            previewValue = servoValue
    }

    color: "#0b1418"
    radius: 7
    border.width: 1
    border.color: "#1e2b31"

    Row {
        id: titleRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.topMargin: 8
        height: 25

        Text {
            width: parent.width - valueBox.width
            text: root.label
            color: "#e9eef0"
            elide: Text.ElideRight
            font.family: "Segoe UI"
            font.pixelSize: 11
            font.bold: true
            font.letterSpacing: 0.7
            anchors.verticalCenter: parent.verticalCenter
        }

        Rectangle {
            id: valueBox
            width: 84
            height: 25
            radius: 4
            color: "#080d10"
            border.color: "#34434a"

            Row {
                anchors.centerIn: parent
                spacing: 5
                Text {
                    text: (root.previewValue > 0 ? "+" : "") + Math.round(root.previewValue)
                    color: root.accent
                    font.family: "Consolas"
                    font.pixelSize: 17
                    font.bold: true
                }
                Text {
                    text: root.unit
                    color: "#b5c0c5"
                    font.pixelSize: 10
                    anchors.baseline: parent.children[0].baseline
                }
            }
        }
    }

    Slider {
        id: slider
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: titleRow.bottom
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        height: 25
        from: root.minimum
        to: root.maximum
        stepSize: 1
        value: root.previewValue

        background: Rectangle {
            x: slider.leftPadding
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: slider.availableWidth
            height: 5
            radius: 3
            color: "#26333a"
            border.color: "#536168"

            Rectangle {
                width: slider.visualPosition * parent.width
                height: parent.height
                radius: parent.radius
                color: root.accent
            }
        }

        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: 19
            height: 19
            radius: 10
            color: "#351218"
            border.width: 3
            border.color: root.accent
        }

        // Qt's styled Slider normally prioritizes dragging the handle.  This
        // full-track interaction layer makes calibration feel more direct:
        // press anywhere to jump there, then keep dragging to scrub the value.
        MouseArea {
            id: trackInteraction
            objectName: root.servoId + "_trackInteraction"
            anchors.fill: parent
            hoverEnabled: true
            preventStealing: true
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.PointingHandCursor

            function applyPointer(pointerX) {
                const usableWidth = Math.max(1, slider.availableWidth)
                const position = Math.max(0, Math.min(1,
                    (pointerX - slider.leftPadding) / usableWidth))
                const rawValue = slider.from + position * (slider.to - slider.from)
                const steppedValue = Math.round(rawValue / slider.stepSize) * slider.stepSize
                root.previewValue = Math.max(slider.from, Math.min(slider.to, steppedValue))
            }

            onPressed: mouse => applyPointer(mouse.x)
            onPositionChanged: mouse => {
                if (pressed)
                    applyPointer(mouse.x)
            }
            onReleased: root.valueRequested(root.previewValue)
            onCanceled: root.previewValue = root.servoValue
        }
    }

    Row {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.bottomMargin: 7
        spacing: 7

        Repeater {
            model: [-5, -1, 1, 5]
            delegate: TacticalButton {
                required property int modelData
                width: (parent.width - 21) / 4
                height: 25
                text: modelData > 0 ? "+" + modelData : String(modelData)
                accent: "#596970"
                onClicked: root.adjustmentRequested(modelData)
            }
        }
    }
}
