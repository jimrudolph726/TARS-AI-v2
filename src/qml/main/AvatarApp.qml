import QtQuick
import "components"
import "components/UiTokens.js" as Ui

Item {
    id: root
    property real uiScale: 1.0

    Rectangle { anchors.fill: parent; color: Ui.background }

    Rectangle {
        id: frame
        anchors.fill: parent
        anchors.margins: Ui.spaceSm * root.uiScale
        anchors.bottomMargin: 31 * root.uiScale
        color: "#061014"
        border.width: 1
        border.color: controller.avatarStatus === "error" ? "#ff3852" : "#30464f"

        Image {
            id: avatarImage
            anchors.fill: parent
            anchors.margins: Ui.spaceXs * root.uiScale
            source: controller.avatarFrameSource
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
            opacity: status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 180 } }
        }

        AppStateView {
            anchors.fill: parent
            state: avatarImage.status === Image.Loading ? "loading" : "error"
            visible: avatarImage.status !== Image.Ready
            title: avatarImage.status === Image.Loading ? "LOADING AVATAR" : "AVATAR UNAVAILABLE"
            detail: controller.avatarError.length ? controller.avatarError : "Install a complete character animation set to enable this view."
            iconText: "T"
            accent: "#ff3852"
            uiScale: root.uiScale
        }

        Rectangle {
            visible: avatarImage.status === Image.Ready
            anchors.fill: parent
            color: "transparent"
            border.width: 1
            border.color: "#182a31"
            opacity: 0.55
        }

        Rectangle {
            id: scanline
            visible: avatarImage.status === Image.Ready
            x: 2 * root.uiScale
            width: parent.width - 4 * root.uiScale
            height: 1 * root.uiScale
            color: "#66ff3852"
            opacity: 0.38
            SequentialAnimation on y {
                running: scanline.visible && root.visible
                loops: Animation.Infinite
                NumberAnimation { from: 3 * root.uiScale; to: Math.max(4, frame.height - 4 * root.uiScale); duration: 3600; easing.type: Easing.Linear }
                PauseAnimation { duration: 900 }
            }
        }

        Rectangle {
            visible: avatarImage.status === Image.Ready
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 7 * root.uiScale
            width: statusText.width + 13 * root.uiScale
            height: 20 * root.uiScale
            radius: 2 * root.uiScale
            color: controller.avatarUsingFallback ? "#332a13" : "#10251d"
            border.width: 1
            border.color: controller.avatarUsingFallback ? "#ffc857" : "#2aff8a"
            Text {
                id: statusText
                anchors.centerIn: parent
                text: controller.avatarUsingFallback ? "FALLBACK FRAME" : "SPRITES ONLINE"
                color: controller.avatarUsingFallback ? "#ffc857" : "#2aff8a"
                font.family: monoFontFamily
                font.pixelSize: Math.max(5, 5.5 * root.uiScale)
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 27 * root.uiScale
        color: "#cc03080a"
        Text {
            anchors.centerIn: parent
            text: controller.avatarCharacter.toUpperCase() + "  ·  " + controller.avatarEmotion + "  ·  " + controller.tarsState
            color: "#d6e0e4"
            font.family: monoFontFamily
            font.pixelSize: Math.max(5, 6 * root.uiScale)
            font.letterSpacing: 1.0 * root.uiScale
        }
    }
}
