import tkinter as tk
from tkinter import ttk
import serial
import time
import os
import threading
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import math
import re
import sqlite3
from collections import deque
from urllib.parse import urlencode
import urllib.request
import ssl
try:
    import certifi
    HAS_CERTIFI = True
except Exception:
    HAS_CERTIFI = False

# Lớp Cửa sổ Lịch sử (Không thay đổi)
class HistoryWindow(tk.Toplevel):
    def __init__(self, master=None, colors=None):
        super().__init__(master)
        self.title("Lịch sử Đo Độ đục")
        self.geometry("600x400")
        self.colors = colors or {"bg_main": "#111827", "text": "#D1D5DB"}
        self.configure(bg=self.colors["bg_main"])
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        columns = ("timestamp", "voltage", "turbidity", "status")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        self.tree.heading("timestamp", text="Thời gian")
        self.tree.heading("voltage", text="Điện áp (mV)")
        self.tree.heading("turbidity", text="Độ đục (NTU)")
        self.tree.heading("status", text="Trạng thái")
        self.tree.column("timestamp", width=150, anchor=tk.W)
        self.tree.column("voltage", width=100, anchor=tk.CENTER)
        self.tree.column("turbidity", width=100, anchor=tk.CENTER)
        self.tree.column("status", width=120, anchor=tk.W)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.tag_configure('distilled', foreground='#22C55E')
        self.tree.tag_configure('clear', foreground='#38BDF8')
        self.tree.tag_configure('slight', foreground='#EAB308')
        self.tree.tag_configure('cloudy', foreground='#F97316')
        self.tree.tag_configure('very_cloudy', foreground='#EF4444')
        button_frame = ttk.Frame(self, padding=(0, 10))
        button_frame.pack(fill="x")
        ttk.Button(button_frame, text="Làm mới", command=self.load_data).pack(side="left", padx=10)
        ttk.Button(button_frame, text="Đóng", command=self.destroy).pack(side="right", padx=10)
        self.load_data()

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turbidity.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT ts, voltage, turbidity, status FROM readings ORDER BY id DESC LIMIT 500")
            rows = cur.fetchall()
            conn.close()
            for ts, voltage, turbidity, status in rows:
                status_key = (status or "").replace(" ", "_").lower()
                status_tag = ""
                if "cất" in status_key: status_tag = 'distilled'
                elif "trong" in status_key: status_tag = 'clear'
                elif "hơi_đục" in status_key: status_tag = 'slight'
                elif "đục" in status_key and "rất" not in status_key: status_tag = 'cloudy'
                elif "rất_đục" in status_key or "rất" in status_key: status_tag = 'very_cloudy'
                self.tree.insert("", tk.END, values=(ts, round(voltage), round(turbidity, 2), status), tags=(status_tag,))
        except Exception as e:
            self.tree.insert("", tk.END, values=(f"Lỗi tải lịch sử: {e}", "", "", ""))


# Lớp Widget Đồng hồ Gauge tùy chỉnh
class GaugeWidget(tk.Canvas):
    def __init__(self, master=None, width=200, height=120, label="", unit="", **kwargs):
        super().__init__(master, width=width, height=height, borderwidth=0, highlightthickness=0, **kwargs)
        self.width = width
        self.height = height
        self.label = label
        self.unit = unit
        self.value = 0
        self.bg_color = "#1F2937"
        self.fill_color = "#374151"
        self.outline_color = "#4B5563"
        self.needle_color = "#EF4444"
        self.text_color = "#F9FAFB"
        self.configure(bg=self.bg_color)
        self.draw_gauge()

    def draw_gauge(self):
        self.delete("all")
        self.create_arc(10, 10, self.width - 10, self.height * 2 - 20, start=0, extent=180, style=tk.ARC, outline=self.outline_color, width=4, fill=self.fill_color)
        self.value_arc = self.create_arc(25, 25, self.width - 25, self.height * 2 - 45, start=180, extent=0, style=tk.ARC, outline=self.get_color_for_value(0), width=16)
        self.create_text(self.width / 2, self.height - 45, text=self.label, font=("Arial", 12), fill=self.text_color)
        self.value_text = self.create_text(self.width / 2, self.height - 20, text=f"0.0 {self.unit}", font=("Arial", 16, "bold"), fill=self.text_color)
        self.needle = self.create_line(self.width / 2, self.height-12, self.width / 2, 30, fill=self.needle_color, width=3)
        self.set_value(self.value)

    def set_value(self, value):
        # Thang đo 0-1000 NTU
        self.value = max(0, min(1000, value))
        self.itemconfig(self.value_text, text=f"{self.value:.1f} {self.unit}")
        angle = (self.value / 1000.0) * 180.0
        self.itemconfig(self.value_arc, extent=-angle, outline=self.get_color_for_value(self.value))
        angle_rad = math.radians(180 - angle)
        center_x, center_y = self.width / 2, self.height - 12
        end_x = center_x + (self.height - 35) * math.cos(angle_rad)
        end_y = center_y - (self.height - 35) * math.sin(angle_rad)
        self.coords(self.needle, center_x, center_y, end_x, end_y)

    def get_color_for_value(self, value):
        if value <= 10: return "#38BDF8"    # Nước trong
        elif value <= 50: return "#EAB308"  # Nước hơi đục
        elif value <= 100: return "#F97316" # Nước đục
        else: return "#EF4444"              # Nước rất đục

# Giao diện chính
class TurbiditySensorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard Giám sát Độ đục Nước")
        self.root.geometry("850x700")
        self.root.resizable(True, True)

        self.colors = {
            "bg_main": "#111827", "bg_card": "#1F2937",
            "text": "#D1D5DB", "text_header": "#F9FAFB", "accent": "#38BDF8",
        }
        self.root.configure(bg=self.colors["bg_main"])
        
        self.serial_connection = None
        self.is_running = False
        self.turbidity_data = []
        self.timestamps = []
        self.history_win = None
        
        self.last_log_time = None
        self.log_interval = 3600  # 1 giờ (3600 giây)
        self.last_turbidity = None
        self.last_voltage = None

        self.current_alert_level = 0
        self.recent_samples = deque(maxlen=120)  # store last ~2 minutes assuming ~1s sample
        self.last_command_sent_at = 0
        self.last_command_type = None
        self.last_notify_at = 0

        # Settings
        self.DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turbidity.db")
        self.TELEGRAM_MIN_INTERVAL_SEC = 60  # giữ cooldown chung; trạng thái thay đổi sẽ bỏ qua
        self.TREND_WINDOW_SEC = 60
        self.TREND_ALERT_SLOPE = 30.0  # NTU per minute

        self.create_styles()
        self.create_widgets()
        # Đường dẫn file .env để lưu cài đặt Telegram (không commit)
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        self.telegram_token = None
        self.telegram_chat_id = None
        self.load_env_settings()

        self.connect_to_arduino()
        self.init_db()
        self.periodic_log()

    def create_styles(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=self.colors["bg_main"], foreground=self.colors["text"], borderwidth=0, focuscolor=self.colors["bg_main"])
        style.configure('TFrame', background=self.colors["bg_main"])
        style.configure('Card.TFrame', background=self.colors["bg_card"])
        style.configure('TButton', font=('Arial', 10, 'bold'), padding=10, background="#374151", foreground=self.colors["text_header"], borderwidth=0)
        style.map('TButton', background=[('active', self.colors["accent"])])
        style.configure("Treeview", rowheight=25, fieldbackground=self.colors["bg_card"], background=self.colors["bg_card"], foreground=self.colors["text"])
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'), background="#374151", foreground=self.colors["text_header"])
        style.map("Treeview.Heading", background=[('active', self.colors["accent"])])

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        header_label = tk.Label(main_frame, text="Dashboard Giám sát Độ đục Nước", bg=self.colors["bg_main"], fg=self.colors["text_header"], font=("Arial", 28, "bold"))
        header_label.grid(row=0, column=0, pady=(0, 10))
        status_controls_frame = ttk.Frame(main_frame)
        status_controls_frame.grid(row=1, column=0, sticky="ew", pady=10)
        status_controls_frame.columnconfigure(0, weight=1)
        status_controls_frame.columnconfigure(1, weight=0)
        self.status_label = tk.Label(status_controls_frame, text="Đang kết nối tới Arduino...", bg=self.colors["bg_main"], fg=self.colors["text"], font=("Arial", 11))
        self.status_label.grid(row=0, column=0, sticky="w", padx=10)
        button_frame = ttk.Frame(status_controls_frame)
        button_frame.grid(row=0, column=1, sticky="e")
        self.start_button = ttk.Button(button_frame, text="Bắt đầu", command=self.start_monitoring)
        self.start_button.pack(side="left", padx=5)
        self.stop_button = ttk.Button(button_frame, text="Dừng lại", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.pack(side="left", padx=5)
        self.connect_button = ttk.Button(button_frame, text="Kết nối lại", command=self.connect_to_arduino)
        self.connect_button.pack(side="left", padx=5)
        self.history_button = ttk.Button(button_frame, text="Lịch sử đo", command=self.open_history_window)
        self.history_button.pack(side="left", padx=5)
    # Đã gỡ bỏ các nút cài đặt và gửi thử Telegram theo yêu cầu
        gauge_frame = ttk.Frame(main_frame)
        gauge_frame.grid(row=2, column=0, pady=20)
        self.turbidity_gauge = GaugeWidget(gauge_frame, width=300, height=180, label="Độ đục", unit="NTU", bg=self.colors["bg_card"])
        self.turbidity_gauge.pack()
        cards_frame = ttk.Frame(main_frame)
        cards_frame.grid(row=3, column=0, sticky="ew", pady=10)
        cards_frame.columnconfigure([0, 1], weight=1)
        status_card = ttk.Frame(cards_frame, style='Card.TFrame', padding=15)
        status_card.grid(row=0, column=0, sticky="nsew", padx=10)
        status_card.pack_propagate(False)
        tk.Label(status_card, text="🌊 Trạng thái Nước", font=("Arial", 16, "bold"), bg=self.colors["bg_card"], fg=self.colors["text_header"]).pack()
        # Hàng hiển thị trạng thái gồm chấm chỉ báo và nhãn trạng thái
        status_row = ttk.Frame(status_card, style='Card.TFrame')
        status_row.pack(pady=10)
        # Chỉ báo nhẹ (dot) - mặc định màu xám trung tính
        self.status_indicator = tk.Canvas(status_row, width=18, height=18, bg=self.colors["bg_card"], highlightthickness=0)
        self.status_indicator_circle = self.status_indicator.create_oval(3, 3, 15, 15, fill="#6B7280", outline="#111827")
        self.status_indicator.pack(side="left", padx=(0, 8))
        # Nhãn trạng thái
        self.water_status_label = tk.Label(status_row, text="--", font=("Arial", 24, "bold"), bg=self.colors["bg_card"], fg=self.colors["accent"])
        self.water_status_label.pack(side="left")
        status_card.config(height=120)
        volt_card = ttk.Frame(cards_frame, style='Card.TFrame', padding=15)
        volt_card.grid(row=0, column=1, sticky="nsew", padx=10)
        volt_card.pack_propagate(False)
        tk.Label(volt_card, text="⚡ Điện áp Cảm biến", font=("Arial", 16, "bold"), bg=self.colors["bg_card"], fg=self.colors["text_header"]).pack()
        self.voltage_label = tk.Label(volt_card, text="-- V", font=("Arial", 24, "bold"), bg=self.colors["bg_card"], fg=self.colors["accent"])
        self.voltage_label.pack(pady=10)
        volt_card.config(height=120)
        self.graph_frame = ttk.Frame(main_frame, style='Card.TFrame')
        self.graph_frame.grid(row=4, column=0, pady=20, padx=10, sticky="nsew")
        main_frame.rowconfigure(4, weight=1)
        self.figure = Figure(figsize=(6, 4), dpi=100, facecolor=self.colors["bg_card"])
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Lịch sử Độ đục (50 điểm gần nhất)", color=self.colors["text_header"])
        self.ax.set_xlabel("Thời gian", color=self.colors["text"])
        self.ax.set_ylabel("NTU", color=self.colors["text"])
        self.ax.tick_params(axis='x', colors=self.colors["text"])
        self.ax.tick_params(axis='y', colors=self.colors["text"])
        self.ax.grid(True, linestyle='--', alpha=0.2, color=self.colors["text"])
        self.ax.set_facecolor("#374151")
        for spine in self.ax.spines.values(): spine.set_edgecolor(self.colors["text"])
        self.line, = self.ax.plot([], [], color=self.colors["accent"], marker='o', markersize=3, linewidth=2)
        self.figure.tight_layout()
        self.canvas_graph = FigureCanvasTkAgg(self.figure, master=self.graph_frame)
        self.canvas_graph.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

    def open_history_window(self):
        if self.history_win is None or not self.history_win.winfo_exists():
            self.history_win = HistoryWindow(self.root, colors=self.colors)
            self.history_win.transient(self.root)
        else:
            self.history_win.lift() 
    
    def connect_to_arduino(self):
        try:
            ports = ['COM3', 'COM4', 'COM5', '/dev/ttyUSB0', '/dev/ttyACM0', '/dev/ttyS0']
            for port in ports:
                try:
                    # Tăng thời gian chờ (sleep) sau khi kết nối
                    self.serial_connection = serial.Serial(port=port, baudrate=9600, timeout=1, write_timeout=1)
                    print(f"Opening port {port}...")
                    time.sleep(2) # Cho Arduino thời gian khởi động lại
                    self.serial_connection.flushInput() # Xóa bộ đệm
                    print(f"Port {port} opened. Flushing input.")
                    self.status_label.config(text=f"Đã kết nối trên {port}")
                    print(f"Connected to Arduino on {port}")
                    
                    # Tự động bắt đầu giám sát sau khi kết nối thành công
                    self.start_monitoring() 
                    return True
                except serial.SerialException as e:
                    print(f"Failed to connect on {port}: {e}")
                    continue
            self.status_label.config(text="Kết nối thất bại - Kiểm tra Arduino")
            print("Failed to connect to Arduino.")
            return False
        except Exception as e:
            print(f"Serial connection error: {e}")
            self.status_label.config(text="Lỗi Serial - Kiểm tra kết nối")
            return False

    def start_monitoring(self):
        if self.serial_connection and self.serial_connection.is_open:
            if not self.is_running: # Chỉ bắt đầu nếu chưa chạy
                self.is_running = True
                self.start_button.config(state=tk.DISABLED)
                self.stop_button.config(state=tk.NORMAL)
                self.status_label.config(text="Đang giám sát... (Nguồn: Arduino)")
                self.reading_thread = threading.Thread(target=self.read_serial_data, daemon=True)
                self.reading_thread.start()
                self.last_log_time = time.time() # Reset đồng hồ log
                print("Monitoring started.")
        else:
            self.status_label.config(text="Không tìm thấy cảm biến! Hãy kết nối lại.")
            print("Monitoring start failed: No serial connection.")

    def stop_monitoring(self):
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text="Đã dừng giám sát.")
        print("Monitoring stopped.")

    def read_serial_data(self):
        while self.is_running and self.serial_connection and self.serial_connection.is_open:
            try:
                if self.serial_connection.in_waiting > 0:
                    line = self.serial_connection.readline().decode('utf-8', errors='ignore').strip()
                    if not line: continue
                    
                    # === SỬA LỖI: ĐÃ TẮT THÔNG BÁO DEBUG ===
                    # print(f"Raw serial data: {line}") 
                    
                    try:
                        voltage_mV, turbidity = self.parse_serial_line(line)
                        self.update_gui(voltage_mV, turbidity)
                    except ValueError as e:
                        # Bỏ qua các dòng không phân tích được (như các dòng setup của Arduino)
                        
                        # === SỬA LỖI: ĐÃ TẮT THÔNG BÁO DEBUG ===
                        # print(f"Lỗi phân tích dữ liệu (bỏ qua): {e} -- line: {line}")
                        pass
            except serial.SerialException as e:
                print(f"Lỗi đọc serial (Mất kết nối?): {e}")
                self.status_label.config(text="Mất kết nối cảm biến!")
                self.stop_monitoring()
                self.connect_button.config(state=tk.NORMAL) # Cho phép kết nối lại
                break # Thoát khỏi vòng lặp đọc
            except Exception as e:
                print(f"Lỗi không xác định khi đọc: {e}")
                time.sleep(1)

    def parse_serial_line(self, line: str):
        # Hàm này đã chuẩn, không cần thay đổi
        line = line.replace("Vôn", "VOLTAGE").replace("Độ đục", "TURBIDITY")
        
        # Chỉ tìm dòng có cả VOLTAGE và TURBIDITY
        if "VOLTAGE" not in line or "TURBIDITY" not in line:
            raise ValueError("Dòng không chứa dữ liệu hợp lệ")
            
        turb_match = re.search(r"TURBIDITY\s*[:=]\s*([-+]?\d*\.?\d+)", line, re.IGNORECASE)
        if not turb_match: raise ValueError("Không tìm thấy TURBIDITY")
        
        turbidity = float(turb_match.group(1))
        
        volt_match = re.search(r"VOLT(?:AGE)?\s*[:=]\s*([-+]?\d*\.?\d+)\s*(mV|v)?", line, re.IGNORECASE)
        if not volt_match: raise ValueError("Không tìm thấy VOLTAGE")
        
        volt_val = float(volt_match.group(1))
        volt_unit = volt_match.group(2)
        
        # Logic phát hiện đơn vị (mV hay V)
        voltage_mV = volt_val
        if volt_unit and volt_unit.lower() == 'v':
            voltage_mV = volt_val * 1000.0
        elif not volt_unit and abs(volt_val) < 100: # Giả định nếu số quá nhỏ (<100) thì đó là Volt
            voltage_mV = volt_val * 1000.0
        
        return float(voltage_mV), float(turbidity)

    def update_gui(self, voltage, turbidity):
        def _update():
            self.voltage_label.config(text=f"{(voltage / 1000.0):.3f} V")
            status, color = self.get_water_status(turbidity)
            self.water_status_label.config(text=status, fg=color)
            # Cập nhật màu chấm chỉ báo theo trạng thái
            try:
                self.status_indicator.itemconfig(self.status_indicator_circle, fill=color)
            except Exception:
                pass
            self.turbidity_gauge.set_value(turbidity)
            
            # Lưu mẫu cho phân tích xu hướng
            self.recent_samples.append((time.time(), turbidity))

            # Gửi Telegram mỗi khi trạng thái thay đổi (không giới hạn tần suất)
            if not hasattr(self, 'last_status_sent'):
                self.last_status_sent = None
            if status != self.last_status_sent:
                try:
                    self.send_notification(f"Trạng thái thay đổi: {status} — {turbidity:.2f} NTU", skip_cooldown=True)
                except Exception:
                    pass
                self.last_status_sent = status

            # Logic Cảnh báo Đa cấp
            new_alert_level = 0
            if turbidity > 100: new_alert_level = 3
            elif turbidity > 50: new_alert_level = 2
            elif turbidity > 10: new_alert_level = 1
            
            if new_alert_level > self.current_alert_level:
                # Tắt tất cả popup: không hiện thông báo ở mọi mức cảnh báo
                self.current_alert_level = new_alert_level
                # Gửi lệnh tới Arduino khi vượt mức rất đục
                if new_alert_level >= 3:
                    self.send_serial_command('A')
                    self.send_notification(f"Cảnh báo: Độ đục rất cao ({turbidity:.2f} NTU)")
            elif new_alert_level == 0 and self.current_alert_level > 0:
                self.current_alert_level = 0
                print("Trạng thái cảnh báo đã reset (nước trong trở lại).")
                # Có thể gửi lệnh tắt nếu muốn
                self.send_serial_command('S')

            # Cập nhật Biểu đồ
            self.turbidity_data.append(turbidity)
            self.timestamps.append(datetime.now().strftime("%H:%M:%S"))
            if len(self.turbidity_data) > 50:
                self.turbidity_data = self.turbidity_data[-50:]
                self.timestamps = self.timestamps[-50:]
            
            self.line.set_data(range(len(self.turbidity_data)), self.turbidity_data)
            
            if len(self.turbidity_data) > 1:
                tick_skip = max(1, len(self.turbidity_data) // 5)
                self.ax.set_xticks(range(0, len(self.turbidity_data), tick_skip))
                self.ax.set_xticklabels(self.timestamps[::tick_skip], rotation=30, ha='right')
            else:
                self.ax.set_xticks([])
                self.ax.set_xticklabels([])
                
            self.ax.relim()
            self.ax.autoscale_view(True, True)
            self.figure.tight_layout()
            self.canvas_graph.draw()

            # Ghi log mỗi lần cập nhật để đồng bộ thời gian thực với app mobile
            current_time = time.time()
            self.log_to_db(voltage, turbidity, status)
            self.last_turbidity = turbidity
            self.last_voltage = voltage
            self.last_log_time = current_time

            # Phát hiện xu hướng tăng nhanh
            try:
                if self.is_trend_rising():
                    self.send_notification(f"Cảnh báo xu hướng: Độ đục đang tăng nhanh (>{self.TREND_ALERT_SLOPE:.0f} NTU/phút)")
                    self.send_serial_command('A')
            except Exception:
                pass

        # Đảm bảo GUI cập nhật trên luồng chính
        if self.root.winfo_exists():
            self.root.after(0, _update)

    def periodic_log(self):
        if self.is_running and self.last_turbidity is not None:
            current_time = time.time()
            if (current_time - self.last_log_time) >= self.log_interval:
                # print(f"Logging (periodic) do đã qua 1 giờ: {self.last_turbidity:.2f} NTU") # Đã tắt debug
                status, _ = self.get_water_status(self.last_turbidity)
                self.log_to_db(self.last_voltage, self.last_turbidity, status)
                self.last_log_time = current_time

        if self.root.winfo_exists():
            self.root.after(10000, self.periodic_log) # Kiểm tra mỗi 10 giây

    # Đã gỡ bỏ chức năng gửi thử Telegram theo yêu cầu

    # ====== Cấu hình Telegram (.env) ======
    def load_env_settings(self):
        # Ưu tiên đọc từ .env; nếu không có thì dùng os.environ
        token, chat = None, None
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            k, v = line.split('=', 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k == 'TELEGRAM_BOT_TOKEN':
                                token = v
                            elif k == 'TELEGRAM_CHAT_ID':
                                chat = v
            except Exception as e:
                print(f"Lỗi đọc .env: {e}")
        # Fallback sang biến môi trường nếu .env không có
        token = token or os.environ.get('TELEGRAM_BOT_TOKEN')
        chat = chat or os.environ.get('TELEGRAM_CHAT_ID')
        self.telegram_token = token
        self.telegram_chat_id = chat
        # Đồng bộ lại vào os.environ cho phiên hiện tại
        if token:
            os.environ['TELEGRAM_BOT_TOKEN'] = token
        if chat:
            os.environ['TELEGRAM_CHAT_ID'] = chat

    # Đã gỡ bỏ chức năng lưu .env qua GUI theo yêu cầu

    # Đã gỡ bỏ cửa sổ cài đặt Telegram theo yêu cầu

    def get_water_status(self, turbidity):
        if turbidity < 1: return "Nước cất", "#22C55E"
        elif turbidity <= 10: return "Nước trong", "#38BDF8"
        elif turbidity <= 50: return "Nước hơi đục", "#EAB308"
        elif turbidity <= 100: return "Nước đục", "#F97316"
        else: return "Nước rất đục", "#EF4444"

    def init_db(self):
        try:
            conn = sqlite3.connect(self.DB_PATH)
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    voltage REAL,
                    turbidity REAL,
                    status TEXT,
                    source TEXT
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Lỗi khởi tạo DB: {e}")

    def log_to_db(self, voltage, turbidity, status):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = sqlite3.connect(self.DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO readings (ts, voltage, turbidity, status, source) VALUES (?, ?, ?, ?, ?)",
                (ts, round(voltage, 0), round(turbidity, 2), status, "Arduino Uno")
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Lỗi ghi DB: {e}")

    def is_trend_rising(self):
        # Compute slope over last TREND_WINDOW_SEC seconds
        if len(self.recent_samples) < 2:
            return False
        cutoff = time.time() - self.TREND_WINDOW_SEC
        window = [s for s in self.recent_samples if s[0] >= cutoff]
        if len(window) < 2:
            return False
        ntu_start = window[0][1]
        ntu_end = window[-1][1]
        dt_min = max(1e-6, (window[-1][0] - window[0][0]) / 60.0)
        slope = (ntu_end - ntu_start) / dt_min
        return slope >= self.TREND_ALERT_SLOPE

    def send_serial_command(self, cmd: str):
        # Avoid spamming; send at most once per 10s per type
        now = time.time()
        if self.serial_connection and self.serial_connection.is_open:
            if self.last_command_type != cmd or (now - self.last_command_sent_at) >= 10:
                try:
                    self.serial_connection.write(cmd.encode('utf-8'))
                    self.last_command_type = cmd
                    self.last_command_sent_at = now
                except Exception as e:
                    print(f"Lỗi gửi lệnh tới Arduino: {e}")

    def send_notification(self, message: str, skip_cooldown: bool = False):
        # Telegram via env vars TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        now = time.time()
        if not token or not chat_id:
            return
        if (not skip_cooldown) and (now - self.last_notify_at) < self.TELEGRAM_MIN_INTERVAL_SEC:
            return
        try:
            api_url = f"https://api.telegram.org/bot{token}/sendMessage"
            params = urlencode({
                "chat_id": chat_id,
                "text": message
            }).encode("utf-8")
            req = urllib.request.Request(api_url, data=params)
            # SSL context: dùng certifi nếu có; có thể bật bỏ qua verify qua env var (không khuyến nghị)
            insecure_skip = os.environ.get("TELEGRAM_INSECURE_SKIP_VERIFY") == "1"
            if insecure_skip:
                print("[Cảnh báo] Đang bỏ qua xác thực SSL (TELEGRAM_INSECURE_SKIP_VERIFY=1). Chỉ sử dụng tạm thời để kiểm tra.")
                context = ssl._create_unverified_context()
            else:
                context = ssl.create_default_context()
                if HAS_CERTIFI:
                    try:
                        context.load_verify_locations(certifi.where())
                    except Exception:
                        pass

            with urllib.request.urlopen(req, context=context, timeout=10) as resp:
                _ = resp.read()
            self.last_notify_at = now
        except Exception as e:
            err = str(e)
            print(f"Gửi Telegram thất bại: {e}")
            if "CERTIFICATE_VERIFY_FAILED" in err.upper():
                print("\nGợi ý khắc phục SSL:\n- Nếu đang ở mạng công ty/proxy, hãy cài chứng chỉ CA nội bộ vào Windows Trusted Root.\n- Hoặc cài certifi: pip install certifi (ứng dụng sẽ tự dùng certifi nếu có).\n- Hoặc đặt biến môi trường SSL_CERT_FILE hoặc REQUESTS_CA_BUNDLE trỏ tới file CA bundle.\n- Chỉ để test tạm thời: set TELEGRAM_INSECURE_SKIP_VERIFY=1 (không khuyến nghị dùng lâu dài).\n")

    def on_closing(self):
        print("Closing application...")
        self.stop_monitoring()
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            print("Serial connection closed.")
        self.root.destroy()

def main():
    root = tk.Tk()
    app = TurbiditySensorGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing) # Xử lý khi nhấn nút X
    root.mainloop()

if __name__ == "__main__":
    main()