"""Pinned explicit PCHIP integration for rate-distortion comparisons."""
import hashlib
import math

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_y4m(path):
    """Reject unsupported formats and truncated frames instead of guessing."""
    with open(path, "rb") as f:
        header = f.readline()
        if not header.startswith(b"YUV4MPEG2 "):
            raise ValueError("Input must be Y4M")
        tags = {t[:1].decode(): t[1:].decode() for t in header.split()[1:]}
        width, height = int(tags["W"]), int(tags["H"])
        if width % 2 or height % 2 or tags.get("C", "420jpeg") not in ("420", "420jpeg", "420mpeg2", "420paldv"):
            raise ValueError("Only even-sized 8-bit 4:2:0 inputs are supported")
        if tags.get("I", "p") != "p":
            raise ValueError("Only progressive inputs are supported")
        fps_n, fps_d = map(int, tags["F"].split(":"))
        if fps_n <= 0 or fps_d <= 0:
            raise ValueError("Invalid frame rate")
        size = width * height * 3 // 2
        count = 0
        while True:
            marker = f.readline()
            if not marker:
                break
            if not (marker == b"FRAME\n" or marker.startswith(b"FRAME ")) or not marker.endswith(b"\n"):
                raise ValueError("Invalid frame marker")
            if len(f.read(size)) != size:
                raise ValueError("Truncated Y4M frame")
            count += 1
    if count < 1:
        raise ValueError("Empty input")
    return dict(width=width, height=height, frames=count, fps_n=fps_n, fps_d=fps_d, frame_bytes=size)


def pchip_integral(x, y, lo, hi):
    """Exact integral of shape-preserving cubic Hermite interpolation."""
    n = len(x)
    h = [x[i+1] - x[i] for i in range(n-1)]
    d = [(y[i+1] - y[i]) / h[i] for i in range(n-1)]
    m = [0.0] * n
    for i in range(1, n-1):
        if d[i-1] * d[i] > 0:
            w1, w2 = 2*h[i] + h[i-1], h[i] + 2*h[i-1]
            m[i] = (w1 + w2) / (w1/d[i-1] + w2/d[i])
    for k, h0, h1, d0, d1 in ((0, h[0], h[1], d[0], d[1]), (n-1, h[-1], h[-2], d[-1], d[-2])):
        v = ((2*h0+h1)*d0 - h0*d1) / (h0+h1)
        if v*d0 <= 0:
            v = 0.0
        elif d0*d1 < 0 and abs(v) > abs(3*d0):
            v = 3*d0
        m[k] = v
    area = 0.0
    for i in range(n-1):
        a, b = max(lo, x[i]), min(hi, x[i+1])
        if b <= a:
            continue
        c0, c1 = y[i], h[i]*m[i]
        c2 = 3*(y[i+1]-y[i]) - h[i]*(2*m[i]+m[i+1])
        c3 = 2*(y[i]-y[i+1]) + h[i]*(m[i]+m[i+1])
        def primitive(t):
            return c0*t + c1*t*t/2 + c2*t**3/3 + c3*t**4/4
        area += h[i]*(primitive((b-x[i])/h[i])-primitive((a-x[i])/h[i]))
    return area


def bd_rate(reference, candidate):
    """Points are (quality, bitrate). Reject extrapolation and nonmonotonicity."""
    curves = []
    for points in (reference, candidate):
        if len(points) < 4 or any(q is None or not math.isfinite(q) or r <= 0 for q, r in points):
            return {"percent": None, "reason": "requires >=4 finite operating points"}
        points = sorted(points)
        if any(points[i+1][0] <= points[i][0] or points[i+1][1] <= points[i][1] for i in range(len(points)-1)):
            return {"percent": None, "reason": "nonmonotonic or duplicate rate/quality points"}
        curves.append(([p[0] for p in points], [math.log(p[1]) for p in points]))
    lo, hi = max(c[0][0] for c in curves), min(c[0][-1] for c in curves)
    if hi <= lo:
        return {"percent": None, "reason": "no quality overlap"}
    area = [pchip_integral(x, y, lo, hi) for x, y in curves]
    return {"percent": 100*math.expm1((area[1]-area[0])/(hi-lo)), "quality_overlap": [lo, hi],
            "overlap_fraction": [(hi-lo)/(x[-1]-x[0]) for x, _ in curves]}
