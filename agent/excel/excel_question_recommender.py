"""
表格问答推荐问题生成节点
根据当前 Excel 表结构和用户查询，生成相关的推荐问题
"""

import json
import logging
import traceback
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.template.prompt_builder import ExcelPromptBuilder
from agent.excel.template.schema_formatter import format_excel_schema_to_m_schema
from common.llm_util import get_llm

logger = logging.getLogger(__name__)


async def excel_question_recommender(state: ExcelAgentState) -> ExcelAgentState:
    """
    推荐问题生成节点
    1. 获取当前 Excel 文件的 schema
    2. 使用 LLM 根据 schema 和用户查询生成推荐问题
    3. 保存推荐问题到 state["recommended_questions"]
    """
    logger.info("---进入推荐问题生成节点---")

    # 获取用户查询
    user_query = state.get("user_query", "")

    # 获取数据库信息（schema）
    db_info = state.get("db_info", [])
    if not db_info:
        logger.warning("数据库信息为空，无法生成推荐问题")
        state["recommended_questions"] = []
        return state

    # 格式化 schema 为 M-Schema 格式
    try:
        schema_str = format_excel_schema_to_m_schema(db_info)
    except Exception as e:
        logger.error(f"格式化 schema 失败: {e}", exc_info=True)
        state["recommended_questions"] = []
        return state

    # 获取历史问题列表（如果有的话，可以从 state 中获取或从数据库查询）
    # 目前暂时使用空列表
    old_questions: List[str] = []

    # 使用 PromptBuilder 构建推荐问题提示词
    prompt_builder = ExcelPromptBuilder()

    try:
        system_prompt, user_prompt = prompt_builder.build_guess_question_prompt(
            schema=schema_str,
            question=user_query,
            old_questions=old_questions,
            lang="简体中文",
            articles_number=4,  # 生成 4 个推荐问题
        )

        # 构建消息列表
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # 调用 LLM
        llm = get_llm(0)
        response = llm.invoke(messages)

        # 解析响应（JSON 数组格式）
        response_content = response.content.strip()

        # 清理 JSON 字符串（移除可能的 markdown 代码块标记）
        if "```json" in response_content:
            response_content = response_content.split("```json")[1]
        if "```" in response_content:
            response_content = response_content.split("```")[0]
        response_content = response_content.strip()

        # 解析 JSON
        try:
            recommended_questions = json.loads(response_content)

            # 验证响应格式
            if isinstance(recommended_questions, list):
                # 确保所有元素都是字符串
                recommended_questions = [str(q) for q in recommended_questions if q]
                state["recommended_questions"] = recommended_questions
                logger.info(f"生成 {len(recommended_questions)} 个推荐问题")
            else:
                logger.warning(f"推荐问题格式错误，期望列表，得到: {type(recommended_questions)}")
                state["recommended_questions"] = []

        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应 JSON 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            state["recommended_questions"] = []

    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"推荐问题生成过程中发生错误: {e}", exc_info=True)
        state["recommended_questions"] = []

    return state

