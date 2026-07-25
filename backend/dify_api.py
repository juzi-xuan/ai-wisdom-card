import os
import json
from typing import Optional, Dict, Any
from pathlib import Path

import requests
from dotenv import load_dotenv
from loguru import logger

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class DifyClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[str] = None,
        input_key: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("DIFY_API_KEY", "")
        self.base_url = base_url or os.getenv("DIFY_API_URL", "https://api.dify.ai/v1")
        self.user_id = user_id or os.getenv("DIFY_USER_ID", "wisdom-card-user")
        self.input_key = input_key or os.getenv("DIFY_INPUT_KEY", "user_query")

        if not self.api_key:
            raise ValueError("DIFY_API_KEY is required. Please set it in .env file.")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _make_request(
        self,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict[str, Any]] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        logger.debug(f"Dify API {method} {url}")
        logger.debug(f"Request payload: {json.dumps(data, ensure_ascii=False, indent=2)}")

        try:
            if method.upper() == "POST":
                response = requests.post(
                    url, headers=self.headers, json=data, timeout=timeout
                )
            elif method.upper() == "GET":
                response = requests.get(url, headers=self.headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            try:
                result = response.json()
            except json.JSONDecodeError:
                result = {"raw_text": response.text}

            logger.debug(
                f"Response status: {response.status_code}, "
                f"body: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}"
            )

            if response.status_code != 200:
                error_msg = result.get("message", result.get("error", response.text))
                logger.error(
                    f"Dify API error: {response.status_code} - {error_msg}"
                )
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "error": error_msg,
                    "raw": result,
                }

            return {"success": True, "status_code": response.status_code, "data": result}

        except requests.exceptions.Timeout:
            logger.error(f"Dify API timeout after {timeout}s")
            return {"success": False, "error": "request_timeout", "status_code": 0}
        except requests.exceptions.ConnectionError:
            logger.error("Dify API connection error")
            return {"success": False, "error": "connection_error", "status_code": 0}
        except Exception as e:
            logger.error(f"Dify API unexpected error: {str(e)}")
            return {"success": False, "error": str(e), "status_code": 0}

    def chat_message(
        self,
        query: str,
        inputs: Optional[Dict[str, Any]] = None,
        response_mode: str = "blocking",
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if inputs is None:
            inputs = {}

        payload = {
            "inputs": inputs,
            "query": query,
            "response_mode": response_mode,
            "user": self.user_id,
        }

        if conversation_id:
            payload["conversation_id"] = conversation_id

        return self._make_request("chat-messages", method="POST", data=payload)

    def run_workflow(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        response_mode: str = "blocking",
        timeout: int = 120,
    ) -> Dict[str, Any]:
        if inputs is None:
            inputs = {}

        payload = {
            "inputs": inputs,
            "response_mode": response_mode,
            "user": self.user_id,
        }

        return self._make_request("workflows/run", method="POST", data=payload, timeout=timeout)

    def run_workflow_streaming(self, inputs: Optional[Dict[str, Any]] = None):
        if inputs is None:
            inputs = {}

        payload = {
            "inputs": inputs,
            "response_mode": "streaming",
            "user": self.user_id,
        }

        url = f"{self.base_url.rstrip('/')}/workflows/run"

        logger.debug(f"Dify API POST (streaming) {url}")

        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=300,
            )

            if response.status_code != 200:
                try:
                    error_body = response.json()
                except Exception:
                    error_body = {"raw_text": response.text}
                yield {
                    "event": "error",
                    "status_code": response.status_code,
                    "message": error_body.get("message", response.text),
                }
                return

            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue

                json_str = line[5:].strip()
                if not json_str:
                    continue

                try:
                    event_data = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                yield event_data

        except requests.exceptions.Timeout:
            yield {"event": "error", "message": "streaming_timeout"}
        except requests.exceptions.ConnectionError:
            yield {"event": "error", "message": "connection_error"}
        except Exception as e:
            yield {"event": "error", "message": str(e)}

    def generate_card(
        self,
        text: str,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        inputs = {self.input_key: text}
        if source:
            inputs["source"] = source

        result = self.run_workflow(inputs=inputs, response_mode="blocking")

        if not result["success"]:
            return result

        data = result["data"]
        outputs = data.get("data", {}).get("outputs", {})
        answer_text = ""

        if outputs:
            for key, value in outputs.items():
                if isinstance(value, str):
                    answer_text = value
                    break

        if not answer_text:
            answer_text = data.get("data", {}).get("output_text", "")

        parsed = self._parse_card_answer(answer_text)

        return {
            "success": True,
            "raw_answer": answer_text,
            "workflow_run_id": data.get("workflow_run_id", ""),
            "task_id": data.get("task_id", ""),
            "card": parsed,
        }

    def _parse_card_answer(self, answer: str) -> Dict[str, Any]:
        if not answer:
            return {}

        answer = answer.strip()

        if answer.startswith("```json"):
            answer = answer[7:]
        if answer.endswith("```"):
            answer = answer[:-3]
        answer = answer.strip()

        try:
            data = json.loads(answer)
            return data
        except json.JSONDecodeError:
            logger.warning("Failed to parse answer as JSON, returning raw text")
            return {"raw_text": answer}

    def get_application_info(self) -> Dict[str, Any]:
        return self._make_request("parameters", method="GET")


def main():
    client = DifyClient()

    info = client.get_application_info()
    print("=" * 50)
    print("应用信息:")
    print(json.dumps(info, ensure_ascii=False, indent=2))

    print("\n" + "=" * 50)
    print("测试卡片生成:")
    test_text = "人生最大的遗憾，不是失败，而是我本可以。"
    result = client.generate_card(text=test_text, source="网络")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
