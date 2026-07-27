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
from image_generator import generate_card_image  # 👆 "卡片印刷机"：把 JSON 变成图片
from database import get_db, GENERATED_DIR  # 👆 数据库操作和图片保存目录


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

st.title("✨ AI 知识卡片生成器")
# 👆 页面上方的大标题（<h1> 级别）

st.caption("基于 Dify 工作流 · 测试版")
# 👆 标题下方的小字说明（灰色，低调）


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

st.divider()  # 👆 水平分割线

# ---------- 输入区：文字输入框 ----------
st.subheader("📝 输入文本")
input_text = st.text_area(
    "输入你想生成卡片的文字",
    # 👆 标签文字
    height=120,
    # 👆 输入框高度（像素）
    placeholder="例如：人生最大的遗憾，不是失败，而是我本可以。",
    # 👆 输入框为空时显示的灰色提示文字
)

# ---------- 输入区：来源（可选） ----------
source = st.text_input(
    "来源（可选）",
    placeholder="书名 / 文章名 / 视频名",
)

# ---------- 按钮区：一行放两个按钮 ----------
col1, col2 = st.columns([1, 1])
# 👆 st.columns 把一行分成若干列，[1,1] 表示等宽两列

with col1:
    # type="primary" 让按钮显示为蓝色高亮（主要操作）
    generate_btn = st.button("🚀 生成卡片", type="primary", use_container_width=True)
    # 👆 "生成"按钮：点击后触发 AI 处理

with col2:
    clear_btn = st.button("🗑️ 清空", use_container_width=True)
    # 👆 "清空"按钮：清空所有输入

# 如果点了"清空"按钮
if clear_btn:
    st.rerun()  # 👆 刷新整个页面，相当于 F5，所有输入都会清空

st.divider()

# ========================== 第七段：核心逻辑 —— 调用 Dify 并展示结果 ==========================

if generate_btn:  # 👆 只有当用户点了"生成卡片"按钮时，才执行下面的代码
    # ---------- 安全检查1：有没有输入文字 ----------
    if not input_text.strip():
        # .strip() 去掉首尾空格后，如果是空的 → 用户没输入
        st.warning("⚠️ 请先输入文本")  # 👆 黄色警告提示
    # ---------- 安全检查2：有没有填 API Key ----------
    elif not api_key:
        st.warning("⚠️ 请先在左侧填写 API Key")
    else:
        # ---------- 创建 Dify 客户端 ----------
        client = DifyClient(
            api_key=api_key,
            base_url=base_url,
            user_id=user_id,
            input_key=input_key,
        )

        # ---------- 打包输入数据 ----------
        # 把 input_key（比如 "y"）作为 key，用户输入的文字作为 value
        # 比如：{"y": "人生最大的遗憾..."}
        inputs = {input_key: input_text}
        if source:
            inputs["source"] = source  # 👆 如果填了来源，也加进去

        # ---------- 占位符：先占坑，后续动态更新内容 ----------
        status_placeholder = st.empty()
        # 👆 st.empty() 创建一个"空容器"，之后可以往里面放东西、换内容、或者清空
        #    类比：贴了一张便利贴，上面写什么可以随时改

        # ---------- 调试信息 ----------
        st.info(f"调试：input_key={input_key}, 模式=fixed（跳过 Dify 调用）")
        # 👆 显示当前实际发送的变量名和内容，方便排查问题

        status_placeholder.info("🤖 正在生成卡片...")
        # 👆 显示蓝色信息提示

        workflow_outputs = {}  # 👆 存储工作流最终输出的完整 outputs 字典
        card_data = {}  # 👆 提取后的卡片数据
        extract_mode = ""  # 👆 提取模式（single_json / multi_field / empty）
        workflow_id = ""  # 👆 存储工作流运行 ID

        # ========== [临时] 跳过 Dify 调用，使用固定数据节省 tokens ==========
        # TODO: 恢复 Dify 调用时取消下面的注释
        # for event in client.run_workflow_streaming(inputs=inputs):
        #     event_type = event.get("event", "")
        #     if event_type == "error":
        #         status_placeholder.empty()
        #         st.error(f"❌ 生成失败: {event.get('message', '未知错误')}")
        #         if "status_code" in event:
        #             st.write(f"**状态码**: {event['status_code']}")
        #         break
        #     elif event_type == "workflow_started":
        #         workflow_id = event.get("workflow_run_id", "")
        #         status_placeholder.info(f"🚀 工作流已启动 (ID: {workflow_id[:8]}...)")
        #     elif event_type == "node_started":
        #         node_title = event.get("data", {}).get("title", "")
        #         status_placeholder.info(f"⏳ 执行中: {node_title}...")
        #     elif event_type == "node_finished":
        #         node_title = event.get("data", {}).get("title", "")
        #         status_placeholder.success(f"✅ 完成: {node_title}")
        #     elif event_type == "workflow_finished":
        #         raw_data = event.get("data") or {}
        #         workflow_outputs = raw_data.get("outputs") or {}
        #         card_data, extract_mode = _extract_card_data_from_outputs(workflow_outputs)
        #         status_placeholder.empty()
        #         if extract_mode != "empty":
        #             field_count = len(card_data)
        #             st.success(f"✅ 生成完成！提取模式：{extract_mode}，共 {field_count} 个字段")
        #         else:
        #             st.warning("⚠️ 未提取到输出内容")
        #             with st.expander("🔍 调试：workflow_finished 原始事件"):
        #                 st.json(event)
        #     elif event_type == "ping":
        #         pass

        # ===== 使用固定卡片数据（跳过 Dify API 调用） =====
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
        status_placeholder.empty()
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
                with st.spinner("🎨 正在渲染卡片图片..."):
                    card_image = generate_card_image(card_data)

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

                # ===== 展示图片 =====
                st.image(
                    card_image,
                    caption=card_data.get("title", "知识卡片"),
                    width=500,
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

# ---------- 搜索功能 ----------
search_col1, search_col2 = st.columns([3, 1])
with search_col1:
    search_keyword = st.text_input("🔍 搜索卡片", placeholder="输入关键词搜索...")
with search_col2:
    st.write("")
    st.write("")
    delete_btn_placeholder = st.empty()

# ---------- 获取卡片列表 ----------
db = get_db()

# ---------- 处理删除操作（放在卡片列表渲染之前） ----------
if "delete_card_id" in st.session_state:
    db.delete_card(st.session_state["delete_card_id"])
    del st.session_state["delete_card_id"]
    st.rerun()

total_count = db.get_card_count()

if search_keyword:
    cards = db.search_cards(search_keyword)
else:
    cards = db.get_all_cards()

# ---------- 显示卡片数量 ----------
if search_keyword:
    st.caption(f"搜索 '{search_keyword}'，找到 {len(cards)} 张卡片")
else:
    st.caption(f"共 {total_count} 张卡片")

# ---------- 卡片网格展示 ----------
if cards:
    # 每行显示 3 张卡片
    cols = st.columns(3)
    for idx, card in enumerate(cards):
        with cols[idx % 3]:
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
            
            # 显示基本信息
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
                
                # 删除按钮
                if st.button(f"🗑️ 删除", key=f"delete_{card['id']}", use_container_width=True):
                    st.session_state["delete_card_id"] = card["id"]
                    st.rerun()
else:
    st.info("还没有卡片，快去生成一张吧！✨")


# ========================== 第九段：页脚提示 ==========================

st.divider()
st.caption("💡 提示：工作流执行可能需要 30-60 秒，请耐心等待")
