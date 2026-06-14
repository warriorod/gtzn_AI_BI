import asyncio

import httpx
import pytest

from services import aimodel_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.com")
            response = httpx.Response(
                self.status_code,
                request=request,
                text=self.text,
            )
            raise httpx.HTTPStatusError(
                "request failed",
                request=request,
                response=response,
            )


class FakeAsyncClient:
    responses = []
    requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def fake_httpx_client(monkeypatch):
    FakeAsyncClient.responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr(aimodel_service.httpx, "AsyncClient", FakeAsyncClient)


def test_check_llm_status_verifies_chat_and_tool_calling():
    FakeAsyncClient.responses = [
        FakeResponse(payload={"data": [{"id": "deepseek-v4-flash"}]}),
        FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
        FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "supplier": 5,
                "api_domain": "https://example.com/v1/",
                "api_key": "secret",
                "base_model": "deepseek-v4-flash",
            }
        )
    )

    assert result == {
        "success": True,
        "message": "连接成功，基础对话和 Agent 工具调用均可用",
        "capabilities": {
            "models": True,
            "chat": True,
            "tool_calling": True,
        },
    }
    assert [request[1] for request in FakeAsyncClient.requests] == [
        "https://example.com/v1/models",
        "https://example.com/v1/chat/completions",
        "https://example.com/v1/chat/completions",
    ]
    tool_body = FakeAsyncClient.requests[2][2]["json"]
    assert tool_body["tool_choice"] == "auto"
    assert tool_body["tools"][0]["function"]["name"] == "connection_test"


def test_check_llm_status_reports_agent_tool_calling_failure():
    FakeAsyncClient.responses = [
        FakeResponse(payload={"data": [{"id": "deepseek-v4-flash"}]}),
        FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
        FakeResponse(
            status_code=400,
            text='"auto" tool choice requires --enable-auto-tool-choice',
        ),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "supplier": 5,
                "api_domain": "https://example.com/v1",
                "api_key": "secret",
                "base_model": "deepseek-v4-flash",
            }
        )
    )

    assert result["success"] is False
    assert result["capabilities"] == {
        "models": True,
        "chat": True,
        "tool_calling": False,
    }
    assert "--enable-auto-tool-choice" in result["message"]


def test_check_llm_status_reports_chat_failure_separately():
    FakeAsyncClient.responses = [
        FakeResponse(payload={"data": [{"id": "deepseek-v4-flash"}]}),
        FakeResponse(status_code=400, text="model does not support chat"),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "supplier": 5,
                "api_domain": "https://example.com/v1",
                "api_key": "secret",
                "base_model": "deepseek-v4-flash",
            }
        )
    )

    assert result["success"] is False
    assert result["capabilities"] == {
        "models": True,
        "chat": False,
        "tool_calling": False,
    }
    assert "基础对话测试失败" in result["message"]


def test_check_llm_status_allows_missing_models_endpoint_when_chat_works():
    FakeAsyncClient.responses = [
        FakeResponse(status_code=404, text="not found"),
        FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
        FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]}),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "supplier": 10,
                "api_domain": "https://example.com/v1",
                "api_key": "secret",
                "base_model": "MiniMax-M2.1",
            }
        )
    )

    assert result == {
        "success": True,
        "message": "连接成功，基础对话和 Agent 工具调用均可用；模型列表接口不可用",
        "capabilities": {
            "models": False,
            "chat": True,
            "tool_calling": True,
        },
    }


def test_check_llm_status_rejects_invalid_chat_response():
    FakeAsyncClient.responses = [
        FakeResponse(payload={"data": [{"id": "deepseek-v4-flash"}]}),
        FakeResponse(payload={"message": "upstream proxy response"}),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "supplier": 5,
                "api_domain": "https://example.com/v1",
                "api_key": "secret",
                "base_model": "deepseek-v4-flash",
            }
        )
    )

    assert result["success"] is False
    assert result["capabilities"]["chat"] is False
    assert "响应格式异常" in result["message"]


def test_check_embedding_status_uses_legacy_models_check_only():
    FakeAsyncClient.responses = [
        FakeResponse(payload={"data": [{"id": "text-embedding-model"}]}),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "model_type": 2,
                "supplier": 5,
                "api_domain": "https://example.com/v1/",
                "api_key": "secret",
                "base_model": "text-embedding-model",
            }
        )
    )

    assert result == {"success": True, "message": "连接成功"}
    assert FakeAsyncClient.requests == [
        (
            "GET",
            "https://example.com/v1/models",
            {
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer secret",
                },
                "timeout": 10,
            },
        )
    ]


def test_check_dashscope_rerank_status_posts_to_configured_endpoint():
    FakeAsyncClient.responses = [
        FakeResponse(
            payload={
                "output": {
                    "results": [
                        {"index": 0, "relevance_score": 0.9},
                    ]
                }
            }
        ),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "model_type": 3,
                "supplier": 6,
                "api_domain": (
                    "https://dashscope.aliyuncs.com/api/v1/services/"
                    "rerank/text-rerank/text-rerank"
                ),
                "api_key": "secret",
                "base_model": "qwen3-rerank",
            }
        )
    )

    assert result == {"success": True, "message": "连接成功"}
    assert len(FakeAsyncClient.requests) == 1
    assert FakeAsyncClient.requests[0][0:2] == (
        "POST",
        (
            "https://dashscope.aliyuncs.com/api/v1/services/"
            "rerank/text-rerank/text-rerank"
        ),
    )
    body = FakeAsyncClient.requests[0][2]["json"]
    assert body["model"] == "qwen3-rerank"
    assert body["input"]["query"] == "什么是文本排序模型"
    assert len(body["input"]["documents"]) == 2
    assert body["parameters"] == {
        "return_documents": False,
        "top_n": 2,
    }


def test_check_generic_rerank_status_uses_generic_payload():
    FakeAsyncClient.responses = [
        FakeResponse(
            payload={
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                ]
            }
        ),
    ]

    result = asyncio.run(
        aimodel_service.check_llm_status(
            {
                "model_type": 3,
                "supplier": 9,
                "api_domain": "https://example.com/rerank",
                "api_key": "secret",
                "base_model": "rerank-model",
            }
        )
    )

    assert result == {"success": True, "message": "连接成功"}
    assert FakeAsyncClient.requests[0][0:2] == (
        "POST",
        "https://example.com/rerank",
    )
    assert FakeAsyncClient.requests[0][2]["json"] == {
        "query": "什么是文本排序模型",
        "documents": [
            "文本排序模型根据相关性对候选文本进行排序",
            "量子计算是计算科学的前沿领域",
        ],
    }
