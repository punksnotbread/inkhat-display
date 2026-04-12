#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
from inky.auto import auto

TEXT = "389 €"

display = auto()
W, H = display.WIDTH, display.HEIGHT

img = Image.new("P", (W, H))
img.putpalette([255, 255, 255, 0, 0, 0, 255, 0, 0] + [0] * (256 - 3) * 3)
draw = ImageDraw.Draw(img)
draw.rectangle([0, 0, W, H], fill=display.WHITE)

font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
bbox = draw.textbbox((0, 0), TEXT, font=font)
x = (W - (bbox[2] - bbox[0])) // 2
y = (H - (bbox[3] - bbox[1])) // 2
draw.text((x, y), TEXT, display.BLACK, font=font)

display.set_image(img)
display.show()
