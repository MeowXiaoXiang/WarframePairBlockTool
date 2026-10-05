# Warframe 配對阻斷器

版本歷程請見 [變更紀錄](CHANGELOG.md)。

![Python 3.14](https://img.shields.io/badge/Python-3.14-blue?logo=python) ![License MIT](https://img.shields.io/badge/License-MIT-green) ![最新發布版 v3.0.0](https://img.shields.io/badge/Latest_release-v3.0.0-orange)

透過 Windows 防火牆暫時阻斷所選的 UDP 埠，降低加入其他玩家主機的機會。實際主機分配仍由遊戲決定。

> 介面中的「配對正常」表示未發現本工具的封鎖規則；程式不會檢查遊戲是否連線正常，或判斷目前由誰擔任主機。

## 下載

[下載 Windows 執行檔 v3.0.0](https://github.com/MeowXiaoXiang/WarframePairBlockTool/releases/download/v3.0.0/WarframePairBlockTool.exe)

[變更紀錄](CHANGELOG.md)中「尚未發布」的修改尚未包含在上述 v3.0.0 下載檔中。

## 功能特色

- **PySide6 介面**：使用 PySide6 建立主視窗、設定視窗與系統匣選單
- **系統匣支援**：關閉主視窗時隱藏至系統匣，可從系統匣重新開啟
- **快捷鍵支援**：可設定全域快捷鍵快速切換阻斷狀態
- **UDP 埠選擇**：可從六組預設的 UDP 埠配對中選擇
- **自動解除阻斷**：預設 20 秒後解除阻斷，避免長時間阻斷影響 P2P 連線的穩定性
- **自動請求系統管理員權限**：工具啟動時會自動請求系統管理員權限，以便修改防火牆規則
- **主題適應**：自動適應 Windows 10/11 的明亮/深色主題設定
- **不進行遊戲注入**：本工具僅通過控制 Windows 防火牆來達成目的，不會對遊戲進行任何注入操作
- **設定檔存放於 AppData**：設定和日誌儲存於 `%APPDATA%\WarframePairBlockTool`

目前原始碼會在啟動時清除所有顯示名稱完全符合 `WarframePairBlockPort` 的本機規則，並確認清理結果。若無法確認狀態，主按鈕顯示「重新檢查」，此時不會建立阻斷規則。從系統匣結束時會再次清理；若失敗，可選擇重試、仍要退出或取消。選擇仍要退出時，封鎖可能持續生效。

啟動檢查或重新檢查期間，可透過主按鈕、系統匣或快捷鍵預約一次阻斷或解除操作；檢查成功後才執行，重複按下不會累積操作。檢查失敗時取消預約，保留「重新檢查」，錯誤可從按鈕的滑鼠提示與日誌查看。還原設定或退出也會取消預約；建立、解除與退出清理期間不接受預約。

設定變更會短暫延遲後自動儲存。設定快捷鍵時可按 Esc 取消；開始後 15 秒內尚未完成設定也會自動取消，並保留原快捷鍵。再次啟動程式會喚出已開啟的視窗。

還原預設設定時，會先在背景解除本工具的封鎖並確認清理成功，再套用預設值；清理失敗時保留原設定，可再次嘗試還原。

日誌預設記錄 INFO，使用 `WarframePairBlockTool.exe --debug`（或 `-debug`）啟動可記錄 DEBUG。日誌依大小輪替，輪替後的檔案保留七天；儲存路徑為 `%APPDATA%\WarframePairBlockTool`。

## v3.0.0 版本更新

- 從 Tkinter 遷移到 PySide6 框架
- 更新主視窗與設定視窗介面
- 新增系統匣功能
- 支援全域快捷鍵
- 新增依系統主題顯示明暗介面的功能；執行中切換的問題由修復分支處理
- 重構專案結構，提高可維護性
- 增強系統通知功能

## 如何使用

1. **啟動工具**：

   - 雙擊 `WarframePairBlockTool.exe`，工具會自動請求系統管理員權限以修改防火牆規則。
2. **開始阻斷配對**：

   - 點擊「**配對正常**」按鈕，建立封鎖所選兩個 UDP 埠的規則，例如 4950 與 4955。
   - 按鈕會變為「**配對已阻斷**」狀態；需要確認規則內容時，可使用「查看防火牆」。
3. **自動解除阻斷**：

   - 預設阻斷 20 秒後自動解除。你也可以在工具中調整所需的阻斷時間。
4. **系統匣操作**：

   - 點擊主視窗的關閉按鈕會隱藏至系統匣；最小化按鈕則會最小化至工作列
   - 在系統匣圖示上按右鍵，可顯示主視窗、切換阻斷或結束程式

## 打包說明

1. **建立 Python 3.14 虛擬環境並安裝依賴**：在專案根目錄的 PowerShell 執行：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. **安裝 PyInstaller 並打包程式**：

   ```powershell
   .\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
   .\.venv\Scripts\python.exe -m PyInstaller build.spec --noconfirm --clean
   ```

3. **查看打包結果**：
   打包完成後，檔案會存放於 `dist` 資料夾內。

## 使用介面示意圖

以下圖片為舊版介面示意；目前原始碼中的提示文字與狀態顯示已有調整。

### 主介面展示

![主介面三態圖示](./markdown_imgs/main_interface.png)

圖中依序展示未阻斷、已阻斷和展開 UDP 埠選單的畫面：

- **左側**：正常狀態，按鈕為綠色，代表目前未進行封鎖
- **中間**：阻斷狀態，按鈕變為紅色，表示目前封鎖中
- **右側**：展開下拉選單，選擇遊戲內設定的 UDP 埠配對

---

### 系統匣功能與狀態顯示

![系統托盤功能](./markdown_imgs/tray_system.png)

透過系統匣圖示，可以快速執行：

- 顯示主視窗
- 切換阻斷狀態
- 查看配對阻斷狀態：綠點表示已解除、紅點表示已啟用；白點表示無法確認
- 一鍵開啟 Windows 防火牆管理介面

---

### 設定面板

![設定面板](./markdown_imgs/settings_panel.png)

此視窗可讓使用者快速調整功能偏好：

- **左側**：未設定快捷鍵，僅啟用 Windows 通知功能
- **右側**：已設定快捷鍵（如 `Alt + A`），可用於快速切換阻斷狀態
- 可點擊按鈕重新設定快捷鍵，或使用「還原預設設定」恢復 UDP 埠、自動恢復及通知設定，並移除快捷鍵

---

### 通知效果展示

![通知效果展示](./markdown_imgs/notifications.png)

當以下狀況發生時，程式會嘗試顯示 Windows 通知：

- 主視窗隱藏至系統匣
- 使用快捷鍵阻斷配對（顯示封鎖的 UDP 埠）
- 使用快捷鍵解除阻斷

> 須啟用「顯示 Windows 通知」。實際顯示方式也受 Windows 設定影響。

## 常見問題與注意事項

1. **無法成為主機？**

   - 檢查防火牆是否有名為「WarframePairBlockPort」的輸出封鎖規則
   - 確保工具中選擇的 UDP 埠與遊戲內設定相符（可在 Warframe 的「選項 → 系統 → 網路連接埠 [UDP]」查看）
   - 確認你的系統允許遊戲的 P2P 連線
2. **阻斷後看不到其他玩家？**

   - 過長的阻斷時間可能導致同步問題。
   - 可啟用「自動恢復配對」，避免忘記解除阻斷。
3. **防毒軟體阻擋執行檔？**

   - 先確認檔案來自預期的下載來源並檢查警告內容；不要直接將未確認的檔案加入信任清單。
4. **找不到系統匣圖示？**

   - 檢查 Windows 工作列右下角的隱藏圖示區域。
   - 確保程式已啟動且未被系統終止。
5. **想要查看或備份設定檔？**

   - 設定檔和日誌儲存於 `%APPDATA%\WarframePairBlockTool` 目錄
   - 可在檔案總管位址列輸入 `%APPDATA%\WarframePairBlockTool` 直接前往
   - 設定檔為 `WarframePairBlockTool.ini`，日誌為 `WarframePairBlockTool.log`

## 貢獻與支援

若有任何問題或建議，請在 GitHub 上提交 Issue 或 Pull Request。
