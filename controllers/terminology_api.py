from sanic import Blueprint, Request
from sanic_ext import openapi

from common.res_decorator import async_json_resp
from common.token_decorator import check_token
from common.param_parser import parse_params
from services.terminology_service import (
    query_terminology_list,
    create_terminology,
    update_terminology,
    delete_terminology,
    enable_terminology,
    get_terminology_detail,
    generate_synonyms_by_llm
)
from model.schemas import (
    get_schema,
    QueryTerminologyRequest,
    TerminologyListResponse,
    SaveTerminologyRequest,
    BaseResponse,
    DeleteTerminologyRequest,
    GenerateSynonymsRequest,
    GenerateSynonymsResponse
)

bp = Blueprint("terminology", url_prefix="/terminology")

@bp.post("/list")
@openapi.summary("分页查询术语")
@openapi.tag("术语管理")
@openapi.body({"application/json": {"schema": get_schema(QueryTerminologyRequest)}}, required=True)
@openapi.response(200, {"application/json": {"schema": get_schema(TerminologyListResponse)}})
@check_token
@async_json_resp
@parse_params
async def list_terminology(request: Request, body: QueryTerminologyRequest):
    return await query_terminology_list(body.page, body.size, body.word, body.dslist)

@bp.post("/save")
@openapi.summary("保存术语(新增/修改)")
@openapi.tag("术语管理")
@openapi.body({"application/json": {"schema": get_schema(SaveTerminologyRequest)}}, required=True)
@openapi.response(200, {"application/json": {"schema": get_schema(BaseResponse)}})
@check_token
@async_json_resp
@parse_params
async def save_term(request: Request, body: SaveTerminologyRequest):
    if body.id:
        return await update_terminology(
            body.id, 
            body.word, 
            body.description, 
            body.other_words, 
            body.specific_ds, 
            body.datasource_ids
        )
    else:
        return await create_terminology(
            body.word, 
            body.description, 
            body.other_words, 
            body.specific_ds, 
            body.datasource_ids
        )

@bp.post("/delete")
@openapi.summary("删除术语")
@openapi.tag("术语管理")
@openapi.body({"application/json": {"schema": get_schema(DeleteTerminologyRequest)}}, required=True)
@openapi.response(200, {"application/json": {"schema": get_schema(BaseResponse)}})
@check_token
@async_json_resp
@parse_params
async def delete_term(request: Request, body: DeleteTerminologyRequest):
    return await delete_terminology(body.ids)

@bp.get("/<id:int>/enable/<enabled:int>")
@openapi.summary("启用/禁用术语")
@openapi.tag("术语管理")
@check_token
@async_json_resp
async def enable_term(request: Request, id: int, enabled: int):
    return await enable_terminology(id, bool(enabled))

@bp.get("/<id:int>")
@openapi.summary("获取术语详情")
@openapi.tag("术语管理")
@check_token
@async_json_resp
async def get_term(request: Request, id: int):
    return await get_terminology_detail(id)

@bp.post("/generate_synonyms")
@openapi.summary("AI生成同义词")
@openapi.tag("术语管理")
@openapi.body({"application/json": {"schema": get_schema(GenerateSynonymsRequest)}}, required=True)
@openapi.response(200, {"application/json": {"schema": get_schema(GenerateSynonymsResponse)}})
@check_token
@async_json_resp
@parse_params
async def gen_synonyms(request: Request, body: GenerateSynonymsRequest):
    return await generate_synonyms_by_llm(body.word)
