#!/usr/bin/env python
# _*_ coding:utf-8 _*_

import os
import logging
import threading
import time
from src.utils import setting

LOG_DIR = setting.LOG_DIR
os.makedirs(LOG_DIR, exist_ok=True)


class Log:
    """
    单例日志类
    """

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.logger = logging.getLogger("app_logger")
        # 根据环境变量设置日志级别
        log_level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
        level = getattr(logging, log_level, logging.INFO)
        self.logger.setLevel(level)
        self.log_level = level

        formatter = logging.Formatter(
            "[%(asctime)s] [%(filename)s|%(funcName)s] "
            "[line:%(lineno)d] %(levelname)-8s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 文件输出
        self.current_log_file = None
        self.file_handler = None
        self.formatter = formatter
        self.update_file_handler()

    def update_file_handler(self):
        folder_name = os.path.join(LOG_DIR, time.strftime("%Y-%m-%d"))
        os.makedirs(folder_name, exist_ok=True)
        log_file_path = os.path.join(folder_name, f"{time.strftime('%H')}.log")

        if self.current_log_file != log_file_path:
            if self.file_handler:
                self.logger.removeHandler(self.file_handler)
                self.file_handler.close()

            fh = logging.FileHandler(log_file_path, encoding="utf-8")
            fh.setLevel(self.log_level)
            fh.setFormatter(self.formatter)
            self.logger.addHandler(fh)

            self.file_handler = fh
            self.current_log_file = log_file_path

    def _write(self, level, message):
        self.update_file_handler()
        getattr(self.logger, level)(message)

    def debug(self, message):
        self._write("debug", message)

    def info(self, message):
        self._write("info", message)

    def warning(self, message):
        self._write("warning", message)

    def error(self, message):
        self._write("error", message)
