import streamlit as st
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import time

# --- Config và Tiêu đề (Chỉ chạy 1 lần) ---
st.set_page_config(
    page_title="Dashboard Giám sát Nước",
    page_icon="🌊",
    layout="wide"
)
st.title("🌊 Dashboard Giám sát Chất lượng Nước")

# Cấu hình cập nhật thời gian thực (điều chỉnh chu kỳ theo thay đổi trạng thái)
FAST_REFRESH_MS = 2000     # làm mới nhanh khi vừa có thay đổi trạng thái
SLOW_REFRESH_MS = 10000    # làm mới chậm khi trạng thái ổn định
BOOST_DURATION_SEC = 30    # khoảng thời gian duy trì làm mới nhanh
if 'realtime_enabled' not in st.session_state:
    st.session_state['realtime_enabled'] = True
realtime = st.toggle(
    "Cập nhật thời gian thực",
    value=st.session_state['realtime_enabled'],
    help="Tự động tải dữ liệu mới. Khi trạng thái nước thay đổi, tốc độ cập nhật sẽ nhanh hơn trong thời gian ngắn."
)
st.session_state['realtime_enabled'] = realtime
computed_refresh_ms = SLOW_REFRESH_MS  # mặc định

# Tùy chọn thông báo khi vượt ngưỡng
if 'notify_enabled' not in st.session_state:
    st.session_state['notify_enabled'] = True
notify_enabled = st.toggle(
    "Thông báo khi vượt ngưỡng",
    value=st.session_state['notify_enabled'],
    help="Hiện thông báo nhẹ khi độ đục vượt các ngưỡng an toàn (10/50/100 NTU)"
)
st.session_state['notify_enabled'] = notify_enabled

# --- Placeholders (Định nghĩa 1 lần) ---
last_update_placeholder = st.caption(f"Đang tải...")
data_source_placeholder = st.caption("")
alert_placeholder = st.empty()
kpi_placeholder = st.empty()
gauge_placeholder = st.empty()
charts_placeholder = st.empty()
history_expander_placeholder = st.empty()

# --- Hàm hỗ trợ (Định nghĩa 1 lần) ---
# Không cần emoji trạng thái nữa

# === Hàm Callbacks (Không thay đổi) ===
def date_filter_changed():
    st.session_state.date_range = st.session_state.date_filter_widget_key

def status_filter_changed():
    st.session_state.selected_statuses = st.session_state.status_filter_widget_key
# ==========================================================

# --- Logic chính (Chỉ chạy khi có tương tác hoặc nhấn nút "Làm mới") ---
try:
    log_path = Path(__file__).parent / "turbidity_log.json"
    with open(log_path, "r", encoding='utf-8') as f:
        logs = json.load(f)

    if logs:
        # === Chuẩn bị Dữ liệu ===
        df = pd.DataFrame(logs)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        latest_data = df.iloc[-1]
        turbidity = latest_data.get('turbidity', 0.0)
        voltage = latest_data.get('voltage', 0.0)
        current_status = latest_data.get('status', '--')
        last_record_time = latest_data.name.strftime('%Y-%m-%d %H:%M:%S') if hasattr(latest_data, 'name') else "--"

        # Theo dõi thay đổi trạng thái để điều chỉnh chu kỳ làm mới
        now_ts = datetime.now().timestamp()
        if 'last_status' not in st.session_state:
            st.session_state['last_status'] = current_status
            st.session_state['boost_until'] = 0.0
        if current_status != st.session_state.get('last_status'):
            st.session_state['last_status'] = current_status
            st.session_state['boost_until'] = now_ts + BOOST_DURATION_SEC
        
        # === BỎ CẢNH BÁO/THÔNG BÁO: Không hiển thị banner cảnh báo ===
        with alert_placeholder.container():
            st.empty()

        # === KPI (Các chỉ số chính - bỏ trạng thái/emoji) ===
        with kpi_placeholder.container():
            col1, col2 = st.columns(2)
            col1.metric(label="Độ đục (NTU)", value=f"{turbidity:.2f}")
            col2.metric(label="Điện áp Cảm biến (mV)", value=f"{voltage:.0f}")
        
        # === ĐỒNG HỒ GAUGE (Thanh tiến trình) ===
        with gauge_placeholder.container():
            progress_value = min(turbidity / 1000.0, 1.0)
            st.progress(progress_value, text=f"Thang đo: {turbidity:.0f} / 1000 NTU")

        # === BIỂU ĐỒ VÀ BẢNG DỮ LIỆU GẦN NHẤT ===
        with charts_placeholder.container():
            col_chart, col_table = st.columns([2, 1])
            with col_chart:
                st.subheader("Lịch sử Độ đục (50 điểm cuối)")
                st.line_chart(df.tail(50)['turbidity'])
            
            with col_table:
                st.subheader("5 Bản ghi Mới nhất")
                st.dataframe(df.tail(5).iloc[::-1], use_container_width=True)

        # === BỘ LỌC LỊCH SỬ (Sử dụng Session State và on_change) ===
        with history_expander_placeholder.container():
            with st.expander("🗂️ Tra cứu Lịch sử Đo đầy đủ"):
                st.subheader("Bộ lọc Dữ liệu")
                
                min_date = df.index.min().date()
                max_date = df.index.max().date()
                all_statuses = df['status'].unique().tolist()

                # --- Khởi tạo Session State nếu chưa có ---
                if 'date_range' not in st.session_state:
                    st.session_state.date_range = (min_date, max_date)
                
                if 'selected_statuses' not in st.session_state:
                    st.session_state.selected_statuses = all_statuses
                
                # --- Gán on_change và key cho widget ---
                st.date_input(
                    "Lọc theo ngày:",
                    value=st.session_state.date_range,
                    min_value=min_date,
                    max_value=max_date,
                    format="DD/MM/YYYY",
                    key="date_filter_widget_key",
                    on_change=date_filter_changed
                )
                
                st.multiselect(
                    "Lọc theo trạng thái:",
                    options=all_statuses,
                    default=st.session_state.selected_statuses,
                    key="status_filter_widget_key",
                    on_change=status_filter_changed
                )
                
                # --- Logic lọc (luôn đọc từ session_state) ---
                filtered_df = df.copy()
                
                if st.session_state.date_range and len(st.session_state.date_range) == 2:
                    start_date = pd.to_datetime(st.session_state.date_range[0])
                    end_date = pd.to_datetime(st.session_state.date_range[1]).replace(hour=23, minute=59, second=59)
                    filtered_df = filtered_df.loc[start_date:end_date]
                
                if st.session_state.selected_statuses:
                    filtered_df = filtered_df[filtered_df['status'].isin(st.session_state.selected_statuses)]
                
                st.subheader(f"Kết quả lọc ({len(filtered_df)} bản ghi)")
                st.dataframe(filtered_df.iloc[::-1], use_container_width=True)
        
                
        last_update_placeholder.caption(
            f"Cập nhật lần cuối (server): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  •  Bản ghi mới nhất (log): {last_record_time}"
        )
        data_source_placeholder.caption(f"Nguồn dữ liệu: {log_path}")
        active_boost = datetime.now().timestamp() <= st.session_state.get('boost_until', 0.0)
        computed_refresh_ms = FAST_REFRESH_MS if active_boost else SLOW_REFRESH_MS

        # Thông báo nhẹ khi vượt ngưỡng (chỉ khi tăng mức)
        if turbidity > 100:
            lvl = 3
        elif turbidity > 50:
            lvl = 2
        elif turbidity > 10:
            lvl = 1
        else:
            lvl = 0
        if 'last_alert_level' not in st.session_state:
            st.session_state['last_alert_level'] = 0
        if notify_enabled:
            if lvl > st.session_state['last_alert_level']:
                # Soạn thông điệp theo mức
                if lvl == 1:
                    msg, icon = f"Nước hơi đục (>10 NTU) — {turbidity:.2f} NTU", "⚠️"
                elif lvl == 2:
                    msg, icon = f"Nước đục (>50 NTU) — {turbidity:.2f} NTU", "🚨"
                elif lvl == 3:
                    msg, icon = f"Nước rất đục (>100 NTU) — {turbidity:.2f} NTU", "⛔"
                else:
                    msg, icon = f"Đã thay đổi mức độ an toàn — {turbidity:.2f} NTU", "ℹ️"
                try:
                    if hasattr(st, 'toast'):
                        st.toast(f"{icon} {msg}")
                    else:
                        # Fallback không gây gián đoạn
                        st.caption(f"{icon} {msg}")
                except Exception:
                    st.caption(f"{icon} {msg}")
            # Cập nhật mức đã thông báo
            st.session_state['last_alert_level'] = lvl

except FileNotFoundError:
    st.caption("Không tìm thấy file turbidity_log.json. Hãy đảm bảo chương trình desktop đang chạy và ghi log.")
except json.JSONDecodeError:
    st.caption("Đang chờ dữ liệu... (File log trống hoặc đang được ghi).")
except Exception as e:
    st.caption(f"Đã xảy ra lỗi: {e}")
    # Xóa state cũ nếu có lỗi
    if 'date_range' in st.session_state:
        del st.session_state['date_range']
    if 'selected_statuses' in st.session_state:
        del st.session_state['selected_statuses']

# Tự làm mới bằng cách rerun phía server (không reload trang)
if realtime:
    time.sleep(max(0.5, int(computed_refresh_ms) / 1000.0))
    # Giữ vị trí cuộn bằng cách không reload trang; Streamlit sẽ cập nhật nội dung khi rerun
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()

# Ghi chú: Trang sẽ tự động cập nhật theo chu kỳ động; có thể tắt bằng toggle ở đầu trang.