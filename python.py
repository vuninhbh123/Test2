# app.py

import streamlit as st
import pandas as pd
from google import genai
from google.genai.errors import APIError
import docx # Thư viện để đọc file .docx
import numpy as np # Dùng cho tính toán NPV/IRR

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Đánh Giá Phương Án Kinh Doanh",
    layout="wide"
)

st.title("Ứng dụng Đánh giá Hiệu quả Dự án Kinh doanh 🚀")
st.markdown("Sử dụng AI để lọc thông số và tính toán các chỉ số tài chính (NPV, IRR, PP, DPP) từ file Word.")

# --- Thiết lập API Key ---
try:
    # Lấy API key từ Streamlit Secrets
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    GEMINI_API_KEY = None
    st.error("Lỗi: Không tìm thấy Khóa API 'GEMINI_API_KEY'. Vui lòng cấu hình trong Streamlit Secrets.")

# --- HÀM HỖ TRỢ ĐỌC FILE WORD ---
def read_docx(file):
    """Đọc toàn bộ nội dung văn bản từ file docx đã tải lên."""
    try:
        doc = docx.Document(file)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        st.error(f"Lỗi đọc file Word: {e}")
        return None

# --- HÀM GỌI API GEMINI ĐỂ LỌC DỮ LIỆU (Yêu cầu 1) ---
@st.cache_data(show_spinner=False)
def extract_financial_data_with_ai(project_text, api_key):
    """
    Sử dụng Gemini AI để trích xuất các thông số tài chính.
    """
    if not api_key:
        return None

    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash'  

        prompt = f"""
        Bạn là một chuyên gia tài chính và phân tích dữ liệu. Hãy đọc văn bản về dự án kinh doanh dưới đây và trích xuất **chính xác** các thông số sau.
        Nếu không tìm thấy, hãy điền 'N/A' (Lưu ý: WACC, Thuế thường là %; các mục còn lại là giá trị tiền tệ).
        **Thời gian của dự án (Dòng đời dự án)** phải được thể hiện bằng số năm nguyên.
        
        Xuất ra kết quả dưới dạng một đối tượng JSON duy nhất (không có chú thích, không có văn bản giải thích).

        Văn bản dự án:
        ---
        {project_text}
        ---

        Định dạng JSON yêu cầu:
        {{
            "Vốn đầu tư ban đầu (Initial Investment)": 0, 
            "Dòng đời dự án (Project Life - năm)": 0, 
            "Doanh thu hàng năm (Annual Revenue)": 0,
            "Chi phí hoạt động hàng năm (Annual Operating Cost)": 0,
            "WACC (Weighted Average Cost of Capital - %)**": 0.0,
            "Thuế suất (Tax Rate - %)**": 0.0
        }}
        """

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        
        # Cố gắng chuyển đổi chuỗi phản hồi JSON sang dict Python
        import json
        return json.loads(response.text.strip())

    except APIError as e:
        st.error(f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}")
        return None
    except json.JSONDecodeError:
        st.error("Lỗi: AI không trả về định dạng JSON hợp lệ. Vui lòng thử lại với tài liệu rõ ràng hơn.")
        return None
    except Exception as e:
        st.error(f"Đã xảy ra lỗi không xác định trong quá trình AI lọc dữ liệu: {e}")
        return None

# --- HÀM TÍNH TOÁN DÒNG TIỀN VÀ CHỈ SỐ (Yêu cầu 2 & 3) ---
def calculate_project_metrics(data):
    """Xây dựng bảng dòng tiền và tính toán NPV, IRR, PP, DPP."""
    
    # 1. Trích xuất thông số
    try:
        investment = float(data.get("Vốn đầu tư ban đầu (Initial Investment)", 0))
        life = int(data.get("Dòng đời dự án (Project Life - năm)", 0))
        revenue = float(data.get("Doanh thu hàng năm (Annual Revenue)", 0))
        cost = float(data.get("Chi phí hoạt động hàng năm (Annual Operating Cost)", 0))
        wacc = float(data.get("WACC (Weighted Average Cost of Capital - %)**", 0)) / 100.0
        tax_rate = float(data.get("Thuế suất (Tax Rate - %)**", 0)) / 100.0
    except ValueError:
        st.error("Lỗi: Các thông số tài chính cần phải là số. Vui lòng kiểm tra dữ liệu AI đã lọc.")
        return None, None
        
    if life <= 0 or wacc <= 0 or investment <= 0:
        st.warning("Dòng đời dự án, WACC hoặc Vốn đầu tư phải lớn hơn 0 để tính toán.")
        return None, None

    # 2. Xây dựng Bảng Dòng Tiền (Cash Flow - CF)
    
    # Giả định đơn giản: Không có Khấu hao, Vốn lưu động, Giá trị thanh lý.
    # Lợi nhuận trước Thuế và Lãi vay (EBIT) = Doanh thu - Chi phí
    ebit = revenue - cost 
    
    # Thuế phải nộp
    tax_paid = ebit * tax_rate if ebit > 0 else 0
    
    # Lợi nhuận sau thuế (Net Income) = EBIT - Thuế
    net_income = ebit - tax_paid
    
    # Dòng tiền thuần (Net Cash Flow) = Net Income + Khấu hao (giả định Khấu hao = 0)
    # Vì không có Khấu hao nên Net Cash Flow = Net Income
    cf_t = net_income 
    
    # Tạo DataFrame
    years = [0] + list(range(1, life + 1))
    
    # Dòng tiền ban đầu: -Vốn đầu tư
    cash_flows = [-investment] + [cf_t] * life
    
    df_cf = pd.DataFrame({
        'Năm': years,
        'Dòng tiền thuần (CF)': cash_flows,
        'Yếu tố': ['Vốn đầu tư'] + ['Dòng tiền hoạt động'] * life
    })
    
    # 3. Tính toán các chỉ số hiệu quả dự án
    
    # NPV (Net Present Value)
    # np.npv (rate, values) - Dòng tiền từ năm 0 trở đi
    npv = np.npv(wacc, cash_flows) 
    
    # IRR (Internal Rate of Return)
    # np.irr (values) - Dòng tiền từ năm 0 trở đi
    try:
        irr = np.irr(cash_flows)
    except Exception:
        irr = np.nan # Có thể không tính được IRR nếu CF không đổi dấu

    # PP (Payback Period - Thời gian hoàn vốn)
    cumulative_cf = np.cumsum(cash_flows)
    payback_year = next((i for i, cf in enumerate(cumulative_cf) if cf >= 0), life)
    
    if payback_year <= life and payback_year > 0:
        # Tính chi tiết: Năm hoàn vốn - 1 + (Vốn còn thiếu cuối năm T-1 / CF năm T)
        prev_cf = cumulative_cf[payback_year - 1] # Giá trị âm
        current_cf = cash_flows[payback_year] # Giá trị dương (dòng tiền năm đó)
        pp = (payback_year - 1) + (-prev_cf / current_cf)
    elif payback_year == 0:
        pp = 0
    else:
        pp = 'Không hoàn vốn'

    # DPP (Discounted Payback Period - Thời gian hoàn vốn có chiết khấu)
    discounted_cf = [cash_flows[0]] + [cf / (1 + wacc)**t for t, cf in enumerate(cash_flows[1:], 1)]
    cumulative_discounted_cf = np.cumsum(discounted_cf)
    
    discounted_payback_year = next((i for i, cf in enumerate(cumulative_discounted_cf) if cf >= 0), life)
    
    if discounted_payback_year <= life and discounted_payback_year > 0:
        prev_dcf = cumulative_discounted_cf[discounted_payback_year - 1]
        current_dcf = discounted_cf[discounted_payback_year]
        dpp = (discounted_payback_year - 1) + (-prev_dcf / current_dcf)
    elif discounted_payback_year == 0:
        dpp = 0
    else:
        dpp = 'Không hoàn vốn'

    metrics = {
        "NPV (Giá trị hiện tại ròng)": f"{npv:,.0f}",
        "IRR (Tỷ suất hoàn vốn nội tại)": f"{irr*100:.2f}%" if not np.isnan(irr) else "Không xác định",
        "PP (Thời gian hoàn vốn)": f"{pp:.2f} năm" if isinstance(pp, float) else pp,
        "DPP (Thời gian hoàn vốn chiết khấu)": f"{dpp:.2f} năm" if isinstance(dpp, float) else dpp
    }

    return df_cf, metrics

# --- HÀM PHÂN TÍCH CHỈ SỐ BẰNG AI (Yêu cầu 4) ---
def analyze_project_with_ai(metrics, api_key):
    """Gửi các chỉ số đánh giá dự án đến Gemini API và nhận nhận xét."""
    if not api_key:
        return "Lỗi: Chưa cung cấp Khóa API."

    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash'  

        # Chuyển metrics thành chuỗi markdown để AI dễ đọc
        metrics_markdown = pd.Series(metrics).to_markdown(numalign="left", stralign="left")

        prompt = f"""
        Bạn là một chuyên gia đánh giá dự án đầu tư. Dựa trên các chỉ số hiệu quả dự án sau, hãy đưa ra một nhận xét khách quan, ngắn gọn (khoảng 3-4 đoạn) về tính khả thi và rủi ro của dự án. 
        Đánh giá tập trung vào:
        1. Tính khả thi dựa trên NPV, IRR so với WACC (cần đánh giá IRR > WACC hay không).
        2. Tốc độ thu hồi vốn (PP, DPP).
        3. Khuyến nghị tóm tắt (nên đầu tư/không nên đầu tư).

        Dữ liệu chỉ số đánh giá dự án:
        {metrics_markdown}
        """

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định trong quá trình AI phân tích: {e}"

# =========================================================================
# --- LUỒNG ỨNG DỤNG STREAMLIT ---
# =========================================================================

# 1. Tải File Word
uploaded_file = st.file_uploader(
    "1. Tải file Word (.docx) chứa Phương án Kinh doanh",
    type=['docx']
)

if uploaded_file is not None and GEMINI_API_KEY:
    
    # Đọc nội dung file Word
    project_text_content = read_docx(uploaded_file)
    
    if project_text_content:
        # Nút bấm để thực hiện tạo tác lọc dữ liệu (Yêu cầu 1)
        if st.button("▶️ 1. Lọc Thông tin Tài chính bằng AI"):
            with st.spinner('Đang gửi văn bản và chờ AI trích xuất thông số...'):
                financial_data = extract_financial_data_with_ai(project_text_content, GEMINI_API_KEY)
                
                if financial_data:
                    st.session_state['financial_data'] = financial_data
                    st.success("AI đã trích xuất dữ liệu thành công!")

        # Hiển thị và chỉnh sửa dữ liệu đã lọc
        if 'financial_data' in st.session_state:
            st.subheader("2. Thông số Tài chính Đã Lọc (Có thể chỉnh sửa)")
            
            # Sử dụng st.data_editor để người dùng có thể điều chỉnh
            # Chuyển đổi dict sang DataFrame để hiển thị và chỉnh sửa
            df_filtered = pd.DataFrame(st.session_state['financial_data'].items(), 
                                      columns=['Chỉ tiêu', 'Giá trị'])
            
            # Đặt index là 'Chỉ tiêu' để dễ chỉnh sửa 'Giá trị'
            df_edited = st.data_editor(
                df_filtered.set_index('Chỉ tiêu'),
                column_config={"Giá trị": st.column_config.NumberColumn("Giá trị", format="%0.4f")},
                use_container_width=True
            )
            
            # Lưu lại dữ liệu đã chỉnh sửa vào session state
            st.session_state['financial_data_edited'] = df_edited.to_dict()['Giá trị']
            
            # Thực hiện tính toán
            st.markdown("---")
            if st.button("🧮 3. Xây dựng Bảng Dòng tiền và Tính toán Chỉ số"):
                with st.spinner('Đang tính toán dòng tiền và chỉ số...'):
                    
                    df_cf, metrics = calculate_project_metrics(st.session_state['financial_data_edited'])
                    
                    if df_cf is not None and metrics is not None:
                        st.session_state['df_cf'] = df_cf
                        st.session_state['metrics'] = metrics
                        st.success("Tính toán hoàn tất!")

            # Hiển thị kết quả tính toán (Yêu cầu 2 & 3)
            if 'metrics' in st.session_state:
                
                # Hiển thị Bảng Dòng Tiền (Yêu cầu 2)
                st.subheader("Bảng Dòng Tiền Thuần (Cash Flow Table)")
                st.dataframe(st.session_state['df_cf'].style.format({
                    'Dòng tiền thuần (CF)': '{:,.0f}'
                }), use_container_width=True)
                
                # Hiển thị Chỉ số Đánh giá (Yêu cầu 3)
                st.subheader("4. Các Chỉ số Đánh giá Hiệu quả Dự án")
                
                # Dùng cột để hiển thị các chỉ số
                cols = st.columns(4)
                for i, (key, value) in enumerate(st.session_state['metrics'].items()):
                    cols[i].metric(key, value)
                
                st.markdown("---")

                # Nút Yêu cầu AI Phân tích (Yêu cầu 4)
                st.subheader("5. Phân tích Hiệu quả Dự án (AI)")
                if st.button("🤖 Yêu cầu AI Phân tích Các Chỉ số"):
                    with st.spinner('Đang gửi chỉ số và chờ Gemini phân tích...'):
                        ai_result = analyze_project_with_ai(st.session_state['metrics'], GEMINI_API_KEY)
                        st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                        st.info(ai_result)

else:
    if not GEMINI_API_KEY:
         st.warning("Vui lòng cấu hình Khóa API 'GEMINI_API_KEY' để sử dụng chức năng AI.")
    else:
        st.info("Vui lòng tải lên file Word để bắt đầu đánh giá phương án kinh doanh.")
