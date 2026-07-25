"""
================================================================================
                                Dify 客户端封装
                         (Dify API Client Wrapper)
================================================================================
这个文件的作用：
    像"快递员"一样，帮我们把文字发送到 Dify AI 平台，
    然后把 Dify 处理完的结果拿回来。

打个比方：
    - 你是客户，想寄一封信（你的文字）给远方的朋友（AI）
    - Python 的 requests 库 = 快递卡车（负责运输）
    - 这个 DifyClient 类 = 快递公司（负责打包、贴标签、追踪）
    - Dify 平台 = 收件人（处理你的文字并回复）
    - .env 文件 = 快递单号本（存着钥匙和地址）
================================================================================
"""

# ========================== 第一段：导入需要的"工具箱" ==========================

import os       # 👉 os 是"操作系统小助手"：可以读取电脑上的环境变量（比如 .env 文件里的配置）
import json     # 👉 json 是"翻译官"：把 Python 的数据（字典、列表）和 JSON 文本互相转换
from typing import Optional, Dict, Any  # 👉 typing 是"标签贴纸"：给变量贴上类型标签，让代码更清晰
from pathlib import Path  # 👉 Path 是"地图导航"：用简单的方式找到电脑上的文件和文件夹

import requests  # 👉 requests 是"网络信使"：通过 HTTP 协议（网络上最通用的语言）发送请求、接收回复
from dotenv import load_dotenv  # 👉 load_dotenv 是"密码读取器"：从 .env 文件里读出密码和配置
from loguru import logger  # 👉 logger 是"日记本"：帮我们记录程序运行时发生了什么，方便调试

# -------------------------- 找到 .env 配置文件的位置 --------------------------
# 当前文件：backend/dify_api.py
# .env 文件：项目根目录/.env
# 所以需要"往上走一层"：Path(__file__).parent.parent
env_path = Path(__file__).parent.parent / ".env"  # 👉 拼出 .env 文件的完整路径
load_dotenv(dotenv_path=env_path)  # 👉 把 .env 文件里的配置读到系统环境变量里


# ========================== 第二段：定义快递公司 ==========================

class DifyClient:
    """
    这是一个"AI 对话客户"类
    作用：帮我们给 Dify AI 平台发消息、收回复
    就像是快递公司的客服，我们只需要告诉它"寄什么"，它会帮我们处理所有细节
    """

    def __init__(
        self,
        api_key: Optional[str] = None,  # 👉 你的 Dify 应用密钥（相当于快递单号），可以不传，会自动从 .env 读
        base_url: Optional[str] = None,  # 👉 Dify 服务的网址（快递公司的地址）
        user_id: Optional[str] = None,  # 👉 使用者名字（用来标记是谁发送的）
        input_key: Optional[str] = None,  # 👉 Dify 工作流接收输入的那个变量名（相当于"收件人姓名栏"）
    ):
        """
        初始化函数：当你 new 一个 DifyClient 时，Python 会自动调用这个函数。
        就像快递公司开业前先要把地址、电话这些信息登记好。
        """

        # ---------- 先用"三选一"策略获取配置 ----------
        # 策略：如果创建时传了参数就用参数，否则从 .env 文件读，再读不到就用默认值
        self.api_key = api_key or os.getenv("DIFY_API_KEY", "")
        # 👆 拿到 API 密钥（钥匙）

        self.base_url = base_url or os.getenv("DIFY_API_URL", "https://api.dify.ai/v1")
        # 👆 拿到 Dify 的服务器地址，默认是 Dify 的云端地址

        self.user_id = user_id or os.getenv("DIFY_USER_ID", "wisdom-card-user")
        # 👆 拿到使用者 ID（标记是谁在操作）

        self.input_key = input_key or os.getenv("DIFY_INPUT_KEY", "user_query")
        # 👆 拿到工作流输入变量的名字（告诉 Dify "变量名叫什么"）

        # ---------- 安全检查：万一忘了填密钥，立刻报错 ----------
        # 没有钥匙（API密钥），什么都做不了
        if not self.api_key:
            raise ValueError("DIFY_API_KEY is required. Please set it in .env file.")
            # 👆 raise 就是"举手报警"，告诉程序员出问题了

        # ---------- 打包"请求头"（给 Dify 看的"身份证"） ----------
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            # 👆 这是"通行证"：告诉 Dify "我有合法的钥匙"，Bearer 是 HTTP 协议的标准写法
            "Content-Type": "application/json",
            # 👆 这是"包裹说明"：告诉 Dify "我发的数据是 JSON 格式"
        }

    def _make_request(
        self,
        endpoint: str,  # 👉 接口路径（比如 "chat-messages" 对应"对话消息"功能）
        method: str = "POST",  # 👉 HTTP 方法：POST 是"发送数据"，GET 是"查询数据"
        data: Optional[Dict[str, Any]] = None,  # 👉 要发送的数据（一个字典，会变成 JSON）
        timeout: int = 60,  # 👉 最多等多少秒（超过这个时间还没回复就放弃）
    ) -> Dict[str, Any]:
        """
        通用的 HTTP 请求函数（"万能快递员"）

        作用：不管是查询信息还是生成卡片，都通过这个函数发送网络请求。
        就像是快递公司的"万能派送员"，不管是寄信还是寄包裹，流程都差不多。

        返回：
            一个统一格式的字典：
            - 成功：{"success": True, "status_code": 200, "data": {...}}
            - 失败：{"success": False, "status_code": 400, "error": "错误原因", "raw": {...}}
        """

        # ---------- 拼出完整的请求地址 ----------
        # base_url 可能是 "https://api.dify.ai/v1"
        # endpoint 可能是 "chat-messages"
        # 拼起来就是 "https://api.dify.ai/v1/chat-messages"
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        # 👆 rstrip('/') 去掉右边多余的 /，lstrip('/') 去掉左边多余的 /，保证不会出现 "//"

        # ---------- 记录日志（方便调试时知道发了什么） ----------
        logger.debug(f"Dify API {method} {url}")
        # 👆 记下"用什么方法访问哪个地址"
        logger.debug(f"Request payload: {json.dumps(data, ensure_ascii=False, indent=2)}")
        # 👆 记下"发送了什么内容"，ensure_ascii=False 让中文正常显示

        try:  # 👉 try 是"安全气囊"，如果下面的代码出错，不会直接爆炸
            # ---------- 根据方法类型发送请求 ----------
            if method.upper() == "POST":
                # POST 请求：向服务器"提交"数据（就像填表提交）
                response = requests.post(
                    url,  # 要访问的网址
                    headers=self.headers,  # 携带的身份信息（通行证）
                    json=data,  # 要发送的数据（requests 会自动转成 JSON 格式）
                    timeout=timeout,  # 最多等多久
                )
            elif method.upper() == "GET":
                # GET 请求：向服务器"查询"数据（就像在网页搜索）
                response = requests.get(url, headers=self.headers, timeout=timeout)
            else:
                # 不支持的其他方法（比如 PUT、DELETE），报错
                raise ValueError(f"Unsupported HTTP method: {method}")

            # ---------- 把服务器的回复从 JSON 转成 Python 字典 ----------
            try:
                result = response.json()
                # 👆 .json() 把服务器返回的 JSON 字符串变成 Python 字典
            except json.JSONDecodeError:
                # 👆 如果服务器返回的不是合法 JSON（比如返回了一个 HTML 错误页）
                result = {"raw_text": response.text}
                # 👆 就把原始文本存起来，至少不会丢失数据

            # ---------- 记录回复日志 ----------
            logger.debug(
                f"Response status: {response.status_code}, "
                f"body: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}"
                # 👆 [:500] 只显示前 500 个字符，防止日志太长
            )

            # ---------- 检查 HTTP 状态码 ----------
            if response.status_code != 200:
                # 200 代表"成功"，不是 200 就是出错了
                # 先尝试从回复中提取错误信息
                error_msg = result.get("message", result.get("error", response.text))
                # 👆 三层 fallback：message > error > 原始文本
                logger.error(
                    f"Dify API error: {response.status_code} - {error_msg}"
                )
                # 返回失败结果（注意 success 是 False）
                return {
                    "success": False,  # 👈 标记失败
                    "status_code": response.status_code,  # 👈 HTTP 状态码（比如 400, 404, 500）
                    "error": error_msg,  # 👈 错误说明
                    "raw": result,  # 👈 原始回复（方便调试）
                }

            # ---------- 一切顺利，返回成功结果 ----------
            return {"success": True, "status_code": response.status_code, "data": result}

        # ========== 下面是各种"意外情况"的处理 ==========
        # 就像快递可能遇到：堵车、地址错了、包裹丢了…

        except requests.exceptions.Timeout:
            # 👆 超时了：等太久没回复，像快递在路上堵了
            logger.error(f"Dify API timeout after {timeout}s")
            return {"success": False, "error": "request_timeout", "status_code": 0}

        except requests.exceptions.ConnectionError:
            # 👆 连接不上：网络断了或者服务器没启动，像快递站关门了
            logger.error("Dify API connection error")
            return {"success": False, "error": "connection_error", "status_code": 0}

        except Exception as e:
            # 👆 其他意外错误（万能兜底）：比如电脑内存不够了
            logger.error(f"Dify API unexpected error: {str(e)}")
            return {"success": False, "error": str(e), "status_code": 0}

    def chat_message(
        self,
        query: str,  # 👉 你要问 AI 的话
        inputs: Optional[Dict[str, Any]] = None,  # 👉 额外的输入变量（如来源）
        response_mode: str = "blocking",  # 👉 回复模式：blocking=等全部生成完再返回，streaming=边生成边返回
        conversation_id: Optional[str] = None,  # 👉 聊天 ID（如果要继续之前的对话）
    ) -> Dict[str, Any]:
        """
        和 Dify 聊天应用对话（Chat Message）

        这个方法专门给"聊天型"的 Dify 应用用。
        如果你的 Dify 应用是"对话型"（Chat App），用这个。

        和 run_workflow 的区别：
        - chat_message：用于"聊天对话型"Dify 应用
        - run_workflow：用于"工作流型"（Workflow）Dify 应用
        """
        if inputs is None:
            inputs = {}  # 👆 如果没有额外输入，就用空字典

        # ---------- 打包要发送的数据 ----------
        payload = {
            "inputs": inputs,  # 👈 额外的输入变量
            "query": query,  # 👈 用户说的话
            "response_mode": response_mode,  # 👈 回复方式：一次性还是流式
            "user": self.user_id,  # 👈 谁在发
        }

        if conversation_id:
            # 👆 如果给了一个对话 ID，说明要继续上一次聊天
            payload["conversation_id"] = conversation_id

        # ---------- 交给"万能快递员"去发送 ----------
        return self._make_request("chat-messages", method="POST", data=payload)

    def run_workflow(
        self,
        inputs: Optional[Dict[str, Any]] = None,  # 👉 传给工作流的变量（key 是变量名，value 是值）
        response_mode: str = "blocking",  # 👉 回复模式
        timeout: int = 120,  # 👉 超时时间设为 120 秒（工作流可能比聊天慢）
    ) -> Dict[str, Any]:
        """
        运行 Dify 工作流（一次性，等全部完成再返回）

        工作流就像一条"流水线"：
        用户输入 → 节点1处理 → 节点2处理 → ... → 输出最终结果

        blocking 模式：就像点外卖"到店取"，等餐做好了才能拿走
        streaming 模式：就像"边做边上菜"，做一道上一道
        """
        if inputs is None:
            inputs = {}

        # ---------- 打包数据 ----------
        payload = {
            "inputs": inputs,  # 👈 传给工作流的所有变量
            "response_mode": response_mode,  # 👈 等全部完成再返回
            "user": self.user_id,
        }

        # ---------- 调用"工作流运行"接口 ----------
        return self._make_request("workflows/run", method="POST", data=payload, timeout=timeout)

    def run_workflow_streaming(self, inputs: Optional[Dict[str, Any]] = None):
        """
        用"流式"模式运行 Dify 工作流（边执行边返回进度）

        和 run_workflow 的区别：
        - run_workflow：一次性等全部完成，返回最终结果
        - run_workflow_streaming：一边执行一通过 yield 返回中间状态

        "流式"是什么意思？
        ==================
        想象你在看直播：
        - 主播每做一个动作，你立刻能看到
        - 不用等整个直播结束才看回放

        yield 是什么？
        =============
        yield 是 Python 里的"接力棒"：
        - 函数遇到 yield 就暂停，把当前值"交出去"
        - 外面处理完这个值后，函数从暂停的地方继续
        - 就像接力赛，一段一段往后传

        这个函数会返回（yield）下面几种事件：
        1. workflow_started  — 工作流开始了
        2. node_started     — 某个节点开始干活了（比如 LLM 节点开始思考）
        3. node_finished    — 某个节点干完活了
        4. workflow_finished — 全部完成了，包含最终结果
        5. ping             — "心跳"，告诉你还活着，别断线
        6. error            — 出错了
        """
        if inputs is None:
            inputs = {}

        # ---------- 打包并标记为 streaming ----------
        payload = {
            "inputs": inputs,  # 👈 传给工作流的变量
            "response_mode": "streaming",  # 👈 关键！告诉 Dify 用流式模式
            "user": self.user_id,  # 👈 谁在使用
        }

        # ---------- 拼出完整 URL ----------
        url = f"{self.base_url.rstrip('/')}/workflows/run"

        # ---------- 记录日志 ----------
        logger.debug(f"Dify API POST (streaming) {url}")

        try:
            # ========== 发送 HTTP 请求（注意：stream=True） ==========
            # stream=True 是关键参数，告诉 requests："别一次性读完回复，我要边收边处理"
            # 就像一个水龙头，开着让它慢慢流，而不是接满一桶再拿走
            response = requests.post(
                url,
                headers=self.headers,  # 👈 携带通行证
                json=payload,  # 👈 要发送的数据
                stream=True,  # 👈 流式模式！这是最重要的参数
                timeout=300,  # 👈 流式模式超时设久一点（5 分钟）
            )

            # ---------- 如果 HTTP 状态码不是 200，说明请求本身就失败了 ----------
            if response.status_code != 200:
                try:
                    error_body = response.json()  # 👆 尝试解析错误详情
                except Exception:
                    error_body = {"raw_text": response.text}  # 👆 解析不了就存原始文本
                yield {
                    "event": "error",  # 👈 告诉我们出错了
                    "status_code": response.status_code,  # 👈 HTTP 错误码
                    "message": error_body.get("message", response.text),  # 👈 错误信息
                }
                return  # 👈 出错就结束，不再继续

            # ========== 开始读取流式回复 ==========
            # Dify 的流式回复是 SSE 格式（Server-Sent Events，服务器推送事件）
            # 每一行的格式是："data: {JSON数据}"
            # 比如：data: {"event": "workflow_started", ...}

            for line in response.iter_lines(decode_unicode=True):
                # 👆 iter_lines() 一行一行地读，decode_unicode=True 让中文正常显示

                # ---------- 跳过空行和非 data 行 ----------
                if not line or not line.startswith("data:"):
                    continue  # 👆 不是有效数据行，跳过

                # ---------- 提取 JSON 部分 ----------
                # "data: {...}" → 去掉前面的 "data:" 五个字符，拿到 "{...}"
                json_str = line[5:].strip()  # 👆 line[5:] 从第6个字符开始取，.strip() 去掉首尾空格
                if not json_str:
                    continue  # 👆 JSON 是空的，跳过

                # ---------- 把 JSON 字符串变成 Python 字典 ----------
                try:
                    event_data = json.loads(json_str)  # 👆 解析 JSON
                except json.JSONDecodeError:
                    continue  # 👆 解析失败（可能是坏数据），跳过

                # ---------- 向外"抛出"这个事件 ----------
                yield event_data  # 👆 函数暂停，把事件交出去，等外面处理完再继续

        # ========== 异常处理 ==========
        except requests.exceptions.Timeout:
            yield {"event": "error", "message": "streaming_timeout"}  # 👆 超时了
        except requests.exceptions.ConnectionError:
            yield {"event": "error", "message": "connection_error"}  # 👆 连不上
        except Exception as e:
            yield {"event": "error", "message": str(e)}  # 👆 其他意外错误

    def generate_card(
        self,
        text: str,  # 👉 用户输入的原始文字（你想记录的那句话）
        source: Optional[str] = None,  # 👉 来源（从哪里看到的，如书名、文章名）
    ) -> Dict[str, Any]:
        """
        生成知识卡片（调用 Dify 工作流，取回 AI 处理结果）

        这个函数做一个完整的流程：
        1. 把文字和来源打包
        2. 发送给 Dify 工作流
        3. 提取 AI 生成的内容
        4. 解析成结构化数据
        """
        # ---------- 把输入打包成字典 ----------
        # self.input_key 是从 .env 里读到的变量名（比如 "y"）
        # 意思：Dify 工作流里有一个叫 "y" 的输入框，我们把文字填进去
        inputs = {self.input_key: text}

        # 如果用户填了来源，也一起带过去
        if source:
            inputs["source"] = source

        # ---------- 调用 blocking 模式 ----------
        result = self.run_workflow(inputs=inputs, response_mode="blocking")

        # ---------- 如果 Dify 返回失败，直接原样返回错误 ----------
        if not result["success"]:
            return result  # 👆 把错误信息原封不动传给调用者

        # ---------- 从复杂的返回数据中提取 AI 生成的文本 ----------
        data = result["data"]  # 👆 Dify 返回的完整数据
        outputs = data.get("data", {}).get("outputs", {})
        # 👆 路径：result["data"]["data"]["outputs"] → 这是 Dify workflow 返回数据的嵌套结构

        answer_text = ""  # 👆 最终要展示的文本，先设空

        # ---------- 尝试从 outputs 里提取文本 ----------
        if outputs:
            for key, value in outputs.items():
                # 👆 遍历所有输出变量
                if isinstance(value, str):  # 👆 如果值是字符串（文本）
                    answer_text = value  # 👆 就用这个
                    break  # 👆 找到第一个就停

        # ---------- 如果上面没找到，换一种方式再试试 ----------
        if not answer_text:
            answer_text = data.get("data", {}).get("output_text", "")

        # ---------- 把 AI 返回的文本解析成结构化数据 ----------
        parsed = self._parse_card_answer(answer_text)

        # ---------- 返回整理后的结果 ----------
        return {
            "success": True,  # 👆 标记成功
            "raw_answer": answer_text,  # 👆 AI 返回的原始文本
            "workflow_run_id": data.get("workflow_run_id", ""),  # 👆 工作流运行 ID（方便追踪）
            "task_id": data.get("task_id", ""),  # 👆 任务 ID
            "card": parsed,  # 👆 解析后的结构化数据
        }

    def _parse_card_answer(self, answer: str) -> Dict[str, Any]:
        """
        解析 AI 返回的文本（尝试从文本中提取 JSON 数据）

        Dify 工作流中的 LLM 有时候会返回这样的格式：
        ```json
        {"title": "...", "content": "..."}
        ```

        这个函数负责把 ```json...``` 包裹的内容提取出来，转成 Python 字典。
        如果 AI 返回的不是 JSON，就原样保存为 raw_text。
        """
        # ---------- 空文本直接返回空字典 ----------
        if not answer:
            return {}

        # ---------- 去掉首尾空格 ----------
        answer = answer.strip()

        # ---------- 如果 AI 用 ```json 包裹了 JSON，去掉这些标记 ----------
        # 比如："```json\n{\"a\":1}\n```" → "{\"a\":1}"
        if answer.startswith("```json"):
            answer = answer[7:]  # 👆 去掉前面 7 个字符 "```json"
        if answer.endswith("```"):
            answer = answer[:-3]  # 👆 去掉后面 3 个字符 "```"
        answer = answer.strip()  # 👆 再去一次首尾空格

        # ---------- 尝试解析 JSON ----------
        try:
            data = json.loads(answer)  # 👆 loads = Load String，把字符串变成 Python 对象
            return data
        except json.JSONDecodeError:
            # 👆 解析失败 = 不是 JSON 格式
            logger.warning("Failed to parse answer as JSON, returning raw text")
            return {"raw_text": answer}  # 👆 把原始文本存起来

    def get_application_info(self) -> Dict[str, Any]:
        """
        获取 Dify 应用的基本信息（用于测试连接是否正常）

        就像打电话问："喂，你们在营业吗？"

        如果返回 success: True，说明：
        - API Key 是正确的
        - 网络是通的
        - Dify 服务是正常的
        """
        return self._make_request("parameters", method="GET")


# ========================== 第三段：自己测试自己的代码 ==========================
# 下面的代码只有在你直接运行这个文件时才执行
# 如果别的文件 import 这个文件，下面的代码不会执行

def main():
    """直接运行这个文件时的测试代码"""
    # ---------- 创建一个客户端 ----------
    client = DifyClient()

    # ---------- 测试1：查看应用信息 ----------
    info = client.get_application_info()
    print("=" * 50)
    print("应用信息:")
    print(json.dumps(info, ensure_ascii=False, indent=2))  # 👆 好看的 JSON 格式打印

    # ---------- 测试2：生成一张卡片 ----------
    print("\n" + "=" * 50)
    print("测试卡片生成:")
    test_text = "人生最大的遗憾，不是失败，而是我本可以。"  # 👆 测试用的句子
    result = client.generate_card(text=test_text, source="网络")
    print(json.dumps(result, ensure_ascii=False, indent=2))


# Python 的特殊变量：当这个文件被直接运行时 __name__ 的值是 "__main__"
if __name__ == "__main__":
    main()  # 👆 只有直接运行时才调用 main()，被 import 时不调用
