"""
Phase 1 预览脚本：验证新配色和新字体效果

运行方式：python preview_phase1.py
"""

import sys
sys.path.insert(0, "backend")

from image_generator import CardImageGenerator
from PIL import Image

# ===== 测试数据 =====
test_data = {
    "title": "生活在别处的宁静",
    "quote": "慢下来，是为了更好地出发。在平凡的日子里，遇见不平凡的自己。",
    "source_quote": "世界上只有一种真正的英雄主义，那就是在认清生活的真相后依然热爱生活。——罗曼·罗兰",
    "summary": "停下来，感受风的温度，聆听内心的声音。慢不是停，而是给自己一个拥抱。",
    "keywords": "慢生活,治愈,自我,宁静",
    "book": "《瓦尔登湖》",
    "movie": "《海上钢琴师》",
    "style": "healing",
}

# ===== 生成卡片 =====
print("=" * 50)
print("Phase 1 预览：新配色 + 新字体")
print("=" * 50)

generator = CardImageGenerator(width=1080, height=1440)

# 使用一张适合的背景图
from pathlib import Path
bg_dir = Path("assets/backgrounds")
bg_files = list(bg_dir.glob("*.jpg"))
if bg_files:
    bg = Image.open(str(bg_files[0]))
    print(f"使用背景图: {bg_files[0].name}")
    img = generator.generate(test_data, custom_bg=bg)
else:
    print("没有背景图，使用随机背景")
    img = generator.generate(test_data)

# ===== 保存预览图 =====
output = "preview_phase1.png"
img.save(output, quality=95)
print(f"\n✅ 预览图已保存: {output}")
print(f"   尺寸: {img.size}")
print(f"   文件大小: {output}")

# ===== 显示图片 =====
try:
    img.show()
    print("   已打开图片预览")
except Exception:
    print("   请手动打开 preview_phase1.png 查看效果")