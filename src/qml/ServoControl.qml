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
    property color accent: "#ff3b52"
    property real previewValue: servoValue
    signal valueRequested(real value)
    signal adjustmentRequested(int delta)

    onServoValueChanged: if (!trackInteraction.pressed) previewValue = servoValue
    color: "#0c1519"
    radius: 5
    border.color: "#202d33"

    Text {
        id: labelText
        anchors.left: parent.left
        anchors.leftMargin: 9
        anchors.top: parent.top
        anchors.topMargin: 5
        width: parent.width - valueText.width - 28
        text: root.label
        color: "#dce4e7"
        elide: Text.ElideRight
        font.pixelSize: 10
        font.bold: true
        font.letterSpacing: 0.5
    }
    Text {
        id: valueText
        anchors.right: parent.right
        anchors.rightMargin: 9
        anchors.verticalCenter: labelText.verticalCenter
        text: (root.previewValue > 0 ? "+" : "") + Math.round(root.previewValue)
        color: root.accent
        font.family: "Consolas"
        font.pixelSize: 13
        font.bold: true
    }

    Slider {
        id: slider
        anchors.left: minusButton.right
        anchors.right: plusButton.left
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 4
        height: Math.max(22, parent.height - 24)
        from: root.minimum
        to: root.maximum
        stepSize: 1
        value: root.previewValue
        background: Rectangle {
            x: slider.leftPadding
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: slider.availableWidth
            height: 4
            radius: 2
            color: "#26343a"
            Rectangle {
                width: slider.visualPosition * parent.width
                height: parent.height
                radius: 2
                color: root.accent
            }
        }
        handle: Rectangle {
            x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
            y: slider.topPadding + slider.availableHeight / 2 - height / 2
            width: 17
            height: 17
            radius: 9
            color: "#11191d"
            border.width: 3
            border.color: root.accent
        }
        MouseArea {
            id: trackInteraction
            anchors.fill: parent
            preventStealing: true
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.PointingHandCursor
            function applyPointer(pointerX) {
                const usable = Math.max(1, slider.availableWidth)
                const position = Math.max(0, Math.min(1, (pointerX - slider.leftPadding) / usable))
                root.previewValue = Math.round(slider.from + position * (slider.to - slider.from))
            }
            onPressed: mouse => applyPointer(mouse.x)
            onPositionChanged: mouse => { if (pressed) applyPointer(mouse.x) }
            onReleased: root.valueRequested(root.previewValue)
            onCanceled: root.previewValue = root.servoValue
        }
    }

    Rectangle {
        id: minusButton
        anchors.left: parent.left
        anchors.leftMargin: 7
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 6
        width: 28
        height: 24
        radius: 4
        color: minusArea.pressed ? "#29353a" : "#141f24"
        border.color: "#46565d"
        Text { anchors.centerIn: parent; text: "−"; color: "#dce4e7"; font.pixelSize: 16 }
        MouseArea { id: minusArea; anchors.fill: parent; onClicked: root.adjustmentRequested(-1) }
    }
    Rectangle {
        id: plusButton
        anchors.right: parent.right
        anchors.rightMargin: 7
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 6
        width: 28
        height: 24
        radius: 4
        color: plusArea.pressed ? "#29353a" : "#141f24"
        border.color: "#46565d"
        Text { anchors.centerIn: parent; text: "+"; color: "#dce4e7"; font.pixelSize: 15 }
        MouseArea { id: plusArea; anchors.fill: parent; onClicked: root.adjustmentRequested(1) }
    }
}
