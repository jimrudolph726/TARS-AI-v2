import QtQuick

Item {
    id: root
    property real uiScale: 1.0
    property var samples: []
    property int lastWakeRevision: controller.wakeEventRevision
    property int lastBargeRevision: controller.bargeInEventRevision
    property int speechFrames: 0
    property int totalFrames: 0

    function normalized(value, reference) {
        return Math.max(0, Math.min(1, value / Math.max(0.008, reference * 2.35)))
    }

    Rectangle { anchors.fill: parent; color: "#040b0e" }

    Row {
        id: metrics
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8 * root.uiScale
        spacing: 5 * root.uiScale

        Repeater {
            model: [
                { label: "RMS", value: (controller.audioRms * 1000).toFixed(1), color: "#dce8ed" },
                { label: "PEAK", value: (controller.audioPeak * 1000).toFixed(1), color: "#ff3852" },
                { label: "FLOOR", value: (controller.audioNoiseFloor * 1000).toFixed(1), color: "#50a9c8" },
                { label: "SPEECH", value: controller.audioSpeechActive ? "ACTIVE" : "QUIET", color: controller.audioSpeechActive ? "#2aff8a" : "#6f8189" }
            ]
            Rectangle {
                required property var modelData
                width: (metrics.width - metrics.spacing * 3) / 4
                height: 31 * root.uiScale
                radius: 3 * root.uiScale
                color: "#091419"
                border.width: 1
                border.color: "#243841"
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 6 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: "#71858e"
                    font.family: monoFontFamily
                    font.pixelSize: Math.max(5, 5.5 * root.uiScale)
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 6 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value
                    color: modelData.color
                    font.family: monoFontFamily
                    font.bold: true
                    font.pixelSize: Math.max(6, 6.5 * root.uiScale)
                }
            }
        }
    }

    Timer {
        interval: 75
        running: root.visible
        repeat: true
        onTriggered: {
            var wake = controller.wakeEventRevision !== root.lastWakeRevision
            var barge = controller.bargeInEventRevision !== root.lastBargeRevision
            root.lastWakeRevision = controller.wakeEventRevision
            root.lastBargeRevision = controller.bargeInEventRevision
            var next = root.samples.slice(0)
            next.push({ rms: controller.audioRms, peak: controller.audioPeak,
                floor: controller.audioNoiseFloor, threshold: controller.audioSpeechThreshold,
                speech: controller.audioSpeechActive, tts: controller.tarsState === "SPEAKING",
                state: controller.tarsState, wake: wake, barge: barge })
            var maximum = Math.max(90, Math.floor(timeline.width / 2.7))
            if (next.length > maximum) next.splice(0, next.length - maximum)
            root.samples = next
            root.totalFrames++
            if (controller.audioSpeechActive) root.speechFrames++
            timeline.requestPaint()
        }
    }

    Canvas {
        id: timeline
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: metrics.bottom
        anchors.bottom: footer.top
        anchors.margins: 8 * root.uiScale
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d"), w = width, h = height
            var labelW = Math.max(48, 51 * root.uiScale), graphX = labelW
            var graphW = Math.max(1, w - graphX), laneH = h / 4
            var labels = ["MIC", "VOICE", "OUTPUT", "STATE"]
            var colors = {"BOOTING":"#52636b", "STANDBY":"#52636b", "IDLE":"#52636b", "LISTENING":"#2aff8a", "THINKING":"#ffc857", "SPEAKING":"#ff3852"}
            ctx.reset(); ctx.fillStyle = "#040b0e"; ctx.fillRect(0, 0, w, h)
            for (var lane = 0; lane < 4; lane++) {
                var top = lane * laneH
                ctx.fillStyle = lane % 2 ? "#061015" : "#081318"; ctx.fillRect(graphX, top, graphW, laneH)
                ctx.strokeStyle = "#243740"; ctx.lineWidth = 1; ctx.strokeRect(graphX + 0.5, top + 0.5, graphW - 1, laneH - 1)
                ctx.fillStyle = "#81949d"; ctx.font = Math.max(6, 6 * root.uiScale) + "px monospace"
                ctx.fillText(labels[lane], 4 * root.uiScale, top + laneH / 2 + 2 * root.uiScale)
                for (var grid = 1; grid < 4; grid++) {
                    var gy = top + laneH * grid / 4
                    ctx.strokeStyle = "#122229"; ctx.beginPath(); ctx.moveTo(graphX, gy); ctx.lineTo(w, gy); ctx.stroke()
                }
            }
            for (var gx = graphX; gx < w; gx += Math.max(30, 38 * root.uiScale)) {
                ctx.strokeStyle = "#122229"; ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, h); ctx.stroke()
            }
            if (!root.samples.length) return
            var dx = graphW / Math.max(1, root.samples.length - 1)
            function plot(lane, color, widthPx, getter) {
                var base = lane * laneH + laneH * 0.86
                ctx.strokeStyle = color; ctx.lineWidth = Math.max(1, widthPx * root.uiScale); ctx.lineJoin = "round"; ctx.beginPath()
                for (var i = 0; i < root.samples.length; i++) {
                    var v = Math.max(0, Math.min(1, getter(root.samples[i])))
                    var x = graphX + i * dx, y = base - v * laneH * 0.72
                    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
                }
                ctx.stroke()
            }
            plot(0, "#ff3852", 1.0, function(s) { return root.normalized(s.peak, s.threshold) })
            plot(0, "#e3edf1", 1.5, function(s) { return root.normalized(s.rms, s.threshold) })
            plot(0, "#50a9c8", 0.8, function(s) { return root.normalized(s.floor, s.threshold) })
            for (var i = 0; i < root.samples.length; i++) {
                var sample = root.samples[i], x = graphX + i * dx
                ctx.fillStyle = sample.speech ? "#2aff8a" : "#1c3a34"; ctx.fillRect(x, laneH * 1.25, Math.max(2, dx + 0.5), laneH * 0.5)
                ctx.fillStyle = sample.tts ? "#b782ff" : "#241f32"; ctx.fillRect(x, laneH * 2.25, Math.max(2, dx + 0.5), laneH * 0.5)
                ctx.fillStyle = colors[sample.state] || "#52636b"; ctx.fillRect(x, laneH * 3.25, Math.max(2, dx + 0.5), laneH * 0.5)
                if (sample.wake || sample.barge) {
                    ctx.strokeStyle = sample.barge ? "#ffc857" : "#2aff8a"; ctx.lineWidth = Math.max(1, 1.4 * root.uiScale)
                    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
                    ctx.fillStyle = ctx.strokeStyle; ctx.fillText(sample.barge ? "B" : "W", x + 2, 8 * root.uiScale)
                }
            }
        }
    }

    Item {
        id: footer
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 27 * root.uiScale
        Text {
            anchors.left: parent.left; anchors.leftMargin: 10 * root.uiScale; anchors.verticalCenter: parent.verticalCenter
            text: "W WAKE  ·  B BARGE-IN  ·  WINDOW " + (root.samples.length * 0.075).toFixed(1) + "s"
            color: "#71858e"; font.family: monoFontFamily; font.pixelSize: Math.max(5, 5.5 * root.uiScale)
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 10 * root.uiScale; anchors.verticalCenter: parent.verticalCenter
            text: controller.tarsState + "  ·  VOICE " + (root.totalFrames ? Math.round(root.speechFrames / root.totalFrames * 100) : 0) + "%"
            color: controller.audioSpeechActive ? "#2aff8a" : "#9aacb4"; font.family: monoFontFamily; font.pixelSize: Math.max(5, 5.5 * root.uiScale)
        }
    }
}
