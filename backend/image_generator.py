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

# ---------- 配色体系（治愈系温暖风格 v4） ----------
# 核心理念：留白、温暖、自然，像一张精美的书签

# 文字颜色（墨色系，适合阅读）
COLOR_TEXT_PRIMARY = "#2C2C2C"       # 深墨色：正文、引用文字
COLOR_TEXT_SECONDARY = "#6B6B6B"     # 柔灰色：辅助信息、小字
COLOR_TEXT_MUTED = "#9E9E9E"         # 浅灰色：最弱的文字
COLOR_TEXT_ON_IMAGE = "#FFFFFF"      # 纯白色：背景图上的文字（标题）

# 装饰色（柔金色，书签的感觉）
COLOR_ACCENT = "#C9A962"             # 柔金色：分割线、装饰元素、点缀

# 半透明面板颜色（温暖奶白）
COLOR_PANEL_BG = (255, 255, 255, 220)     # 白色 85% 透明度：信息面板
COLOR_QUOTE_BG = (255, 253, 248, 235)    # 暖白色 92% 透明度：引用区
COLOR_BOTTOM_BG = (245, 242, 238, 225)   # 米灰色 88% 透明度：底部信息区

# 文字颜色（保留旧变量名兼容，暂时保持旧值避免破坏深色卡片上的文字）
# 这些常量会在 Phase 3 重绘卡片时切换为新配色
COLOR_GOLD = COLOR_ACCENT           # 柔金色：用于标题、装饰线
COLOR_CREAM = "#FFFFFF"             # 白色：用于深色半透明卡片上的文字（不能改！）
COLOR_DEEP_PURPLE = "#292747"       # 深紫：用于卡片背景遮罩（保持旧值）
COLOR_WHITE = "#FFFFFF"             # 纯白：通用白色

# 背景遮罩（新版大幅降低透明度，保留背景图美感）
OVERLAY_ALPHA = 40  # 从 160 降到 40，几乎不遮挡背景

# ---------- 排版参数 ----------
PADDING_H = 80
PADDING_V = 60
LINE_SPACING_RATIO = 1.8  # 从 1.6 提升到 1.8，行距更宽松

# ---------- 背景图片 ----------
BACKGROUNDS_DIR = Path(__file__).parent.parent / "assets" / "backgrounds"
ICONS_DIR = Path(__file__).parent.parent / "assets" / "icons"
FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# ---------- 布局区域高度比例（暂时保持旧布局，Phase 2 再重构） ----------
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
# 新版字体体系：手写体（标题）+ 优雅衬线（正文）+ 系统字体（回退）
# 字体文件存放在 assets/fonts/ 目录下

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    加载中文字体（通用版，用于正文、副标题等）

    加载优先级：
    1. 系统微软雅黑（首选，清晰现代）
    2. 系统 DengXian
    3. 项目字体目录的 ZCOOL 小薇（衬线风格回退）
    4. 系统楷体/宋体
    5. 默认字体（最后兜底）
    """
    candidates = []

    # 优先使用系统微软雅黑
    candidates.extend([
        ("C:/Windows/Fonts/msyh.ttc", 2 if bold else 0),    # 微软雅黑
        ("C:/Windows/Fonts/msyhbd.ttc", 0),                  # 微软雅黑粗体
        ("C:/Windows/Fonts/Deng.ttf", 0),                    # DengXian
    ])

    # 项目字体回退
    if FONTS_DIR.exists():
        candidates.append((str(FONTS_DIR / "ZCOOLXiaoWei-Regular.ttf"), 0))

    # 更多系统字体回退
    candidates.extend([
        ("C:/Windows/Fonts/simkai.ttf", 0),           # 楷体
        ("C:/Windows/Fonts/simsun.ttc", 1 if bold else 0),  # 宋体
    ])

    for font_path, font_index in candidates:
        try:
            return ImageFont.truetype(font_path, size, index=font_index)
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的中文字体（通用）, size={size}")
    return ImageFont.load_default()


def _load_handwriting_font(size: int) -> ImageFont.FreeTypeFont:
    """
    加载手写体字体（用于大标题，营造温暖手写感）

    加载优先级：
    1. 刘建毛草手写体（渲染正常的手写体）
    2. 马善政手写体（⚠️ 注意：此字体 bbox 异常，可能渲染不出来）
    3. 系统楷体（最接近手写的系统字体）
    4. 系统仿宋（次优选择）

    ⚠️ 2026-08-02 发现：马善政字体 bbox 返回 (0, descent, width, descent)，
    导致字形在 PIL 中不可见。暂时放在第二优先级，待后续验证修复后再启用。
    """
    candidates = []

    # 优先使用渲染正常的手写体
    if FONTS_DIR.exists():
        candidates.extend([
            (str(FONTS_DIR / "LiuJianMaoCao-Regular.ttf"), 0),  # 刘建毛草 ✅ 渲染正常
            (str(FONTS_DIR / "MaShanZheng-Regular.ttf"), 0),    # 马善政 ⚠️ 可能渲染不出来
        ])

    # 系统字体回退
    candidates.extend([
        ("C:/Windows/Fonts/simkai.ttf", 0),       # 楷体
        ("C:/Windows/Fonts/simfang.ttf", 0),      # 仿宋
        ("C:/Windows/Fonts/simsun.ttc", 0),       # 宋体
    ])

    for font_path, font_index in candidates:
        try:
            logger.debug(f"加载手写体: {font_path}, size={size}")
            font = ImageFont.truetype(font_path, size, index=font_index)
            # 验证字体是否能正常渲染（检查 bbox 是否合理）
            test_bbox = font.getbbox("测试")
            if test_bbox[3] - test_bbox[1] <= 1:
                # bbox 高度为 0 或极小，字体有问题，跳过
                logger.warning(f"字体 {font_path} bbox 异常 {test_bbox}，跳过")
                continue
            return font
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的手写体字体, size={size}")
    return ImageFont.load_default()


def _load_light_font(size: int) -> ImageFont.FreeTypeFont:
    """
    加载细体字体（用于辅助信息、小字，轻盈不压迫）

    加载优先级：
    1. 系统微软雅黑 Light（最细的系统中文字体）
    2. ZCOOL 小薇（如果没有 Light 雅黑）
    3. DengXian
    4. 普通雅黑
    """
    candidates = [
        ("C:/Windows/Fonts/msyhl.ttc", 0),        # 微软雅黑 Light
    ]

    if FONTS_DIR.exists():
        candidates.append((str(FONTS_DIR / "ZCOOLXiaoWei-Regular.ttf"), 0))

    candidates.extend([
        ("C:/Windows/Fonts/Dengl.ttf", 0),         # DengXian Light
        ("C:/Windows/Fonts/msyh.ttc", 0),          # 微软雅黑
        ("C:/Windows/Fonts/simsun.ttc", 0),        # 宋体
    ])

    for font_path, font_index in candidates:
        try:
            return ImageFont.truetype(font_path, size, index=font_index)
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的细体字体, size={size}")
    return ImageFont.load_default()


def _load_lxgw_wenkai_font(size: int) -> ImageFont.FreeTypeFont:
    """
    加载 LXGW WenKai Bold 霞鹜文楷粗体（用于大标题）

    加载优先级：
    1. 项目字体目录的 LXGW WenKai Bold（多种文件名兼容）
    2. 系统楷体（最接近的手写风格系统字体）
    3. 刘建毛草（项目内手写体回退）
    """
    candidates = []

    if FONTS_DIR.exists():
        candidates.extend([
            (str(FONTS_DIR / "LXGWWenKai-Bold.ttf"), 0),
            (str(FONTS_DIR / "LXGWWenKai-Bold.otf"), 0),
            (str(FONTS_DIR / "LXGW WenKai Bold.ttf"), 0),
            (str(FONTS_DIR / "LXGW WenKai Bold.otf"), 0),
            (str(FONTS_DIR / "lxgw-wenkai-bold.ttf"), 0),
            (str(FONTS_DIR / "lxgw-wenkai-bold.otf"), 0),
        ])
        # 回退：项目内其他手写体
        candidates.append((str(FONTS_DIR / "LiuJianMaoCao-Regular.ttf"), 0))

    # 系统字体回退
    candidates.extend([
        ("C:/Windows/Fonts/simkai.ttf", 0),       # 楷体
        ("C:/Windows/Fonts/simfang.ttf", 0),      # 仿宋
        ("C:/Windows/Fonts/simsun.ttc", 0),       # 宋体
    ])

    for font_path, font_index in candidates:
        try:
            logger.debug(f"加载霞鹜文楷: {font_path}, size={size}")
            font = ImageFont.truetype(font_path, size, index=font_index)
            test_bbox = font.getbbox("测试")
            if test_bbox[3] - test_bbox[1] <= 1:
                logger.warning(f"字体 {font_path} bbox 异常 {test_bbox}，跳过")
                continue
            return font
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的霞鹜文楷字体, size={size}")
    return ImageFont.load_default()


def _load_jason_handwriting_font(size: int) -> ImageFont.FreeTypeFont:
    """
    加载 JasonHandWriting 手写体（用于卡片标题）

    加载优先级：
    1. 繁体中文手写体 JasonHandwriting1-Regular.ttf（支持中文）
    2. 其他繁体变体回退
    3. 拉丁版本回退
    4. 系统楷体回退
    """
    jason_dir = FONTS_DIR / "JasonHandWritingFonts-20251204"
    candidates = []

    if jason_dir.exists():
        tw_dir = jason_dir / "tw"
        latin_dir = jason_dir / "latin"

        # 优先使用繁体中文手写体
        if tw_dir.exists():
            candidates.extend([
                (str(tw_dir / "JasonHandwriting1-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting2-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting3-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting4-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting5-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting6-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting7-Regular.ttf"), 0),
                (str(tw_dir / "JasonHandwriting8-Regular.ttf"), 0),
                # SemiBold 变体
                (str(tw_dir / "JasonHandwriting1-SemiBold.ttf"), 0),
                (str(tw_dir / "JasonHandwriting2-SemiBold.ttf"), 0),
                (str(tw_dir / "JasonHandwriting3-SemiBold.ttf"), 0),
            ])

        # 拉丁版本回退
        if latin_dir.exists():
            candidates.extend([
                (str(latin_dir / "JasonHandwriting-Regular.ttf"), 0),
                (str(latin_dir / "JasonHandwriting-Bold.ttf"), 0),
                (str(latin_dir / "JasonHandwriting-SemiBold.ttf"), 0),
            ])

    # 系统字体回退
    candidates.extend([
        ("C:/Windows/Fonts/simkai.ttf", 0),       # 楷体
        ("C:/Windows/Fonts/simfang.ttf", 0),      # 仿宋
        ("C:/Windows/Fonts/simsun.ttc", 0),       # 宋体
    ])

    for font_path, font_index in candidates:
        try:
            logger.debug(f"加载 JasonHandWriting: {font_path}, size={size}")
            font = ImageFont.truetype(font_path, size, index=font_index)
            test_bbox = font.getbbox("测试")
            if test_bbox[3] - test_bbox[1] <= 1:
                logger.warning(f"字体 {font_path} bbox 异常 {test_bbox}，跳过")
                continue
            return font
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的 JasonHandWriting 字体, size={size}")
    return ImageFont.load_default()


def _load_sourcehan_serif_font(size: int) -> ImageFont.FreeTypeFont:
    """
    加载 SourceHanSerif 思源宋体（用于金句）

    加载优先级：
    1. 项目字体目录的 SourceHanSerif（多种文件名兼容）
    2. 系统宋体
    3. ZCOOL 小薇（衬线风格回退）
    """
    candidates = []

    if FONTS_DIR.exists():
        candidates.extend([
            (str(FONTS_DIR / "SourceHanSerifSC-Regular.otf"), 0),
            (str(FONTS_DIR / "SourceHanSerifCN-Regular.otf"), 0),
            (str(FONTS_DIR / "SourceHanSerif-Regular.otf"), 0),
            (str(FONTS_DIR / "SourceHanSerifSC-Regular.ttf"), 0),
            (str(FONTS_DIR / "SourceHanSerifCN-Regular.ttf"), 0),
            (str(FONTS_DIR / "SourceHanSerif-Regular.ttf"), 0),
            (str(FONTS_DIR / "SourceHanSerif.otf"), 0),
            (str(FONTS_DIR / "SourceHanSerif.ttf"), 0),
        ])
        candidates.append((str(FONTS_DIR / "ZCOOLXiaoWei-Regular.ttf"), 0))

    # 系统字体回退
    candidates.extend([
        ("C:/Windows/Fonts/simsun.ttc", 0),       # 宋体
        ("C:/Windows/Fonts/simkai.ttf", 0),       # 楷体
    ])

    for font_path, font_index in candidates:
        try:
            logger.debug(f"加载思源宋体: {font_path}, size={size}")
            font = ImageFont.truetype(font_path, size, index=font_index)
            test_bbox = font.getbbox("测试")
            if test_bbox[3] - test_bbox[1] <= 1:
                logger.warning(f"字体 {font_path} bbox 异常 {test_bbox}，跳过")
                continue
            return font
        except (OSError, IOError):
            continue

    logger.warning(f"未找到可用的思源宋体字体, size={size}")
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


# ========================== 背景感知文字 ==========================

def _add_gradient_overlay(img: Image.Image) -> Image.Image:
    """
    给背景图添加顶部→底部的暗化渐变遮罩

    效果：
        顶部：0% 透明 → 底部：50% 黑色
        这样文字区域永远有足够对比度，类似电影字幕的黑边处理
    """
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    h = img.height
    for y in range(h):
        # 从上到下，渐变增加黑色透明度
        ratio = y / h
        alpha = int(140 * ratio)  # 底部最多 140/255 ≈ 55% 黑色
        overlay_draw.line([(0, y), (img.width, y)], fill=(0, 0, 0, alpha))

    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _auto_text_color(img: Image.Image) -> Dict[str, str]:
    """
    全局检测背景亮度，返回统一的文字配色方案

    类似 iPhone 锁屏 / 小红书封面 的设计逻辑：
        一张图只检测一次，全卡统一用同一套配色

    返回：
        {
            "main":       主文字颜色,
            "secondary":  次要文字颜色,
            "accent":     装饰/标题颜色,
            "stroke":     描边/阴影颜色,
        }
    """
    try:
        # 缩小采样，加速计算
        sample = img.convert("RGB").resize((50, 50))
        pixels = list(sample.getdata())

        if not pixels:
            return {
                "main": "#FFFFFF", "secondary": "#EEEEEE",
                "accent": "#E8C77A", "stroke": "#222222",
            }

        brightness = sum(
            0.299 * r + 0.587 * g + 0.114 * b
            for r, g, b in pixels
        ) / len(pixels)

        if brightness > 170:
            # 背景很亮 → 深色文字
            return {
                "main": "#222222",
                "secondary": "#555555",
                "accent": "#B08A3E",
                "stroke": "#FFFFFF",
                "shadow": "#FFFFFF",
            }
        else:
            # 背景较暗 → 白色文字
            return {
                "main": "#FFFFFF",
                "secondary": "#EEEEEE",
                "accent": "#E8C77A",
                "stroke": "#222222",
                "shadow": "#000000",
            }
    except Exception:
        return {
            "main": "#FFFFFF", "secondary": "#EEEEEE",
            "accent": "#E8C77A", "stroke": "#222222",
            "shadow": "#000000",
        }


def _draw_text_with_shadow(
    draw: ImageDraw.Draw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    shadow_color: str = "#000000",
    shadow_offset: int = 2,
    stroke_color: Optional[str] = None,
    stroke_width: int = 0,
):
    """
    绘制带阴影/描边的文字，增强背景上的可读性
    x, y 为文字左上角坐标
    """
    # 1. 阴影
    if shadow_offset > 0:
        draw.text(
            (x + shadow_offset, y + shadow_offset),
            text, fill=shadow_color, font=font
        )

    # 2. 描边
    if stroke_width > 0 and stroke_color:
        draw.text(
            (x, y), text, fill=stroke_color, font=font,
            stroke_width=stroke_width
        )

    # 3. 文字主体
    draw.text((x, y), text, fill=color, font=font)


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

        # ---------- 字体（v6：JasonHandWriting 标题 + 思源宋体金句 + 雅黑正文） ----------
        # 标题用 JasonHandWriting 手写体
        self.font_title_handwriting = _load_jason_handwriting_font(max(8, int(72 * self._scale)))

        # 引用金句用 SourceHanSerif 思源宋体
        self.font_quote_handwriting = _load_sourcehan_serif_font(max(8, int(42 * self._scale)))

        # 副标题/英文装饰用微软雅黑
        self.font_subtitle = _load_font(max(8, int(28 * self._scale)))

        # 正文用微软雅黑，28px
        self.font_body = _load_font(max(8, int(28 * self._scale)))

        # 信息面板标题
        self.font_panel_title = _load_font(max(8, int(22 * self._scale)), bold=True)

        # 辅助信息用微软雅黑 Light
        self.font_caption = _load_light_font(max(8, int(18 * self._scale)))

        # 旧字体兼容（保留用于过渡期，后续版本移除）
        self.font_title_line1 = self.font_title_handwriting
        self.font_title_line2 = self.font_title_handwriting
        self.font_quote = self.font_quote_handwriting
        self.font_quote_author = self.font_caption
        self.font_summary_title = self.font_panel_title
        self.font_summary = self.font_body
        self.font_tag = self.font_body
        self.font_tag_icon = self.font_subtitle
        self.font_rec_title = self.font_panel_title
        self.font_rec_name = self.font_subtitle

        logger.info(f"CardImageGenerator v6 初始化, 画布={self.width}x{self.height}, 字体: JasonHandWriting(标题)/SourceHanSerif(金句)/Microsoft YaHei(正文)")

    def generate(self, card_data: Dict[str, Any], custom_bg: Optional[Image.Image] = None) -> Image.Image:
        """生成阅读书签风格知识卡片"""
        title = card_data.get("title", "知识卡片")
        quote = card_data.get("quote", "")
        source_quote = card_data.get("source_quote", "")
        summary = card_data.get("summary", "")
        book = card_data.get("book", "")
        movie = card_data.get("movie", "")

        logger.info(f"开始生成卡片: title='{title[:20]}...'" )

        img = self._load_background(custom_bg)

        # 1. 添加顶部暗化渐变遮罩，确保文字可读
        img = _add_gradient_overlay(img)

        # 2. 全局检测背景亮度，确定统一的文字配色方案
        self.text_theme = _auto_text_color(img)

        draw = ImageDraw.Draw(img)
        self._img = img

        # 新版布局：标题 / 金句 / 思考 / 延伸阅读
        zones = {
            "title": {"y_start": 120, "height": 220},
            "quote": {"y_start": 390, "height": 300},
            "summary": {"y_start": 760, "height": 260},
            "recommend": {"y_start": 1120, "height": 220},
        }

        self._draw_title(draw, title, zones["title"])

        if quote:
            self._draw_quote_card(draw, quote, zones["quote"], bg_alpha=80, icon_text="")

        if source_quote and not quote:
            self._draw_quote_card(draw, source_quote, zones["quote"], bg_alpha=80, icon_text="")

        if summary:
            self._draw_summary(draw, summary, zones["summary"])

        self._draw_recommend(draw, book, movie, zones["recommend"])

        return img


    def _load_background(self, custom_bg: Optional[Image.Image] = None) -> Image.Image:
        """加载背景图片并叠加半透明遮罩

        参数：
            custom_bg: 用户自定义的背景图片（PIL Image）。如果提供，优先使用；
                       如果为 None，则从背景库随机选一张。
        """
        bg = None  # 👈 最终要用来画画的背景图（RGB 模式）

        # ===== 第一步：如果用户上传了自定义背景，优先使用 =====
        if custom_bg is not None:
            # 把上传的图片转成 RGB 模式（去掉透明通道，方便后续处理）
            bg = custom_bg.convert("RGB")
            logger.info("使用用户上传的自定义背景图")
        else:
            # ===== 第二步：没有自定义背景，就从背景库随机选一张 =====
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

        # ===== 第三步：把背景图缩放裁剪到画布尺寸（cover 模式） =====
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
        """阅读笔记标题：使用全局文字主题"""
        x = int(120 * self._scale)
        y = zone["y_start"]
        theme = self.text_theme

        # 装饰小标题（READING NOTE）用主题 accent 色
        draw.text((x, y), "READING NOTE", fill=theme["accent"], font=self.font_subtitle)
        y += int(70 * self._scale)

        # 标题正文：纯白色，无阴影无描边
        lines = _split_title_lines(title)
        for line in lines:
            draw.text((x, y), line, fill="#FFFFFF", font=self.font_title_handwriting)
            y += int(95 * self._scale)

    def _draw_quote_card(
        self, draw: ImageDraw.Draw, quote: str, zone: dict,
        bg_alpha: int = 80, icon_text: str = ""
    ):
        """简洁引用区域：使用全局文字主题"""
        x = int(130 * self._scale)
        y = zone["y_start"]
        max_w = int(820 * self._scale)
        theme = self.text_theme

        # 顶部装饰线
        draw.line((x, y, x + 120, y), fill=theme["accent"], width=3)
        y += 35

        # 金句文字：带阴影 + 描边
        lines = _wrap_text(quote, self.font_quote_handwriting, max_w)
        for line in lines:
            _draw_text_with_shadow(
                draw, line, x, y, self.font_quote_handwriting,
                color=theme["main"],
                shadow_color=theme["shadow"],
                shadow_offset=int(2 * self._scale),
                stroke_color=theme["stroke"],
                stroke_width=int(1 * self._scale),
            )
            y += int(65 * self._scale)

    def _draw_summary(self, draw: ImageDraw.Draw, summary: str, zone: dict):
        """思考区域：半透明白雾 + 全局文字主题"""
        x = int(130 * self._scale)
        y = zone["y_start"]
        h = zone["height"]
        right = self.width - int(80 * self._scale)
        theme = self.text_theme

        # 1. 半透明白雾底
        mist_overlay = Image.new("RGBA", self._img.size, (0, 0, 0, 0))
        mist_draw = ImageDraw.Draw(mist_overlay)
        margin = int(20 * self._scale)
        mist_draw.rounded_rectangle(
            [x - margin, y - margin, right, y + h],
            radius=int(24 * self._scale),
            fill=(255, 255, 255, 50)
        )
        self._img.paste(Image.alpha_composite(self._img.convert("RGBA"), mist_overlay), (0, 0))

        # 2. 随机装饰图标
        icon_size = int(50 * self._scale)
        icon_img = _load_random_icon(icon_size)
        if icon_img:
            draw.text((x + icon_size + int(10 * self._scale), y + int(5 * self._scale)),
                      "一点思考", fill=theme["accent"], font=self.font_panel_title)
            self._img.paste(icon_img, (x, y), icon_img)
        else:
            draw.text((x, y), "一点思考", fill=theme["accent"], font=self.font_panel_title)

        y += 55

        # 3. 正文文字：带阴影
        lines = _wrap_text(summary, self.font_body, int(800 * self._scale))
        for line in lines:
            _draw_text_with_shadow(
                draw, line, x, y, self.font_body,
                color=theme["main"],
                shadow_color=theme["shadow"],
                shadow_offset=int(2 * self._scale),
                stroke_color=theme["stroke"],
                stroke_width=0,
            )
            y += int(42 * self._scale)

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
        """延伸阅读区域：使用全局文字主题"""
        x = int(130 * self._scale)
        y = zone["y_start"]
        theme = self.text_theme

        # 随机添加装饰图标
        icon_size = int(50 * self._scale)
        icon_img = _load_random_icon(icon_size)
        if icon_img:
            draw.text((x + icon_size + int(10 * self._scale), y + int(5 * self._scale)),
                      "延伸阅读", fill=theme["accent"], font=self.font_panel_title)
            self._img.paste(icon_img, (x, y), icon_img)
        else:
            draw.text((x, y), "延伸阅读", fill=theme["accent"], font=self.font_panel_title)
        y += 60

        if book:
            _draw_text_with_shadow(
                draw, f"📖 {book}", x, y, self.font_rec_name,
                color=theme["main"],
                shadow_color=theme["shadow"],
                shadow_offset=int(2 * self._scale),
                stroke_color=theme["stroke"],
                stroke_width=0,
            )
            y += 55

        if movie:
            _draw_text_with_shadow(
                draw, f"🎬 {movie}", x, y, self.font_rec_name,
                color=theme["main"],
                shadow_color=theme["shadow"],
                shadow_offset=int(2 * self._scale),
                stroke_color=theme["stroke"],
                stroke_width=0,
            )


# ========================== 便捷函数 ==========================

def generate_card_image(card_data: Dict[str, Any], custom_bg: Optional[Image.Image] = None) -> Image.Image:
    """快捷函数：一行代码生成卡片图片

    参数：
        custom_bg: 用户自定义背景图（可选）。如果提供，优先使用；
                   如果为 None，则随机选背景。
    """
    generator = CardImageGenerator()
    return generator.generate(card_data, custom_bg=custom_bg)


def generate_card_bytes(card_data: Dict[str, Any], format: str = "PNG") -> bytes:
    """生成卡片图片并返回字节数据"""
    img = generate_card_image(card_data)
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf.getvalue()



