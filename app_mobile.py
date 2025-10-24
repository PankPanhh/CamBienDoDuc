import streamlit as st
import json
import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
import plotly.graph_objects as go

# --- Config và Tiêu đề (Chỉ chạy 1 lần) ---
st.set_page_config(
    page_title="Dashboard Giám sát Nước",
    page_icon="🌊",
    layout="wide"
)

# === CSS CỰC KỲ ĐỠN GIẢN ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Inter', sans-serif;
    }
    
    .main {
        background: #0a0e1a;
        padding: 1rem;
    }
    
    /* Header đơn giản */
    .simple-header {
        background: #1e3a8a;
        padding: 2rem;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .simple-header h1 {
        color: white;
        font-size: 1.8rem;
        font-weight: 600;
        margin: 0;
    }
    
    .simple-header p {
        color: rgba(255,255,255,0.8);
        font-size: 0.9rem;
        margin-top: 0.5rem;
    }
    
    /* Card cơ bản */
    .simple-card {
        background: #1a1f35;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255,255,255,0.05);
    }
    
    /* Status đơn giản */
    .status-simple {
        text-align: center;
        padding: 2rem 1rem;
        border-radius: 12px;
        background: #1a1f35;
        border: 2px solid;
    }
    
    .status-simple.ok { border-color: #10b981; }
    .status-simple.warn { border-color: #f59e0b; }
    .status-simple.bad { border-color: #ef4444; }
    
    .status-icon { font-size: 3rem; }
    .status-title { font-size: 1.2rem; font-weight: 600; margin: 0.5rem 0; }
    .status-value { font-size: 2.5rem; font-weight: 700; margin-top: 0.5rem; }
    
    /* Metric đơn giản */
    .simple-metric {
        background: #1a1f35;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: rgba(255,255,255,0.6);
        margin-bottom: 0.5rem;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #3b82f6;
    }
    
    /* Hide Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
</style>
""", unsafe_allow_html=True)

# Header siêu đơn giản
st.markdown("""
<div class="simple-header">
    <h1>💧 Giám Sát Chất Lượng Nước</h1>
    <p>Hệ thống đo độ đục thời gian thực</p>
</div>
""", unsafe_allow_html=True)

# Cấu hình cập nhật thời gian thực (điều chỉnh chu kỳ theo thay đổi trạng thái)
FAST_REFRESH_MS = 1000     # làm mới nhanh khi vừa có thay đổi trạng thái
SLOW_REFRESH_MS = 10000    # làm mới chậm khi trạng thái ổn định
BOOST_DURATION_SEC = 30    # khoảng thời gian duy trì làm mới nhanh

# Settings row
col_set1, col_set2 = st.columns(2)

with col_set1:
    if 'realtime_enabled' not in st.session_state:
        st.session_state['realtime_enabled'] = True
    realtime = st.toggle(
        "⚡ Cập nhật thời gian thực",
        value=st.session_state['realtime_enabled'],
        help="Tự động tải dữ liệu mới. Khi trạng thái nước thay đổi, tốc độ cập nhật sẽ nhanh hơn trong thời gian ngắn."
    )
    st.session_state['realtime_enabled'] = realtime

with col_set2:
    if 'notify_enabled' not in st.session_state:
        st.session_state['notify_enabled'] = True
    notify_enabled = st.toggle(
        "🔔 Thông báo cảnh báo",
        value=st.session_state['notify_enabled'],
        help="Hiện thông báo nhẹ khi độ đục vượt các ngưỡng an toàn (10/50/100 NTU)"
    )
    st.session_state['notify_enabled'] = notify_enabled

st.markdown("---")

# === FRAGMENT: PHẦN TỰ ĐỘNG CẬP NHẬT (KHÔNG RELOAD TOÀN TRANG) ===
@st.fragment(run_every=None)  # Sẽ set động trong hàm
def realtime_data_display():
    """Fragment này tự động cập nhật mà không làm reload toàn trang"""
    
    now_ts = datetime.now().timestamp()
    
    try:
        db_path = Path(__file__).parent / "turbidity.db"
        if db_path.exists():
            # Đọc từ SQLite
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            rows = cur.execute("SELECT ts, turbidity, voltage, status FROM readings ORDER BY ts ASC").fetchall()
            conn.close()
            if not rows:
                raise json.JSONDecodeError("empty", "", 0)
            df = pd.DataFrame(rows, columns=["timestamp", "turbidity", "voltage", "status"])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        else:
            # Fallback: Đọc từ JSON nếu DB chưa sẵn sàng
            log_path = Path(__file__).parent / "turbidity_log.json"
            with open(log_path, "r", encoding='utf-8') as f:
                logs = json.load(f)
            if not logs:
                raise json.JSONDecodeError("empty", "", 0)
            df = pd.DataFrame(logs)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)

        # === Chuẩn bị dữ liệu mới nhất ===
        latest_data = df.iloc[-1]
        turbidity = float(latest_data.get('turbidity', 0.0))
        voltage = float(latest_data.get('voltage', 0.0))
        current_status = latest_data.get('status', '--')
        last_record_time = latest_data.name.strftime('%Y-%m-%d %H:%M:%S') if hasattr(latest_data, 'name') else "--"

        # Theo dõi thay đổi trạng thái để điều chỉnh chu kỳ làm mới
        if 'last_status' not in st.session_state:
            st.session_state['last_status'] = current_status
            st.session_state['boost_until'] = 0.0
        if current_status != st.session_state.get('last_status'):
            st.session_state['last_status'] = current_status
            st.session_state['boost_until'] = now_ts + BOOST_DURATION_SEC

        # === CẢNH BÁO ===
        if turbidity > 100:
            st.error(f'⛔ Nước rất đục: {turbidity:.2f} NTU')
        elif turbidity > 50:
            st.warning(f'⚠️ Nước đục: {turbidity:.2f} NTU')
        elif turbidity > 10:
            st.info(f'ℹ️ Hơi đục: {turbidity:.2f} NTU')

        # === LAYOUT 2 CỘT ===
        col1, col2 = st.columns(2)
        
        # Cột 1: Trạng thái
        with col1:
            if turbidity <= 10:
                css_class, icon, text, color = "ok", "✅", "Nước Trong", "#10b981"
            elif turbidity <= 50:
                css_class, icon, text, color = "warn", "⚠️", "Hơi Đục", "#f59e0b"
            else:
                css_class, icon, text, color = "bad", "⛔", "Nước Đục", "#ef4444"
            
            st.markdown(f"""
            <div class="status-simple {css_class}">
                <div class="status-icon">{icon}</div>
                <div class="status-title" style="color: {color};">{text}</div>
                <div class="status-value" style="color: {color};">{turbidity:.2f} <span style="font-size:1rem;">NTU</span></div>
            </div>
            """, unsafe_allow_html=True)
        
        # Cột 2: Metrics
        with col2:
            st.markdown(f"""
            <div class="simple-metric" style="margin-bottom: 1rem;">
                <div class="metric-label">⚡ Điện áp</div>
                <div class="metric-value">{voltage:.0f} <span style="font-size:1rem;">mV</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            time_str = last_record_time.split()[1] if ' ' in last_record_time else last_record_time
            st.markdown(f"""
            <div class="simple-metric">
                <div class="metric-label">🕐 Cập nhật</div>
                <div class="metric-value" style="font-size:1.5rem;">{time_str}</div>
            </div>
            """, unsafe_allow_html=True)

        # === ĐỒNG HỒ ===
        st.markdown("### 📊 Đồng Hồ Đo", unsafe_allow_html=True)
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=turbidity,
            number={'font': {'size': 40}},
            gauge={
                'axis': {'range': [0, 200]},
                'bar': {'color': "#3b82f6"},
                'steps': [
                    {'range': [0, 10], 'color': 'rgba(16,185,129,0.2)'},
                    {'range': [10, 50], 'color': 'rgba(245,158,11,0.2)'},
                    {'range': [50, 200], 'color': 'rgba(239,68,68,0.2)'}
                ],
                'threshold': {'line': {'color': "red", 'width': 3}, 'value': 100}
            }
        ))
        
        fig.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=20, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            font={'color': "white"}
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # === DỮ LIỆU & BIỂU ĐỒ - Tabs đơn giản ===
        st.markdown("### 📈 Lịch Sử")
        
        tab1, tab2 = st.tabs(['Biểu đồ', 'Dữ liệu'])
        
        with tab1:
            st.line_chart(df.tail(50)['turbidity'], height=300)
        
        with tab2:
            st.dataframe(
                df.tail(10).iloc[::-1],
                use_container_width=True,
                height=300
            )
        
        # Footer
        st.caption(f"🕐 {datetime.now().strftime('%H:%M:%S')} • 📝 {last_record_time}")

        # === Thông báo Toast chỉ khi thay đổi trạng thái (không phải liên tục) ===
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
        if st.session_state['notify_enabled']:
            if lvl > st.session_state['last_alert_level']:
                # Chỉ toast khi MỨC TĂNG (thay đổi trạng thái)
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
                except Exception:
                    pass
            # Cập nhật mức đã thông báo
            st.session_state['last_alert_level'] = lvl

    except FileNotFoundError:
        st.caption("Không tìm thấy nguồn dữ liệu (SQLite/JSON). Hãy đảm bảo chương trình desktop đang chạy và ghi log.")
    except json.JSONDecodeError:
        st.caption("Đang chờ dữ liệu... (File log trống hoặc đang được ghi).")
    except Exception as e:
        st.caption(f"Đã xảy ra lỗi: {e}")

# Gọi fragment với auto-refresh nếu realtime enabled
if realtime:
    # Tính interval động
    active_boost = datetime.now().timestamp() <= st.session_state.get('boost_until', 0.0)
    refresh_interval = FAST_REFRESH_MS / 1000.0 if active_boost else SLOW_REFRESH_MS / 1000.0
    
    # Fragment tự động rerun theo interval
    @st.fragment(run_every=refresh_interval)
    def auto_refresh_fragment():
        realtime_data_display()
    
    auto_refresh_fragment()
else:
    # Nếu tắt realtime, chỉ hiển thị 1 lần
    realtime_data_display()

# === BỘ LỌC LỊCH SỬ (PHẦN TĨNH - Chỉ reload khi tương tác) ===
# Hàm Callbacks
def date_filter_changed():
    st.session_state.date_range = st.session_state.date_filter_widget_key

def status_filter_changed():
    st.session_state.selected_statuses = st.session_state.status_filter_widget_key

# Đọc dữ liệu cho bộ lọc
try:
    db_path = Path(__file__).parent / "turbidity.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        rows = cur.execute("SELECT ts, turbidity, voltage, status FROM readings ORDER BY ts ASC").fetchall()
        conn.close()
        if rows:
            df_filter = pd.DataFrame(rows, columns=["timestamp", "turbidity", "voltage", "status"])
            df_filter['timestamp'] = pd.to_datetime(df_filter['timestamp'])
            df_filter.set_index('timestamp', inplace=True)
            
            with st.expander("🗂️ Tra cứu Lịch sử Đo đầy đủ"):
                st.subheader("Bộ lọc Dữ liệu")

                min_date = df_filter.index.min().date()
                max_date = df_filter.index.max().date()
                all_statuses = df_filter['status'].unique().tolist()

                # Khởi tạo Session State nếu chưa có
                if 'date_range' not in st.session_state:
                    st.session_state.date_range = (min_date, max_date)

                if 'selected_statuses' not in st.session_state:
                    st.session_state.selected_statuses = all_statuses

                # Widget với callback
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

                # Logic lọc
                filtered_df = df_filter.copy()

                if st.session_state.date_range and len(st.session_state.date_range) == 2:
                    start_date = pd.to_datetime(st.session_state.date_range[0])
                    end_date = pd.to_datetime(st.session_state.date_range[1]).replace(hour=23, minute=59, second=59)
                    filtered_df = filtered_df.loc[start_date:end_date]

                if st.session_state.selected_statuses:
                    filtered_df = filtered_df[filtered_df['status'].isin(st.session_state.selected_statuses)]

                st.subheader(f"Kết quả lọc ({len(filtered_df)} bản ghi)")
                st.dataframe(filtered_df.iloc[::-1], use_container_width=True)
except Exception:
    pass