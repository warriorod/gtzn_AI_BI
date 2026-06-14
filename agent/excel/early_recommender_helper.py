"""
表格问答早期推荐问题生成辅助模块
用于在 excel_parsing 之后提前启动推荐问题生成
"""
import logging
import threading
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor

from agent.excel.excel_agent_state import ExcelAgentState
from agent.excel.excel_question_recommender import excel_question_recommender
from copy import deepcopy
import asyncio

logger = logging.getLogger(__name__)

# 全局线程池和任务字典
_recommender_executor: Optional[ThreadPoolExecutor] = None
_recommender_lock = threading.Lock()
_recommender_futures: dict = {}  # {task_id: {'future': future, 'result': [], 'completed': False}}


def get_recommender_executor() -> ThreadPoolExecutor:
    """获取或创建推荐问题生成的线程池"""
    global _recommender_executor
    if _recommender_executor is None:
        with _recommender_lock:
            if _recommender_executor is None:
                _recommender_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="excel_early_recommender")
                logger.info("✅ 创建表格问答早期推荐问题生成线程池")
    return _recommender_executor


def start_early_recommender(state: ExcelAgentState) -> ExcelAgentState:
    """
    早期启动推荐问题生成（在 excel_parsing 之后立即开始）
    
    Args:
        state: ExcelAgent 状态对象
        
    Returns:
        更新后的 state（推荐问题可能还未完成）
    """
    try:
        # 检查是否有必要的依赖
        db_info = state.get("db_info", [])
        user_query = state.get("user_query", "")
        
        if not db_info or not user_query:
            logger.debug("推荐问题生成所需数据不完整，跳过早期启动")
            return state
        
        # 创建任务ID用于跟踪
        task_id = f"excel_{id(state)}"
        
        logger.info("🚀 早期启动推荐问题生成（后台并行执行）")
        
        # 在线程池中异步执行推荐问题生成
        executor = get_recommender_executor()
        
        def run_recommender():
            """在线程中运行 excel_question_recommender"""
            try:
                state_copy = deepcopy(state)
                # excel_question_recommender 是异步函数，需要在新的事件循环中运行
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result_state = loop.run_until_complete(excel_question_recommender(state_copy))
                finally:
                    loop.close()
                
                recommended_questions = result_state.get("recommended_questions", [])
                
                with _recommender_lock:
                    if task_id in _recommender_futures:
                        _recommender_futures[task_id]['completed'] = True
                        _recommender_futures[task_id]['result'] = recommended_questions
                
                logger.info(f"✅ 早期推荐问题生成完成，任务ID: {task_id}，生成 {len(recommended_questions)} 个问题")
            except Exception as e:
                logger.error(f"❌ 早期推荐问题生成失败: {e}", exc_info=True)
                with _recommender_lock:
                    if task_id in _recommender_futures:
                        _recommender_futures[task_id]['completed'] = True
                        _recommender_futures[task_id]['result'] = []
                        _recommender_futures[task_id]['error'] = str(e)
        
        future = executor.submit(run_recommender)
        
        with _recommender_lock:
            _recommender_futures[task_id] = {
                'future': future,
                'result': [],
                'completed': False,
                'error': None
            }
        
        # 在 state 中保存 task_id
        state["_early_recommender_task_id"] = task_id
        
    except Exception as e:
        logger.error(f"❌ 早期启动推荐问题生成失败: {e}", exc_info=True)
        if "_early_recommender_task_id" not in state:
            state["_early_recommender_task_id"] = None
    
    return state


def wait_for_early_recommender(task_id: str, timeout: int = 5) -> Optional[List[str]]:
    """
    等待早期推荐问题生成任务完成
    
    Args:
        task_id: 任务ID
        timeout: 超时时间（秒）
        
    Returns:
        推荐问题列表，如果超时或失败则返回 None
    """
    try:
        with _recommender_lock:
            if task_id not in _recommender_futures:
                logger.warning(f"未找到任务ID {task_id} 的状态")
                return None
            
            task_info = _recommender_futures[task_id].copy()
        
        # 如果任务已完成，直接返回结果
        if task_info.get('completed'):
            result = task_info.get('result', [])
            # 清理任务信息
            with _recommender_lock:
                try:
                    del _recommender_futures[task_id]
                except KeyError:
                    pass
            return result if result else None
        
        # 如果任务未完成，等待完成
        future = task_info.get('future')
        if future:
            try:
                future.result(timeout=timeout)
                # 重新获取结果
                with _recommender_lock:
                    if task_id in _recommender_futures:
                        task_info = _recommender_futures[task_id]
                        result = task_info.get('result', [])
                        # 清理任务信息
                        try:
                            del _recommender_futures[task_id]
                        except KeyError:
                            pass
                        return result if result else None
            except Exception as e:
                logger.warning(f"等待推荐问题生成失败: {e}")
                # 清理任务信息
                with _recommender_lock:
                    try:
                        del _recommender_futures[task_id]
                    except KeyError:
                        pass
                return None
        
    except Exception as e:
        logger.error(f"等待推荐问题生成异常: {e}", exc_info=True)
    
    return None


def wait_and_merge_early_recommender(state: ExcelAgentState) -> ExcelAgentState:
    """
    等待早期启动的推荐问题生成任务并合并结果
    
    如果早期任务已完成，直接合并结果
    如果未完成，等待完成（最多5秒）后合并
    如果超时或失败，回退到直接调用 excel_question_recommender
    
    Args:
        state: ExcelAgent 状态对象
        
    Returns:
        更新后的 state
    """
    task_id = state.get("_early_recommender_task_id")
    
    if not task_id:
        logger.debug("没有早期启动的推荐问题任务")
        # 如果 state 中已有推荐问题，直接使用
        if "recommended_questions" in state and state.get("recommended_questions"):
            return state
        # 否则直接生成（异步函数需要在新的事件循环中运行）
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result_state = loop.run_until_complete(excel_question_recommender(deepcopy(state)))
            finally:
                loop.close()
            if "recommended_questions" in result_state:
                state["recommended_questions"] = result_state.get("recommended_questions", [])
        except Exception as e:
            logger.error(f"生成推荐问题失败: {e}", exc_info=True)
            state["recommended_questions"] = []
        return state
    
    # 等待早期任务完成
    recommended_questions = wait_for_early_recommender(task_id, timeout=5)
    
    if recommended_questions is not None:
        state["recommended_questions"] = recommended_questions
        logger.info(f"✅ 合并早期生成的推荐问题，数量: {len(recommended_questions)}")
    else:
        # 超时或失败，回退到直接生成
        logger.warning("⚠️ 早期推荐问题任务超时或失败，回退到直接生成")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result_state = loop.run_until_complete(excel_question_recommender(deepcopy(state)))
            finally:
                loop.close()
            if "recommended_questions" in result_state:
                state["recommended_questions"] = result_state.get("recommended_questions", [])
            else:
                state["recommended_questions"] = []
        except Exception as e:
            logger.error(f"回退生成推荐问题失败: {e}", exc_info=True)
            state["recommended_questions"] = []
    
    return state

