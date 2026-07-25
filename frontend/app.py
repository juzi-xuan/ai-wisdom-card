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

# ---------- 导入我们自己写的 Dify 客户端 ----------
# 现在 Python 已经知道去 backend/ 找了（前面加了 sys.path）
from dify_api import DifyClient  # 👆 我们自己写的"AI 对话客户端"


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
        st.info(f"调试：input_key={input_key}, 发送内容={inputs}")
        # 👆 显示当前实际发送的变量名和内容，方便排查问题

        status_placeholder.info("🤖 正在连接 Dify 工作流...")
        # 👆 显示蓝色信息提示

        answer_text = ""  # 👆 存储 AI 返回的最终文本
        workflow_id = ""  # 👆 存储工作流运行 ID

        # ========== 用流式模式调用 Dify 工作流 ==========
        # for event in xxx: 意思是"对这个生成器里的每个事件，逐个处理"
        # run_workflow_streaming 是一个"生成器"（generator），它不一次性返回全部数据
        # 而是每收到一个事件就 yield 一个，for 循环就能逐个拿到
        for event in client.run_workflow_streaming(inputs=inputs):
            # ---------- 获取事件类型 ----------
            event_type = event.get("event", "")
            # 👆 从事件中取出 "event" 字段，如果不存在就用空字符串

            # ===== 情况1：出错了 =====
            if event_type == "error":
                status_placeholder.empty()  # 👆 清空状态提示
                st.error(f"❌ 生成失败: {event.get('message', '未知错误')}")
                if "status_code" in event:
                    st.write(f"**状态码**: {event['status_code']}")
                break  # 👆 出错就跳出循环，不再处理后续事件

            # ===== 情况2：工作流开始了 =====
            elif event_type == "workflow_started":
                # 获取运行 ID（方便追踪这次执行）
                workflow_id = event.get("workflow_run_id", "")
                status_placeholder.info(f"🚀 工作流已启动 (ID: {workflow_id[:8]}...)")
                # 👆 [:8] 只显示 ID 的前 8 位，不用显示完整长串

            # ===== 情况3：某个节点开始干活了 =====
            elif event_type == "node_started":
                # 获取节点名称
                node_title = event.get("data", {}).get("title", "")
                status_placeholder.info(f"⏳ 执行中: {node_title}...")
                # 👆 告诉用户"现在 AI 在干什么"

            # ===== 情况4：某个节点干完了 =====
            elif event_type == "node_finished":
                node_title = event.get("data", {}).get("title", "")
                status_placeholder.success(f"✅ 完成: {node_title}")

            # ===== 情况5：整个工作流完成 =====
            elif event_type == "workflow_finished":
                # ---------- 从返回数据中提取 AI 生成的文本 ----------
                # Dify workflow streaming 返回的结构：
                # event.data.outputs 里包含所有输出变量
                data = event.get("data") or {}
                outputs = data.get("outputs") or {}
                # 👆 防御性编程：如果任何一层是 None，用空字典替代

                # 优先找名为 "text" 的输出变量（本工作流的输出变量名）
                answer_text = outputs.get("text", "")

                # 如果 "text" 不存在，遍历所有输出找第一个字符串值
                if not answer_text:
                    for key, value in outputs.items():
                        if isinstance(value, str):  # 👆 检查是不是字符串类型
                            answer_text = value
                            break  # 👆 找到第一个就停

                status_placeholder.empty()  # 👆 清空进度提示

                if answer_text:
                    st.success("✅ 生成完成！")
                else:
                    # 如果没提取到内容，显示调试信息
                    st.warning("⚠️ 未提取到输出内容")
                    with st.expander("调试：workflow_finished 原始事件"):
                        st.json(event)  # 👆 展开查看原始事件数据

            # ===== 情况6：心跳（ping） =====
            elif event_type == "ping":
                pass  # 👆 "心跳"包，告诉"我还活着"，不需要做任何处理

        # ===== 循环结束，展示最终结果 =====

        if answer_text:
            # ---------- 有内容：展示 AI 的输出 ----------
            st.subheader("📄 生成结果")
            st.markdown(answer_text)
            # 👆 st.markdown 渲染 Markdown 格式，支持粗体、标题、列表等美化

        else:
            # ---------- 没内容：提示用户 ----------
            st.warning("⚠️ 工作流完成但未返回内容，请检查 Dify 工作流配置")

        # ---------- 显示工作流 ID（方便追踪） ----------
        if workflow_id:
            st.caption(f"工作流 ID: `{workflow_id}`")

# ========================== 第八段：页脚提示 ==========================

st.divider()
st.caption("💡 提示：工作流执行可能需要 30-60 秒，请耐心等待")
