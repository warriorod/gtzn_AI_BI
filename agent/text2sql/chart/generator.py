"""
图表配置生成节点
使用 LLM 根据 SQL 执行结果生成图表配置（AntV 格式）
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List

from langchain_core.messages import SystemMessage, HumanMessage

from agent.common.json_value import convert_value_for_json
from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.template.prompt_builder import PromptBuilder
from common.llm_util import get_llm

logger = logging.getLogger(__name__)


def prepare_data_for_json(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    准备数据用于JSON序列化，转换所有Decimal、datetime等类型
    
    Args:
        data: 原始数据列表
    
    Returns:
        转换后的数据列表，所有值都是JSON可序列化的
    """
    converted_data = []
    for row in data:
        converted_row = {}
        for key, value in row.items():
            converted_row[key] = convert_value_for_json(value)
        converted_data.append(converted_row)
    return converted_data


def chart_generator(state: AgentState) -> AgentState:
    """
    图表配置生成节点
    使用 LLM 根据 SQL 执行结果生成图表配置（JSON 格式，适配 AntV 组件）
    
    Args:
        state: Agent 状态对象
        
    Returns:
        更新后的 state
    """
    try:
        # 获取 SQL 执行结果
        execution_result = state.get("execution_result")
        if not execution_result or not execution_result.success:
            logger.warning("SQL 执行失败或结果为空，跳过图表生成")
            return state
        
        data = execution_result.data or []
        if not data:
            logger.warning("SQL 执行结果数据为空，跳过图表生成")
            return state
        
        # 获取生成的SQL和用户查询
        generated_sql = state.get("generated_sql") or state.get("filtered_sql")
        user_query = state.get("user_query", "")
        chart_type = state.get("chart_type", "table")
        
        # 使用图表类型（包括 table 类型，table 类型也需要生成图表配置以获取字段映射）
        chart_type_simple = chart_type
        
        # 使用 PromptBuilder 构建图表生成提示词
        prompt_builder = PromptBuilder()
        
        # 将数据转换为字符串（限制数据量，避免提示词过长）
        data_preview = data[:10]  # 只使用前10条数据作为示例
        # 转换Decimal、datetime等类型为JSON可序列化的格式
        data_preview_converted = prepare_data_for_json(data_preview)
        data_str = json.dumps(data_preview_converted, ensure_ascii=False, indent=2)
        
        system_prompt, user_prompt = prompt_builder.build_chart_prompt(
            sql=generated_sql or "",
            question=user_query,
            chart_type=chart_type_simple,
            lang="简体中文",
        )
        
        # 将数据添加到用户提示词中
        # 注意：如果模板中没有数据占位符，我们需要手动添加
        if "{data}" not in user_prompt:
            user_prompt = user_prompt + f"\n\n<data>\n{data_str}\n</data>"
        else:
            user_prompt = user_prompt.format(data=data_str)
        
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
            chart_config = json.loads(response_content)
            
            # 验证图表配置格式
            if isinstance(chart_config, dict):
                # 确保包含必要的字段
                if "type" not in chart_config:
                    chart_config["type"] = chart_type_simple
                
                # 对所有value字段进行lowercase处理，确保后续映射时能正确匹配
                # 处理columns字段（表格类型）
                if chart_config.get('columns'):
                    for col in chart_config.get('columns', []):
                        if isinstance(col, dict) and col.get('value'):
                            col['value'] = col.get('value').lower()
                
                # 处理axis字段（图表类型）
                if chart_config.get('axis'):
                    axis = chart_config.get('axis', {})
                    if isinstance(axis, dict):
                        for axis_key in ['x', 'y', 'series']:
                            axis_item = axis.get(axis_key)
                            if isinstance(axis_item, dict) and axis_item.get('value'):
                                axis_item['value'] = axis_item.get('value').lower()
                
                # 将图表配置保存到 state
                state["chart_config"] = chart_config
                logger.info(f"图表配置生成成功，类型: {chart_config.get('type', chart_type_simple)}")
            else:
                logger.warning(f"图表配置格式错误，期望字典，得到: {type(chart_config)}")
                state["chart_config"] = None
                
        except json.JSONDecodeError as e:
            logger.error(f"解析 LLM 响应 JSON 失败: {e}")
            logger.error(f"响应内容: {response_content[:500]}")
            state["chart_config"] = None
        
    except Exception as e:
        traceback.print_exception(e)
        logger.error(f"图表配置生成过程中发生错误: {e}", exc_info=True)
        state["chart_config"] = None
    
    return state
