.pragma library

// TARS visual-system tokens. Keep geometry and typography in one place so
// fullscreen, windowed, rotated, and touch layouts share the same rhythm.

var canvasWidth = 480
var canvasHeight = 720
var maximumUiScale = 1.45
var maximumContentScale = 1.25

var background = "#03080a"
var surface = "#071014"
var surfaceRaised = "#09151b"
var surfacePressed = "#24151b"
var surfaceHover = "#142129"
var border = "#26363d"
var borderStrong = "#31444d"
var borderInner = "#13242b"
var textPrimary = "#edf3f5"
var textSecondary = "#97a7ae"
var textMuted = "#71858e"
var disabled = "#59666d"
var red = "#ff3852"
var green = "#2aff8a"
var amber = "#ffc857"
var blue = "#64b5f6"

var space2xs = 2
var spaceXs = 4
var spaceSm = 6
var spaceMd = 8
var spaceLg = 12
var spaceXl = 16

var radiusSm = 4
var radiusMd = 6
var radiusLg = 8

var textCaption = 6
var textSmall = 7
var textBody = 8
var textLabel = 9
var textHeading = 13
var textTitle = 18
var textHero = 30

// 44 logical pixels is the baseline interactive target. Dense controls may
// render smaller artwork, but their clickable surface should not be smaller.
var touchMin = 44
var touchComfortable = 50

function scaled(value, scale) {
    return value * scale
}

function clampedScale(width, height) {
    return Math.max(0.66, Math.min(width / canvasWidth,
                                  height / canvasHeight,
                                  maximumUiScale))
}

function contentScale(scale) {
    return Math.max(0.78, Math.min(scale, maximumContentScale))
}

