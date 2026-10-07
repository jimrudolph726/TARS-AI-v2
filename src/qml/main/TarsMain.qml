import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: window

    visible: controller.uiVisible
    width: initialWindowWidth
    height: initialWindowHeight
    minimumWidth: displayRotation % 180 === 0 ? 320 : 480
    minimumHeight: displayRotation % 180 === 0 ? 480 : 320
    title: "TARS-AI"
    color: "#03080a"

    readonly property color red: "#ff3852"
    readonly property color green: "#2aff8a"
    readonly property color amber: "#ffc857"
    readonly property color pale: "#edf3f5"

    background: Rectangle {
        color: "#03080a"

        Rectangle {
            anchors.fill: parent
            color: "#071014"
            opacity: 0.44
        }
    }

    Item {
        id: scene

        property string overlayMode: ""
        focus: true
        Keys.onEscapePressed: controller.exitProgram()
        readonly property bool rotated: displayRotation === 90 || displayRotation === 270
        readonly property real uiScale: Math.min(width / 480, height / 720)
        readonly property color stateColor: controller.tarsState === "STANDBY" ? "#829199"
                                            : controller.tarsState === "THINKING" ? window.amber
                                            : window.red

        width: rotated ? window.height : window.width
        height: rotated ? window.width : window.height
        anchors.centerIn: parent
        rotation: displayRotation
        clip: true

        // Low-contrast instrumentation grid, implemented with scene-graph
        // rectangles so it remains inexpensive on the Raspberry Pi.
        Repeater {
            model: Math.ceil(scene.width / Math.max(20, 28 * scene.uiScale))
            Rectangle {
                required property int index
                x: index * 28 * scene.uiScale
                y: 0
                width: 1
                height: scene.height
                color: "#29414a"
                opacity: 0.075
            }
        }
        Repeater {
            model: Math.ceil(scene.height / Math.max(20, 28 * scene.uiScale))
            Rectangle {
                required property int index
                x: 0
                y: index * 28 * scene.uiScale
                width: scene.width
                height: 1
                color: "#29414a"
                opacity: 0.075
            }
        }

        ColumnLayout {
            id: page
            anchors.fill: parent
            anchors.margins: 9 * scene.uiScale
            spacing: 7 * scene.uiScale

            TarsPanel {
                id: header
                Layout.fillWidth: true
                Layout.preferredHeight: 61 * scene.uiScale
                strongBorder: true
                accent: window.red

                Rectangle {
                    width: 3 * scene.uiScale
                    height: parent.height - 14 * scene.uiScale
                    anchors.left: parent.left
                    anchors.leftMargin: 4 * scene.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    color: window.red
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 13 * scene.uiScale
                    anchors.rightMargin: 4 * scene.uiScale
                    spacing: 6 * scene.uiScale

                    Column {
                        Layout.preferredWidth: parent.width * 0.33
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 1 * scene.uiScale

                        Text {
                            text: "TARS"
                            color: window.pale
                            font.family: displayFontFamily
                            font.pixelSize: 25 * scene.uiScale
                            font.bold: true
                            font.letterSpacing: 2.4 * scene.uiScale
                        }
                        Text {
                            visible: scene.width >= 410
                            text: "TACTICAL AUTONOMOUS SYSTEM"
                            color: "#93a4ac"
                            font.family: monoFontFamily
                            font.pixelSize: 5.5 * scene.uiScale
                            font.letterSpacing: 0.8 * scene.uiScale
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.preferredHeight: 37 * scene.uiScale
                        color: "#314149"
                    }

                    Column {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 2 * scene.uiScale

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: controller.currentTime
                            color: window.pale
                            font.family: monoFontFamily
                            font.pixelSize: 13 * scene.uiScale
                            font.bold: true
                            font.letterSpacing: 1.4 * scene.uiScale
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: controller.currentDate
                            color: "#899aa3"
                            font.family: monoFontFamily
                            font.pixelSize: 6.5 * scene.uiScale
                            font.letterSpacing: 1.2 * scene.uiScale
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.preferredHeight: 37 * scene.uiScale
                        color: "#314149"
                    }

                    Row {
                        Layout.preferredWidth: 100 * scene.uiScale
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 7 * scene.uiScale

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 1
                            Text {
                                text: "WIFI"
                                color: controller.wifiOnline ? window.green : window.red
                                font.family: monoFontFamily
                                font.pixelSize: 8 * scene.uiScale
                                font.bold: true
                            }
                            Text {
                                text: controller.wifiOnline ? "ONLINE" : "OFFLINE"
                                color: controller.wifiOnline ? window.green : window.red
                                font.family: monoFontFamily
                                font.pixelSize: 6.5 * scene.uiScale
                                font.bold: true
                            }
                        }

                        Button {
                            id: powerButton
                            width: 38 * scene.uiScale
                            height: width
                            anchors.verticalCenter: parent.verticalCenter
                            hoverEnabled: true
                            onClicked: scene.overlayMode = "power"

                            contentItem: Text {
                                text: "PWR"
                                color: window.red
                                font.pixelSize: 20 * scene.uiScale
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                            background: Rectangle {
                                radius: 5 * scene.uiScale
                                color: powerButton.down ? "#2b171d" : "#09141a"
                                border.color: powerButton.hovered ? window.red : "#24343c"
                            }
                        }
                    }
                }
            }

            TarsPanel {
                id: hero
                Layout.fillWidth: true
                Layout.preferredHeight: 224 * scene.uiScale
                accent: scene.stateColor
                strongBorder: true
                showCornerMarks: true

                Column {
                    anchors.fill: parent
                    anchors.topMargin: 10 * scene.uiScale
                    anchors.bottomMargin: 7 * scene.uiScale
                    spacing: 1 * scene.uiScale

                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 9 * scene.uiScale
                        Rectangle {
                            width: 55 * scene.uiScale
                            height: 1
                            color: scene.stateColor
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: "TARS AI"
                            color: "#aebbc1"
                            font.family: monoFontFamily
                            font.pixelSize: 8 * scene.uiScale
                            font.letterSpacing: 2.5 * scene.uiScale
                        }
                        Rectangle {
                            width: 55 * scene.uiScale
                            height: 1
                            color: scene.stateColor
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: controller.tarsState
                        color: window.pale
                        font.family: displayFontFamily
                        font.pixelSize: 31 * scene.uiScale
                        font.bold: true
                        font.letterSpacing: 5 * scene.uiScale
                    }

                    SignalCore {
                        width: parent.width
                        height: 126 * scene.uiScale
                        state: controller.tarsState
                        accent: scene.stateColor
                        uiScale: scene.uiScale
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: controller.stateDetail
                        color: "#a8b7be"
                        font.family: monoFontFamily
                        font.pixelSize: 7.5 * scene.uiScale
                        font.letterSpacing: 2.2 * scene.uiScale
                    }
                }

            }

            TarsPanel {
                id: conversationPanel
                Layout.fillWidth: true
                Layout.preferredHeight: 169 * scene.uiScale

                ListView {
                    id: conversationList
                    anchors.fill: parent
                    anchors.margins: 4 * scene.uiScale
                    spacing: 7 * scene.uiScale
                    clip: true
                    model: controller.conversationModel
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                        width: Math.max(2, 3 * scene.uiScale)
                        contentItem: Rectangle {
                            implicitWidth: 3 * scene.uiScale
                            radius: width / 2
                            color: window.red
                            opacity: 0.65
                        }
                    }

                    delegate: ConversationCard {
                        width: conversationList.width - (conversationList.ScrollBar.vertical.visible ? 7 * scene.uiScale : 0)
                        height: 70 * scene.uiScale
                        speaker: model.speaker
                        message: model.message
                        messageTime: model.messageTime
                        isTars: model.isTars
                        accent: window.red
                        uiScale: scene.uiScale
                    }

                    onCountChanged: Qt.callLater(positionViewAtEnd)
                }
            }

            TarsPanel {
                id: telemetryPanel
                Layout.fillWidth: true
                Layout.preferredHeight: 69 * scene.uiScale

                RowLayout {
                    anchors.fill: parent
                    spacing: 0

                    TelemetryTile {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        label: "BATTERY"
                        value: controller.batteryAvailable ? controller.batteryPercent + "%" : "--"
                        iconText: "B"
                        valueColor: window.green
                        uiScale: scene.uiScale
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: parent.height * 0.65; color: "#32434b" }
                    TelemetryTile {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        label: "CPU"
                        value: controller.cpuAvailable ? controller.cpuTemperature + "°C" : "--"
                        iconText: "C"
                        valueColor: controller.cpuTemperature >= 70 ? window.red : window.green
                        uiScale: scene.uiScale
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: parent.height * 0.65; color: "#32434b" }
                    TelemetryTile {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        label: "WI-FI"
                        value: controller.wifiOnline ? "ONLINE" : "OFFLINE"
                        iconText: "W"
                        valueColor: controller.wifiOnline ? window.green : window.red
                        uiScale: scene.uiScale
                    }
                }
            }

            RowLayout {
                id: nav
                Layout.fillWidth: true
                Layout.preferredHeight: 101 * scene.uiScale
                spacing: 6 * scene.uiScale

                TarsButton {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: "CAMERA"
                    iconText: "[]"
                    accent: window.red
                    onClicked: {
                        controller.activateFeature("Camera")
                        scene.overlayMode = "camera"
                    }
                }
                TarsButton {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: "APPS"
                    iconText: "::"
                    accent: window.red
                    onClicked: scene.overlayMode = "apps"
                }
                TarsButton {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: controller.muted ? "UNMUTE" : "MUTE"
                    iconText: controller.muted ? "X" : "//"
                    accent: window.red
                    selected: controller.muted
                    onClicked: controller.toggleMute()
                }
                TarsButton {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: "MENU"
                    iconText: "="
                    accent: window.red
                    onClicked: scene.overlayMode = "menu"
                }
            }
        }

        Rectangle {
            id: toast
            visible: controller.noticeText.length > 0 && scene.overlayMode.length === 0
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 118 * scene.uiScale
            width: Math.min(parent.width - 32 * scene.uiScale, toastText.implicitWidth + 30 * scene.uiScale)
            height: 30 * scene.uiScale
            radius: height / 2
            color: "#111d22"
            border.color: window.red
            opacity: visible ? 0.96 : 0

            Text {
                id: toastText
                anchors.centerIn: parent
                text: controller.noticeText
                color: "#dce5e9"
                font.family: monoFontFamily
                font.pixelSize: 7.5 * scene.uiScale
                elide: Text.ElideRight
            }

            Behavior on opacity { NumberAnimation { duration: 160 } }
        }

        Rectangle {
            id: modalOverlay
            anchors.fill: parent
            visible: scene.overlayMode.length > 0
            color: "#d903080a"
            z: 50

            MouseArea { anchors.fill: parent }

            TarsPanel {
                id: modal
                width: parent.width - 42 * scene.uiScale
                height: parent.height * 0.68
                anchors.centerIn: parent
                strongBorder: true
                accent: window.red
                showCornerMarks: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 15 * scene.uiScale
                    spacing: 10 * scene.uiScale

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 38 * scene.uiScale

                        Column {
                            Layout.fillWidth: true
                            Text {
                                text: scene.overlayMode === "camera" ? "CAMERA"
                                    : scene.overlayMode === "apps" ? "APPLICATIONS"
                                    : scene.overlayMode === "menu" ? "SYSTEM MENU"
                                    : "POWER CONTROL"
                                color: window.pale
                                font.family: displayFontFamily
                                font.pixelSize: 17 * scene.uiScale
                                font.bold: true
                                font.letterSpacing: 2 * scene.uiScale
                            }
                            Text {
                                text: "TARS-AI · NATIVE QML CONTROL"
                                color: "#91a2aa"
                                font.family: monoFontFamily
                                font.pixelSize: 6.5 * scene.uiScale
                                font.letterSpacing: 1.2 * scene.uiScale
                            }
                        }

                        TarsButton {
                            Layout.preferredWidth: 50 * scene.uiScale
                            Layout.fillHeight: true
                            text: "CLOSE"
                            iconText: "X"
                            accent: window.red
                            onClicked: scene.overlayMode = ""
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: window.red
                        opacity: 0.65
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Column {
                            anchors.centerIn: parent
                            visible: scene.overlayMode === "camera"
                            spacing: 14 * scene.uiScale

                            Rectangle {
                                width: modal.width - 70 * scene.uiScale
                                height: 205 * scene.uiScale
                                anchors.horizontalCenter: parent.horizontalCenter
                                radius: 6 * scene.uiScale
                                color: "#03090c"
                                border.color: "#42606c"

                                Repeater {
                                    model: 4
                                    Rectangle {
                                        required property int index
                                        width: index % 2 === 0 ? parent.width * 0.26 : 1
                                        height: index % 2 === 0 ? 1 : parent.height * 0.32
                                        x: index === 0 ? 0 : index === 2 ? parent.width * 0.74 : parent.width / 2
                                        y: index === 1 ? 0 : index === 3 ? parent.height * 0.68 : parent.height / 2
                                        color: window.red
                                        opacity: 0.35
                                    }
                                }
                                Rectangle {
                                    width: 56 * scene.uiScale
                                    height: width
                                    radius: width / 2
                                    anchors.centerIn: parent
                                    color: "transparent"
                                    border.color: window.red
                                    opacity: 0.7
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 12 * scene.uiScale
                                    text: "CAMERA MODULE"
                                    color: "#9babb3"
                                    font.family: monoFontFamily
                                    font.pixelSize: 8 * scene.uiScale
                                    font.letterSpacing: 1.3 * scene.uiScale
                                }
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "Live camera migration is the next interface module"
                                color: "#9babb3"
                                font.family: monoFontFamily
                                font.pixelSize: 8 * scene.uiScale
                            }
                        }

                        GridLayout {
                            anchors.fill: parent
                            visible: scene.overlayMode === "apps"
                            columns: 2
                            rowSpacing: 9 * scene.uiScale
                            columnSpacing: 9 * scene.uiScale

                            Repeater {
                                model: [
                                    { "label": "AVATAR", "icon": "T" },
                                    { "label": "CLOCK", "icon": "CLK" },
                                    { "label": "REMOTE", "icon": "RMT" },
                                    { "label": "SERVO TEST", "icon": "SRV" }
                                ]
                                delegate: TarsButton {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    text: modelData.label
                                    iconText: modelData.icon
                                    accent: window.red
                                    onClicked: {
                                        controller.launchApp(modelData.label)
                                        scene.overlayMode = ""
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            visible: scene.overlayMode === "menu"
                            spacing: 8 * scene.uiScale

                            TarsButton {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                text: "SYSTEM STATUS"
                                iconText: "SYS"
                                accent: window.red
                                onClicked: {
                                    controller.activateFeature("System status")
                                    scene.overlayMode = ""
                                }
                            }
                            TarsButton {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                text: controller.wifiOnline
                                    ? "WI-FI · " + (controller.wifiSsid.length > 0 ? controller.wifiSsid : "ONLINE")
                                    : "WI-FI · OFFLINE"
                                iconText: "WIFI"
                                accent: window.red
                                onClicked: {
                                    controller.activateFeature("Wi-Fi")
                                    scene.overlayMode = ""
                                }
                            }
                            TarsButton {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                text: "EXIT TARS"
                                iconText: "EXIT"
                                accent: window.red
                                onClicked: {
                                    scene.overlayMode = ""
                                    controller.exitProgram()
                                }
                            }
                        }

                        Column {
                            anchors.centerIn: parent
                            visible: scene.overlayMode === "power"
                            width: parent.width
                            spacing: 18 * scene.uiScale

                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "PWR"
                                color: window.red
                                font.pixelSize: 58 * scene.uiScale
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "SHUT DOWN TARS?"
                                color: window.pale
                                font.family: displayFontFamily
                                font.pixelSize: 18 * scene.uiScale
                                font.bold: true
                                font.letterSpacing: 2 * scene.uiScale
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "This will safely stop TARS and power off the Raspberry Pi."
                                color: "#97a7ae"
                                font.family: monoFontFamily
                                font.pixelSize: 8 * scene.uiScale
                            }
                            Row {
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 10 * scene.uiScale
                                TarsButton {
                                    width: 130 * scene.uiScale
                                    height: 62 * scene.uiScale
                                    text: "CANCEL"
                                    iconText: "<"
                                    accent: "#829199"
                                    onClicked: scene.overlayMode = ""
                                }
                                TarsButton {
                                    width: 170 * scene.uiScale
                                    height: 62 * scene.uiScale
                                    text: "SHUT DOWN"
                                    iconText: "PWR"
                                    accent: window.red
                                    selected: true
                                    onClicked: {
                                        controller.requestShutdown()
                                        scene.overlayMode = ""
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: !controller.runtimeReady
            color: "#e603080a"
            z: 80

            Column {
                anchors.centerIn: parent
                width: parent.width - 56 * scene.uiScale
                spacing: 18 * scene.uiScale

                SignalCore {
                    width: parent.width
                    height: 132 * scene.uiScale
                    state: "BOOTING"
                    accent: window.red
                    uiScale: scene.uiScale
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "INITIALIZING TARS"
                    color: window.pale
                    font.family: displayFontFamily
                    font.pixelSize: 22 * scene.uiScale
                    font.bold: true
                    font.letterSpacing: 3 * scene.uiScale
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: controller.runtimeStatus
                    color: "#9eb0b8"
                    font.family: monoFontFamily
                    font.pixelSize: 8 * scene.uiScale
                    font.letterSpacing: 1.2 * scene.uiScale
                }
                TarsButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 150 * scene.uiScale
                    height: 54 * scene.uiScale
                    text: "EXIT"
                    iconText: "X"
                    accent: window.red
                    onClicked: controller.exitProgram()
                }
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: controller.overlayVisible
            color: "#f003080a"
            z: 100

            Image {
                anchors.fill: parent
                anchors.margins: 12 * scene.uiScale
                source: controller.overlaySource
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                cache: false
            }
        }
    }
}
