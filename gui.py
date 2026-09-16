import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import time
import uuid
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext, filedialog

from exporter import export
from scraper import ScraperError, WebScraper
from config import save_task, load_task, list_tasks
from database import (
    init_db,
    save_record,
    save_record_stream,
    list_records,
    get_record,
    get_record_rows,
    count_record_rows,
    delete_record,
    add_proxy,
    list_proxies,
    delete_proxy,
    existing_keys,
    check_proxy,
)
from scheduler import InAppScheduler
from picker import pick_selector
from dedup import deduplicate
from streaming import process_rows
from cleaner import apply_clean_rules, CLEAN_RULES
from templates import get_template, get_template_names
from subdomain import collect_subdomains
from version import __version__


class ScraperGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"通用信息收集爬虫 v{__version__}")
        self.root.geometry("1200x900")
        self.root.minsize(1100, 800)

        self.fields = []
        self.result_data = []
        self.raw_data = []
        self.scheduler = InAppScheduler()
        self.scheduler.on_log = lambda msg: self.root.after(0, lambda: self._log(msg))
        self.scheduler.start()
        self.start_time = None
        self._scheduled_running = set()

        init_db()
        self._build_ui()

    def _build_ui(self):
        # ===== 顶部任务名称与模板 =====
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(top, text="任务名:").pack(side=tk.LEFT)
        self.task_name_var = tk.StringVar()
        tk.Entry(top, textvariable=self.task_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(top, text="保存任务", command=self._save_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="加载任务", command=self._load_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="任务列表", command=self._show_task_list).pack(side=tk.LEFT, padx=2)
        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)
        tk.Label(top, text="模板:").pack(side=tk.LEFT)
        self.template_var = tk.StringVar()
        template_opts = [""] + [f"{k}|{name}" for k, name, _ in get_template_names()]
        ttk.Combobox(top, textvariable=self.template_var, values=template_opts, state="readonly", width=20).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="加载模板", command=self._load_template).pack(side=tk.LEFT, padx=2)

        # ===== 笔记本标签页 =====
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        config_tab = tk.Frame(notebook)
        notebook.add(config_tab, text="采集配置")
        self._build_config_tab(config_tab)

        anti_tab = tk.Frame(notebook)
        notebook.add(anti_tab, text="反爬与代理")
        self._build_anti_tab(anti_tab)

        process_tab = tk.Frame(notebook)
        notebook.add(process_tab, text="数据处理")
        self._build_process_tab(process_tab)

        schedule_tab = tk.Frame(notebook)
        notebook.add(schedule_tab, text="定时任务")
        self._build_schedule_tab(schedule_tab)

        subdomain_tab = tk.Frame(notebook)
        notebook.add(subdomain_tab, text="子域名收集")
        self._build_subdomain_tab(subdomain_tab)

        history_tab = tk.Frame(notebook)
        notebook.add(history_tab, text="历史记录")
        self._build_history_tab(history_tab)

        # ===== 统计面板 =====
        self.stat_frame = tk.LabelFrame(self.root, text="统计")
        self.stat_frame.pack(fill=tk.X, padx=10, pady=2)
        self.stat_var = tk.StringVar(value="原始: 0 | 去重后: 0 | 耗时: 0s")
        tk.Label(self.stat_frame, textvariable=self.stat_var, font=("Microsoft YaHei", 10)).pack(anchor=tk.W, padx=5, pady=2)

        # ===== 底部操作与日志 =====
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="开始采集", command=self._start_scrape).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="导出数据", command=self._export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self.root, textvariable=self.status_var).pack(anchor=tk.W, padx=10)

        log_frame = tk.LabelFrame(self.root, text="运行日志")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_config_tab(self, parent):
        basic = tk.LabelFrame(parent, text="基本配置")
        basic.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(basic, text="起始 URL:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.url_var = tk.StringVar()
        tk.Entry(basic, textvariable=self.url_var).grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
        ttk.Button(basic, text="可视化选元素", command=self._open_picker).grid(row=0, column=2, padx=5)

        tk.Label(basic, text="采集模式:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.mode_var = tk.StringVar(value="static")
        ttk.Combobox(basic, textvariable=self.mode_var, values=["static", "api"], state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(basic, text="选择器类型:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.selector_type_var = tk.StringVar(value="css")
        ttk.Combobox(basic, textvariable=self.selector_type_var, values=["css", "xpath"], state="readonly").grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(basic, text="列表选择器:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.list_selector_var = tk.StringVar()
        tk.Entry(basic, textvariable=self.list_selector_var).grid(row=3, column=1, sticky=tk.EW, padx=5, pady=2)

        tk.Label(basic, text="Cookie (可选):").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.cookie_var = tk.StringVar()
        tk.Entry(basic, textvariable=self.cookie_var).grid(row=4, column=1, sticky=tk.EW, padx=5, pady=2)
        self.save_cookie_var = tk.BooleanVar(value=False)
        tk.Checkbutton(basic, text="保存 Cookie（加密）", variable=self.save_cookie_var).grid(row=4, column=2, sticky=tk.W, padx=5, pady=2)

        tk.Label(basic, text="User-Agent:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
        self.ua_var = tk.StringVar(value="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        tk.Entry(basic, textvariable=self.ua_var).grid(row=5, column=1, sticky=tk.EW, padx=5, pady=2)

        basic.columnconfigure(1, weight=1)

        # ===== API 配置（仅 API 模式使用） =====
        api_frame = tk.LabelFrame(parent, text="API 配置")
        api_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(api_frame, text="请求方法:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_method_var = tk.StringVar(value="GET")
        ttk.Combobox(api_frame, textvariable=self.api_method_var, values=["GET", "POST"], state="readonly", width=10).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="请求体类型:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.api_body_type_var = tk.StringVar(value="json")
        ttk.Combobox(api_frame, textvariable=self.api_body_type_var, values=["json", "form"], state="readonly", width=10).grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="额外请求头 (JSON):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_headers_var = tk.StringVar()
        tk.Entry(api_frame, textvariable=self.api_headers_var).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=2)

        tk.Label(api_frame, text="请求体 (JSON):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_body_var = tk.StringVar()
        tk.Entry(api_frame, textvariable=self.api_body_var).grid(row=2, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=2)

        tk.Label(api_frame, text="API 分页方式:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_pagination_var = tk.StringVar(value="none")
        ttk.Combobox(api_frame, textvariable=self.api_pagination_var, values=["none", "param", "offset"], state="readonly", width=12).grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="分页参数名:").grid(row=3, column=2, sticky=tk.W, padx=5, pady=2)
        self.api_page_param_var = tk.StringVar(value="page")
        tk.Entry(api_frame, textvariable=self.api_page_param_var, width=10).grid(row=3, column=3, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="分页步长:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_page_step_var = tk.IntVar(value=1)
        tk.Spinbox(api_frame, from_=1, to=1000, textvariable=self.api_page_step_var, width=8).grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="Offset 参数名:").grid(row=4, column=2, sticky=tk.W, padx=5, pady=2)
        self.api_offset_param_var = tk.StringVar(value="offset")
        tk.Entry(api_frame, textvariable=self.api_offset_param_var, width=10).grid(row=4, column=3, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="Offset 步长:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_offset_step_var = tk.IntVar(value=20)
        tk.Spinbox(api_frame, from_=1, to=10000, textvariable=self.api_offset_step_var, width=8).grid(row=5, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(api_frame, text="下一页 URL JSONPath:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_next_url_path_var = tk.StringVar()
        tk.Entry(api_frame, textvariable=self.api_next_url_path_var).grid(row=6, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=2)
        tk.Label(api_frame, text="游标 JSONPath / 参数:").grid(row=7, column=0, sticky=tk.W, padx=5, pady=2)
        self.api_cursor_path_var = tk.StringVar()
        tk.Entry(api_frame, textvariable=self.api_cursor_path_var, width=20).grid(row=7, column=1, sticky=tk.EW, padx=5, pady=2)
        self.api_cursor_param_var = tk.StringVar(value="cursor")
        tk.Entry(api_frame, textvariable=self.api_cursor_param_var, width=12).grid(row=7, column=3, sticky=tk.W, padx=5, pady=2)

        api_frame.columnconfigure(1, weight=1)
        api_frame.columnconfigure(3, weight=1)

        paging = tk.LabelFrame(parent, text="翻页配置")
        paging.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(paging, text="最大页数:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.max_pages_var = tk.IntVar(value=1)
        tk.Spinbox(paging, from_=1, to=999, textvariable=self.max_pages_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(paging, text="翻页方式:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.page_mode_var = tk.StringVar(value="none")
        ttk.Combobox(paging, textvariable=self.page_mode_var, values=["none", "url", "param"], state="readonly").grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(paging, text="下一页选择器/参数名:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.page_selector_var = tk.StringVar(value="page")
        tk.Entry(paging, textvariable=self.page_selector_var).grid(row=2, column=1, sticky=tk.EW, padx=5, pady=2)

        tk.Label(paging, text="翻页步长:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.page_step_var = tk.IntVar(value=1)
        tk.Spinbox(paging, from_=1, to=100, textvariable=self.page_step_var).grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)

        paging.columnconfigure(1, weight=1)

        field_frame = tk.LabelFrame(parent, text="字段配置")
        field_frame.pack(fill=tk.X, padx=5, pady=5)

        input_f = tk.Frame(field_frame)
        input_f.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(input_f, text="字段名:").pack(side=tk.LEFT)
        self.field_name_var = tk.StringVar()
        tk.Entry(input_f, textvariable=self.field_name_var, width=12).pack(side=tk.LEFT, padx=2)
        tk.Label(input_f, text="选择器:").pack(side=tk.LEFT)
        self.field_selector_var = tk.StringVar()
        tk.Entry(input_f, textvariable=self.field_selector_var, width=20).pack(side=tk.LEFT, padx=2)
        tk.Label(input_f, text="属性:").pack(side=tk.LEFT)
        self.field_attr_var = tk.StringVar()
        tk.Entry(input_f, textvariable=self.field_attr_var, width=8).pack(side=tk.LEFT, padx=2)
        tk.Label(input_f, text="JSONPath:").pack(side=tk.LEFT)
        self.field_json_path_var = tk.StringVar()
        tk.Entry(input_f, textvariable=self.field_json_path_var, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(input_f, text="添加字段", command=self._add_field).pack(side=tk.LEFT, padx=5)

        self.field_tree = ttk.Treeview(field_frame, columns=("name", "selector", "attr", "json_path"), show="headings", height=5)
        self.field_tree.heading("name", text="字段名")
        self.field_tree.heading("selector", text="选择器/CSS/XPath")
        self.field_tree.heading("attr", text="属性")
        self.field_tree.heading("json_path", text="JSONPath")
        self.field_tree.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(field_frame, text="删除选中字段", command=self._del_field).pack(pady=2)

        result_frame = tk.LabelFrame(parent, text="结果预览")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.result_tree = ttk.Treeview(result_frame, show="headings")
        self.result_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _build_anti_tab(self, parent):
        frame = tk.LabelFrame(parent, text="反爬策略")
        frame.pack(fill=tk.X, padx=5, pady=5)

        self.random_ua_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="随机 User-Agent", variable=self.random_ua_var).grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)

        self.render_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="使用 Playwright 渲染（JS 动态页面）", variable=self.render_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        tk.Label(frame, text="等待策略:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.render_wait_var = tk.StringVar(value="domcontentloaded")
        ttk.Combobox(frame, textvariable=self.render_wait_var, values=["domcontentloaded", "load", "networkidle"], state="readonly", width=16).grid(row=0, column=3, padx=5)

        tk.Label(frame, text="重试次数:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.retries_var = tk.IntVar(value=2)
        tk.Spinbox(frame, from_=0, to=10, textvariable=self.retries_var).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        tk.Label(frame, text="基础延迟(秒):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.delay_var = tk.DoubleVar(value=0.5)
        tk.Entry(frame, textvariable=self.delay_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

        self.delay_random_var = tk.BooleanVar(value=True)
        tk.Checkbutton(frame, text="随机延迟（0~基础延迟）", variable=self.delay_random_var).grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)

        proxy_frame = tk.LabelFrame(parent, text="代理池")
        proxy_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        proxy_input = tk.Frame(proxy_frame)
        proxy_input.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(proxy_input, text="代理地址 (http://ip:port):").pack(side=tk.LEFT)
        self.proxy_input_var = tk.StringVar()
        tk.Entry(proxy_input, textvariable=self.proxy_input_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(proxy_input, text="添加代理", command=self._add_proxy).pack(side=tk.LEFT, padx=2)
        ttk.Button(proxy_input, text="刷新列表", command=self._refresh_proxies).pack(side=tk.LEFT, padx=2)

        self.proxy_tree = ttk.Treeview(proxy_frame, columns=("address", "status", "fail", "latency"), show="headings", height=8)
        self.proxy_tree.heading("address", text="代理地址")
        self.proxy_tree.heading("status", text="状态")
        self.proxy_tree.heading("fail", text="失败次数")
        self.proxy_tree.heading("latency", text="延迟(秒)")
        self.proxy_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        btns = tk.Frame(proxy_frame); btns.pack(pady=2)
        ttk.Button(btns, text="删除选中代理", command=self._del_proxy).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="检查全部代理", command=self._check_proxies).pack(side=tk.LEFT, padx=2)

        self._refresh_proxies()

    def _build_process_tab(self, parent):
        dedup_frame = tk.LabelFrame(parent, text="去重配置")
        dedup_frame.pack(fill=tk.X, padx=5, pady=5)
        self.dedup_var = tk.BooleanVar(value=False)
        tk.Checkbutton(dedup_frame, text="启用去重", variable=self.dedup_var).pack(anchor=tk.W, padx=5, pady=2)
        tk.Label(dedup_frame, text="去重字段（用逗号分隔，留空按整行去重）:").pack(anchor=tk.W, padx=5)
        self.dedup_fields_var = tk.StringVar()
        tk.Entry(dedup_frame, textvariable=self.dedup_fields_var).pack(fill=tk.X, padx=5, pady=2)
        self.incremental_var = tk.BooleanVar(value=False)
        tk.Checkbutton(dedup_frame, text="增量采集（按去重字段过滤本次重复项）", variable=self.incremental_var).pack(anchor=tk.W, padx=5, pady=2)
        tk.Label(dedup_frame, text="增量字段（ID / URL / 时间，可选）:").pack(anchor=tk.W, padx=5)
        self.incremental_id_var = tk.StringVar(); self.incremental_url_var = tk.StringVar(); self.incremental_time_var = tk.StringVar()
        row = tk.Frame(dedup_frame); row.pack(fill=tk.X, padx=5)
        for label, var in (("ID", self.incremental_id_var), ("URL", self.incremental_url_var), ("时间", self.incremental_time_var)):
            tk.Label(row, text=label).pack(side=tk.LEFT); tk.Entry(row, textvariable=var, width=12).pack(side=tk.LEFT, padx=3)

        clean_frame = tk.LabelFrame(parent, text="清洗规则")
        clean_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        input_f = tk.Frame(clean_frame)
        input_f.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(input_f, text="字段名:").pack(side=tk.LEFT)
        self.clean_field_var = tk.StringVar()
        tk.Entry(input_f, textvariable=self.clean_field_var, width=15).pack(side=tk.LEFT, padx=2)
        tk.Label(input_f, text="规则:").pack(side=tk.LEFT)
        self.clean_rule_var = tk.StringVar()
        ttk.Combobox(input_f, textvariable=self.clean_rule_var, values=list(CLEAN_RULES.keys()), state="readonly", width=18).pack(side=tk.LEFT, padx=2)
        ttk.Button(input_f, text="添加规则", command=self._add_clean_rule).pack(side=tk.LEFT, padx=5)

        self.clean_tree = ttk.Treeview(clean_frame, columns=("field", "rule"), show="headings", height=6)
        self.clean_tree.heading("field", text="字段名")
        self.clean_tree.heading("rule", text="规则")
        self.clean_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        ttk.Button(clean_frame, text="删除选中规则", command=self._del_clean_rule).pack(pady=2)

        self.clean_rules = {}

    def _build_schedule_tab(self, parent):
        tk.Label(parent, text="应用内定时任务（按分钟间隔）").pack(anchor=tk.W, padx=5, pady=5)

        input_f = tk.Frame(parent)
        input_f.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(input_f, text="间隔分钟:").pack(side=tk.LEFT)
        self.schedule_interval_var = tk.IntVar(value=60)
        tk.Spinbox(input_f, from_=1, to=10080, textvariable=self.schedule_interval_var, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(input_f, text="添加当前任务为定时任务", command=self._add_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_f, text="刷新", command=self._refresh_schedules).pack(side=tk.LEFT, padx=5)

        self.schedule_tree = ttk.Treeview(parent, columns=("id", "interval", "next_run"), show="headings", height=8)
        self.schedule_tree.heading("id", text="任务ID")
        self.schedule_tree.heading("interval", text="间隔(分钟)")
        self.schedule_tree.heading("next_run", text="下次执行")
        self.schedule_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(parent, text="删除选中定时任务", command=self._del_schedule).pack(pady=2)

        tk.Label(parent, text="提示：也可通过系统计划任务实现更灵活的调度。").pack(anchor=tk.W, padx=5)

    def _build_subdomain_tab(self, parent):
        tk.Label(parent, text="输入根域名（如 example.com，不要带 http://）").pack(anchor=tk.W, padx=5, pady=5)

        input_f = tk.Frame(parent)
        input_f.pack(fill=tk.X, padx=5, pady=2)
        self.subdomain_domain_var = tk.StringVar()
        tk.Entry(input_f, textvariable=self.subdomain_domain_var, width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_f, text="开始收集", command=self._start_subdomain).pack(side=tk.LEFT, padx=5)
        self.subdomain_wordlist_var = tk.StringVar()
        ttk.Button(input_f, text="加载词典", command=self._choose_subdomain_wordlist).pack(side=tk.LEFT, padx=5)

        opts = tk.Frame(parent)
        opts.pack(fill=tk.X, padx=5, pady=2)
        self.subdomain_brute_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="DNS 字典爆破", variable=self.subdomain_brute_var).pack(side=tk.LEFT, padx=5)
        self.subdomain_crtsh_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opts, text="crt.sh 证书查询", variable=self.subdomain_crtsh_var).pack(side=tk.LEFT, padx=5)

        tk.Label(opts, text="线程数:").pack(side=tk.LEFT, padx=5)
        self.subdomain_threads_var = tk.IntVar(value=50)
        tk.Spinbox(opts, from_=10, to=200, textvariable=self.subdomain_threads_var, width=8).pack(side=tk.LEFT, padx=2)

        self.subdomain_tree = ttk.Treeview(parent, columns=("子域名", "IP", "来源"), show="headings", height=14)
        self.subdomain_tree.heading("子域名", text="子域名")
        self.subdomain_tree.heading("IP", text="IP")
        self.subdomain_tree.heading("来源", text="来源")
        self.subdomain_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_f = tk.Frame(parent)
        btn_f.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_f, text="导出结果", command=self._export_subdomain).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="清空结果", command=self._clear_subdomain).pack(side=tk.LEFT, padx=2)

    def _start_subdomain(self):
        domain = self.subdomain_domain_var.get().strip().lower()
        if not domain:
            messagebox.showwarning("提示", "请输入域名")
            return
        domain = domain.replace("http://", "").replace("https://", "").split("/")[0]
        self.subdomain_tree.delete(*self.subdomain_tree.get_children())
        self.status_var.set("正在收集子域名...")
        self.progress["value"] = 0
        self.start_time = time.time()
        thread = threading.Thread(
            target=self._subdomain_worker,
            args=(domain,),
            daemon=True,
        )
        thread.start()

    def _choose_subdomain_wordlist(self):
        path = filedialog.askopenfilename(filetypes=[("文本词典", "*.txt"), ("所有文件", "*.*")])
        if path:
            self.subdomain_wordlist_var.set(path)

    def _subdomain_worker(self, domain: str):
        try:
            self.current_record_id = None
            from subdomain import load_wordlist
            words = load_wordlist(self.subdomain_wordlist_var.get()) if self.subdomain_wordlist_var.get() else None
            data = collect_subdomains(
                domain=domain,
                enable_brute=self.subdomain_brute_var.get(),
                enable_crtsh=self.subdomain_crtsh_var.get(),
                threads=self.subdomain_threads_var.get(), wordlist=words,
                timeout=2.0,
                on_progress=lambda cur, total: self.root.after(0, lambda: self._update_progress(cur, total)),
                on_log=lambda msg: self.root.after(0, lambda: self._log(msg)),
            )
            self.result_data = data
            self.root.after(0, self._show_subdomain_results)
            elapsed = round(time.time() - self.start_time, 2)
            self.root.after(0, lambda: self._update_stat(0, len(data), elapsed))
            self.root.after(0, lambda: self._log(f"子域名收集完成，共 {len(data)} 个"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"子域名收集失败: {e}"))
            self.root.after(0, lambda: self.status_var.set("收集失败"))

    def _show_subdomain_results(self):
        self.status_var.set(f"子域名收集完成，共 {len(self.result_data)} 个")
        for row in self.result_data:
            self.subdomain_tree.insert("", tk.END, values=(row["子域名"], row["IP"], row["来源"]))

    def _export_subdomain(self):
        if not self.result_data:
            messagebox.showwarning("提示", "没有可导出的数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            export(self.result_data, path)
            messagebox.showinfo("完成", f"已导出到: {path}")
            self._log(f"导出成功: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _clear_subdomain(self):
        self.subdomain_tree.delete(*self.subdomain_tree.get_children())
        self.result_data.clear()

    def _build_history_tab(self, parent):
        ttk.Button(parent, text="刷新历史记录", command=self._refresh_history).pack(anchor=tk.W, padx=5, pady=5)
        self.history_tree = ttk.Treeview(
            parent,
            columns=("id", "task_name", "start_url", "count", "created_at"),
            show="headings",
            height=12,
        )
        self.history_tree.heading("id", text="ID")
        self.history_tree.heading("task_name", text="任务名")
        self.history_tree.heading("start_url", text="起始URL")
        self.history_tree.heading("count", text="条数")
        self.history_tree.heading("created_at", text="时间")
        self.history_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        btn_f = tk.Frame(parent)
        btn_f.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_f, text="查看详情", command=self._view_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="导出选中", command=self._export_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_f, text="删除选中", command=self._delete_history).pack(side=tk.LEFT, padx=2)

        self._refresh_history()

    def _log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _add_field(self):
        name = self.field_name_var.get().strip()
        selector = self.field_selector_var.get().strip()
        json_path = self.field_json_path_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "字段名不能为空")
            return
        if not selector and not json_path:
            messagebox.showwarning("提示", "选择器和 JSONPath 至少填一个")
            return
        self.fields.append({
            "name": name,
            "selector": selector,
            "attr": self.field_attr_var.get().strip() or None,
            "json_path": json_path or None,
        })
        self.field_tree.insert("", tk.END, values=(name, selector, self.field_attr_var.get().strip(), json_path))
        self.field_name_var.set("")
        self.field_selector_var.set("")
        self.field_attr_var.set("")
        self.field_json_path_var.set("")

    def _del_field(self):
        selected = self.field_tree.selection()
        if not selected:
            return
        indices = sorted([self.field_tree.index(item) for item in selected], reverse=True)
        for item in selected:
            self.field_tree.delete(item)
        for idx in indices:
            if 0 <= idx < len(self.fields):
                self.fields.pop(idx)

    def _add_clean_rule(self):
        field = self.clean_field_var.get().strip()
        rule = self.clean_rule_var.get().strip()
        if not field or not rule:
            messagebox.showwarning("提示", "字段名和规则不能为空")
            return
        self.clean_rules.setdefault(field, []).append(rule)
        self.clean_tree.insert("", tk.END, values=(field, rule))
        self.clean_field_var.set("")
        self.clean_rule_var.set("")

    def _del_clean_rule(self):
        selected = self.clean_tree.selection()
        if not selected:
            return
        for item in selected:
            vals = self.clean_tree.item(item, "values")
            self.clean_tree.delete(item)
            if vals and vals[0] in self.clean_rules:
                self.clean_rules[vals[0]].remove(vals[1])
                if not self.clean_rules[vals[0]]:
                    del self.clean_rules[vals[0]]

    def _load_template(self):
        val = self.template_var.get()
        if not val or "|" not in val:
            messagebox.showwarning("提示", "请先选择一个模板")
            return
        key = val.split("|")[0]
        tpl = get_template(key)
        if not tpl:
            return
        self._apply_task_config(tpl)
        self.task_name_var.set(tpl.get("name", ""))
        self._log(f"已加载模板: {tpl.get('name', '')}")

    def _open_picker(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请先填写起始 URL")
            return

        def run():
            try:
                result = pick_selector(url)
                self.root.after(0, lambda: self._apply_picker_result(result))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"选择器助手出错: {e}"))

        threading.Thread(target=run, daemon=True).start()

    def _apply_picker_result(self, result: dict):
        sel_type = self.selector_type_var.get()
        selector = result.get(sel_type, "")
        if not selector:
            messagebox.showinfo("提示", "未获取到选择器")
            return
        self.field_selector_var.set(selector)
        self._log(f"可视化选择器结果: {selector}")
        messagebox.showinfo("选择器已生成", f"{sel_type.upper()}: {selector}\n已填入字段选择器框")

    def _start_scrape(self):
        if not self.url_var.get().strip():
            messagebox.showwarning("提示", "请输入起始 URL")
            return
        if not self.list_selector_var.get().strip() or not self.fields:
            messagebox.showwarning("提示", "请配置列表选择器和至少一个字段")
            return
        self.result_data.clear()
        self.raw_data.clear()
        self.progress["value"] = 0
        self.status_var.set("采集中...")
        self.start_time = time.time()
        thread = threading.Thread(target=self._scrape_worker, daemon=True)
        thread.start()

    def _scrape_worker(self):
        scraper = None
        try:
            proxies = [p["address"] for p in list_proxies() if p["enabled"]]
            task = self._collect_task_config()
            scraper = WebScraper(
                start_url=self.url_var.get().strip(),
                mode=self.mode_var.get(),
                headers={"User-Agent": self.ua_var.get().strip()} if self.ua_var.get().strip() else {},
                cookies=self.cookie_var.get().strip() or None,
                delay=self.delay_var.get(),
                delay_random=self.delay_random_var.get(),
                proxy_pool=proxies if proxies else None,
                random_ua=self.random_ua_var.get(),
                retries=self.retries_var.get(),
                render=self.render_var.get(),
                render_wait_until=self.render_wait_var.get(),
                api_config=task.get("api_config"),
                checkpoint_path=os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "InfoScraper", "checkpoints", (self.task_name_var.get().strip() or "current") + ".json"),
            )
            raw = scraper.iter_run(
                list_selector=self.list_selector_var.get().strip(),
                fields=self.fields,
                selector_type=self.selector_type_var.get(),
                max_pages=self.max_pages_var.get(),
                next_page_selector=self.page_selector_var.get().strip() if self.page_mode_var.get() == "url" else None,
                next_page_mode="param" if self.page_mode_var.get() == "param" else "url",
                next_page_param=self.page_selector_var.get().strip() or "page",
                next_page_step=self.page_step_var.get(),
                on_progress=lambda p, total: self.root.after(0, lambda: self._update_progress(p, total)),
                on_log=lambda msg: self.root.after(0, lambda: self._log(msg)),
            )
            raw_count = 0

            # 数据处理
            dedup_fields = [f.strip() for f in self.dedup_fields_var.get().split(",") if f.strip()]
            if self.incremental_var.get():
                dedup_fields += [v.strip() for v in (self.incremental_id_var.get(), self.incremental_url_var.get(), self.incremental_time_var.get()) if v.strip() and v.strip() not in dedup_fields]
            known = existing_keys(self.task_name_var.get().strip(), dedup_fields) if self.incremental_var.get() and dedup_fields else set()
            def stream_rows():
                nonlocal raw_count
                for row in raw:
                    raw_count += 1
                    if len(self.raw_data) < 100:
                        self.raw_data.append(row)
                    yield row
            processed = []; processed_count = 0
            def processed_rows():
                nonlocal processed_count
                for row in process_rows(stream_rows(), self.clean_rules, dedup_fields if self.dedup_var.get() else None, known, dedup=self.dedup_var.get()):
                    processed_count += 1
                    if len(processed) < 100:
                        processed.append(row)
                    yield row
            record_id = save_record_stream(self.task_name_var.get().strip(), self.url_var.get().strip(), processed_rows())
            self.current_record_id = record_id
            if self.clean_rules:
                self.root.after(0, lambda: self._log(f"已应用清洗规则: {len(self.clean_rules)} 个字段"))
            if self.dedup_var.get() or self.incremental_var.get():
                self.root.after(0, lambda: self._log(f"逐条处理完成: {raw_count} 条原始数据"))

            self.result_data = processed
            self.root.after(0, self._show_results)
            elapsed = round(time.time() - self.start_time, 2)
            self.root.after(0, lambda: self._update_stat(raw_count, processed_count, elapsed))
            self.result_count = processed_count

            # 自动保存到数据库
            self.root.after(0, lambda: self._log(f"已保存到历史记录，ID: {record_id}"))
            self.root.after(0, self._refresh_history)
        except Exception as e:
            self.root.after(0, lambda: self._log(f"错误: {e}"))
            self.root.after(0, lambda: self.status_var.set("采集失败"))
        finally:
            if scraper is not None:
                scraper.close()

    def _update_progress(self, page: int, total: int):
        self.progress["value"] = min(page / self.max_pages_var.get() * 100, 100)
        self.status_var.set(f"已采集 {page} 页，共 {total} 条数据")
        self._log(f"第 {page} 页完成，累计 {total} 条")

    def _update_stat(self, raw: int, deduped: int, elapsed: float):
        self.stat_var.set(f"原始: {raw} | 去重后: {deduped} | 耗时: {elapsed}s")

    def _show_results(self):
        total = getattr(self, "result_count", len(self.result_data))
        self.status_var.set(f"采集完成，共 {total} 条")
        self._log(f"采集完成，共 {total} 条（预览前100条）")
        self.result_tree.delete(*self.result_tree.get_children())
        if not self.result_data and not getattr(self, "current_record_id", None):
            return
        cols = list(self.result_data[0].keys())
        self.result_tree["columns"] = cols
        for c in cols:
            self.result_tree.heading(c, text=c)
            self.result_tree.column(c, width=100)
        for row in self.result_data[:100]:
            self.result_tree.insert("", tk.END, values=[row.get(c, "") for c in cols])

    def _export(self):
        if not self.result_data:
            messagebox.showwarning("提示", "没有可导出的数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            data = get_record(int(self.current_record_id))["data"] if getattr(self, "current_record_id", None) else self.result_data
            export(data, path)
            messagebox.showinfo("完成", f"已导出到: {path}")
            self._log(f"导出成功: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _save_task(self):
        name = self.task_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入任务名")
            return
        task = self._collect_task_config()
        try:
            save_task(name, task)
        except Exception as exc:
            messagebox.showerror("错误", f"任务保存失败: {exc}")
            return
        checkpoint_path = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "InfoScraper", "checkpoints", (self.task_name_var.get().strip() or "current") + ".json")
        if os.path.exists(checkpoint_path):
            choice = messagebox.askyesnocancel("发现未完成采集", "检测到上次未完成的断点。\n选择“是”继续，“否”重新开始，“取消”不启动。")
            if choice is None:
                return
            if choice is False:
                try: os.remove(checkpoint_path)
                except OSError: pass
        messagebox.showinfo("完成", f"任务 '{name}' 已保存")

    def _load_task(self):
        name = self.task_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入要加载的任务名")
            return
        try:
            task = load_task(name)
        except FileNotFoundError:
            messagebox.showerror("错误", f"未找到任务: {name}")
            return
        except Exception as exc:
            messagebox.showerror("错误", f"任务加载失败: {exc}")
            return
        self._apply_task_config(task)
        self._log(f"已加载任务: {name}")

    def _collect_task_config(self) -> dict:
        api_headers = {}
        api_body = {}
        try:
            h = self.api_headers_var.get().strip()
            if h:
                api_headers = json.loads(h)
        except Exception:
            self._log("API 额外请求头不是合法 JSON，已忽略")
        try:
            b = self.api_body_var.get().strip()
            if b:
                api_body = json.loads(b)
        except Exception:
            self._log("API 请求体不是合法 JSON，已忽略")

        return {
            "url": self.url_var.get(),
            "mode": self.mode_var.get(),
            "selector_type": self.selector_type_var.get(),
            "list_selector": self.list_selector_var.get(),
            "cookie": self.cookie_var.get(),
            "save_cookie": self.save_cookie_var.get(),
            "ua": self.ua_var.get(),
            "max_pages": self.max_pages_var.get(),
            "page_mode": self.page_mode_var.get(),
            "page_selector": self.page_selector_var.get(),
            "page_step": self.page_step_var.get(),
            "fields": self.fields,
            "random_ua": self.random_ua_var.get(),
            "render": self.render_var.get(),
            "render_wait_until": self.render_wait_var.get(),
            "retries": self.retries_var.get(),
            "delay": self.delay_var.get(),
            "delay_random": self.delay_random_var.get(),
            "dedup": self.dedup_var.get(),
            "dedup_fields": self.dedup_fields_var.get(),
            "incremental": self.incremental_var.get(),
            "incremental_id": self.incremental_id_var.get(), "incremental_url": self.incremental_url_var.get(), "incremental_time": self.incremental_time_var.get(),
            "clean_rules": self.clean_rules,
            "api_config": {
                "method": self.api_method_var.get(),
                "body_type": self.api_body_type_var.get(),
                "headers": api_headers,
                "body": api_body,
                "pagination_type": self.api_pagination_var.get(),
                "pagination_param": self.api_page_param_var.get(),
                "pagination_step": self.api_page_step_var.get(),
                "request_page_param": self.api_page_param_var.get(),
                "offset_param": self.api_offset_param_var.get(),
                "offset_step": self.api_offset_step_var.get(),
                "next_url_path": self.api_next_url_path_var.get().strip(),
                "cursor_path": self.api_cursor_path_var.get().strip(),
                "cursor_param": self.api_cursor_param_var.get().strip() or "cursor",
            },
        }

    def _apply_task_config(self, task: dict):
        self.url_var.set(task.get("url", ""))
        self.mode_var.set(task.get("mode", "static"))
        self.selector_type_var.set(task.get("selector_type", "css"))
        self.list_selector_var.set(task.get("list_selector", ""))
        self.cookie_var.set(task.get("cookie", ""))
        self.save_cookie_var.set(bool(task.get("save_cookie", False)))
        self.ua_var.set(task.get("ua", ""))
        self.max_pages_var.set(task.get("max_pages", 1))
        self.page_mode_var.set(task.get("page_mode", "none"))
        self.page_selector_var.set(task.get("page_selector", "page"))
        self.page_step_var.set(task.get("page_step", 1))
        self.fields = task.get("fields", [])
        self.field_tree.delete(*self.field_tree.get_children())
        for f in self.fields:
            self.field_tree.insert("", tk.END, values=(
                f["name"], f.get("selector", ""), f.get("attr", ""), f.get("json_path", "")
            ))
        self.random_ua_var.set(task.get("random_ua", False))
        self.render_var.set(task.get("render", False))
        self.render_wait_var.set(task.get("render_wait_until", "domcontentloaded"))
        self.retries_var.set(task.get("retries", 2))
        self.delay_var.set(task.get("delay", 0.5))
        self.delay_random_var.set(task.get("delay_random", True))
        self.dedup_var.set(task.get("dedup", False))
        self.dedup_fields_var.set(task.get("dedup_fields", ""))
        self.incremental_var.set(bool(task.get("incremental", False)))
        self.incremental_id_var.set(task.get("incremental_id", "")); self.incremental_url_var.set(task.get("incremental_url", "")); self.incremental_time_var.set(task.get("incremental_time", ""))
        self.clean_rules = task.get("clean_rules", {})
        self.clean_tree.delete(*self.clean_tree.get_children())
        for field, rules in self.clean_rules.items():
            for rule in rules:
                self.clean_tree.insert("", tk.END, values=(field, rule))

        api_cfg = task.get("api_config", {})
        self.api_method_var.set(api_cfg.get("method", "GET"))
        self.api_body_type_var.set(api_cfg.get("body_type", "json"))
        try:
            self.api_headers_var.set(json.dumps(api_cfg.get("headers", {}), ensure_ascii=False) if api_cfg.get("headers") else "")
        except Exception:
            self.api_headers_var.set("")
        try:
            self.api_body_var.set(json.dumps(api_cfg.get("body", {}), ensure_ascii=False) if api_cfg.get("body") else "")
        except Exception:
            self.api_body_var.set("")
        self.api_pagination_var.set(api_cfg.get("pagination_type", "none"))
        self.api_page_param_var.set(api_cfg.get("pagination_param", "page"))
        self.api_page_step_var.set(api_cfg.get("pagination_step", 1))
        self.api_offset_param_var.set(api_cfg.get("offset_param", "offset"))
        self.api_offset_step_var.set(api_cfg.get("offset_step", 20))
        self.api_next_url_path_var.set(api_cfg.get("next_url_path", ""))
        self.api_cursor_path_var.set(api_cfg.get("cursor_path", ""))
        self.api_cursor_param_var.set(api_cfg.get("cursor_param", "cursor"))

    def _show_task_list(self):
        names = list_tasks()
        if not names:
            messagebox.showinfo("任务列表", "暂无保存的任务")
            return
        top = tk.Toplevel(self.root)
        top.title("任务列表")
        top.geometry("300x300")
        lb = tk.Listbox(top)
        lb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        for n in names:
            lb.insert(tk.END, n)

        def load():
            sel = lb.curselection()
            if sel:
                self.task_name_var.set(lb.get(sel[0]))
                self._load_task()
                top.destroy()

        ttk.Button(top, text="加载", command=load).pack(pady=5)

    # === 反爬与代理 ===
    def _add_proxy(self):
        addr = self.proxy_input_var.get().strip()
        if not addr:
            return
        add_proxy(addr)
        self.proxy_input_var.set("")
        self._refresh_proxies()

    def _refresh_proxies(self):
        self.proxy_tree.delete(*self.proxy_tree.get_children())
        for p in list_proxies():
            self.proxy_tree.insert("", tk.END, values=(p["address"], "启用" if p["enabled"] else "禁用", p["fail_count"], f"{p.get('latency', 0):.3f}"))

    def _del_proxy(self):
        selected = self.proxy_tree.selection()
        for item in selected:
            vals = self.proxy_tree.item(item, "values")
            if vals:
                delete_proxy(vals[0])
        self._refresh_proxies()

    def _check_proxies(self):
        """Check proxies off the UI thread and refresh statuses on the UI thread."""
        proxies = [p["address"] for p in list_proxies()]
        def worker():
            def check_one(address):
                ok = check_proxy(address)
                if not ok:
                    from database import mark_proxy_fail
                    mark_proxy_fail(address)
                    if next((p for p in list_proxies() if p["address"] == address), {"fail_count": 0})["fail_count"] >= 3:
                        from database import set_proxy_enabled
                        set_proxy_enabled(address, False)
                else:
                    from database import mark_proxy_success
                    mark_proxy_success(address)
                self.root.after(0, lambda a=address, good=ok: self._log(f"代理 {a}: {'可用' if good else '不可用'}"))
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(proxies)))) as pool:
                list(pool.map(check_one, proxies))
            self.root.after(0, self._refresh_proxies)
        threading.Thread(target=worker, daemon=True).start()

    # === 定时任务 ===
    def _add_schedule(self):
        name = self.task_name_var.get().strip() or "未命名"
        interval = self.schedule_interval_var.get()
        task = self._collect_task_config()
        task["task_name"] = name
        job_id = f"{name}_{uuid.uuid4().hex[:8]}"

        def callback(t):
            if job_id in self._scheduled_running:
                self.root.after(0, lambda: self._log(f"定时任务跳过重叠执行: {name}"))
                return
            self._scheduled_running.add(job_id)
            self.root.after(0, lambda: self._log(f"定时任务触发: {name}"))
            def run():
                try: self._run_scheduled_task(t)
                finally:
                    self._scheduled_running.discard(job_id)
                    self.scheduler.finish(job_id)
            thread = threading.Thread(target=run, daemon=True)
            thread.start()

        if self.scheduler.add_job(job_id, task, interval, callback):
            self._refresh_schedules()

    def _run_scheduled_task(self, task: dict):
        scraper = None
        try:
            proxies = [p["address"] for p in list_proxies() if p["enabled"]]
            scraper = WebScraper(
                start_url=task["url"],
                mode=task.get("mode", "static"),
                headers={"User-Agent": task.get("ua")} if task.get("ua") else {},
                cookies=task.get("cookie") or None,
                delay=task.get("delay", 0.5),
                delay_random=task.get("delay_random", True),
                proxy_pool=proxies if proxies else None,
                random_ua=task.get("random_ua", False),
                retries=task.get("retries", 2),
                render=task.get("render", False),
                render_wait_until=task.get("render_wait_until", "domcontentloaded"),
                api_config=task.get("api_config"),
            )
            raw_rows = scraper.iter_run(
                list_selector=task["list_selector"],
                fields=task["fields"],
                selector_type=task.get("selector_type", "css"),
                max_pages=task.get("max_pages", 1),
                next_page_selector=task.get("page_selector") if task.get("page_mode") == "url" else None,
                next_page_mode="param" if task.get("page_mode") == "param" else "url",
                next_page_param=task.get("page_selector") or "page",
                next_page_step=task.get("page_step", 1),
                on_progress=lambda p, total: self.root.after(0, lambda: self._log(f"定时任务 第{p}页 累计{total}条")),
                on_log=lambda msg: self.root.after(0, lambda: self._log(f"[定时] {msg}")),
            )
            dedup_fields = [f.strip() for f in task.get("dedup_fields", "").split(",") if f.strip()] if task.get("dedup") else None
            data = process_rows(raw_rows, task.get("clean_rules") or {}, dedup_fields, dedup=bool(task.get("dedup")))
            record_id = save_record_stream(task.get("task_name", "定时任务"), task["url"], data)
            self.root.after(0, lambda: self._log(f"定时任务完成，保存记录 ID: {record_id}"))
            self.root.after(0, self._refresh_history)
        except Exception as e:
            self.root.after(0, lambda: self._log(f"定时任务失败: {e}"))
        finally:
            if scraper is not None:
                scraper.close()

    def _refresh_schedules(self):
        self.schedule_tree.delete(*self.schedule_tree.get_children())
        for job in self.scheduler.list_jobs():
            self.schedule_tree.insert("", tk.END, values=(job["id"], job["interval"], job["next_run"]))

    def _del_schedule(self):
        selected = self.schedule_tree.selection()
        for item in selected:
            vals = self.schedule_tree.item(item, "values")
            if vals:
                self.scheduler.remove_job(vals[0])
        self._refresh_schedules()

    # === 历史记录 ===
    def _refresh_history(self):
        self.history_tree.delete(*self.history_tree.get_children())
        for r in list_records():
            self.history_tree.insert("", tk.END, values=(r["id"], r["task_name"], r["start_url"], r["total_count"], r["created_at"]))

    def _view_history(self):
        selected = self.history_tree.selection()
        if not selected:
            return
        record_id = self.history_tree.item(selected[0], "values")[0]
        top = tk.Toplevel(self.root)
        top.title(f"历史记录详情 #{record_id}")
        top.geometry("700x500")
        text = scrolledtext.ScrolledText(top)
        text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        page = {"offset": 0}; page_size = 200; total = count_record_rows(int(record_id))
        bar = tk.Frame(top); bar.pack(fill=tk.X, padx=5)
        def refresh_page():
            rows = get_record_rows(int(record_id), limit=page_size, offset=page["offset"])
            text.configure(state=tk.NORMAL); text.delete("1.0", tk.END)
            text.insert(tk.END, json.dumps(rows, ensure_ascii=False, indent=2))
            pages = max(1, (total + page_size - 1) // page_size)
            current = page["offset"] // page_size + 1
            text.insert(tk.END, f"\n\n第 {current}/{pages} 页，显示 {page['offset'] + 1}-{page['offset'] + len(rows)} / 共 {total} 条")
            text.configure(state=tk.DISABLED)
            prev.configure(state=tk.NORMAL if page["offset"] else tk.DISABLED)
            next_btn.configure(state=tk.NORMAL if len(rows) == page_size else tk.DISABLED)
        def prev_page():
            page["offset"] = max(0, page["offset"] - page_size); refresh_page()
        def next_page():
            page["offset"] += page_size; refresh_page()
        prev = ttk.Button(bar, text="上一页", command=prev_page); prev.pack(side=tk.LEFT)
        next_btn = ttk.Button(bar, text="下一页", command=next_page); next_btn.pack(side=tk.LEFT, padx=5)
        refresh_page()
        text.configure(state=tk.DISABLED)

    def _export_history(self):
        selected = self.history_tree.selection()
        if not selected:
            return
        record_id = self.history_tree.item(selected[0], "values")[0]
        record = get_record(int(record_id))
        if not record:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            export(record["data"], path)
            messagebox.showinfo("完成", f"已导出到: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _delete_history(self):
        selected = self.history_tree.selection()
        for item in selected:
            record_id = self.history_tree.item(item, "values")[0]
            delete_record(int(record_id))
        self._refresh_history()


def main():
    root = tk.Tk()
    app = ScraperGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.scheduler.stop(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
