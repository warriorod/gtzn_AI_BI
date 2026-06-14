"""
动态 SQL 生成节点
用于处理动态数据源场景，将 SQL 查询中的表名替换为对应的子查询
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List

from langchain_core.messages import SystemMessage, HumanMessage

from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.template import PromptBuilder, get_database_engine_info
from common.llm_util import get_llm

logger = logging.getLogger(__name__)


async def dynamic_sql_generator(
    state: AgentState,
    sql: str,
    sub_query: List[Dict[str, str]],
) -> Optional[str]:
    """
    动态 SQL 生成函数
    将 SQL 查询中的表名替换为对应的子查询
    
    Args:
        state: Agent 状态对象（用于获取数据库类型等信息）
        sql: 原始 SQL 语句
        sub_query: 子查询映射表 [{"table": "表名", "query": "子查询语句"}, ...]
    
    Returns:
        生成的动态 SQL 语句，如果生成失败则返回 None
    """
    logger.info("---进入动态 SQL 生成节点---")

    if not sql or not sub_query:
        logger.warning("SQL 或子查询映射表为空，无法生成动态 SQL")
        return None

    # 获取数据库类型（用于确定引擎规范）
    datasource_id = state.get("datasource_id")
    db_type = "mysql"  # 默认类型

    if datasource_id:
        try:
            from model.db_connection_pool import get_db_pool
            from services.datasource_service import DatasourceService

            db_pool = get_db_pool()
            with db_pool.get_session() as session:
                ds = DatasourceService.get_datasource_by_id(session, datasource_id)
                if ds:
                    db_type = ds.type
        except Exception as e:
            logger.warning(f"获取数据源信息失败: {e}，使用默认值")

    # 获取数据库引擎信息
    engine = get_database_engine_info(db_type)

    # 使用 PromptBuilder 构建动态 SQL 提示词
    prompt_builder = PromptBuilder()

    try:
        system_prompt, user_prompt = prompt_builder.build_dynamic_sql_prompt(
            sql=sql,
            sub_query=sub_query,
            engine=engine,
            lang="简体中文",
        )

        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 调用 LLM
        llm = get_llm(0)
        response = llm.invoke(messages)

        # 解析响应（JSON 格式）
        response_content = response.content.strip()

        # 清理 JSON 字符串（移除可能的 markdown 代码块标记）
        if "```json" in response_content:
            response_content = response_content.split("```json")[1]
        if "```" in response_content:
            response_content = response_content.split("```")[0]
        response_content = response_content.strip()

        # 解析 JSON
        try:
            result = json.loads(response_content)

            # 检查是否成功生成 SQL
            if "success" in result and result["success"]:
                generated_sql = result.get("sql", "")
                if generated_sql:
                    logger.info("动态 SQL 生成成功")
                    return generated_sql
                else:
                    logger.warning("LLM 响应中缺少 SQL 字段")
                    return None
            else:
                error_msg = result.get("message", "未知错误")
                logger.warning(f"LLM 未能生成动态 SQL: {error_msg}")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应 JSON 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            return None

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"动态 SQL 生成过程中发生错误: {e}", exc_info=True)
        return None


async def dynamic_sql_generator_node(state: AgentState) -> AgentState:
    """
    动态 SQL 生成节点（LangGraph 节点）
    
    注意：这是一个可选节点，通常不会直接集成到主工作流中
    而是作为工具函数在需要时调用
    
    Args:
        state: Agent 状态对象
    
    Returns:
        更新后的 state
    """
    logger.info("---进入动态 SQL 生成节点（LangGraph）---")

    # 获取原始 SQL
    sql = state.get("generated_sql") or state.get("filtered_sql")
    if not sql:
        logger.warning("SQL 为空，跳过动态 SQL 生成")
        return state

    # 获取子查询映射表（从 state 中获取，如果存在的话）
    sub_query = state.get("sub_query_mapping", [])
    if not sub_query:
        logger.info("子查询映射表为空，跳过动态 SQL 生成")
        return state

    # 调用动态 SQL 生成函数
    generated_sql = await dynamic_sql_generator(state, sql, sub_query)

    if generated_sql:
        # 将生成的动态 SQL 保存到 state
        state["dynamic_sql"] = generated_sql
        logger.info("动态 SQL 生成成功并保存到 state")
    else:
        logger.warning("动态 SQL 生成失败")

    return state
