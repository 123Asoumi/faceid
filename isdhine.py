import sys
import os
import cv2
import time
import ctypes
import shutil
import subprocess
import datetime
import numpy as np
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QPushButton, QSystemTrayIcon, QMenu, QDialog, QComboBox,
    QFormLayout, QHBoxLayout, QStackedWidget, QGraphicsOpacityEffect,
    QSizePolicy, QScrollArea, QFrame, QFileDialog, QCheckBox
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QThread, QSize, QSettings,
    QPropertyAnimation, QEasingCurve, QRect, QRectF, QPointF,
    QParallelAnimationGroup, QVariantAnimation, Property
)
from PySide6.QtGui import (
    QIcon, QFont, QPixmap, QPainter, QColor, QPen,
    QAction, QPainterPath, QCursor, QLinearGradient,
    QImage, QRadialGradient, QBrush
)

# ── Asset layout ──────────────────────────────────────────────────────────────
def _res(*parts) -> str:
    """Path to a bundled resource — works both from source and from a PyInstaller
    one-file/one-dir build (which unpacks assets under sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)

LOGO_PATH      = _res("Asset", "logo", "BLOQZ.png")
ICON_PATH      = _res("Asset", "logo", "icone.png")
SPRITE_PATH    = _res("Asset", "sprite", "req.png")
BUNDLED_BG_DIR = _res("Asset", "backgrounds")

# Writable user data (survives app updates; where imported backgrounds go).
def _user_data_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:  # Linux / other: honour XDG, else ~/.local/share
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "BLOQZ")

USER_DIR    = _user_data_dir()
USER_BG_DIR = os.path.join(USER_DIR, "backgrounds")

# ── Consent / data-protection policy ──────────────────────────────────────────
# Bump this string to re-prompt every user for consent (e.g. after a policy change).
CONSENT_VERSION = "2024-06-benin-loi-2017-20-2020-35"
LAW_CODE_NUM_URL = ("https://www.afapdp.org/wp-content/uploads/2018/06/"
                    "Benin-Loi-2017-20-Portant-code-du-numerique-en-Republique-du-Benin.pdf")
LAW_2020_35_URL  = "https://sgg.gouv.bj/doc/loi-2020-35/"

# ── Palette ──────────────────────────────────────────────────────────────────
BG       = "#0a1424"   # deep navy
BG2      = "#050b16"   # near-black base for the vignette
SURFACE  = "#101f38"   # raised card / control surface
BLUE     = "#5aa9ff"   # primary accent
BLUE_DIM = "#2d5c9e"
BLUE_MID = "#3a6090"
TEXT     = "#f2f7ff"
MUTED    = "#8fb4e6"
FAINT    = "#5c7aa8"   # very low-emphasis text
BORDER   = "#20396a"

# ── State accents (drive the status orb + labels) ─────────────────────────────
GREEN    = "#3ddc97"   # present / protected
AMBER    = "#ffb454"   # absent / warning
RED      = "#ff5d6c"   # locking / locked
SLATE    = "#6d8299"   # paused / error / neutral

# ── Type system ───────────────────────────────────────────────────────────────
FONT_UI  = "Segoe UI, sans-serif"
FONT_MONO = "Consolas, Cascadia Mono, monospace"  # numeric / technical readouts

# ─────────────────────────────────────────────────────────────────────────────
#  Settings Manager
# ─────────────────────────────────────────────────────────────────────────────
class SettingsManager:
    def __init__(self):
        self.settings = QSettings("BLOQZ", "BLOQZApp")

    def get_timeout(self):    return int(self.settings.value("timeout", 30))
    def set_timeout(self, v): self.settings.setValue("timeout", v)

    def get_camera_index(self):    return int(self.settings.value("camera_index", 0))
    def set_camera_index(self, v): self.settings.setValue("camera_index", v)

    def get_background(self):    return self.settings.value("background", "")
    def set_background(self, v): self.settings.setValue("background", v)

    def get_onboarded(self):    return self.settings.value("onboarded", "false") == "true"
    def set_onboarded(self, v): self.settings.setValue("onboarded", "true" if v else "false")

    # Consent is versioned: bumping CONSENT_VERSION re-prompts every user.
    def get_consent_version(self):    return str(self.settings.value("consent_version", ""))
    def set_consent(self, version, when):
        self.settings.setValue("consent_version", version)
        self.settings.setValue("consent_date", when)
    def has_consented(self):
        return self.get_consent_version() == CONSENT_VERSION


# ─────────────────────────────────────────────────────────────────────────────
#  System Locker
# ─────────────────────────────────────────────────────────────────────────────
class SystemLocker:
    """Cross-platform screen lock. Windows uses the Win32 API; Linux tries the
    common session/screensaver lockers in turn (adapted from the lock-on-absence
    project). Returns True only when a mechanism confirmed success."""

    # Linux lockers, tried in order until one returns exit code 0.
    _LINUX_LOCKERS = (
        ["loginctl", "lock-session"],
        ["xdg-screensaver", "lock"],
        ["gnome-screensaver-command", "--lock"],
        ["dm-tool", "lock"],
        ["i3lock", "-n"],
        ["slock"],
    )

    @staticmethod
    def lock() -> bool:
        if sys.platform == "win32":
            try:
                return bool(ctypes.windll.user32.LockWorkStation())
            except Exception:
                return False

        lockers = SystemLocker._LINUX_LOCKERS
        if sys.platform == "darwin":  # bonus: macOS, free to support
            lockers = (["pmset", "displaysleepnow"],
                       ["osascript", "-e",
                        'tell application "System Events" to keystroke "q" '
                        'using {command down, control down}'])
        for args in lockers:
            try:
                r = subprocess.run(args, timeout=5, check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if r.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Face Detector
# ─────────────────────────────────────────────────────────────────────────────
class FaceDetector:
    def __init__(self):
        base = cv2.data.haarcascades
        # alt2 is generally the most reliable frontal cascade; default is a
        # second chance. Equalised grayscale makes both far less light-sensitive.
        self.cascades = [
            cv2.CascadeClassifier(base + "haarcascade_frontalface_alt2.xml"),
            cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml"),
        ]
        self.cascades = [c for c in self.cascades if not c.empty()]

    def detect(self, frame) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        # smallest face to accept, scaled to the frame so moderate distance is fine
        m = max(int(min(frame.shape[:2]) * 0.08), 40)
        for casc in self.cascades:
            faces = casc.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4,
                                          minSize=(m, m))
            if len(faces) > 0:
                return True
        return False


# ── Camera backend selection (Windows MSMF often opens but never reads) ────────
def _open_capture(index: int):
    """Open the webcam, preferring DirectShow on Windows where the default MSMF
    backend frequently reports isOpened()==True yet returns no frames."""
    if sys.platform == "win32":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap
        cap.release()
    return cv2.VideoCapture(index)


# ─────────────────────────────────────────────────────────────────────────────
#  Camera Manager (background thread)
# ─────────────────────────────────────────────────────────────────────────────
class CameraManager(QThread):
    face_detected = Signal(bool)
    camera_error  = Signal()

    def __init__(self, camera_index=0):
        super().__init__()
        self.camera_index = camera_index
        self.running      = True
        self.paused       = False
        self.detector     = FaceDetector()
        self.face_history = []
        self.history_size = 12          # ~1.2 s rolling window at 10 fps

    def run(self):
        cap = _open_capture(self.camera_index)
        if not cap.isOpened():
            self.camera_error.emit()
            return
        # give the sensor a moment and drop the first (often black) frames
        for _ in range(5):
            cap.read()
            time.sleep(0.05)

        fails = 0
        while self.running:
            if self.paused:
                time.sleep(0.3)
                continue
            ret, frame = cap.read()
            if not ret or frame is None:
                # tolerate transient read hiccups instead of erroring out at once
                fails += 1
                if fails >= 30:
                    self.camera_error.emit()
                    break
                time.sleep(0.1)
                continue
            fails = 0
            detected = self.detector.detect(frame)
            self.face_history.append(detected)
            if len(self.face_history) > self.history_size:
                self.face_history.pop(0)
            # "present" as long as a face was seen at least twice in the window,
            # so a few missed frames don't wrongly mark you absent and lock.
            self.face_detected.emit(sum(self.face_history) >= 2)
            time.sleep(0.1)
        cap.release()

    def stop(self):
        self.running = False
        self.wait()


# ─────────────────────────────────────────────────────────────────────────────
#  Settings Dialog  (small popup, unchanged)
# ─────────────────────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    TIMEOUTS = {
        "2 seconds":  2,
        "5 seconds":  5,
        "10 seconds": 10,
        "30 seconds": 30,
        "1 minute":   60,
        "5 minutes":  300,
        "1 hour":     3600,
        "24 hours":   86400,
    }
    _btn = """
        QPushButton {{
            background: {bg}; color: {fg};
            border: 1px solid {bd}; border-radius: 8px;
            padding: 7px 20px; font-size: 12px; {extra}
        }}
        QPushButton:hover {{ background: {hbg}; color: {hfg}; border-color: {hbd}; }}
    """

    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self.sm = sm
        self.imported = False
        self.setWindowTitle("BLOQZ — Settings")
        self.setFixedSize(420, 350)
        self.setStyleSheet(f"background:{BG}; color:{TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(18)

        title = QLabel("SETTINGS")
        title.setStyleSheet(f"font-size:16px; font-weight:800; color:{BLUE}; letter-spacing:3px;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)

        combo_css = (
            f"QComboBox{{background:{SURFACE}; color:{TEXT}; border:1px solid {BORDER};"
            "border-radius:8px; padding:7px 12px; font-size:12px;}"
            f"QComboBox:hover{{border-color:{BLUE};}}"
            f"QComboBox QAbstractItemView{{background:{SURFACE}; color:{TEXT};"
            f"selection-background-color:{BLUE_DIM}; border:1px solid {BORDER};}}")
        lbl_css   = f"color:{MUTED}; font-size:12px; font-weight:600;"

        self.t_combo = QComboBox()
        self.t_combo.setStyleSheet(combo_css)
        cur = sm.get_timeout()
        for k, v in self.TIMEOUTS.items():
            self.t_combo.addItem(k, v)
            if v == cur:
                self.t_combo.setCurrentText(k)
        tl = QLabel("Absence Timeout")
        tl.setStyleSheet(lbl_css)
        form.addRow(tl, self.t_combo)

        self.c_combo = QComboBox()
        self.c_combo.setStyleSheet(combo_css)
        self.c_combo.addItem("Default Webcam (0)", 0)
        self.c_combo.addItem("External Webcam (1)", 1)
        self.c_combo.setCurrentIndex(sm.get_camera_index())
        cl = QLabel("Webcam")
        cl.setStyleSheet(lbl_css)
        form.addRow(cl, self.c_combo)

        # ── Backgrounds: let the user import their own image ────────────────────
        self.import_btn = QPushButton("Import image…")
        self.import_btn.setStyleSheet(self._btn.format(
            bg="transparent", fg=MUTED, bd=BORDER, extra="",
            hbg=SURFACE, hfg=BLUE, hbd=BLUE))
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.clicked.connect(self._import_background)
        bl = QLabel("Backgrounds")
        bl.setStyleSheet(lbl_css)
        form.addRow(bl, self.import_btn)

        layout.addLayout(form)

        self.import_note = QLabel("")
        self.import_note.setStyleSheet(f"color:{GREEN}; font-size:10px;")
        self.import_note.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.import_note)

        priv = QLabel("Your camera stays on your device.\nBLOQZ does not upload your camera feed.")
        priv.setStyleSheet(f"color:{BLUE_MID}; font-size:10px; font-style:italic;")
        priv.setAlignment(Qt.AlignCenter)
        layout.addWidget(priv)

        row = QHBoxLayout()
        row.addStretch()
        save = QPushButton("Save")
        save.setStyleSheet(self._btn.format(bg=BLUE, fg="#000", bd=BLUE, extra="font-weight:bold;", hbg="#6ab2ff", hfg="#000", hbd=BLUE))
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        row.addWidget(save)
        layout.addLayout(row)

    def _import_background(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import background image", os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not files:
            return
        os.makedirs(USER_BG_DIR, exist_ok=True)
        added = 0
        for src in files:
            base = os.path.basename(src)
            dst  = os.path.join(USER_BG_DIR, base)
            # avoid clobbering an existing asset of the same name
            stem, ext = os.path.splitext(base)
            n = 1
            while os.path.exists(dst):
                dst = os.path.join(USER_BG_DIR, f"{stem}_{n}{ext}")
                n += 1
            try:
                shutil.copyfile(src, dst)
                added += 1
            except OSError:
                pass
        self.imported = self.imported or added > 0
        if added:
            self.import_note.setStyleSheet(f"color:{GREEN}; font-size:10px;")
            self.import_note.setText(
                f"{added} image{'s' if added > 1 else ''} added — open the picker to use "
                f"{'them' if added > 1 else 'it'}.")
        else:
            self.import_note.setStyleSheet(f"color:{RED}; font-size:10px;")
            self.import_note.setText("Could not import the selected file(s).")

    def _save(self):
        self.sm.set_timeout(self.t_combo.currentData())
        self.sm.set_camera_index(self.c_combo.currentData())
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
#  Morph noise  (fbm threshold field driving the dissolve)
# ─────────────────────────────────────────────────────────────────────────────
def _fbm_field(w: int, h: int, octaves: int = 5, seed: int = 7) -> "np.ndarray":
    """A fractal value-noise field in [0,1], sized to the hero. Each octave is a
    small random grid bicubically upsampled; summing them at halving amplitude
    gives the drifting-tatter look the WebGL fbm produced in the original."""
    rng = np.random.default_rng(seed)
    field = np.zeros((h, w), np.float32)
    amp, cells = 0.5, 3
    for _ in range(octaves):
        grid = rng.random((cells + 1, cells + 1), dtype=np.float32)
        field += amp * cv2.resize(grid, (w, h), interpolation=cv2.INTER_CUBIC)
        amp *= 0.5
        cells *= 2
    field -= field.min()
    field /= max(float(field.max()), 1e-6)
    return field


def _wordmark(path: str, height: int, tint: str | None = None) -> QPixmap:
    """Load the BLOQZ wordmark (already transparent-backed PNG), trim it to its
    content, and optionally recolour the blue ink to `tint` so it reads on the
    dark UI. The white padlock detail is left white."""
    pm = QPixmap(path)
    if pm.isNull():
        return pm
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), np.uint8).reshape(h, w, 4).copy()

    fg = buf[..., 3] > 10                                  # visible pixels
    r, g, b = buf[..., 0].astype(np.int32), buf[..., 1].astype(np.int32), buf[..., 2].astype(np.int32)
    bluish = fg & (b > r + 25)                             # the wordmark, not the white lock
    if tint:
        c = QColor(tint)
        buf[bluish, 0] = c.red(); buf[bluish, 1] = c.green(); buf[bluish, 2] = c.blue()

    ys, xs = np.where(fg)                                  # trim transparent margins
    if len(xs):
        pad = 6
        x0 = max(int(xs.min()) - pad, 0); x1 = min(int(xs.max()) + pad + 1, w)
        y0 = max(int(ys.min()) - pad, 0); y1 = min(int(ys.max()) + pad + 1, h)
        buf = np.ascontiguousarray(buf[y0:y1, x0:x1])
        h, w = buf.shape[:2]
    out = QImage(buf.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(out).scaledToHeight(height, Qt.SmoothTransformation)


def _app_icon() -> QIcon:
    """The BLOQZ shark icon with its white background knocked out to transparency
    and trimmed to the shark, so it reads cleanly in the taskbar and tray."""
    # Prefer the pre-built multi-resolution .ico when present (crisp at all sizes).
    ico = _res("Asset", "logo", "icone.ico")
    if os.path.exists(ico):
        return QIcon(ico)
    pm = QPixmap(ICON_PATH)
    if pm.isNull():
        return QIcon()
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), np.uint8).reshape(h, w, 4).copy()
    lum = buf[..., :3].mean(axis=2)
    ink = lum < 210                       # shark = dark blue; background = white
    buf[..., 3] = np.where(ink, 255, 0).astype(np.uint8)
    ys, xs = np.where(ink)
    if len(xs):
        pad = 12
        x0 = max(int(xs.min()) - pad, 0); x1 = min(int(xs.max()) + pad + 1, w)
        y0 = max(int(ys.min()) - pad, 0); y1 = min(int(ys.max()) + pad + 1, h)
        buf = np.ascontiguousarray(buf[y0:y1, x0:x1])
        h, w = buf.shape[:2]
    out = QImage(buf.data, w, h, w * 4, QImage.Format_RGBA8888).copy()
    return QIcon(QPixmap.fromImage(out))


def _circular(pm: QPixmap, size: int) -> QPixmap:
    """Crop a pixmap into a soft circular badge of the given diameter."""
    if pm.isNull():
        return pm
    src = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    x = (src.width() - size) // 2
    y = (src.height() - size) // 2
    p.drawPixmap(-x, -y, src)
    p.end()
    return out


# ── Vector icons (no emoji — per design guidelines) ───────────────────────────
def _icon_image(color: str, size: int = 20) -> QIcon:
    """A framed-picture glyph: rectangle, a sun, and a mountain line."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color)); pen.setWidthF(1.6); pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    m = size * 0.14
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    p.drawRoundedRect(r, size * 0.12, size * 0.12)
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(size * 0.36, size * 0.36), size * 0.055, size * 0.055)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(m + 1, size - m - 2)
    path.lineTo(size * 0.46, size * 0.55)
    path.lineTo(size * 0.62, size * 0.7)
    path.lineTo(size * 0.74, size * 0.56)
    path.lineTo(size - m - 1, size - m - 2)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def _icon_gear(color: str, size: int = 18) -> QIcon:
    """A settings gear: toothed ring with a hollow hub."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(size / 2, size / 2)
    import math
    outer, inner, teeth = size * 0.44, size * 0.30, 8
    ring = QPainterPath()
    for i in range(teeth * 2):
        ang = math.pi * i / teeth
        rad = outer if i % 2 == 0 else outer * 0.78
        pt = QPointF(c.x() + rad * math.cos(ang), c.y() + rad * math.sin(ang))
        ring.lineTo(pt) if i else ring.moveTo(pt)
    ring.closeSubpath()
    p.setBrush(QColor(color)); p.setPen(Qt.NoPen)
    p.drawPath(ring)
    # hollow hub
    p.setBrush(Qt.transparent)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(c, inner * 0.55, inner * 0.55)
    p.end()
    return QIcon(pm)


def _pm_lock(color: str, size: int = 24) -> QPixmap:
    """A padlock glyph (feature icon)."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color); s = size
    pen = QPen(c); pen.setWidthF(1.8); pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(s*0.30, s*0.16, s*0.40, s*0.42), 0, 180*16)  # shackle
    p.setPen(Qt.NoPen); p.setBrush(c)
    body = QPainterPath(); body.addRoundedRect(QRectF(s*0.24, s*0.42, s*0.52, s*0.40), s*0.08, s*0.08)
    p.drawPath(body)
    p.setBrush(QColor(BG2))
    p.drawEllipse(QPointF(s*0.5, s*0.60), s*0.05, s*0.05)
    p.end()
    return pm


def _pm_camera(color: str, size: int = 24) -> QPixmap:
    """A camera glyph."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color); s = size
    pen = QPen(c); pen.setWidthF(1.8); pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(s*0.14, s*0.28, s*0.72, s*0.50), s*0.1, s*0.1)
    p.drawEllipse(QPointF(s*0.5, s*0.53), s*0.13, s*0.13)
    # viewfinder bump
    p.setBrush(c); p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(s*0.34, s*0.20, s*0.20, s*0.10), 2, 2)
    p.end()
    return pm


def _pm_clock(color: str, size: int = 24) -> QPixmap:
    """A clock/timer glyph."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color); s = size
    pen = QPen(c); pen.setWidthF(1.8); pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(s*0.5, s*0.54), s*0.34, s*0.34)
    p.drawLine(QPointF(s*0.5, s*0.54), QPointF(s*0.5, s*0.34))
    p.drawLine(QPointF(s*0.5, s*0.54), QPointF(s*0.64, s*0.60))
    p.end()
    return pm


def _pm_shield(color: str, size: int = 24) -> QPixmap:
    """A shield glyph (privacy / local)."""
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color); s = size
    path = QPainterPath()
    path.moveTo(s*0.5, s*0.14)
    path.lineTo(s*0.82, s*0.26)
    path.lineTo(s*0.82, s*0.52)
    path.cubicTo(s*0.82, s*0.74, s*0.66, s*0.84, s*0.5, s*0.90)
    path.cubicTo(s*0.34, s*0.84, s*0.18, s*0.74, s*0.18, s*0.52)
    path.lineTo(s*0.18, s*0.26)
    path.closeSubpath()
    pen = QPen(c); pen.setWidthF(1.8); pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen); p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    # check
    pen.setWidthF(2.0); p.setPen(pen)
    p.drawPolyline([QPointF(s*0.38, s*0.50), QPointF(s*0.47, s*0.60), QPointF(s*0.64, s*0.40)])
    p.end()
    return pm


def _pm_image(color: str, size: int = 24) -> QPixmap:
    return _icon_image(color, size).pixmap(size, size)


def _qpix_to_rgba(pm: QPixmap) -> "np.ndarray":
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), np.uint8).reshape(h, w, 4)
    return buf.copy()


# ─────────────────────────────────────────────────────────────────────────────
#  MorphHero  (full-bleed image that dissolves into the next through noise)
# ─────────────────────────────────────────────────────────────────────────────
class MorphHero(QWidget):
    DURATION  = 1400   # ms of dissolve
    EDGE      = 0.14   # width of the dissolve front, in threshold units
    LUM_BIAS  = 0.35   # how much the incoming frame's brightness burns through first

    def __init__(self, parent=None):
        super().__init__(parent)
        self._src_from = QPixmap()
        self._src_to   = QPixmap()
        self._cov_from = QPixmap()
        self._cov_to   = QPixmap()
        self._to_rgba  = None      # cached RGBA of the cover-scaled target
        self._to_lum   = None      # its luminance, for the burn-through bias
        self._noise    = None      # fbm field at the current size
        self._cache_sz = QSize(0, 0)
        self._progress = 1.0
        self._radius   = 18

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self.DURATION)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutQuint)
        self._anim.valueChanged.connect(self._on_tick)

    def _on_tick(self, v):
        self._progress = float(v)
        self.update()

    # ── Cover scaling (object-fit: cover, centre crop) ──────────────────────────
    def _cover(self, pm: QPixmap) -> QPixmap:
        if pm.isNull() or self.width() <= 0 or self.height() <= 0:
            return QPixmap()
        sc = pm.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = (sc.width()  - self.width())  // 2
        y = (sc.height() - self.height()) // 2
        return sc.copy(x, y, self.width(), self.height())

    def _rebuild_caches(self):
        self._cache_sz = self.size()
        self._cov_from = self._cover(self._src_from)
        self._cov_to   = self._cover(self._src_to)
        if not self._cov_to.isNull():
            self._to_rgba = _qpix_to_rgba(self._cov_to)
            rgb = self._to_rgba[..., :3].astype(np.float32) / 255.0
            self._to_lum = rgb.mean(axis=2)
        else:
            self._to_rgba = None
            self._to_lum  = None
        if self.width() > 0 and self.height() > 0:
            self._noise = _fbm_field(self.width(), self.height())

    # ── Public: swap to a new image ─────────────────────────────────────────────
    def set_image(self, pm: QPixmap, animate: bool = True):
        animate = animate and not self._src_to.isNull() and self.width() > 0
        self._src_from = self._src_to
        self._src_to   = pm if pm is not None else QPixmap()
        self._rebuild_caches()
        if animate:
            self._progress = 0.0
            self._anim.stop()
            self._anim.start()
        else:
            self._anim.stop()
            self._progress = 1.0
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.size() != self._cache_sz:
            self._rebuild_caches()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, self.width(), self.height(), self._radius, self._radius)
        p.setClipPath(clip)

        if self._cov_to.isNull():
            p.fillPath(clip, QColor(BG))
            p.end()
            return

        # Fully settled, or nothing to dissolve from → just the target.
        if self._progress >= 1.0 or self._cov_from.isNull() or self._noise is None:
            p.drawPixmap(0, 0, self._cov_to)
            p.end()
            return

        p.drawPixmap(0, 0, self._cov_from)

        # Widen the sweep so 0 and 1 are fully one image, then bias the threshold
        # by the target's luminance so its lit areas cross the front first.
        thr = self._progress * (1.0 + 2.0 * self.EDGE) - self.EDGE
        eff = self._noise - (self._to_lum - 0.5) * self.LUM_BIAS
        alpha = np.clip((thr - eff) / (2.0 * self.EDGE) + 0.5, 0.0, 1.0)

        out = self._to_rgba.copy()
        out[..., 3] = (alpha * 255).astype(np.uint8)
        h, w = out.shape[:2]
        qimg = QImage(out.data, w, h, w * 4, QImage.Format_RGBA8888)
        p.drawImage(0, 0, qimg)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  Thumbnail strip button
# ─────────────────────────────────────────────────────────────────────────────
class ThumbButton(QPushButton):
    picked = Signal(int)

    def __init__(self, index: int, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.index = index
        self.setFixedSize(84, 54)
        self.setCursor(Qt.PointingHandCursor)
        self._pm = pixmap
        self._active = False
        self._hover  = False
        self.clicked.connect(lambda: self.picked.emit(self.index))

    def set_active(self, on: bool):
        self._active = on
        self.update()

    def enterEvent(self, event):
        self._hover = True; self.update()

    def leaveEvent(self, event):
        self._hover = False; self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(float(r.x()), float(r.y()), float(r.width()), float(r.height()), 8, 8)
        p.setClipPath(path)
        if not self._pm.isNull():
            sc = self._pm.scaled(r.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            # active = 1.0, hover = 0.85, idle = 0.55  (React thumbnail states)
            p.setOpacity(1.0 if self._active else (0.85 if self._hover else 0.55))
            p.drawPixmap(r.x() + (r.width()-sc.width())//2, r.y() + (r.height()-sc.height())//2, sc)
            p.setOpacity(1.0)
        else:
            p.fillPath(path, QColor(SURFACE))
            p.setPen(QColor(MUTED)); p.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, "No BG")
        p.setClipping(False)
        # border-2: solid white when active, faint on hover, transparent otherwise
        if self._active:
            pen = QPen(QColor(TEXT))
        elif self._hover:
            pen = QPen(QColor(255, 255, 255, 90))
        else:
            pen = QPen(QColor(0, 0, 0, 0))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawRoundedRect(r, 8, 8)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  Inline Background Picker  (morph gallery — lives inside the stack)
# ─────────────────────────────────────────────────────────────────────────────
class BackgroundPickerWidget(QWidget):
    background_selected = Signal()  # emitted when user picks or clears

    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self.sm       = sm
        self._paths   : list[str]     = [""]
        self._pixmaps : list[QPixmap] = [QPixmap()]
        self._active  = 0

        self._load_assets()
        self._build_ui()

    # ── Asset loading ───────────────────────────────────────────────────────────
    def _load_assets(self):
        seen = set()
        for folder in (BUNDLED_BG_DIR, USER_BG_DIR):
            if not os.path.isdir(folder):
                continue
            for f in sorted(os.listdir(folder)):
                if not f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                    continue
                if f in seen:            # a user import shadows a bundled default
                    continue
                seen.add(f)
                full = os.path.abspath(os.path.join(folder, f))
                pm   = QPixmap(full)
                if not pm.isNull():
                    self._paths.append(full)
                    self._pixmaps.append(pm)

    def _display_pixmap(self, i: int) -> QPixmap:
        """The pixmap shown for slot i; the empty 'No background' slot renders
        as the app's own gradient rather than a blank tile."""
        pm = self._pixmaps[i]
        if not pm.isNull():
            return pm
        grad_pm = QPixmap(600, 800)
        grad_pm.fill(Qt.transparent)
        gp = QPainter(grad_pm)
        g = QLinearGradient(0, 0, 0, 800)
        g.setColorAt(0, QColor(BG)); g.setColorAt(1, QColor(BG2))
        gp.fillRect(grad_pm.rect(), g)
        gp.end()
        return grad_pm

    def _populate_thumbs(self):
        """(Re)build the thumbnail strip from the current asset list."""
        lay = self._strip_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._thumbs = []
        lay.addStretch()
        for i in range(len(self._paths)):
            t = ThumbButton(i, self._display_pixmap(i), self._strip.widget())
            t.picked.connect(self._go)
            lay.addWidget(t)
            self._thumbs.append(t)
        lay.addStretch()

    def reload_assets(self):
        """Rescan the Asset folder (e.g. after the user imports an image) and
        rebuild the strip, keeping the current selection if it still exists."""
        self._paths   = [""]
        self._pixmaps = [QPixmap()]
        self._load_assets()
        self._populate_thumbs()

    # ── UI ──────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.setStyleSheet("background: transparent;")

        self._hero = MorphHero(self)

        # gradient scrim over the bottom of the hero (from-transparent to-black/65)
        self._scrim = QLabel(self)
        self._scrim.setAttribute(Qt.WA_TransparentForMouseEvents)

        # counter (top-left) over the hero — index only, never file names
        self._counter = QLabel("", self)
        self._counter.setStyleSheet(
            f"color:{TEXT}; font-family:{FONT_MONO}; font-size:11px; font-weight:700; letter-spacing:2px;"
            "background:rgba(6,15,30,110); border:1px solid rgba(255,255,255,30);"
            "border-radius:11px; padding:4px 12px;")

        # arrows — glassy circular, matching the MorphGallery React component
        # (h-11 w-11, rounded-full, border-white/20, bg-white/10, hover bg-white/25)
        self._prev = QPushButton("‹", self)
        self._next = QPushButton("›", self)
        for b, slot in ((self._prev, -1), (self._next, 1)):
            b.setFixedSize(44, 44)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{border:1px solid rgba(255,255,255,50);"
                "border-radius:22px; background:rgba(255,255,255,26);"
                f"color:{TEXT}; font-size:24px; font-weight:600; padding-bottom:4px;}}"
                "QPushButton:hover{background:rgba(255,255,255,64); border-color:rgba(255,255,255,90);}"
                "QPushButton:pressed{background:rgba(255,255,255,40);}")
            b.clicked.connect(lambda _=False, s=slot: self._go(self._active + s))

        # thumbnail strip
        self._strip = QScrollArea(self)
        self._strip.setWidgetResizable(True)
        self._strip.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._strip.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._strip.setFrameShape(QFrame.NoFrame)
        self._strip.setFixedHeight(66)
        self._strip.setStyleSheet("background:transparent;")
        strip_inner = QWidget()
        strip_inner.setStyleSheet("background:transparent;")
        self._strip_layout = QHBoxLayout(strip_inner)
        self._strip_layout.setContentsMargins(10, 4, 10, 4)
        self._strip_layout.setSpacing(8)
        self._thumbs: list[ThumbButton] = []
        self._strip.setWidget(strip_inner)
        self._populate_thumbs()

        # bottom bar
        self._bar = QWidget(self)
        bl = QHBoxLayout(self._bar)
        bl.setContentsMargins(20, 6, 20, 6)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(self._glass_btn())
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.background_selected.emit)
        bl.addWidget(back_btn)
        bl.addStretch()

        no_bg_btn = QPushButton("No background")
        no_bg_btn.setStyleSheet(self._glass_btn())
        no_bg_btn.setCursor(Qt.PointingHandCursor)
        no_bg_btn.clicked.connect(self._clear_bg)
        bl.addWidget(no_bg_btn)
        bl.addSpacing(10)

        self._sel_btn = QPushButton("Select")
        self._sel_btn.setStyleSheet(self._primary_btn())
        self._sel_btn.setCursor(Qt.PointingHandCursor)
        self._sel_btn.clicked.connect(self._select_current)
        bl.addWidget(self._sel_btn)

    @staticmethod
    def _glass_btn():
        # frosted control, like the gallery's arrow/overlay chrome
        return """
            QPushButton {
                background:rgba(255,255,255,18); color:#f2f7ff;
                border:1px solid rgba(255,255,255,45); border-radius:10px;
                padding:8px 18px; font-size:12px; font-weight:600;
            }
            QPushButton:hover { background:rgba(255,255,255,40); border-color:rgba(255,255,255,90); }
            QPushButton:pressed { background:rgba(255,255,255,26); }
        """

    @staticmethod
    def _primary_btn():
        return f"""
            QPushButton {{
                background:{BLUE}; color:#04101f;
                border:1px solid {BLUE}; border-radius:10px;
                padding:8px 24px; font-size:12px; font-weight:800;
            }}
            QPushButton:hover {{ background:#7bbcff; border-color:#7bbcff; }}
            QPushButton:pressed {{ background:{BLUE_DIM}; }}
        """

    # ── Geometry ──────────────────────────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        bar_h, strip_h = 48, 66
        hero_h = h - bar_h - strip_h
        hx, hy, hw, hh = 12, 12, w - 24, hero_h - 24
        self._hero.setGeometry(hx, hy, hw, hh)

        # gradient scrim across the bottom third of the hero
        scrim_h = min(int(hh * 0.42), 220)
        self._scrim.setGeometry(hx, hy + hh - scrim_h, hw, scrim_h)
        self._paint_scrim(hw, scrim_h)
        self._scrim.raise_()
        self._counter.raise_()
        self._prev.raise_(); self._next.raise_()

        self._strip.setGeometry(0, hero_h, w, strip_h)
        self._bar.setGeometry(0, h - bar_h, w, bar_h)

        self._counter.adjustSize()
        self._counter.move(hx + 12, hy + 12)

        self._prev.move(hx + 12, hy + (hh - 44) // 2)
        self._next.move(hx + hw - 56, hy + (hh - 44) // 2)

    def _paint_scrim(self, w: int, h: int):
        if w <= 0 or h <= 0:
            return
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(4, 10, 20, 0))
        g.setColorAt(1.0, QColor(4, 10, 20, 166))   # ~ to-black/65
        # clip to the hero's rounded bottom corners
        path = QPainterPath()
        path.addRoundedRect(0, -20, w, h + 20, 18, 18)
        p.setClipPath(path)
        p.fillRect(0, 0, w, h, g)
        p.end()
        self._scrim.setPixmap(pm)

    # ── Navigation ──────────────────────────────────────────────────────────────
    def _go(self, i: int, animate: bool = True):
        n = len(self._paths)
        if n == 0:
            return
        i = i % n
        self._active = i
        self._hero.set_image(self._display_pixmap(i), animate=animate)
        self._update_ui()

    def _update_ui(self):
        i = self._active
        self._counter.setText(f"{i+1:02d} / {len(self._paths):02d}")
        for t in self._thumbs:
            t.set_active(t.index == i)
        # keep the active thumb in view
        if 0 <= i < len(self._thumbs):
            self._strip.ensureWidgetVisible(self._thumbs[i], 60, 0)
        self._counter.adjustSize()

    # ── Actions ───────────────────────────────────────────────────────────────
    def _select_current(self):
        self.sm.set_background(self._paths[self._active])
        self.background_selected.emit()

    def _clear_bg(self):
        self.sm.set_background("")
        self.background_selected.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Right, Qt.Key_Down):
            self._go(self._active + 1)
        elif event.key() in (Qt.Key_Left, Qt.Key_Up):
            self._go(self._active - 1)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._select_current()

    # ── Reset when shown again ────────────────────────────────────────────────
    def reset(self):
        current = self.sm.get_background()
        start = 0
        if current:
            for j, pth in enumerate(self._paths):
                if pth == current:
                    start = j
                    break
        self._go(start, animate=False)

# ─────────────────────────────────────────────────────────────────────────────
#  Status Orb  (animated scanner ring — the app's focal point)
# ─────────────────────────────────────────────────────────────────────────────
class StatusOrb(QWidget):
    """A breathing radial orb with a rotating scanner arc. Its colour and motion
    reflect the current protection state, so the whole screen reads at a glance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
        self._color   = QColor(BLUE)
        self._target  = QColor(BLUE)
        self._pulse   = 0.0     # 0..1 breathing phase
        self._sweep   = 0.0     # 0..360 scanner angle
        self._spin    = True    # whether the scanner arc rotates

        # breathing pulse (opacity/size)
        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setDuration(2200)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_anim.valueChanged.connect(self._on_pulse)
        self._pulse_anim.start()

        # smooth colour transitions between states
        self._color_anim = QVariantAnimation(self)
        self._color_anim.setDuration(450)
        self._color_anim.valueChanged.connect(self._on_color)

        # scanner rotation
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._on_spin)
        self._spin_timer.start(16)

    def set_state_color(self, hexcolor: str, spin: bool = True):
        self._spin = spin
        self._target = QColor(hexcolor)
        self._color_anim.stop()
        self._color_anim.setStartValue(QColor(self._color))
        self._color_anim.setEndValue(QColor(hexcolor))
        self._color_anim.start()

    def _on_pulse(self, v):
        self._pulse = float(v)
        self.update()

    def _on_color(self, c):
        self._color = QColor(c)
        self.update()

    def _on_spin(self):
        if self._spin:
            self._sweep = (self._sweep + 2.4) % 360.0
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        breathe = 0.5 + 0.5 * abs(self._pulse * 2 - 1)  # triangle 0..1
        base_r  = 46
        c = self._color

        # soft, restrained halo (tinted ambient depth — not a neon glow)
        halo_r = base_r + 16 + breathe * 6
        glow = QRadialGradient(cx, cy, halo_r)
        glow.setColorAt(0.62, QColor(c.red(), c.green(), c.blue(), 34))
        glow.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # faint track ring
        p.setBrush(Qt.NoBrush)
        track = QColor(c); track.setAlpha(45)
        pen = QPen(track); pen.setWidth(2)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), base_r, base_r)

        # rotating scanner arc
        arc = QColor(c); arc.setAlpha(235)
        pen = QPen(arc); pen.setWidth(3); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        rect = QRectF(cx - base_r, cy - base_r, base_r * 2, base_r * 2)
        p.drawArc(rect, int(-self._sweep * 16), int(110 * 16))

        # inner disc
        disc = QRadialGradient(cx, cy - 6, base_r - 6)
        disc.setColorAt(0.0, QColor(SURFACE))
        disc.setColorAt(1.0, QColor(BG2))
        p.setPen(Qt.NoPen)
        p.setBrush(disc)
        p.drawEllipse(QPointF(cx, cy), base_r - 8, base_r - 8)
        # 1px top-edge highlight — physical refraction, not a glow
        p.setBrush(Qt.NoBrush)
        rim = QPen(QColor(255, 255, 255, 26)); rim.setWidth(1)
        p.setPen(rim)
        p.drawArc(QRectF(cx - (base_r - 8), cy - (base_r - 8),
                         (base_r - 8) * 2, (base_r - 8) * 2), 30 * 16, 120 * 16)

        # padlock mark (echoes the lock in the BLOQZ logo), tinted to the state
        self._draw_lock(p, cx, cy, c)
        p.end()

    @staticmethod
    def _draw_lock(p: QPainter, cx: float, cy: float, c: QColor):
        body_w, body_h = 26.0, 20.0
        bx, by = cx - body_w / 2, cy - 2
        # shackle (the arc on top)
        pen = QPen(c); pen.setWidth(3); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        sh_r = 8.0
        p.drawArc(QRectF(cx - sh_r, by - sh_r - 3, sh_r * 2, sh_r * 2 + 6),
                  0 * 16, 180 * 16)
        # body
        p.setPen(Qt.NoPen); p.setBrush(c)
        body = QPainterPath()
        body.addRoundedRect(QRectF(bx, by, body_w, body_h), 5, 5)
        p.drawPath(body)
        # keyhole
        p.setBrush(QColor(BG2))
        p.drawEllipse(QPointF(cx, cy + 5), 2.6, 2.6)


# ─────────────────────────────────────────────────────────────────────────────
#  Home View  (the main protection screen)
# ─────────────────────────────────────────────────────────────────────────────
class HomeView(QWidget):
    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self.sm = sm
        self.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(44, 26, 44, 24)
        layout.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        top = QHBoxLayout()
        brand = QLabel()
        wm = _wordmark(LOGO_PATH, 36, tint=BLUE)
        if not wm.isNull():
            brand.setPixmap(wm)
        else:
            brand.setText("BLOQZ")
            brand.setStyleSheet(f"font-size:15px; font-weight:800; color:{BLUE}; letter-spacing:4px;")
        top.addWidget(brand)
        top.addStretch()

        # countdown chip — hidden until the user leaves the camera
        self.countdown_chip = QLabel()
        self.countdown_chip.setAlignment(Qt.AlignCenter)
        self.countdown_chip.setFixedHeight(30)
        self.countdown_chip.setMinimumWidth(52)
        self.countdown_chip.setVisible(False)
        self._style_chip(AMBER)
        top.addWidget(self.countdown_chip)
        top.addSpacing(8)

        self.bg_btn = QPushButton()
        self.bg_btn.setIcon(_icon_image(BLUE, 20))
        self.bg_btn.setIconSize(QSize(20, 20))
        self.bg_btn.setFixedSize(36, 36)
        self.bg_btn.setToolTip("Change background")
        self.bg_btn.setStyleSheet(
            "QPushButton{border:1px solid " + BORDER + "; border-radius:10px;"
            "background:rgba(16,31,56,140);}"
            "QPushButton:hover{background:" + SURFACE + "; border-color:" + BLUE + ";}"
            "QPushButton:pressed{background:" + BORDER + ";}")
        self.bg_btn.setCursor(Qt.PointingHandCursor)
        top.addWidget(self.bg_btn)
        top.addSpacing(8)

        self.help_btn = QPushButton("?")
        self.help_btn.setFixedSize(36, 36)
        self.help_btn.setToolTip("About BLOQZ")
        self.help_btn.setStyleSheet(
            "QPushButton{border:1px solid " + BORDER + "; border-radius:10px;"
            "background:rgba(16,31,56,140); color:" + MUTED + "; font-size:16px; font-weight:800;}"
            "QPushButton:hover{background:" + SURFACE + "; border-color:" + BLUE + "; color:" + BLUE + ";}"
            "QPushButton:pressed{background:" + BORDER + ";}")
        self.help_btn.setCursor(Qt.PointingHandCursor)
        top.addWidget(self.help_btn)
        layout.addLayout(top)

        layout.addStretch(2)

        # ── Status orb ────────────────────────────────────────────────────────
        self.orb = StatusOrb()
        orb_row = QHBoxLayout()
        orb_row.addStretch(); orb_row.addWidget(self.orb); orb_row.addStretch()
        layout.addLayout(orb_row)

        layout.addSpacing(26)

        # ── Status ────────────────────────────────────────────────────────────
        self.status_lbl = QLabel("INITIALIZING")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet(
            f"font-size:23px; font-weight:800; color:{TEXT}; letter-spacing:3px;")
        layout.addWidget(self.status_lbl)

        layout.addSpacing(9)

        self.sub_lbl = QLabel("Starting camera…")
        self.sub_lbl.setAlignment(Qt.AlignCenter)
        self.sub_lbl.setStyleSheet(f"font-size:13px; color:{MUTED}; letter-spacing:.3px;")
        layout.addWidget(self.sub_lbl)

        layout.addStretch(3)

        # ── Footer status pill ─────────────────────────────────────────────────
        self.footer = QLabel("Protection active")
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setStyleSheet(self._pill_css(BLUE_DIM, FAINT))
        foot_row = QHBoxLayout()
        foot_row.addStretch(); foot_row.addWidget(self.footer); foot_row.addStretch()
        layout.addLayout(foot_row)

        layout.addSpacing(18)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.setSpacing(12)

        self.settings_btn = QPushButton("  Settings")
        self.settings_btn.setIcon(_icon_gear(MUTED, 16))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.setStyleSheet(self._btn(BORDER, MUTED, SURFACE, BLUE))
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btns.addWidget(self.settings_btn)

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.setStyleSheet(self._btn(BORDER, MUTED, "#2a0d1a", RED))
        self.quit_btn.setCursor(Qt.PointingHandCursor)
        self.quit_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btns.addWidget(self.quit_btn)
        layout.addLayout(btns)

    @staticmethod
    def _pill_css(border, fg):
        return (f"font-size:11px; font-weight:600; color:{fg}; letter-spacing:1px;"
                f"border:1px solid {border}; border-radius:11px;"
                "background:rgba(16,31,56,120); padding:4px 14px;")

    @staticmethod
    def _btn(bd, fg, hbg, hfg):
        return f"""
            QPushButton {{
                background:rgba(16,31,56,90); color:{fg};
                border:1px solid {bd}; border-radius:10px;
                padding:9px 18px; font-size:12px; font-weight:600;
            }}
            QPushButton:hover {{ background:{hbg}; color:{hfg}; border-color:{hfg}; }}
            QPushButton:pressed {{ background:{bd}; }}
        """

    def _style_chip(self, color: str):
        self.countdown_chip.setStyleSheet(
            f"color:{color}; font-family:{FONT_MONO}; font-size:14px; font-weight:800;"
            f"letter-spacing:1px; border:1px solid {color}; border-radius:15px;"
            "background:rgba(16,31,56,150); padding:2px 12px;")

    def show_countdown(self, seconds: int):
        color = RED if seconds <= 5 else AMBER
        self._style_chip(color)
        self.countdown_chip.setText(f"{seconds}s")
        self.countdown_chip.setToolTip(f"Locking in {seconds}s")
        self.countdown_chip.setVisible(True)

    def hide_countdown(self):
        self.countdown_chip.setVisible(False)

    def set_status(self, title: str, sub: str, footer: str,
                   title_color: str = TEXT, sub_color: str = MUTED, footer_color: str = BLUE_DIM,
                   orb_color: str = BLUE, orb_spin: bool = True):
        self.status_lbl.setText(title)
        self.status_lbl.setStyleSheet(
            f"font-size:23px; font-weight:800; color:{title_color}; letter-spacing:3px;")
        self.sub_lbl.setText(sub)
        self.sub_lbl.setStyleSheet(f"font-size:13px; color:{sub_color}; letter-spacing:.3px;")
        self.footer.setText(footer)
        self.footer.setStyleSheet(self._pill_css(footer_color, footer_color))
        self.orb.set_state_color(orb_color, spin=orb_spin)


# ─────────────────────────────────────────────────────────────────────────────
#  Sprite Sheet Animation  (horizontal strip → frame-by-frame playback)
# ─────────────────────────────────────────────────────────────────────────────
class SpriteSheetWidget(QWidget):
    """Plays a horizontal sprite sheet frame by frame. `bounce` ping-pongs the
    sequence (0→n-1→0), which reads as a smooth turn-and-return for the shark
    rather than a hard jump back to the first pose."""

    def __init__(self, path: str, frames: int = 5, fps: int = 9,
                 bounce: bool = True, parent=None):
        super().__init__(parent)
        self._frames = self._slice(QPixmap(path), frames)
        self._i      = 0
        self._dir    = 1
        self._bounce = bounce
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._interval = max(int(1000 / max(fps, 1)), 16)

    @staticmethod
    def _slice(sheet: QPixmap, n: int) -> list[QPixmap]:
        if sheet.isNull() or n <= 0:
            return []
        w, h = sheet.width(), sheet.height()
        out = []
        for i in range(n):
            x0 = round(i * w / n)
            x1 = round((i + 1) * w / n)
            out.append(sheet.copy(x0, 0, x1 - x0, h))
        return out

    def start(self):
        if self._frames:
            self._timer.start(self._interval)

    def stop(self):
        self._timer.stop()

    def _advance(self):
        n = len(self._frames)
        if n <= 1:
            return
        if self._bounce:
            self._i += self._dir
            if self._i >= n - 1:
                self._i = n - 1; self._dir = -1
            elif self._i <= 0:
                self._i = 0; self._dir = 1
        else:
            self._i = (self._i + 1) % n
        self.update()

    def paintEvent(self, event):
        if not self._frames:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        fr = self._frames[self._i]
        sc = fr.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - sc.width()) // 2
        y = (self.height() - sc.height()) // 2
        p.drawPixmap(x, y, sc)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
#  Loading View  (shown while the camera initialises)
# ─────────────────────────────────────────────────────────────────────────────
class LoadingView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.addStretch(2)

        wm = _wordmark(LOGO_PATH, 40, tint=BLUE)
        brand = QLabel(); brand.setAlignment(Qt.AlignCenter)
        if not wm.isNull():
            brand.setPixmap(wm)
        else:
            brand.setText("BLOQZ")
            brand.setStyleSheet(f"font-size:26px; font-weight:800; color:{BLUE}; letter-spacing:6px;")
        layout.addWidget(brand)

        layout.addSpacing(30)

        # animated shark sprite sheet (req.png, 5 frames, ping-pong)
        self.sprite = SpriteSheetWidget(SPRITE_PATH, frames=5, fps=9, bounce=True)
        self.sprite.setFixedSize(230, 150)
        sp_row = QHBoxLayout()
        sp_row.addStretch(); sp_row.addWidget(self.sprite); sp_row.addStretch()
        layout.addLayout(sp_row)

        layout.addSpacing(26)

        self._msg = QLabel("Starting camera")
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setStyleSheet(f"font-size:13px; color:{MUTED}; letter-spacing:1px;")
        layout.addWidget(self._msg)

        layout.addStretch(3)

        # animated ellipsis
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._timer.start(400)
        self.sprite.start()

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        self._msg.setText("Starting camera" + "." * self._dots)

    def set_message(self, text: str):
        self._msg.setText(text)

    def stop(self):
        self._timer.stop()
        self.sprite.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  Consent View  (data-protection policy — mandatory before first use)
# ─────────────────────────────────────────────────────────────────────────────
class ConsentView(QWidget):
    accepted = Signal()

    POLICY_HTML = f"""
    <p style="color:{TEXT}; font-size:13px; font-weight:700;">Protection de vos données</p>
    <p style="color:{MUTED}; font-size:12px; line-height:150%;">
      BLOQZ utilise votre <b>webcam</b> pour détecter en temps réel votre présence
      (détection de visage) afin de verrouiller automatiquement votre session
      lorsque vous vous éloignez.
    </p>
    <p style="color:{MUTED}; font-size:12px; line-height:150%;">
      <b>Traitement 100&nbsp;% local&nbsp;:</b> les images sont analysées à la volée
      sur votre appareil. Aucune image n'est enregistrée, stockée, ni transmise à
      un tiers ou à Internet. Aucun profil biométrique n'est conservé.
    </p>
    <p style="color:{MUTED}; font-size:12px; line-height:150%;">
      <b>Base légale&nbsp;:</b> votre consentement, conformément à la
      <a href="{LAW_CODE_NUM_URL}" style="color:{BLUE};">Loi n°2017-20 portant Code du
      numérique en République du Bénin</a> et à la
      <a href="{LAW_2020_35_URL}" style="color:{BLUE};">Loi n°2020-35</a> qui la modifie.
    </p>
    <p style="color:{MUTED}; font-size:12px; line-height:150%;">
      <b>Vos droits</b> (accès, rectification, opposition, effacement)&nbsp;: comme
      rien n'est conservé, vous les exercez en désactivant la protection, en
      choisissant «&nbsp;No background&nbsp;», ou en désinstallant l'application.
      Vous pouvez aussi saisir l'<b>APDP</b> (Autorité de Protection des Données
      Personnelles du Bénin).
    </p>
    <p style="color:{FAINT}; font-size:11px; line-height:150%;">
      La détection de visage peut constituer une donnée à caractère personnel.
      En cochant la case ci-dessous, vous consentez librement à ce traitement pour
      la seule finalité de verrouillage automatique.
    </p>
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 26, 36, 24)
        layout.setSpacing(0)

        title = QLabel("CONSENTEMENT")
        title.setStyleSheet(f"font-size:16px; font-weight:800; color:{BLUE}; letter-spacing:3px;")
        layout.addWidget(title)
        layout.addSpacing(4)
        sub = QLabel("Protection des données — Bénin")
        sub.setStyleSheet(f"font-size:12px; color:{MUTED};")
        layout.addWidget(sub)
        layout.addSpacing(14)

        # scrollable policy text
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        body = QLabel()
        body.setText(self.POLICY_HTML)
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setOpenExternalLinks(True)
        body.setAlignment(Qt.AlignTop)
        body.setStyleSheet(
            f"background:rgba(16,31,56,90); border:1px solid {BORDER};"
            "border-radius:12px; padding:14px;")
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        layout.addSpacing(12)

        # consent checkbox
        self.check = QCheckBox(
            "J'ai lu et j'accepte le traitement de ma webcam pour le verrouillage "
            "automatique (Loi n°2017-20 & Loi n°2020-35).")
        self.check.setCursor(Qt.PointingHandCursor)
        self.check.setStyleSheet(f"""
            QCheckBox {{ color:{TEXT}; font-size:12px; }}
            QCheckBox::indicator {{ width:20px; height:20px; }}
            QCheckBox::indicator:unchecked {{
                border:1px solid {BORDER}; border-radius:5px; background:{SURFACE};
            }}
            QCheckBox::indicator:checked {{
                border:1px solid {BLUE}; border-radius:5px; background:{BLUE};
            }}
        """)
        self.check.toggled.connect(self._on_toggle)
        layout.addWidget(self.check)

        layout.addSpacing(12)

        self.accept_btn = QPushButton("Accepter et continuer")
        self.accept_btn.setEnabled(False)
        self.accept_btn.setCursor(Qt.PointingHandCursor)
        self._style_accept()
        self.accept_btn.clicked.connect(self.accepted.emit)
        layout.addWidget(self.accept_btn)

    def _on_toggle(self, on: bool):
        self.accept_btn.setEnabled(on)
        self._style_accept()

    def _style_accept(self):
        on = self.accept_btn.isEnabled()
        bg = BLUE if on else SURFACE
        fg = "#04101f" if on else FAINT
        self.accept_btn.setStyleSheet(f"""
            QPushButton {{
                background:{bg}; color:{fg}; border:1px solid {BLUE if on else BORDER};
                border-radius:11px; padding:11px 24px; font-size:13px; font-weight:800;
            }}
            QPushButton:hover {{ background:{'#7bbcff' if on else SURFACE}; }}
            QPushButton:pressed {{ background:{BLUE_DIM if on else SURFACE}; }}
        """)


# ─────────────────────────────────────────────────────────────────────────────
#  About View  (what BLOQZ is + what you can do with it)
# ─────────────────────────────────────────────────────────────────────────────
class AboutView(QWidget):
    done = Signal()   # user finished onboarding / closed the page

    FEATURES = [
        (_pm_camera, "Face-aware auto-lock",
         "BLOQZ watches your webcam and locks Windows the moment you step away."),
        (_pm_clock,  "Grace countdown",
         "A short delay before locking — a live countdown shows in the top bar."),
        (_pm_image,  "Custom backgrounds",
         "Pick or import your own image; slides dissolve with a noise morph."),
        (_pm_shield, "Private by design",
         "Frames are analysed locally in real time. Nothing is recorded or uploaded."),
    ]

    def __init__(self, first_run: bool = True, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 28)
        layout.setSpacing(0)

        # header: wordmark + tagline
        wm = _wordmark(LOGO_PATH, 34, tint=BLUE)
        brand = QLabel(); brand.setAlignment(Qt.AlignCenter)
        if not wm.isNull():
            brand.setPixmap(wm)
        else:
            brand.setText("BLOQZ")
            brand.setStyleSheet(f"font-size:22px; font-weight:800; color:{BLUE}; letter-spacing:5px;")
        layout.addWidget(brand)
        layout.addSpacing(8)

        tag = QLabel("Your screen locks itself when you're not there.")
        tag.setAlignment(Qt.AlignCenter)
        tag.setWordWrap(True)
        tag.setStyleSheet(f"font-size:13px; color:{MUTED};")
        layout.addWidget(tag)

        layout.addSpacing(22)

        # feature rows
        for icon_fn, title, desc in self.FEATURES:
            layout.addWidget(self._feature(icon_fn, title, desc))
            layout.addSpacing(14)

        layout.addStretch(1)

        # CTA
        self.cta = QPushButton("Get started" if first_run else "Back")
        self.cta.setStyleSheet(f"""
            QPushButton {{
                background:{BLUE}; color:#04101f; border:1px solid {BLUE};
                border-radius:11px; padding:11px 24px; font-size:13px; font-weight:800;
            }}
            QPushButton:hover {{ background:#7bbcff; border-color:#7bbcff; }}
            QPushButton:pressed {{ background:{BLUE_DIM}; }}
        """)
        self.cta.setCursor(Qt.PointingHandCursor)
        self.cta.clicked.connect(self.done.emit)
        layout.addWidget(self.cta)

    @staticmethod
    def _feature(icon_fn, title: str, desc: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            f"background:rgba(16,31,56,110); border:1px solid {BORDER}; border-radius:14px;")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(14)

        badge = QLabel(); badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(icon_fn(BLUE, 24))
        badge.setStyleSheet(
            f"background:rgba(90,169,255,28); border:1px solid {BLUE_DIM}; border-radius:10px;")
        row.addWidget(badge, 0, Qt.AlignTop)

        col = QVBoxLayout(); col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"background:transparent; border:none; font-size:13px; font-weight:700; color:{TEXT};")
        d = QLabel(desc); d.setWordWrap(True)
        d.setStyleSheet(f"background:transparent; border:none; font-size:11px; color:{MUTED};")
        col.addWidget(t); col.addWidget(d)
        row.addLayout(col, 1)
        return card


# ─────────────────────────────────────────────────────────────────────────────
#  Splash Screen  (brand reveal at launch — frameless, fades out)
# ─────────────────────────────────────────────────────────────────────────────
class SplashScreen(QWidget):
    finished = Signal()

    def __init__(self, duration: int = 1900):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setFixedSize(460, 570)
        self._duration = duration

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._card = QWidget()
        self._card.setStyleSheet(
            f"background:{BG}; border:1px solid {BORDER}; border-radius:18px;")
        root.addWidget(self._card)

        lay = QVBoxLayout(self._card)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.addStretch(2)

        # animated shark mascot (guaranteed on-screen for the splash duration)
        self.sprite = SpriteSheetWidget(SPRITE_PATH, frames=5, fps=9, bounce=True)
        self.sprite.setFixedSize(260, 168)
        sp_row = QHBoxLayout()
        sp_row.addStretch(); sp_row.addWidget(self.sprite); sp_row.addStretch()
        lay.addLayout(sp_row)

        lay.addSpacing(26)

        wm = _wordmark(LOGO_PATH, 46, tint=BLUE)
        brand = QLabel(); brand.setAlignment(Qt.AlignCenter)
        if not wm.isNull():
            brand.setPixmap(wm)
        else:
            brand.setText("BLOQZ")
            brand.setStyleSheet(f"font-size:30px; font-weight:800; color:{BLUE}; letter-spacing:7px;")
        lay.addWidget(brand)

        lay.addSpacing(10)
        tag = QLabel("Face-aware auto-lock")
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet(f"font-size:12px; color:{MUTED}; letter-spacing:3px;")
        lay.addWidget(tag)
        lay.addStretch(3)

        # fade-in
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fade = QPropertyAnimation(self._fx, b"opacity", self)
        self._fade.setDuration(500)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)

    def start(self):
        # centre on screen
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - self.width() // 2,
                  scr.center().y() - self.height() // 2)
        self.show()
        self.sprite.start()
        self._fade.start()
        QTimer.singleShot(self._duration, self._dismiss)

    def _dismiss(self):
        self._out = QPropertyAnimation(self._fx, b"opacity", self)
        self._out.setDuration(420)
        self._out.setStartValue(1.0)
        self._out.setEndValue(0.0)
        self._out.setEasingCurve(QEasingCurve.InCubic)
        self._out.finished.connect(self._close)
        self._out.start()

    def _close(self):
        self.sprite.stop()
        self.finished.emit()
        self.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sm              = SettingsManager()
        self.timeout_seconds = self.sm.get_timeout()
        self.countdown       = self.timeout_seconds
        self.state           = "INITIALIZING"

        self.setWindowTitle("BLOQZ")
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(400, 500)
        self.resize(460, 570)
        self.setStyleSheet(f"QMainWindow {{ background:{BG}; }} QWidget {{ background:transparent; }}")

        # ── Stacked views ─────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._home = HomeView(self.sm)
        self._picker = BackgroundPickerWidget(self.sm)
        self._loading = LoadingView()
        self._about = AboutView(first_run=not self.sm.get_onboarded())
        self._consent = ConsentView()

        self._stack.addWidget(self._home)     # index 0
        self._stack.addWidget(self._picker)   # index 1
        self._stack.addWidget(self._loading)  # index 2
        self._stack.addWidget(self._about)    # index 3
        self._stack.addWidget(self._consent)  # index 4

        # wire home buttons
        self._home.bg_btn.clicked.connect(self._show_picker)
        self._home.settings_btn.clicked.connect(self._open_settings)
        self._home.quit_btn.clicked.connect(self._quit)
        self._home.help_btn.clicked.connect(self._show_about)

        # wire picker + about + consent
        self._picker.background_selected.connect(self._show_home)
        self._about.done.connect(self._finish_about)
        self._consent.accepted.connect(self._accept_consent)

        # ── Timer & camera ────────────────────────────────────────────────────
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._cam = None
        self._ready = False

        # ── Tray ──────────────────────────────────────────────────────────────
        self._setup_tray()

        # The camera only starts AFTER data-protection consent. Without consent,
        # go straight to the consent screen and touch no webcam at all.
        if self.sm.has_consented():
            self._begin_protection()
        else:
            self._stack.setCurrentWidget(self._consent)

    # ── Camera lifecycle (never runs before consent) ───────────────────────────
    def _begin_protection(self):
        """Start the webcam + show the loading screen while it warms up."""
        self._ready = False
        self._stack.setCurrentWidget(self._loading)
        self._loading.start()
        self._loading_since = time.monotonic()

        if self._cam is None:
            self._cam = CameraManager(self.sm.get_camera_index())
            self._cam.face_detected.connect(self._on_face)
            self._cam.camera_error.connect(self._on_cam_error)
            self._cam.start()

        QTimer.singleShot(6000, self._leave_loading_fallback)

    # ── Painting (no overlay — raw background) ────────────────────────────────
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        bg_path = self.sm.get_background()
        if bg_path and os.path.exists(bg_path):
            pm = QPixmap(bg_path)
            painter.drawPixmap(
                self.rect(),
                pm.scaled(self.rect().size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            )
        else:
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, QColor(BG))
            grad.setColorAt(1, QColor(BG2))
            painter.fillRect(self.rect(), grad)
            # soft radial glow behind the orb region for depth
            painter.setRenderHint(QPainter.Antialiasing)
            cx, cy = self.width() / 2, self.height() * 0.42
            glow = QRadialGradient(cx, cy, self.width() * 0.7)
            glow.setColorAt(0.0, QColor(30, 60, 110, 90))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawRect(self.rect())
        painter.end()

    # ── View switching ────────────────────────────────────────────────────────
    def _show_picker(self):
        self._picker.reload_assets()
        self._picker.reset()
        self._stack.setCurrentIndex(1)

    def _show_home(self):
        self._stack.setCurrentIndex(0)
        self.update()   # repaint background if it changed

    def _show_about(self):
        self._about.cta.setText("Back")
        self._stack.setCurrentWidget(self._about)

    def _finish_about(self):
        self.sm.set_onboarded(True)
        self._show_home()

    def _accept_consent(self):
        # record the versioned consent, then start the camera and continue.
        self.sm.set_consent(CONSENT_VERSION, datetime.datetime.now().isoformat(timespec="seconds"))
        self._begin_protection()

    # ── Startup flow (loading → consent → about / home) ────────────────────────
    def _enter_app(self):
        if self._ready:
            return
        # keep the loading screen (and its animation) on screen a short minimum
        elapsed = time.monotonic() - getattr(self, "_loading_since", 0)
        min_show = 1.6
        if elapsed < min_show:
            QTimer.singleShot(int((min_show - elapsed) * 1000), self._enter_app)
            return
        self._ready = True
        self._loading.stop()
        # Mandatory data-protection consent before any use.
        if not self.sm.has_consented():
            self._stack.setCurrentWidget(self._consent)
        elif self.sm.get_onboarded():
            self._show_home()
        else:
            self._stack.setCurrentWidget(self._about)

    def _leave_loading_fallback(self):
        if not self._ready:
            self._loading.set_message("Camera is taking a while…")
            self._enter_app()

    # ── Settings ──────────────────────────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self.sm, self)
        if dlg.exec():
            self.timeout_seconds = self.sm.get_timeout()
            self.countdown       = self.timeout_seconds
            if self._cam.camera_index != self.sm.get_camera_index():
                self._cam.stop()
                self._cam = CameraManager(self.sm.get_camera_index())
                self._cam.face_detected.connect(self._on_face)
                self._cam.camera_error.connect(self._on_cam_error)
                self._cam.start()

    # ── State machine ─────────────────────────────────────────────────────────
    def _set_state(self, s: str):
        self.state = s
        h = self._home
        if s != "ABSENT":
            h.hide_countdown()
        if s == "PRESENT":
            h.set_status("", "", "",
                         title_color=TEXT, sub_color=MUTED, footer_color=GREEN,
                         orb_color=GREEN, orb_spin=False)
            h.hide_countdown()
            self._timer.stop()
        elif s == "ABSENT":
            self.countdown = self.timeout_seconds
            h.set_status("STILL THERE?", "", "",
                         title_color=AMBER, sub_color=MUTED, footer_color=AMBER,
                         orb_color=AMBER, orb_spin=True)
            h.show_countdown(self.countdown)
            self._timer.start(1000)
        elif s == "LOCKING":
            h.set_status("LOCKING", "Securing your session", "Locking…",
                         title_color=RED, sub_color=MUTED, footer_color=RED,
                         orb_color=RED, orb_spin=True)
            self._timer.stop()
            if SystemLocker.lock():
                self.state = "LOCKED"
            else:
                # No lock mechanism available (common on minimal Linux setups)
                self.state = "LOCK_FAILED"
                h.set_status("LOCK UNAVAILABLE", "No screen locker found",
                             "Install a locker (e.g. loginctl / xdg-screensaver)",
                             title_color=AMBER, sub_color=MUTED, footer_color=AMBER,
                             orb_color=AMBER, orb_spin=False)
        elif s == "LOCKED":
            h.set_status("LOCKED", "Awaiting your return", "Locked",
                         title_color=TEXT, sub_color=BLUE_MID, footer_color=SLATE,
                         orb_color=SLATE, orb_spin=False)
        elif s == "ERROR":
            h.set_status("NO CAMERA", "Protection paused", "Camera error",
                         title_color=SLATE, sub_color=FAINT, footer_color=SLATE,
                         orb_color=SLATE, orb_spin=False)
        elif s == "PAUSED":
            h.set_status("PAUSED", "Protection suspended", "Paused",
                         title_color=SLATE, sub_color=BLUE_MID, footer_color=SLATE,
                         orb_color=SLATE, orb_spin=False)

    def _on_face(self, present: bool):
        if not self._ready:          # camera works → leave the loading screen
            self._enter_app()
        if self.state in ("ERROR", "PAUSED"):
            return
        if present and self.state != "PRESENT":
            self._set_state("PRESENT")
        elif not present and self.state in ("PRESENT", "INITIALIZING"):
            self._set_state("ABSENT")

    def _tick(self):
        if self.state == "ABSENT":
            self.countdown -= 1
            if self.countdown <= 0:
                self._set_state("LOCKING")
            else:
                self._home.show_countdown(self.countdown)

    def _on_cam_error(self):
        if not self._ready:
            self._enter_app()
        self._set_state("ERROR")
        self._cam.paused = True
        self._pause_action.setText("Resume protection")

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _setup_tray(self):
        icon = _app_icon()
        if icon.isNull():
            pm = QPixmap(16, 16); pm.fill(QColor(BG))
            p = QPainter(pm); p.setPen(QPen(QColor(BLUE), 2))
            p.drawEllipse(2, 2, 12, 12); p.drawPoint(8, 8); p.end()
            icon = QIcon(pm)

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("BLOQZ — Protection active")

        menu = QMenu()
        menu.addAction("Show BLOQZ").triggered.connect(self.showNormal)
        menu.addSeparator()
        self._pause_action = menu.addAction("Pause protection")
        self._pause_action.triggered.connect(self._toggle_pause)
        menu.addAction("Settings").triggered.connect(self._open_settings)
        menu.addAction("About BLOQZ").triggered.connect(
            lambda: (self.showNormal(), self._show_about()))
        menu.addAction("Lock now").triggered.connect(SystemLocker.lock)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(self._quit)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _toggle_pause(self):
        if self._cam is None:      # protection not started yet (awaiting consent)
            return
        if self._cam.paused:
            self._cam.paused = False
            self._pause_action.setText("Pause protection")
            self._set_state("PRESENT") if self.state == "PAUSED" else None
        else:
            self._cam.paused = True
            self._pause_action.setText("Resume protection")
            self._set_state("PAUSED")

    # ── Misc ──────────────────────────────────────────────────────────────────
    def _quit(self):
        if self._cam is not None:
            self._cam.stop()
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.showMessage("BLOQZ", "Running in background", QSystemTrayIcon.Information, 2000)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Make Windows show BLOQZ's own taskbar icon instead of python.exe's.
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BLOQZ.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(_app_icon())
    ui_font = QFont("Segoe UI")
    ui_font.setPointSize(10)
    app.setFont(ui_font)
    app.setStyleSheet(f"""
        QMenu {{
            background:{BG}; color:{MUTED};
            border:1px solid {BORDER}; border-radius:8px; padding:4px;
        }}
        QMenu::item {{ padding:6px 18px; border-radius:6px; }}
        QMenu::item:selected {{ background:{BLUE_DIM}; color:{TEXT}; }}
        QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 8px; }}
        QDialog {{ background:{BG}; color:{TEXT}; }}
        QToolTip {{ background:{SURFACE}; color:{TEXT}; border:1px solid {BORDER};
                    border-radius:6px; padding:4px 8px; }}
    """)
    win = MainWindow()

    # Splash first, then reveal the main window (which opens on its loading screen).
    splash = SplashScreen()

    def _launch():
        win.show()

    splash.finished.connect(_launch)
    splash.start()

    sys.exit(app.exec())
