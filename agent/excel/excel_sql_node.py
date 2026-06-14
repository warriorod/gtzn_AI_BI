"""
表格问答 SQL 生成节点
使用模板系统生成 SQL 语句
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.template.prompt_builder import ExcelPromptBuilder
from agent.excel.template.schema_formatter import format_excel_schema_to_m_schema, get_excel_engine_info
from common.llm_util import get_llm

logger = logging.getLogger(__name__)


def sql_generate_excel(state: ExcelAgentState) -> ExcelAgentState:
    """
    使用模板系统生成 SQL 语句
    
    Args:
        state: Excel Agent 状态对象
        
    Returns:
        更新后的 state
    """
    try:
        # 获取数据库信息
        db_info = state.get("db_info", [])
        if not db_info:
            logger.error("db_info 为空，无法生成 SQL")
            state["generated_sql"] = "No SQL query generated"
            state["chart_type"] = None
            return state
        
        # 格式化 schema 为 M-Schema 格式
        schema_str = format_excel_schema_to_m_schema(db_info)
        logger.debug(f"Schema 格式化完成，包含 {len(db_info)} 张表")
        
        # 获取数据库引擎信息
        engine = get_excel_engine_info()
        
        # 使用 PromptBuilder 构建提示词
        prompt_builder = ExcelPromptBuilder()
        
        error_msg = ""  # 错误消息（暂时为空）
        
        # 获取系统提示词和用户提示词
        system_prompt, user_prompt = prompt_builder.build_sql_prompt(
            schema=schema_str,
            question=state["user_query"],
            engine=engine,
            lang="简体中文",
            enable_query_limit=True,  # 启用查询限制
            error_msg=error_msg,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        
        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        
        # 调用 LLM
        llm = get_llm()
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
        import re
        result = None
        try:
            # 先尝试直接解析
            result = json.loads(response_content)
        except json.JSONDecodeError as e:
            # 如果失败，尝试修复转义序列
            logger.warning(f"首次 JSON 解析失败: {e}，尝试修复转义序列")
            try:
                def fix_sql_field(match):
                    prefix = match.group(1)
                    sql_content = match.group(2)
                    suffix = match.group(3)
                    fixed_sql = re.sub(r'\\\s*\n\s*', ' ', sql_content)
                    return f'{prefix}{fixed_sql}{suffix}'
                
                fixed_content = re.sub(
                    r'("sql"\s*:\s*")(.*?)(")',
                    fix_sql_field,
                    response_content,
                    flags=re.DOTALL
                )
                
                result = json.loads(fixed_content)
                logger.info("通过修复转义序列成功解析 JSON")
            except (json.JSONDecodeError, Exception) as e2:
                logger.error(f"修复转义序列后仍然失败: {e2}")
                result = None
        
        # 处理解析结果
        if result and result.get("success", True):
            # 成功生成 SQL
            sql = result.get("sql", "")
            if isinstance(sql, str):
                state["generated_sql"] = sql
            else:
                state["generated_sql"] = str(sql) if sql else ""
            
            # 图表类型：从 chart-type 字段获取，默认为 table
            chart_type = result.get("chart-type", result.get("chart_type", "table"))
            state["chart_type"] = chart_type
            
            # 保存使用的表名（如果模板返回了 tables 字段）
            if "tables" in result:
                tables = result.get("tables", [])
                if isinstance(tables, list):
                    state["used_tables"] = tables
                    logger.info(f"SQL 使用的表: {tables}")
            
            # 保存完整的 SQL 生成响应 JSON（用于前端显示）
            sql_response_json = {
                "success": True,
                "sql": state["generated_sql"],
                "tables": result.get("tables", []),
                "chart-type": chart_type
            }
            state["sql_response_json"] = sql_response_json
        elif result:
            # 生成失败（success 为 false）
            error_message = result.get("message", "无法生成 SQL")
            logger.warning(f"SQL 生成失败: {error_message}")
            state["generated_sql"] = "No SQL query generated"
            state["chart_type"] = None
        else:
            # 解析完全失败
            logger.error(f"解析 LLM 响应 JSON 失败，响应内容: {response_content[:500]}")
            state["generated_sql"] = "No SQL query generated"
            state["chart_type"] = None

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"SQL 生成过程中发生错误: {e}", exc_info=True)
        state["generated_sql"] = "No SQL query generated"
        state["chart_type"] = None

    return state
