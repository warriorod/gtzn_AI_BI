import logging
from typing import Optional

from common.exception import MyException
from common.minio_util import MinioUtils
from common.res_decorator import async_json_resp
from constants.code_enum import SysCodeEnum
from sanic import Blueprint, Request
from services.file_chat_service import read_excel, read_file_columns
from services.text2_sql_service import exe_file_sql_query
from sanic_ext import openapi
from common.param_parser import parse_params
from model.schemas import (
    ReadFileRequest,
    ReadFileResponse,
    ReadFileColumnRequest,
    ReadFileColumnResponse,
    UploadFileResponse,
    UploadFileAndParseResponse,
    ProcessFileLlmOutRequest,
    ProcessFileLlmOutResponse,
    get_schema,
)

bp = Blueprint("fileChatApi", url_prefix="/file")

minio_utils = MinioUtils()


@bp.post("/read_file")
@openapi.summary("读取文件内容")
@openapi.description("读取Excel文件的第一行内容（表头）")
@openapi.tag("文件服务")
@openapi.parameter(
    name="file_qa_str",
    location="query",
    schema={"type": "string"},
    description="文件地址（MinIO对象key）",
    required=False,
)
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(ReadFileRequest),
        }
    },
    description="文件地址（可通过query参数或body传递）",
    required=False,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(ReadFileResponse),
        }
    },
    description="文件内容",
)
@async_json_resp
@parse_params
async def read_file(request: Request, file_qa_str: Optional[str] = None, body: Optional[ReadFileRequest] = None) -> dict:
    """
    读取excel文件第一行内容
    :param request: 请求对象
    :param file_qa_str: 文件地址（从query参数自动解析）
    :param body: 请求体（从JSON自动解析）
    """
    # 优先使用query参数，否则使用body
    file_key = file_qa_str
    if not file_key and body:
        file_key = body.file_qa_str

    file_key = file_key.split("|")[0]  # 取文档地址

    file_url = minio_utils.get_file_url_by_key(object_key=file_key)
    result = await read_excel(file_url)
    return result


@bp.post("/read_file_column")
@openapi.summary("读取文件列信息")
@openapi.description("读取Excel文件的列信息（表头）")
@openapi.tag("文件服务")
@openapi.parameter(
    name="file_qa_str",
    location="query",
    schema={"type": "string"},
    description="文件地址（MinIO对象key）",
    required=False,
)
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(ReadFileColumnRequest),
        }
    },
    description="文件地址（可通过query参数或body传递）",
    required=False,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(ReadFileColumnResponse),
        }
    },
    description="列信息",
)
@async_json_resp
@parse_params
async def read_file_column(req: Request, file_qa_str: Optional[str] = None, body: Optional[ReadFileColumnRequest] = None):
    """
    读取excel文件列信息
    :param req: 请求对象
    :param file_qa_str: 文件地址（可通过query参数或body传递）
    :param body: 请求体
    :return:
    """
    file_key = file_qa_str
    if not file_key and body:
        file_key = body.file_qa_str

    file_key = file_key.split("|")[0]  # 取文档地址

    file_url = minio_utils.get_file_url_by_key(object_key=file_key)
    result = await read_file_columns(file_url)
    return result


@bp.post("/upload_file")
@openapi.summary("上传文件")
@openapi.description("上传文件到MinIO存储")
@openapi.tag("文件服务")
@openapi.body(
    {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": "要上传的文件",
                    },
                },
                "required": ["file"],
            }
        }
    },
    description="文件上传",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(UploadFileResponse),
        }
    },
    description="上传成功",
)
@async_json_resp
async def upload_file(request: Request):
    """
    上传附件
    :param request:
    :return:
    """
    file_key = minio_utils.upload_file_from_request(request=request)
    return file_key


@bp.post("/upload_file_and_parse")
@openapi.summary("上传文件并解析")
@openapi.description("上传文件到MinIO并解析文件内容")
@openapi.tag("文件服务")
@openapi.body(
    {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": "要上传的文件",
                    },
                },
                "required": ["file"],
            }
        }
    },
    description="文件上传",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(UploadFileAndParseResponse),
        }
    },
    description="上传并解析成功",
)
@async_json_resp
async def upload_file_and_parse(request: Request):
    """
    上传附件并解析内容
    :param request:
    :return:
    """
    file_key_dict = minio_utils.upload_file_and_parse_from_request(request=request)
    return file_key_dict


@bp.post("/process_file_llm_out")
@openapi.summary("处理文件问答LLM输出")
@openapi.description("处理文件问答中大模型返回的SQL语句并执行查询")
@openapi.tag("文件服务")
@openapi.parameter(
    name="file_key",
    location="query",
    schema={"type": "string"},
    description="文件key（MinIO对象key）",
    required=True,
)
@openapi.body(
    {
        "application/json": {
            "schema": get_schema(ProcessFileLlmOutRequest),
        }
    },
    description="SQL语句（通过body传递）",
    required=True,
)
@openapi.response(
    200,
    {
        "application/json": {
            "schema": get_schema(ProcessFileLlmOutResponse),
        }
    },
    description="查询成功",
)
@async_json_resp
@parse_params
async def process_file_llm_out(req: Request, file_key: str, body: ProcessFileLlmOutRequest):
    """
    文件问答处理大模型返回SQL语句
    :param req: 请求对象
    :param file_key: 文件key（查询参数）
    :param body: SQL请求体（自动从请求中解析）
    """
    try:
        body_str = body.sql
        logging.info(f"query param: {body_str}")

        result = await exe_file_sql_query(file_key, body_str)
        return result
    except Exception as e:
        logging.error(f"Error processing LLM output: {e}")
        raise MyException(SysCodeEnum.c_9999)
