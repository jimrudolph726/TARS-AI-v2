.pragma library

// One source of truth for every app exposed by the launcher. Keep runtime
// status outside this file; TarsMain maps badgeKey values to live controller
// properties without duplicating titles, icons, or QML source paths.
var applications = [
    { id: "clock", title: "CLOCK", icon: "CLK", source: "ClockApp.qml", badgeKey: "ready", enabled: true },
    { id: "dashboard", title: "DASHBOARD", icon: "SYS", source: "DashboardApp.qml", badgeKey: "live", enabled: true },
    { id: "eyes", title: "EYES", icon: "00", source: "EyesApp.qml", badgeKey: "live", enabled: true },
    { id: "avatar", title: "AVATAR", icon: "T", source: "AvatarApp.qml", badgeKey: "avatar", enabled: true },
    { id: "remote", title: "REMOTE ACCESS", icon: "LINK", source: "RemoteApp.qml", badgeKey: "remote", enabled: true },
    { id: "audio", title: "AUDIO TIMELINE", icon: "WAVE", source: "AudioApp.qml", badgeKey: "live", enabled: true }
]

function find(appId) {
    for (var index = 0; index < applications.length; ++index) {
        if (applications[index].id === appId)
            return applications[index]
    }
    return null
}

function titleFor(appId) {
    var app = find(appId)
    return app ? app.title : "APPLICATION"
}

function sourceFor(appId) {
    var app = find(appId)
    return app && app.enabled ? app.source : ""
}

