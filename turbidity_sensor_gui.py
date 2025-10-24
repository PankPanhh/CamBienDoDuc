import tkinter as tk
from tkinter import ttk
import serial
import json
import time
import os
import threading
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import math
import re

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
            with open("turbidity_log.json", "r", encoding='utf-8') as f:
                logs = json.load(f)
            for record in reversed(logs):
                status_key = record.get("status", "").replace(" ", "_").lower()
                status_tag = ""
                if "cất" in status_key: status_tag = 'distilled'
                elif "trong" in status_key: status_tag = 'clear'
                elif "hơi_đục" in status_key: status_tag = 'slight'
                elif "đục" in status_key: status_tag = 'cloudy'
                elif "rất_đục" in status_key: status_tag = 'very_cloudy'
                self.tree.insert("", tk.END, values=(
                    record.get("timestamp", ""),
                    record.get("voltage", ""),
                    record.get("turbidity", ""),
                    record.get("status", "")
                ), tags=(status_tag,))
        except FileNotFoundError:
            self.tree.insert("", tk.END, values=("Không tìm thấy file log", "", "", ""))
        except json.JSONDecodeError:
            self.tree.insert("", tk.END, values=("File log bị lỗi hoặc trống", "", "", ""))


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

        self.create_styles()
        self.create_widgets()
        self.connect_to_arduino()
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
            
            # Logic Cảnh báo Đa cấp
            new_alert_level = 0
            if turbidity > 100: new_alert_level = 3
            elif turbidity > 50: new_alert_level = 2
            elif turbidity > 10: new_alert_level = 1
            
            if new_alert_level > self.current_alert_level:
                # Tắt tất cả popup: không hiện thông báo ở mọi mức cảnh báo
                self.current_alert_level = new_alert_level
            elif new_alert_level == 0 and self.current_alert_level > 0:
                self.current_alert_level = 0
                print("Trạng thái cảnh báo đã reset (nước trong trở lại).")

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
            self.log_to_json(voltage, turbidity, status)
            self.last_turbidity = turbidity
            self.last_voltage = voltage
            self.last_log_time = current_time

        # Đảm bảo GUI cập nhật trên luồng chính
        if self.root.winfo_exists():
            self.root.after(0, _update)

    def periodic_log(self):
        if self.is_running and self.last_turbidity is not None:
            current_time = time.time()
            if (current_time - self.last_log_time) >= self.log_interval:
                # print(f"Logging (periodic) do đã qua 1 giờ: {self.last_turbidity:.2f} NTU") # Đã tắt debug
                status, _ = self.get_water_status(self.last_turbidity)
                self.log_to_json(self.last_voltage, self.last_turbidity, status)
                self.last_log_time = current_time

        if self.root.winfo_exists():
            self.root.after(10000, self.periodic_log) # Kiểm tra mỗi 10 giây

    def get_water_status(self, turbidity):
        if turbidity < 1: return "Nước cất", "#22C55E"
        elif turbidity <= 10: return "Nước trong", "#38BDF8"
        elif turbidity <= 50: return "Nước hơi đục", "#EAB308"
        elif turbidity <= 100: return "Nước đục", "#F97316"
        else: return "Nước rất đục", "#EF4444"

    def log_to_json(self, voltage, turbidity, status):
        # Ghi atomically vào file log nằm cùng thư mục script, tránh lỗi đọc giữa chừng
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = {"timestamp": timestamp, "voltage": round(voltage, 0), "turbidity": round(turbidity, 2), "status": status, "source": "Arduino Uno"}
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "turbidity_log.json")
        tmp_path = file_path + ".tmp"
        try:
            logs = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding='utf-8') as f:
                        logs = json.load(f)
                except json.JSONDecodeError:
                    # Nếu file đang được ghi dở, bỏ qua và tạo log mới
                    logs = []
            logs.append(data)
            # Ghi ra file tạm và thay thế atomically
            with open(tmp_path, "w", encoding='utf-8') as f:
                json.dump(logs[-1000:], f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except Exception as e:
            print(f"Lỗi ghi JSON: {e}") # Giữ lại thông báo lỗi này

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