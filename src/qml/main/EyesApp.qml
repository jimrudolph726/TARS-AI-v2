import QtQuick

Item {
    id: root
    property real uiScale: 1.0
    property string mood: controller.eyeMood
    property string reaction: ""
    property real gazeX: 0
    property real gazeY: 0
    property bool blinking: false
    property color accent: mood === "ANGRY" || mood === "ANNOYED" ? "#ff3852"
                           : mood === "SAD" ? "#4b91d1"
                           : mood === "EXCITED" || mood === "SURPRISED" ? "#ffda47"
                           : mood === "AFRAID" || mood === "CONFUSED" ? "#b782ff"
                           : mood === "LOVE" || mood === "SHY" ? "#ff5b92"
                           : mood === "DISGUSTED" ? "#62bd5c"
                           : mood === "SLEEPY" ? "#4d8991"
                           : mood === "CURIOUS" ? "#55c6ed" : "#ff3852"

    onMoodChanged: {
        if (mood === "SIDEEYE_LEFT") gazeX = -0.85
        else if (mood === "SIDEEYE_RIGHT") gazeX = 0.85
        else if (!pointer.containsMouse) { gazeX = 0; gazeY = 0 }
    }

    Behavior on gazeX { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }
    Behavior on gazeY { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }

    function triggerReaction(kind) {
        reaction = kind
        reactionTimer.restart()
        controller.speakEyeReaction(kind)
        eyeCanvas.requestPaint()
    }

    Rectangle { anchors.fill: parent; color: "#020709" }

    Timer {
        id: blinkTimer
        interval: mood === "SLEEPY" ? 1700 : 2800 + Math.random() * 2300
        running: root.visible
        repeat: false
        onTriggered: { root.blinking = true; blinkEnd.restart() }
    }
    Timer {
        id: blinkEnd
        interval: root.mood === "SLEEPY" ? 260 : 135
        onTriggered: {
            root.blinking = false
            blinkTimer.interval = root.mood === "SLEEPY" ? 1500 : 2400 + Math.random() * 3000
            blinkTimer.restart()
        }
    }
    Timer { id: reactionTimer; interval: 1150; onTriggered: { root.reaction = ""; eyeCanvas.requestPaint() } }
    Timer {
        interval: 1100
        running: root.visible && !pointer.containsMouse
        repeat: true
        onTriggered: { root.gazeX = (Math.random() - 0.5) * 0.38; root.gazeY = (Math.random() - 0.5) * 0.24 }
    }
    Timer { interval: 33; running: root.visible; repeat: true; onTriggered: eyeCanvas.requestPaint() }

    Canvas {
        id: eyeCanvas
        anchors.fill: parent
        anchors.margins: 9 * root.uiScale
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d"), w = width, h = height
            var centerY = h * 0.48
            var eyeW = Math.min(w * 0.34, 150 * root.uiScale)
            var eyeH = Math.min(h * 0.34, 104 * root.uiScale)
            var gap = Math.max(18 * root.uiScale, w * 0.07)
            var leftX = w / 2 - gap / 2 - eyeW, rightX = w / 2 + gap / 2
            var top = centerY - eyeH / 2
            var sleepy = root.mood === "SLEEPY"
            var surprised = root.mood === "SURPRISED" || root.mood === "AFRAID"
            var angry = root.mood === "ANGRY" || root.mood === "ANNOYED"
            var sad = root.mood === "SAD"
            var closed = root.blinking || root.reaction === "forehead_tap"
            var scale = surprised ? 1.12 : sleepy ? 0.58 : 1.0
            if (root.reaction === "dizzy") scale = 0.78
            ctx.reset(); ctx.clearRect(0, 0, w, h)

            function roundedRect(x, y, rw, rh, radius) {
                var r = Math.min(radius, rw / 2, rh / 2)
                ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + rw - r, y)
                ctx.quadraticCurveTo(x + rw, y, x + rw, y + r); ctx.lineTo(x + rw, y + rh - r)
                ctx.quadraticCurveTo(x + rw, y + rh, x + rw - r, y + rh); ctx.lineTo(x + r, y + rh)
                ctx.quadraticCurveTo(x, y + rh, x, y + rh - r); ctx.lineTo(x, y + r)
                ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath()
            }
            function drawEye(x, side) {
                var eh = closed ? Math.max(5, 7 * root.uiScale) : eyeH * scale
                var y = centerY - eh / 2
                ctx.shadowColor = root.accent; ctx.shadowBlur = 14 * root.uiScale; ctx.fillStyle = root.accent
                roundedRect(x, y, eyeW, eh, closed ? eh / 2 : 22 * root.uiScale); ctx.fill(); ctx.shadowBlur = 0
                ctx.strokeStyle = "#ffdce2"; ctx.globalAlpha = 0.65; ctx.lineWidth = Math.max(1, 1.3 * root.uiScale); ctx.stroke(); ctx.globalAlpha = 1
                if (closed) return
                var pupilR = (surprised ? 9 : sleepy ? 13 : 12) * root.uiScale
                var px = x + eyeW / 2 + root.gazeX * eyeW * 0.48, py = centerY + root.gazeY * eh * 0.42
                if ((root.reaction === "poke_left" && side < 0) || (root.reaction === "poke_right" && side > 0)) pupilR *= 0.55
                ctx.fillStyle = "#041014"; ctx.beginPath(); ctx.arc(px, py, pupilR, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = "#d9f6ff"; ctx.globalAlpha = 0.7; ctx.beginPath(); ctx.arc(px - pupilR * 0.3, py - pupilR * 0.3, pupilR * 0.18, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1
                if (angry || sad) {
                    ctx.strokeStyle = "#020709"; ctx.lineWidth = 13 * root.uiScale; ctx.beginPath()
                    var innerY = angry ? y + 18 * root.uiScale : y - 1, outerY = angry ? y - 1 : y + 18 * root.uiScale
                    if (side < 0) { ctx.moveTo(x - 4, outerY); ctx.lineTo(x + eyeW + 4, innerY) }
                    else { ctx.moveTo(x - 4, innerY); ctx.lineTo(x + eyeW + 4, outerY) }
                    ctx.stroke()
                }
            }
            drawEye(leftX, -1); drawEye(rightX, 1)

            if (root.reaction === "dizzy") {
                ctx.strokeStyle = "#ffda47"; ctx.lineWidth = 2 * root.uiScale
                for (var i = 0; i < 3; i++) {
                    var angle = Date.now() / 260 + i * Math.PI * 2 / 3
                    var sx = w / 2 + Math.cos(angle) * 55 * root.uiScale, sy = top - 13 * root.uiScale + Math.sin(angle) * 9 * root.uiScale
                    ctx.strokeRect(sx - 3, sy - 3, 6, 6)
                }
            }
            if (root.mood === "LOVE") {
                ctx.fillStyle = "#ff5b92"; ctx.font = Math.max(12, 15 * root.uiScale) + "px sans-serif"
                ctx.fillText("♥", w / 2 - 6 * root.uiScale, top - 8 * root.uiScale)
            }
            if (controller.tarsState === "SPEAKING") {
                var pulse = 0.5 + 0.5 * Math.sin(Date.now() / 95)
                ctx.strokeStyle = root.accent; ctx.globalAlpha = 0.22 + pulse * 0.35; ctx.lineWidth = 1.5 * root.uiScale
                ctx.beginPath(); ctx.arc(w / 2, centerY, Math.min(w, h) * (0.34 + pulse * 0.025), 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1
            }
        }
    }

    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        onPositionChanged: function(mouse) {
            root.gazeX = Math.max(-1, Math.min(1, (mouse.x / width - 0.5) * 2))
            root.gazeY = Math.max(-1, Math.min(1, (mouse.y / height - 0.5) * 2))
        }
        onExited: { root.gazeX = 0; root.gazeY = 0 }
        onDoubleClicked: function(mouse) { mouse.accepted = true; root.triggerReaction("dizzy") }
        onClicked: function(mouse) {
            var nx = mouse.x / width, ny = mouse.y / height
            if (ny < 0.27) root.triggerReaction("forehead_tap")
            else if (ny > 0.72) root.triggerReaction("chin_tap")
            else if (nx > 0.43 && nx < 0.57) root.triggerReaction("boop_nose")
            else if (nx < 0.5) root.triggerReaction("poke_left")
            else root.triggerReaction("poke_right")
        }
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 9 * root.uiScale
        text: (root.reaction ? root.reaction.replace("_", " ").toUpperCase() : "TOUCH OR MOVE TO INTERACT") + "  ·  " + root.mood + "  ·  " + controller.tarsState
        color: root.reaction ? root.accent : "#81949d"
        font.family: monoFontFamily
        font.pixelSize: Math.max(5, 6 * root.uiScale)
        font.letterSpacing: 0.9 * root.uiScale
    }
}
