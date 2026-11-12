import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from ctypes import wintypes

APP = 'Hominhtuan95'
MAX_SECONDS = 10800  # 3 gio
KEYS = [('Tab', 0x09), ('Space', 0x20)] + [(f'Skill {i}', 0x30+i) for i in range(1, 10)] + [('Bom mau F7', 0x76), ('Bom mana F8', 0x77)]
VK_RETURN_CITY = 0x78  # F9
DEFAULTS = {'Tab': 3, 'Space': 5, 'Bom mau F7': 10, 'Bom mana F8': 10}
user32 = ctypes.windll.user32
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


def windows():
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @callback_type
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            if buf.value.strip():
                found.append((int(hwnd), buf.value.strip()))
        return True
    user32.EnumWindows(cb, 0)
    return found


def send_key(hwnd, vk):
    # Gửi phím tới HWND, không chiếm bàn phím đang sử dụng.
    # Game dùng DirectInput có thể không nhận PostMessage.
    scan = user32.MapVirtualKeyW(vk, 0)
    down = 1 | (scan << 16)
    up = down | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, 0x0100, vk, down)
    time.sleep(0.045)
    user32.PostMessageW(hwnd, 0x0101, vk, up)


class Slot:
    def __init__(self, parent, index, app):
        self.app = app
        self.index = index
        self.frame = ttk.LabelFrame(parent, text=f'Cửa sổ {index + 1}', padding=8)
        self.frame.grid(row=index // 2, column=index % 2, sticky='nsew', padx=5, pady=5)
        self.hwnd_var = tk.StringVar()
        self.targets = {}
        self.running = threading.Event()
        self.worker = None
        self.status = tk.StringVar(value='Đang dừng')
        ttk.Label(self.frame, text='Chọn cửa sổ game:').grid(row=0, column=0, columnspan=2, sticky='w')
        self.combo = ttk.Combobox(self.frame, textvariable=self.hwnd_var, state='readonly', width=41)
        self.combo.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(0, 7))
        ttk.Label(self.frame, text='Tác vụ').grid(row=2, column=0, sticky='w')
        ttk.Label(self.frame, text='Lặp lại (giây)').grid(row=2, column=1, columnspan=2, sticky='w')
        for r, (label, vk) in enumerate(KEYS, start=3):
            enabled = tk.BooleanVar(value=label in ('Tab', 'Space'))
            seconds = tk.StringVar(value=str(DEFAULTS.get(label, 2)))
            ttk.Checkbutton(self.frame, text=label, variable=enabled).grid(row=r, column=0, sticky='w')
            ttk.Entry(self.frame, textvariable=seconds, width=9).grid(row=r, column=1, sticky='w', padx=6, pady=1)
            self.targets[label] = (enabled, seconds, vk)
        row = 3 + len(KEYS)
        ttk.Separator(self.frame).grid(row=row, column=0, columnspan=3, sticky='ew', pady=5)
        self.city_enabled = tk.BooleanVar(value=False)
        self.city_seconds = tk.StringVar(value='3600')
        ttk.Checkbutton(self.frame, text='Về Thành F9', variable=self.city_enabled).grid(row=row+1, column=0, sticky='w')
        ttk.Entry(self.frame, textvariable=self.city_seconds, width=9).grid(row=row+1, column=1, sticky='w', padx=6)
        ttk.Label(self.frame, text='giây, tối đa 10800').grid(row=row+1, column=2, sticky='w')
        ttk.Label(self.frame, textvariable=self.status, foreground='#1768aa').grid(row=row+2, column=0, columnspan=3, sticky='w', pady=5)
        self.frame.columnconfigure(2, weight=1)

    def refresh(self, items):
        old = self.hwnd_var.get()
        values = [f'{hwnd} | {title}' for hwnd, title in items]
        self.combo['values'] = values
        if old in values:
            self.hwnd_var.set(old)
        elif not self.running.is_set():
            self.hwnd_var.set('')

    def prepare(self):
        selected = self.hwnd_var.get()
        if not selected:
            raise ValueError(f'Cửa sổ {self.index+1}: chưa chọn game')
        hwnd = int(selected.split(' | ', 1)[0])
        if not user32.IsWindow(hwnd):
            raise ValueError(f'Cửa sổ {self.index+1}: game đã đóng')
        tasks = []
        for label, (enabled, seconds, vk) in self.targets.items():
            if enabled.get():
                period = float(seconds.get().strip())
                if not 0.05 <= period <= MAX_SECONDS:
                    raise ValueError(f'{label}: thời gian phải từ 0.05 đến 10800 giây')
                tasks.append((label, vk, period))
        city_after = None
        if self.city_enabled.get():
            city_after = float(self.city_seconds.get().strip())
            if not 1 <= city_after <= MAX_SECONDS:
                raise ValueError('Về Thành: nhập từ 1 đến 10800 giây')
        if not tasks and city_after is None:
            raise ValueError(f'Cửa sổ {self.index+1}: chưa bật tác vụ nào')
        return hwnd, tasks, city_after

    def start(self, config):
        if self.running.is_set():
            return
        self.running.set()
        self.status.set('Đang chạy')
        self.worker = threading.Thread(target=self.loop, args=config, daemon=True)
        self.worker.start()

    def stop(self):
        self.running.clear()
        self.status.set('Đang dừng')

    def loop(self, hwnd, tasks, city_after):
        start = time.monotonic()
        due = {label: start for label, _, _ in tasks}
        try:
            while self.running.is_set():
                if not user32.IsWindow(hwnd):
                    self.app.set_status(self, 'Cửa sổ game đã đóng')
                    break
                now = time.monotonic()
                # Ưu tiên Về Thành: ngừng toàn bộ Skill/Tab/Space/F7/F8 trước khi gửi F9.
                if city_after is not None and now - start >= city_after:
                    self.running.clear()
                    self.app.set_status(self, 'Đã dừng Auto, chuẩn bị Về Thành F9')
                    send_key(hwnd, VK_RETURN_CITY)
                    self.app.set_status(self, 'Đã gửi F9 – Auto đã dừng')
                    return
                ready = [(label, vk, period) for label, vk, period in tasks if due[label] <= now]
                if ready:
                    label, vk, period = min(ready, key=lambda t: due[t[0]])
                    # Không gửi phím mới nếu đã dừng; chỉ có 1 luồng gửi cho mỗi HWND.
                    if not self.running.is_set():
                        break
                    send_key(hwnd, vk)
                    due[label] = time.monotonic() + period
                else:
                    time.sleep(0.035)
        except Exception as exc:
            self.app.set_status(self, f'Lỗi: {exc}')
        finally:
            self.running.clear()


class App:
    def __init__(self, root):
        self.root = root
        root.title('Hominhtuan95 - Auto 4 cửa sổ')
        root.geometry('1050x820')
        root.minsize(900, 650)
        top = ttk.Frame(root, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='HOMINHTUAN95 | AUTO 4 CỬA SỔ', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(top, text='9 Skill (1–9) | Tab | Space | F7 Máu | F8 Mana | F9 Về Thành | F1 Bật/Tắt').pack(anchor='w')
        toolbar = ttk.Frame(root, padding=(10, 0, 10, 5))
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Làm mới cửa sổ', command=self.refresh).pack(side='left', padx=(0, 8))
        ttk.Button(toolbar, text='BẬT AUTO (F1)', command=self.start_all).pack(side='left', padx=4)
        ttk.Button(toolbar, text='TẮT AUTO (F1)', command=self.stop_all).pack(side='left', padx=4)
        ttk.Label(toolbar, text='Chỉ chạy các ô đã chọn cửa sổ game').pack(side='left', padx=10)
        outer = ttk.Frame(root, padding=5)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        self.slots = [Slot(outer, i, self) for i in range(4)]
        footer = ttk.Frame(root, padding=8)
        footer.pack(fill='x')
        ttk.Label(footer, text='Liên hệ Zalo: TuanHo – 0398438721', font=('Segoe UI', 11, 'bold')).pack(side='left')
        ttk.Label(footer, text='F1 chỉ hoạt động khi cửa sổ Hominhtuan95 được chọn').pack(side='right')
        root.bind('<F1>', self.toggle)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def refresh(self):
        items = windows()
        for slot in self.slots:
            slot.refresh(items)

    def set_status(self, slot, value):
        try:
            self.root.after(0, lambda: slot.status.set(value))
        except RuntimeError:
            pass

    def start_all(self):
        configs = []
        selected_hwnds = set()
        try:
            for slot in self.slots:
                if not slot.hwnd_var.get():
                    continue
                cfg = slot.prepare()
                if cfg[0] in selected_hwnds:
                    raise ValueError('Một cửa sổ game không được chọn ở nhiều ô')
                selected_hwnds.add(cfg[0])
                configs.append((slot, cfg))
            if not configs:
                raise ValueError('Hãy chọn ít nhất một cửa sổ game')
        except (ValueError, TypeError) as exc:
            messagebox.showerror('Cấu hình chưa đúng', str(exc))
            return
        for slot, cfg in configs:
            slot.start(cfg)

    def stop_all(self):
        for slot in self.slots:
            slot.stop()

    def toggle(self, event=None):
        if any(slot.running.is_set() for slot in self.slots):
            self.stop_all()
        else:
            self.start_all()
        return 'break'

    def close(self):
        self.stop_all()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    try:
        ttk.Style().theme_use('clam')
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
