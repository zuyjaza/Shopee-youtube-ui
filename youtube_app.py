import streamlit as st
import requests
import time
import streamlit.components.v1 as components

import json
import os

# --- Cấu hình API Server ---
API_URL = "http://127.0.0.1:8002"
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def main():
    # --- Page Configuration ---
    st.set_page_config(page_title="Mã YouTube Shopee", page_icon="▶️", layout="centered")

    # Load initial config
    if "config_loaded" not in st.session_state:
        config = load_config()
        st.session_state["zalo_link"] = config.get("zalo_link", "https://zalo.me/g/svkgoi169")
        st.session_state["fixed_link"] = config.get("fixed_link", "https://www.youtube.com/@antigrav")
        st.session_state["api_url"] = config.get("api_url", "http://127.0.0.1:8002")
        st.session_state["config_loaded"] = True

    # Global API_URL
    api_url_global = st.session_state["api_url"]

    # --- Sidebar: Cấu hình ---
    with st.sidebar:
        st.header("⚙️ Cấu hình")
        zalo_link = st.text_input(
            "Link nhóm Zalo",
            value=st.session_state["zalo_link"],
            placeholder="https://zalo.me/g/..."
        )
        
        fixed_link = st.text_input(
            "Link YouTube cố định",
            value=st.session_state["fixed_link"],
            placeholder="https://www.youtube.com/..."
        )

        api_url_input = st.text_input(
            "API URL (Mặc định: 127.0.0.1:8002)",
            value=st.session_state["api_url"],
            placeholder="http://..."
        )
        
        if st.button("💾 LƯU CẤU HÌNH"):
            st.session_state["zalo_link"] = zalo_link
            st.session_state["fixed_link"] = fixed_link
            st.session_state["api_url"] = api_url_input
            save_config({
                "zalo_link": zalo_link,
                "fixed_link": fixed_link,
                "api_url": api_url_input
            })
            st.success("Đã lưu cấu hình!")
            time.sleep(1)
            st.rerun()

        st.caption("Mã sau khi gán xong sẽ trả về link này.")

    # --- Custom CSS ---
    st.markdown("""
    <style>
        .stApp {
            background-color: #f0f2f5;
        }
        /* Xoá hoàn toàn khoảng trắng trên cùng */
        .block-container {
            padding-top: 0 !important;
            margin-top: 0 !important;
        }
        header[data-testid="stHeader"] {
            display: none !important;
        }
        }
        /* Phông chữ và tiêu đề - SIÊU KHỔNG LỒ & BẮT BUỘC */
        .header-title {
            color: #212121 !important;
            text-align: center !important;
            font-weight: 900 !important;
            font-size: 8vw !important; /* To theo chiều ngang màn hình */
            margin-top: 10px !important;
            margin-bottom: 30px !important;
            display: flex !important;
            flex-direction: row !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 15px !important;
            line-height: 1.1 !important;
            width: 100% !important;
            white-space: nowrap !important;
        }
        @media (max-width: 768px) {
            .header-title {
                font-size: 10vw !important; /* To hơn nữa trên điện thoại */
                gap: 10px !important;
            }
        }
        .header-title span {
            display: inline-block !important;
        }
        /* Ô nhập liệu với viền đỏ */
        .stTextInput input {
            border: 2px solid #ff0000 !important;
            border-radius: 6px !important;
            padding: 10px !important;
            background-color: #f0f2f6 !important;
            color: #333 !important;
        }
        /* Nút Chuyển đổi màu đỏ */
        div.stButton > button {
            background-color: #ff0000 !important;
            color: white !important;
            border: none !important;
            border-radius: 6px !important;
            font-weight: 700 !important;
            padding: 10px 20px !important;
            width: auto !important;
            margin-top: 10px;
        }
        /* Alert thành công */
        .stAlert {
            background-color: #e6f4ea !important;
            color: #1e7e34 !important;
            border: none !important;
            border-radius: 6px !important;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- Main Content ---
    yt_icon = """
    <svg viewBox="0 0 2859 2000" style="width: 70px; height: 70px; flex-shrink: 0;">
        <path fill="#FF0000" d="M2790.8 311.2c-32.3-121.1-127.1-216-248.2-248.2C2323.9 0 1429.5 0 1429.5 0S535 0 316.4 63C195.3 95.2 100.5 190.1 68.2 311.2 0 529.8 0 985 0 985s0 455.2 68.2 673.8c32.3 121.1 127.1 216 248.2 248.2 218.6 63 1113.1 63 1113.1 63s894.4 0 1113.1-63c121.1-32.3 216-127.1 248.2-248.2 68.2-218.6 68.2-673.8 68.2-673.8s0-455.2-68.2-673.8"/>
        <path fill="#FFF" d="M1142.4 1416.3l742.8-431.3-742.8-431.3z"/>
    </svg>
    """
    st.markdown(f"<div class='header-title'>{yt_icon}<span>Mã YouTube Shopee</span></div>", unsafe_allow_html=True)

    st.markdown(f"""
    <a href="{zalo_link}" target="_blank" style="text-decoration: none;">
        <div style="
            background-color: #0068ff;
            color: white; padding: 12px;
            border-radius: 8px; text-align: center;
            font-weight: 700; margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        ">
            💬 THAM GIA NHÓM ZALO HỖ TRỢ
        </div>
    </a>
    """, unsafe_allow_html=True)

    # Input link Shopee
    original_url = st.text_input("Shopee URL", placeholder="Dán link Shopee cần lấy mã vào đây", label_visibility="collapsed")
    sub_id = ""
    
    # Quản lý trạng thái nút bấm
    if "processing_active" not in st.session_state:
        st.session_state["processing_active"] = False

    if st.button("CHUYỂN ĐỔI LINK", disabled=st.session_state["processing_active"]):
        if not original_url:
            st.warning("Vui lòng dán link Shopee!")
        elif "smtt=0" in original_url:
            st.warning("⚠️ Đây là link video, hãy gửi link sản phẩm.")
        elif not any(domain in original_url for domain in ["shopee.vn", "shp.ee", "s.shopee"]):
            st.warning("⚠️ Vui lòng dán link Shopee.")
        else:
            st.session_state["processing_active"] = True
            st.rerun()

    # Logic xử lý khi đang active
    if st.session_state["processing_active"]:
        with st.spinner("Đang xử lý..."):
            try:
                resolved_url = original_url
                req_res = requests.post(f"{api_url_global}/request-conversion", json={"url": resolved_url, "sub_id": sub_id})
                job_id = req_res.json().get("job_id") if req_res.status_code == 200 else None

                if not job_id:
                    st.error(f"❌ Lỗi server ({req_res.status_code}): {req_res.text[:300]}")
                    st.session_state["processing_active"] = False
                    st.button("THỬ LẠI", on_click=lambda: st.rerun())
                else:
                    max_retries = 60  # 60 × 0.5s = 30 giây
                    status_placeholder = st.empty()
                    found_result = False
                    
                    for _ in range(max_retries):
                        time.sleep(0.5)
                        status_req = requests.get(f"{api_url_global}/check-status", params={"job_id": job_id})
                        if status_req.status_code == 200:
                            data = status_req.json()
                            # if data["status"] == "pending" and data.get("queue_position", 0) > 0:
                            #     status_placeholder.warning(f"⏳ Bạn đang ở vị trí thứ **{data['queue_position']}** trong hàng đợi. Vui lòng đợi...")
                            # elif data.get("detailed_status"):
                            #     status_placeholder.info(f"⏳ {data['detailed_status']}")
                            
                            if data["status"] == "complete":
                                status_placeholder.empty()
                                raw_yt_link = data.get("youtube_link", "")
                                result_link = raw_yt_link if raw_yt_link and raw_yt_link != "SUCCESS" else st.session_state.get("fixed_link", "")
                                st.success("Gắn mã thành công ✅")
                                st.text_input("Result", value=result_link, label_visibility="collapsed", key="res_val")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    # Sử dụng link trực tiếp được style như button thay vì cho button vào trong thẻ a
                                    st.markdown(f"""
                                    <a href="{result_link}" target="_blank" style="text-decoration: none;">
                                        <div style="
                                            width: 100%; padding: 10px; background-color: white; 
                                            color: #333; border: 1px solid #ccc; border-radius: 6px; 
                                            text-align: center; font-weight: 600; font-size: 14px;
                                            box-sizing: border-box;
                                        ">
                                            🌍 MỞ LINK ĐỂ LẤY MÃ
                                        </div>
                                    </a>
                                    """, unsafe_allow_html=True)
                                with col2:
                                    components.html(f"<button onclick=\"navigator.clipboard.writeText('{result_link}').then(() => {{ this.innerHTML = '✅ ĐĂNG COPY'; this.style.backgroundColor = '#ff0000'; this.style.color = 'white'; setTimeout(() => {{ this.innerHTML = '📋 COPY LINK'; this.style.backgroundColor = 'white'; this.style.color = '#333'; }}, 2000); }})\" style=\"width: 100%; padding: 10px; background-color: white; color: #333; border: 2px solid #ff0000; border-radius: 6px; cursor: pointer; font-weight: 600; font-family: sans-serif;\">📋 COPY LINK</button>", height=55)
                                found_result = True
                                break
                            elif data["status"] == "error":
                                status_placeholder.empty()
                                err_msg = data.get('error', 'Lỗi không xác định')
                                if not err_msg.startswith("❌"):
                                    err_msg = f"❌ {err_msg}"
                                st.error(err_msg)
                                found_result = True
                                break
                    
                    if not found_result:
                        st.error("⏳ Hết thời gian chờ (30s). Vui lòng thử lại.")
                    
                    st.session_state["processing_active"] = False

            except Exception as e:
                st.error(f"Lỗi: {str(e)}")
                st.session_state["processing_active"] = False

if __name__ == "__main__":
    main()
