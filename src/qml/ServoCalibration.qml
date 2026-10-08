import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 1440
    height: 900
    minimumWidth: 320
    minimumHeight: 200
    title: "TARS Servo Calibration"
    color: "#03080a"

    readonly property color red: "#ff3852"
    readonly property color green: "#2aff8a"
    readonly property color pale: "#dbe4e8"
    readonly property real designWidth: 1440
    readonly property real designHeight: 900
    readonly property real interfaceScale: Math.min(width / designWidth, height / designHeight)
    readonly property real outerMargin: 13
    readonly property real headerHeight: 74
    readonly property real footerHeight: 194

    background: Rectangle {
        color: "#03080a"
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#071014" }
            GradientStop { position: 0.55; color: "#03080a" }
            GradientStop { position: 1.0; color: "#050b0e" }
        }
    }

    // The dashboard was designed at 1440x900. Scale the entire logical canvas
    // uniformly so it fits smaller Pi displays (including 800x480) without
    // cropping either side or changing pointer/drag coordinates.
    Item {
        id: designSurface
        width: window.designWidth
        height: window.designHeight
        anchors.centerIn: parent
        scale: window.interfaceScale
        transformOrigin: Item.Center
        focus: true
        Keys.onEscapePressed: window.close()

    Rectangle {
        id: topBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: window.headerHeight
        color: "#050c0f"

        Rectangle {
            width: 3
            height: parent.height - 18
            anchors.left: parent.left
            anchors.leftMargin: 13
            anchors.verticalCenter: parent.verticalCenter
            color: window.red
        }

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 38
            anchors.verticalCenter: parent.verticalCenter
            spacing: 15

            Text {
                text: "TARS"
                color: "#eef3f5"
                font.family: "Segoe UI"
                font.pixelSize: Math.max(30, window.headerHeight * 0.52)
                font.bold: true
                font.letterSpacing: 3
            }
            Rectangle { width: 1; height: 45; color: "#314047" }
            Text {
                text: "TACTICAL\nAUTONOMOUS\nRECONNAISSANCE\nSYSTEM"
                color: "#a7b2b7"
                font.family: "Consolas"
                font.pixelSize: 9
                font.letterSpacing: 2.4
                lineHeight: 1.08
            }
        }

        Column {
            anchors.centerIn: parent
            spacing: 7
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "SERVO CALIBRATION"
                color: "#edf2f4"
                font.family: "Segoe UI"
                font.pixelSize: Math.max(23, window.headerHeight * 0.36)
                font.bold: true
                font.letterSpacing: 3
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 450
                height: 2
                color: window.red
                opacity: 0.8
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "SIDE ALIGNMENT  ·  ARM TUNING  ·  MOTION TEST"
                color: "#9ba7ad"
                font.family: "Consolas"
                font.pixelSize: 9
                font.letterSpacing: 2.7
            }
        }

        Column {
            anchors.right: parent.right
            anchors.rightMargin: 30
            anchors.verticalCenter: parent.verticalCenter
            spacing: 5
            Text {
                anchors.right: parent.right
                text: "CASE  ·  ENDURANCE  ·  LOYALTY  ·  HUMOUR"
                color: "#9eabb1"
                font.family: "Consolas"
                font.pixelSize: 8
                font.letterSpacing: 1.5
            }
            Text {
                anchors.right: parent.right
                text: "\"A BETTER TOMORROW.\""
                color: "#c5cdd1"
                font.family: "Consolas"
                font.pixelSize: 9
                font.letterSpacing: 2.2
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: "#26343a"
        }
    }

    RowLayout {
        id: mainRow
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: topBar.bottom
        anchors.bottom: statusBar.top
        anchors.margins: window.outerMargin
        spacing: 10

        CalibrationSide {
            Layout.fillHeight: true
            Layout.preferredWidth: 420
            Layout.minimumWidth: 315
            servoModel: controller.leftServos
            sideName: "LEFT"
            panelAccent: window.red
        }

        Rectangle {
            id: digitalTwin
            Layout.fillHeight: true
            Layout.fillWidth: true
            Layout.minimumWidth: 360
            color: "#050d10"
            radius: 7
            border.width: 1
            border.color: window.red
            clip: true

            Canvas {
                anchors.fill: parent
                opacity: 0.25
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.strokeStyle = "#294047"
                    ctx.lineWidth = 1
                    for (let x = 0; x < width; x += 24) {
                        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
                    }
                    for (let y = 0; y < height; y += 24) {
                        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke()
                    }
                }
            }

            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 10
                width: 130
                height: 43
                color: "#071014"
                border.color: "#314047"
                Text {
                    anchors.centerIn: parent
                    text: "FRONT VIEW\nDIGITAL TWIN"
                    color: "#b9c3c8"
                    horizontalAlignment: Text.AlignHCenter
                    font.family: "Consolas"
                    font.pixelSize: 9
                    font.letterSpacing: 1.8
                }
            }

            Image {
                id: robotImage
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: twinCaption.top
                anchors.margins: 22
                source: controller.tarsImageUrl
                fillMode: Image.PreserveAspectFit
                mipmap: true
                opacity: 0.72
            }

            Rectangle {
                anchors.left: robotImage.left
                anchors.bottom: twinCaption.top
                anchors.bottomMargin: 10
                width: Math.max(4, robotImage.width * 0.028)
                height: robotImage.height * 0.34
                color: window.red
                opacity: 0.48
            }
            Rectangle {
                anchors.right: robotImage.right
                anchors.bottom: twinCaption.top
                anchors.bottomMargin: 10
                width: Math.max(4, robotImage.width * 0.028)
                height: robotImage.height * 0.34
                color: window.red
                opacity: 0.48
            }

            Item {
                id: twinCaption
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 60

                Rectangle {
                    anchors.fill: parent
                    color: "#050c0f"
                    opacity: 0.94
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: 8
                    text: "TARS"
                    color: "#eef3f5"
                    font.family: "Segoe UI"
                    font.pixelSize: 22
                    font.bold: true
                    font.letterSpacing: 3
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 7
                    text: controller.hardwareConnected
                          ? "ALL SERVOS  ·  PCA9685 CONNECTED  ·  LIVE CALIBRATION"
                          : "ALL SERVOS  ·  MOCK HARDWARE  ·  SAFE PREVIEW"
                    color: "#9faab0"
                    font.family: "Consolas"
                    font.pixelSize: 8
                    font.letterSpacing: 1.8
                }
            }
        }

        CalibrationSide {
            Layout.fillHeight: true
            Layout.preferredWidth: 420
            Layout.minimumWidth: 315
            servoModel: controller.rightServos
            sideName: "RIGHT"
            panelAccent: window.red
        }
    }

    RowLayout {
        id: footer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: window.outerMargin
        anchors.rightMargin: window.outerMargin
        anchors.bottomMargin: window.outerMargin
        height: window.footerHeight - window.outerMargin
        spacing: 10

        Panel {
            Layout.fillHeight: true
            Layout.preferredWidth: 490
            Layout.minimumWidth: 370
            title: "MOVEMENT TEST"
            subtitle: "TEST BASIC MOVEMENTS"
            iconText: "▷"
            accent: window.red

            contentItem: Row {
                anchors.fill: parent
                spacing: 8
                Repeater {
                    model: [
                        { "label": "STEP\nFORWARD", "icon": "↑", "command": "Step Forward" },
                        { "label": "WALK\nFORWARD", "icon": "⇈", "command": "Walk Forward" },
                        { "label": "TURN\nLEFT", "icon": "↶", "command": "Turn Left" },
                        { "label": "TURN\nRIGHT", "icon": "↷", "command": "Turn Right" }
                    ]
                    delegate: TacticalButton {
                        required property var modelData
                        width: (parent.width - 24) / 4
                        height: parent.height
                        text: modelData.label
                        iconText: modelData.icon
                        accent: index === 0 ? window.red : "#819099"
                        primary: index === 0
                        onClicked: controller.runMovement(modelData.command)
                    }
                }
            }
        }

        Panel {
            Layout.fillHeight: true
            Layout.fillWidth: true
            Layout.minimumWidth: 425
            title: "SYSTEM STATUS"
            subtitle: "HARDWARE & POWER MONITORING"
            iconText: "⌁"
            accent: window.red

            contentItem: Column {
                anchors.fill: parent
                spacing: 8

                Row {
                    width: parent.width
                    height: 58
                    spacing: 7

                    Repeater {
                        model: [
                            { "title": "BATTERY", "value": controller.batteryPercent + "%  " + controller.batteryVoltage.toFixed(2) + "V", "ok": true },
                            { "title": "SERVO POWER", "value": controller.servoPower ? "ACTIVE" : "DISABLED", "ok": controller.servoPower },
                            { "title": "PCA9685", "value": controller.hardwareModeText, "ok": controller.hardwareConnected },
                            { "title": "INA260", "value": "MOCK CONNECTED", "ok": true }
                        ]
                        delegate: Rectangle {
                            required property var modelData
                            width: (parent.width - 21) / 4
                            height: parent.height
                            color: "#0b1418"
                            radius: 5
                            border.color: "#26353b"

                            Column {
                                anchors.centerIn: parent
                                spacing: 4
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: modelData.title
                                    color: "#9daab0"
                                    font.family: "Consolas"
                                    font.pixelSize: 8
                                    font.letterSpacing: 0.9
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: modelData.value
                                    color: modelData.ok ? window.green : window.red
                                    font.family: "Segoe UI"
                                    font.pixelSize: 10
                                    font.bold: true
                                }
                            }
                        }
                    }
                }

                Row {
                    width: parent.width
                    height: parent.height - 66
                    spacing: 8

                    ComboBox {
                        id: profileBox
                        width: parent.width * 0.47
                        height: parent.height
                        model: ["Default", "Fine Tuning", "Factory Safe"]
                        currentIndex: Math.max(0, model.indexOf(controller.activeProfile))
                        onActivated: controller.setProfile(currentText)

                        contentItem: Text {
                            leftPadding: 12
                            rightPadding: 28
                            text: profileBox.displayText
                            color: window.pale
                            verticalAlignment: Text.AlignVCenter
                            font.family: "Segoe UI"
                            font.pixelSize: 10
                            font.bold: true
                        }
                        background: Rectangle {
                            radius: 5
                            color: "#0b1418"
                            border.color: profileBox.activeFocus ? window.red : "#26353b"
                        }
                        indicator: Text {
                            x: profileBox.width - width - 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: "⌄"
                            color: "#aeb9be"
                            font.pixelSize: 16
                        }
                        delegate: ItemDelegate {
                            required property var modelData
                            width: profileBox.width
                            height: 34
                            contentItem: Text {
                                text: parent.modelData
                                color: parent.highlighted ? "#ffffff" : "#b8c2c7"
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: 10
                            }
                            background: Rectangle {
                                color: parent.highlighted ? "#302027" : "#0b1418"
                            }
                        }
                        popup: Popup {
                            y: profileBox.height + 2
                            width: profileBox.width
                            implicitHeight: contentItem.implicitHeight + 2
                            padding: 1
                            contentItem: ListView {
                                implicitHeight: contentHeight
                                model: profileBox.popup.visible ? profileBox.delegateModel : null
                                currentIndex: profileBox.highlightedIndex
                            }
                            background: Rectangle {
                                color: "#0b1418"
                                border.color: window.red
                                radius: 5
                            }
                        }
                    }

                    Rectangle {
                        width: parent.width - profileBox.width - 8
                        height: parent.height
                        radius: 5
                        color: "#0b1418"
                        border.color: controller.unsavedChanges ? window.red : "#26353b"
                        Row {
                            anchors.centerIn: parent
                            spacing: 9
                            Text { text: controller.unsavedChanges ? "▣" : "✓"; color: controller.unsavedChanges ? window.red : window.green; font.pixelSize: 19 }
                            Column {
                                Text { text: "UNSAVED CHANGES"; color: "#9daab0"; font.pixelSize: 8; font.letterSpacing: 1 }
                                Text { text: controller.unsavedChanges ? "Yes · review before saving" : "No · profile synchronized"; color: window.pale; font.pixelSize: 10 }
                            }
                        }
                    }
                }
            }
        }

        Panel {
            Layout.fillHeight: true
            Layout.preferredWidth: 365
            Layout.minimumWidth: 310
            title: "CALIBRATION ACTIONS"
            subtitle: "SAVE, LOAD AND SERVO CONTROL"
            iconText: "⚙"
            accent: window.red

            contentItem: GridLayout {
                anchors.fill: parent
                columns: 2
                rowSpacing: 8
                columnSpacing: 8

                TacticalButton {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    text: controller.servoPower ? "DISABLE SERVOS" : "ENABLE SERVOS"
                    iconText: "⏻"; accent: window.red; primary: true
                    onClicked: controller.servoPower ? controller.disableServos() : controller.enableServos()
                }
                TacticalButton {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    text: "RESET POSITION"; iconText: "↶"; accent: "#a9b5bb"
                    onClicked: controller.resetPositions()
                }
                TacticalButton {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    text: "REVERT"; iconText: "↩"; accent: "#a9b5bb"; enabled: controller.unsavedChanges
                    onClicked: controller.revertCalibration()
                }
                TacticalButton {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    text: "SAVE CALIBRATION"; iconText: "▣"; accent: window.red; primary: true; enabled: controller.unsavedChanges
                    onClicked: controller.saveCalibration()
                }
            }
        }
    }

    Rectangle {
        id: statusBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: footer.top
        anchors.leftMargin: window.outerMargin
        anchors.rightMargin: window.outerMargin
        anchors.bottomMargin: 3
        height: 20
        radius: 3
        color: "#071014"
        border.color: "#1d2a30"
        Text {
            anchors.centerIn: parent
            text: controller.statusText
            color: "#aebac0"
            font.family: "Consolas"
            font.pixelSize: 9
            font.letterSpacing: 0.8
        }
    }
    }
}
