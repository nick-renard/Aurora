from lib.AuroraExtension import AuroraExtension
import time


class Renard_FullRainbow(AuroraExtension):
    def __init__(self, NeoPixels, HDMI):
        super().__init__(NeoPixels, HDMI)
        self.Author = "Nick Renard (@nick-renard)"
        self.Description = "This extension displays a unified rainbow effect on all LEDs."
        self.Name = "Unified Rainbow (LED Only)"
        self.noHDMI = True
        self.rainbow_colors = [
            (148, 0, 211),  # Violet
            (75, 0, 130),  # Indigo
            (0, 0, 255),  # Blue
            (0, 255, 0),  # Green
            (255, 255, 0),  # Yellow
            (255, 165, 0),  # Orange
            (255, 0, 0)  # Red
        ]
        self.num_colors = len(self.rainbow_colors)
        self.color_index = 0

    def takeScreenShot(self, filepath):
        # No screenshot since it's just LEDs
        return True

    def update_rainbow(self):
        # Set all LEDs to the current color in the rainbow_colors list
        r, g, b = self.rainbow_colors[self.color_index]
        for i in range(self.pixelsCount):
            self.pixels[i] = (r, g, b)
        self.pixels.show()

        # Move to the next color in the rainbow_colors list
        self.color_index = (self.color_index + 1) % self.num_colors

    def visualise(self):
        # Continuously update the unified rainbow effect
        while True:
            self.update_rainbow()
            time.sleep(0.1)  # Adjust the delay to control the speed of the rainbow effect
