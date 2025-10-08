# python.py

import streamlit as st
import pandas as pd
import numpy as np
import io
from pydocx import PyDocx
from google import genai
from google.genai.errors import APIError

# --- HẰNG SỐ ---
# Dùng cho việc tính toán tài chính
N_NAM_TOI_DA = 10 
# Danh sách các chỉ tiêu cần trích xuất
CHIEU_KHOA_CAN_LOC = [
    "Vốn đầu tư (Investment)", 
    "Dòng đời dự án (Project Life)", 
    "Doanh thu năm đầu (Revenue Year 1)", 
    "Chi phí hoạt động năm đầu (Operating Cost Year 1)", 
    "Tốc độ tăng trưởng hàng năm (Annual Growth Rate)", # Giả định tốc độ tăng trưởng cố định
    "WACC/Tỷ suất chiết khấu (Discount Rate)", 
    "Thuế suất (Tax Rate)"
]

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Đánh giá Phương án Kinh doanh",
    layout="wide"
)

st.title("Ứng dụng Đánh giá Phương án Kinh doanh 📈")
st.caption("Sử dụng Gemini AI để trích xuất dữ liệu, tính toán chỉ số và phân tích hiệu quả dự án.")

# --- Thiết lập API Key ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("⚠️ **Lỗi Cấu hình:** Vui lòng thêm Khóa API Gemini vào Streamlit Secrets với tên biến `GEMINI_API_KEY`.")
    st.stop()


# --- CHỨC NĂNG 1: TRÍCH XUẤT DỮ LIỆU TỪ FILE WORD DÙNG AI ---
def extract_text_from_docx(uploaded_file):
    """Đọc file docx và trích xuất nội dung văn bản."""
    try:
        # pydocx cần một đường dẫn file. Chúng ta tạo file tạm từ BytesIO
        with open("temp_doc.docx", "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # Đọc nội dung HTML từ file tạm, sau đó chuyển sang văn bản thuần túy
        html = PyDocx().to_html(filename="temp_doc.docx")
        # Loại bỏ các thẻ HTML để lấy văn bản thuần túy
        text_content = ' '.join(html.split()) 
        return text_content
    except Exception as e:
        st.error(f"Lỗi đọc file Word: {e}")
        return None

def ai_extract_financial_data(doc_text, api_key):
    """Sử dụng Gemini để lọc các chỉ tiêu tài chính từ văn bản."""
    
    prompt = f"""
    Bạn là một chuyên gia phân tích dự án kinh doanh. Nhiệm vụ của bạn là trích xuất các thông số tài chính chính xác từ văn bản dự án dưới đây.
    
    Văn bản dự án:
    ---
    {doc_text[:15000]} 
    ---
    
    Vui lòng trích xuất các giá trị sau và trả lời bằng một **JSON duy nhất**. 
    Nếu không tìm thấy chỉ tiêu nào, đặt giá trị là 0 hoặc N/A.
    
    1. Vốn đầu tư (Investment): Giá trị ban đầu, thường là chi tiêu ở Năm 0.
    2. Dòng đời dự án (Project Life): Số năm hoạt động (Ví dụ: 5 năm, 10 năm).
    3. Doanh thu năm đầu (Revenue Year 1): Giá trị doanh thu dự kiến trong năm đầu tiên.
    4. Chi phí hoạt động năm đầu (Operating Cost Year 1): Giá trị chi phí hoạt động, chưa tính khấu hao và thuế.
    5. Tốc độ tăng trưởng hàng năm (Annual Growth Rate): Tốc độ tăng trưởng cố định cho Doanh thu và Chi phí (Ví dụ: 5% hoặc 0.05).
    6. WACC/Tỷ suất chiết khấu (Discount Rate): Tỷ lệ chiết khấu dùng để tính NPV (Ví dụ: 10% hoặc 0.1).
    7. Thuế suất (Tax Rate): Tỷ lệ thuế thu nhập doanh nghiệp (Ví dụ: 20% hoặc 0.2).
    
    Đơn vị tiền tệ mặc định là Việt Nam Đồng (VND). Bỏ qua các đơn vị tiền tệ khác trong đầu ra.
    
    Ví dụ định dạng JSON:
    {{
      "Vốn đầu tư (Investment)": 1000000000,
      "Dòng đời dự án (Project Life)": 5,
      "Doanh thu năm đầu (Revenue Year 1)": 300000000,
      "Chi phí hoạt động năm đầu (Operating Cost Year 1)": 150000000,
      "Tốc độ tăng trưởng hàng năm (Annual Growth Rate)": 0.05,
      "WACC/Tỷ suất chiết khấu (Discount Rate)": 0.12,
      "Thuế suất (Tax Rate)": 0.2
    }}
    """
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        # Sử dụng eval/json.loads để chuyển chuỗi JSON thành Dict Python
        import json
        return json.loads(response.text)
    
    except APIError as e:
        st.error(f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}")
        return None
    except Exception as e:
        st.error(f"Lỗi trong quá trình trích xuất JSON: {e}")
        st.code(response.text if 'response' in locals() else "Không nhận được phản hồi", language='json')
        return None

# --- CHỨC NĂNG 2 & 3: TÍNH TOÁN DÒNG TIỀN VÀ CHỈ SỐ ---

# Hàm giúp chuẩn hóa định dạng số cho phép tính
def standardize_rate(value):
    """Chuyển đổi giá trị tỷ lệ (có thể là % hoặc số thập phân) sang số thập phân."""
    if isinstance(value, (int, float)):
        # Nếu là giá trị lớn hơn 1, giả định đó là % và chia cho 100
        return value / 100 if value > 1 else value
    return 0.0

@st.cache_data(show_spinner=False)
def calculate_project_metrics(data):
    """Xây dựng bảng dòng tiền và tính toán các chỉ số tài chính."""
    
    # Chuẩn hóa và trích xuất dữ liệu từ AI
    v_dau_tu = data.get("Vốn đầu tư (Investment)", 0)
    n_nam = data.get("Dòng đời dự án (Project Life)", 0)
    doanh_thu_1 = data.get("Doanh thu năm đầu (Revenue Year 1)", 0)
    chi_phi_hd_1 = data.get("Chi phí hoạt động năm đầu (Operating Cost Year 1)", 0)
    toc_do_tang_truong = standardize_rate(data.get("Tốc độ tăng trưởng hàng năm (Annual Growth Rate)", 0))
    wacc = standardize_rate(data.get("WACC/Tỷ suất chiết khấu (Discount Rate)", 0))
    thue_suat = standardize_rate(data.get("Thuế suất (Tax Rate)", 0))
    
    if n_nam == 0 or wacc == 0:
        st.warning("Dòng đời dự án hoặc WACC không hợp lệ. Không thể tính toán.")
        return None, None

    # Giả định Khấu hao: Tuy không được lọc, ta giả định Khấu hao đường thẳng bằng Vốn đầu tư / Dòng đời dự án
    khau_hao = v_dau_tu / n_nam if n_nam > 0 else 0
    
    # 2. Xây dựng Bảng Dòng Tiền (Cash Flow)
    
    # Khởi tạo bảng dòng tiền với số năm cần thiết (từ năm 0 đến năm n_nam)
    years = list(range(n_nam + 1))
    df_cf = pd.DataFrame(index=years)
    
    # Năm 0: Chỉ có Vốn đầu tư (Outflow)
    df_cf.loc[0, 'Doanh thu'] = 0
    df_cf.loc[0, 'Chi phí hoạt động'] = 0
    df_cf.loc[0, 'Vốn đầu tư'] = -v_dau_tu # Chi tiền
    df_cf.loc[0, 'Lợi nhuận trước thuế (EBT)'] = 0
    df_cf.loc[0, 'Thuế'] = 0
    df_cf.loc[0, 'Dòng tiền sau thuế (ATCF)'] = -v_dau_tu

    # Các Năm 1 đến N
    for year in range(1, n_nam + 1):
        # Tính toán Doanh thu và Chi phí theo Tốc độ tăng trưởng
        revenue = doanh_thu_1 * ((1 + toc_do_tang_truong) ** (year - 1))
        op_cost = chi_phi_hd_1 * ((1 + toc_do_tang_truong) ** (year - 1))
        
        # 1. Lợi nhuận trước thuế (EBT = Doanh thu - Chi phí hoạt động - Khấu hao)
        ebt = revenue - op_cost - khau_hao
        
        # 2. Thuế (Tax)
        tax = max(0, ebt * thue_suat)
        
        # 3. Lợi nhuận sau thuế (EAT)
        eat = ebt - tax
        
        # 4. Dòng tiền sau thuế (ATCF = EAT + Khấu hao - Vốn đầu tư bổ sung)
        # Trong mô hình cơ bản này, không có vốn đầu tư bổ sung hay giá trị thanh lý cuối kỳ
        atcf = eat + khau_hao
        
        # Ghi vào DataFrame
        df_cf.loc[year, 'Doanh thu'] = revenue
        df_cf.loc[year, 'Chi phí hoạt động'] = op_cost
        df_cf.loc[year, 'Khấu hao (Giả định)'] = khau_hao # Thêm dòng khấu hao để tiện theo dõi
        df_cf.loc[year, 'Lợi nhuận trước thuế (EBT)'] = ebt
        df_cf.loc[year, 'Thuế'] = tax
        df_cf.loc[year, 'Dòng tiền sau thuế (ATCF)'] = atcf

    # 3. Tính toán các chỉ số
    cf_values = df_cf['Dòng tiền sau thuế (ATCF)'].values
    
    # a. NPV (Net Present Value)
    npv_value = np.npv(wacc, cf_values)
    
    # b. IRR (Internal Rate of Return)
    try:
        irr_value = np.irr(cf_values)
    except:
        irr_value = np.nan
        
    # c. PP (Payback Period) và DPP (Discounted Payback Period)
    
    # Tính Tổng dòng tiền tích lũy và Dòng tiền chiết khấu tích lũy
    df_cf['Dòng tiền chiết khấu (DCF)'] = df_cf['Dòng tiền sau thuế (ATCF)'] / ((1 + wacc) ** df_cf.index)
    
    # Ghi đè năm 0 bằng giá trị ATCF của nó để tính tích lũy đúng
    df_cf.loc[0, 'Dòng tiền chiết khấu (DCF)'] = df_cf.loc[0, 'Dòng tiền sau thuế (ATCF)'] 
    
    df_cf['Tổng tích lũy (Cum. CF)'] = df_cf['Dòng tiền sau thuế (ATCF)'].cumsum()
    df_cf['Tổng tích lũy Chiết khấu (Cum. DCF)'] = df_cf['Dòng tiền chiết khấu (DCF)'].cumsum()
    
    # Tìm PP và DPP
    
    # PP
    cf_cum = df_cf['Tổng tích lũy (Cum. CF)']
    pp_year_before = cf_cum[cf_cum < 0].index.max() # Năm cuối cùng mà tích lũy còn âm
    if pp_year_before is np.nan:
        pp_value = 0 # Hoàn vốn ngay
    elif pp_year_before < n_nam:
        # PP = Năm trước + |Tổng tích lũy năm trước| / Dòng tiền năm đó
        pp_value = pp_year_before + (abs(cf_cum.loc[pp_year_before]) / df_cf.loc[pp_year_before + 1, 'Dòng tiền sau thuế (ATCF)'])
    else:
        pp_value = np.inf # Không hoàn vốn trong dòng đời dự án

    # DPP
    dcf_cum = df_cf['Tổng tích lũy Chiết khấu (Cum. DCF)']
    dpp_year_before = dcf_cum[dcf_cum < 0].index.max()
    if dpp_year_before is np.nan:
        dpp_value = 0 # Hoàn vốn ngay
    elif dpp_year_before < n_nam:
        # DPP = Năm trước + |Tổng tích lũy Chiết khấu năm trước| / Dòng tiền Chiết khấu năm đó
        dpp_value = dpp_year_before + (abs(dcf_cum.loc[dpp_year_before]) / df_cf.loc[dpp_year_before + 1, 'Dòng tiền chiết khấu (DCF)'])
    else:
        dpp_value = np.inf
        
    # Chuẩn hóa hiển thị NPV, IRR, PP, DPP
    metrics = {
        "NPV (Giá trị hiện tại ròng)": npv_value,
        "IRR (Tỷ suất sinh lời nội bộ)": irr_value,
        "PP (Thời gian hoàn vốn)": pp_value,
        "DPP (Thời gian hoàn vốn chiết khấu)": dpp_value,
        "WACC (Tỷ suất chiết khấu)": wacc
    }
    
    return df_cf, metrics


# --- CHỨC NĂNG 4: PHÂN TÍCH CHỈ SỐ BẰNG AI ---
def ai_analyze_metrics(metrics, wacc, api_key):
    """Sử dụng Gemini để phân tích các chỉ số hiệu quả dự án."""
    
    prompt = f"""
    Bạn là một chuyên gia thẩm định dự án tài chính. Dựa trên các chỉ số hiệu quả của dự án dưới đây, hãy đưa ra nhận xét chi tiết và chuyên sâu, tập trung vào tính khả thi và rủi ro của dự án.
    
    Các chỉ số cần phân tích:
    1. NPV (Giá trị hiện tại ròng): {metrics.get('NPV (Giá trị hiện tại ròng)', 'N/A'):,.0f} VND
    2. IRR (Tỷ suất sinh lời nội bộ): {metrics.get('IRR (Tỷ suất sinh lời nội bộ)', np.nan) * 100:.2f}%
    3. WACC (Tỷ suất chiết khấu): {wacc * 100:.2f}%
    4. PP (Thời gian hoàn vốn): {metrics.get('PP (Thời gian hoàn vốn)', np.nan):.2f} năm
    5. DPP (Thời gian hoàn vốn chiết khấu): {metrics.get('DPP (Thời gian hoàn vốn chiết khấu)', np.nan):.2f} năm
    
    Yêu cầu phân tích:
    - **NPV & IRR:** Đánh giá tính khả thi (NPV > 0 và IRR > WACC). 
    - **Thời gian hoàn vốn:** So sánh PP và DPP với Dòng đời dự án. Nhấn mạnh sự khác biệt giữa PP và DPP.
    - **Kết luận:** Tóm tắt ngắn gọn nên *chấp nhận* hay *từ chối* dự án này và lý do chính.
    - Trả lời bằng tiếng Việt.
    """
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text
    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định trong quá trình phân tích: {e}"

# ===============================================
# --- LOGIC CHÍNH CỦA STREAMLIT APP ---
# ===============================================

# --- Khu vực Tải File (Chức năng 1) ---
uploaded_file = st.file_uploader(
    "1. Tải file Word (.docx) chứa Phương án Kinh doanh",
    type=['docx']
)

# Sử dụng Streamlit Session State để lưu dữ liệu đã lọc và các chỉ số
if 'extracted_data' not in st.session_state:
    st.session_state['extracted_data'] = None
if 'cash_flow_df' not in st.session_state:
    st.session_state['cash_flow_df'] = None
if 'metrics' not in st.session_state:
    st.session_state['metrics'] = None

if uploaded_file is not None:
    # --- Chức năng 1: Lọc dữ liệu ---
    if st.button("Trích xuất Dữ liệu Tài chính (AI)", key="btn_extract", use_container_width=True):
        doc_text = extract_text_from_docx(uploaded_file)
        if doc_text:
            with st.spinner('Đang gửi văn bản tới Gemini AI để trích xuất các thông số...'):
                extracted_data = ai_extract_financial_data(doc_text, API_KEY)
                st.session_state['extracted_data'] = extracted_data
                st.session_state['cash_flow_df'] = None # Xóa kết quả cũ
                st.session_state['metrics'] = None
                
    if st.session_state['extracted_data']:
        st.divider()
        st.subheader("1. Thông số Tài chính đã Trích xuất (AI) 🤖")
        
        # Hiển thị dưới dạng DataFrame cho dễ nhìn
        df_extracted = pd.Series(st.session_state['extracted_data']).to_frame('Giá trị')
        st.dataframe(df_extracted, use_container_width=True)
        
        # --- Chức năng 2 & 3: Tính toán Dòng tiền và Chỉ số ---
        try:
            df_cf, metrics = calculate_project_metrics(st.session_state['extracted_data'])
            st.session_state['cash_flow_df'] = df_cf
            st.session_state['metrics'] = metrics
            
            # --- Hiển thị Kết quả ---
            
            # Bảng Dòng tiền (Chức năng 2)
            st.subheader("2. Bảng Dòng tiền Dự án (Cash Flow Statement)")
            st.dataframe(df_cf.style.format({
                'Doanh thu': '{:,.0f}',
                'Chi phí hoạt động': '{:,.0f}',
                'Khấu hao (Giả định)': '{:,.0f}',
                'Lợi nhuận trước thuế (EBT)': '{:,.0f}',
                'Thuế': '{:,.0f}',
                'Dòng tiền sau thuế (ATCF)': '{:,.0f}',
                'Dòng tiền chiết khấu (DCF)': '{:,.0f}',
                'Tổng tích lũy (Cum. CF)': '{:,.0f}',
                'Tổng tích lũy Chiết khấu (Cum. DCF)': '{:,.0f}'
            }), use_container_width=True)

            # Các Chỉ số Đánh giá (Chức năng 3)
            st.subheader("3. Các Chỉ số Đánh giá Hiệu quả Dự án")
            
            col1, col2, col3, col4 = st.columns(4)
            wacc_rate = metrics['WACC (Tỷ suất chiết khấu)']
            
            with col1:
                st.metric(
                    label="NPV (Giá trị hiện tại ròng)", 
                    value=f"{metrics['NPV (Giá trị hiện tại ròng)']:,.0f} VND",
                    delta="Dự án KHẢ THI" if metrics['NPV (Giá trị hiện tại ròng)'] > 0 else "Dự án KHÔNG KHẢ THI"
                )
            with col2:
                st.metric(
                    label="IRR (Tỷ suất sinh lời nội bộ)", 
                    value=f"{metrics['IRR (Tỷ suất sinh lời nội bộ)'] * 100:.2f}%",
                    delta="IRR > WACC" if metrics['IRR (Tỷ suất sinh lời nội bộ)'] > wacc_rate else "IRR < WACC"
                )
            with col3:
                st.metric(label="PP (Thời gian hoàn vốn)", value=f"{metrics['PP (Thời gian hoàn vốn)']:.2f} năm")
            with col4:
                st.metric(label="DPP (Hoàn vốn chiết khấu)", value=f"{metrics['DPP (Thời gian hoàn vốn chiết khấu)']:.2f} năm")
                
            st.info(f"Tỷ suất chiết khấu (WACC) đang sử dụng: **{wacc_rate * 100:.2f}%**")
                
            st.divider()
            
            # --- Chức năng 4: Phân tích AI ---
            st.subheader("4. Phân tích Hiệu quả Dự án (AI) 🧠")
            if st.button("Yêu cầu AI Phân tích Chỉ số", key="btn_analyze", type="primary", use_container_width=True):
                with st.spinner('Đang gửi dữ liệu và chờ Gemini phân tích...'):
                    ai_result = ai_analyze_metrics(metrics, wacc_rate, API_KEY)
                    st.session_state['ai_analysis'] = ai_result
            
            if 'ai_analysis' in st.session_state and st.session_state['ai_analysis']:
                st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                st.info(st.session_state['ai_analysis'])


        except Exception as e:
            st.error(f"Lỗi trong quá trình tính toán Dòng tiền/Chỉ số: {e}. Vui lòng kiểm tra lại dữ liệu trích xuất.")
            st.session_state['cash_flow_df'] = None
            st.session_state['metrics'] = None
            
else:
    st.info("Vui lòng tải lên file Word để bắt đầu quá trình đánh giá.")
