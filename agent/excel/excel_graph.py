import logging

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.excel_data_render_apache import excel_data_render_apache
from agent.excel.excel_excute_sql import exe_sql_excel_query
from agent.excel.excel_mapping_node import read_excel_columns
from agent.excel.excel_sql_node import sql_generate_excel
from agent.excel.excel_data_render_antv import excel_data_render_antv
from agent.excel.excel_chart_generator import excel_chart_generator
from agent.excel.excel_question_recommender import excel_question_recommender
from agent.excel.excel_summarizer import summarize
from agent.excel.parallel_collector import parallel_collect_after_sql_executor
from agent.excel.early_recommender_helper import start_early_recommender
from agent.excel.unified_collector import unified_collect

logger = logging.getLogger(__name__)


def data_render_condition(state: ExcelAgentState) -> str:
    """
    根据 chart_type 判断渲染方式
    表格使用 data_render_apache，其他图表使用 data_render_antv
    """
    # 处理 chart_type 可能为 None 的情况
    chart_type_value = state.get("chart_type") or ""
    chart_type = chart_type_value.lower() if isinstance(chart_type_value, str) else ""
    logger.info(f"chart_type: {chart_type}")
    
    # 如果是表格类型，使用 apache 渲染
    if not chart_type or chart_type == "table":
        return "data_render_apache"
    
    # 其他图表类型使用 antv 渲染
    return "data_render"


def create_excel_graph():
    """
    :return:
    """
    graph = StateGraph(ExcelAgentState)

    graph.add_node("excel_parsing", read_excel_columns)
    # 优化：早期启动推荐问题生成（在后台并行执行）
    graph.add_node("early_recommender", start_early_recommender)
    graph.add_node("sql_generator", sql_generate_excel)
    graph.add_node("sql_executor", exe_sql_excel_query)
    # 优化：并行执行 chart_generator 和 summarize
    graph.add_node("parallel_collector", parallel_collect_after_sql_executor)
    # 统一收集节点：按顺序收集 summarize → 图表数据 → 推荐问题
    graph.add_node("unified_collector", unified_collect)
    # 保留原有节点以兼容（但不再使用）
    graph.add_node("chart_generator", excel_chart_generator)
    graph.add_node("summarize", summarize)
    graph.add_node("data_render", excel_data_render_antv)
    graph.add_node("data_render_apache", excel_data_render_apache)
    graph.add_node("question_recommender", excel_question_recommender)

    graph.set_entry_point("excel_parsing")
    # 优化：在 excel_parsing 之后立即启动推荐问题生成（不阻塞主流程）
    graph.add_edge("excel_parsing", "early_recommender")
    graph.add_edge("early_recommender", "sql_generator")
    graph.add_edge("sql_generator", "sql_executor")
    # 优化：并行执行 chart_generator 和 summarize（推荐问题已在后台执行）
    graph.add_edge("sql_executor", "parallel_collector")
    # 统一收集：按顺序收集 summarize → 图表数据 → 推荐问题
    graph.add_edge("parallel_collector", "unified_collector")
    graph.add_edge("unified_collector", END)
    
    # 保留原有边以兼容（但不再使用）
    # graph.add_edge("excel_parsing", "sql_generator")
    # graph.add_edge("sql_executor", "chart_generator")
    # graph.add_edge("chart_generator", "summarize")
    # graph.add_conditional_edges(
    #     "summarize", data_render_condition, {"data_render": "data_render", "data_render_apache": "data_render_apache"}
    # )
    # graph.add_edge("data_render", "question_recommender")
    # graph.add_edge("data_render_apache", "question_recommender")
    # graph.add_edge("question_recommender", END)
    graph_compiled: CompiledStateGraph = graph.compile()

    # logger.info(f"excel_graph mermaid_code: {graph_compiled.get_graph().draw_mermaid()}")

    return graph_compiled
