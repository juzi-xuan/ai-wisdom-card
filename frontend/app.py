import sys
import json
import os
from pathlib import Path

import streamlit as st

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from dify_api import DifyClient


def _get_config(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.getenv(key, default)

st.set_page_config(
    page_title="AI 知识卡片 - Dify 工作流测试",
    page_icon="✨",
    layout="centered",
)

st.title("✨ AI 知识卡片生成器")
st.caption("基于 Dify 工作流 · 测试版")

with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input(
        "Dify API Key",
        value=_get_config("DIFY_API_KEY", ""),
        type="password",
        help="在 Dify 应用的「API 密钥」中获取",
    )
    base_url = st.text_input(
        "Dify API 地址",
        value=_get_config("DIFY_API_URL", "https://api.dify.ai/v1"),
    )
    input_key = st.text_input(
        "输入变量名",
        value=_get_config("DIFY_INPUT_KEY", "user_query"),
        help="工作流的起始输入变量名",
    )
    user_id = st.text_input(
        "用户 ID",
        value=_get_config("DIFY_USER_ID", "test-user"),
    )

    st.divider()
    if st.button("🧪 测试连接", use_container_width=True):
        if not api_key:
            st.error("请先填写 API Key")
        else:
            try:
                client = DifyClient(
                    api_key=api_key,
                    base_url=base_url,
                    user_id=user_id,
                    input_key=input_key,
                )
                with st.spinner("正在连接..."):
                    result = client.get_application_info()
                if result["success"]:
                    st.success("✅ 连接成功！")
                    with st.expander("查看应用信息"):
                        st.json(result["data"])
                else:
                    st.error(f"❌ 连接失败: {result.get('error', '未知错误')}")
            except Exception as e:
                st.error(f"❌ 异常: {str(e)}")

st.divider()

st.subheader("📝 输入文本")
input_text = st.text_area(
    "输入你想生成卡片的文字",
    height=120,
    placeholder="例如：人生最大的遗憾，不是失败，而是我本可以。",
)

source = st.text_input(
    "来源（可选）",
    placeholder="书名 / 文章名 / 视频名",
)

col1, col2 = st.columns([1, 1])
with col1:
    generate_btn = st.button("🚀 生成卡片", type="primary", use_container_width=True)
with col2:
    clear_btn = st.button("🗑️ 清空", use_container_width=True)

if clear_btn:
    st.rerun()

st.divider()

if generate_btn:
    if not input_text.strip():
        st.warning("⚠️ 请先输入文本")
    elif not api_key:
        st.warning("⚠️ 请先在左侧填写 API Key")
    else:
        client = DifyClient(
            api_key=api_key,
            base_url=base_url,
            user_id=user_id,
            input_key=input_key,
        )

        inputs = {input_key: input_text}
        if source:
            inputs["source"] = source

        status_placeholder = st.empty()

        st.info(f"调试：input_key={input_key}, 发送内容={inputs}")
        status_placeholder.info("🤖 正在连接 Dify 工作流...")
        answer_text = ""
        workflow_id = ""

        for event in client.run_workflow_streaming(inputs=inputs):
            event_type = event.get("event", "")

            if event_type == "error":
                status_placeholder.empty()
                st.error(f"❌ 生成失败: {event.get('message', '未知错误')}")
                if "status_code" in event:
                    st.write(f"**状态码**: {event['status_code']}")
                break

            elif event_type == "workflow_started":
                workflow_id = event.get("workflow_run_id", "")
                status_placeholder.info(f"🚀 工作流已启动 (ID: {workflow_id[:8]}...)")

            elif event_type == "node_started":
                node_title = event.get("data", {}).get("title", "")
                status_placeholder.info(f"⏳ 执行中: {node_title}...")

            elif event_type == "node_finished":
                node_title = event.get("data", {}).get("title", "")
                status_placeholder.success(f"✅ 完成: {node_title}")

            elif event_type == "workflow_finished":
                data = event.get("data") or {}
                outputs = data.get("outputs") or {}
                answer_text = outputs.get("text", "")
                if not answer_text:
                    for key, value in outputs.items():
                        if isinstance(value, str):
                            answer_text = value
                            break
                status_placeholder.empty()
                if answer_text:
                    st.success("✅ 生成完成！")
                else:
                    st.warning("⚠️ 未提取到输出内容")
                    with st.expander("调试：workflow_finished 原始事件"):
                        st.json(event)

            elif event_type == "ping":
                pass

        if answer_text:
            st.subheader("📄 生成结果")
            st.markdown(answer_text)
        else:
            st.warning("⚠️ 工作流完成但未返回内容，请检查 Dify 工作流配置")

        if workflow_id:
            st.caption(f"工作流 ID: `{workflow_id}`")

st.divider()
st.caption("💡 提示：工作流执行可能需要 30-60 秒，请耐心等待")
