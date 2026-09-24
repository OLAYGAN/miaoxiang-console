# 交给另一台 Codex 的说明

这是一个完整的开发源码快照，用于在另一台电脑上继续修改、修 bug、运行测试和重新打包。不要只把 `MiaoxiangConsole.exe` 交给 Codex；exe 只能运行，不能方便地继续修改。

## 打开方式

1. 把这整个源码目录放到本地可写位置，例如 `D:\MusicAI\aimusic`。
2. 在 Codex 中打开这个目录。
3. 确保电脑安装了 Python 3.11 或更高版本，并安装了 Google Chrome 或 Microsoft Edge。
4. 首次安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m playwright install chromium
```

5. 运行自动化测试：

```powershell
.\.venv\Scripts\python -m pytest
```

6. 启动控制台：

```powershell
.\.venv\Scripts\python -m backend.main
```

也可以直接双击项目根目录的 `启动控制台.bat`。

## 后续修改

- 后端代码在 `backend/`。
- 前端代码在 `frontend/`。
- 测试代码在 `tests/`。
- 当前账号配置和断点数据在 `data/`。
- 修改完成后重新运行测试。
- 如果要生成最终可执行程序，双击 `打包EXE.bat`，然后复制整个 `dist\MiaoxiangConsole` 文件夹或对应压缩包。

## 注意事项

- 这个源码包保留了 `.git` 和当前工作区改动，方便继续追踪版本。
- `data/` 中可能包含本机账号、API Key 和绝对路径。换电脑后，如果目录不同，需要在账号设置或系统设置中重新选择路径。
- `dist/` 和 `build/` 没有放进来，它们是构建产物，不属于源码。
- 当前项目依赖定义在 `pyproject.toml`，不是 `requirements.txt`。
