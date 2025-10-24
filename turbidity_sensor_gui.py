import tkinter as tk
# Import ttkbootstrap as b
import ttkbootstrap as b
import serial
import time
import os
import threading
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
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

# Lớp Cửa sổ Lịch sử (Đã nâng cấp lên ttkbootstrap)
class HistoryWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Lịch sử Đo Độ đục")
        self.geometry("600x400")

        # Sử dụng b.Frame
        frame = b.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        columns = ("timestamp", "voltage", "turbidity", "status")
        # Sử dụng b.Treeview
        self.tree = b.Treeview(frame, columns=columns, show="headings", bootstyle='primary')
        self.tree.heading("timestamp", text="Thời gian")
        self.tree.heading("voltage", text="Điện áp (mV)")
        self.tree.heading("turbidity", text="Độ đục (NTU)")
        self.tree.heading("status", text="Trạng thái")
        self.tree.column("timestamp", width=150, anchor=tk.W)
        self.tree.column("voltage", width=100, anchor=tk.CENTER)
        self.tree.column("turbidity", width=100, anchor=tk.CENTER)
        self.tree.column("status", width=120, anchor=tk.W)

        # Sử dụng b.Scrollbar
        scrollbar = b.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # Xóa tag_configure, thay bằng bootstyle tags trong load_data
        
        button_frame = b.Frame(self, padding=(0, 10))
        button_frame.pack(fill="x")
        
        # Sử dụng b.Button
        b.Button(button_frame, text="Làm mới", command=self.load_data, bootstyle='primary').pack(side="left", padx=10)
        b.Button(button_frame, text="Đóng", command=self.destroy, bootstyle='secondary').pack(side="right", padx=10)
        
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
                
                # Sử dụng bootstyle tags cho Treeview
                status_tag = "default"
                if "cất" in status_key: status_tag = 'success'
                elif "trong" in status_key: status_tag = 'info'
                elif "hơi_đục" in status_key: status_tag = 'warning'
                elif "đục" in status_key and "rất" not in status_key: status_tag = 'danger'
                elif "rất_đục" in status_key or "rất" in status_key: status_tag = 'danger'
                
                self.tree.insert("", tk.END, values=(ts, round(voltage), round(turbidity, 2), status), tags=(status_tag,))
        except Exception as e:
            self.tree.insert("", tk.END, values=(f"Lỗi tải lịch sử: {e}", "", "", ""))


# Đã XÓA lớp GaugeWidget tùy chỉnh theo yêu cầu

# Giao diện chính
class TurbiditySensorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard Giám sát Độ đục Nước")
        self.root.geometry("850x700")
        self.root.resizable(True, True)

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
        self.TREND_LINE_WINDOW_SEC = 300  # cửa sổ hiển thị đường xu hướng trên biểu đồ
        self.TREND_ROLLING_WINDOW_SEC = 60  # cửa sổ lăn cho đường xu hướng (tạo gấp khúc)
        # Cảnh báo tốc độ thay đổi ngắn hạn (1-2 phút)
        self.RATE_WINDOW_SEC = 60             # cửa sổ 1 phút (có thể tăng 120s nếu cần)
        self.RATE_ALERT_SLOPE = 20.0          # NTU/phút
        self.RATE_MIN_DELTA = 10.0            # thay đổi tối thiểu trong cửa sổ
        self.RATE_MIN_POINTS = 3              # tối thiểu số điểm trong cửa sổ
        self.RATE_ALERT_COOLDOWN_SEC = 60     # tránh spam cảnh báo ngắn hạn
        self.last_rate_alert_at = 0.0

        # Xóa create_styles()
        self.create_widgets()
        # Đường dẫn file .env để lưu cài đặt Telegram (không commit)
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        self.telegram_token = None
        self.telegram_chat_id = None
        self.load_env_settings()

        self.connect_to_arduino()
        self.init_db()
        self.periodic_log()

    # Đã XÓA hàm create_styles(self)

    def create_widgets(self):
        # Sử dụng b.Frame
        main_frame = b.Frame(self.root, padding=20)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        
        # Sử dụng b.Label
        header_label = b.Label(main_frame, text="Dashboard Giám sát Độ đục Nước", font=("Arial", 28, "bold"))
        header_label.grid(row=0, column=0, pady=(0, 10))
        
        status_controls_frame = b.Frame(main_frame)
        status_controls_frame.grid(row=1, column=0, sticky="ew", pady=10)
        status_controls_frame.columnconfigure(0, weight=1)
        status_controls_frame.columnconfigure(1, weight=0)
        
        # Sử dụng b.Label
        self.status_label = b.Label(status_controls_frame, text="Đang kết nối tới Arduino...", font=("Arial", 11))
        self.status_label.grid(row=0, column=0, sticky="w", padx=10)
        
        button_frame = b.Frame(status_controls_frame)
        button_frame.grid(row=0, column=1, sticky="e")
        
        # Sử dụng b.Button với bootstyle='primary'
        self.start_button = b.Button(button_frame, text="Bắt đầu", command=self.start_monitoring, bootstyle='primary')
        self.start_button.pack(side="left", padx=5)
        self.stop_button = b.Button(button_frame, text="Dừng lại", command=self.stop_monitoring, state=tk.DISABLED, bootstyle='primary')
        self.stop_button.pack(side="left", padx=5)
        self.connect_button = b.Button(button_frame, text="Kết nối lại", command=self.connect_to_arduino, bootstyle='primary')
        self.connect_button.pack(side="left", padx=5)
        self.history_button = b.Button(button_frame, text="Lịch sử đo", command=self.open_history_window, bootstyle='primary')
        self.history_button.pack(side="left", padx=5)

        gauge_frame = b.Frame(main_frame)
        gauge_frame.grid(row=2, column=0, pady=20)
        
        # Ttkbootstrap Meter widget thay thế GaugeWidget tùy chỉnh
        self.turbidity_gauge = b.Meter(
            gauge_frame,
            metersize=250,
            amounttotal=1000,
            amountused=0,
            subtext="NTU",
            bootstyle='info',
            interactive=False,
            stripethickness=10
        )
        self.turbidity_gauge.pack()

        cards_frame = b.Frame(main_frame)
        cards_frame.grid(row=3, column=0, sticky="ew", pady=10)
        cards_frame.columnconfigure([0, 1], weight=1)

        # Card Trạng thái Nước với bố cục cải tiến
        status_card = b.Frame(cards_frame, bootstyle='secondary', padding=20)
        status_card.grid(row=0, column=0, sticky="nsew", padx=10)
        
        b.Label(status_card, text="🌊 Trạng thái Nước", font=("Arial", 16, "bold")).pack(pady=(0, 10))
        
        # Hàng hiển thị trạng thái
        status_row = b.Frame(status_card, bootstyle='secondary')
        status_row.pack(pady=10)
        
        # Chỉ báo màu với nền khớp theme darkly
        self.status_indicator = tk.Canvas(status_row, width=18, height=18, bg="#2b3e50", highlightthickness=0)
        self.status_indicator_circle = self.status_indicator.create_oval(3, 3, 15, 15, fill="#6B7280", outline="#2b3e50")
        self.status_indicator.pack(side="left", padx=(0, 8))
        
        # Nhãn trạng thái với font lớn
        self.water_status_label = b.Label(status_row, text="--", font=("Arial", 24, "bold"))
        self.water_status_label.pack(side="left")

        # Card Điện áp với bố cục cải tiến
        volt_card = b.Frame(cards_frame, bootstyle='secondary', padding=20)
        volt_card.grid(row=0, column=1, sticky="nsew", padx=10)
        
        b.Label(volt_card, text="⚡ Điện áp Cảm biến", font=("Arial", 16, "bold")).pack(pady=(0, 10))
        
        # Nhãn điện áp với font lớn
        self.voltage_label = b.Label(volt_card, text="-- V", font=("Arial", 24, "bold"))
        self.voltage_label.pack(pady=10)
        
        # Card Biểu đồ
        self.graph_frame = b.Frame(main_frame, bootstyle='secondary', padding=20)
        self.graph_frame.grid(row=4, column=0, pady=20, padx=10, sticky="nsew")
        main_frame.rowconfigure(4, weight=1)

        # Cấu hình biểu đồ với màu sắc phù hợp cho theme darkly
        self.figure = Figure(figsize=(6, 4), dpi=100, facecolor="#2b3e50")
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Lịch sử Độ đục (50 điểm gần nhất)", color="#ffffff")
        self.ax.set_xlabel("Thời gian", color="#ffffff")
        self.ax.set_ylabel("NTU", color="#ffffff")
        self.ax.tick_params(axis='x', colors="#ffffff")
        self.ax.tick_params(axis='y', colors="#ffffff")
        self.ax.grid(True, linestyle='--', alpha=0.3, color="#52667a")
        self.ax.set_facecolor("#1e2d3d")
        for spine in self.ax.spines.values(): 
            spine.set_edgecolor("#52667a")
        
        # Lưu màu primary và warning từ theme để dùng cho biểu đồ
        self.line, = self.ax.plot([], [], color='#3b8fd6', marker='o', markersize=3, linewidth=2)
        self.trend_line, = self.ax.plot([], [], color='#f39c12', linestyle='--', linewidth=2, alpha=0.9)
        
        self.figure.tight_layout()
        self.canvas_graph = FigureCanvasTkAgg(self.figure, master=self.graph_frame)
        self.canvas_graph.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        # =======================================

    def open_history_window(self):
        if self.history_win is None or not self.history_win.winfo_exists():
            # Xóa tham số 'colors'
            self.history_win = HistoryWindow(self.root)
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
                    # Xóa bộ đệm input với API mới; fallback tương thích nếu cần
                    try:
                        reset_fn = getattr(self.serial_connection, "reset_input_buffer", None)
                        if callable(reset_fn):
                            reset_fn()
                        else:
                            flush_fn = getattr(self.serial_connection, "flushInput", None)
                            if callable(flush_fn):
                                flush_fn()
                    except Exception:
                        pass
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
            
            # Lấy trạng thái và bootstyle tương ứng
            status, status_bootstyle = self.get_water_status_bootstyle(turbidity)
            
            # Cập nhật nhãn trạng thái với màu tương ứng
            self.water_status_label.config(text=status, bootstyle=status_bootstyle)
            
            # Lấy màu hex từ bootstyle để cập nhật chỉ báo canvas
            color_map = {
                'success': '#00bc8c',
                'info': '#3498db',
                'warning': '#f39c12',
                'danger': '#e74c3c'
            }
            indicator_color = color_map.get(status_bootstyle, '#6B7280')
            
            # Cập nhật màu chấm chỉ báo
            self.status_indicator.itemconfig(self.status_indicator_circle, fill=indicator_color)
            
            # Cập nhật Meter với giá trị và màu tương ứng
            self.turbidity_gauge.configure(amountused=turbidity, bootstyle=status_bootstyle)
            
            # Lưu mẫu cho phân tích xu hướng
            self.recent_samples.append((time.time(), turbidity))

            # Cảnh báo tốc độ thay đổi ngắn hạn (1 phút): dự báo vấn đề trước khi vượt ngưỡng cao
            try:
                now_ts = time.time()
                cutoff_short = now_ts - self.RATE_WINDOW_SEC
                short_window = [s for s in self.recent_samples if s[0] >= cutoff_short]
                if len(short_window) >= max(2, self.RATE_MIN_POINTS):
                    t0s = short_window[0][0]
                    ts2 = [(w[0] - t0s) / 60.0 for w in short_window]  # phút
                    ys2 = [w[1] for w in short_window]
                    mean_t2 = sum(ts2) / len(ts2)
                    mean_y2 = sum(ys2) / len(ys2)
                    denom2 = sum((t - mean_t2) ** 2 for t in ts2) or 1e-9
                    slope2 = sum((t - mean_t2) * (y - mean_y2) for t, y in zip(ts2, ys2)) / denom2
                    delta2 = ys2[-1] - ys2[0]
                    dur2 = max(1e-6, ts2[-1] - ts2[0])
                    if slope2 >= self.RATE_ALERT_SLOPE and delta2 >= self.RATE_MIN_DELTA:
                        if (now_ts - self.last_rate_alert_at) >= self.RATE_ALERT_COOLDOWN_SEC:
                            self.last_rate_alert_at = now_ts
                            try:
                                self.send_notification(
                                    f"📈 Trend Warning: Water is getting cloudy fast! ~{slope2:.0f} NTU/min (Δ{delta2:.1f} NTU/{dur2:.1f} min)",
                                    skip_cooldown=True,
                                )
                            except Exception:
                                pass
            except Exception:
                pass

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

            # Vẽ overlay Xu hướng (gấp khúc) với hồi quy tuyến tính lăn (rolling)
            try:
                cutoff = time.time() - self.TREND_LINE_WINDOW_SEC
                window = [s for s in self.recent_samples if s[0] >= cutoff]
                if len(window) >= 2:
                    t0 = window[0][0]
                    ts = [(w[0] - t0) / 60.0 for w in window]  # phút
                    ys = [w[1] for w in window]
                    roll_min = max(0.1, self.TREND_ROLLING_WINDOW_SEC / 60.0)  # phút
                    y_fit_series = []
                    for i in range(len(ts)):
                        # Chọn đoạn con trong (ts[i] - roll_min, ts[i])
                        left_t = ts[i] - roll_min
                        sub_t = [t for t in ts[: i + 1] if t >= left_t]
                        sub_y = ys[len(ts[: i + 1]) - len(sub_t) : i + 1]
                        if len(sub_t) >= 2:
                            mt = sum(sub_t) / len(sub_t)
                            my = sum(sub_y) / len(sub_y)
                            den = sum((t - mt) ** 2 for t in sub_t) or 1e-9
                            sl = sum((t - mt) * (y - my) for t, y in zip(sub_t, sub_y)) / den
                            itc = my - sl * mt
                            y_fit_series.append(sl * ts[i] + itc)
                        else:
                            # Fallback: dùng giá trị thực hoặc bản sao giá trị trước đó để nối mượt
                            y_fit_series.append(y_fit_series[-1] if y_fit_series else ys[i])

                    tail_n = min(len(window), len(self.turbidity_data))
                    x_start = max(0, len(self.turbidity_data) - tail_n)
                    x_idx = list(range(x_start, len(self.turbidity_data)))
                    self.trend_line.set_data(x_idx, y_fit_series[-tail_n:])
                else:
                    self.trend_line.set_data([], [])
            except Exception:
                self.trend_line.set_data([], [])
            
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
                status, _ = self.get_water_status_bootstyle(self.last_turbidity)
                self.log_to_db(self.last_voltage, self.last_turbidity, status)
                self.last_log_time = current_time

        if self.root.winfo_exists():
            self.root.after(10000, self.periodic_log) # Kiểm tra mỗi 10 giây

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

    # Hàm tiện ích mới: trả về (status_text, bootstyle_name)
    def get_water_status_bootstyle(self, turbidity):
        if turbidity < 1: return "Nước cất", "success"
        elif turbidity <= 10: return "Nước trong", "info"
        elif turbidity <= 50: return "Nước hơi đục", "warning"
        elif turbidity <= 100: return "Nước đục", "danger"
        else: return "Nước rất đục", "danger"

    # Hàm get_water_status cũ (không còn dùng)
    # def get_water_status(self, turbidity): ...
        
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
    # Sử dụng b.Window với themename='darkly'
    root = b.Window(themename='darkly')
    app = TurbiditySensorGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing) # Xử lý khi nhấn nút X
    root.mainloop()

if __name__ == "__main__":
    main()