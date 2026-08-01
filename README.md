# Qiskit 编程器

一个源码可用的轻量本地 Qiskit 图形编程环境，使用 Python 和 Tkinter 构建。它提供代码编辑、语法着色、运行/停止、输出查看和贝尔态示例，适合学习量子电路与 Qiskit 的 `transpile` 编译流程。

> 本项目是社区项目，与 IBM 或 Qiskit 官方没有隶属关系。

## 功能

- 本地编辑和运行 Python/Qiskit 代码
- 新建、打开、保存和另存为
- Python 基础语法着色
- `F5` 运行，`Shift+F5` 停止
- 内置贝尔态示例
- 在独立窗口显示 Matplotlib 图形
- 支持 Qiskit Aer 本地模拟器和 IBM Runtime 客户端

## 环境要求

- Python 3.11 或更高版本
- macOS、Linux 或 Windows
- Tkinter（通常随 Python 安装；部分 Linux 发行版需单独安装）

## 安装

```bash
git clone https://github.com/Isacc-1/qiskit-programmer.git
cd qiskit-programmer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows 激活虚拟环境：

```powershell
.venv\Scripts\activate
```

## 启动图形界面

```bash
python qiskit_ide.py
```

macOS 用户也可以双击 `启动Qiskit编程器.command`。

打开后，在编辑区输入代码并点击“▶ 运行”或按 `F5`，结果会显示在下方输出区。

## 终端示例

```bash
python hello_qiskit.py
```

示例会创建贝尔态：

```python
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)

state = Statevector.from_instruction(circuit)
print(circuit.draw())
print(state.probabilities_dict())
```

## 编译并模拟电路

Qiskit 使用 `transpile()` 把电路编译为目标后端支持的指令：

```python
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

circuit = QuantumCircuit(2, 2)
circuit.h(0)
circuit.cx(0, 1)
circuit.measure([0, 1], [0, 1])

backend = AerSimulator()
compiled = transpile(circuit, backend, optimization_level=2)
counts = backend.run(compiled, shots=1024).result().get_counts()

print(compiled.draw())
print(counts)
```

## 项目结构

```text
qiskit-programmer/
├── qiskit_ide.py                 # 图形编程器
├── hello_qiskit.py               # 最小贝尔态示例
├── requirements.txt              # Python 依赖
└── 启动Qiskit编程器.command       # macOS 双击启动脚本
```

## 许可证

本项目采用 [PolyForm Noncommercial License 1.0.0](LICENSE)：允许个人学习、研究、实验、业余项目，以及符合许可证定义的非商业组织使用；**不允许商业用途**。

因为许可证限制商业使用，本项目属于“源码可用（source-available）”，而不是 OSI 定义的开源软件。商业授权请联系版权所有者。
