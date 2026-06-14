import logging

from sanic import Blueprint, Request
from sanic_ext import openapi

from services.db_qadata_process import select_report_by_title
from services.text2_sql_service import exe_sql_query
from common.exception import MyException
from constants.code_enum import SysCodeEnum
from common.res_decorator import async_json_resp
from common.param_parser import parse_params
from model.schemas import (
    ProcessLlmOutRequest,
    ProcessLlmOutResponse,
    QueryGuidedReportResponse,
    get_schema,
)

bp = Blueprint("text2sql", url_prefix="/llm")


@bp.post("/process_llm_out")
@openapi.summary("处理LLM输出的SQL")
@openapi.description("数据问答处理大模型返回的SQL语句并执行查询")
@openapi.tag("数据问答")
@openapi.body(
    {
        "application/x-www-form-urlencoded": {
            "schema": get_schema(ProcessLlmOutRequest),
        }
    },
    description="SQL语句",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(ProcessLlmOutResponse),
        }
    },
    description="查询成功",
)
@async_json_resp
@parse_params
async def process_llm_out(req: Request, llm_text: str):
    """
    数据问答处理大模型返回SQL语句
    :param req: 请求对象
    :param llm_text: SQL语句（从表单中解析）
    """
    try:
        logging.info(f"query param: {llm_text}")

        result = await exe_sql_query(llm_text)
        return result
    except Exception as e:
        logging.error(f"Error processing LLM output: {e}")
        raise MyException(SysCodeEnum.c_9999)


@bp.get("/query_guided_report")
@openapi.summary("查询引导报告")
@openapi.description("根据查询字符串查询相关的引导报告")
@openapi.tag("数据问答")
@openapi.parameter(
    name="query_str",
    location="query",
    schema={"type": "string"},
    description="查询字符串",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(QueryGuidedReportResponse),
        }
    },
    description="查询成功",
)
@async_json_resp
@parse_params
async def query_guided_report(req: Request, query_str: str):
    """
    查询报告
    :param req: 请求对象
    :param query_str: 查询字符串（查询参数）
    """
    try:
        question_str = query_str.strip().replace("\r", "")
        result = await select_report_by_title(question_str)
        return result
    except Exception as e:
        logging.error(f"查询报告失败: {e}")
        raise MyException(SysCodeEnum.c_9999)
