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

    Keys.onEscapePressed: window.close()

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
                Layout.preferredWidth: 138
                Layout.preferredHeight: 28
                radius: 5
                color: "#0e171b"
                border.color: controller.hardwareConnected ? window.green : "#59666c"
                Text {
                    anchors.centerIn: parent
                    text: controller.hardwareModeText
                    color: controller.hardwareConnected ? window.green : "#a8b2b7"
                    font.family: "Consolas"
                    font.pixelSize: 11
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
                model: ["CALIBRATION", "MOVEMENTS"]
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
                        onClicked: window.currentPage = index
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
            }
            CalibrationSide {
                Layout.fillWidth: true
                Layout.fillHeight: true
                servoModel: controller.rightServos
                sideName: "RIGHT"
                panelAccent: window.accent
            }
        }

        RowLayout {
            anchors.fill: parent
            spacing: 10
            visible: window.currentPage === 1

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
                text: controller.servoPower ? "POWER OFF" : "POWER ON"
                iconText: "⏻"
                accent: window.accent
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
