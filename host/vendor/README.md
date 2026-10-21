# pySerial 离线依赖

此目录保留 pySerial 3.5 的 `serial` 模块与原包元数据，让电脑端在未联网安装依赖时也能使用串口。`board_link.py` 优先从本目录导入。

- 上游项目：[pySerial](https://github.com/pyserial/pyserial)
- 版本：3.5
- 许可证：BSD-3-Clause；源码保留原版权和许可证标识，包元数据位于 `pyserial-3.5.dist-info/`。

当前运输记录器使用 Python 标准库 Tkinter 作为界面，无需 PySide6、pyqtgraph 或 NumPy。使用系统环境安装时，可在项目根目录执行 `python -m pip install -r host/requirements.txt`。
