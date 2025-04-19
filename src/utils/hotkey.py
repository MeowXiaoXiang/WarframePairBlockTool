import threading
import keyboard
from PySide6.QtCore import QObject, Signal
from loguru import logger

class HotkeyManager(QObject):
    """用於處理跨線程的快捷鍵操作"""
    toggle_signal = Signal(bool)  # 修改為帶參數的信號
    
    def __init__(self):
        super().__init__()
        logger.debug("初始化快捷鍵管理器")
        self._thread = None
        self._stop_event = threading.Event()
    
    def register_hotkey(self, hotkey, callback):
        """註冊快捷鍵（在新線程中執行keyboard監聽）"""
        try:
            if not hotkey:
                logger.debug("沒有提供有效的快捷鍵")
                return False
                
            # 若已經有監聽線程，先停止它
            self.unregister_hotkey()
            
            # 重設停止事件
            self._stop_event.clear()
            
            def listener_thread():
                logger.debug(f"啟動快捷鍵監聽線程: {hotkey}")
                try:
                    keyboard.add_hotkey(hotkey, callback, suppress=False)
                    
                    # 持續運行直到停止事件被設置
                    while not self._stop_event.is_set():
                        self._stop_event.wait(0.1)  # 短暫睡眠以降低CPU使用率
                        
                    # 清理
                    keyboard.remove_hotkey(hotkey)
                    logger.debug("快捷鍵監聽已停止")
                except Exception as e:
                    logger.error(f"快捷鍵監聽發生錯誤: {e}")
                    logger.exception("詳細錯誤")
            
            # 啟動新的監聽線程
            self._thread = threading.Thread(target=listener_thread, daemon=True)
            self._thread.start()
            logger.info(f"已註冊快捷鍵: {hotkey}")
            return True
        except Exception as e:
            logger.error(f"註冊快捷鍵時發生錯誤: {e}")
            logger.exception("詳細錯誤")
            return False
    
    def unregister_hotkey(self):
        """取消註冊快捷鍵並停止監聽線程"""
        try:
            if self._thread and self._thread.is_alive():
                logger.debug("停止現有的快捷鍵監聽線程")
                self._stop_event.set()
                self._thread.join(1.0)  # 等待線程結束，最多1秒
                self._thread = None
                return True
            return False
        except Exception as e:
            logger.error(f"取消註冊快捷鍵時發生錯誤: {e}")
            logger.exception("詳細錯誤")
            return False
    
    def emit_toggle(self, from_hotkey=True):
        """發送切換信號到UI線程，標記是否來自快捷鍵"""
        try:
            logger.debug(f"發送切換信號到UI線程 [來自快捷鍵: {from_hotkey}]")
            self.toggle_signal.emit(from_hotkey)
        except Exception as e:
            logger.error(f"發送切換信號時發生錯誤: {e}")
            logger.exception("詳細錯誤")
    
    @staticmethod
    def format_hotkey_display(hotkey):
        """格式化快捷鍵顯示"""
        if not hotkey:
            return ""
            
        parts = hotkey.split('+')
        formatted_parts = []
        
        for part in parts:
            part = part.strip()
            # 特殊按鍵首字母大寫
            if part.lower() in ['ctrl', 'alt', 'shift', 'win']:
                formatted_parts.append(part.capitalize())
            # 單個字母全部大寫
            elif len(part) == 1 and part.isalpha():
                formatted_parts.append(part.upper())
            # 其他按鍵首字母大寫
            else:
                formatted_parts.append(part.capitalize())
                
        return ' + '.join(formatted_parts) 