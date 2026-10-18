"""Kid-facing copies of math question pictures.

Screenshots taken from the contest website start with a blue title line such as
"2023 AMC 10A Problem 1" plus a light-blue underline. In practice mode a kid could
look the answer up from that line, so a copy without it is made and shown to the kid
instead of the original. The original file is never changed.
"""
import os
import secrets
import time

from PIL import Image


def title_header_height(im):
    """Pixel height of a blue title + underline at the top of the picture, or None if there is none."""
    im = im.convert("RGB")
    w, h = im.size
    if h < 90 or w < 300:
        return None
    px = im.load()
    top = min(h, 140)
    rows = []  # (non-white pixels, blue pixels) per row, sampling every other column
    for y in range(top):
        nw = bl = 0
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if min(r, g, b) < 235:
                nw += 1
                if b - r > 25:
                    bl += 1
        rows.append((nw, bl))

    first = next((y for y, (nw, _) in enumerate(rows) if nw), None)
    if first is None or first > 60:
        return None
    end = first
    while end < top and rows[end][0]:
        end += 1
    band = rows[first:end]
    # The title is one line of (almost only) blue text
    if not 12 <= end - first <= 45 or sum(b for _, b in band) < 0.85 * sum(n for n, _ in band):
        return None

    # Underline: a light-blue row spanning most of the width, shortly below the title
    wide = 0.6 * (w // 2)
    for y in range(end, min(top, end + 25)):
        nw, bl = rows[y]
        if bl > wide:
            while y + 1 < top and rows[y + 1][1] > wide:
                y += 1
            return y + 1
        if nw and bl < nw * 0.85:
            return None
    return None


def make_kid_image(upload_folder, image_path, question_id):
    """Save a copy of the picture without its title line; returns the new file name, or None if there is no title."""
    src = os.path.join(upload_folder, image_path)
    with Image.open(src) as im:
        cut = title_header_height(im)
        if not cut:
            return None
        ext = image_path.rsplit(".", 1)[-1].lower()
        filename = f"mathq_{question_id}_k_{int(time.time())}_{secrets.token_hex(6)}.{ext}"
        cropped = im.crop((0, cut, im.width, im.height))
        if ext in ("jpg", "jpeg") and cropped.mode not in ("RGB", "L"):
            cropped = cropped.convert("RGB")
        cropped.save(os.path.join(upload_folder, filename))
    return filename
