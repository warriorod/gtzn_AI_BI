"""
表格问答提示词构建器
根据模板系统构建各种提示词（SQL生成等）
"""

import logging
from typing import Optional, Tuple
from datetime import datetime

from agent.excel.template.template_loader import ExcelTemplateLoader

logger = logging.getLogger(__name__)


class ExcelPromptBuilder:
    """
    表格问答提示词构建器，集成所有模板模块
    """
    
    def __init__(self):
        self.template_loader = ExcelTemplateLoader()
        self.base_template = None
        self._init_base_template()
    
    def _init_base_template(self):
        """初始化基础模板"""
        try:
            self.base_template = self.template_loader.load_base_template()
        except Exception as e:
            logger.error(f"Failed to load base template: {e}")
            raise
    
    def build_sql_prompt(
        self,
        schema: str,
        question: str,
        engine: str,
        lang: str = "简体中文",
        enable_query_limit: bool = True,
        error_msg: str = "",
        current_time: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        构建 SQL 生成提示词（系统提示词 + 用户提示词）
        
        Args:
            schema: 数据库表结构（M-Schema 格式）
            question: 用户问题
            engine: 数据库引擎及版本信息
            lang: 语言（默认：简体中文）
            enable_query_limit: 是否启用查询限制
            error_msg: 错误消息（上次执行失败的错误信息）
            current_time: 当前时间（格式：YYYY-MM-DD HH:MM:SS）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            # 加载数据库特定的 SQL 模板
            sql_template_dict = self.template_loader.load_sql_template()
            sql_template = sql_template_dict.get('template', sql_template_dict)
            sql_base_template = self.base_template['template']['sql']
            
            # 获取 process_check
            process_check = sql_template.get('process_check') if sql_template.get('process_check') else sql_base_template['process_check']
            
            # 获取 query_limit 规则
            query_limit = sql_base_template['query_limit'] if enable_query_limit else sql_base_template['no_query_limit']
            
            # 组合基础 SQL 规则
            base_sql_rules = (
                sql_template['quot_rule'] + 
                query_limit + 
                sql_template['limit_rule'] + 
                sql_template['other_rule']
            )
            
            # 获取示例
            sql_examples = sql_template['basic_example']
            example_engine = sql_template['example_engine']
            example_answer_1 = sql_template['example_answer_1_with_limit'] if enable_query_limit else sql_template['example_answer_1']
            example_answer_2 = sql_template['example_answer_2_with_limit'] if enable_query_limit else sql_template['example_answer_2']
            example_answer_3 = sql_template['example_answer_3_with_limit'] if enable_query_limit else sql_template['example_answer_3']
            
            # 构建系统提示词
            system_prompt = sql_base_template['system'].format(
                engine=engine,
                schema=schema,
                question=question,
                lang=lang,
                process_check=process_check,
                base_sql_rules=base_sql_rules,
                basic_sql_examples=sql_examples,
                example_engine=example_engine,
                example_answer_1=example_answer_1,
                example_answer_2=example_answer_2,
                example_answer_3=example_answer_3,
            )
            
            # 构建用户提示词
            if current_time is None:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            user_prompt = sql_base_template['user'].format(
                engine=engine,
                schema=schema,
                question=question,
                current_time=current_time,
                error_msg=error_msg,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build SQL prompt: {e}", exc_info=True)
            raise
    
    def build_chart_prompt(
        self,
        sql: str,
        question: str,
        lang: str = "简体中文",
        chart_type: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        构建图表配置生成提示词
        
        Args:
            sql: SQL 语句
            question: 用户问题
            lang: 语言（默认：简体中文）
            chart_type: 推荐的图表类型（可选）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            chart_template = self.base_template['template']['chart']
            
            # 构建系统提示词
            system_prompt = chart_template['system'].format(
                lang=lang,
            )
            
            # 构建用户提示词
            user_prompt = chart_template['user'].format(
                question=question,
                sql=sql,
                chart_type=chart_type or "",
                data="{data}",  # 占位符，后续会被替换
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build chart prompt: {e}", exc_info=True)
            raise
    
    def build_guess_question_prompt(
        self,
        schema: str,
        question: str = "",
        old_questions: list = None,
        lang: str = "简体中文",
        articles_number: int = 4,
    ) -> Tuple[str, str]:
        """
        构建推荐问题生成提示词
        
        Args:
            schema: 数据库表结构（M-Schema 格式）
            question: 当前问题（可选）
            old_questions: 历史问题列表
            lang: 语言（默认：简体中文）
            articles_number: 推荐问题数量（默认：4）
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            import json
            guess_template = self.base_template['template']['guess']
            
            # 将历史问题列表转换为 JSON 字符串
            old_questions_json = json.dumps(old_questions or [], ensure_ascii=False)
            
            # 构建系统提示词
            system_prompt = guess_template['system'].format(
                lang=lang,
                articles_number=articles_number,
            )
            
            # 构建用户提示词
            user_prompt = guess_template['user'].format(
                question=question,
                schema=schema,
                old_questions=old_questions_json,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build guess question prompt: {e}", exc_info=True)
            raise
    
    def build_summarizer_prompt(
        self,
        data_result: str,
        user_query: str,
        current_time: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        构建数据总结提示词（系统提示词 + 用户提示词）
        
        Args:
            data_result: 数据结果（JSON格式字符串）
            user_query: 用户问题
            current_time: 当前时间（格式：YYYY-MM-DD HH:MM:SS），如果为None则自动生成
        
        Returns:
            (system_prompt, user_prompt) 元组
        """
        try:
            if current_time is None:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            summarizer_template = self.base_template['template']['summarizer']
            
            # 构建系统提示词
            system_prompt = summarizer_template['system']
            
            # 构建用户提示词
            user_prompt = summarizer_template['user'].format(
                data_result=data_result,
                user_query=user_query,
                current_time=current_time,
            )
            
            return system_prompt, user_prompt
            
        except Exception as e:
            logger.error(f"Failed to build summarizer prompt: {e}", exc_info=True)
            raise

