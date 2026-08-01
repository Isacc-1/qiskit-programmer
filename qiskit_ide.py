import os
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import traceback
from io import BytesIO
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


SAMPLE_CODE = '''from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

# 创建两个纠缠的量子比特
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)

state = Statevector.from_instruction(circuit)
probabilities = {
    str(bits): round(float(probability), 4)
    for bits, probability in state.probabilities_dict().items()
}

print(circuit.draw())
print("测量概率:", probabilities)
'''


def run_user_script(script_path: str) -> None:
    """Run an editor buffer inside the bundled Python/Qiskit runtime."""
    path = Path(script_path).resolve()
    code = path.read_text(encoding="utf-8")
    # Render with a non-interactive backend.  Native Matplotlib GUI backends
    # are fragile in a frozen child process, so the IDE displays the rendered
    # figures itself after the user's script finishes.
    os.environ["MPLBACKEND"] = "Agg"
    mpl_config = Path(tempfile.gettempdir()) / "QiskitProgrammer-matplotlib"
    mpl_config.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config))
    namespace = {
        "__name__": "__main__",
        "__file__": str(path),
        "__builtins__": __builtins__,
    }
    sys.argv = [str(path)]
    try:
        exec(compile(code, str(path), "exec"), namespace)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)

    # Jupyter displays returned figures automatically.  Recreate that behavior
    # in the desktop app with a small, stable Tk image viewer.
    try:
        import matplotlib.pyplot as plt

        if plt.get_fignums():
            from PIL import Image, ImageTk

            figures = [plt.figure(number) for number in plt.get_fignums()]
            viewer = tk.Tk()
            viewer.title("Qiskit 图形结果")
            viewer.configure(background="white")

            windows: list[tk.Misc] = [viewer]
            for index, figure in enumerate(figures):
                window = viewer if index == 0 else tk.Toplevel(viewer)
                window.title(f"Qiskit 图形结果 {index + 1}")

                buffer = BytesIO()
                figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
                buffer.seek(0)
                image = Image.open(buffer)
                max_size = (
                    int(viewer.winfo_screenwidth() * 0.9),
                    int(viewer.winfo_screenheight() * 0.8),
                )
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)

                label = ttk.Label(window, image=photo)
                label.pack(fill="both", expand=True, padx=10, pady=10)
                window._qiskit_photo = photo  # type: ignore[attr-defined]
                window._qiskit_buffer = buffer  # type: ignore[attr-defined]
                windows.append(window)

            viewer.mainloop()
    except ImportError:
        pass


class QiskitIDE(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Qiskit 编程器")
        self.geometry("1100x720")
        self.minsize(760, 520)

        self.current_file: Path | None = None
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str | None] = queue.Queue()
        self.modified = False

        self._build_style()
        self._build_menu()
        self._build_toolbar()
        self._build_workspace()
        self._bind_shortcuts()

        self.editor.insert("1.0", SAMPLE_CODE)
        self.editor.edit_modified(False)
        self._highlight()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._poll_output)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
        style.configure("Run.TButton", font=("Helvetica", 13, "bold"))

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="新建", command=self.new_file, accelerator="⌘N")
        file_menu.add_command(label="打开…", command=self.open_file, accelerator="⌘O")
        file_menu.add_command(label="保存", command=self.save_file, accelerator="⌘S")
        file_menu.add_command(label="另存为…", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._close, accelerator="⌘Q")
        menu.add_cascade(label="文件", menu=file_menu)

        run_menu = tk.Menu(menu, tearoff=False)
        run_menu.add_command(label="运行代码", command=self.run_code, accelerator="F5")
        run_menu.add_command(label="停止运行", command=self.stop_code, accelerator="Shift+F5")
        run_menu.add_separator()
        run_menu.add_command(label="载入贝尔态示例", command=self.load_sample)
        menu.add_cascade(label="运行", menu=run_menu)
        self.config(menu=menu)

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="打开", command=self.open_file).pack(side="left", padx=3)
        ttk.Button(toolbar, text="保存", command=self.save_file).pack(side="left", padx=3)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        self.run_button = ttk.Button(
            toolbar, text="▶ 运行 (F5)", command=self.run_code, style="Run.TButton"
        )
        self.run_button.pack(side="left", padx=3)
        self.stop_button = ttk.Button(toolbar, text="■ 停止", command=self.stop_code, state="disabled")
        self.stop_button.pack(side="left", padx=3)
        ttk.Button(toolbar, text="示例", command=self.load_sample).pack(side="left", padx=8)

        self.status = ttk.Label(toolbar, text="就绪 · Qiskit 本地环境")
        self.status.pack(side="right", padx=6)

    def _build_workspace(self) -> None:
        pane = ttk.Panedwindow(self, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        editor_frame = ttk.LabelFrame(pane, text="Python / Qiskit 代码", padding=5)
        output_frame = ttk.LabelFrame(pane, text="运行结果", padding=5)
        pane.add(editor_frame, weight=3)
        pane.add(output_frame, weight=2)

        self.editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("Menlo", 14),
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="white",
            selectbackground="#375a7f",
            padx=10,
            pady=10,
        )
        editor_y = ttk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        editor_x = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=editor_y.set, xscrollcommand=editor_x.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        editor_y.grid(row=0, column=1, sticky="ns")
        editor_x.grid(row=1, column=0, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        self.editor.tag_configure("keyword", foreground="#569cd6")
        self.editor.tag_configure("string", foreground="#ce9178")
        self.editor.tag_configure("comment", foreground="#6a9955")
        self.editor.tag_configure("builtin", foreground="#4ec9b0")
        self.editor.bind("<<Modified>>", self._on_modified)
        self.editor.bind("<KeyRelease>", lambda _event: self._highlight())

        self.output = tk.Text(
            output_frame,
            wrap="word",
            state="disabled",
            font=("Menlo", 13),
            background="#101010",
            foreground="#eeeeee",
            padx=10,
            pady=10,
        )
        output_y = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=output_y.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        output_y.grid(row=0, column=1, sticky="ns")
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)

    def _bind_shortcuts(self) -> None:
        command = "Command" if sys.platform == "darwin" else "Control"
        self.bind(f"<{command}-n>", lambda _event: self.new_file())
        self.bind(f"<{command}-o>", lambda _event: self.open_file())
        self.bind(f"<{command}-s>", lambda _event: self.save_file())
        self.bind("<F5>", lambda _event: self.run_code())
        self.bind("<Shift-F5>", lambda _event: self.stop_code())

    def _on_modified(self, _event: tk.Event) -> None:
        if self.editor.edit_modified():
            self.modified = True
            self.editor.edit_modified(False)
            self._update_title()

    def _update_title(self) -> None:
        name = self.current_file.name if self.current_file else "未命名.py"
        marker = " *" if self.modified else ""
        self.title(f"{name}{marker} — Qiskit 编程器")

    def _highlight(self) -> None:
        code = self.editor.get("1.0", "end-1c")
        for tag in ("keyword", "string", "comment", "builtin"):
            self.editor.tag_remove(tag, "1.0", "end")

        patterns = {
            "comment": r"#[^\n]*",
            "string": r"(?:'''[\s\S]*?'''|\"\"\"[\s\S]*?\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")",
            "keyword": r"\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|raise|return|True|try|while|with|yield)\b",
            "builtin": r"\b(?:print|range|len|str|float|int|dict|list|set|tuple|QuantumCircuit|Statevector)\b",
        }
        for tag, pattern in patterns.items():
            for match in re.finditer(pattern, code):
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                self.editor.tag_add(tag, start, end)

    def _confirm_discard(self) -> bool:
        if not self.modified:
            return True
        answer = messagebox.askyesnocancel("尚未保存", "要先保存当前代码吗？")
        if answer is None:
            return False
        if answer:
            return self.save_file()
        return True

    def new_file(self) -> None:
        if not self._confirm_discard():
            return
        self.editor.delete("1.0", "end")
        self.current_file = None
        self.modified = False
        self._update_title()

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        filename = filedialog.askopenfilename(
            title="打开 Python 文件", filetypes=[("Python 文件", "*.py"), ("所有文件", "*")]
        )
        if not filename:
            return
        try:
            text = Path(filename).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))
            return
        self.current_file = Path(filename)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.modified = False
        self.editor.edit_modified(False)
        self._highlight()
        self._update_title()

    def save_file(self) -> bool:
        if self.current_file is None:
            return self.save_as()
        try:
            self.current_file.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("无法保存", str(exc))
            return False
        self.modified = False
        self._update_title()
        self.status.configure(text=f"已保存 · {self.current_file.name}")
        return True

    def save_as(self) -> bool:
        filename = filedialog.asksaveasfilename(
            title="保存 Python 文件",
            defaultextension=".py",
            filetypes=[("Python 文件", "*.py"), ("所有文件", "*")],
        )
        if not filename:
            return False
        self.current_file = Path(filename)
        return self.save_file()

    def load_sample(self) -> None:
        if not self._confirm_discard():
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", SAMPLE_CODE)
        self.current_file = None
        self.modified = True
        self._highlight()
        self._update_title()

    def _write_output(self, text: str, clear: bool = False) -> None:
        self.output.configure(state="normal")
        if clear:
            self.output.delete("1.0", "end")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def run_code(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("正在运行", "请先停止当前程序。")
            return

        code = self.editor.get("1.0", "end-1c")
        if self.current_file:
            working_dir = self.current_file.parent
        elif getattr(sys, "frozen", False):
            working_dir = Path.home() / "Documents" / "QiskitProjects"
            working_dir.mkdir(parents=True, exist_ok=True)
        else:
            working_dir = Path(__file__).parent
        temp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="qiskit_run_", dir=working_dir, delete=False, encoding="utf-8"
        )
        temp.write(code)
        temp.close()
        temp_path = Path(temp.name)

        self._write_output("正在使用本地 Qiskit 环境运行…\n\n", clear=True)
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.configure(text="运行中…")

        def worker() -> None:
            try:
                if getattr(sys, "frozen", False):
                    command = [sys.executable, "--run-script", str(temp_path)]
                else:
                    command = [sys.executable, "-u", str(temp_path)]
                self.process = subprocess.Popen(
                    command,
                    cwd=working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
                assert self.process.stdout is not None
                for line in self.process.stdout:
                    self.output_queue.put(line)
                return_code = self.process.wait()
                message = "\n✓ 运行完成\n" if return_code == 0 else f"\n✗ 程序退出，代码 {return_code}\n"
                self.output_queue.put(message)
            except Exception as exc:
                self.output_queue.put(f"\n无法运行：{exc}\n")
            finally:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
                self.output_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def stop_code(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            self._write_output("\n正在停止…\n")
        except OSError as exc:
            self._write_output(f"\n停止失败：{exc}\n")

    def _poll_output(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item is None:
                    self.process = None
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.status.configure(text="就绪 · Qiskit 本地环境")
                else:
                    self._write_output(item)
        except queue.Empty:
            pass
        self.after(80, self._poll_output)

    def _close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("程序仍在运行", "停止程序并退出吗？"):
                return
            self.stop_code()
        if self._confirm_discard():
            self.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--run-script":
        run_user_script(sys.argv[2])
    else:
        app = QiskitIDE()
        app.mainloop()
