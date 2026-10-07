"""Offline photo geometry estimates. No recognition of bodies or people.

Line/curve support is measured on image contours. Broad closed shapes are a 2-D
proxy for large masses, not a measurement of the building's physical volume.
Ambiguous and low-detail images remain unclassified. Review can override this.
"""
from PIL import Image, ImageOps
import numpy as np

METHOD = 'photo-geometry-v1'


def analyze_geometry(image):
    import cv2  # offline dependency; never imported in the Vercel API
    image = ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((640, 640))
    rgb = np.asarray(image)
    h, w = rgb.shape[:2]
    if min(h, w) < 64:
        return {}
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 120)
    # Ignore the image frame. Do not mistake it for architectural lines.
    edges[:3] = edges[-3:] = 0
    edges[:, :3] = edges[:, -3:] = 0
    edge_count = int(np.count_nonzero(edges))
    if edge_count < .002 * h * w or float(gray.std()) < 8:
        return {}
    line_mask = np.zeros_like(edges)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=35,
                           minLineLength=max(30, min(h, w) * .12), maxLineGap=6)
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            cv2.line(line_mask, (x1, y1), (x2, y2), 255, 4)
    linear = float(np.count_nonzero((line_mask > 0) & (edges > 0)) / edge_count)
    curves = np.zeros_like(edges)
    masses = np.zeros_like(edges)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter < min(h, w) * .12:
            continue
        area = cv2.contourArea(contour)
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        x, y, cw, ch = cv2.boundingRect(contour)
        polygon = cv2.approxPolyDP(contour, .012 * perimeter, True)
        if len(polygon) >= 7 and area > 100 and hull_area and area / hull_area > .65:
            cv2.drawContours(curves, [contour], -1, 255, 4)
        # Large closed forms, away from the frame; exclude sky/floor borders.
        if (.06 <= area / (h * w) <= .65 and min(cw / w, ch / h) > .18
                and x > 3 and y > 3 and x + cw < w - 3 and y + ch < h - 3
                and hull_area and area / hull_area > .72):
            cv2.drawContours(masses, [contour], -1, 255, -1)
    curved = float(np.count_nonzero((curves > 0) & (line_mask == 0) & (edges > 0)) / edge_count)
    mass = min(1.0, float(np.count_nonzero(masses) / (h * w)) * 2)
    # A very weak signal is not converted into a confident categorical match.
    signals = {'linear': linear, 'curved': curved, 'volumetric': mass}
    top = 'volumetric' if mass >= .3 else max(signals, key=signals.get)
    if signals[top] < .18:
        return {}
    return {'form': top}
