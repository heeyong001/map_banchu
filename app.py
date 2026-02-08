import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import random
import os

# [수정 1] GestureHandling 없을 때 에러 방지
try:
    from folium.plugins import GestureHandling
    gesture_handling_available = True
except ImportError:
    gesture_handling_available = False

# 1. 화면 설정
st.set_page_config(layout="wide", page_title="재고 현황 대시보드")

# 스타일 CSS
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem !important;
        }
        div[data-testid="stVerticalBlock"] button {
            text-align: left !important;
            justify-content: flex-start !important;
            border: none !important;
            background: transparent !important;
            padding-left: 0px !important;
        }
        div[data-testid="stVerticalBlock"] button:hover {
            background: #f0f2f6 !important;
            color: black !important;
        }
        div[data-testid="stVerticalBlock"] button:focus {
            background: #ffecec !important;
            color: red !important;
            font-weight: bold !important;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 데이터 사전
# ==============================================================================

REGION_MAPPING = {
    "강변TM": ["강변", "테크노", "구의"],
    "신도림TM": ["신도림"],
    "남부": ["수원", "팔달", "우만", "영통", "권선", "장안", "화성", "동탄", "봉담", "병점", "오산", "평택", "장당", "송탄", "안중", "팽성", "안성", "대천", "공도", "군포", "산본", "의왕", "안양", "평촌", "만안", "동안", "과천"],
    "서남": ["강서", "화곡", "마곡", "양천", "목동", "구로", "개봉", "오류", "금천", "가산", "영등포", "여의도", "동작", "사당", "관악", "신림", "봉천", "시흥", "배곧", "정왕", "안산", "부천", "상동", "중동", "김포", "광명", "철산", "서부물류"],
    "서북": ["은평", "연신내", "수색", "마포", "홍대", "신촌", "서대문", "용산", "이태원", "청파", "파주", "운정", "문산", "고양", "일산", "삼송", "원흥", "화정", "성사", "덕양"],
    "동북": ["광진", "군자", "성동", "성수", "왕십리", "동대문", "종로", "숭인", "중랑", "상봉", "성북", "강북", "도봉", "노원", "의정부", "양주", "포천", "동두천", "지행", "구리", "남양주", "별내", "다산", "양평", "양수"],
    "동남": ["강남", "서초", "송파", "잠실", "강동", "천호", "성남", "분당", "판교", "위례", "하남", "미사", "광주", "이천", "여주", "홍문", "용인", "수지", "기흥", "죽전"],
    "인천": ["인천", "부평", "계양", "서구", "연수", "남동", "미추홀", "송도", "청라"],
    "강원": ["강원", "춘천", "원주", "강릉", "속초", "동해", "인제", "원통", "홍천"]
}

CITY_COORDS = {
    # 1. [최우선] 특정 업체명
    "반추": [37.5186, 126.8913], "반추정보통신": [37.5186, 126.8913],
    
    # [고양시 덕양구 상세]
    "화정": [37.6346, 126.8326], "성사": [37.6533, 126.8430], "삼송": [37.6530, 126.8950], 
    "원흥": [37.6500, 126.8730], "덕양": [37.6380, 126.8330],
    "일산": [37.6600, 126.7700], "고양": [37.6600, 126.7700],

    # [경기 서남부 상세]
    "배곧": [37.3705, 126.7335], "정왕": [37.3450, 126.7400], "은행": [37.4360, 126.7970],
    "상동": [37.5050, 126.7530], "중동": [37.5020, 126.7640], "소사": [37.4830, 126.7940],
    "풍무": [37.6030, 126.7230], "사우": [37.6190, 126.7190], "구래": [37.6450, 126.6280],
    "철산": [37.4760, 126.8680], "하안": [37.4550, 126.8810],

    # [경기 남부 상세]
    "팔달": [37.2798, 127.0441], "우만": [37.2913, 127.0396], "영통": [37.2511, 127.0709],
    "장안": [37.3036, 126.9745], "권선": [37.2575, 126.9715],
    "동탄": [37.2005, 127.0976], "병점": [37.2070, 127.0330], "봉담": [37.2160, 126.9450], "향남": [37.1320, 126.9210],
    "장당": [37.0468, 127.0607], "송탄": [37.0820, 127.0570], "안중": [36.9930, 126.9310], "팽성": [36.9580, 127.0520],
    "공도": [37.0010, 127.1720], "대천": [37.0160, 127.2660],

    # [경기 동남부 상세]
    "판교": [37.3956, 127.1112], "분당": [37.3827, 127.1189], "야탑": [37.4110, 127.1280],
    "위례": [37.4787, 127.1458], "수지": [37.3223, 127.0975], "기흥": [37.2655, 127.1293], "죽전": [37.3240, 127.1070],
    "미사": [37.5640, 127.1940], "경안": [37.4090, 127.2570], "태전": [37.3940, 127.2280],
    "홍문": [37.2960, 127.6365], 

    # [경기 북부/동부 상세]
    "민락": [37.7470, 127.0990], "지행": [37.8935, 127.0545], 
    "옥정": [37.8220, 127.0960], "덕정": [37.8420, 127.0620],
    "다산": [37.6230, 127.1570], "별내": [37.6440, 127.1150], "호평": [37.6550, 127.2430],
    "양수": [37.5452, 127.3276], "운정": [37.7160, 126.7450], "문산": [37.8550, 126.7940],
    "전곡": [38.0260, 127.0660],

    # [강원 상세]
    "원통": [38.1326, 128.2036], "인제": [38.0697, 128.1703],

    # [인천 상세]
    "부평": [37.5070, 126.7219], "계양": [37.5374, 126.7377], "송도": [37.3947, 126.6393], "청라": [37.5384, 126.6337],
    "구월": [37.4490, 126.7050], "주안": [37.4650, 126.6800], "검단": [37.5930, 126.6740],

    # [서울 상세]
    "테크노": [37.5351, 127.0957], "강변": [37.5351, 127.0957], "구의": [37.5370, 127.0861], "신도림": [37.5087, 126.8905],
    "마곡": [37.5600, 126.8250], "화곡": [37.5411, 126.8495], "목동": [37.5302, 126.8729], 
    "가산": [37.4800, 126.8826], "신림": [37.4842, 126.9296], "봉천": [37.4820, 126.9530],
    "사당": [37.4765, 126.9816], "여의도": [37.5219, 126.9242], "잠실": [37.5132, 127.1000], "천호": [37.5436, 127.1255],
    "홍대": [37.5575, 126.9245], "신촌": [37.5598, 126.9425], "합정": [37.5484, 126.9137], "연신내": [37.6186, 126.9207],
    "수색": [37.5802, 126.8958], "이태원": [37.5345, 126.9940], "청파": [37.5447, 126.9678], "혜화": [37.5820, 127.0010],
    "군자": [37.5571, 127.0794], "아차산": [37.5520, 127.0890], "성수": [37.5445, 127.0559], "왕십리": [37.5619, 127.0384],
    "상봉": [37.5954, 127.0858], "수유": [37.6370, 127.0250], "창동": [37.6530, 127.0470], "노원": [37.6542, 127.0568],
    "서부물류": [37.5113, 126.8373],

    # [수도권 주요 시/군]
    "시흥": [37.3801, 126.8029], "안산": [37.3219, 126.8309], "부천": [37.5034, 126.7660], "김포": [37.6153, 126.7157], "광명": [37.4786, 126.8646],
    "수원": [37.2636, 127.0286], "화성": [37.1995, 126.8315], "오산": [37.1498, 127.0772], "평택": [36.9925, 127.1127], "안성": [37.0080, 127.2797],
    "군포": [37.3614, 126.9351], "산본": [37.3614, 126.9351], "의왕": [37.3447, 126.9739], "안양": [37.3943, 126.9568],
    "이천": [37.2811, 127.4358], "여주": [37.2983, 127.6370], "광주": [37.4294, 127.2550], "성남": [37.4200, 127.1265], "용인": [37.2410, 127.1775], "하남": [37.5393, 127.2149],
    "동두천": [37.9036, 127.0604], "구리": [37.6033, 127.1436], "남양주": [37.6360, 127.2165], "의정부": [37.7381, 127.0337], "양주": [37.7853, 127.0458], "포천": [37.8949, 127.2003],
    "파주": [37.7600, 126.7800], "일산": [37.6600, 126.7700], "고양": [37.6600, 126.7700],
    "인천": [37.4563, 126.7052],

    # [서울 구]
    "강남": [37.4979, 127.0276], "서초": [37.4837, 127.0324], "송파": [37.5145, 127.1066], "강동": [37.5301, 127.1238],
    "강서": [37.5509, 126.8495], "양천": [37.5169, 126.8665], "구로": [37.4954, 126.8874], "금천": [37.4573, 126.8964],
    "영등포": [37.5264, 126.8962], "동작": [37.5124, 126.9393], "관악": [37.4784, 126.9516],
    "마포": [37.5663, 126.9016], "서대문": [37.5791, 126.9368], "은평": [37.6027, 126.9291], "용산": [37.5326, 126.9645],
    "종로": [37.5729, 126.9791], "중구": [37.5637, 126.9975], "성동": [37.5633, 127.0371], "광진": [37.5385, 127.0823],
    "동대문": [37.5714, 127.0097], "중랑": [37.6065, 127.0927], "성북": [37.5891, 127.0182], "강북": [37.6396, 127.0257], "도봉": [37.6688, 127.0471],

    # [최후순위 - 광역]
    "춘천": [37.8813, 127.7298], "원주": [37.3422, 127.9202], "강릉": [37.7519, 128.8760],
    "강원": [37.8228, 128.1555], "서울": [37.5665, 126.9780], "경기": [37.4138, 127.5183],
    "서남": [37.5120, 126.8680], "동북": [37.6542, 127.0568]
}

# ==============================================================================
# 3. 헬퍼 함수
# ==============================================================================

def get_region_category(text):
    if pd.isna(text): return "기타"
    text = str(text).strip()
    explicit_keys = ["강변TM", "신도림TM", "동남", "동북", "서남", "서북", "남부", "강원", "인천"]
    for key in explicit_keys:
        if key in text:
            return key
    for key, keywords in REGION_MAPPING.items():
        for keyword in keywords:
            if keyword in text:
                return key
    return "기타"

def get_city_only(text):
    if pd.isna(text): return "미분류(서울)"
    text = str(text)
    for city in CITY_COORDS.keys():
        if city in text:
            return city
    return "미분류(서울)"

def get_coordinate_with_jitter(text):
    if pd.isna(text): return None, None, "미확인"
    text = str(text)
    base_lat, base_lon = 37.5665, 126.9780
    for city, coords in CITY_COORDS.items():
        if city in text:
            base_lat, base_lon = coords
            break
    jitter_lat = base_lat + random.uniform(-0.015, 0.015)
    jitter_lon = base_lon + random.uniform(-0.015, 0.015)
    return jitter_lat, jitter_lon

def get_real_color(korean_color):
    if pd.isna(korean_color): return '#3388ff', '#000000'
    c = str(korean_color).lower()
    if '블랙' in c or 'black' in c or '스페이스' in c or '그라파이트' in c: return '#000000', '#FFFFFF' 
    elif '화이트' in c or 'white' in c or '실버' in c or '스타라이트' in c: return '#FFFFFF', '#000000' 
    elif '티타늄' in c or '내추럴' in c or '그레이' in c: return '#808080', '#000000' 
    elif '블루' in c or 'blue' in c: return '#0000FF', '#FFFFFF' 
    elif '핑크' in c or 'pink' in c: return '#FFC0CB', '#000000' 
    elif '그린' in c or 'green' in c: return '#008000', '#FFFFFF' 
    elif '골드' in c or '옐로우' in c: return '#FFD700', '#000000' 
    elif '퍼플' in c or '보라' in c: return '#800080', '#FFFFFF' 
    elif '레드' in c or 'red' in c: return '#FF0000', '#FFFFFF' 
    return '#3388ff', '#000000'

# ==============================================================================
# [핵심] 최적화된 데이터 로드 함수
# ==============================================================================
@st.cache_data
def load_data_optimized(file):
    if isinstance(file, str): # 파일 경로인 경우
        df = pd.read_excel(file, dtype=str)
    else: # 파일 객체인 경우
        df = pd.read_excel(file, dtype=str)
    
    boyu_col = None
    for col in df.columns:
        if '보유처' in str(col):
            boyu_col = col
            break
            
    if boyu_col:
        df[boyu_col] = df[boyu_col].astype(str).str.replace(r'^[^-\s]*\d[^-\s]*-', '', regex=True)
        coords = df[boyu_col].apply(get_coordinate_with_jitter)
        df['cached_lat'] = [x[0] for x in coords]
        df['cached_lon'] = [x[1] for x in coords]
        df['cached_region'] = df[boyu_col].apply(get_region_category)
        df['cached_city'] = df[boyu_col].apply(get_city_only)
        
    return df

# --- 세션 초기화 ---
if 'filtered_data' not in st.session_state:
    st.session_state['filtered_data'] = None
if 'selected_idx' not in st.session_state:
    st.session_state['selected_idx'] = None

# =========================================================
# 1. [상단] 파일 업로드 및 영구 저장 로직
# =========================================================
DATA_FILE = 'inventory_data.xlsx' # 데이터 파일
META_FILE = 'file_info.txt' # [NEW] 파일 이름 저장용

with st.expander("📂 데이터 업로드 (클릭하여 열기)", expanded=True):
    col_up, col_del = st.columns([8, 2])
    with col_up:
        uploaded_file = st.file_uploader("엑셀 파일을 올려주세요 (자동 저장됨)", type=["xlsx", "csv"])
    with col_del:
        if st.button("🗑️ 데이터 초기화"):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            if os.path.exists(META_FILE):
                os.remove(META_FILE)
            st.session_state['filtered_data'] = None
            st.cache_data.clear()
            st.rerun()

# [핵심 로직] 파일 업로드 시 -> 데이터와 '이름'을 함께 저장
if uploaded_file:
    # 1. 엑셀 파일 저장
    with open(DATA_FILE, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # 2. 파일 이름 저장 (NEW)
    with open(META_FILE, "w", encoding="utf-8") as f:
        f.write(uploaded_file.name)
        
    st.success(f"✅ [{uploaded_file.name}] 파일이 서버에 저장되었습니다.")
    st.cache_data.clear()

# [핵심 로직] 저장된 파일 불러오기 + 이름 표시
df = None
if os.path.exists(DATA_FILE):
    try:
        df = load_data_optimized(DATA_FILE)
        
        # 저장된 이름 읽어오기
        saved_file_name = "이전 데이터"
        if os.path.exists(META_FILE):
            with open(META_FILE, "r", encoding="utf-8") as f:
                saved_file_name = f.read().strip()
                
        if not uploaded_file:
            st.info(f"📂 이전에 저장된 파일 [{saved_file_name}]을 불러왔습니다.")
            
    except Exception as e:
        st.error(f"파일 로드 오류: {e}")

if df is not None:
    col_map = {}
    for col in df.columns:
        clean_col = str(col).replace('▼', '').strip()
        if '보유처' in clean_col: col_map['보유처'] = col
        elif '모델명' in clean_col: col_map['모델명'] = col
        elif '색상' in clean_col: col_map['색상'] = col
        elif any(k in clean_col for k in ['재고', '상태', '등급']): col_map['status'] = col

    target_col = None
    if len(df.columns) >= 14:
        target_col = df.columns[13] # N열
    
    if target_col is None:
        for col in df.columns:
            c = str(col).replace('▼', '').strip()
            if any(k in c for k in ['출고', '날짜', '메모', '비고']):
                target_col = col
                break

    if target_col:
        col_map['target_col'] = target_col

    if '보유처' not in col_map:
        st.error("🚨 엑셀에 '보유처' 컬럼이 없습니다.")
        st.stop()

    real_boyu = col_map['보유처']
    real_model = col_map.get('모델명', df.columns[0])
    real_color = col_map.get('색상', None)
    real_status = col_map.get('status', None)
    real_target = col_map.get('target_col', None)
    
    # =========================================================
    # 2. 검색 조건
    # =========================================================
    st.markdown("##### 🔍 검색 조건")
    col1, col2, col3, col4 = st.columns([3, 3, 3, 1])
    
    with col1:
        all_models = df[real_model].unique().tolist()
        selected_models = st.multiselect("모델 선택", all_models, default=all_models)
        
    with col2:
        if real_color:
            if selected_models:
                filtered_models_df = df[df[real_model].isin(selected_models)]
                available_colors = ["전체"] + sorted(filtered_models_df[real_color].unique().tolist())
            else:
                available_colors = ["전체"]
            selected_colors = st.multiselect("색상 선택", available_colors, default=["전체"])
        else:
            selected_colors = []
            st.write("색상 정보 없음")

    with col3:
        region_order = ["전체", "동남", "동북", "서남", "서북", "남부", "강원", "인천", "강변TM", "신도림TM"]
        selected_regions = st.multiselect("지역 선택", region_order, default=["전체"])

    with col4:
        st.write("") 
        st.write("") 
        search_clicked = st.button("🚀 조회", type="primary")

    # =========================================================
    # 3. 조회 및 결과
    # =========================================================
    if search_clicked:
        filtered_df = df[df[real_model].isin(selected_models)]
        
        if real_color and selected_colors:
            if "전체" not in selected_colors:
                filtered_df = filtered_df[filtered_df[real_color].isin(selected_colors)]
            
        if selected_regions:
            if "전체" not in selected_regions:
                filtered_df = filtered_df[filtered_df['cached_region'].isin(selected_regions)]

        filtered_df = filtered_df.sort_values(by=real_boyu, ascending=True)

        list_df = filtered_df.copy()
        
        if not list_df.empty:
            map_df = list_df[~list_df[real_boyu].astype(str).str.startswith('도매-', na=False)]
        else:
            map_df = pd.DataFrame()

        st.session_state['filtered_data'] = {'list': list_df, 'map': map_df}
        st.session_state['selected_idx'] = None

    st.markdown("---")

    if st.session_state['filtered_data'] is not None:
        
        data_store = st.session_state['filtered_data']
        list_df = data_store['list']
        map_df = data_store['map']

        if not list_df.empty:
            left_col, right_col = st.columns([6, 4]) 

            # [우측] 리스트
            with right_col:
                st.subheader(f"📋 검색 결과 ({len(list_df)}건)")
                
                if not map_df.empty:
                    unclassified_df = map_df[map_df['cached_city'] == '미분류(서울)']
                    if not unclassified_df.empty:
                        st.warning(f"⚠️ 위치 미확인 {len(unclassified_df)}건")
                        with st.expander("🚨 리스트 확인"):
                            st.dataframe(unclassified_df[[real_boyu, real_model, 'cached_city']], hide_index=True)

                h1, h2, h3, h4, h5, h6 = st.columns([2.8, 2.2, 1.5, 1.5, 1.5, 2.0])
                h1.markdown("**보유처 (클릭)**")
                h2.markdown("**모델명**")
                h3.markdown("**색상**")
                h4.markdown("**재고상태**") 
                h5.markdown("**지역**")
                
                date_header = real_target if real_target else "출고일(미확인)"
                h6.markdown(f"**{date_header}**")
                st.divider()

                selected_idx = st.session_state['selected_idx']
                display_df = list_df.copy()
                if selected_idx is not None and selected_idx in display_df.index:
                    sel_row = display_df.loc[[selected_idx]]
                    others = display_df.drop(selected_idx)
                    display_df = pd.concat([sel_row, others])

                with st.container(height=500):
                    for idx, row in display_df.iterrows():
                        c1, c2, c3, c4, c5, c6 = st.columns([2.8, 2.2, 1.5, 1.5, 1.5, 2.0])
                        
                        is_selected = (selected_idx == idx)
                        btn_label = f"🔴 {row[real_boyu]}" if is_selected else str(row[real_boyu])
                        
                        if c1.button(btn_label, key=f"btn_{idx}", use_container_width=True):
                            st.session_state['selected_idx'] = idx
                            st.rerun()

                        c2.write(row[real_model])
                        c3.write(row[real_color] if real_color else "-")
                        
                        status_val = row[real_status] if real_status else "-"
                        if str(status_val) == "nan": status_val = "-"
                        if status_val != "정상" and status_val != "-":
                            c4.markdown(f"<span style='background-color: #ffe6e6; color: red; padding: 3px; border-radius: 5px; font-weight: bold;'>{status_val}</span>", unsafe_allow_html=True)
                        else:
                            c4.write(status_val)

                        c5.write(row['cached_region'])
                        
                        val = row[real_target] if real_target else "-"
                        if str(val) == 'nan': val = "-"
                        c6.write(val)

            # [좌측] 지도
            with left_col:
                selected_index = st.session_state['selected_idx']

                if selected_index is not None and selected_index not in map_df.index:
                     st.warning("선택하신 항목은 '도매' 데이터이므로 지도에 표시되지 않습니다.")
                     selected_index = None

                if not map_df.empty:
                    center_lat = map_df['cached_lat'].mean()
                    center_lon = map_df['cached_lon'].mean()
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                    
                    if gesture_handling_available:
                        try:
                            GestureHandling().add_to(m)
                        except:
                            pass

                    for idx, row in map_df.iterrows():
                        current_color_name = row[real_color] if real_color else 'blue'
                        icon_color_hex, _ = get_real_color(current_color_name)
                        
                        if idx == selected_index:
                            marker_pin_color = 'red'
                            z_index = 1000
                        else:
                            marker_pin_color = 'white'
                            z_index = 1

                        val = row[real_target] if real_target else "-"
                        if str(val) == 'nan': val = "-"

                        safe_copy_text = f"{row['cached_region']} | {row[real_model]} | {current_color_name} | {row[real_boyu]} | {val}"
                        safe_copy_text = safe_copy_text.replace("'", "").replace("\n", " ").replace('"', '')

                        popup_html = f"""
                        <div id="popup-{idx}" style="cursor: pointer;" 
                             onclick="navigator.clipboard.writeText('{safe_copy_text}').then(() => {{alert('클립보드에 복사되었습니다');}});">
                            <b>{row['cached_region']} ({row['cached_city']})</b><br>
                            {row[real_model]}<br>
                            색상: {current_color_name}<br>
                            {row[real_boyu]}<br>
                            비고: {val}
                        </div>
                        """
                        
                        folium.Marker(
                            location=[row['cached_lat'], row['cached_lon']],
                            icon=folium.Icon(color=marker_pin_color, icon_color=icon_color_hex, icon='mobile-alt', prefix='fa'),
                            popup=folium.Popup(popup_html, max_width=300),
                            z_index_offset=z_index
                        ).add_to(m)

                    sw = map_df[['cached_lat', 'cached_lon']].min().values.tolist()
                    ne = map_df[['cached_lat', 'cached_lon']].max().values.tolist()
                    m.fit_bounds([sw, ne])

                    st_folium(m, width="100%", height=700, returned_objects=[])

                else:
                     m = folium.Map(location=[37.5665, 126.9780], zoom_start=7)
                     st_folium(m, width="100%", height=700, returned_objects=[])
                     st.info("💡 지도에 표시할 데이터가 없습니다.")

        else:
            st.warning("조건에 맞는 데이터가 없습니다.")
else:
    st.info("☝️ 상단의 '📂 데이터 업로드' 버튼을 눌러 엑셀 파일을 올려주세요.")