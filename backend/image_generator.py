"""
================================================================================
                       AI 知识卡片 · 图片生成器
                 (Pillow-based Card Image Generator)
================================================================================
这个文件的作用：
    把 Dify 工作流返回的卡片设计 JSON，变成一张看得见摸得着的图片。

打个比方：
    - Dify 工作流 = "建筑设计师"，输出的是"设计图纸"（JSON 数据）
    - 这个文件 = "施工队"，按照图纸用 Pillow 把卡片"盖"出来
    - Pillow 库 = "画笔和颜料"，负责在画布上写字、画线、填色

技术方案：
    - 画布尺寸：800×1200（竖版卡片，适合手机分享）
    - 配色方案：深色背景 + 金色文字，极简哲思风格
    - 字体：优先使用系统宋体（衬线体），找不到则用默认字体
    - 文字排版：手动计算换行和居中，模拟设计软件的效果

依赖说明：
    Pillow（PIL）是 Python 最流行的图片处理库，像 Photoshop 的命令行版本
================================================================================
"""

# ========================== 第一段：导入工具箱 ==========================

import io  # 👉 io 是"内存读写器"：把图片临时存在内存里，不用写到硬盘
import math  # 👉 math 是"数学小助手"：帮你做各种数学计算（三角函数、圆周率等）
import textwrap  # 👉 textwrap 是"文字排版员"：自动把长文字切成一行一行的
import re  # 👉 re 是"文字侦探"：用正则表达式在文本中查找匹配的内容
import os  # 👉 os 是"操作系统小助手"：读取文件夹、路径等
import random  # 👉 random 是"随机数生成器"：随机选背景图
from pathlib import Path  # 👉 Path 是"地图导航"：处理文件路径
from typing import Dict, Any, Optional, List, Tuple  # 👉 类型标签

from PIL import Image, ImageDraw, ImageFont, ImageEnhance  # 👉 Pillow 图片处理三件套
from loguru import logger  # 👉 日记本


# ========================== 第二段：卡片尺寸和配色常量 ==========================
# 把常用的数值定义成常量（全大写），方便统一修改

# ---------- 画布尺寸（类似手机屏幕比例） ----------
CARD_WIDTH = 900  # 👈 画布宽度（像素）—— 高清渲染，前端显示时缩放
CARD_HEIGHT = 1200  # 👈 画布高度（像素）

# ---------- 配色方案：极简哲思风 ----------
COLOR_BG = "#1B1B2F"  # 👈 背景色：深蓝黑（像深夜的天空，安静深邃）
COLOR_BG_LIGHTER = "#252545"  # 👈 背景辅助色：稍亮的深蓝（用于装饰线条和区块）
COLOR_GOLD = "#D4A76A"  # 👈 主金色：温暖的古铜金（用于标题和核心文字）
COLOR_GOLD_LIGHT = "#E8D5B7"  # 👈 浅金色：柔和的金色（用于次要文字如摘要）
COLOR_WHITE = "#F0EDE5"  # 👈 米白色：柔和的白色（用于关键词和普通文字，不刺眼）
COLOR_TEXT_DIM = "#8B8B9E"  # 👈 暗灰色：低亮度文字（用于来源标签等辅助信息）
COLOR_ACCENT = "#5B8DEF"  # 👈 强调蓝：蓝色点缀（用于链接符号、小装饰）

# ---------- 排版参数 ----------
PADDING_H = 60  # 👈 左右内边距（像素）
PADDING_V = 50  # 👈 上下内边距（像素）
LINE_SPACING_RATIO = 1.6  # 👈 行间距倍数（相对于字号，1.6 = 行高的 1.6 倍）

# ---------- 背景图片配置 ----------
BACKGROUNDS_DIR = Path(__file__).parent.parent / "assets" / "backgrounds"
OVERLAY_ALPHA = 140  # 👈 遮罩透明度（0=全透明, 255=全黑，140 ≈ 55% 不透明度）


# ========================== 第三段：字体加载工具 ==========================

def _load_chinese_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    加载中文字体（"寻宝"策略）

    按照优先级从高到低依次尝试：
    1. 宋体（SimSun）— Windows 自带，衬线体，适合哲思风格
    2. 微软雅黑（Microsoft YaHei）— Windows 自带，清晰现代
    3. 等线（DengXian）— Windows 10+ 自带
    4. 黑体（SimHei）— Windows 老版本自带

    如果都找不到，用 Pillow 默认字体（不支持中文，但不会崩溃）

    参数：
        size: 字号大小（像素）
        bold: 是否加粗（目前通过字体选择模拟，非真粗体）

    返回：
        ImageFont 字体对象
    """
    # ---------- Windows 系统字体路径列表（按优先级排列） ----------
    # 用列表列举候选字体，逐个尝试，找到就用
    font_candidates = [
        ("C:/Windows/Fonts/simsun.ttc", 0),  # 👈 宋体（SimSun），索引 0 = 常规
        ("C:/Windows/Fonts/simsun.ttc", 1),  # 👈 宋体，索引 1 = 粗体（如果 bold=True）
        ("C:/Windows/Fonts/msyh.ttc", 0),  # 👈 微软雅黑，常规
        ("C:/Windows/Fonts/msyh.ttc", 1),  # 👈 微软雅黑，粗体
        ("C:/Windows/Fonts/Dengb.ttf", 0),  # 👈 等线，常规（注意文件名）
        ("C:/Windows/Fonts/Deng.ttf", 0),  # 👈 等线，别名
        ("C:/Windows/Fonts/simhei.ttf", 0),  # 👈 黑体，常规
    ]

    for font_path, font_index in font_candidates:
        try:
            font = ImageFont.truetype(font_path, size, index=font_index)
            # 👆 truetype 加载字体文件，size 指定大小，index 指定字体的第几个"变体"
            logger.debug(f"字体加载成功: {font_path} (index={font_index}, size={size})")
            return font
        except (OSError, IOError):
            continue  # 👆 这个字体不存在或坏了，试下一个

    # ---------- 兜底：所有系统字体都找不到，用 Pillow 默认字体 ----------
    logger.warning(f"未找到可用的中文字体，使用默认字体（中文可能显示为方框）size={size}")
    return ImageFont.load_default()
    # 👆 load_default() 返回一个等宽位图字体，不支持中文，但至少不会崩溃


def _get_bold_font(size: int) -> ImageFont.FreeTypeFont:
    """
    加载粗体中文字体

    和 _load_chinese_font 类似，但专门找粗体版本。
    粗体主要用于需要"视觉突出"的文字，比如标题里的核心词。

    参数：
        size: 字号大小

    返回：
        粗体字体对象
    """
    # ---------- 候选粗体字体列表 ----------
    bold_candidates = [
        ("C:/Windows/Fonts/simsun.ttc", 1),  # 👈 宋体粗体（ttc 文件的 index=1）
        ("C:/Windows/Fonts/msyhbd.ttc", 0),  # 👈 微软雅黑粗体（独立文件）
        ("C:/Windows/Fonts/msyh.ttc", 2),  # 👈 微软雅黑粗体（ttc 的 index=2）
        ("C:/Windows/Fonts/simhei.ttf", 0),  # 👈 黑体（天生粗一些）
    ]

    for font_path, font_index in bold_candidates:
        try:
            font = ImageFont.truetype(font_path, size, index=font_index)
            logger.debug(f"粗体字体加载成功: {font_path} (index={font_index}, size={size})")
            return font
        except (OSError, IOError):
            continue

    # ---------- 兜底：找不到粗体，用普通字体（至少能显示） ----------
    logger.warning(f"未找到粗体中文字体，使用普通字体 size={size}")
    return _load_chinese_font(size)


# ========================== 第四段：文字工具函数 ==========================

def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """
    把长文字自动换行（"文字裁缝"）

    Pillow 不像浏览器，不会自动换行。所以我们需要自己测量每行能放多少字。

    工作原理：
    1. 一个字符一个字符地累积
    2. 每加一个字符就用 font.getlength() 测一下当前行宽度
    3. 如果宽度超过 max_width，就把当前行"剪断"，开始新的一行

    参数：
        text  : 要换行的文本
        font  : 使用的字体
        max_width: 每行最大宽度（像素）

    返回：
        按行分割后的字符串列表，如 ["第一行文字", "第二行文字", ...]
    """
    lines: List[str] = []  # 👆 存放最终分好的每一行
    current_line = ""  # 👆 当前正在累积的这一行

    for char in text:
        # ---------- 测试：把当前字符加到行上，看宽度是否超标 ----------
        test_line = current_line + char
        line_width = font.getlength(test_line)

        if line_width <= max_width:
            # 没超标 → 把字符加进去
            current_line = test_line
        else:
            # 超标了 → 先把当前行"存档"，然后当前字符开始新的一行
            if current_line:
                lines.append(current_line)
            current_line = char  # 👆 新行从当前字符开始

    # ---------- 别忘了最后一行 ----------
    if current_line:
        lines.append(current_line)

    return lines


def _draw_multiline_text(
    draw: ImageDraw.Draw,
    text: str,
    y_start: int,
    font: ImageFont.FreeTypeFont,
    color: str,
    max_width: int,
    canvas_width: int,
    padding_h: int,
    line_spacing: Optional[int] = None,
    align: str = "center",
) -> int:
    """
    在画布上绘制多行文字（"画字机器人"）

    自动换行 + 自动计算位置 + 逐行绘制。

    参数：
        draw      : Pillow 的画笔对象
        text      : 要绘制的文字
        y_start   : 第一行顶部的 Y 坐标（像素，从上往下数）
        font      : 字体对象
        color     : 文字颜色
        max_width : 每行最大宽度
        canvas_width: 画布总宽度
        padding_h : 左右内边距
        line_spacing: 行间距（像素），不传则自动用字体大小 × 1.6
        align     : 对齐方式

    返回：
        绘制完所有文字后的底部 Y 坐标（可以紧接着画下一段文字）
    """
    if not text:
        return y_start

    if line_spacing is None:
        line_spacing = int(font.size * LINE_SPACING_RATIO)

    lines = _wrap_text(text, font, max_width)

    y = y_start
    center_x = canvas_width // 2

    for line in lines:
        if align == "center":
            x = center_x
            draw.text((x, y), line, fill=color, font=font, anchor="ma")
        elif align == "right":
            x = canvas_width - padding_h
            draw.text((x, y), line, fill=color, font=font, anchor="ra")
        else:
            x = padding_h
            draw.text((x, y), line, fill=color, font=font, anchor="la")

        y += line_spacing

    return y


def _draw_text_with_highlight(
    draw: ImageDraw.Draw,
    text: str,
    highlight_words: List[str],
    y_start: int,
    normal_font: ImageFont.FreeTypeFont,
    highlight_font: ImageFont.FreeTypeFont,
    normal_color: str,
    highlight_color: str,
    max_width: int,
    canvas_width: int,
    padding_h: int,
) -> int:
    """
    绘制带"高亮词"的多行文字（"荧光笔功能"）

    简化方案：和普通多行文字绘制一样
    """
    return _draw_multiline_text(
        draw, text, y_start, normal_font, normal_color, max_width,
        canvas_width, padding_h
    )


# ========================== 第五段：卡片生成器主类 ==========================

class CardImageGenerator:
    """
    知识卡片图片生成器（"卡片印刷机"）

    把 Dify 工作流返回的卡片设计数据，渲染成一张 800×1200 的竖版图片。
    
    使用方法：
        gen = CardImageGenerator()
        card_data = {
            "title": "偶然表象下的必然积累",
            "quote": "所谓运气...",
            "summary": "成功并非...",
            ...
        }
        image = gen.generate(card_data)
        image.save("card.png")  # 保存到文件
        # 或者
        image.show()  # 直接预览
    """

    def __init__(self, width: int = CARD_WIDTH, height: int = CARD_HEIGHT):
        """
        初始化生成器

        参数：
            width  : 卡片宽度（默认 800）
            height : 卡片高度（默认 1200）
        """
        self.width = width
        self.height = height
        # 👆 画布尺寸

        # ---------- 计算缩放比例（以 800 宽为基准） ----------
        # 所有字体大小、间距、装饰元素位置都按比例缩放
        # 这样无论卡片是 200 宽还是 2000 宽，布局都不会乱
        self._scale: float = width / 800.0
        # 👆 _scale = 1.0 时（默认 800 宽），一切照旧
        #    _scale = 0.25 时（200 宽），所有尺寸都缩小到 1/4

        # ---------- 计算缩放后的间距 ----------
        self._padding_h: int = max(10, int(PADDING_H * self._scale))
        # 👆 左右内边距，最少保留 10px 防止为 0
        self._padding_v: int = max(10, int(PADDING_V * self._scale))
        # 👆 上下内边距

        # ---------- 预加载所有字体（字号按比例缩放） ----------
        # 最小字号不低于 8，否则文字看不清
        self.font_title = _load_chinese_font(max(8, int(52 * self._scale)))
        self.font_title_bold = _get_bold_font(max(8, int(56 * self._scale)))
        self.font_quote = _load_chinese_font(max(8, int(36 * self._scale)))
        self.font_quote_bold = _get_bold_font(max(8, int(38 * self._scale)))
        self.font_summary = _load_chinese_font(max(8, int(22 * self._scale)))
        self.font_keyword = _load_chinese_font(max(8, int(20 * self._scale)))
        self.font_book = _load_chinese_font(max(8, int(20 * self._scale)))
        self.font_book_title = _load_chinese_font(max(8, int(24 * self._scale)))
        self.font_source = _load_chinese_font(max(8, int(18 * self._scale)))
        self.font_decorative = _load_chinese_font(max(8, int(14 * self._scale)))

        logger.info(
            f"CardImageGenerator 初始化完成, 画布={self.width}x{self.height}, "
            f"缩放比例={self._scale:.2f}"
        )

    def generate(self, card_data: Dict[str, Any]) -> Image.Image:
        """
        生成卡片图片（主入口，"按打印键"）

        这是外部调用者唯一需要关心的函数。传入 Dify 输出的 JSON，
        返回一张可以保存、展示、分享的 Pillow Image 对象。

        参数：
            card_data: Dify 工作流返回的卡片设计数据字典，包含：
                - title    (str): 卡片标题
                - quote    (str): 核心引用（金句）
                - summary  (str): AI 总结
                - keywords (str): 关键词（逗号分隔）
                - style    (str): 设计风格描述（目前用于参考，暂不做差异化渲染）
                - book     (str): 推荐书籍
                - movie    (str): 推荐电影

        返回：
            PIL.Image 对象（RGBA 模式，800×1200 的图片）
        """
        # ---------- 解析输入数据 ----------
        title = card_data.get("title", "知识卡片")
        quote = card_data.get("quote", "")
        summary = card_data.get("summary", "")
        keywords_str = card_data.get("keywords", "")
        style = card_data.get("style", "")
        book = card_data.get("book", "")
        movie = card_data.get("movie", "")

        # ---------- 解析关键词列表 ----------
        # 关键词是逗号分隔的字符串，比如 "长期主义, 厚积薄发, 因果律"
        keywords = [kw.strip() for kw in keywords_str.replace("，", ",").split(",") if kw.strip()]
        # 👆 同时处理中文逗号和英文逗号

        # ---------- 分析风格描述，提取"强调词" ----------
        # 从 style 字段中提取 Dify 指定要突出的词
        highlight_words = self._extract_highlight_words(style, title, quote)

        logger.info(f"开始生成卡片: title='{title[:20]}...', highlight={highlight_words}")

        # ========== 第一层：加载背景图（"铺画纸"） ==========
        img = self._load_background()
        draw = ImageDraw.Draw(img)
        # 👆 ImageDraw.Draw(img) 拿到"画笔"，所有绘制操作都通过它

        # ========== 第三层：从下往上布局 ==========
        # 采用"从下往上"的布局策略：先画底部，因为底部内容多
        # 这样能更好地利用画布空间，避免上半部分太空下半部分太挤

        y_current = self.height - self._padding_v  # 👆 从画布底部开始往上排

        # ---------- 底部装饰线 ----------
        y_current -= int(20 * self._scale)
        self._draw_horizontal_rule(draw, y_current, COLOR_GOLD_LIGHT, alpha=60)
        y_current -= int(30 * self._scale)

        # ---------- 推荐区域：书籍 & 电影 ----------
        if book or movie:
            y_current = self._draw_recommendations(draw, book, movie, y_current)

        # ---------- 分割线 ----------
        self._draw_horizontal_rule(draw, y_current, COLOR_GOLD_LIGHT, alpha=60)
        y_current -= int(40 * self._scale)

        # ---------- 关键词标签 ----------
        if keywords:
            y_current = self._draw_keywords(draw, keywords, y_current)

        # ---------- 分割线 ----------
        self._draw_horizontal_rule(draw, y_current, COLOR_GOLD_LIGHT, alpha=60)
        y_current -= int(40 * self._scale)

        # ---------- 摘要文字 ----------
        if summary:
            y_current = self._draw_summary(draw, summary, y_current)

        # ========== 第四层：从上往下布局（核心引用和标题） ==========
        # 上半部分：标题在顶部，引用在中间偏上

        y_top = self._padding_v + int(20 * self._scale)  # 👆 顶部起画点

        # ---------- 标题 ----------
        y_top = self._draw_title(draw, title, y_top, highlight_words)

        y_top += int(40 * self._scale)  # 👆 标题和引用之间的间距

        # ---------- 核心引用（金句） ----------
        if quote:
            y_top = self._draw_quote(draw, quote, y_top, highlight_words)

        # ---------- 顶部装饰线 ----------
        y_line = self._padding_v + int(10 * self._scale)
        self._draw_horizontal_rule(draw, y_line, COLOR_GOLD, alpha=150)

        logger.info("卡片生成完成")

        # ---------- 返回最终的图片 ----------
        return img

    def _extract_highlight_words(
        self, style: str, title: str, quote: str
    ) -> List[str]:
        """
        从风格描述中提取需要"高亮突出"的词

        比如 style 中包含 "视觉重心突出'必然'二字"，
        我们就提取出 "必然" 作为高亮词。

        参数：
            style: Dify 输出的风格描述
            title: 标题文本（用于验证高亮词是否在标题中存在）
            quote: 引用文本（用于验证高亮词是否在引用中存在）

        返回：
            高亮词列表（在 title 或 quote 中实际存在的词）
        """
        highlight_words: List[str] = []

        # ---------- 用正则匹配被「」、''、""、"、'引号包裹的词 ----------
        # 这些是中文中常见的"强调标记"
        patterns = [
            r'「(.+?)」',  # 👆 匹配中文书名号包裹的词，如「必然」
            r"『(.+?)』",  # 👆 匹配中文双书名号
            r'"(.+?)"',  # 👆 匹配英文双引号
            r"'(.+?)'",  # 👆 匹配英文单引号
            r'突出"(.+?)"',  # 👆 匹配 "突出"xxx""
            r'突出「(.+?)」',  # 👆 匹配 "突出「xxx」"
            r'突出\'(.+?)\'',  # 👆 匹配 "突出'xxx'"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, style)
            for match in matches:
                # ---------- 验证：高亮词必须在标题或引用中真实存在 ----------
                if match in title or match in quote:
                    if match not in highlight_words:
                        highlight_words.append(match)

        return highlight_words

    # =====================================================================
    # 以下是各个"绘制模块"（就像不同的画笔，各画各的部分）
    # =====================================================================

    def _load_background(self) -> Image.Image:
        """
        加载背景图片并叠加半透明遮罩

        从 assets/backgrounds/ 随机选一张图，缩放裁剪到卡片尺寸，
        然后盖一层半透明深色遮罩，保证文字可读性。

        返回：
            RGBA 模式的 Image 对象（卡片尺寸）
        """
        bg_path = None

        # ---------- 尝试从 backgrounds 文件夹随机选一张图 ----------
        if BACKGROUNDS_DIR.exists():
            bg_files = [
                f for f in BACKGROUNDS_DIR.iterdir()
                if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
            ]
            if bg_files:
                bg_path = random.choice(bg_files)
                logger.info(f"选中背景图: {bg_path.name}")

        # ---------- 如果没有背景图，退回纯色背景 ----------
        if bg_path is None:
            logger.warning("未找到背景图，使用纯色背景")
            return Image.new("RGBA", (self.width, self.height), COLOR_BG)

        # ---------- 加载并适配尺寸（居中裁剪） ----------
        bg = Image.open(bg_path).convert("RGB")
        # 计算缩放比例：确保背景图能覆盖整个卡片（不留黑边）
        scale_w = self.width / bg.width
        scale_h = self.height / bg.height
        scale = max(scale_w, scale_h)  # 👈 用较大的缩放比，确保覆盖

        new_w = int(bg.width * scale)
        new_h = int(bg.height * scale)
        bg = bg.resize((new_w, new_h), Image.LANCZOS)

        # 居中裁剪到卡片尺寸
        left = (new_w - self.width) // 2
        top = (new_h - self.height) // 2
        bg = bg.crop((left, top, left + self.width, top + self.height))

        # ---------- 叠加半透明深色遮罩（保证文字可读） ----------
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, OVERLAY_ALPHA))
        bg_rgba = bg.convert("RGBA")
        img = Image.alpha_composite(bg_rgba, overlay)

        logger.info(f"背景图加载完成: {bg_path.name}, 尺寸={self.width}x{self.height}")
        return img

    def _draw_background(self, draw: ImageDraw.Draw):
        """
        绘制背景装饰元素

        在深色背景上添加一些微妙的几何元素，增加设计感：
        - 右上角淡色大圆（象征日晕/时间循环）
        - 底部淡淡的横线纹理（象征年轮）
        - 角落的微小装饰点
        """
        # ---------- 右上角装饰圆 ----------
        # 所有位置和尺寸都按 _scale 缩放
        circle_cx = self.width - int(60 * self._scale)
        circle_cy = int(120 * self._scale)
        circle_r = int(180 * self._scale)

        for i in range(3):
            r_offset = int(i * 8 * self._scale)
            r = circle_r + r_offset
            draw.ellipse(
                [
                    circle_cx - r,
                    circle_cy - r,
                    circle_cx + r,
                    circle_cy + r,
                ],
                outline="#3A3A5C",
                width=max(1, int(self._scale)),
            )

        # ---------- 右下角小装饰圆 ----------
        small_r = int(40 * self._scale)
        small_cx = self.width - int(100 * self._scale)
        small_cy = self.height - int(80 * self._scale)
        draw.ellipse(
            [small_cx - small_r, small_cy - small_r, small_cx + small_r, small_cy + small_r],
            outline="#3A3A5C",
            width=max(1, int(self._scale)),
        )

        # ---------- 左侧竖线装饰 ----------
        line_x = int(45 * self._scale)
        top_y = int(80 * self._scale)
        bottom_y = self.height - int(80 * self._scale)
        draw.line(
            [(line_x, top_y), (line_x, bottom_y)],
            fill="#2E2E4A",
            width=max(1, int(self._scale)),
        )

        # ---------- 底部年轮纹理（多条横线模拟年轮） ----------
        base_y = self.height - int(130 * self._scale)
        for i in range(5):
            y = base_y + int(i * 12 * self._scale)
            alpha = max(20 - i * 3, 5)
            r, g, b = self._hex_to_rgb(COLOR_GOLD_LIGHT)
            line_color = (r, g, b, alpha)
            line_width = self.width - self._padding_h * 2
            line_img = Image.new("RGBA", (line_width, 1), line_color)
            img = draw._image
            img.paste(line_img, (self._padding_h, y), line_img)

    def _draw_title(
        self, draw: ImageDraw.Draw, title: str, y_start: int, highlight_words: List[str]
    ) -> int:
        """
        绘制卡片标题

        标题位于卡片顶部，用大号金色字体。

        如果标题中包含高亮词（如"必然"），在标题上方单独用更大的粗体金色
        渲染这些高亮词，形成"标题之上有核心词"的视觉层次。

        参数：
            draw    : 画笔
            title   : 标题文字
            y_start : 起始 Y 坐标
            highlight_words: 需要突出的词列表

        返回：
            标题区域底部 Y 坐标
        """
        # ---------- 如果有高亮词，先在标题上方渲染高亮词 ----------
        y = y_start

        for word in highlight_words:
            # 用更大的粗体金色渲染高亮词
            _draw_multiline_text(
                draw,
                word,
                y,
                self.font_title_bold,
                COLOR_GOLD,
                self.width - self._padding_h * 2,
                self.width,
                self._padding_h,
                align="center",
            )
            y += int(self.font_title_bold.size * 1.4)

        # ---------- 渲染标题正文 ----------
        # 标题和上方高亮词之间有一点间隔
        if highlight_words:
            y += int(10 * self._scale)

        y = _draw_multiline_text(
            draw,
            title,
            y,
            self.font_title,
            COLOR_GOLD,
            self.width - self._padding_h * 2,
            self.width,
            self._padding_h,
            align="center",
        )

        # ---------- 标题下方的短装饰线 ----------
        y += int(15 * self._scale)
        rule_width = int(80 * self._scale)
        rule_y = y
        x_left = (self.width - rule_width) // 2
        draw.line(
            [(x_left, rule_y), (x_left + rule_width, rule_y)],
            fill=COLOR_GOLD,
            width=max(1, int(2 * self._scale)),
        )

        return y + int(20 * self._scale)

    def _draw_quote(
        self, draw: ImageDraw.Draw, quote: str, y_start: int, highlight_words: List[str]
    ) -> int:
        """
        绘制核心引用（金句）

        这是卡片的"灵魂"，用较大的字号和醒目的颜色。

        如果引用中包含高亮词，会尝试用粗体+金色渲染（尽力而为，因为
        Pillow 不支持单行内多字体混排，这里采用整体渲染的方式）。

        参数：
            draw    : 画笔
            quote   : 引用文字
            y_start : 起始 Y 坐标
            highlight_words: 高亮词列表

        返回：
            引用区域底部 Y 坐标
        """
        # ---------- 引用文字最大宽度（比卡片宽度窄一点，留呼吸空间） ----------
        quote_max_width = self.width - self._padding_h * 3  # 👆 两边各留 1.5 倍边距

        # ---------- 尝试用粗体渲染（如果高亮词存在，说明需要强调） ----------
        if highlight_words:
            font = self.font_quote_bold
            color = COLOR_GOLD
        else:
            font = self.font_quote
            color = COLOR_GOLD_LIGHT

        y = _draw_multiline_text(
            draw,
            quote,
            y_start,
            font,
            color,
            quote_max_width,
            self.width,
            self._padding_h,
            align="center",
        )

        return y + int(10 * self._scale)

    def _draw_summary(
        self, draw: ImageDraw.Draw, summary: str, y_start: int
    ) -> int:
        """
        绘制 AI 摘要

        摘要文字用小号字体，颜色偏淡，放在引用下方，
        起到"补充说明"的作用。

        摘要文字块从底部向上排布，所以 y_start 是摘要的底部，
        我们需要计算出绘制起始位置。

        参数：
            draw    : 画笔
            summary : 摘要文字
            y_start : 摘要区域的"底部"Y 坐标（从下往上算）

        返回：
            摘要区域的"顶部"Y 坐标（即绘制完后的起始位置，供上方元素使用）
        """
        max_width = self.width - self._padding_h * 2

        # ---------- 先计算摘要文字需要多少行、总高度是多少 ----------
        lines = _wrap_text(summary, self.font_summary, max_width)
        line_spacing = int(self.font_summary.size * LINE_SPACING_RATIO)
        total_height = len(lines) * line_spacing

        # ---------- 从下往上算：底部是 y_start，顶部是 y_start - total_height ----------
        draw_start_y = y_start - total_height

        # ---------- 绘制标签 ----------
        label_y = draw_start_y - int(30 * self._scale)
        _draw_multiline_text(
            draw,
            "—  ＡＩ  ·  解  读  —",
            label_y,
            self.font_keyword,
            COLOR_TEXT_DIM,
            max_width,
            self.width,
            self._padding_h,
            align="center",
        )

        # ---------- 绘制摘要内容 ----------
        _draw_multiline_text(
            draw,
            summary,
            draw_start_y,
            self.font_summary,
            COLOR_GOLD_LIGHT,
            max_width,
            self.width,
            self._padding_h,
            align="center",
            line_spacing=line_spacing,
        )

        # 返回摘要区域的顶部（含标签）
        return label_y - int(20 * self._scale)

    def _draw_keywords(
        self, draw: ImageDraw.Draw, keywords: List[str], y_start: int
    ) -> int:
        """
        绘制关键词标签行

        关键词以 `#标签` 的形式水平排列，居中显示，从下往上排布。

        参数：
            draw     : 画笔
            keywords : 关键词列表
            y_start  : 关键词区域底部 Y 坐标

        返回：
            关键词区域顶部 Y 坐标
        """
        # ---------- 先构建标签文字总行 ----------
        tag_line = "  ".join([f"#{kw}" for kw in keywords])

        # ---------- 检查是否会超宽 ----------
        tag_width = self.font_keyword.getlength(tag_line)
        max_width = self.width - self._padding_h * 2

        if tag_width <= max_width:
            # 不超宽 → 单行居中
            y = y_start - int(self.font_keyword.size * LINE_SPACING_RATIO)
            _draw_multiline_text(
                draw,
                tag_line,
                y,
                self.font_keyword,
                COLOR_WHITE,
                max_width,
                self.width,
                self._padding_h,
                align="center",
            )
            return y - int(20 * self._scale)
        else:
            # 超宽 → 分两行
            mid = len(keywords) // 2
            line1 = "  ".join([f"#{kw}" for kw in keywords[:mid]])
            line2 = "  ".join([f"#{kw}" for kw in keywords[mid:]])

            line_spacing = int(self.font_keyword.size * LINE_SPACING_RATIO)
            y = y_start - line_spacing * 2

            _draw_multiline_text(
                draw, line1, y, self.font_keyword, COLOR_WHITE,
                max_width, self.width, self._padding_h, align="center"
            )
            _draw_multiline_text(
                draw, line2, y + line_spacing, self.font_keyword, COLOR_WHITE,
                max_width, self.width, self._padding_h, align="center"
            )
            return y - int(20 * self._scale)

    def _draw_recommendations(
        self, draw: ImageDraw.Draw, book: str, movie: str, y_start: int
    ) -> int:
        """
        绘制推荐区域（书籍 & 电影）

        展示 AI 推荐的同类书籍和电影。

        参数：
            draw    : 画笔
            book    : 推荐书籍名
            movie   : 推荐电影名
            y_start : 推荐区域底部 Y 坐标

        返回：
            推荐区域顶部 Y 坐标
        """
        max_width = self.width - self._padding_h * 2
        line_spacing = int(self.font_book.size * 1.5)

        # ---------- 从下往上布局 ----------
        items = []
        if book:
            items.append(("📖", book))
        if movie:
            items.append(("🎬", movie))

        total_rows = 1 + len(items)
        total_height = total_rows * line_spacing
        y = y_start - total_height

        # ---------- 标题行 ----------
        _draw_multiline_text(
            draw,
            "—  ＡＩ  ·  推  荐  —",
            y,
            self.font_keyword,
            COLOR_TEXT_DIM,
            max_width,
            self.width,
            self._padding_h,
            align="center",
        )
        y += line_spacing

        # ---------- 书籍和电影行 ----------
        for emoji, name in items:
            text = f"{emoji}  {name}"
            _draw_multiline_text(
                draw,
                text,
                y,
                self.font_book_title,
                COLOR_GOLD_LIGHT,
                max_width,
                self.width,
                self._padding_h,
                align="center",
            )
            y += line_spacing

        return y_start - total_height - int(20 * self._scale)

    def _draw_horizontal_rule(
        self, draw: ImageDraw.Draw, y: int, color: str, alpha: int = 100
    ):
        """
        画一条水平分割线

        由于 Pillow 的 draw.line 不支持 alpha 通道，
        这里用创建一个带透明度的小图片然后 paste 的方式实现。

        参数：
            draw  : 画笔（用于获取底层图片）
            y     : 线的 Y 坐标
            color : 颜色（十六进制如 #D4A76A）
            alpha : 透明度（0=完全透明, 255=完全不透明）
        """
        r, g, b = self._hex_to_rgb(color)
        rule_width = self.width - self._padding_h * 4
        rule_img = Image.new("RGBA", (rule_width, 1), (r, g, b, alpha))
        x = (self.width - rule_width) // 2
        img = draw._image
        img.paste(rule_img, (x, y), rule_img)

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        """
        将十六进制颜色转成 RGB 元组

        比如 "#D4A76A" → (212, 167, 106)

        参数：
            hex_color: 十六进制颜色字符串

        返回：
            (R, G, B) 三元组，每个值 0-255
        """
        hex_color = hex_color.lstrip("#")
        # 👆 去掉开头的 #
        return (
            int(hex_color[0:2], 16),  # 👆 前两位 → 红色（0-255）
            int(hex_color[2:4], 16),  # 👆 中间两位 → 绿色
            int(hex_color[4:6], 16),  # 👆 后两位 → 蓝色
        )


# ========================== 第六段：便捷函数 ==========================

def generate_card_image(card_data: Dict[str, Any]) -> Image.Image:
    """
    快捷函数：一行代码生成卡片图片

    这是最常用的入口，封装了 CardImageGenerator 的初始化。

    用法：
        from image_generator import generate_card_image

        card_data = {"title": "...", "quote": "...", ...}
        img = generate_card_image(card_data)
        img.save("my_card.png")

    参数：
        card_data: Dify 工作流返回的卡片设计数据

    返回：
        生成的 PIL Image 对象
    """
    generator = CardImageGenerator()
    return generator.generate(card_data)


def generate_card_bytes(card_data: Dict[str, Any], format: str = "PNG") -> bytes:
    """
    生成卡片图片并返回字节数据（用于网页直接展示）

    和 generate_card_image 的区别：
    - generate_card_image 返回 Image 对象（可以保存、进一步处理）
    - generate_card_bytes 返回 bytes（可以直接通过 HTTP 发送给浏览器）

    参数：
        card_data: 卡片设计数据
        format   : 图片格式（PNG, JPEG 等）

    返回：
        图片的二进制数据（bytes）
    """
    img = generate_card_image(card_data)

    # ---------- 把图片"存"到内存中的一个虚拟文件里 ----------
    buf = io.BytesIO()  # 👆 BytesIO 是"内存中的文件"（不和硬盘打交道）
    img.save(buf, format=format)  # 👆 把图片编码成 PNG 格式写入内存
    buf.seek(0)  # 👆 把"文件指针"移到开头，这样从开头开始读

    return buf.getvalue()  # 👆 拿到完整的二进制数据


# ========================== 第七段：自测代码 ==========================

def main():
    """
    直接运行这个文件时的测试代码
    
    用用户提供的示例数据生成一张测试卡片并保存。
    """
    # ---------- 测试数据（用户提供的 Dify 输出示例） ----------
    test_card_data = {
        "title": "偶然表象下的必然积累",
        "quote": "所谓运气，不过是长期主义在时间维度上的显影；所有横空出世的偶然，皆是厚积薄发的必然。",
        "summary": "成功并非纯粹的运气博弈，而是持续行动与因果律的精确兑现。坚持赋予了苦难与等待以正向意义，它是穿越瓶颈期唯一的底层支撑，让延迟满足成为对抗焦虑的最强解药。",
        "keywords": "长期主义, 厚积薄发, 因果律, 韧性, 延迟满足",
        "style": '极简哲思风，深色背景搭配金色衬线字体，视觉重心突出"必然"二字，辅以沙漏或年轮纹理象征时间沉淀',
        "book": "《纳瓦尔宝典》",
        "movie": "《肖申克的救赎》",
    }

    # ---------- 生成卡片 ----------
    print("正在生成测试卡片...")
    img = generate_card_image(test_card_data)

    # ---------- 保存 ----------
    output_path = "test_card_output.png"
    img.save(output_path)
    print(f"卡片已保存到: {output_path}")
    print(f"图片尺寸: {img.size}")
    print("可以用图片查看器打开预览。")


# ---------- Python 惯用写法：直接运行才执行 main，被 import 时不执行 ----------
if __name__ == "__main__":
    main()
