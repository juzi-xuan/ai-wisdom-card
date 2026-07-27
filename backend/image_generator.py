"""
AI 知识卡片 · 图片生成器（v3 完整重构版）
"""

import io
import math
import re
import os
import random
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from loguru import logger


# ========================== 常量配置 ==========================

CARD_WIDTH = 1080
CARD_HEIGHT = 1440

# ---------- 配色体系（三主色） ----------
COLOR_GOLD = "#FFD700"        # 主色1：亮金色（标题、分割线、图标），比原来更亮
COLOR_CREAM = "#FFFFFF"       # 主色2：纯白色（正文），比原来更亮
COLOR_DEEP_PURPLE = "#292747" # 主色3：深紫（卡片背景）

# 背景渐变色
COLOR_GRADIENT_TOP = "#25284A"     # 顶部：深蓝紫
COLOR_GRADIENT_MID = "#62526D"     # 中部：灰紫
COLOR_GRADIENT_BOTTOM = "#8D6570"  # 底部：暗粉紫

COLOR_TEXT_DIM = "#B0B0C8"
COLOR_WHITE = "#FFFFFF"

# ---------- 排版参数 ----------
PADDING_H = 80
PADDING_V = 60
LINE_SPACING_RATIO = 1.6

# ---------- 背景图片 ----------
BACKGROUNDS_DIR = Path(__file__).parent.parent / "assets" / "backgrounds"
ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"
OVERLAY_ALPHA = 160

# ---------- 布局区域高度比例 ----------
ZONE_RATIOS = [0.20, 0.17, 0.18, 0.15, 0.10, 0.15]

# ---------- 关键词图标映射 ----------
TAG_ICON_MAP = {
    "运气": "✨",
    "长期主义": "⏱",
    "因果律": "♻",
    "持续行动": "↗",
    "厚积薄发": "⏳",
    "韧性": "💪",
    "延迟满足": "🎯",
}


# ========================== 字体加载 ==========================

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """加载中文字体，优先宋体（衬线体）"""
    candidates = [
        ("C:/Windows/Fonts/simsun.ttc", 1 if bold else 0),
        ("C:/Windows/Fonts/msyhbd.ttc", 0),
        ("C:/Windows/Fonts/msyh.ttc", 2 if bold else 0),
        ("C:/Windows/Fonts/Dengb.ttf", 0),
        ("C:/Windows/Fonts/simhei.ttf", 0),
    ]

    for font_path, font_index in candidates:
        try:
            return ImageFont.truetype(font_path, size, index=font_index)
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的中文字体, size={size}")
    return ImageFont.load_default()


def _load_random_icon(icon_size: int) -> Optional[Image.Image]:
    """
    随机加载一个图标文件（就像从玩具箱里随机拿一个玩具）

    这个函数的作用：
        去 assets/icons/ 文件夹里找图标文件，
        随机选一个，调整大小后交给调用者。
        如果文件夹不存在或者里面没文件，就返回 None（告诉调用者：没找到哦）

    打个比方：
        这个函数 = "玩具箱管理员"
        - ICONS_DIR = "玩具箱"（assets/icons/ 文件夹）
        - icon_files = "箱子里的玩具列表"
        - random.choice() = "闭着眼睛从箱子里拿一个"
        - icon_img = "拿出来的玩具"

    参数：
        icon_size: 图标要变成多大（正方形，比如 60 就变成 60x60 像素）

    返回：
        调整好大小的图标图片；如果没找到图标，返回 None
    """
    # ===== 第一步：检查玩具箱（文件夹）有没有 =====
    if not ICONS_DIR.exists():
        # 👆 ICONS_DIR.exists() 检查文件夹是否存在
        # 如果文件夹都没有，就直接返回 None（告诉调用者：没找到玩具箱）
        logger.debug(f"图标目录不存在: {ICONS_DIR}")
        return None

    # ===== 第二步：从玩具箱里挑出所有"合格的玩具"（图标文件） =====
    # 支持的图标格式：PNG、JPG、WebP
    icon_files = [
        f for f in ICONS_DIR.iterdir()
        # 👆 ICONS_DIR.iterdir() 把文件夹里所有文件都列出来
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        # 👆 只挑后缀是这些的文件，就像只挑"玩具车"，不要"书"和"衣服"
    ]

    # ===== 第三步：检查玩具箱里有没有玩具 =====
    if not icon_files:
        # 👆 如果 icon_files 是空列表（里面什么都没有）
        logger.debug(f"图标目录为空: {ICONS_DIR}")
        return None  # 告诉调用者：玩具箱是空的

    # ===== 第四步：闭着眼睛随机拿一个玩具 =====
    icon_path = random.choice(icon_files)
    # 👆 random.choice() = 随机选择，就像抽奖一样
    logger.info(f"选中图标: {icon_path.name}")

    # ===== 第五步：把玩具拿出来，整理好（打开图片并调整大小） =====
    try:
        # 🖼️ 打开图片文件，就像拆开玩具包装
        icon_img = Image.open(icon_path).convert("RGBA")
        # 👆 convert("RGBA") 让图片支持透明背景（就像玩具可以有透明的翅膀）

        # 把图片调整到指定大小，就像把大玩具缩小到合适的尺寸
        icon_img = icon_img.resize((icon_size, icon_size), Image.LANCZOS)
        # 👆 Image.LANCZOS 是一种高级的缩放方法，能让图片缩小后依然清晰

        return icon_img  # 把整理好的玩具交给调用者
    except Exception as e:
        # 如果打开图片失败（比如文件损坏），就记录错误并返回 None
        logger.warning(f"加载图标失败: {icon_path.name}, 错误: {e}")
        return None


# ========================== 文字工具 ==========================

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """把长文字自动换行"""
    lines: List[str] = []
    current_line = ""

    for char in text:
        test_line = current_line + char
        if font.getlength(test_line) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = char

    if current_line:
        lines.append(current_line)

    return lines


def _draw_text_spaced(
    draw: ImageDraw.Draw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    spacing: int = 20,
    stroke_color: str = "#000000",
    stroke_width: int = 0,
) -> int:
    """绘制带字间距的文字（可带描边），返回底部y

    参数：
        stroke_color: 描边颜色，默认黑色
        stroke_width: 描边宽度，0表示不描边
    """
    for char in text:
        if stroke_width > 0:
            # 先画描边（在文字周围画一圈深色）
            draw.text((x, y), char, fill=stroke_color, font=font, stroke_width=stroke_width)
        # 再画文字主体（覆盖在描边上）
        draw.text((x, y), char, fill=color, font=font)
        x += int(font.getlength(char)) + spacing
    return y + int(font.size * 1.4)


def _draw_multiline_spaced(
    draw: ImageDraw.Draw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    spacing: int = 20,
    max_width: int = 700,
) -> int:
    """绘制带字间距的多行文字，返回底部y"""
    lines = _wrap_text(text, font, max_width)
    for line in lines:
        y = _draw_text_spaced(draw, line, x, y, font, color, spacing)
    return y


def _draw_centered_text(
    draw: ImageDraw.Draw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    canvas_width: int,
    spacing: int = 15,
    stroke_color: str = "#1a1a2e",
    stroke_width: int = 0,
) -> int:
    """绘制居中带字间距的文字（可带描边），返回底部y"""
    # 计算总宽度
    total_w = sum(int(font.getlength(c)) + spacing for c in text) - spacing
    x = (canvas_width - total_w) // 2
    return _draw_text_spaced(draw, text, x, y, font, color, spacing, stroke_color, stroke_width)


def _draw_multiline_centered(
    draw: ImageDraw.Draw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    canvas_width: int,
    max_width: int = 800,
    line_spacing: Optional[int] = None,
    stroke_color: str = "#1a1a2e",
    stroke_width: int = 0,
) -> int:
    """绘制居中多行文字（可带描边），返回底部y"""
    lines = _wrap_text(text, font, max_width)
    if line_spacing is None:
        line_spacing = int(font.size * LINE_SPACING_RATIO)

    center_x = canvas_width // 2
    for line in lines:
        if stroke_width > 0:
            # 先画描边
            draw.text((center_x, y), line, fill=stroke_color, font=font, anchor="ma", stroke_width=stroke_width)
        # 再画文字主体
        draw.text((center_x, y), line, fill=color, font=font, anchor="ma")
        y += line_spacing
    return y


def _split_title_lines(title: str) -> List[str]:
    """智能拆分标题为两行"""
    if "的" in title:
        idx = title.index("的") + 1
        return [title[:idx], title[idx:]]

    for sep in ["，", "、", "；"]:
        if sep in title:
            idx = title.index(sep) + 1
            return [title[:idx], title[idx:]]

    mid = len(title) // 2
    return [title[:mid], title[mid:]]


# ========================== 背景绘制 ==========================

def _create_gradient_bg(width: int, height: int) -> Image.Image:
    """创建渐变背景（深蓝紫 → 灰紫 → 暗粉紫）"""
    img = Image.new("RGB", (width, height))

    # 解析颜色
    def hex_to_rgb(hex_color):
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    top_rgb = hex_to_rgb(COLOR_GRADIENT_TOP)
    mid_rgb = hex_to_rgb(COLOR_GRADIENT_MID)
    bot_rgb = hex_to_rgb(COLOR_GRADIENT_BOTTOM)

    for y in range(height):
        ratio = y / height
        if ratio < 0.5:
            # 上半部分：top → mid
            t = ratio * 2
            r = int(top_rgb[0] + (mid_rgb[0] - top_rgb[0]) * t)
            g = int(top_rgb[1] + (mid_rgb[1] - top_rgb[1]) * t)
            b = int(top_rgb[2] + (mid_rgb[2] - top_rgb[2]) * t)
        else:
            # 下半部分：mid → bottom
            t = (ratio - 0.5) * 2
            r = int(mid_rgb[0] + (bot_rgb[0] - mid_rgb[0]) * t)
            g = int(mid_rgb[1] + (bot_rgb[1] - mid_rgb[1]) * t)
            b = int(mid_rgb[2] + (bot_rgb[2] - mid_rgb[2]) * t)

        for x in range(width):
            img.putpixel((x, y), (r, g, b))

    return img


def _draw_cloud(img: Image.Image, cx: int, cy: int, size: int, alpha: int = 80):
    """绘制一朵云（由多个椭圆叠加组成）"""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    ellipses = [
        (cx - size, cy - size // 3, cx + size, cy + size // 3),
        (cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2),
        (cx + size // 4, cy - size // 3, cx + size, cy + size // 4),
    ]

    for box in ellipses:
        overlay_draw.ellipse(box, fill=(255, 255, 255, alpha))

    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=size // 4))

    base_rgba = img.convert("RGBA")
    composite = Image.alpha_composite(base_rgba, overlay)
    img.paste(composite, (0, 0))


def _draw_moon(img: Image.Image, cx: int, cy: int, radius: int):
    """绘制月亮（金色圆形+光晕）"""
    base_rgba = img.convert("RGBA")

    # 光晕（大而淡）
    for i in range(3):
        r = radius + i * 15
        alpha = max(40 - i * 12, 5)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(232, 199, 122, alpha)
        )
        base_rgba = Image.alpha_composite(base_rgba, overlay)

    # 月亮本体
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(232, 199, 122, 200)
    )
    base_rgba = Image.alpha_composite(base_rgba, overlay)
    img.paste(base_rgba, (0, 0))


# ========================== 卡片生成器 ==========================

class CardImageGenerator:
    """知识卡片图片生成器（v3）"""

    def __init__(self, width: int = CARD_WIDTH, height: int = CARD_HEIGHT):
        self.width = width
        self.height = height
        self._scale: float = width / 1080.0

        self._padding_h: int = max(10, int(PADDING_H * self._scale))
        self._padding_v: int = max(10, int(PADDING_V * self._scale))

        # ---------- 字体 ----------
        self.font_title_line1 = _load_font(max(8, int(72 * self._scale)), bold=True)
        self.font_title_line2 = _load_font(max(8, int(90 * self._scale)), bold=True)
        self.font_quote = _load_font(max(8, int(38 * self._scale)))
        self.font_quote_author = _load_font(max(8, int(22 * self._scale)))
        self.font_summary_title = _load_font(max(8, int(24 * self._scale)))
        self.font_summary = _load_font(max(8, int(28 * self._scale)))
        self.font_tag = _load_font(max(8, int(26 * self._scale)))
        self.font_tag_icon = _load_font(max(8, int(22 * self._scale)))
        self.font_rec_title = _load_font(max(8, int(24 * self._scale)))
        self.font_rec_name = _load_font(max(8, int(36 * self._scale)), bold=True)

        logger.info(f"CardImageGenerator v3 初始化, 画布={self.width}x{self.height}")

    def generate(self, card_data: Dict[str, Any]) -> Image.Image:
        """生成卡片图片（主入口）"""
        title = card_data.get("title", "知识卡片")
        quote = card_data.get("quote", "")
        source_quote = card_data.get("source_quote", "")
        summary = card_data.get("summary", "")
        keywords_str = card_data.get("keywords", "")
        book = card_data.get("book", "")
        movie = card_data.get("movie", "")

        keywords = [kw.strip() for kw in keywords_str.replace("，", ",").split(",") if kw.strip()]

        logger.info(f"开始生成卡片: title='{title[:20]}...'")

        # ========== 加载背景图 ==========
        img = self._load_background()
        draw = ImageDraw.Draw(img)

        # ========== 计算6个区域 ==========
        usable_height = self.height - self._padding_v * 2
        zone_heights = [int(usable_height * r) for r in ZONE_RATIOS]

        zones = {}
        y = self._padding_v
        zone_names = ["title", "quote1", "quote2", "summary", "keywords", "recommend"]
        for name, h in zip(zone_names, zone_heights):
            zones[name] = {"y_start": y, "y_end": y + h, "height": h}
            y += h

        # ========== 绘制各区域 ==========

        # --- 区域1：标题 ---
        self._draw_title(draw, title, zones["title"])

        # --- 区域2：金句卡片1 ---
        if quote:
            self._draw_quote_card(
                draw, quote, zones["quote1"],
                bg_alpha=120,  # 半透明磨砂，提高透明度增强文字对比度
                icon_text="✦",
            )

        # --- 区域3：金句卡片2 ---
        if source_quote:
            self._draw_quote_card(
                draw, source_quote, zones["quote2"],
                bg_alpha=160,  # 更深，提高透明度增强文字对比度
                icon_text="✧",
            )

        # --- 区域4：AI解读 ---
        if summary:
            self._draw_summary(draw, summary, zones["summary"])

        # --- 区域5：关键词胶囊标签 ---
        if keywords:
            self._draw_keywords(draw, keywords, zones["keywords"])

        # --- 区域6：AI推荐 ---
        self._draw_recommend(draw, book, movie, zones["recommend"])

        return img

    def _load_background(self) -> Image.Image:
        """加载背景图片并叠加半透明遮罩"""
        bg_path = None

        if BACKGROUNDS_DIR.exists():
            bg_files = [
                f for f in BACKGROUNDS_DIR.iterdir()
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
            ]
            if bg_files:
                bg_path = random.choice(bg_files)
                logger.info(f"选中背景图: {bg_path.name}")

        if bg_path is None:
            logger.warning("未找到背景图，使用纯色背景")
            return Image.new("RGBA", (self.width, self.height), COLOR_DEEP_PURPLE)

        bg = Image.open(bg_path).convert("RGB")
        scale_w = self.width / bg.width
        scale_h = self.height / bg.height
        scale = max(scale_w, scale_h)

        new_w = int(bg.width * scale)
        new_h = int(bg.height * scale)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)

        left = (new_w - self.width) // 2
        top = (new_h - self.height) // 2
        bg = bg.crop((left, top, left + self.width, top + self.height))

        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, OVERLAY_ALPHA))
        bg_rgba = bg.convert("RGBA")
        img = Image.alpha_composite(bg_rgba, overlay)

        return img

    # ==================== 区域绘制 ====================

    def _draw_title(self, draw: ImageDraw.Draw, title: str, zone: dict):
        """标题：左对齐，带字间距，两行不同字号，带描边增强清晰度"""
        lines = _split_title_lines(title)

        x_start = int(180 * self._scale)
        y = zone["y_start"] + int(40 * self._scale)

        for i, line in enumerate(lines):
            font = self.font_title_line1 if i == 0 else self.font_title_line2
            y = _draw_text_spaced(
                draw, line, x_start, y, font, COLOR_GOLD,
                spacing=int(20 * self._scale),
                stroke_color="#1a1a2e",  # 深紫色描边
                stroke_width=int(2 * self._scale)  # 描边宽度，让文字更清晰
            )

    def _draw_quote_card(
        self, draw: ImageDraw.Draw, quote: str, zone: dict,
        bg_alpha: int = 60, icon_text: str = "✦"
    ):
        """绘制金句卡片（半透明圆角矩形+左侧图标+左对齐文字）"""
        card_w = int(800 * self._scale)
        card_h = int(230 * self._scale)
        card_x = int(140 * self._scale)
        card_y = zone["y_start"] + int((zone["height"] - card_h) // 2)
        border_radius = int(32 * self._scale)

        # ---------- 绘制半透明卡片背景（磨砂玻璃效果） ----------
        card_overlay = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_overlay)
        card_draw.rounded_rectangle(
            [0, 0, card_w, card_h],
            radius=border_radius,
            fill=(41, 39, 71, bg_alpha)
        )
        card_draw.rounded_rectangle(
            [0, 0, card_w, card_h],
            radius=border_radius,
            outline=(232, 199, 122, 150),
            width=max(1, int(1 * self._scale))
        )
        # 创建全尺寸overlay并粘贴卡片
        full_overlay = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
        full_overlay.paste(card_overlay, (card_x, card_y))
        base_rgba = draw._image.convert("RGBA")
        composite = Image.alpha_composite(base_rgba, full_overlay)
        draw._image.paste(composite, (0, 0))

        # ---------- 左侧图标（优先加载图标文件，回退到圆球+文字） ----------
        # 📐 计算图标大小和位置
        icon_size = int(60 * self._scale)
        # 👆 图标大小是 60x60 像素（乘以缩放比例），就像一个小徽章
        icon_bg_x = card_x + int(50 * self._scale)
        # 👆 图标左边距离卡片左边 50 像素（留出一点空隙）
        icon_bg_y = card_y + (card_h - icon_size) // 2
        # 👆 图标垂直居中：卡片高度减去图标高度，除以 2，就是上边距

        # 🎲 尝试从图标文件夹里随机拿一个图标
        icon_img = _load_random_icon(icon_size)
        # 👆 调用玩具箱管理员，让它随机拿一个玩具（图标）

        if icon_img is not None:
            # ✅ 拿到了图标！直接把图标贴到卡片上

            # 把卡片图片转换成支持透明的模式（RGBA）
            base_rgba = draw._image.convert("RGBA")
            # 👆 RGBA = 红、绿、蓝、透明度，就像给图片加了一层"透明魔法"

            # 创建一个全透明的画布，用来放图标
            full_icon = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
            # 👆 (0, 0, 0, 0) = 黑色但完全透明（看不见）

            # 把图标贴到画布的指定位置
            full_icon.paste(icon_img, (icon_bg_x, icon_bg_y), icon_img)
            # 👆 第三个参数 icon_img 是"蒙版"，用来保留图标的透明部分
            #    就像贴贴纸时，只贴有图案的地方，透明的地方不会盖住下面

            # 把图标画布和卡片图片合并
            composite = Image.alpha_composite(base_rgba, full_icon)
            # 👆 alpha_composite = 透明合并，让两个图片重叠时透明部分正常显示

            # 把合并后的图片放回原来的卡片上
            draw._image.paste(composite, (0, 0))

        else:
            # ❌ 没找到图标！那就用老办法：画一个圆球，上面写个字

            # 创建一个透明的小圆画布，用来画圆球
            icon_overlay = Image.new("RGBA", (icon_size, icon_size), (0, 0, 0, 0))
            icon_draw = ImageDraw.Draw(icon_overlay)

            # 在小圆画布上画一个金色的圆形（圆球背景）
            icon_draw.ellipse([0, 0, icon_size, icon_size], fill=(232, 199, 122, 100))
            # 👆 ellipse = 椭圆，这里画的是正圆（因为宽高一样）
            #    fill=(232, 199, 122, 100) = 金色，透明度 100（半透明）

            # 把小圆画布放到卡片的全大图上
            full_icon = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
            full_icon.paste(icon_overlay, (icon_bg_x, icon_bg_y))

            # 合并到卡片上
            base_rgba = draw._image.convert("RGBA")
            composite = Image.alpha_composite(base_rgba, full_icon)
            draw._image.paste(composite, (0, 0))

            # 在圆球中间写一个装饰符号（比如 ✦ 或 ✧）
            icon_font = _load_font(max(8, int(28 * self._scale)))
            # 👆 加载字体，大小是 28 像素
            draw.text(
                (icon_bg_x + icon_size // 2, icon_bg_y + icon_size // 2),
                # 👆 坐标：图标左上角 + 图标大小的一半 = 正中间
                icon_text, fill=COLOR_GOLD, font=icon_font, anchor="mm"
                # 👆 anchor="mm" = 文字中心点对齐坐标点（就像把字放在靶心）
            )

        # ---------- 正文（左对齐） ----------
        text_x = card_x + int(130 * self._scale)
        text_max_w = card_w - int(160 * self._scale)

        # 分离破折号出处
        dash = "\u2014\u2014"
        main_quote = quote
        author = None
        if dash in quote:
            parts = quote.split(dash, 1)
            main_quote = parts[0].rstrip()
            author = "\u2014\u2014" + parts[1].lstrip()

        # 绘制引文（带描边增强清晰度）
        y_text = card_y + int(30 * self._scale)
        lines = _wrap_text(main_quote, self.font_quote, text_max_w)
        line_spacing = int(self.font_quote.size * 1.5)
        stroke_width = int(1 * self._scale)  # 描边宽度

        for line in lines:
            # 先画描边，让文字更清晰
            draw.text((text_x, y_text), line, fill="#1a1a2e", font=self.font_quote, stroke_width=stroke_width)
            # 再画文字主体
            draw.text((text_x, y_text), line, fill=COLOR_CREAM, font=self.font_quote)
            y_text += line_spacing

        # ---------- 作者（右下角，带描边） ----------
        if author:
            author_font = self.font_quote_author
            author_w = int(author_font.getlength(author))
            author_x = card_x + card_w - int(50 * self._scale) - author_w
            author_y = card_y + card_h - int(40 * self._scale)
            # 先画描边
            draw.text((author_x, author_y), author, fill="#1a1a2e", font=author_font, stroke_width=stroke_width)
            # 再画文字主体
            draw.text((author_x, author_y), author, fill=COLOR_GOLD, font=author_font)

    def _draw_summary(self, draw: ImageDraw.Draw, summary: str, zone: dict):
        """AI解读区域，带描边增强清晰度"""
        y = zone["y_start"] + int(10 * self._scale)
        stroke_width = int(1 * self._scale)

        # 标题（带描边）
        y = _draw_centered_text(
            draw, "— AI解读 —", y,
            self.font_summary_title, COLOR_GOLD,
            self.width, spacing=int(15 * self._scale),
            stroke_width=stroke_width
        )
        y += int(20 * self._scale)

        # 正文（带描边）
        _draw_multiline_centered(
            draw, summary, y,
            self.font_summary, COLOR_CREAM,
            self.width, max_width=int(800 * self._scale),
            stroke_width=stroke_width
        )

    def _draw_keywords(self, draw: ImageDraw.Draw, keywords: List[str], zone: dict):
        """关键词胶囊标签"""
        tag_padding_h = int(24 * self._scale)
        tag_height = int(70 * self._scale)
        tag_gap = int(20 * self._scale)
        border_radius = int(30 * self._scale)

        # 构建标签
        tag_items = [(TAG_ICON_MAP.get(kw, "•"), kw) for kw in keywords]

        # 计算每个标签宽度
        tag_sizes = []
        for icon, text in tag_items:
            icon_w = int(self.font_tag_icon.getlength(icon))
            text_w = int(self.font_tag.getlength(text))
            tag_w = icon_w + int(6 * self._scale) + text_w + tag_padding_h * 2
            tag_sizes.append(tag_w)

        # 居中排列
        total_w = sum(tag_sizes) + tag_gap * (len(tag_sizes) - 1)
        x_start = (self.width - total_w) // 2
        y_center = zone["y_start"] + zone["height"] // 2
        y_tag = y_center - tag_height // 2

        x = x_start
        for (icon, text), tag_w in zip(tag_items, tag_sizes):
            tag_w_int = int(tag_w)
            x_int = int(x)

            # 半透明背景+边框
            tag_overlay = Image.new("RGBA", (tag_w_int, tag_height), (0, 0, 0, 0))
            tag_draw = ImageDraw.Draw(tag_overlay)
            tag_draw.rounded_rectangle(
                [0, 0, tag_w_int, tag_height],
                radius=border_radius,
                fill=(41, 39, 71, 180)
            )
            tag_draw.rounded_rectangle(
                [0, 0, tag_w_int, tag_height],
                radius=border_radius,
                outline=(232, 199, 122, 220),
                width=max(1, int(1 * self._scale))
            )
            base_rgba = draw._image.convert("RGBA")
            tag_full = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
            tag_full.paste(tag_overlay, (x_int, y_tag))
            composite = Image.alpha_composite(base_rgba, tag_full)
            draw._image.paste(composite, (0, 0))

            # 图标（带描边）
            icon_x = x_int + tag_padding_h
            icon_y = y_center - self.font_tag_icon.size // 2
            draw.text((icon_x, icon_y), icon, fill="#1a1a2e", font=self.font_tag_icon, stroke_width=int(1 * self._scale))
            draw.text((icon_x, icon_y), icon, fill=COLOR_GOLD, font=self.font_tag_icon)

            # 文字（带描边）
            text_x = icon_x + int(self.font_tag_icon.getlength(icon)) + int(6 * self._scale)
            text_y = y_center - self.font_tag.size // 2
            draw.text((text_x, text_y), text, fill="#1a1a2e", font=self.font_tag, stroke_width=int(1 * self._scale))
            draw.text((text_x, text_y), text, fill=COLOR_CREAM, font=self.font_tag)

            x += tag_w + tag_gap

    def _draw_recommend(self, draw: ImageDraw.Draw, book: str, movie: str, zone: dict):
        """AI推荐区域，带描边增强清晰度"""
        y = zone["y_start"] + int(10 * self._scale)
        stroke_width = int(1 * self._scale)

        # 标题（带描边）
        y = _draw_centered_text(
            draw, "— AI推荐 —", y,
            self.font_rec_title, COLOR_GOLD,
            self.width, spacing=int(15 * self._scale),
            stroke_width=stroke_width
        )
        y += int(30 * self._scale)

        # 书名（带描边）
        if book:
            _draw_multiline_centered(
                draw, book, y,
                self.font_rec_name, COLOR_CREAM,
                self.width,
                stroke_width=stroke_width
            )
            y += int(self.font_rec_name.size * 1.8)

        # 电影名（带描边）
        if movie:
            _draw_multiline_centered(
                draw, movie, y,
                self.font_rec_name, COLOR_CREAM,
                self.width,
                stroke_width=stroke_width
            )


# ========================== 便捷函数 ==========================

def generate_card_image(card_data: Dict[str, Any]) -> Image.Image:
    """快捷函数：一行代码生成卡片图片"""
    generator = CardImageGenerator()
    return generator.generate(card_data)


def generate_card_bytes(card_data: Dict[str, Any], format: str = "PNG") -> bytes:
    """生成卡片图片并返回字节数据"""
    img = generate_card_image(card_data)
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf.getvalue()


# ========================== 自测代码 ==========================

def main():
    """直接运行时的测试代码"""
    test_card_data = {
        "title": "\u5076\u7136\u8868\u8c61\u4e0b\u7684\u5fc5\u7136\u79ef\u7d2f",
        "quote": "\u201c\u771f\u7684\u731b\u58eb\uff0c\u6562\u4e8e\u76f4\u9762\u60e8\u6de1\u7684\u4eba\u751f\uff0c\u6562\u4e8e\u6b63\u89c6\u6dcc\u6dcf\u7684\u9c9c\u8840\u3002\u201d\u2014\u2014\u300a\u8bb0\u5ff5\u5218\u548c\u73cd\u541b\u300b",
        "source_quote": "\u4e16\u754c\u4e0a\u53ea\u6709\u4e00\u79cd\u771f\u6b63\u7684\u82f1\u96c4\u4e3b\u4e49\uff0c\u90a3\u5c31\u662f\u5728\u8ba4\u6e05\u751f\u6d3b\u7684\u771f\u76f8\u540e\u4f9d\u7136\u70ed\u7231\u751f\u6d3b\u3002\u2014\u2014\u7f57\u66fc\u00b7\u7f57\u5170",
        "summary": "\u6210\u529f\u5e76\u975e\u7eaf\u7cb9\u7684\u8fd0\u6c14\u535a\u5f08\uff0c\u800c\u662f\u6301\u7eed\u884c\u52a8\u4e0e\u56e0\u679c\u5f8b\u7684\u7cbe\u786e\u5151\u73b0\u3002",
        "keywords": "\u8fd0\u6c14\u3001\u957f\u671f\u4e3b\u4e49\u3001\u56e0\u679c\u5f8b\u3001\u6301\u7eed\u884c\u52a8",
        "book": "\u300a\u7eb3\u74e6\u5c14\u5b9d\u5178\u300b",
        "movie": "\u300a\u8096\u7533\u514b\u7684\u6551\u8d4e\u300b",
    }

    print("正在生成测试卡片...")
    img = generate_card_image(test_card_data)
    output_path = "test_card_v3.png"
    img.save(output_path)
    print(f"卡片已保存到: {output_path}")
    print(f"图片尺寸: {img.size}")


if __name__ == "__main__":
    main()
