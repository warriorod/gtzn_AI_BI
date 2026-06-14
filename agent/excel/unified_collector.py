"""
表格问答统一收集器
按顺序收集并推送：summarize → 图表数据 → 推荐问题
"""
import logging

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.excel_data_render_antv import excel_data_render_antv
from agent.excel.excel_data_render_apache import excel_data_render_apache

logger = logging.getLogger(__name__)


def unified_collect(state: ExcelAgentState) -> ExcelAgentState:
    """
    统一收集节点
    按顺序收集：summarize → 图表数据 → 推荐问题
    
    这个节点会：
    1. 确保 summarize 结果已准备好
    2. 根据 chart_type 调用相应的 data_render 生成图表数据
    3. 等待并合并推荐问题（如果早期任务存在）
    
    Args:
        state: ExcelAgent 状态对象（包含 parallel_collector 的结果）
        
    Returns:
        更新后的 state，包含所有收集的数据
    """
    logger.info("📦 开始统一收集：summarize → 图表数据 → 推荐问题")
    
    # 1. 确保 summarize 结果已准备好（应该已经在 parallel_collector 中完成）
    if "report_summary" not in state or not state.get("report_summary"):
        logger.warning("⚠️ summarize 结果为空，跳过")
    
    # 2. 生成图表数据（根据 chart_type 选择渲染方式）
    try:
        if "chart_config" in state and state.get("chart_config"):
            logger.info("📊 生成图表数据...")
            
            # 根据 chart_type 选择渲染方式（和 data_render_condition 逻辑一致）
            chart_type_value = state.get("chart_type") or ""
            chart_type = chart_type_value.lower() if isinstance(chart_type_value, str) else ""
            
            if not chart_type or chart_type == "table":
                # 表格类型使用 apache 渲染
                state = excel_data_render_apache(state)
            else:
                # 其他图表类型使用 antv 渲染
                state = excel_data_render_antv(state)
            
            logger.info("✅ 图表数据生成完成")
        else:
            logger.warning("⚠️ chart_config 为空，跳过图表数据生成")
    except Exception as e:
        logger.error(f"❌ 生成图表数据失败: {e}", exc_info=True)
    
    # 3. 等待并合并推荐问题（如果早期任务存在）
    try:
        if "_early_recommender_task_id" in state and state.get("_early_recommender_task_id"):
            logger.info("📋 等待并合并推荐问题...")
            from agent.excel.early_recommender_helper import wait_and_merge_early_recommender
            state = wait_and_merge_early_recommender(state)
            logger.info("✅ 推荐问题合并完成")
        
        # 如果推荐问题仍然为空，回退到直接生成
        if "recommended_questions" not in state or not state.get("recommended_questions"):
            logger.info("📋 推荐问题为空，回退到直接生成...")
            from agent.excel.early_recommender_helper import wait_and_merge_early_recommender
            # wait_and_merge_early_recommender 在没有 task_id 时会直接生成
            state = wait_and_merge_early_recommender(state)
            logger.info("✅ 推荐问题生成完成")
    except Exception as e:
        logger.error(f"❌ 合并推荐问题失败: {e}", exc_info=True)
        if "recommended_questions" not in state:
            state["recommended_questions"] = []
    
    logger.info("✅ 统一收集完成")
    return state

