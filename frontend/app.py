"""
================================================================================
                            AI 知识卡片 · 前端页面
                      (Streamlit Frontend - MVP Test)
================================================================================
这个文件的作用：
    创建一个"网页"，让你在浏览器里输入文字，
    点击按钮发送给 Dify AI 处理，然后展示 AI 返回的结果。

打个比方：
    这个文件 = 便利店的"收银台"
    - 上面的文字输入框 = "你想要什么"（输入你的句子）
    - 左侧的设置面板 = "后台的开关"（配置 API 密钥和地址）
    - 生成按钮 = "下单按钮"（点了就发送给 Dify）
    - 下方的展示区 = "取餐口"（AI 处理完的结果在这里显示）

技术说明：
    Streamlit 是一个 Python 库，它可以把 Python 代码直接变成网页。
    你不需要写 HTML / CSS / JavaScript，只需要用 Python 函数来描述页面。
================================================================================
"""

# ========================== 第一段：导入工具箱 ==========================

import sys  # 👉 sys 是"系统管家"：和 Python 解释器打交道，这里用来修改模块搜索路径
import json  # 👉 json 是"翻译官"：能把字符串变成字典、把字典变成字符串
import os  # 👉 os 是"操作系统小助手"：读取系统环境变量
import re  # 👉 re 是"文字侦探"：用正则表达式在文本中查找匹配的内容
import io  # 👉 io 是"内存读写器"：把图片临时存在内存里，方便下载
from datetime import datetime  # 👉 datetime 是"时间戳"：生成唯一的文件名
from pathlib import Path  # 👉 Path 是"地图导航"：处理文件和文件夹路径

import streamlit as st  # 👉 streamlit 是"网页生成器"：把 Python 代码变成网页，简称 st
import streamlit.components.v1 as components  # 用于执行 JavaScript

# ---------- 让 Python 能"找到" backend 文件夹里的代码 ----------
# 因为 dify_api.py 在 backend/ 文件夹里
# 而 app.py 在 frontend/ 文件夹里
# 所以需要把 backend 文件夹的路径加到 sys.path（Python 的"寻路列表"）中
backend_path = Path(__file__).parent.parent / "backend"
# 👆 当前文件 frontend/app.py → 往上走一层到根目录 → 再进入 backend
sys.path.insert(0, str(backend_path))
# 👆 把 backend 的路径插到最前面，这样 import 时 Python 会优先去 backend 找

from dotenv import load_dotenv  # 👉 "密码读取器"：从 .env 文件里读出密钥和配置

# ---------- 加载 .env 文件 ----------
env_path = Path(__file__).parent.parent / ".env"  # 👆 找到项目根目录下的 .env 文件
load_dotenv(dotenv_path=env_path)  # 👆 把 .env 里的配置读到环境变量里

# ---------- 导入我们自己写的 Dify 客户端和图片生成器 ----------
# 现在 Python 已经知道去 backend/ 找了（前面加了 sys.path）
from dify_api import DifyClient  # 👆 我们自己写的"AI 对话客户端"
from image_generator import generate_card_image, BACKGROUNDS_DIR  # 👆 卡片印刷机 + 背景库目录
from database import get_db, GENERATED_DIR  # 👆 数据库操作和图片保存目录
from PIL import Image  # 👆 图片处理库：把上传的文件变成 PIL 图片对象


# ========================== 第二段：辅助工具函数 ==========================

def _get_config(key: str, default: str = "") -> str:
    """
    安全地获取配置值（"三保险"策略）

    按优先级从三个地方找：
    1. Streamlit 的 secrets（部署时用）
    2. 系统环境变量 / .env 文件（本地开发用）
    3. 默认值（兜底）

    为什么需要这个函数？
    ====================
    直接写 st.secrets.get() 在没有配置 secrets 时会直接报错崩溃。
    这个函数会先尝试，失败了就换一种方式，不会让程序崩溃。

    参数：
        key    : 配置项的名字，比如 "DIFY_API_KEY"
        default: 如果哪都找不到，用这个默认值

    返回：
        找到的配置值（字符串）
    """
    try:
        return st.secrets.get(key, default)  # 👆 先尝试从 Streamlit secrets 读
    except Exception:
        return os.getenv(key, default)  # 👆 读不到就从环境变量（.env）里读


def _parse_card_json(raw_text: str) -> dict:
    """
    解析 Dify 工作流返回的卡片设计 JSON

    Dify 工作流输出的 LLM 文本可能包含以下格式之一：
    1. 纯 JSON：{"title": "...", "quote": "..."}
    2. Markdown 代码块包裹的 JSON：```json\n{...}\n```
    3. 文本中嵌入 JSON（LLM 在 JSON 前后加了解释性文字）

    这个函数用"层层剥洋葱"的策略，尝试提取出有效的 JSON。

    参数：
        raw_text: Dify 工作流返回的原始文本

    返回：
        解析成功的字典；如果完全无法解析，返回空字典 {}
    """
    if not raw_text:
        return {}

    text = raw_text.strip()

    # ===== 策略 1：尝试直接解析（最常见的情况） =====
    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        pass  # 👆 解析失败继续尝试其他策略

    # ===== 策略 2：去掉 ```json ... ``` 包裹 =====
    # 匹配被 Markdown 代码块包裹的 JSON
    json_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    match = re.search(json_block_pattern, text, re.DOTALL)
    # 👆 re.DOTALL 让 . 也能匹配换行符，因为 JSON 通常跨多行
    if match:
        try:
            data = json.loads(match.group(1).strip())
            return data
        except json.JSONDecodeError:
            pass

    # ===== 策略 3：查找第一个 { 到最后一个 } 之间的内容 =====
    # 适用于 LLM 在 JSON 前后写了废话的情况
    # 比如："好的，以下是卡片设计：\n{...}\n希望对你有帮助"
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_candidate = text[first_brace:last_brace + 1]
        try:
            data = json.loads(json_candidate)
            return data
        except json.JSONDecodeError:
            pass

    # ===== 全部失败：返回空字典 =====
    return {}


def _extract_card_data_from_outputs(outputs: dict) -> dict:
    """
    从 Dify 工作流的 outputs 中提取卡片数据（支持两种模式）

    模式 1：单 JSON 模式
        Dify 输出只有一个变量，值是完整的卡片 JSON 字符串
        例：{"text": '{"title":"...","quote":"...","book":"..."}'}

    模式 2：多字段模式
        Dify 输出有多个变量，每个变量对应卡片的一个字段
        例：{"title":"...","quote":"...","summary":"...","book":"...","movie":"..."}

    参数：
        outputs: Dify workflow_finished 事件中的 outputs 字典

    返回：
        (card_data: dict, extraction_mode: str) 元组
        card_data: 卡片数据字典
        extraction_mode: "single_json" | "multi_field" | "empty"
    """
    if not outputs:
        return {}, "empty"

    # ===== 策略 A：多字段模式检测 =====
    # 如果 outputs 里有 card_data 需要的字段（title, quote 等），说明是多字段模式
    card_field_names = {"title", "quote", "summary", "keywords", "style", "book", "movie"}
    output_keys = set(outputs.keys())
    matching_fields = output_keys & card_field_names
    # 👆 取交集：看看 outputs 的 key 中有多少个是卡片字段名

    if len(matching_fields) >= 2:
        # 至少匹配 2 个字段 → 大概率是多字段模式
        # 直接使用 outputs 作为 card_data（只取匹配的字段）
        card_data = {k: outputs[k] for k in matching_fields if outputs[k]}
        # 👆 过滤掉空值
        return card_data, "multi_field"

    # ===== 策略 B：单 JSON 模式检测 =====
    # 遍历所有输出值，尝试把每个字符串值解析成 JSON
    for key, value in outputs.items():
        if isinstance(value, str):
            parsed = _parse_card_json(value)
            if parsed and len(parsed) >= 2:
                # 至少有 2 个字段 → 是有效的卡片 JSON
                return parsed, "single_json"

    # ===== 兜底：取第一个非空字符串作为 raw_text =====
    for key, value in outputs.items():
        if isinstance(value, str) and value.strip():
            return {"raw_text": value}, "fallback"

    return {}, "empty"


# ========================== 第三段：配置网页基本信息 ==========================

st.set_page_config(
    page_title="AI 知识卡片 - Dify 工作流测试",
    # 👆 浏览器标签页上显示的文字
    page_icon="✨",
    # 👆 浏览器标签页上的小图标（emoji）
    layout="centered",
    # 👆 页面布局："centered" = 内容居中（适合小工具），"wide" = 宽屏（适合数据看板）
)


# ========================== 第四段：网页标题 ==========================

st.title("卡片生成器")

# ========================== 第四段半：注入背景图 + 浮动动画 CSS ==========================
import base64
_assets_dir = Path.cwd().parent / "assets"
if not _assets_dir.exists():
    _assets_dir = Path.cwd() / "assets"

# 加载手写字体（使用系统字体，避免 base64 嵌入过大）
font_css = """
@font-face {
    font-family: 'Ma Shan Zheng';
    src: local('KaiTi'), local('STKaiti'), local('楷体');
    font-weight: normal;
    font-style: normal;
}
@font-face {
    font-family: 'LiuJian Mao Cao';
    src: local('STKaiti'), local('KaiTi'), local('楷体');
    font-weight: normal;
    font-style: normal;
}
"""

# 加载背景图（缩放到合理尺寸后嵌入）
bg_css = ""
bg_path = _assets_dir / "前端背景.png"
if bg_path.exists():
    try:
        from PIL import Image as _PIL
        import io as _io
        _bg_img = _PIL.open(bg_path)
        # 缩放到宽度 1200px 以内
        _w, _h = _bg_img.size
        if _w > 1200:
            _new_w = 1200
            _new_h = int(_h * 1200 / _w)
            _bg_img = _bg_img.resize((_new_w, _new_h), _PIL.LANCZOS)
        _buf = _io.BytesIO()
        _bg_img.save(_buf, format="JPEG", quality=85, optimize=True)
        _bg_data = base64.b64encode(_buf.getvalue()).decode()
        bg_css = f"""
    section.stMain {{
        background-image: url("data:image/jpeg;base64,{_bg_data}") !important;
        background-size: cover !important;
        background-position: center center !important;
        background-repeat: no-repeat !important;
        background-attachment: fixed !important;
    }}
    [data-testid="stAppViewContainer"] > div {{
        background: transparent !important;
    }}
        """
    except Exception:
        bg_css = ""

# 加载并处理古风素材图（去白底、旋转等）
from PIL import Image as PILImage
import io

def _remove_white_bg(img, threshold=245):
    """将接近白色的像素转为透明（使用 numpy 加速，更宽容的判断）"""
    import numpy as np
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.array(img)
    # 判断条件：像素亮度（平均）>= threshold，且最大通道差 <= 15（灰度/白色）
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    brightness = (r + g + b) / 3
    max_diff = np.maximum(np.maximum(np.abs(r.astype(int)-g.astype(int)), np.abs(g.astype(int)-b.astype(int))), np.abs(r.astype(int)-b.astype(int)))
    white_mask = (brightness >= threshold) & (max_diff <= 20)
    arr[white_mask, 3] = 0
    return Image.fromarray(arr)

def _remove_color_bg(img, bg_color=(255, 255, 255), tolerance=30):
    """将指定颜色（含容差）转为完全透明"""
    import numpy as np
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.array(img)
    r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
    mask = (np.abs(r - bg_color[0]) <= tolerance) & \
           (np.abs(g - bg_color[1]) <= tolerance) & \
           (np.abs(b - bg_color[2]) <= tolerance)
    arr[mask, 3] = 0
    return Image.fromarray(arr)

def _trim_transparent(img):
    """裁剪掉图片四周的透明区域"""
    import numpy as np
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.array(img)
    alpha = arr[:,:,3]
    rows = np.any(alpha > 10, axis=1)
    cols = np.any(alpha > 10, axis=0)
    if rows.any():
        ymin, ymax = np.where(rows)[0][[0, -1]]
        xmin, xmax = np.where(cols)[0][[0, -1]]
        img = img.crop((xmin, ymin, xmax+1, ymax+1))
    return img

def _process_img(img_path, rotate=0, max_size=None, remove_bg=False, bg_color=(255,255,255), tolerance=30):
    """加载图片并处理：去背景、旋转、裁剪、缩放"""
    if not img_path.exists():
        return None
    img = PILImage.open(img_path)
    
    # 确保 RGBA 模式
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    
    # 去背景
    if remove_bg:
        img = _remove_color_bg(img, bg_color, tolerance)
    
    # 旋转（使用透明背景填充扩展区域）
    if rotate != 0:
        img = img.rotate(rotate, expand=True, resample=PILImage.BICUBIC, fillcolor=(0,0,0,0))
        # 裁剪掉旋转后多余的透明边框
        img = _trim_transparent(img)
    
    # 缩放（保持比例）
    if max_size:
        w, h = img.size
        if max(w, h) > max_size:
            if w > h:
                new_w = max_size
                new_h = int(h * max_size / w)
            else:
                new_h = max_size
                new_w = int(w * max_size / h)
            img = img.resize((new_w, new_h), PILImage.LANCZOS)
    
    # 转为 base64
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"

# 处理三张素材
# 便利贴：去除白色背景（保留米黄色主体），不旋转
_note_b64 = _process_img(_assets_dir / "便利贴本体.png", rotate=0, max_size=600, remove_bg=True, bg_color=(255,255,255), tolerance=15)

# 羽毛笔：去除白色背景，顺时针旋转45°
_feather_b64 = _process_img(_assets_dir / "羽毛笔.png", rotate=45, max_size=220, remove_bg=True, bg_color=(255,255,255), tolerance=18)

# 书签：去除白色背景，顺时针旋转90°
_bookmark_b64 = _process_img(_assets_dir / "书签.png", rotate=-90, max_size=130, remove_bg=True, bg_color=(255,255,255), tolerance=40)

st.markdown(f"""
<style>
/* ===== 加载手写字体 ===== */
{font_css}

/* ===== 古风卷轴 · 全局样式 ===== */

@keyframes sprite-float {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-12px); }}
}}
@keyframes ink-spread {{
    0% {{ opacity: 0; transform: scale(0.8); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}
@keyframes seal-press {{
    0% {{ transform: scale(1.3) rotate(-5deg); }}
    60% {{ transform: scale(0.95) rotate(-5deg); }}
    100% {{ transform: scale(1) rotate(-5deg); }}
}}

/* 小精灵浮动 */
.sprite-container {{
    display: flex;
    justify-content: center;
    margin: 10px 0 20px 0;
}}
.sprite-img {{
    animation: sprite-float 3s ease-in-out infinite;
    filter: drop-shadow(0 12px 20px rgba(180, 140, 60, 0.25));
    width: 280px;
}}

/* 透明背景层（仅内部容器，section.stMain 保留背景图） */
.stApp, section.stMain > div, section.stMain > div > div {{
    background: transparent !important;
}}

/* ===== 卡片弹窗全屏样式 ===== */
/* 当卡片弹窗激活时，全屏显示 iframe 及其所有容器 */
.card-modal-overlay .stAppViewContainer,
.card-modal-overlay .stAppViewContainer > div,
.card-modal-overlay .stMain,
.card-modal-overlay .stMainBlockContainer,
.card-modal-overlay .stVerticalBlock,
.card-modal-overlay .stElementContainer:last-child {{
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    z-index: 99999 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    overflow: hidden !important;
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}}
.card-modal-overlay .stElementContainer:last-child iframe {{
    width: 100vw !important;
    height: 100vh !important;
    border: none !important;
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    z-index: 100000 !important;
}}
/* 弹窗激活时隐藏侧边栏和其他内容 */
.card-modal-overlay [data-testid="stSidebar"],
.card-modal-overlay section[data-testid="stSidebar"],
.card-modal-overlay aside,
.card-modal-overlay .stSidebar {{
    display: none !important;
}}
.card-modal-overlay [data-testid="stToolbar"],
.card-modal-overlay [data-testid="stDecoration"],
.card-modal-overlay header {{
    display: none !important;
}}

/* ===== 古风主题配色 ===== */
:root {{
    --parchment-light: #f7ecd4;
    --parchment: #f0dfbf;
    --parchment-dark: #d9c49a;
    --ink-dark: #2c1810;
    --ink-medium: #4a3520;
    --gold: #b8860b;
    --gold-light: #d4a843;
    --gold-dark: #8b6914;
    --seal-red: #a52a2a;
    --seal-red-light: #c0392b;
    --scroll-end: #8b6914;
}}

/* ===== 卷轴容器 ===== */
.scroll-container {{
    position: relative;
    padding: 28px 40px 44px 40px;
    margin: 20px 0;
    background: linear-gradient(180deg, var(--parchment-light) 0%, var(--parchment) 15%, var(--parchment) 85%, var(--parchment-dark) 100%);
    border: 2px solid var(--gold);
    border-radius: 4px;
    box-shadow:
        inset 0 0 60px rgba(139, 105, 20, 0.1),
        inset 0 30px 80px rgba(139, 105, 20, 0.08),
        0 8px 24px rgba(0, 0, 0, 0.12),
        0 4px 8px rgba(139, 105, 20, 0.3);
}}

/* 卷轴两端的滚轴 */
.scroll-container::before,
.scroll-container::after {{
    content: '';
    position: absolute;
    left: -6px;
    right: -6px;
    height: 18px;
    background: linear-gradient(180deg, var(--gold-dark) 0%, var(--gold) 40%, var(--gold-light) 50%, var(--gold) 60%, var(--gold-dark) 100%);
    border: 2px solid var(--gold-dark);
    border-radius: 10px;
    box-shadow:
        0 2px 6px rgba(0, 0, 0, 0.2),
        inset 0 1px 2px rgba(255, 248, 220, 0.5);
}}
.scroll-container::before {{
    top: -14px;
}}
.scroll-container::after {{
    bottom: -14px;
}}

/* 羊皮纸纹理 */
.scroll-container > .scroll-texture {{
    position: absolute;
    inset: 0;
    background-image:
        radial-gradient(ellipse at 15% 25%, rgba(139, 105, 20, 0.08) 0%, transparent 40%),
        radial-gradient(ellipse at 85% 75%, rgba(139, 105, 20, 0.06) 0%, transparent 35%),
        radial-gradient(ellipse at 50% 50%, rgba(139, 105, 20, 0.03) 0%, transparent 60%);
    pointer-events: none;
    z-index: 0;
}}
.scroll-container > *:not(.scroll-texture) {{
    position: relative;
    z-index: 1;
}}

/* 羽毛笔装饰（左上角） */
.feather-pen {{
    position: absolute;
    top: -18px;
    left: 24px;
    width: 80px;
    height: 80px;
    z-index: 10;
    pointer-events: none;
    animation: ink-spread 0.8s ease-out;
}}
.feather-pen svg {{
    filter: drop-shadow(2px 3px 4px rgba(0, 0, 0, 0.25));
}}

/* 红色印章装饰（右下角） */
.red-seal {{
    position: absolute;
    bottom: -20px;
    right: 30px;
    width: 60px;
    height: 60px;
    z-index: 10;
    pointer-events: none;
    animation: seal-press 0.6s ease-out;
}}
.red-seal svg {{
    filter: drop-shadow(1px 2px 3px rgba(0, 0, 0, 0.3));
}}

/* 卷轴标签装饰 */
.scroll-label {{
    font-family: 'Ma Shan Zheng', 'LiuJian Mao Cao', 'KaiTi', 'STKaiti', serif;
    color: var(--ink-dark);
    font-size: 20px;
    letter-spacing: 4px;
    margin-bottom: 12px;
    padding-left: 8px;
    border-left: 3px solid var(--seal-red);
    line-height: 1;
}}

/* ===== 文本域容器：便利贴风格（仅主区域） ===== */
section.stMain .stTextArea {{
    position: relative;
    margin-top: 8px;
    overflow: visible !important;
}}
section.stMain .stTextArea > div {{
    background: {f'url("{_note_b64}") no-repeat center/100% 100%' if _note_b64 else '#f5edc6'} !important;
    border: none !important;
    border-radius: 2px !important;
    box-shadow:
        0 6px 18px rgba(0, 0, 0, 0.08),
        0 2px 6px rgba(139, 105, 20, 0.12);
    padding: 0 !important;
    overflow: visible !important;
}}
section.stMain .stTextArea > div > div {{
    background: transparent !important;
    overflow: visible !important;
}}
section.stMain .stTextArea > div > div > textarea {{
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 52px 28px 36px 36px !important;
    min-height: 360px !important;
    font-family: 'Ma Shan Zheng', 'LiuJian Mao Cao', 'KaiTi', 'STKaiti', serif !important;
    font-size: 16px !important;
    line-height: 2.2 !important;
    color: var(--ink-dark) !important;
    box-shadow: none !important;
    outline: none !important;
    resize: vertical;
}}
section.stMain .stTextArea > div > div > textarea:focus {{
    outline: none !important;
    box-shadow: none !important;
}}
/* 只隐藏主区域的文本域标签 */
section.stMain .stTextArea label {{
    display: none !important;
}}

/* 装饰元素容器 */
.deco-wrapper {{
    position: relative;
    margin-bottom: -24px;
    z-index: 5;
}}
.deco-feather {{
    position: absolute;
    top: -38px;
    left: -50px;
    width: 110px;
    height: 140px;
    z-index: 10;
    pointer-events: none;
    filter: drop-shadow(2px 4px 6px rgba(0, 0, 0, 0.15));
}}
.deco-bookmark {{
    position: absolute;
    bottom: -22px;
    right: -8px;
    width: 100px;
    height: 60px;
    z-index: 10;
    pointer-events: none;
    filter: drop-shadow(2px 4px 6px rgba(0, 0, 0, 0.18));
}}

/* 隐藏原生占位提示中的滚动文字 */
.stTextArea small {{
    color: var(--ink-medium) !important;
    opacity: 0.6;
}}

/* ===== 来源输入：下划线风格（仅主区域） ===== */
section.stMain .stTextInput > div {{
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid var(--gold) !important;
    border-radius: 0 !important;
    padding: 6px 2px !important;
    box-shadow: none !important;
}}
section.stMain .stTextInput > div:hover {{
    border-bottom: 2px solid var(--gold) !important;
}}
section.stMain .stTextInput > div > div > input {{
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 4px 2px 4px 2px !important;
    font-family: 'Ma Shan Zheng', 'LiuJian Mao Cao', 'KaiTi', serif !important;
    font-size: 17px !important;
    color: var(--ink-dark) !important;
    box-shadow: none !important;
    outline: none !important;
    transition: all 0.3s ease;
}}
/* 保留侧边栏标签 */
section.stSidebar .stTextInput label {{
    display: block !important;
    color: var(--ink-medium) !important;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif !important;
    font-size: 14px !important;
}}
/* 只隐藏主区域的标签 */
section.stMain .stTextInput label {{
    display: none !important;
}}

/* ===== 文件上传：柔和羊皮纸 ===== */
.stFileUploader {{
    background: linear-gradient(160deg, #faf2e0 0%, #f3e5c8 100%) !important;
    border: 1px dashed var(--gold) !important;
    border-radius: 4px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06), inset 0 1px 3px rgba(139, 105, 20, 0.05);
    margin-top: 16px;
}}
.stFileUploader > section {{
    background: transparent !important;
}}
.stFileUploader p {{
    color: var(--ink-medium) !important;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif !important;
    font-size: 15px !important;
}}
.stFileUploader small {{
    color: var(--ink-medium) !important;
    opacity: 0.7;
}}
/* 隐藏主区域文件上传的原生标签（我们用自定义标签） */
section.stMain .stFileUploader label {{
    display: none !important;
}}
/* 文件上传标签自定义 */
.upload-label {{
    font-family: 'Ma Shan Zheng', 'LiuJian Mao Cao', 'KaiTi', serif;
    color: var(--ink-dark);
    font-size: 18px;
    letter-spacing: 3px;
    margin: 24px 0 4px 0;
    padding-left: 8px;
    border-left: 3px solid var(--gold);
    line-height: 1;
}}

/* ===== 按钮：烫金风格 ===== */
.stButton > button {{
    background: linear-gradient(145deg, var(--parchment-light) 0%, var(--parchment) 100%) !important;
    color: var(--ink-dark) !important;
    font-family: 'Ma Shan Zheng', 'LiuJian Mao Cao', 'KaiTi', serif !important;
    font-size: 18px !important;
    font-weight: 700 !important;
    padding: 14px 32px !important;
    border: 2px solid var(--gold) !important;
    border-radius: 6px !important;
    box-shadow:
        0 0 0 1px rgba(255, 248, 220, 0.8) inset,
        0 0 0 3px var(--gold-dark) inset,
        0 0 0 4px rgba(255, 248, 220, 0.5) inset,
        0 6px 20px rgba(139, 105, 20, 0.3),
        0 2px 4px rgba(0, 0, 0, 0.15);
    transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
    letter-spacing: 4px;
    position: relative;
}}
.stButton > button:hover {{
    background: linear-gradient(145deg, #fdf2dc 0%, var(--parchment-light) 100%) !important;
    box-shadow:
        0 0 0 1px rgba(255, 248, 220, 0.8) inset,
        0 0 0 3px var(--gold) inset,
        0 0 0 4px rgba(255, 248, 220, 0.5) inset,
        0 8px 25px rgba(139, 105, 20, 0.4),
        0 3px 6px rgba(0, 0, 0, 0.2);
    transform: translateY(-2px);
}}
.stButton > button:active {{
    transform: translateY(1px);
    box-shadow:
        0 0 0 1px rgba(255, 248, 220, 0.8) inset,
        0 0 0 3px var(--gold-dark) inset,
        0 2px 8px rgba(139, 105, 20, 0.3);
}}

/* ===== 侧边栏：卷轴背板 ===== */
.stSidebar {{
    background: linear-gradient(180deg, var(--parchment-light) 0%, var(--parchment) 50%, var(--parchment-dark) 100%) !important;
    border-right: 3px double var(--gold);
    box-shadow: inset -4px 0 10px rgba(139, 105, 20, 0.15);
}}
.stSidebar .stTextInput > div > div > input {{
    background: rgba(255, 248, 220, 0.6) !important;
    border: 1px solid var(--gold) !important;
    border-radius: 4px !important;
    padding: 8px 12px !important;
    font-family: inherit !important;
    box-shadow: inset 0 1px 3px rgba(139, 105, 20, 0.1) !important;
}}
.stSidebar h1, .stSidebar h2, .stSidebar h3 {{
    color: var(--ink-dark) !important;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif !important;
    border-bottom: 2px solid var(--gold);
    padding-bottom: 8px;
}}

/* ===== 标题：墨色书法 ===== */
h1 {{
    color: var(--ink-dark) !important;
    font-family: 'Ma Shan Zheng', 'LiuJian Mao Cao', 'KaiTi', serif !important;
    font-size: 42px !important;
    text-align: center !important;
    letter-spacing: 12px !important;
    text-shadow: 2px 2px 4px rgba(255, 248, 220, 0.8), 0 0 20px rgba(139, 105, 20, 0.2);
    margin-bottom: 20px !important;
    position: relative;
    padding: 16px 0;
}}
h1::before, h1::after {{
    content: '❈';
    color: var(--gold);
    font-size: 24px;
    margin: 0 20px;
    opacity: 0.6;
}}

h2, h3, h4 {{
    color: var(--ink-dark) !important;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif !important;
}}

/* ===== 文字与标签 ===== */
.stMarkdown, p, label, .stRadio label, .stSelectbox label {{
    color: var(--ink-medium) !important;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif !important;
}}
.stTextArea label, .stTextInput label, .stFileUploader label {{
    color: var(--ink-dark) !important;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif !important;
    font-size: 18px !important;
    font-weight: 400 !important;
    letter-spacing: 2px;
}}

/* ===== 分割线：金色装饰 ===== */
hr, .stDivider {{
    border: none !important;
    height: 2px !important;
    background: linear-gradient(90deg, transparent 0%, var(--gold-dark) 20%, var(--gold) 50%, var(--gold-dark) 80%, transparent 100%) !important;
    margin: 24px 0 !important;
    position: relative;
}}
hr::before {{
    content: '❖';
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    background: transparent;
    padding: 0 12px;
    color: var(--gold);
    font-size: 16px;
}}

/* ===== 信息提示框 ===== */
.stInfo {{
    background: linear-gradient(135deg, rgba(240, 223, 191, 0.95) 0%, rgba(247, 236, 212, 0.95) 100%) !important;
    border: 1px solid var(--gold) !important;
    border-left: 4px solid var(--seal-red) !important;
    border-radius: 4px !important;
    color: var(--ink-dark) !important;
}}

/* ===== 通用容器透明 ===== */
[data-testid="stVerticalBlock"] > div, .element-container {{
    background: transparent !important;
}}

/* ===== 复选框古风 ===== */
.stCheckbox input[type="checkbox"] {{
    accent-color: var(--seal-red);
}}

/* ===== 标签/徽章 ===== */
.stBadge {{
    background: var(--gold) !important;
    color: white !important;
    font-family: 'Ma Shan Zheng', serif !important;
}}

/* ===== 滚动条 ===== */
::-webkit-scrollbar {{
    width: 8px;
}}
::-webkit-scrollbar-track {{
    background: var(--parchment-dark);
    border-radius: 4px;
}}
::-webkit-scrollbar-thumb {{
    background: var(--gold);
    border-radius: 4px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: var(--gold-dark);
}}

{bg_css}

/* ===== 游戏抽卡 · 粒子流光动画 ===== */
@keyframes card-appear {{
    0% {{ opacity: 0; transform: scale(0.5) translateY(60px); filter: blur(20px); }}
    40% {{ opacity: 0.5; transform: scale(0.7) translateY(30px); filter: blur(10px); }}
    100% {{ opacity: 1; transform: scale(1) translateY(0); filter: blur(0); }}
}}
@keyframes glow-pulse {{
    0% {{ transform: scale(0.3); opacity: 1; }}
    50% {{ transform: scale(1.6); opacity: 0.3; }}
    100% {{ transform: scale(2.2); opacity: 0; }}
}}
@keyframes light-burst {{
    0% {{ transform: scale(0); opacity: 1; background: radial-gradient(circle, #fffbe6 0%, #ffd700 40%, #ff8c00 70%, transparent 100%); }}
    40% {{ transform: scale(1.3); opacity: 0.7; }}
    100% {{ transform: scale(1.8); opacity: 0; background: radial-gradient(circle, transparent 0%, transparent 100%); }}
}}
@keyframes light-burst-2 {{
    0% {{ transform: scale(0); opacity: 0.9; background: radial-gradient(circle, #fff8dc 0%, #ffec8b 50%, transparent 100%); }}
    50% {{ transform: scale(1.1); opacity: 0.5; }}
    100% {{ transform: scale(1.5); opacity: 0; }}
}}
@keyframes particle-float {{
    0% {{ transform: translateY(0) translateX(0) scale(1); opacity: 1; }}
    50% {{ transform: translateY(-30px) translateX(10px) scale(1.2); opacity: 0.8; }}
    100% {{ transform: translateY(-60px) translateX(-5px) scale(0.6); opacity: 0; }}
}}
@keyframes particle-spiral {{
    0% {{ transform: rotate(0deg) translateX(0) scale(1); opacity: 0; }}
    20% {{ opacity: 1; }}
    100% {{ transform: rotate(360deg) translateX(50px) scale(0.3); opacity: 0; }}
}}
@keyframes sparkle {{
    0%, 100% {{ opacity: 0; transform: scale(0); }}
    50% {{ opacity: 1; transform: scale(1); }}
}}
@keyframes shimmer {{
    0% {{ background-position: -200% center; }}
    100% {{ background-position: 200% center; }}
}}
@keyframes rotate-rays {{
    0% {{ transform: translate(-50%, -50%) rotate(0deg); }}
    100% {{ transform: translate(-50%, -50%) rotate(360deg); }}
}}
@keyframes floor-glow {{
    0%, 100% {{ opacity: 0.5; }}
    50% {{ opacity: 0.9; }}
}}

/* 卡片动画容器 */
.card-reveal-wrapper {{
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: 40px 20px;
    min-height: 600px;
}}
.card-reveal-wrapper .card-bg-layer {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 500px;
    height: 500px;
    border-radius: 50%;
    pointer-events: none;
}}
.card-reveal-wrapper .light-burst {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: radial-gradient(circle, #fffbe6 0%, #ffd700 40%, #ff8c00 70%, transparent 100%);
    animation: light-burst 2.2s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
    filter: blur(25px);
    pointer-events: none;
    z-index: 1;
}}
.card-reveal-wrapper .light-burst-2 {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 250px;
    height: 250px;
    border-radius: 50%;
    background: radial-gradient(circle, #fff8dc 0%, #ffb347 50%, transparent 100%);
    animation: light-burst-2 2.5s cubic-bezier(0.3, 0.7, 0.4, 1) 0.2s forwards;
    filter: blur(20px);
    pointer-events: none;
    z-index: 1;
}}
.card-reveal-wrapper .glow-ring {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 320px;
    height: 440px;
    border-radius: 20px;
    background: radial-gradient(ellipse at center, rgba(255, 215, 0, 0.45) 0%, rgba(255, 215, 0, 0.2) 30%, transparent 70%);
    animation: glow-pulse 2.0s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
    filter: blur(12px);
    pointer-events: none;
    z-index: 2;
}}
.card-reveal-wrapper .rotating-rays {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 500px;
    height: 500px;
    pointer-events: none;
    z-index: 2;
    animation: rotate-rays 6s linear 0.5s 3;
}}
.card-reveal-wrapper .rotating-rays .ray {{
    position: absolute;
    top: 50%;
    left: 50%;
    width: 2px;
    height: 250px;
    background: linear-gradient(to top, transparent 0%, rgba(255, 215, 0, 0.6) 30%, rgba(255, 215, 0, 0.1) 70%, transparent 100%);
    transform-origin: bottom center;
    border-radius: 50%;
}}
.card-reveal-wrapper .particle {{
    position: absolute;
    border-radius: 50%;
    pointer-events: none;
    z-index: 3;
}}
.card-reveal-wrapper .particle-float {{
    animation: particle-float 2.4s cubic-bezier(0.3, 0.7, 0.4, 1) forwards;
}}
.card-reveal-wrapper .particle-spiral {{
    animation: particle-spiral 2.8s cubic-bezier(0.3, 0.7, 0.4, 1) forwards;
}}
.card-reveal-wrapper .sparkle {{
    position: absolute;
    color: #ffd700;
    font-size: 18px;
    animation: sparkle 2.2s ease-in-out forwards;
    pointer-events: none;
    z-index: 4;
}}
.card-reveal-wrapper .card-image {{
    position: relative;
    z-index: 10;
    max-width: 500px;
    border-radius: 8px;
    box-shadow:
        0 0 30px rgba(255, 215, 0, 0.5),
        0 0 60px rgba(255, 140, 0, 0.3),
        0 12px 40px rgba(0, 0, 0, 0.4);
    animation: card-appear 2.0s cubic-bezier(0.22, 1, 0.36, 1) 0.3s forwards;
    opacity: 0;
}}
.card-reveal-wrapper .card-shimmer {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 500px;
    height: 700px;
    pointer-events: none;
    z-index: 11;
    opacity: 0;
    animation: card-appear 2.0s cubic-bezier(0.22, 1, 0.36, 1) 0.3s forwards;
}}
.card-reveal-wrapper .card-shimmer::after {{
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(
        105deg,
        transparent 0%,
        transparent 30%,
        rgba(255, 255, 255, 0.18) 45%,
        rgba(255, 255, 255, 0.4) 50%,
        rgba(255, 255, 255, 0.18) 55%,
        transparent 70%,
        transparent 100%
    );
    background-size: 200% 100%;
    animation: shimmer 3s ease-in-out 1.5s forwards;
    border-radius: 8px;
}}
.card-reveal-wrapper .title-banner {{
    position: relative;
    z-index: 12;
    margin-top: 20px;
    text-align: center;
    font-family: 'Ma Shan Zheng', 'KaiTi', serif;
    font-size: 22px;
    color: var(--gold);
    letter-spacing: 4px;
    opacity: 0;
    animation: card-appear 1.5s ease-out 1.8s forwards;
    text-shadow: 0 0 10px rgba(255, 215, 0, 0.6);
}}
.card-reveal-wrapper .floor-glow {{
    position: absolute;
    bottom: -20px;
    left: 50%;
    transform: translateX(-50%);
    width: 400px;
    height: 80px;
    background: radial-gradient(ellipse at center, rgba(255, 215, 0, 0.6) 0%, rgba(255, 140, 0, 0.3) 40%, transparent 70%);
    filter: blur(15px);
    pointer-events: none;
    z-index: 1;
    animation: floor-glow 3s ease-in-out 0.5s forwards;
    opacity: 0;
}}
</style>
""", unsafe_allow_html=True)

# ========================== 第四段三分之二：小精灵浮动展示区 ==========================
sprite_found = False

if _assets_dir.exists():
    # 优先使用处理后的透明小精灵
    sprite_candidates = [
        _assets_dir / "小精灵_透明.png",
        _assets_dir / "去背景小精灵.png",
        _assets_dir / "小精灵.png",
    ]
    sprite_path = next((p for p in sprite_candidates if p.exists()), None)
    
    if sprite_path:
        with open(sprite_path, "rb") as img_f:
            img_data = base64.b64encode(img_f.read()).decode()
        img_mime = sprite_path.suffix.lower().lstrip(".")
        if img_mime == "jpg":
            img_mime = "jpeg"
        
        st.markdown(f"""
        <div class="sprite-container">
            <img src="data:image/{img_mime};base64,{img_data}" class="sprite-img" alt="小精灵" />
        </div>
        """, unsafe_allow_html=True)
        sprite_found = True

if not sprite_found:
    st.info("🧚 小精灵图片未找到")


def show_card_with_particle_effect(card_image, title="知识卡片"):
    """
    展示游戏抽卡风格的全屏弹窗卡片
    - 使用 st.markdown 直接渲染，避免 iframe overflow 限制
    - 卡片图片通过 base64 嵌入到 img 标签中
    - 关闭按钮使用 Streamlit 原生按钮（CSS 定位到右上角）
    """
    # 初始化弹窗状态
    if "show_modal" not in st.session_state:
        st.session_state.show_modal = False
    
    # 如果弹窗未开启，移除 modal-active 类的效果并返回
    if not st.session_state.show_modal:
        st.markdown("""
        <style>
        body.modal-active::before { display: none !important; }
        body.modal-active [data-testid="stSidebar"] { display: block !important; }
        body.modal-active header { display: flex !important; }
        </style>
        """, unsafe_allow_html=True)
        return
    
    # ========== 0. 添加 modal-active 类到 body（用于隐藏侧边栏和 header） ==========
    # 使用 components.html 因为 st.markdown 会过滤 script 标签
    components.html("""
    <!DOCTYPE html>
    <html>
    <body>
    <script>
    (function() {
        try {
            var parentDoc = window.parent.document || window.top.document || document;
            if (parentDoc && parentDoc.body) {
                parentDoc.body.classList.add('modal-active');
            }
        } catch(e) {
            document.body.classList.add('modal-active');
        }
    })();
    </script>
    </body>
    </html>
    """, height=1)
    
    # ========== 1. 全屏遮罩和关闭按钮样式 ==========
    st.markdown("""
    <style>
    /* 全屏遮罩 */
    body.modal-active::before {
        content: '';
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: rgba(0, 0, 0, 0.9);
        z-index: 99998;
    }
    body.modal-active [data-testid="stSidebar"] { display: none !important; }
    body.modal-active header { display: none !important; }
    body.modal-active [data-testid="stAppViewContainer"] { padding-top: 0 !important; }
    
    /* 关闭按钮容器 - 固定在右上角 */
    .st-key-close_modal_btn {
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        left: auto !important;
        z-index: 100000 !important;
        margin: 0 !important;
        padding: 0 !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    
    /* 关闭按钮样式 */
    .st-key-close_modal_btn button {
        width: 56px !important;
        min-width: 56px !important;
        height: 56px !important;
        border-radius: 50% !important;
        background: linear-gradient(135deg, #ffd700 0%, #ff8c00 100%) !important;
        border: 3px solid rgba(255,215,0,0.9) !important;
        color: #fff !important;
        font-size: 24px !important;
        font-weight: bold !important;
        box-shadow: 0 4px 20px rgba(255,215,0,0.6), 0 0 30px rgba(255,140,0,0.4) !important;
        transition: all 0.3s ease !important;
        padding: 0 !important;
        margin: 0 !important;
        animation: closeBtnPulse 2s ease-in-out infinite !important;
    }
    .st-key-close_modal_btn button:hover {
        transform: scale(1.15) !important;
        box-shadow: 0 6px 35px rgba(255,215,0,0.8), 0 0 45px rgba(255,140,0,0.6) !important;
    }
    @keyframes closeBtnPulse {
        0%, 100% { box-shadow: 0 4px 20px rgba(255,215,0,0.6), 0 0 30px rgba(255,140,0,0.4); }
        50% { box-shadow: 0 4px 20px rgba(255,215,0,0.9), 0 0 45px rgba(255,140,0,0.6); }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # ========== 2. 关闭按钮 ==========
    if st.button("✕", key="close_modal_btn", help="点击关闭弹窗", 
                 type="primary", use_container_width=False):
        st.session_state.show_modal = False
        st.rerun()
    
    # ========== 3. 卡片弹窗内容（使用 st.markdown 直接渲染，不使用 iframe） ==========
    
    import io
    buf = io.BytesIO()
    card_image.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    import random
    random.seed(42)

    # 生成下落粒子
    falling_particles = ""
    for i in range(80):
        x = random.randint(-300, 300)
        start_y = random.randint(-600, -200)
        end_y = random.randint(-100, 300)
        size = random.randint(4, 10)
        delay = round(random.uniform(0, 4), 2)
        dur = round(random.uniform(3, 5), 1)
        drift_x = round(random.uniform(-60, 60), 0)
        colors = ['#ffd700', '#ffb347', '#fffbe6', '#ff8c00', '#ffe55c', '#fff8dc']
        color = random.choice(colors)
        falling_particles += f'<div class="fp" style="--sx:{start_y}px;--ex:{drift_x}px;--ey:{end_y}px;left:calc(50% + {x}px);width:{size}px;height:{size}px;background:{color};box-shadow:0 0 {size*4}px {color};animation-delay:{delay}s;animation-duration:{dur}s"></div>'

    # 生成环绕粒子
    orbit_particles = ""
    for i in range(30):
        angle = (i / 30) * 360
        radius = random.randint(200, 260)
        size = random.randint(5, 10)
        colors = ['#ffd700', '#ffb347', '#fffbe6', '#ffe55c']
        color = random.choice(colors)
        orbit_particles += f'<div class="op" style="--angle:{angle}deg;--r:{radius}px;width:{size}px;height:{size}px;background:{color};box-shadow:0 0 {size*3}px {color};"></div>'

    # 闪光星星
    sparkle_html = ""
    for s in range(20):
        x = random.randint(-250, 250)
        y = random.randint(-300, 300)
        delay = round(random.uniform(0, 4), 2)
        size = random.randint(14, 32)
        sparkle_html += f'<div class="sparkle" style="left:calc(50% + {x}px);top:calc(50% + {y}px);animation-delay:{delay}s;font-size:{size}px">✦</div>'

    # 旋转光线
    rays_html = ""
    for r in range(24):
        rays_html += f'<div class="ray" style="--ray-angle:{r * 15}deg"></div>'

    # 预生成 idle 粒子
    idle_particles_html = ""
    for i in range(40):
        x = round(random.uniform(-250, 250), 0)
        y = round(random.uniform(-320, 320), 0)
        dur = round(random.uniform(3, 8), 1)
        delay = round(random.uniform(0, 6), 1)
        size = random.randint(4, 8)
        hue = '#ffd700' if random.random() > 0.3 else '#ffb347'
        idle_particles_html += f'<div class="ip" style="left:calc(50% + {x}px);top:calc(50% + {y}px);width:{size}px;height:{size}px;background:{hue};box-shadow:0 0 {size*3}px {hue}, 0 0 {size*6}px rgba(255,180,71,0.4);animation-duration:{dur}s;animation-delay:{delay}s"></div>'

    # 完整的卡片弹窗 HTML（使用 st.markdown 直接渲染）
    modal_html = f"""
    <style>
    /* 弹窗容器 - 全屏固定定位 */
    .card-modal {{
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: radial-gradient(ellipse at center, rgba(20,10,5,0.95) 0%, rgba(10,5,2,0.99) 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 99999;
        overflow: visible;
    }}

    /* 舞台容器 - 定位卡片和粒子 */
    .card-stage {{
        position: relative;
        width: 600px;
        height: 800px;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    /* 中心光晕爆发 */
    .burst {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%,-50%);
        width: 360px; height: 360px;
        border-radius: 50%;
        background: radial-gradient(circle, #fffbe6 0%, #ffd700 30%, #ff8c00 60%, transparent 100%);
        filter: blur(35px);
        z-index: 1;
        opacity: 0;
        animation: burstAnim 2.5s cubic-bezier(0.2,0.8,0.2,1) forwards;
    }}
    .burst-2 {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%,-50%);
        width: 280px; height: 280px;
        border-radius: 50%;
        background: radial-gradient(circle, #fff8dc 0%, #ffb347 50%, transparent 100%);
        filter: blur(28px);
        z-index: 1;
        opacity: 0;
        animation: burstAnim2 3s cubic-bezier(0.3,0.7,0.4,1) 0.2s forwards;
    }}

    /* 卡片光晕 */
    .glow {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%,-50%);
        width: 380px; height: 500px;
        border-radius: 16px;
        background: radial-gradient(ellipse at center, rgba(255,215,0,0.5) 0%, rgba(255,215,0,0.25) 30%, transparent 70%);
        filter: blur(18px);
        z-index: 2;
        opacity: 0;
        animation: glowAnim 2.2s cubic-bezier(0.2,0.8,0.2,1) forwards;
    }}

    /* 旋转光线 */
    .rays {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%,-50%);
        width: 600px; height: 600px;
        pointer-events: none;
        z-index: 3;
        opacity: 0;
        animation: raysFade 0.5s ease forwards, spin 8s linear 0.5s 2;
    }}
    .rays .ray {{
        position: absolute;
        top: 50%; left: 50%;
        width: 2px; height: 300px;
        background: linear-gradient(to top, transparent 0%, rgba(255,215,0,0.7) 20%, rgba(255,215,0,0.15) 60%, transparent 100%);
        transform-origin: bottom center;
        transform: translateX(-50%) rotate(var(--ray-angle));
    }}

    /* 下落粒子 */
    .fp {{
        position: absolute;
        border-radius: 50%;
        pointer-events: none;
        z-index: 5;
        opacity: 0;
        animation: fallingP var(--dur,3s) cubic-bezier(0.3,0.7,0.4,1) forwards;
    }}

    /* 环绕粒子 */
    .op {{
        position: absolute;
        top: 50%; left: 50%;
        border-radius: 50%;
        pointer-events: none;
        z-index: 4;
        opacity: 0;
        animation: orbitP 4s cubic-bezier(0.3,0.7,0.4,1) forwards;
    }}

    /* 闪光星星 */
    .sparkle {{
        position: absolute;
        color: #ffd700;
        pointer-events: none;
        z-index: 6;
        opacity: 0;
        animation: sparkleAnim 2.5s ease-in-out forwards;
        text-shadow: 0 0 10px #ffd700, 0 0 20px #ffb347;
    }}

    /* 卡片图片样式 */
    .card-img {{
        position: relative;
        z-index: 10;
        width: 420px;
        border-radius: 12px;
        box-shadow: 0 0 40px rgba(255,215,0,0.6), 0 0 80px rgba(255,140,0,0.4), 0 16px 50px rgba(0,0,0,0.8);
    }}

    /* 闪光扫过效果 */
    .shimmer {{
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%,-50%);
        width: 420px; height: 560px;
        pointer-events: none;
        z-index: 11;
        opacity: 0;
        border-radius: 12px;
        overflow: hidden;
    }}
    .shimmer::after {{
        content: '';
        position: absolute;
        top: -50%; left: -50%;
        width: 200%; height: 200%;
        background: linear-gradient(105deg, transparent 0%, transparent 35%, rgba(255,255,255,0.2) 45%, rgba(255,255,255,0.5) 50%, rgba(255,255,255,0.2) 55%, transparent 65%, transparent 100%);
        background-size: 200% 100%;
        animation: shimmerMove 3.5s ease-in-out 2s forwards;
    }}

    /* 地面光晕 */
    .floor {{
        position: absolute;
        bottom: 20px; left: 50%;
        transform: translateX(-50%);
        width: 380px; height: 60px;
        background: radial-gradient(ellipse at center, rgba(255,215,0,0.6) 0%, rgba(255,215,0,0.2) 40%, transparent 70%);
        filter: blur(20px);
        z-index: 9;
        opacity: 0;
        animation: floorAnim 3s ease-out 0.8s forwards;
    }}

    /* 标题 */
    .card-title {{
        position: absolute;
        bottom: -60px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 12;
        text-align: center;
        font-family: 'Ma Shan Zheng', 'KaiTi', 'STKaiti', serif;
        font-size: 28px;
        color: #ffd700;
        letter-spacing: 8px;
        white-space: nowrap;
        opacity: 0;
        animation: titleAnim 1.5s ease-out 2s forwards;
        text-shadow: 0 0 15px rgba(255,215,0,0.8), 0 0 30px rgba(255,140,0,0.5);
    }}

    /* 持续飘浮粒子 */
    .idle-particles {{
        position: absolute;
        top: 50%; left: 50%;
        width: 500px; height: 600px;
        pointer-events: none;
        z-index: 4;
        opacity: 0;
        animation: idleFadeIn 1s ease 4s forwards;
    }}
    .idle-particles .ip {{
        position: absolute;
        border-radius: 50%;
        animation: idleFloat var(--dur,4s) ease-in-out infinite var(--delay,0s);
    }}

    /* 动画关键帧 */
    @keyframes burstAnim {{ 0%{{transform:translate(-50%,-50%) scale(0.2);opacity:1;}} 60%{{transform:translate(-50%,-50%) scale(1.4);opacity:0.6;}} 100%{{transform:translate(-50%,-50%) scale(2.0);opacity:0;}} }}
    @keyframes burstAnim2 {{ 0%{{transform:translate(-50%,-50%) scale(0);opacity:0.9;}} 50%{{transform:translate(-50%,-50%) scale(1.2);opacity:0.5;}} 100%{{transform:translate(-50%,-50%) scale(1.8);opacity:0;}} }}
    @keyframes glowAnim {{ 0%{{transform:translate(-50%,-50%) scale(0.5);opacity:1;}} 50%{{transform:translate(-50%,-50%) scale(1.3);opacity:0.4;}} 100%{{transform:translate(-50%,-50%) scale(1.8);opacity:0;}} }}
    @keyframes raysFade {{ 0%{{opacity:0;}} 20%{{opacity:1;}} 100%{{opacity:0;}} }}
    @keyframes spin {{ 0%{{transform:translate(-50%,-50%) rotate(0deg);}} 100%{{transform:translate(-50%,-50%) rotate(360deg);}} }}
    @keyframes fallingP {{ 0%{{opacity:0;transform:translateY(var(--sx)) scale(0.5);}} 15%{{opacity:1;}} 85%{{opacity:0.8;}} 100%{{opacity:0;transform:translate(var(--ex), var(--ey)) scale(0.3);}} }}
    @keyframes orbitP {{ 0%{{opacity:0;transform:rotate(var(--angle)) translateX(0) scale(0.3);}} 20%{{opacity:1;}} 80%{{opacity:0.6;}} 100%{{opacity:0;transform:rotate(var(--angle)) translateX(var(--r)) scale(0.5);}} }}
    @keyframes sparkleAnim {{ 0%,100%{{opacity:0;transform:scale(0);}} 30%{{opacity:1;transform:scale(1.3);}} 50%{{opacity:0.8;transform:scale(1);}} 70%{{opacity:1;transform:scale(1.2);}} }}
    @keyframes shimmerMove {{ 0%{{background-position:-200% center;}} 100%{{background-position:200% center;}} }}
    @keyframes floorAnim {{ 0%,100%{{opacity:0;}} 40%{{opacity:0.8;}} 80%{{opacity:0.6;}} }}
    @keyframes titleAnim {{ 0%{{opacity:0;transform:translateX(-50%) translateY(20px);}} 100%{{opacity:1;transform:translateX(-50%) translateY(0);}} }}
    @keyframes idleFadeIn {{ 0%{{opacity:0;}} 100%{{opacity:0.7;}} }}
    @keyframes idleFloat {{ 0%,100%{{transform:translate(0,0);}} 25%{{transform:translate(6px,-10px);}} 50%{{transform:translate(-4px,-18px);}} 75%{{transform:translate(-8px,-6px);}} }}
    </style>

    <div class="card-modal">
        <div class="card-stage">
            <div class="burst"></div>
            <div class="burst-2"></div>
            <div class="glow"></div>
            <div class="rays">
                {rays_html}
            </div>
            {orbit_particles}
            {falling_particles}
            {sparkle_html}
            <img src="data:image/png;base64,{img_b64}" class="card-img" alt="{title}" />
            <div class="shimmer"></div>
            <div class="floor"></div>
            <div class="idle-particles">
                {idle_particles_html}
            </div>
            <div class="card-title">✦ {title} ✦</div>
        </div>
    </div>
    """
    
    # 使用 st.markdown 直接渲染卡片弹窗（避免 iframe overflow 限制）
    st.markdown(modal_html, unsafe_allow_html=True)
    
    # 停止页面继续渲染（防止弹窗下面显示主界面内容）
    st.stop()


# ========================== 第五段：左侧边栏（设置面板） ==========================

# with st.sidebar 意思是"以下内容放在页面左侧的边栏里"
with st.sidebar:
    # ---------- 边栏标题 ----------
    st.header("⚙️ 设置")  # 👆 边栏的标题

    # ---------- API Key 输入框（密码框） ----------
    api_key = st.text_input(
        "Dify API Key",
        # 👆 输入框上方的标签
        value=_get_config("DIFY_API_KEY", ""),
        # 👆 默认值：从 .env 文件读取（如果配置了的话）
        type="password",
        # 👆 密码框：输入的内容会显示成 ••••••，防止别人偷看
        help="在 Dify 应用的「API 密钥」中获取",
        # 👆 鼠标悬停时显示的小提示
    )

    # ---------- Dify 服务器地址 ----------
    base_url = st.text_input(
        "Dify API 地址",
        value=_get_config("DIFY_API_URL", "https://api.dify.ai/v1"),
        # 👆 默认用 Dify 云端地址
    )

    # ---------- 工作流输入变量名 ----------
    input_key = st.text_input(
        "输入变量名",
        value=_get_config("DIFY_INPUT_KEY", "user_query"),
        # 👆 默认值。注意：不同 Dify 工作流的输入变量名可能不同
        help="工作流的起始输入变量名（在 Dify 工作流编辑器中查看）",
    )

    # ---------- 用户 ID ----------
    user_id = st.text_input(
        "用户 ID",
        value=_get_config("DIFY_USER_ID", "test-user"),
    )

    # ---------- 分割线 ----------
    st.divider()  # 👆 画一条水平线，把不同的功能区隔开

    # ---------- "测试连接"按钮 ----------
    if st.button("🧪 测试连接", use_container_width=True):
        # 👆 创建一个按钮，用户点击时下面缩进的代码会执行
        # use_container_width=True 让按钮撑满整行宽度

        if not api_key:
            # 如果 API Key 是空的
            st.error("请先填写 API Key")  # 👆 显示红色错误提示
        else:
            try:
                # ---------- 创建 DifyClient 并测试连接 ----------
                client = DifyClient(
                    api_key=api_key,  # 👆 用你填的密钥
                    base_url=base_url,  # 👆 用你填的地址
                    user_id=user_id,  # 👆 用你填的用户 ID
                    input_key=input_key,  # 👆 用你填的变量名
                )

                # with st.spinner("xxx") 会在代码执行期间显示一个旋转的加载动画
                with st.spinner("正在连接..."):
                    result = client.get_application_info()
                    # 👆 就像打电话："喂？在吗？"

                # ---------- 判断连接结果 ----------
                if result["success"]:
                    st.success("✅ 连接成功！")  # 👆 绿色成功提示
                    with st.expander("查看应用信息"):
                        # 👆 st.expander 创建一个可折叠的区域
                        st.json(result["data"])  # 👆 以好看的格式显示 JSON
                else:
                    st.error(f"❌ 连接失败: {result.get('error', '未知错误')}")
                    # 👆 红色错误提示
            except Exception as e:
                st.error(f"❌ 异常: {str(e)}")


# ========================== 第六段：主区域（输入和生成） ==========================

# ---------- 羽毛笔装饰（左上角） ----------
if _feather_b64:
    st.markdown(f"""
    <div class="deco-wrapper" style="position:relative;margin-bottom:-16px;">
      <img src="{_feather_b64}" class="deco-feather" alt="羽毛笔" />
    </div>
    """, unsafe_allow_html=True)

# ---------- 文本域（便利贴风格） ----------
input_text = st.text_area(
    "文本",
    height=160,
    placeholder="输入你喜欢的文字...",
)

# ---------- 书签装饰（右下角） ----------
if _bookmark_b64:
    st.markdown(f"""
    <div style="position:relative;margin-top:-18px;margin-bottom:4px;">
      <img src="{_bookmark_b64}" class="deco-bookmark" alt="书签" />
    </div>
    """, unsafe_allow_html=True)

# ---------- 来源输入（图二风格：下划线 + 标签在上方） ----------
st.markdown("""
<div style="margin: 18px 0 2px 0; padding-left: 4px;">
  <span style="font-family:'Ma Shan Zheng','KaiTi',serif; color:#2c1810; font-size:15px; letter-spacing:2px;">
    来源（可选）
  </span>
</div>
""", unsafe_allow_html=True)

source = st.text_input(
    "来源（可选）",
    placeholder="书名 / 文章名 / 视频名",
)

# ---------- 背景图上传 ----------
st.markdown("""
<div style="margin: 20px 0 2px 0; padding-left: 4px;">
  <span style="font-family:'Ma Shan Zheng','KaiTi',serif; color:#2c1810; font-size:15px; letter-spacing:2px;">
    选择背景图（可选，不上传则随机使用背景库）
  </span>
</div>
""", unsafe_allow_html=True)

uploaded_bg = st.file_uploader(
    "选择背景图（可选，不上传则随机使用背景库）",
    type=["jpg", "jpeg", "png", "webp"],
    help="上传一张你喜欢的图片作为卡片背景",
)
save_to_library = False
if uploaded_bg is not None:
    save_to_library = st.checkbox(
        "保存到背景库（以后可能随机用到）",
        value=False,
    )
    st.image(uploaded_bg, caption="背景图预览", width=250)

# ---------- 生成卡片按钮 ----------
st.markdown('<div style="margin-top: 28px;"></div>', unsafe_allow_html=True)
generate_btn = st.button("✦ 生 成 卡 片 ✦", type="primary", use_container_width=True)

st.markdown('<div style="text-align:center; margin: 20px 0; color: var(--gold); font-size: 18px; letter-spacing: 16px;">❈ ❈ ❈</div>', unsafe_allow_html=True)

# ========================== 第七段：核心逻辑 —— 调用 Dify 并展示结果 ==========================

if generate_btn:  # 👆 只有当用户点了"生成卡片"按钮时，才执行下面的代码
    # ---------- 安全检查1：有没有输入文字 ----------
    if not input_text.strip():
        # .strip() 去掉首尾空格后，如果是空的 → 用户没输入
        st.warning("⚠️ 请先输入文本")  # 👆 黄色警告提示
    # ---------- 安全检查2：API Key 检查已禁用（使用固定数据模式） ----------
    # elif not api_key:
    #     st.warning("⚠️ 请先在左侧填写 API Key")
    # else:
    #     # ---------- 创建 Dify 客户端（已禁用） ----------
    #     client = DifyClient(
    #         api_key=api_key,
    #         base_url=base_url,
    #         user_id=user_id,
    #         input_key=input_key,
    #     )
    #
    #     # ---------- 打包输入数据 ----------
    #     inputs = {input_key: input_text}
    #     if source:
    #         inputs["source"] = source
    #
    #     status_placeholder = st.empty()
    #     st.info(f"调试：input_key={input_key}, 模式=Dify 工作流调用")
    #     status_placeholder.info("🤖 正在生成卡片...")
    #
    #     workflow_outputs = {}
    #     card_data = {}
    #     extract_mode = ""
    #     workflow_id = ""
    #
    #     # ========== 调用 Dify 工作流（已禁用，节省 tokens） ==========
    #     for event in client.run_workflow_streaming(inputs=inputs):
    #         event_type = event.get("event", "")
    #         if event_type == "error":
    #             status_placeholder.empty()
    #             st.error(f"❌ 生成失败: {event.get('message', '未知错误')}")
    #             if "status_code" in event:
    #                 st.write(f"**状态码**: {event['status_code']}")
    #             break
    #         elif event_type == "workflow_started":
    #             workflow_id = event.get("workflow_run_id", "")
    #             status_placeholder.info(f"🚀 工作流已启动 (ID: {workflow_id[:8]}...)")
    #         elif event_type == "node_started":
    #             node_title = event.get("data", {}).get("title", "")
    #             status_placeholder.info(f"⏳ 执行中: {node_title}...")
    #         elif event_type == "node_finished":
    #             node_title = event.get("data", {}).get("title", "")
    #             status_placeholder.success(f"✅ 完成: {node_title}")
    #         elif event_type == "workflow_finished":
    #             raw_data = event.get("data") or {}
    #             workflow_outputs = raw_data.get("outputs") or {}
    #             card_data, extract_mode = _extract_card_data_from_outputs(workflow_outputs)
    #             status_placeholder.empty()
    #             if extract_mode != "empty":
    #                 field_count = len(card_data)
    #                 st.success(f"✅ 生成完成！提取模式：{extract_mode}，共 {field_count} 个字段")
    #             else:
    #                 st.warning("⚠️ 未提取到输出内容")
    #                 with st.expander("🔍 调试：workflow_finished 原始事件"):
    #                     st.json(event)
    #         elif event_type == "ping":
    #             pass

    # ===== 使用固定卡片数据（跳过 Dify API 调用，节省 tokens） =====
    card_data = {
        "title": "偶然表象下的必然积累",
        "quote": "真的猛士，敢于直面惨淡的人生，敢于正视淋漓的鲜血。——《记念刘和珍君》",
        "source_quote": "世界上只有一种真正的英雄主义，那就是在认清生活的真相后依然热爱生活。——罗曼·罗兰",
        "summary": "成功并非纯粹的运气博弈，而是持续行动与因果律的精确兑现。",
        "book": "《纳瓦尔宝典》",
        "movie": "《肖申克的救赎》",
        "keywords": "运气、长期主义、因果律、持续行动",
    }
    extract_mode = "fixed"
    workflow_outputs = {}
    workflow_id = ""
    st.success("✅ 卡片数据已就绪（固定数据模式）")

    # ===== 循环结束，展示最终结果 =====

    # ---------- 判断 card_data 是否包含有效的卡片字段 ----------
    # 有效字段：title、quote、summary 中的至少一个
    card_field_names = {"title", "quote", "summary"}
    has_card_fields = bool(card_field_names & set(card_data.keys()))
    # 👆 取交集：card_data 的 key 中有多少个是有效的卡片字段名

    if card_data and has_card_fields:
        # ---------- 有卡片数据：生成并展示图片 ----------
        st.subheader("🖼️ 生成的卡片")

        # ===== 调试面板：查看数据链路每一步 =====
        with st.expander("🔍 调试：查看数据链路"):
            tab1, tab2, tab3 = st.tabs(["Dify Outputs", "提取模式", "Card Data"])

            with tab1:
                st.caption("Dify 工作流返回的原始 outputs：")
                st.json(workflow_outputs)
                # 👆 看看 Dify 到底输出了哪些变量，叫什么名字

            with tab2:
                st.caption(f"提取模式：**{extract_mode}**")
                if extract_mode == "multi_field":
                    st.info("""
                    **多字段模式**：Dify 工作流把 title、quote、summary、book、movie
                    等字段作为独立的输出变量。前端会自动把它们合并成卡片数据。
                    """)
                elif extract_mode == "single_json":
                    st.info("""
                    **单 JSON 模式**：Dify 工作流把整个卡片设计打包成一个 JSON 字符串输出。
                    前端解析这个 JSON 得到卡片数据。
                    """)
                else:
                    st.warning(f"未知模式: {extract_mode}")

            with tab3:
                st.json(card_data)
                # 👆 最终用来生成图片的数据

        # ===== 生成图片 =====
        try:
            # ===== 处理自定义背景图 =====
            custom_bg = None  # 👈 默认 None → 走随机背景逻辑
            if uploaded_bg is not None:
                # 把上传的文件读成 PIL 图片对象
                custom_bg = Image.open(uploaded_bg)
                # 如果用户勾选了"保存到背景库"，就把图片存到 backgrounds 文件夹
                if save_to_library:
                    # 生成不重复的文件名：user_ + 时间戳 + 原后缀
                    bg_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    bg_suffix = Path(uploaded_bg.name).suffix.lower() or ".jpg"
                    bg_filename = f"user_{bg_timestamp}{bg_suffix}"
                    bg_save_path = BACKGROUNDS_DIR / bg_filename
                    # 保存到背景库（转成 RGB 避免透明通道导致 jpg 保存报错）
                    custom_bg.convert("RGB").save(bg_save_path)
                    st.info(f"💾 背景图已保存到背景库: {bg_filename}")

            with st.spinner("🎨 正在渲染卡片图片..."):
                # 生成卡片图片（传入 custom_bg；为 None 时自动走随机背景）
                card_image = generate_card_image(card_data, custom_bg=custom_bg)

            # ===== 保存图片到本地 =====
            # 生成安全的文件名（去掉特殊字符）
            title_for_filename = re.sub(r'[\\/:*?"<>|]', '', card_data.get("title", "知识卡片"))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{title_for_filename}_{timestamp}.png"
            image_path = GENERATED_DIR / image_filename
            card_image.save(image_path, format="PNG")

            # ===== 保存卡片到数据库 =====
            db = get_db()
            card_id = db.save_card(card_data, str(image_path))
            st.success(f"✅ 卡片已保存到卡片书（ID: {card_id}）")

            # ===== 展示卡片（带炫酷粒子流光动画） =====
            # 设置弹窗状态为显示
            st.session_state.show_modal = True
            show_card_with_particle_effect(
                card_image,
                title=card_data.get("title", "知识卡片"),
            )

            # ===== 下载按钮 =====
            buf = io.BytesIO()
            card_image.save(buf, format="PNG")
            buf.seek(0)

            download_filename = f"{card_data.get('title', '知识卡片')}.png"
            st.download_button(
                label="📥 下载卡片图片",
                data=buf.getvalue(),
                file_name=download_filename,
                mime="image/png",
                use_container_width=True,
            )

        except Exception as img_error:
            st.error(f"❌ 图片生成失败: {str(img_error)}")
            st.warning("回退为 JSON 展示：")
            st.json(card_data)

    elif card_data:
        # ---------- card_data 有内容但缺少有效卡片字段（如只有 raw_text） ----------
        st.warning("⚠️ 输出数据缺少卡片字段（title/quote/summary），以原始数据展示：")
        with st.expander("🔍 调试：查看原始数据"):
            st.caption("Dify 原始 outputs：")
            st.json(workflow_outputs)
            st.caption("提取后的 card_data：")
            st.json(card_data)
        raw_text = card_data.get("raw_text", json.dumps(card_data, ensure_ascii=False))
        st.markdown(raw_text)

    else:
        # ---------- 完全没内容 ----------
        st.warning("⚠️ 工作流完成但未返回任何内容，请检查 Dify 工作流配置")
        with st.expander("🔍 调试：workflow_outputs"):
            st.json(workflow_outputs)

    # ---------- 显示工作流 ID（方便追踪） ----------
    if workflow_id:
        st.caption(f"工作流 ID: `{workflow_id}`")

# ========================== 第八段：卡片书页面 ==========================

st.divider()
st.subheader("📚 我的卡片书")

# ---------- 获取数据库实例 ----------
db = get_db()

# ---------- 处理删除操作（放在卡片列表渲染之前） ----------
if "delete_card_id" in st.session_state:
    db.delete_card(st.session_state["delete_card_id"])
    del st.session_state["delete_card_id"]
    st.rerun()

# ---------- 搜索和筛选控制 ----------
search_col1, search_col2, search_col3 = st.columns([3, 1, 1])
with search_col1:
    search_keyword = st.text_input("🔍 搜索卡片", placeholder="输入关键词搜索...", key="card_search")
with search_col2:
    view_mode = st.selectbox("📋 查看方式", ["📂 按主题分组", "🔲 平铺展示"])
with search_col3:
    batch_mode = st.checkbox("🗑️ 批量管理", key="batch_mode")
    # 👆 勾选后进入批量管理模式，可以批量选择和删除卡片

# ---------- 初始化批量选择的卡片 ID 列表 ----------
if "selected_card_ids" not in st.session_state:
    st.session_state["selected_card_ids"] = []

# ---------- 获取标签统计（用于标签筛选） ----------
all_tags = db.get_all_tags()
# 👆 获取所有标签及其使用次数

# ---------- 初始化选中标签列表 ----------
selected_tags = []
# 👆 先初始化为空列表，后面根据 checkbox 选择更新

# ---------- 标签筛选区 ----------
if all_tags:
    st.markdown("### 🏷️ 标签筛选")
    
    # 显示热门标签（最多显示 15 个）
    tag_cols = st.columns(5)
    
    for idx, tag_info in enumerate(all_tags[:15]):
        tag = tag_info["tag"]
        count = tag_info["count"]
        col = tag_cols[idx % 5]
        
        # 用 checkbox 实现标签筛选
        if col.checkbox(f"{tag} ({count})", key=f"tag_{tag}"):
            selected_tags.append(tag)
    
    if selected_tags:
        st.caption(f"已选标签: {', '.join(selected_tags)}")

# ---------- 获取筛选后的卡片 ----------
if view_mode == "📂 按主题分组":
    # 获取按风格分组的卡片
    grouped_cards = db.get_cards_grouped_by_style(
        keyword=search_keyword if search_keyword else "",
        tags=selected_tags
    )
    
    # 显示筛选结果
    total_filtered = sum(len(cards) for cards in grouped_cards.values())
    st.caption(f"找到 {total_filtered} 张卡片，分布在 {len(grouped_cards)} 个主题中")
    
    if grouped_cards:
        # 风格图标映射
        style_icons = {
            "healing": "🏥",
            "philosophy": "🧘",
            "inspiration": "💪",
            "eastern": "☯️",
            "minimal": "⚪",
            "elegant": "✨",
        }
        
        # 批量操作栏
        if batch_mode:
            batch_col1, batch_col2 = st.columns([2, 1])
            with batch_col1:
                st.info(f"已选择 {len(st.session_state['selected_card_ids'])} 张卡片")
            with batch_col2:
                if st.button("✅ 全选", use_container_width=True):
                    # 获取所有卡片 ID
                    all_ids = []
                    for cards in grouped_cards.values():
                        all_ids.extend([c['id'] for c in cards])
                    st.session_state["selected_card_ids"] = all_ids
                    st.rerun()
            
            # 批量删除按钮
            if st.button(f"🗑️ 批量删除 {len(st.session_state['selected_card_ids'])} 张", 
                        disabled=len(st.session_state['selected_card_ids']) == 0,
                        type="primary",
                        use_container_width=True):
                if st.session_state['selected_card_ids']:
                    deleted = db.batch_delete_cards(st.session_state['selected_card_ids'])
                    st.success(f"已删除 {deleted} 张卡片")
                    st.session_state["selected_card_ids"] = []
                    st.rerun()
        
        # 按主题分组展示
        for style, cards in grouped_cards.items():
            icon = style_icons.get(style, "📁")
            with st.expander(f"{icon} {style} ({len(cards)}张)"):
                # 每行显示 3 张卡片
                cols = st.columns(3)
                for idx, card in enumerate(cards):
                    with cols[idx % 3]:
                        # 批量选择复选框
                        if batch_mode:
                            is_selected = card['id'] in st.session_state['selected_card_ids']
                            if st.checkbox(f"选择 ID:{card['id']}", value=is_selected, 
                                        key=f"select_{card['id']}"):
                                if card['id'] not in st.session_state['selected_card_ids']:
                                    st.session_state['selected_card_ids'].append(card['id'])
                            else:
                                if card['id'] in st.session_state['selected_card_ids']:
                                    st.session_state['selected_card_ids'].remove(card['id'])
                        
                        # 显示卡片图片（如果有）
                        if card.get("card_image_path") and os.path.exists(card["card_image_path"]):
                            st.image(
                                card["card_image_path"],
                                caption=card.get("title", "知识卡片"),
                                width="stretch",
                            )
                        else:
                            # 如果没有图片，显示文字卡片
                            st.write(f"**{card.get('title', '无标题')}**")
                            st.write(f"📝 {card.get('quote', '')[:30]}...")
                        
                        # 显示详情
                        with st.expander(f"详情 (ID: {card['id']})"):
                            st.write(f"**标题**: {card.get('title', '')}")
                            st.write(f"**金句**: {card.get('quote', '')}")
                            if card.get('source_quote'):
                                st.write(f"**引用**: {card['source_quote']}")
                            if card.get('summary'):
                                st.write(f"**解读**: {card['summary']}")
                            if card.get('keywords'):
                                st.write(f"**关键词**: {card['keywords']}")
                            if card.get('book'):
                                st.write(f"**书籍**: {card['book']}")
                            if card.get('movie'):
                                st.write(f"**电影**: {card['movie']}")
                            st.write(f"**创建时间**: {card.get('created_at', '')}")
                            
                            # 删除按钮（非批量模式下显示）
                            if not batch_mode:
                                if st.button(f"🗑️ 删除", key=f"delete_{card['id']}", use_container_width=True):
                                    st.session_state["delete_card_id"] = card["id"]
                                    st.rerun()
    else:
        st.info("还没有符合条件的卡片，快去生成一张吧！✨")

else:  # 平铺展示模式
    # 获取筛选后的卡片
    cards = db.filter_cards(
        keyword=search_keyword if search_keyword else "",
        tags=selected_tags
    )
    
    # 显示筛选结果
    st.caption(f"找到 {len(cards)} 张卡片")
    
    if cards:
        # 批量操作栏
        if batch_mode:
            batch_col1, batch_col2 = st.columns([2, 1])
            with batch_col1:
                st.info(f"已选择 {len(st.session_state['selected_card_ids'])} 张卡片")
            with batch_col2:
                if st.button("✅ 全选", key="select_all_flat", use_container_width=True):
                    st.session_state["selected_card_ids"] = [c['id'] for c in cards]
                    st.rerun()
            
            # 批量删除按钮
            if st.button(f"🗑️ 批量删除 {len(st.session_state['selected_card_ids'])} 张", 
                        key="batch_delete_flat",
                        disabled=len(st.session_state['selected_card_ids']) == 0,
                        type="primary",
                        use_container_width=True):
                if st.session_state['selected_card_ids']:
                    deleted = db.batch_delete_cards(st.session_state['selected_card_ids'])
                    st.success(f"已删除 {deleted} 张卡片")
                    st.session_state["selected_card_ids"] = []
                    st.rerun()
        
        # 每行显示 3 张卡片
        cols = st.columns(3)
        for idx, card in enumerate(cards):
            with cols[idx % 3]:
                # 批量选择复选框
                if batch_mode:
                    is_selected = card['id'] in st.session_state['selected_card_ids']
                    if st.checkbox(f"选择 ID:{card['id']}", value=is_selected, 
                                key=f"select_flat_{card['id']}"):
                        if card['id'] not in st.session_state['selected_card_ids']:
                            st.session_state['selected_card_ids'].append(card['id'])
                    else:
                        if card['id'] in st.session_state['selected_card_ids']:
                            st.session_state['selected_card_ids'].remove(card['id'])
                
                # 显示卡片图片（如果有）
                if card.get("card_image_path") and os.path.exists(card["card_image_path"]):
                    st.image(
                        card["card_image_path"],
                        caption=card.get("title", "知识卡片"),
                        width="stretch",
                    )
                else:
                    # 如果没有图片，显示文字卡片
                    st.write(f"**{card.get('title', '无标题')}**")
                    st.write(f"📝 {card.get('quote', '')[:30]}...")
                
                # 显示详情
                with st.expander(f"详情 (ID: {card['id']})"):
                    st.write(f"**标题**: {card.get('title', '')}")
                    st.write(f"**金句**: {card.get('quote', '')}")
                    if card.get('source_quote'):
                        st.write(f"**引用**: {card['source_quote']}")
                    if card.get('summary'):
                        st.write(f"**解读**: {card['summary']}")
                    if card.get('keywords'):
                        st.write(f"**关键词**: {card['keywords']}")
                    if card.get('book'):
                        st.write(f"**书籍**: {card['book']}")
                    if card.get('movie'):
                        st.write(f"**电影**: {card['movie']}")
                    st.write(f"**创建时间**: {card.get('created_at', '')}")
                    
                    # 删除按钮（非批量模式下显示）
                    if not batch_mode:
                        if st.button(f"🗑️ 删除", key=f"delete_{card['id']}", use_container_width=True):
                            st.session_state["delete_card_id"] = card["id"]
                            st.rerun()
    else:
        st.info("还没有符合条件的卡片，快去生成一张吧！✨")


# ========================== 第九段：页脚提示 ==========================

st.divider()
st.caption("💡 提示：工作流执行可能需要 30-60 秒，请耐心等待")
