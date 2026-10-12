"""Test doubles shared by several test modules."""


class FakeMap:
    def __init__(self):
        self.layers, self.controls, self.zoomed = [], [], None
        self.dc = object()

    def add_layer(self, layer, hover=False, key=""):
        layer.key = key
        self.layers = [lyr for lyr in self.layers if getattr(lyr, "key", None) != key] + [layer]

    def find_layer(self, key, base=False, none_ok=False):
        return next((lyr for lyr in self.layers if getattr(lyr, "key", None) == key), None)

    def remove_layer(self, key, base=False, none_ok=False):
        self.layers = [lyr for lyr in self.layers if lyr is not key]

    def zoom_bounds(self, bounds, zoom_out=1):
        self.zoomed = bounds

    def add_control(self, c):
        self.controls.append(c)

    def remove_control(self, c):
        self.controls.remove(c)
