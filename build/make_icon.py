"""build/mcp_orange.ico 를 만든다 (Pillow 없이 표준 라이브러리만 사용).

    python build\\make_icon.py          -> build\\mcp_orange.ico  (+ build\\icon_preview.png)
디자인: 주황 둥근 사각형 위에 흰색 워크플로 — 입력이 두 갈래로 나뉘었다 다시 합쳐지는 모양(Orange 캔버스 + MCP 연결).
결과 .ico 는 저장소에 커밋해 두므로, 디자인을 바꿀 때만 다시 실행한다.
"""
import math
import struct
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
TOP, BOTTOM = (255, 152, 40), (230, 100, 0)          # 배경 세로 그라데이션
NODES = ((0.22, 0.50), (0.50, 0.27), (0.50, 0.73), (0.78, 0.50))   # 입력 -> 두 갈래 처리 -> 결과
LINKS = ((0, 1), (0, 2), (1, 3), (2, 3))
NODE_R, LINK_W, CORNER, MARGIN = 0.105, 0.05, 0.22, 0.03


def _seg_dist(px, py, a, b):
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _in_round_rect(x, y):
    lo, hi, r = MARGIN, 1 - MARGIN, CORNER
    if not (lo <= x <= hi and lo <= y <= hi):
        return False
    cx = min(max(x, lo + r), hi - r)
    cy = min(max(y, lo + r), hi - r)
    return math.hypot(x - cx, y - cy) <= r


def _is_white(x, y):
    if any(math.hypot(x - nx, y - ny) <= NODE_R for nx, ny in NODES):
        return True
    return any(_seg_dist(x, y, NODES[a], NODES[b]) <= LINK_W / 2 for a, b in LINKS)


def render(size):
    ss = 4 if size <= 64 else 3
    rows = []
    for j in range(size):
        row = bytearray()
        for i in range(size):
            cov = white = 0
            for sj in range(ss):
                for si in range(ss):
                    x, y = (i + (si + .5) / ss) / size, (j + (sj + .5) / ss) / size
                    if _in_round_rect(x, y):
                        cov += 1
                        white += _is_white(x, y)
            if not cov:
                row += b"\0\0\0\0"
                continue
            t = (j + .5) / size
            bg = [TOP[k] + (BOTTOM[k] - TOP[k]) * t for k in range(3)]
            w = white / cov
            row += bytes(int(bg[k] * (1 - w) + 255 * w) for k in range(3))
            row += bytes([round(255 * cov / (ss * ss))])
        rows.append(bytes(row))
    return rows


def png(size, rows):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    out = Path(__file__).resolve().parent
    frames = [(s, png(s, render(s))) for s in SIZES]
    head = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b"", b""
    for s, data in frames:
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    (out / "mcp_orange.ico").write_bytes(head + entries + blobs)
    (out / "icon_preview.png").write_bytes(frames[-1][1])
    print("wrote mcp_orange.ico (%d bytes, sizes %s)" % (len(head + entries + blobs), SIZES))


if __name__ == "__main__":
    main()
