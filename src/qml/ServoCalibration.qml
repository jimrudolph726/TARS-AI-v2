import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 960
    height: 600
    minimumWidth: 720
    minimumHeight: 420
    title: "TARS Servo Control"
    color: "#05090b"

    readonly property color accent: "#ff3b52"
    readonly property color green: "#35e98a"
    readonly property color textPrimary: "#eef3f5"
    readonly property color textMuted: "#8f9ba1"
    property int currentPage: 0
    property bool closeConfirmed: false

    onClosing: close => {
        if (controller.unsavedChanges && !closeConfirmed) {
            close.accepted = false
            unsavedDialog.open()
        }
    }

    Dialog {
        id: unsavedDialog
        anchors.centerIn: parent
        width: Math.min(440, window.width - 40)
        modal: true
        closePolicy: Popup.NoAutoClose
        background: Rectangle {
            color: "#0a1216"
            radius: 7
            border.color: window.accent
        }
        contentItem: ColumnLayout {
            spacing: 12
            Text {
                Layout.fillWidth: true
                text: "UNSAVED CALIBRATION"
                color: window.textPrimary
                font.pixelSize: 15
                font.bold: true
                font.letterSpacing: 1.4
            }
            Text {
                Layout.fillWidth: true
                text: "Save the new servo offsets before closing?"
                color: window.textMuted
                wrapMode: Text.WordWrap
                font.pixelSize: 11
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                TacticalButton {
                    Layout.fillWidth: true
                    height: 34
                    text: "CANCEL"
                    onClicked: unsavedDialog.close()
                }
                TacticalButton {
                    Layout.fillWidth: true
                    height: 34
                    text: "DISCARD"
                    accent: "#8b9ca4"
                    onClicked: {
                        window.closeConfirmed = true
                        unsavedDialog.close()
                        window.close()
                    }
                }
                TacticalButton {
                    Layout.fillWidth: true
                    height: 34
                    text: "SAVE"
                    primary: true
                    accent: window.accent
                    onClicked: {
                        controller.saveCalibration()
                        Qt.callLater(function() {
                            if (!controller.unsavedChanges) {
                                window.closeConfirmed = true
                                unsavedDialog.close()
                                window.close()
                            }
                        })
                    }
                }
            }
        }
    }

    Shortcut {
        sequence: "Esc"
        onActivated: window.close()
    }

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 50
        color: "#080e11"
        border.color: "#1f2a2f"

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            spacing: 14
            Text {
                text: "TARS"
                color: window.textPrimary
                font.family: "Segoe UI"
                font.pixelSize: 24
                font.bold: true
                font.letterSpacing: 3
            }
            Rectangle { width: 2; height: 30; color: window.accent }
            Column {
                Layout.fillWidth: true
                spacing: 1
                Text {
                    text: "SERVO CONTROL"
                    color: window.textPrimary
                    font.pixelSize: 15
                    font.bold: true
                    font.letterSpacing: 2
                }
                Text {
                    text: "CALIBRATE · TEST · VERIFY"
                    color: window.textMuted
                    font.family: "Consolas"
                    font.pixelSize: 9
                    font.letterSpacing: 1.4
                }
            }
            Rectangle {
                Layout.preferredWidth: 170
                Layout.preferredHeight: 28
                radius: 5
                color: "#0e171b"
                border.color: controller.hardwareConnected ? window.green : "#59666c"
                Text {
                    anchors.centerIn: parent
                    text: controller.hardwareModeText
                    color: controller.hardwareConnected ? window.green : "#a8b2b7"
                    font.family: "Consolas"
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }
    }

    Rectangle {
        id: tabBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        height: 36
        color: "#070c0f"
        border.color: "#1b262b"

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 14
            height: parent.height
            spacing: 4
            Repeater {
                model: ["CALIBRATION", "RANGE TEST", "MOVEMENTS", "GAIT DIAGNOSTIC"]
                delegate: Rectangle {
                    required property string modelData
                    required property int index
                    width: 142
                    height: parent.height
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: window.currentPage === index ? window.textPrimary : window.textMuted
                        font.pixelSize: 11
                        font.bold: true
                        font.letterSpacing: 1.2
                    }
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 3
                        color: window.currentPage === index ? window.accent : "transparent"
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (window.currentPage === 1 && index !== 1
                                    && controller.rangeTestArmed)
                                controller.setRangeTestArmed(false)
                            window.currentPage = index
                        }
                    }
                }
            }
        }
    }

    Item {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: tabBar.bottom
        anchors.bottom: actionBar.top
        anchors.margins: 8

        RowLayout {
            anchors.fill: parent
            spacing: 10
            visible: window.currentPage === 0
            CalibrationSide {
                Layout.fillWidth: true
                Layout.fillHeight: true
                servoModel: controller.leftServos
                sideName: "LEFT"
                panelAccent: window.accent
                controlsEnabled: !controller.movementActive && !controller.rangeTestArmed
            }
            CalibrationSide {
                Layout.fillWidth: true
                Layout.fillHeight: true
                servoModel: controller.rightServos
                sideName: "RIGHT"
                panelAccent: window.accent
                controlsEnabled: !controller.movementActive && !controller.rangeTestArmed
            }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 10
            visible: window.currentPage === 1

            Rectangle {
                Layout.preferredWidth: 255
                Layout.fillHeight: true
                radius: 7
                color: "#091115"
                border.color: "#28353b"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 9
                    spacing: 6
                    Text {
                        Layout.fillWidth: true
                        text: "SELECT ONE SERVO"
                        color: window.textPrimary
                        font.pixelSize: 12
                        font.bold: true
                        font.letterSpacing: 1.2
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Range testing never changes saved calibration."
                        color: window.textMuted
                        wrapMode: Text.WordWrap
                        font.pixelSize: 8
                    }
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 4
                        model: controller.rangeServoOptions
                        delegate: TacticalButton {
                            required property var modelData
                            width: ListView.view.width
                            height: 31
                            text: modelData.label
                            primary: controller.selectedRangeServo === modelData.id
                            accent: controller.selectedRangeServo === modelData.id
                                    ? window.accent : "#68767d"
                            enabled: modelData.available && !controller.rangeTestBusy
                            onClicked: controller.selectRangeServo(modelData.id)
                        }
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 7
                color: "#091115"
                border.color: controller.rangeTestArmed ? window.accent : "#28353b"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        text: controller.selectedRangeServoLabel
                        color: window.textPrimary
                        font.pixelSize: 17
                        font.bold: true
                        font.letterSpacing: 1.5
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "CALIBRATED ENDPOINTS  "
                              + controller.rangeTestMinimumPulse + "  →  "
                              + controller.rangeTestMaximumPulse
                        color: window.green
                        font.family: "Consolas"
                        font.pixelSize: 10
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 88
                        radius: 6
                        color: "#0c1519"
                        border.color: "#26343a"
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 3
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: "REQUESTED  " + controller.rangeTestPercent + "%"
                                    color: window.accent
                                    font.family: "Consolas"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: "PWM " + controller.rangeTestPulse
                                    color: window.textPrimary
                                    font.family: "Consolas"
                                    font.pixelSize: 12
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "APPLIED  " + controller.rangeTestAppliedPercent + "%"
                                      + (controller.rangeTestBusy ? "  ·  MOVING" : "  ·  HOLDING")
                                color: controller.rangeTestBusy ? window.green : window.textMuted
                                font.family: "Consolas"
                                font.pixelSize: 9
                            }
                        }
                    }

                    Slider {
                        id: rangeSlider
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        from: 0
                        to: 100
                        stepSize: 1
                        snapMode: Slider.SnapAlways
                        live: true
                        value: controller.rangeTestPercent
                        enabled: controller.rangeTestArmed && !controller.movementActive
                        onMoved: controller.previewRangePosition(value)
                        onPressedChanged: {
                            if (!pressed)
                                controller.setRangePosition(value)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        TacticalButton {
                            Layout.fillWidth: true
                            height: 34
                            text: "-10%"
                            enabled: controller.rangeTestArmed
                            onClicked: controller.nudgeRangePosition(-10)
                        }
                        TacticalButton {
                            Layout.fillWidth: true
                            height: 34
                            text: "-1%"
                            enabled: controller.rangeTestArmed
                            onClicked: controller.nudgeRangePosition(-1)
                        }
                        TacticalButton {
                            Layout.fillWidth: true
                            height: 34
                            text: "+1%"
                            enabled: controller.rangeTestArmed
                            onClicked: controller.nudgeRangePosition(1)
                        }
                        TacticalButton {
                            Layout.fillWidth: true
                            height: 34
                            text: "+10%"
                            enabled: controller.rangeTestArmed
                            onClicked: controller.nudgeRangePosition(10)
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        text: "SAFETY\nSupport the selected joint before arming. Motion is limited to the calibrated endpoints and ramped at a controlled rate. DISABLE PWM releases all torque immediately."
                        color: "#b6c0c4"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 9
                        lineHeight: 1.2
                    }

                    TacticalButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        text: controller.rangeTestArmed ? "DISARM RANGE TEST" : "ARM SELECTED SERVO"
                        accent: controller.rangeTestArmed ? window.accent : window.green
                        primary: true
                        enabled: controller.hardwareConnected && controller.servoPower
                                 && !controller.movementActive
                        onClicked: controller.setRangeTestArmed(!controller.rangeTestArmed)
                    }
                }
            }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 10
            visible: window.currentPage === 2

            Rectangle {
                Layout.preferredWidth: 166
                Layout.fillHeight: true
                radius: 7
                color: "#091115"
                border.color: "#28353b"
                Column {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 4
                    Text {
                        text: "PRESET GROUP"
                        color: window.textMuted
                        font.family: "Consolas"
                        font.pixelSize: 9
                        font.letterSpacing: 1.2
                    }
                    Repeater {
                        model: controller.movementCategories
                        delegate: TacticalButton {
                            required property string modelData
                            width: parent.width
                            height: 34
                            text: modelData.toUpperCase()
                            accent: controller.movementCategory === modelData ? window.accent : "#68767d"
                            primary: controller.movementCategory === modelData
                            onClicked: controller.setMovementCategory(modelData)
                        }
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: controller.movementActive
                              ? "Movement active. STOP interrupts at the next safe motion checkpoint."
                              : "Choose a preset. Arm presets are disabled when arms_present is false."
                        color: window.textMuted
                        font.pixelSize: 8
                        lineHeight: 1.1
                    }
                    Item { width: 1; height: Math.max(0, parent.height - 244) }
                    TacticalButton {
                        width: parent.width
                        height: 36
                        text: "STOP"
                        iconText: "■"
                        accent: window.accent
                        primary: true
                        enabled: controller.movementActive
                        onClicked: controller.stopMovement()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 7
                color: "#091115"
                border.color: "#28353b"
                Text {
                    id: movementTitle
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 12
                    text: controller.movementCategory.toUpperCase() + " PRESETS"
                    color: window.textPrimary
                    font.pixelSize: 13
                    font.bold: true
                    font.letterSpacing: 1.3
                }
                GridView {
                    id: movementGrid
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: movementTitle.bottom
                    anchors.bottom: parent.bottom
                    anchors.margins: 8
                    anchors.topMargin: 10
                    clip: true
                    model: controller.movementPresets
                    cellWidth: width >= 650 ? width / 4 : width / 3
                    cellHeight: 66
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Item {
                        required property var modelData
                        width: movementGrid.cellWidth
                        height: movementGrid.cellHeight
                        TacticalButton {
                            anchors.fill: parent
                            anchors.margins: 4
                            text: modelData.name.toUpperCase()
                            accent: modelData.category === "Locomotion" ? window.accent
                                  : modelData.category === "Arms" ? "#d5a85c" : "#8b9ca4"
                            primary: modelData.key === "step_forward" || modelData.key === "walk_forward"
                            enabled: modelData.available && !controller.movementActive
                            onClicked: controller.runMovement(modelData.key)
                        }
                    }
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 10
            visible: window.currentPage === 3

            Rectangle {
                Layout.preferredWidth: 205
                Layout.fillHeight: true
                radius: 7
                color: "#091115"
                border.color: "#28353b"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    Text {
                        Layout.fillWidth: true
                        text: "MANUAL GAIT TEST"
                        color: window.textPrimary
                        font.pixelSize: 12
                        font.bold: true
                        font.letterSpacing: 1.2
                    }
                    Text {
                        Layout.fillWidth: true
                        text: controller.diagnosticProfileText
                        color: window.green
                        font.family: "Consolas"
                        font.pixelSize: 9
                        font.bold: true
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        TacticalButton {
                            Layout.fillWidth: true
                            height: 32
                            text: "FORWARD"
                            primary: controller.diagnosticDirection === "forward"
                            accent: window.accent
                            enabled: controller.diagnosticPhase <= 0 && !controller.movementActive
                            onClicked: controller.setDiagnosticDirection("forward")
                        }
                        TacticalButton {
                            Layout.fillWidth: true
                            height: 32
                            text: "BACKWARD"
                            primary: controller.diagnosticDirection === "backward"
                            accent: window.accent
                            enabled: controller.diagnosticPhase <= 0 && !controller.movementActive
                            onClicked: controller.setDiagnosticDirection("backward")
                        }
                    }

                    TacticalButton {
                        Layout.fillWidth: true
                        height: 36
                        text: controller.diagnosticPhase < 0 ? "START AT NEUTRAL" : "RESET TO NEUTRAL"
                        accent: "#8b9ca4"
                        enabled: !controller.movementActive
                        onClicked: controller.startDiagnostic()
                    }

                    TacticalButton {
                        Layout.fillWidth: true
                        height: 36
                        text: "RUN ORIGINAL STEP"
                        accent: window.green
                        primary: true
                        enabled: !controller.movementActive
                        onClicked: controller.runOriginalStepReplay()
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 62
                        radius: 5
                        color: "#0c1519"
                        border.color: controller.diagnosticPhase < 0 ? "#46545a" : window.accent
                        Column {
                            anchors.fill: parent
                            anchors.margins: 7
                            spacing: 3
                            Text {
                                text: controller.diagnosticPhase < 0
                                      ? "NOT INITIALIZED"
                                      : controller.diagnosticPhase === controller.diagnosticPhases.length
                                        ? "SEQUENCE COMPLETE"
                                        : "HOLDING PHASE " + controller.diagnosticPhase
                                color: controller.diagnosticPhase < 0 ? window.textMuted : window.textPrimary
                                font.pixelSize: 10
                                font.bold: true
                            }
                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: controller.diagnosticPhase < 0
                                      ? "Support TARS, then start at neutral."
                                      : controller.diagnosticPhase === controller.diagnosticPhases.length
                                        ? "Restart to repeat the test."
                                        : "Choose any phase to replay the original sequence through it."
                                color: window.textMuted
                                font.pixelSize: 8
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        wrapMode: Text.WordWrap
                        text: "SAFETY\nKeep one hand ready to support TARS. A phase replays the untouched original step from neutral, then holds at that phase. DISABLE PWM releases torque immediately."
                        color: "#b6c0c4"
                        font.pixelSize: 8
                        lineHeight: 1.15
                    }

                    TacticalButton {
                        Layout.fillWidth: true
                        height: 36
                        text: "STOP ACTIVE PHASE"
                        iconText: "■"
                        accent: window.accent
                        primary: true
                        enabled: controller.movementActive
                        onClicked: controller.stopMovement()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 7
                color: "#091115"
                border.color: "#28353b"

                Text {
                    id: diagnosticTitle
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 10
                    text: controller.diagnosticDirection.toUpperCase() + " SUPPORT TRANSFER"
                    color: window.textPrimary
                    font.pixelSize: 12
                    font.bold: true
                    font.letterSpacing: 1.1
                }
                Text {
                    id: diagnosticHint
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: diagnosticTitle.bottom
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 2
                    text: "Select any phase to replay continuously from neutral through that original pose."
                    color: window.textMuted
                    font.family: "Consolas"
                    font.pixelSize: 8
                }

                GridView {
                    id: diagnosticGrid
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: diagnosticHint.bottom
                    anchors.bottom: parent.bottom
                    anchors.margins: 7
                    anchors.topMargin: 6
                    clip: true
                    model: controller.diagnosticPhases
                    cellWidth: width / 2
                    cellHeight: height / Math.ceil(Math.max(1, count) / 2)
                    interactive: false

                    delegate: Item {
                        required property var modelData
                        width: diagnosticGrid.cellWidth
                        height: diagnosticGrid.cellHeight

                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 3
                            radius: 5
                            color: modelData.selected ? Qt.rgba(window.accent.r, window.accent.g, window.accent.b, 0.13)
                                  : modelData.completed ? "#0d1b18" : "#0d1519"
                            border.width: modelData.selected ? 2 : 1
                            border.color: modelData.selected ? window.accent
                                        : modelData.completed ? window.green : "#344148"
                            opacity: controller.diagnosticPhase >= 0 ? 1.0 : 0.55

                            Row {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 8
                                Rectangle {
                                    width: 25
                                    height: 25
                                    radius: 13
                                    color: modelData.completed ? window.green
                                          : modelData.selected ? window.accent : "#263238"
                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.completed ? "✓" : modelData.index
                                        color: modelData.completed ? "#04110a" : window.textPrimary
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }
                                Column {
                                    width: parent.width - 34
                                    spacing: 2
                                    Text {
                                        width: parent.width
                                        text: modelData.name
                                        color: window.textPrimary
                                        elide: Text.ElideRight
                                        font.pixelSize: 9
                                        font.bold: true
                                    }
                                    Text {
                                        width: parent.width
                                        text: modelData.description
                                        color: window.textMuted
                                        elide: Text.ElideRight
                                        font.pixelSize: 7
                                    }
                                    Text {
                                        width: parent.width
                                        text: modelData.poseText
                                        color: modelData.selected ? window.accent : "#829097"
                                        font.family: "Consolas"
                                        font.pixelSize: 7
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: controller.diagnosticPhase >= 0 && !controller.movementActive
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: controller.runDiagnosticPhase(modelData.index)
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: actionBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 50
        color: "#080e11"
        border.color: "#1f2a2f"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: controller.statusText
                color: window.textMuted
                elide: Text.ElideRight
                font.family: "Consolas"
                font.pixelSize: 10
            }
            TacticalButton {
                Layout.preferredWidth: 112
                Layout.preferredHeight: 34
                text: controller.servoPower ? "DISABLE PWM" : "ENABLE PWM"
                iconText: "⏻"
                accent: window.accent
                enabled: !controller.powerTransition
                onClicked: controller.servoPower ? controller.disableServos() : controller.enableServos()
            }
            TacticalButton {
                Layout.preferredWidth: 105
                Layout.preferredHeight: 34
                text: "NEUTRAL"
                accent: "#8b9ca4"
                enabled: !controller.movementActive
                onClicked: controller.resetPositions()
            }
            TacticalButton {
                visible: window.currentPage === 0
                Layout.preferredWidth: 96
                Layout.preferredHeight: 34
                text: "REVERT"
                accent: "#8b9ca4"
                enabled: controller.unsavedChanges
                onClicked: controller.revertCalibration()
            }
            TacticalButton {
                visible: window.currentPage === 0
                Layout.preferredWidth: 112
                Layout.preferredHeight: 34
                text: "SAVE"
                iconText: "✓"
                accent: window.accent
                primary: true
                enabled: controller.unsavedChanges
                onClicked: controller.saveCalibration()
            }
        }
    }
}
