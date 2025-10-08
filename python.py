# app.py

import streamlit as st
import pandas as pd
from google import genai
from google.genai.errors import APIError
import docx
import numpy as np
import json # Thư viện cần thiết cho json.loads()

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
    # st.error("Lỗi: Không tìm thấy Khóa API 'GEMINI_API_KEY'. Vui lòng cấu hình trong Streamlit Secrets.")

# --- HÀM HỖ TRỢ ĐỌC FILE WORD (Giữ nguyên) ---
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

# --- HÀM GỌI API GEMINI ĐỂ LỌC DỮ LIỆU (ĐÃ CHỈNH SỬA LỖI JSON) ---
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
        
        **QUAN TRỌNG: Chỉ trả lời bằng đối tượng JSON thuần túy, không có bất kỳ văn bản, giải thích, hay ký tự nào khác bên ngoài khối JSON. KHÔNG SỬ DỤNG ```JSON HOẶC ```.**

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
        
        # --- BẮT ĐẦU PHẦN XỬ LÝ HẬU KỲ ĐỂ KHẮC PHỤC LỖI JSON ---
        json_string = response.text.strip()
        
        # 1. Loại bỏ các khối markdown thừa (ví dụ: ```json...``` hoặc ```...)
        if json_string.startswith("```json"):
            json_string = json_string[7:].strip()
        elif json_string.startswith("```"): # Trường hợp không có 'json'
            json_string = json_string[3:].strip()
            
        if json_string.endswith("```"):
            json_string = json_string[:-3].strip()
        
        # 2. Xử lý trường hợp AI trả về text không phải JSON (rất hiếm khi xảy ra nếu prompt tốt)
        if not json_string.startswith("{") or not json_string.endswith("}"):
            raise json.JSONDecodeError("Phản hồi không phải là cấu trúc JSON", json_string, 0)
            
        # 3. Cố gắng chuyển đổi chuỗi JSON đã được dọn dẹp sang dict Python
        return json.loads(json_string)

    except APIError as e:
        st.error(f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}")
        return None
    except json.JSONDecodeError as jde:
        st.error(f"Lỗi: AI không trả về định dạng JSON hợp lệ. Vui lòng thử lại với tài liệu rõ ràng hơn.")
        st.markdown("**Phản hồi thô của AI để kiểm tra:**")
        st.code(response.text) # Hiển thị phản hồi thô để dễ dàng debug
        return None
    except Exception as e:
        st.error(f"Đã xảy ra lỗi không xác định trong quá trình AI lọc dữ liệu: {e}")
        return None
        
# --- HÀM TÍNH TOÁN DÒNG TIỀN VÀ CHỈ SỐ (Giữ nguyên) ---
def calculate_project_metrics(data):
    """Xây dựng bảng dòng tiền và tính toán NPV, IRR, PP, DPP."""
    
    # 1. Trích xuất thông số
    try:
        # Xử lý các giá trị N/A nếu AI không tìm thấy
        investment = float(data.get("Vốn đầu tư ban đầu (Initial Investment)", 0) if data.get("Vốn đầu tư ban đầu (Initial Investment)") != 'N/A' else 0)
        life = int(data.get("Dòng đời dự án (Project Life - năm)", 0) if data.get("Dòng đời dự án (Project Life - năm)") != 'N/A' else 0)
        revenue = float(data.get("Doanh thu hàng năm (Annual Revenue)", 0) if data.get("Doanh thu hàng năm (Annual Revenue)") != 'N/A' else 0)
        cost = float(data.get("Chi phí hoạt động hàng năm (Annual Operating Cost)", 0) if data.get("Chi phí hoạt động hàng năm (Annual Operating Cost)") != 'N/A' else 0)
        wacc = float(data.get("WACC (Weighted Average Cost of Capital - %)**", 0) if data.get("WACC (Weighted Average Cost of Capital - %)**") != 'N/A' else 0) / 100.0
        tax_rate = float(data.get("Thuế suất (Tax Rate - %)**", 0) if data.get("Thuế suất (Tax Rate - %)**") != 'N/A' else 0) / 100.0
    except ValueError:
        st.error("Lỗi: Các thông số tài chính cần phải là số. Vui lòng kiểm tra dữ liệu AI đã lọc.")
        return None, None
        
    if life <= 0 or wacc <= 0 or investment <= 0:
        st.warning("Dòng đời dự án, WACC hoặc Vốn đầu tư phải lớn hơn 0 để tính toán. Vui lòng kiểm tra lại dữ liệu đã lọc.")
        return None, None

    # 2. Xây dựng Bảng Dòng Tiền (Cash Flow - CF)
    
    ebit = revenue - cost 
    tax_paid = ebit * tax_rate if ebit > 0 else 0
    net_income = ebit - tax_paid
    cf_t = net_income 
    
    years = [0] + list(range(1, life + 1))
    cash_flows = [-investment] + [cf_t] * life
    
    df_cf = pd.DataFrame({
        'Năm': years,
        'Dòng tiền thuần (CF)': cash_flows,
        'Yếu tố': ['Vốn đầu tư'] + ['Dòng tiền hoạt động'] * life
    })
    
    # 3. Tính toán các chỉ số hiệu quả dự án
    
    # NPV (Net Present Value)
    npv = np.npv(wacc, cash_flows) 
    
    # IRR (Internal Rate of Return)
    try:
        irr = np.irr(cash_flows)
    except Exception:
        irr = np.nan 

    # PP (Payback Period - Thời gian hoàn vốn)
    cumulative_cf = np.cumsum(cash_flows)
    payback_year = next((i for i, cf in enumerate(cumulative_cf) if cf >= 0), life)
    
    if payback_year <= life and payback_year > 0:
        prev_cf = cumulative_cf[payback_year - 1]
        current_cf = cash_flows[payback_year]
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
        "WACC": f"{wacc*100:.2f}%",
        "NPV (Giá trị hiện tại ròng)": f"{npv:,.0f}",
        "IRR (Tỷ suất hoàn vốn nội tại)": f"{irr*100:.2f}%" if not np.isnan(irr) else "Không xác định",
        "PP (Thời gian hoàn vốn)": f"{pp:.2f} năm" if isinstance(pp, float) else pp,
        "DPP (Thời gian hoàn vốn chiết khấu)": f"{dpp:.2f} năm" if isinstance(dpp, float) else dpp
    }

    return df_cf, metrics

# --- HÀM PHÂN TÍCH CHỈ SỐ BẰNG AI (Giữ nguyên) ---
def analyze_project_with_ai(metrics, api_key):
    """Gửi các chỉ số đánh giá dự án đến Gemini API và nhận nhận xét."""
    if not api_key:
        return "Lỗi: Chưa cung cấp Khóa API."

    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash'  

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
# --- LUỒNG ỨNG DỤNG STREAMLIT (Giữ nguyên) ---
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
            # Xóa session cũ để chạy lại cache_data
            if 'financial_data' in st.session_state:
                del st.session_state['financial_data']
            
            with st.spinner('Đang gửi văn bản và chờ AI trích xuất thông số...'):
                financial_data = extract_financial_data_with_ai(project_text_content, GEMINI_API_KEY)
                
                if financial_data:
                    st.session_state['financial_data'] = financial_data
                    st.session_state['financial_data_edited'] = financial_data # Khởi tạo dữ liệu chỉnh sửa
                    st.success("AI đã trích xuất dữ liệu thành công! Vui lòng kiểm tra và chỉnh sửa.")

        # Hiển thị và chỉnh sửa dữ liệu đã lọc
        if 'financial_data_edited' in st.session_state:
            st.subheader("2. Thông số Tài chính Đã Lọc (Có thể chỉnh sửa)")
            
            # Chuyển đổi dict sang DataFrame để hiển thị và chỉnh sửa
            df_filtered = pd.DataFrame(st.session_state['financial_data_edited'].items(), 
                                      columns=['Chỉ tiêu', 'Giá trị'])
            
            df_edited = st.data_editor(
                df_filtered.set_index('Chỉ tiêu'),
                column_config={"Giá trị": st.column_config.TextColumn("Giá trị", help="Nhập giá trị số (ví dụ: 10000000) hoặc N/A")},
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
                
                cols = st.columns(5) # 5 cột cho 5 chỉ số (Thêm WACC)
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
         st.warning("Vui lòng cấu hình Khóa API 'GEMINI_API_KEY' trong Streamlit Secrets để sử dụng chức năng AI.")
    else:
        st.info("Vui lòng tải lên file Word để bắt đầu đánh giá phương án kinh doanh.")
