from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 圆角底
r = 110
bg = (18, 27, 43, 255)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=bg)

# 屏幕
sx0, sy0, sx1, sy1 = 78, 96, S - 78, 340
d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=26, fill=(255, 255, 255, 255))
d.rounded_rectangle([sx0 + 14, sy0 + 14, sx1 - 14, sy1 - 14], radius=16, fill=(38, 118, 255, 255))
# 屏幕渐变
grad = Image.new("RGBA", (sx1 - sx0 - 28, sy1 - sy0 - 28))
gd = ImageDraw.Draw(grad)
for y in range(grad.height):
    t = y / max(1, grad.height - 1)
    c = (int(45 + 20 * t), int(120 + 40 * t), int(255 - 40 * t), 255)
    gd.line([(0, y), (grad.width, y)], fill=c)
mask = Image.new("L", grad.size, 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, grad.width - 1, grad.height - 1], radius=16, fill=255)
img.paste(grad, (sx0 + 14, sy0 + 14), mask)

# 支架
d.rounded_rectangle([S // 2 - 34, 336, S // 2 + 34, 372], radius=8, fill=(255, 255, 255, 255))
d.rounded_rectangle([S // 2 - 96, 370, S // 2 + 96, 396], radius=14, fill=(255, 255, 255, 255))

# 屏幕里的箭头（控件感）
pts = [(206, 150), (206, 268), (240, 234), (262, 282), (286, 271), (264, 224), (312, 224)]
d.polygon(pts, fill=(255, 255, 255, 255))

# 在线小绿点
d.ellipse([S - 150, S - 160, S - 86, S - 96], fill=(30, 200, 110, 255))

img.save(r"C:\Users\Administrator\Doubao\chats\2026-11-06\new-chat-1\macremote\app.ico",
         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
img.resize((256, 256), Image.LANCZOS).save(r"C:\Users\Administrator\Doubao\chats\2026-11-06\new-chat-1\macremote\app_preview.png")
print("icon ok")
