import json
import logging
import os
from datetime import datetime
from typing import List, Optional

from sqlalchemy import or_, text, desc, update
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage

from common.exception import MyException
from constants.code_enum import SysCodeEnum
from common.llm_util import get_llm
from model import Datasource
from model.db_connection_pool import get_db_pool
from model.db_models import TTerminology, TAiModel
from model.serializers import model_to_dict
from model.schemas import PaginatedResponse
from services.embedding_service import get_default_embedding_model

logger = logging.getLogger(__name__)
pool = get_db_pool()

# 是否启用 embedding 功能
EMBEDDING_ENABLED = os.getenv("EMBEDDING_ENABLED", "true").lower() == "true"


async def query_terminology_list(page: int, size: int, word: Optional[str] = None, dslist: Optional[List[int]] = None):
    """
    分页查询术语
    """
    with pool.get_session() as session:
        query = session.query(TTerminology)
        
        # 筛选条件
        filters = [TTerminology.pid.is_(None)] # 只查询父节点
        
        if word:
            # 搜索：匹配父节点名称或子节点(同义词)名称
            # 先找到匹配的ID
            matched_ids_query = session.query(TTerminology.id).filter(TTerminology.word.ilike(f"%{word}%"))
            matched_ids = [row[0] for row in matched_ids_query.all()]
            
            if matched_ids:
                # 查找这些ID及其父ID
                parent_ids_query = session.query(TTerminology.pid).filter(TTerminology.id.in_(matched_ids), TTerminology.pid.isnot(None))
                parent_ids = [row[0] for row in parent_ids_query.all()]
                
                # 合并ID：直接匹配的ID（如果是父节点） + 子节点对应的父ID
                all_candidate_ids = set(matched_ids) | set(parent_ids)
                filters.append(TTerminology.id.in_(all_candidate_ids))
            else:
                return PaginatedResponse(records=[], current_page=page, total_count=0, total_pages=0)

        if dslist:
             # 数据源筛选
             ds_conditions = [TTerminology.specific_ds == False]
             
             ds_str_list = [str(d) for d in dslist]
             ds_vals = ", ".join([f"'{d}'" for d in ds_str_list])
             if ds_vals:
                 ds_check = text(f"""
                    specific_ds = true AND datasource_ids IS NOT NULL AND EXISTS (
                        SELECT 1 FROM json_array_elements_text(datasource_ids::json) WHERE value IN ({ds_vals})
                    )
                 """)
                 ds_conditions.append(ds_check)
             
             filters.append(or_(*ds_conditions))

        query = query.filter(*filters)
        
        total_count = query.count()
        total_pages = (total_count + size - 1) // size
        
        records = query.order_by(desc(TTerminology.create_time)).offset((page - 1) * size).limit(size).all()
        
        result_list = []
        for record in records:
            item = model_to_dict(record)
            
            # 排除 embedding 字段（前端不需要，且可能包含 numpy 数组）
            if 'embedding' in item:
                del item['embedding']
            
            # 查询子节点（同义词）
            children = session.query(TTerminology).filter(TTerminology.pid == record.id).all()
            item['other_words'] = [c.word for c in children]
            
            # 解析 datasource_ids 获取名称
            item['datasource_names'] = []
            item['datasource_ids'] = []
            if record.specific_ds and record.datasource_ids:
                try:
                    ds_ids = json.loads(record.datasource_ids)
                    item['datasource_ids'] = ds_ids
                    if ds_ids:
                        ds_names = session.query(Datasource.name).filter(Datasource.id.in_(ds_ids)).all()
                        item['datasource_names'] = [r[0] for r in ds_names]
                except:
                    pass
            
            result_list.append(item)
            
        return PaginatedResponse(
            records=result_list,
            current_page=page,
            total_count=total_count,
            total_pages=total_pages,
        )

async def create_terminology(word: str, description: str, other_words: List[str], specific_ds: bool, datasource_ids: List[int], oid: int = 1):
    with pool.get_session() as session:
        # 检查重复
        all_words = [word] + other_words
        # 检查数据库中是否已存在这些词（作为父节点或子节点）
        existing = session.query(TTerminology).filter(TTerminology.word.in_(all_words)).first()
        if existing:
            raise MyException(SysCodeEnum.PARAM_ERROR, f"术语或同义词 '{existing.word}' 已存在")
            
        # 创建父节点
        parent = TTerminology(
            word=word,
            description=description,
            specific_ds=specific_ds,
            datasource_ids=json.dumps(datasource_ids) if datasource_ids else '[]',
            oid=oid,
            enabled=True,
            create_time=datetime.now()
        )
        session.add(parent)
        session.flush() # 获取ID
        
        # 创建子节点
        for ow in other_words:
            if not ow.strip():
                continue
            child = TTerminology(
                pid=parent.id,
                word=ow,
                specific_ds=specific_ds,
                datasource_ids=json.dumps(datasource_ids) if datasource_ids else '[]',
                oid=oid,
                enabled=True,
                create_time=datetime.now()
            )
            session.add(child)
            
        session.commit()
        
        # 计算并保存 embedding（异步处理，不阻塞）
        if EMBEDDING_ENABLED:
            try:
                await save_terminology_embeddings([parent.id])
            except Exception as e:
                logger.warning(f"保存术语 embedding 失败: {e}", exc_info=True)
                # 不抛出异常，避免影响创建流程
        
        return True

async def update_terminology(id: int, word: str, description: str, other_words: List[str], specific_ds: bool, datasource_ids: List[int], oid: int = 1):
    with pool.get_session() as session:
        parent = session.query(TTerminology).filter(TTerminology.id == id).first()
        if not parent:
            raise MyException(SysCodeEnum.PARAM_ERROR, "术语不存在")
            
        # 检查重复 (排除自己和自己的子节点)
        all_words = [word] + other_words
        existing = session.query(TTerminology).filter(
            TTerminology.word.in_(all_words),
            TTerminology.id != id,
            or_(TTerminology.pid != id, TTerminology.pid.is_(None)) 
        ).first()
        
        if existing:
             raise MyException(SysCodeEnum.PARAM_ERROR, f"术语或同义词 '{existing.word}' 已存在")

        # 更新父节点
        parent.word = word
        parent.description = description
        parent.specific_ds = specific_ds
        parent.datasource_ids = json.dumps(datasource_ids) if datasource_ids else '[]'
        
        # 删除旧子节点
        session.query(TTerminology).filter(TTerminology.pid == id).delete()
        
        # 添加新子节点
        for ow in other_words:
            if not ow.strip():
                continue
            child = TTerminology(
                pid=parent.id,
                word=ow,
                specific_ds=specific_ds,
                datasource_ids=json.dumps(datasource_ids) if datasource_ids else '[]',
                oid=oid,
                enabled=parent.enabled,
                create_time=datetime.now()
            )
            session.add(child)
            
        session.commit()
        
        # 计算并保存 embedding（异步处理，不阻塞）
        if EMBEDDING_ENABLED:
            try:
                await save_terminology_embeddings([id])
            except Exception as e:
                logger.warning(f"保存术语 embedding 失败: {e}", exc_info=True)
                # 不抛出异常，避免影响更新流程
        
        return True

async def delete_terminology(ids: List[int]):
    with pool.get_session() as session:
        # 删除父节点和子节点
        session.query(TTerminology).filter(or_(TTerminology.id.in_(ids), TTerminology.pid.in_(ids))).delete(synchronize_session=False)
        session.commit()
        return True

async def enable_terminology(id: int, enabled: bool):
    with pool.get_session() as session:
        # 更新父节点和子节点
        session.query(TTerminology).filter(or_(TTerminology.id == id, TTerminology.pid == id)).update({TTerminology.enabled: enabled}, synchronize_session=False)
        session.commit()
        return True

async def get_terminology_detail(id: int):
    with pool.get_session() as session:
        record = session.query(TTerminology).filter(TTerminology.id == id).first()
        if not record:
            return None
            
        item = model_to_dict(record)
        
        # 排除 embedding 字段（前端不需要，且可能包含 numpy 数组）
        if 'embedding' in item:
            del item['embedding']
        
        # 查询子节点
        children = session.query(TTerminology).filter(TTerminology.pid == record.id).all()
        item['other_words'] = [c.word for c in children]
        
        # 解析 datasource_ids
        item['datasource_ids'] = []
        item['datasource_names'] = []
        if record.datasource_ids:
            try:
                ds_ids = json.loads(record.datasource_ids)
                item['datasource_ids'] = ds_ids
                if ds_ids:
                    ds_names = session.query(Datasource.name).filter(Datasource.id.in_(ds_ids)).all()
                    item['datasource_names'] = [r[0] for r in ds_names]
            except:
                pass
                
        return item

async def generate_synonyms_by_llm(word: str) -> List[str]:
    """
    使用LLM生成同义词
    """
    try:
        llm = get_llm()
        prompt = f"""
        请为术语 "{word}" 生成5个同义词，用于数据分析和商业智能场景。
        请直接返回JSON数组格式的字符串，例如 ["词1", "词2"]。
        不要包含Markdown标记或其他文本。
        """
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        
        # 清理可能存在的markdown代码块标记
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
            
        try:
            result = json.loads(content)
            if isinstance(result, list):
                return [str(w) for w in result]
            else:
                return []
        except json.JSONDecodeError:
            # 如果解析失败，尝试按逗号分割
            return [w.strip() for w in content.split(",") if w.strip()]
            
    except Exception as e:
        logger.error(f"Error generating synonyms: {e}")
        # 如果是因为没有配置模型，抛出特定错误
        if "No default AI model" in str(e):
             raise MyException(SysCodeEnum.PARAM_ERROR, "未配置默认AI模型，请先在模型管理中配置")
        raise MyException(SysCodeEnum.c_9999, f"AI生成失败: {str(e)}")


def _save_terminology_embeddings_sync(ids: List[int]):
    """
    同步版本：计算并保存术语的 embedding（在后台线程中执行）
    
    Args:
        ids: 术语ID列表（父节点ID），会自动处理子节点
    """
    if not EMBEDDING_ENABLED:
        return
    
    if not ids or len(ids) == 0:
        return
    
    try:
        with pool.get_session() as session:
            # 查询术语及其子节点（所有需要计算 embedding 的术语）
            # 使用 or_(id.in_(ids), pid.in_(ids)) 查询父节点和所有子节点
            terminology_list = session.query(TTerminology).filter(
                or_(TTerminology.id.in_(ids), TTerminology.pid.in_(ids))
            ).all()
            
            if not terminology_list:
                return
            
            # 收集所有术语的 word（用于批量生成 embedding）
            words_list = [term.word for term in terminology_list if term.word]
            
            if not words_list:
                return
            
            logger.info(f"开始计算 {len(words_list)} 个术语的 embedding（父节点和子节点）...")
            
            # 批量生成 embedding（优先使用用户配置的模型，没有则使用离线模型）
            # 术语 embedding 存储在 pgvector 中
            embeddings = []
            try:
                # 尝试获取在线模型配置（同步方式）
                model_config = None
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    model_config = loop.run_until_complete(get_default_embedding_model())
                    loop.close()
                except Exception as e:
                    logger.debug(f"获取在线模型配置失败: {e}，将使用离线模型")
                
                if model_config:
                    # 使用在线模型逐个生成（在线模型通常不支持批量）
                    from openai import OpenAI
                    
                    # 处理 Ollama 特殊格式
                    base_url = model_config["api_domain"]
                    if model_config["supplier"] == 3:  # Ollama
                        if not base_url.endswith("/v1"):
                            base_url = f"{base_url.rstrip('/')}/v1"
                    
                    client = OpenAI(
                        api_key=model_config["api_key"] or "empty",
                        base_url=base_url
                    )
                    
                    embeddings = []
                    for word in words_list:
                        try:
                            response = client.embeddings.create(model=model_config["base_model"], input=word)
                            if response.data:
                                embeddings.append(response.data[0].embedding)
                            else:
                                embeddings.append(None)
                        except Exception as e:
                            logger.warning(f"在线模型生成术语 '{word}' 的 embedding 失败: {e}，跳过")
                            embeddings.append(None)
                    
                    success_count = sum(1 for e in embeddings if e is not None)
                    logger.info(f"✅ 使用在线模型生成 {success_count}/{len(words_list)} 个术语 embedding")
                else:
                    # 使用离线模型批量生成
                    from common.local_embedding import _get_local_embedding_model
                    local_model = _get_local_embedding_model()
                    
                    if not local_model:
                        logger.error("❌ 本地 embedding 模型不可用，无法计算术语 embedding")
                        return
                    
                    # 使用本地模型的批量方法
                    if hasattr(local_model, 'embed_documents'):
                        embeddings = local_model.embed_documents(words_list)
                        logger.info(f"✅ 使用离线模型批量生成 {len(embeddings)} 个术语 embedding（维度: 768）")
                    else:
                        # 如果没有 embed_documents，逐个生成
                        from common.local_embedding import generate_embedding_local_sync
                        embeddings = [generate_embedding_local_sync(word) for word in words_list]
                        logger.info(f"✅ 使用离线模型逐个生成 {len(embeddings)} 个术语 embedding（维度: 768）")
                        
            except Exception as e:
                logger.error(f"批量生成术语 embedding 失败: {e}", exc_info=True)
                return
            
            # 逐个更新到数据库（每个更新单独 commit，避免一个失败影响其他）
            success_count = 0
            for index in range(len(terminology_list)):
                if index < len(embeddings) and embeddings[index] is not None:
                    term = terminology_list[index]
                    try:
                        stmt = update(TTerminology).where(
                            TTerminology.id == term.id
                        ).values(embedding=embeddings[index])
                        session.execute(stmt)
                        session.commit()  # 每个更新单独 commit
                        success_count += 1
                        logger.debug(f"✅ 成功更新术语 {term.id} ({term.word}) 的 embedding")
                    except Exception as e:
                        error_msg = str(e)
                        # 检查是否是维度不匹配错误
                        if "expected" in error_msg and "dimensions" in error_msg:
                            logger.error(
                                f"❌ 术语 {term.id} ({term.word}) 的 embedding 维度不匹配: {e}。"
                            )
                        else:
                            logger.error(f"更新术语 {term.id} ({term.word}) 的 embedding 失败: {e}")
                        # 回滚当前事务，继续处理下一个
                        try:
                            session.rollback()
                        except:
                            pass
                        # 继续处理下一个，不中断
            
            logger.info(f"✅ 成功保存 {success_count}/{len(terminology_list)} 个术语的 embedding")
            
    except Exception as e:
        logger.error(f"保存术语 embedding 失败: {e}", exc_info=True)
        # 不抛出异常，避免影响主流程


async def save_terminology_embeddings(ids: List[int]):
    """
    异步包装：在后台线程中执行 embedding 计算和保存
    
    Args:
        ids: 术语ID列表（父节点ID），会自动处理子节点
    """
    if not EMBEDDING_ENABLED:
        return
    
    if not ids or len(ids) == 0:
        return
    
    # 在后台线程中执行，不阻塞主流程
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _save_terminology_embeddings_sync, ids)
