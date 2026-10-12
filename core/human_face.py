"""
Two natural human faces for the HUD centre — Aria and Kael.

They subclass :class:`core.avatar.HoloAvatar` and reuse its entire animation
brain — viseme lip-sync, blinking, gaze saccades, brow acting, sleep lids,
deliberate glances — overriding only the paint. A human face therefore
behaves exactly like the hologram: same timing, same mouth, same eyes that
look away while thinking and meet you while listening. Only the skin differs.

Software rendered like everything else in the HUD (QPainter, no GPU, no new
dependency). The look is shaded 2D naturalism: skin-tone radial modelling,
detailed eyes with real pupils that follow the gaze state, hair, and a mouth
with teeth and tongue driven by the same jaw value as the hologram.

Variants
    aria — feminine presenting: softer jaw, long dark hair, brown eyes.
    kael — masculine presenting: stronger jaw, short crop, hazel eyes.

Lifecycle matches HoloAvatar exactly::

    face = HumanFace("aria")
    face.step(dt, amp, speaking=..., muted=..., state=...)
    face.paint(painter, cx, cy, r, primary, accent, bg)
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QRadialGradient

from core.avatar import HoloAvatar, _blend, _c

# Crown of the hair to the bottom of the shoulders, in head-half-heights.
# Callers fit the figure to the room with this, exactly like HoloAvatar.SPAN.
SPAN = 2.5


def _skin(base: QColor, shadow: QColor, cx: float, cy: float, rad: float) -> QBrush:
    """Soft modelling light: warm centre high on the left, falloff to shadow."""
    g = QRadialGradient(cx - rad * 0.28, cy - rad * 0.34, rad * 1.55)
    light = QColor(
        min(255, base.red() + 26), min(255, base.green() + 22),
        min(255, base.blue() + 18))
    g.setColorAt(0.00, light)
    g.setColorAt(0.55, base)
    g.setColorAt(1.00, shadow)
    return QBrush(g)


class HumanFace(HoloAvatar):
    """A natural human HUD face. Drop-in sibling of HoloAvatar."""

    VARIANTS = ("aria", "kael")

    _SKIN = {
        "aria": (QColor("#eabd92"), QColor("#c78f60")),
        "kael": (QColor("#c68e5c"), QColor("#946038")),
    }
    _HAIR = {"aria": QColor("#2c1a10"), "kael": QColor("#161009")}
    _IRIS = {"aria": QColor("#5a3a22"), "kael": QColor("#4d5e33")}
    _LIP = {"aria": QColor("#b05a58"), "kael": QColor("#96504e")}
    _BLUSH = {"aria": QColor("#d9707e"), "kael": QColor("#a85a4a")}
    _JAW_W = {"aria": 0.585, "kael": 0.645}   # face half-width, in r

    def __init__(self, variant: str = "aria") -> None:
        super().__init__()
        self.variant = variant if variant in self.VARIANTS else "aria"
        self.SPAN = SPAN

    # ── small paint helpers ──────────────────────────────────────────────

    @staticmethod
    def _ellipse(p: QPainter, cx: float, cy: float, rx: float, ry: float,
                 brush: QBrush) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(brush)
        p.drawEllipse(QRectF(cx - rx, cy - ry, rx * 2.0, ry * 2.0))

    def paint(self, p: QPainter, cx: float, cy: float, r: float,
              primary: QColor, accent: QColor, bg: QColor | None = None) -> None:
        """Draw the face with its centre at (cx, cy); `r` = half-height in px."""
        if bg is None:
            bg = QColor(0, 0, 0)
        v = self.variant
        skin_b, skin_s = self._SKIN[v]
        hair = self._HAIR[v]
        jaw_w = self._JAW_W[v]
        amp = self._glow

        # 2D parallax from the same head-pose state the hologram integrates.
        dx = self._yaw * 0.10 * r
        dy = self._pitch * 0.09 * r + self._emph * 0.022 * r
        jaw_drop = self._mouth * 0.13 * r
        fx, fy = cx + dx, cy + dy

        # ── faint aura: the one HUD thread tying the faces together ──────
        # (muted already arrives tinted: the caller passes the muted colour
        # as primary, so the rim and aura follow without a special case)
        ar = r * 1.7
        aura = QRadialGradient(fx, fy, ar)
        aura.setColorAt(0.00, _c(primary, 13 + 30 * amp))
        aura.setColorAt(0.55, _c(primary, 7 + 16 * amp))
        aura.setColorAt(1.00, _c(primary, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(aura))
        p.drawEllipse(QRectF(fx - ar, fy - ar, ar * 2, ar * 2))

        dark = QColor("#141a26")          # clothing
        dark_edge = _blend(bg, primary, 40)

        # ── back hair ────────────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hair))
        if v == "aria":
            # long fall past the shoulders
            back = QPainterPath()
            back.moveTo(fx - 0.86 * r, fy + 1.30 * r)
            back.cubicTo(fx - 0.95 * r, fy + 0.30 * r,
                         fx - 0.92 * r, fy - 0.70 * r,
                         fx - 0.42 * r, fy - 1.02 * r)
            back.cubicTo(fx, fy - 1.22 * r,
                         fx + 0.42 * r, fy - 1.02 * r,
                         fx + 0.92 * r, fy - 0.70 * r)
            back.cubicTo(fx + 0.95 * r, fy + 0.30 * r,
                         fx + 0.86 * r, fy + 1.30 * r,
                         fx + 0.30 * r, fy + 1.32 * r)
            back.lineTo(fx - 0.30 * r, fy + 1.32 * r)
            back.closeSubpath()
            p.drawPath(back)
        else:
            # short crop: a cap over the crown
            cap = QPainterPath()
            cap.moveTo(fx - 0.70 * r, fy - 0.30 * r)
            cap.cubicTo(fx - 0.72 * r, fy - 0.95 * r,
                         fx - 0.30 * r, fy - 1.12 * r,
                         fx, fy - 1.12 * r)
            cap.cubicTo(fx + 0.30 * r, fy - 1.12 * r,
                         fx + 0.72 * r, fy - 0.95 * r,
                         fx + 0.70 * r, fy - 0.30 * r)
            cap.cubicTo(fx + 0.55 * r, fy - 0.62 * r,
                         fx - 0.55 * r, fy - 0.62 * r,
                         fx - 0.70 * r, fy - 0.30 * r)
            cap.closeSubpath()
            p.drawPath(cap)

        # ── neck + shoulders ─────────────────────────────────────────────
        neck = QPainterPath()
        neck.moveTo(fx - 0.21 * r, fy + 0.62 * r)
        neck.lineTo(fx - 0.30 * r, fy + 1.10 * r)
        neck.lineTo(fx + 0.30 * r, fy + 1.10 * r)
        neck.lineTo(fx + 0.21 * r, fy + 0.62 * r)
        neck.closeSubpath()
        p.setBrush(QBrush(skin_s))
        p.drawPath(neck)
        # chin shadow falling on the throat
        self._ellipse(p, fx, fy + 0.72 * r, 0.20 * r, 0.10 * r,
                      QBrush(_c(skin_s.darker(115), 110)))

        shoulders = QPainterPath()
        shoulders.moveTo(fx - 0.95 * r, fy + 1.38 * r)
        shoulders.cubicTo(fx - 0.90 * r, fy + 1.02 * r,
                           fx - 0.45 * r, fy + 0.98 * r,
                           fx - 0.28 * r, fy + 1.02 * r)
        shoulders.lineTo(fx + 0.28 * r, fy + 1.02 * r)
        shoulders.cubicTo(fx + 0.45 * r, fy + 0.98 * r,
                           fx + 0.90 * r, fy + 1.02 * r,
                           fx + 0.95 * r, fy + 1.38 * r)
        shoulders.closeSubpath()
        p.setBrush(QBrush(dark))
        p.drawPath(shoulders)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(dark_edge, 1.2))
        p.drawPath(shoulders)

        # ── ears ─────────────────────────────────────────────────────────
        for s in (-1.0, 1.0):
            self._ellipse(p, fx + s * jaw_w * r, fy + 0.06 * r,
                          0.085 * r, 0.125 * r, QBrush(skin_b))

        # ── face base ────────────────────────────────────────────────────
        face_rx, face_ry = jaw_w * r, 0.92 * r
        self._ellipse(p, fx, fy, face_rx, face_ry,
                      _skin(skin_b, skin_s, fx, fy, face_rx))

        # soft modelling shadows: temples, jaw edge, chin
        sh = QColor(skin_s.darker(112))
        self._ellipse(p, fx - face_rx * 0.82, fy - 0.30 * r,
                      0.16 * r, 0.30 * r, QBrush(_c(sh, 70)))
        self._ellipse(p, fx + face_rx * 0.82, fy + 0.18 * r,
                      0.15 * r, 0.28 * r, QBrush(_c(sh, 60)))
        self._ellipse(p, fx, fy + face_ry * 0.86, 0.22 * r, 0.10 * r,
                      QBrush(_c(sh, 55)))

        # kael: stronger jaw + faint beard shadow around it
        if v == "kael":
            beard = QPainterPath()
            beard.moveTo(fx - face_rx * 0.92, fy + 0.18 * r)
            beard.quadTo(fx, fy + face_ry * 1.06, fx + face_rx * 0.92, fy + 0.18 * r)
            beard.quadTo(fx, fy + 0.55 * r, fx - face_rx * 0.92, fy + 0.18 * r)
            beard.closeSubpath()
            p.setBrush(QBrush(_c(QColor("#3a2c22"), 46)))
            p.drawPath(beard)

        # blush high on the cheeks, breathing a little with speech
        bl = self._BLUSH[v]
        self._ellipse(p, fx - face_rx * 0.52, fy + 0.22 * r,
                      0.13 * r, 0.085 * r, QBrush(_c(bl, 34 + 26 * amp)))
        self._ellipse(p, fx + face_rx * 0.52, fy + 0.22 * r,
                      0.13 * r, 0.085 * r, QBrush(_c(bl, 34 + 26 * amp)))

        # ── nose ─────────────────────────────────────────────────────────
        nose_hl = QColor(min(255, skin_b.red() + 30),
                         min(255, skin_b.green() + 26),
                         min(255, skin_b.blue() + 22))
        p.setPen(QPen(_c(nose_hl, 90), max(1.0, 0.022 * r)))
        p.drawLine(QPointF(fx + dx * 0.35, fy - 0.10 * r),
                   QPointF(fx + dx * 0.55, fy + 0.24 * r))
        nostril = QColor(skin_s.darker(150))
        for s in (-1.0, 1.0):
            p.setPen(QPen(_c(nostril, 150), max(1.2, 0.026 * r)))
            p.drawArc(QRectF(fx + s * 0.048 * r - 0.020 * r, fy + 0.255 * r,
                             0.040 * r, 0.028 * r),
                      200 * 16, 140 * 16)

        # ── eyes ─────────────────────────────────────────────────────────
        lid_open = max(0.03, (1.0 - self._blink) * (0.12 + 0.88 * self._lids))
        iris_c = self._IRIS[v]
        for s in (-1.0, 1.0):
            ex = fx + s * 0.228 * r + dx * 0.25
            ey = fy - 0.155 * r
            erw, erh = 0.118 * r, 0.070 * r * lid_open + 0.004 * r

            # socket shading + sclera
            self._ellipse(p, ex, ey, erw + 0.012 * r, erh + 0.014 * r,
                          QBrush(_c(skin_s.darker(108), 90)))
            self._ellipse(p, ex, ey, erw, erh, QBrush(QColor("#f1ece3")))

            if lid_open > 0.18:
                gx = ex + self._gaze[0] * erw * 0.34
                gy = ey + self._gaze[1] * erh * 0.38
                ir = min(erh * 0.95, erw * 0.46)
                ig = QRadialGradient(gx, gy, ir)
                ig.setColorAt(0.0, iris_c.lighter(135))
                ig.setColorAt(0.62, iris_c)
                ig.setColorAt(1.0, iris_c.darker(170))
                self._ellipse(p, gx, gy, ir, ir, QBrush(ig))
                self._ellipse(p, gx, gy, ir * 0.46, ir * 0.46,
                              QBrush(QColor("#0d0a08")))
                self._ellipse(p, gx - ir * 0.30, gy - ir * 0.34,
                              ir * 0.20, ir * 0.20, QBrush(QColor(255, 255, 255, 235)))

            # upper lid fold + lash line riding the lid edge
            lid_y = ey - erh
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(skin_b))
            p.drawRect(QRectF(ex - erw - 0.014 * r, ey - erh - 0.05 * r,
                              (erw + 0.014 * r) * 2, 0.05 * r))
            p.setBrush(Qt.BrushStyle.NoBrush)
            lash = hair.lighter(140) if v == "kael" else hair
            p.setPen(QPen(lash, 2.0 if v == "aria" else 2.6))
            arc = QPainterPath()
            arc.moveTo(ex - erw, lid_y + 0.004 * r)
            arc.quadTo(ex, lid_y - 0.022 * r, ex + erw, lid_y + 0.004 * r)
            p.drawPath(arc)
            if v == "aria":
                # outer-corner flicks
                p.setPen(QPen(lash, 1.4))
                tip = ex + s * erw
                p.drawLine(QPointF(tip, lid_y + 0.004 * r),
                           QPointF(tip + s * 0.035 * r, lid_y - 0.012 * r))
            # lower lid whisper
            p.setPen(QPen(_c(skin_s.darker(120), 120), 1.1))
            p.drawArc(QRectF(ex - erw * 0.9, ey - erh * 0.4,
                             erw * 1.8, erh * 1.5), 200 * 16, 140 * 16)

        # ── brows ────────────────────────────────────────────────────────
        brow_lift = self._brow * 0.055 * r
        for s in (-1.0, 1.0):
            bx = fx + s * 0.228 * r + dx * 0.25
            by = fy - 0.305 * r - brow_lift
            bw = 0.135 * r
            path = QPainterPath()
            if v == "aria":
                path.moveTo(bx - bw, by + 0.018 * r)
                path.quadTo(bx, by - 0.026 * r, bx + bw, by + 0.006 * r)
                p.setPen(QPen(hair, 3.2))
            else:
                path.moveTo(bx - bw, by + 0.010 * r)
                path.quadTo(bx, by - 0.012 * r, bx + bw, by + 0.004 * r)
                p.setPen(QPen(hair, 5.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # ── mouth ────────────────────────────────────────────────────────
        self._paint_mouth(p, fx, fy + jaw_drop, r, jaw_w, bg)

        # ── front hair ───────────────────────────────────────────────────
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hair))
        if v == "aria":
            # centre sweep + falls framing the cheeks
            sweep = QPainterPath()
            sweep.moveTo(fx - face_rx * 0.98, fy - 0.30 * r)
            sweep.cubicTo(fx - face_rx * 1.02, fy - 0.85 * r,
                           fx - 0.30 * r, fy - 1.06 * r,
                           fx + 0.05 * r, fy - 1.02 * r)
            sweep.cubicTo(fx + 0.35 * r, fy - 0.99 * r,
                           fx + 0.62 * r, fy - 0.88 * r,
                           fx + face_rx * 0.99, fy - 0.55 * r)
            sweep.cubicTo(fx + 0.60 * r, fy - 0.72 * r,
                           fx + 0.10 * r, fy - 0.80 * r,
                           fx - 0.30 * r, fy - 0.72 * r)
            sweep.cubicTo(fx - 0.62 * r, fy - 0.66 * r,
                           fx - 0.72 * r, fy - 0.50 * r,
                           fx - face_rx * 0.98, fy - 0.30 * r)
            sweep.closeSubpath()
            p.drawPath(sweep)
            for s in (-1.0, 1.0):
                fall = QPainterPath()
                fall.moveTo(fx + s * face_rx * 0.98, fy - 0.45 * r)
                fall.cubicTo(fx + s * face_rx * 1.06, fy + 0.10 * r,
                              fx + s * 0.72 * r, fy + 0.75 * r,
                              fx + s * 0.62 * r, fy + 1.25 * r)
                fall.lineTo(fx + s * 0.40 * r, fy + 1.25 * r)
                fall.cubicTo(fx + s * 0.50 * r, fy + 0.70 * r,
                              fx + s * face_rx * 0.80, fy + 0.05 * r,
                              fx + s * face_rx * 0.72, fy - 0.48 * r)
                fall.closeSubpath()
                p.drawPath(fall)
        else:
            # textured crop: scalloped hairline
            p.setBrush(QBrush(hair))
            for i in range(9):
                t = -0.62 + i * 0.155
                self._ellipse(p, fx + t * r, fy - 0.86 * r + 0.05 * r * math.cos(i * 1.3),
                              0.105 * r, 0.16 * r, QBrush(hair))

        # ── rim light: the theme still touches the face ──────────────────
        rim_a = 26 + 60 * amp
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_c(primary, rim_a), max(1.2, 0.020 * r)))
        p.drawArc(QRectF(fx - face_rx, fy - face_ry, face_rx * 2, face_ry * 2),
                  70 * 16, 140 * 16)

    # ── mouth ────────────────────────────────────────────────────────────

    def _paint_mouth(self, p: QPainter, fx: float, fy: float, r: float,
                     jaw_w: float, bg: QColor) -> None:
        """Lips, teeth and tongue from the shared jaw value.

        `fy` already carries the jaw drop. `wide` spreads (/i/) or rounds
        (/u/) the lips; openness comes from `self._mouth` alone.
        """
        v = self.variant
        lip = self._LIP[v]
        lip_dark = lip.darker(150)
        my = fy + 0.44 * r
        wide = max(-1.0, min(1.0, self._wide))
        w = 0.30 * r * (1.0 + (0.26 * wide if wide > 0 else 0.14 * wide))
        w = max(0.13 * r, w)

        if self._mouth <= 0.02:
            # resting lips: one calm line with a hint of the lower lip
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(lip_dark, max(1.4, 0.024 * r)))
            line = QPainterPath()
            line.moveTo(fx - w, my)
            line.quadTo(fx, my + 0.028 * r + abs(wide) * 0.012 * r, fx + w, my)
            p.drawPath(line)
            self._ellipse(p, fx, my + 0.045 * r, w * 0.62, 0.028 * r,
                          QBrush(_c(lip, 70)))
            return

        h = max(0.05 * r, self._mouth * 0.34 * r)
        # cupid's bow dip on the upper edge
        upper = QPainterPath()
        upper.moveTo(fx - w, my - h * 0.28)
        upper.quadTo(fx - w * 0.35, my - h * 0.52, fx, my - h * 0.34)
        upper.quadTo(fx + w * 0.35, my - h * 0.52, fx + w, my - h * 0.28)
        upper.quadTo(fx, my + h * 0.10, fx - w, my - h * 0.28)
        upper.closeSubpath()
        # fuller lower lip
        lower = QPainterPath()
        lower.moveTo(fx - w, my - h * 0.28)
        lower.quadTo(fx, my + h * 1.02, fx + w, my - h * 0.28)
        lower.quadTo(fx, my + h * 0.10, fx - w, my - h * 0.28)
        lower.closeSubpath()

        # cavity: dark but warm, never a black hole
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#3d1613")))
        cav = QPainterPath()
        cav.moveTo(fx - w * 0.92, my - h * 0.22)
        cav.quadTo(fx, my + h * 0.86, fx + w * 0.92, my - h * 0.22)
        cav.quadTo(fx, my - h * 0.05, fx - w * 0.92, my - h * 0.22)
        cav.closeSubpath()
        p.drawPath(cav)

        # tongue rising with openness
        self._ellipse(p, fx, my + h * (0.52 - 0.18 * self._mouth),
                      w * 0.58, h * 0.30, QBrush(QColor("#a05252")))

        # upper teeth strip
        th = h * 0.34
        teeth = QPainterPath()
        teeth.moveTo(fx - w * 0.80, my - h * 0.30)
        teeth.lineTo(fx + w * 0.80, my - h * 0.30)
        teeth.lineTo(fx + w * 0.72, my - h * 0.30 + th)
        teeth.quadTo(fx, my - h * 0.30 + th + h * 0.08,
                     fx - w * 0.72, my - h * 0.30 + th)
        teeth.closeSubpath()
        p.setBrush(QBrush(QColor("#ece5d8")))
        p.drawPath(teeth)

        # lip edges over everything
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(lip, max(1.6, 0.028 * r)))
        p.drawPath(upper)
        p.drawPath(lower)
