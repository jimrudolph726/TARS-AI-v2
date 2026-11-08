import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/UiTokens.js" as Ui
import "AppRegistry.js" as AppRegistry

ApplicationWindow {
    id: window

    visible: controller.uiVisible
    width: initialWindowWidth
    height: initialWindowHeight
    minimumWidth: displayRotation % 180 === 0 ? 320 : 480
    minimumHeight: displayRotation % 180 === 0 ? 480 : 320
    title: "TARS-AI"
    color: Ui.background

    readonly property color red: Ui.red
    readonly property color green: Ui.green
    readonly property color amber: Ui.amber
    readonly property color pale: Ui.textPrimary

    background: Rectangle {
        color: Ui.background

        Rectangle {
            anchors.fill: parent
            color: "#071014"
            opacity: 0.44
        }
    }

    Item {
        id: scene
        objectName: "scene"

        property string overlayMode: ""
        property string activeAppId: ""
        property string appReturnMode: "apps"
        property string confirmationAction: ""
        readonly property string confirmationTitle: confirmationAction === "servo" ? "OPEN SERVO CALIBRATION?"
            : confirmationAction === "restart" ? "RESTART TARS?"
            : confirmationAction === "exit" ? "EXIT TARS APPLICATION?"
            : "SHUT DOWN RASPBERRY PI?"
        readonly property string confirmationMessage: confirmationAction === "servo"
            ? "TARS will stop listening, cancel movement, disable every PWM output, and release the servo controller before opening the tester. Support the robot before continuing."
            : confirmationAction === "restart"
            ? "TARS will stop cleanly and restart the application. The Raspberry Pi will remain powered on."
            : confirmationAction === "exit"
            ? "TARS will stop cleanly and return to the Raspberry Pi desktop. The Raspberry Pi will remain powered on."
            : "TARS will stop cleanly and power off the Raspberry Pi."
        readonly property string confirmationButtonText: confirmationAction === "servo" ? "OPEN TESTER"
            : confirmationAction === "restart" ? "RESTART"
            : confirmationAction === "exit" ? "EXIT APP"
            : "SHUT DOWN"
        readonly property string confirmationIcon: confirmationAction === "servo" ? "SRV"
            : confirmationAction === "restart" ? "RST"
            : confirmationAction === "exit" ? "EXIT"
            : "PWR"

        function openConfirmation(action) {
            confirmationAction = action
            overlayMode = "confirm"
        }

        function openApp(appName, returnMode) {
            var definition = AppRegistry.find(appName)
            if (!definition || !definition.enabled)
                return
            activeAppId = appName
            appReturnMode = returnMode || "apps"
            overlayMode = "app"
        }

        function closeApp() {
            activeAppId = ""
            overlayMode = appReturnMode
            appReturnMode = "apps"
        }

        function retryActiveApp() {
            var requestedApp = activeAppId
            activeAppId = ""
            Qt.callLater(function() { scene.activeAppId = requestedApp })
        }

        function launcherBadge(app) {
            if (app.badgeKey === "health") {
                if (!controller.runtimeReady)
                    return "WAIT"
                var groups = [controller.hardwareDiagnostics, controller.softwareDiagnostics]
                for (var groupIndex = 0; groupIndex < groups.length; ++groupIndex) {
                    for (var itemIndex = 0; itemIndex < groups[groupIndex].length; ++itemIndex) {
                        if (groups[groupIndex][itemIndex].state === "error")
                            return "CHECK"
                    }
                }
                return "GOOD"
            }
            if (app.badgeKey === "dashboard") {
                if (controller.dashboardLoading)
                    return "SYNC"
                if (controller.dashboardError.length)
                    return "ERROR"
                return controller.dashboardLastUpdated.length ? "LIVE" : "READY"
            }
            if (app.badgeKey === "remote") {
                if (controller.remoteState === "active" || controller.remoteState === "hotspot")
                    return "ONLINE"
                if (controller.remoteState === "error")
                    return "ERROR"
                if (controller.remoteState === "scanning" || controller.remoteState === "starting")
                    return "WAIT"
                return "READY"
            }
            if (app.badgeKey === "avatar")
                return controller.avatarFrameSource.length > 0 ? "LIVE" : "SETUP"
            return app.badgeKey === "live" ? "LIVE" : "READY"
        }

        function launcherBadgeColor(app) {
            var badge = launcherBadge(app)
            if (badge === "ERROR")
                return window.red
            if (badge === "WAIT" || badge === "SETUP" || badge === "SYNC" || badge === "CHECK")
                return window.amber
            return window.green
        }

        function executeConfirmation() {
            var action = confirmationAction
            confirmationAction = ""
            overlayMode = ""
            if (action === "servo")
                controller.launchServoCalibration()
            else if (action === "restart")
                controller.requestRestart()
            else if (action === "exit")
                controller.exitProgram()
            else if (action === "shutdown")
                controller.requestShutdown()
        }

        focus: true
        Keys.onEscapePressed: {
            if (scene.overlayMode === "app") {
                scene.closeApp()
            } else if (scene.overlayMode.length > 0) {
                if (scene.overlayMode === "camera")
                    controller.closeCamera()
                scene.confirmationAction = ""
                scene.overlayMode = ""
            } else {
                scene.openConfirmation("exit")
            }
        }
        readonly property bool rotated: displayRotation === 90 || displayRotation === 270
        // Scale from the 480x720 portrait design canvas, but cap growth so a
        // fullscreen/VNC surface gains breathing room instead of giant type.
        readonly property real uiScale: Ui.clampedScale(width, height)
        readonly property real contentScale: Ui.contentScale(uiScale)
        readonly property real controlScale: Math.max(0.82, contentScale)
        readonly property real touchTarget: Math.max(Ui.touchMin, Ui.touchMin * controlScale)
        readonly property real comfortableTouchTarget: Math.max(Ui.touchComfortable,
                                                                  Ui.touchComfortable * controlScale)
        readonly property real modalMargin: Math.max(Ui.spaceLg, Ui.spaceXl * contentScale)
        readonly property bool runtimeFailed: controller.runtimeStatus.toUpperCase().indexOf("FAILED") >= 0
            || controller.runtimeStatus.toUpperCase().indexOf("ERROR") >= 0
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
            anchors.margins: Ui.spaceMd * scene.uiScale
            spacing: Ui.spaceSm * scene.uiScale

            TarsPanel {
                id: header
                uiScale: scene.uiScale
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(61 * scene.uiScale,
                                                 scene.touchTarget + 2 * Ui.spaceSm * scene.uiScale)
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
                        Layout.preferredWidth: scene.width < 400
                            ? scene.touchTarget
                            : 100 * scene.uiScale
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 7 * scene.uiScale

                        Column {
                            visible: scene.width >= 400
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
                            width: scene.touchTarget
                            height: width
                            anchors.verticalCenter: parent.verticalCenter
                            hoverEnabled: true
                            onClicked: scene.openConfirmation("shutdown")

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
                uiScale: scene.uiScale
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
                        audioLevels: controller.audioLevels
                        audioLevel: controller.audioLevel
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
                uiScale: scene.uiScale
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: 207 * scene.uiScale

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
                        height: 89 * scene.uiScale
                        speaker: model.speaker
                        message: model.message
                        messageTime: model.messageTime
                        isTars: model.isTars
                        accent: window.red
                        uiScale: scene.uiScale
                    }

                    onCountChanged: Qt.callLater(positionViewAtEnd)
                }

                AppStateView {
                    anchors.fill: parent
                    anchors.margins: Ui.spaceMd * scene.uiScale
                    visible: conversationList.count === 0 && controller.runtimeReady
                    state: "empty"
                    title: "NO CONVERSATION YET"
                    detail: "Say “Hey TARS” to begin a conversation."
                    iconText: "T"
                    accent: "#829199"
                    uiScale: scene.contentScale
                }
            }

            TarsPanel {
                id: telemetryPanel
                uiScale: scene.uiScale
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
                Layout.minimumHeight: scene.touchTarget
                Layout.preferredHeight: scene.touchTarget
                Layout.maximumHeight: scene.touchTarget
                spacing: Ui.spaceSm * scene.controlScale

                TarsButton {
                    uiScale: scene.contentScale
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    text: "CAMERA"
                    iconText: "[]"
                    iconPixelSize: 15 * scene.controlScale
                    labelPixelSize: 7 * scene.controlScale
                    accent: window.red
                    onClicked: {
                        controller.openCamera()
                        scene.overlayMode = "camera"
                    }
                }
                TarsButton {
                    uiScale: scene.contentScale
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    text: "APPS"
                    iconText: "::"
                    iconPixelSize: 15 * scene.controlScale
                    labelPixelSize: 7 * scene.controlScale
                    accent: window.red
                    onClicked: scene.overlayMode = "apps"
                }
                TarsButton {
                    uiScale: scene.contentScale
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    text: controller.muted ? "UNMUTE" : "MUTE"
                    iconText: controller.muted ? "X" : "//"
                    iconPixelSize: 15 * scene.controlScale
                    labelPixelSize: 7 * scene.controlScale
                    accent: window.red
                    selected: controller.muted
                    onClicked: controller.toggleMute()
                }
                TarsButton {
                    uiScale: scene.contentScale
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    text: "MENU"
                    iconText: "="
                    iconPixelSize: 15 * scene.controlScale
                    labelPixelSize: 7 * scene.controlScale
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
                uiScale: scene.contentScale
                width: Math.min(parent.width - 2 * scene.modalMargin, 680 * scene.uiScale)
                height: scene.overlayMode === "app"
                    ? Math.min(parent.height - 2 * scene.modalMargin, 760 * scene.uiScale)
                    : scene.overlayMode === "apps"
                        ? Math.min(parent.height - 2 * scene.modalMargin, 330 * scene.controlScale)
                    : scene.overlayMode === "menu"
                        ? Math.min(parent.height - 2 * scene.modalMargin, 360 * scene.controlScale)
                    : scene.overlayMode === "confirm"
                        ? Math.min(parent.height - 2 * scene.modalMargin, 330 * scene.controlScale)
                    : Math.min(parent.height - 2 * scene.modalMargin, 760 * scene.uiScale)
                anchors.centerIn: parent
                strongBorder: true
                accent: window.red
                showCornerMarks: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Ui.spaceLg * scene.controlScale
                    spacing: Ui.spaceMd * scene.controlScale

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: scene.touchTarget

                        Column {
                            Layout.fillWidth: true
                            Text {
                                text: scene.overlayMode === "camera" ? "CAMERA"
                                    : scene.overlayMode === "apps" ? "APPLICATIONS"
                                    : scene.overlayMode === "app" ? AppRegistry.titleFor(scene.activeAppId)
                                    : scene.overlayMode === "menu" ? "SYSTEM MENU"
                                    : scene.overlayMode === "confirm" ? "CONFIRM ACTION"
                                    : "SYSTEM CONTROL"
                                color: window.pale
                                font.family: displayFontFamily
                                font.pixelSize: Ui.textTitle * scene.contentScale
                                font.bold: true
                                font.letterSpacing: 2 * scene.controlScale
                            }
                            Text {
                                text: "TARS-AI · NATIVE QML CONTROL"
                                color: "#91a2aa"
                                font.family: monoFontFamily
                                font.pixelSize: Ui.textCaption * scene.contentScale
                                font.letterSpacing: 1.2 * scene.controlScale
                            }
                        }

                        Button {
                            id: closeOverlayButton
                            Layout.preferredWidth: 88 * scene.controlScale
                            Layout.preferredHeight: scene.touchTarget
                            Layout.alignment: Qt.AlignVCenter
                            hoverEnabled: true
                            onClicked: {
                                if (scene.overlayMode === "camera")
                                    controller.closeCamera()
                                if (scene.overlayMode === "app") {
                                    scene.closeApp()
                                } else {
                                    scene.activeAppId = ""
                                    scene.appReturnMode = "apps"
                                    scene.confirmationAction = ""
                                    scene.overlayMode = ""
                                }
                            }

                            contentItem: Row {
                                anchors.centerIn: parent
                                spacing: 5 * scene.controlScale
                                Text {
                                    text: scene.overlayMode === "app" ? "‹" : "×"
                                    color: window.red
                                    font.family: displayFontFamily
                                    font.pixelSize: 11 * scene.contentScale
                                    font.bold: true
                                }
                                Text {
                                    text: scene.overlayMode === "app" ? "BACK" : "CLOSE"
                                    color: window.pale
                                    font.family: displayFontFamily
                                    font.pixelSize: Ui.textSmall * scene.contentScale
                                    font.bold: true
                                    font.letterSpacing: 0.7 * scene.controlScale
                                }
                            }
                            background: Rectangle {
                                radius: 4 * scene.controlScale
                                color: closeOverlayButton.down ? "#2b171d" : "#09141a"
                                border.color: window.red
                            }
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

                        Rectangle {
                            anchors.fill: parent
                            visible: scene.overlayMode === "camera"
                            radius: 6 * scene.uiScale
                            color: "#03090c"
                            border.color: controller.cameraReady ? window.red : "#42606c"
                            clip: true

                            Item {
                                id: cameraFeed
                                anchors.fill: parent
                                anchors.margins: 2 * scene.uiScale
                                visible: controller.cameraReady

                                // The display is mounted in portrait orientation. Swap the
                                // source dimensions before rotating so the feed fills the
                                // viewport without being stretched or clipped incorrectly.
                                Image {
                                    id: rotatedCameraImage
                                    width: parent.height
                                    height: parent.width
                                    anchors.centerIn: parent
                                    rotation: 90
                                    source: controller.cameraReady
                                        ? "image://camera/frame/" + controller.cameraFrameRevision
                                        : ""
                                    cache: false
                                    asynchronous: false
                                    fillMode: Image.PreserveAspectCrop
                                }
                            }

                            Repeater {
                                model: controller.cameraReady ? 4 : 0
                                Rectangle {
                                    required property int index
                                    width: index % 2 === 0 ? parent.width * 0.18 : 1
                                    height: index % 2 === 0 ? 1 : parent.height * 0.22
                                    x: index === 0 ? 0 : index === 2 ? parent.width * 0.82 : parent.width / 2
                                    y: index === 1 ? 0 : index === 3 ? parent.height * 0.78 : parent.height / 2
                                    color: window.red
                                    opacity: 0.55
                                }
                            }

                            AppStateView {
                                anchors.fill: parent
                                visible: !controller.cameraReady
                                state: controller.cameraError.length ? "error"
                                    : controller.cameraActive ? "loading" : "empty"
                                title: controller.cameraError.length ? "CAMERA UNAVAILABLE"
                                    : controller.cameraActive ? "STARTING CAMERA" : "CAMERA INACTIVE"
                                detail: controller.cameraError.length ? controller.cameraError
                                    : controller.cameraActive
                                        ? "Waiting for the first optical frame."
                                        : "Start the camera to open the live optical feed."
                                actionText: controller.cameraError.length ? "RETRY CAMERA"
                                    : controller.cameraActive ? "" : "START CAMERA"
                                actionIcon: "CAM"
                                accent: controller.cameraError.length ? window.red : "#829199"
                                uiScale: scene.contentScale
                                onActionTriggered: controller.openCamera()
                            }

                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                height: 24 * scene.uiScale
                                color: "#b003090c"
                                visible: controller.cameraReady
                                Text {
                                    anchors.centerIn: parent
                                    text: "LIVE OPTICAL FEED  ·  " + rotatedCameraImage.sourceSize.width + "×" + rotatedCameraImage.sourceSize.height
                                    color: "#d5dfe3"
                                    font.family: monoFontFamily
                                    font.pixelSize: 6.5 * scene.uiScale
                                    font.letterSpacing: 1.1 * scene.uiScale
                                }
                            }
                        }

                        GridLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            visible: scene.overlayMode === "apps"
                            columns: 2
                            rowSpacing: 7 * scene.controlScale
                            columnSpacing: 7 * scene.controlScale

                            Repeater {
                                model: AppRegistry.applications
                                delegate: TarsButton {
                                    required property var modelData
                                    uiScale: scene.contentScale
                                    dense: true
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    Layout.preferredWidth: 1
                                    Layout.minimumHeight: scene.touchTarget
                                    Layout.preferredHeight: scene.touchTarget
                                    Layout.maximumHeight: scene.touchTarget
                                    text: modelData.title
                                    iconText: modelData.icon
                                    badgeText: scene.launcherBadge(modelData)
                                    badgeColor: scene.launcherBadgeColor(modelData)
                                    iconPixelSize: 12 * scene.controlScale
                                    labelPixelSize: 6.5 * scene.controlScale
                                    accent: window.red
                                    enabled: modelData.enabled
                                    onClicked: scene.openApp(modelData.id, "apps")
                                }
                            }
                        }

                        Loader {
                            id: appLoader
                            anchors.fill: parent
                            visible: scene.overlayMode === "app"
                            active: visible
                            source: AppRegistry.sourceFor(scene.activeAppId)
                            onLoaded: {
                                if (item && item.hasOwnProperty("uiScale"))
                                    item.uiScale = Qt.binding(function() { return scene.contentScale })
                            }
                        }

                        AppStateView {
                            anchors.fill: parent
                            visible: scene.overlayMode === "app" && appLoader.status !== Loader.Ready
                            state: appLoader.status === Loader.Loading ? "loading" : "error"
                            title: appLoader.status === Loader.Loading ? "LOADING APPLICATION" : "APPLICATION UNAVAILABLE"
                            detail: appLoader.status === Loader.Error
                                ? "The selected QML pane could not be loaded. Check the terminal for details."
                                : "Preparing " + AppRegistry.titleFor(scene.activeAppId) + "."
                            actionText: appLoader.status === Loader.Error ? "RETRY APP" : ""
                            actionIcon: "R"
                            uiScale: scene.contentScale
                            onActionTriggered: scene.retryActiveApp()
                        }

                        GridLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            visible: scene.overlayMode === "menu"
                            columns: 2
                            rowSpacing: 7 * scene.controlScale
                            columnSpacing: 7 * scene.controlScale

                            TarsButton {
                                uiScale: scene.contentScale
                                dense: true
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: 1
                                Layout.minimumHeight: scene.touchTarget
                                Layout.preferredHeight: scene.touchTarget
                                Layout.maximumHeight: scene.touchTarget
                                text: "SYSTEM HEALTH"
                                iconText: "HLTH"
                                iconPixelSize: 11 * scene.controlScale
                                labelPixelSize: 6.5 * scene.controlScale
                                accent: window.red
                                onClicked: scene.openApp("system-health", "menu")
                            }
                            TarsButton {
                                uiScale: scene.contentScale
                                dense: true
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: 1
                                Layout.minimumHeight: scene.touchTarget
                                Layout.preferredHeight: scene.touchTarget
                                Layout.maximumHeight: scene.touchTarget
                                text: "WI-FI & REMOTE"
                                iconText: "LINK"
                                iconPixelSize: 11 * scene.controlScale
                                labelPixelSize: 6.5 * scene.controlScale
                                accent: window.red
                                onClicked: scene.openApp("remote", "menu")
                            }
                            TarsButton {
                                uiScale: scene.contentScale
                                dense: true
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: 1
                                Layout.minimumHeight: scene.touchTarget
                                Layout.preferredHeight: scene.touchTarget
                                Layout.maximumHeight: scene.touchTarget
                                text: "SERVO CALIBRATION"
                                iconText: "SRV"
                                iconPixelSize: 11 * scene.controlScale
                                labelPixelSize: 6.5 * scene.controlScale
                                accent: window.red
                                enabled: !controller.calibrationActive
                                onClicked: scene.openConfirmation("servo")
                            }
                            TarsButton {
                                uiScale: scene.contentScale
                                dense: true
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: 1
                                Layout.minimumHeight: scene.touchTarget
                                Layout.preferredHeight: scene.touchTarget
                                Layout.maximumHeight: scene.touchTarget
                                text: "RESTART TARS"
                                iconText: "RST"
                                iconPixelSize: 11 * scene.controlScale
                                labelPixelSize: 6.5 * scene.controlScale
                                accent: window.amber
                                onClicked: scene.openConfirmation("restart")
                            }
                            TarsButton {
                                uiScale: scene.contentScale
                                dense: true
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: 1
                                Layout.minimumHeight: scene.touchTarget
                                Layout.preferredHeight: scene.touchTarget
                                Layout.maximumHeight: scene.touchTarget
                                text: "EXIT APPLICATION"
                                iconText: "EXIT"
                                iconPixelSize: 11 * scene.controlScale
                                labelPixelSize: 6.5 * scene.controlScale
                                accent: "#829199"
                                onClicked: scene.openConfirmation("exit")
                            }
                            TarsButton {
                                uiScale: scene.contentScale
                                dense: true
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredWidth: 1
                                Layout.minimumHeight: scene.touchTarget
                                Layout.preferredHeight: scene.touchTarget
                                Layout.maximumHeight: scene.touchTarget
                                text: "SHUT DOWN PI"
                                iconText: "PWR"
                                iconPixelSize: 11 * scene.controlScale
                                labelPixelSize: 6.5 * scene.controlScale
                                accent: window.red
                                selected: true
                                onClicked: scene.openConfirmation("shutdown")
                            }
                        }

                        ConfirmationDialog {
                            anchors.fill: parent
                            visible: scene.overlayMode === "confirm"
                            iconText: scene.confirmationIcon
                            title: scene.confirmationTitle
                            message: scene.confirmationMessage
                            confirmText: scene.confirmationButtonText
                            accent: scene.confirmationAction === "restart" ? window.amber : window.red
                            uiScale: scene.contentScale
                            onRejected: {
                                scene.confirmationAction = ""
                                scene.overlayMode = ""
                            }
                            onAccepted: scene.executeConfirmation()
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
                    text: scene.runtimeFailed ? "STARTUP FAILED" : "INITIALIZING TARS"
                    color: scene.runtimeFailed ? window.red : window.pale
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
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Ui.spaceMd * scene.contentScale

                    TarsButton {
                        visible: scene.runtimeFailed
                        uiScale: scene.contentScale
                        width: 150 * scene.contentScale
                        height: scene.comfortableTouchTarget
                        text: "RESTART"
                        iconText: "R"
                        accent: window.amber
                        onClicked: controller.requestRestart()
                    }
                    TarsButton {
                        uiScale: scene.contentScale
                        width: 150 * scene.contentScale
                        height: scene.comfortableTouchTarget
                        text: "EXIT"
                        iconText: "X"
                        accent: window.red
                        onClicked: controller.exitProgram()
                    }
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
