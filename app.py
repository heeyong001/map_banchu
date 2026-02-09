import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
import random
import os
import hashlib
import json

# [안전 장치] GestureHandling 모듈 에러 방지
try:
    from folium.plugins import GestureHandling
    gesture_handling_available = True
except ImportError:
    gesture_handling_available = False

# 1. 화면 설정
st.set_page_config(layout="wide", page_title="재고 현황 대시보드")

# ==============================================================================
# [핵심] CSS 스타일 최적화 (모바일 리스트 & 드래그 개선)
# ==============================================================================
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        
        /* [모바일 최적화] 리스트 아이템 간격 축소 */
        div[data-testid="stVerticalBlock"] > div {
            gap: 0.5rem !important;
        }
        
        /* [모바일 최적화] 버튼 스타일: 작고 컴팩트하게 */
        div.stButton > button {
            width: 100%;
            height: auto;
            padding: 0.3rem 0.5rem;
            font-size: 14px;
            line-height: 1.2;
        }

        /* 팝업 테이블 스타일 */
        .popup-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11px !important;
            font-family: sans-serif;
        }
        .popup-table th {
            background-color: #f2f2f2;
            border-bottom: 1px solid #ddd;
            padding: 2px 4px !important;
            text-align: center;
            font-weight: bold;
        }
        .popup-table td {
            border-bottom: 1px solid #ddd;
            padding: 2px 4px !important;
            text-align: center;
        }
        
        /* 리스트 텍스트 스타일 */
        .list-title {
            font-weight: bold;
            font-size: 14px;
            color: #333;
            margin-bottom: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .list-sub {
            font-size: 12px;
            color: #666;
        }
        
        /* 구분선 여백 축소 */
        hr {
            margin-top: 0.5em !important;
            margin-bottom: 0.5em !important;
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
    "서북": ["은평", "연신내", "수색", "마포", "홍대", "신촌", "서대문", "용산", "이태원", "청파", "파주", "운정", "문산", "고양", "일산", "삼송", "원흥", "화정", "성사", "덕양", "신원"],
    "동북": ["광진", "군자", "성동", "성수", "왕십리", "동대문", "종로", "숭인", "중랑", "상봉", "성북", "강북", "도봉", "노원", "의정부", "양주", "포천", "동두천", "지행", "구리", "남양주", "별내", "다산", "양평", "양수"],
    "동남": ["강남", "서초", "송파", "잠실", "강동", "천호", "성남", "분당", "판교", "위례", "하남", "미사", "광주", "이천", "여주", "홍문", "용인", "수지", "기흥", "죽전"],
    "인천": ["인천", "부평", "계양", "서구", "연수", "남동", "미추홀", "송도", "청라"],
    "강원": ["강원", "춘천", "원주", "강릉", "속초", "동해", "인제", "원통", "홍천"]
}

CITY_COORDS = {
    "반추": [37.5156, 126.8950], "반추정보통신": [37.5156, 126.8950], 
    "신원": [37.6744, 126.8653], 
    "화정": [37.6346, 126.8326], "성사": [37.6533, 126.8430], "삼송": [37.6530, 126.8950], 
    "원흥": [37.6500, 126.8730], "덕양": [37.6380, 126.8330],
    "일산": [37.6600, 126.7700], "고양": [37.6600, 126.7700],
    "배곧": [37.3705, 126.7335], "정왕": [37.3450, 126.7400], "은행": [37.4360, 126.7970],
    "상동": [37.5050, 126.7530], "중동": [37.5020, 126.7640], "소사": [37.4830, 126.7940],
    "풍무": [37.6030, 126.7230], "사우": [37.6190, 126.7190], "구래": [37.6450, 126.6280],
    "철산": [37.4760, 126.8680], "하안": [37.4550, 126.8810],
    "팔달": [37.2798, 127.0441], "우만": [37.2913, 127.0396], "영통": [37.2511, 127.0709],
    "장안": [37.3036, 126.9745], "권선": [37.2575, 126.9715],
    "동탄": [37.2005, 127.0976], "병점": [37.2070, 127.0330], "봉담": [37.2160, 126.9450], "향남": [37.1320, 126.9210],
    "장당": [37.0468, 127.0607], "송탄": [37.0820, 127.0570], "안중": [36.9930, 126.9310], "팽성": [36.9580, 127.0520],
    "공도": [37.0010, 127.1720], "대천": [37.0160, 127.2660],
    "판교": [37.3956, 127.1112], "분당": [37.3827, 127.1189], "야탑": [37.4110, 127.1280],
    "위례": [37.4787, 127.1458], "수지": [37.3223, 127.0975], "기흥": [37.2655, 127.1293], "죽전": [37.3240, 127.1070],
    "미사": [37.5640, 127.1940], "경안": [37.4090, 127.2570], "태전": [37.3940, 127.2280],
    "홍문": [37.2960, 127.6365], 
    "민락": [37.7470, 127.0990], "지행": [37.8935, 127.0545], 
    "옥정": [37.8220, 127.0960], "덕정": [37.8420, 127.0620],
    "다산": [37.6230, 127.1570], "별내": [37.6440, 127.1150], "호평": [37.6550, 127.2430],
    "양수": [37.5452, 127.3276], "운정": [37.7160, 126.7450], "문산": [37.8550, 126.7940],
    "전곡": [38.0260, 127.0660],
    "원통": [38.1326, 128.2036], "인제": [38.0697, 128.1703],
    "부평": [37.5070, 126.7219], "계양": [37.5374, 126.7377], "송도": [37.3947, 126.6393], "청라": [37.5384, 126.6337],
    "구월": [37.4490, 126.7050], "주안": [37.4650, 126.6800], "검단": [37.5930, 126.6740],
    "테크노": [37.5351, 127.0957], "강변": [37.5351, 127.0957], "구의": [37.5370, 127.0861], "신도림": [37.5087, 126.8905],
    "마곡": [37.5600, 126.8250], "화곡": [37.5411, 126.8495], "목동": [37.5302, 126.8729], 
    "가산": [37.4800, 126.8826], "신림": [37.4842, 126.9296], "봉천": [37.4820, 126.9530],
    "사당": [37.4765, 126.9816], "여의도": [37.5219, 126.9242], "잠실": [37.5132, 127.1000], "천호": [37.5436, 127.1255],
    "홍대": [37.5575, 126.9245], "신촌": [37.5598, 126.9425], "합정": [37.5484, 126.9137], "연신내": [37.6186, 126.9207],
    "수색": [37.5802, 126.8958], "이태원": [37.5345, 126.9940], "청파": [37.5447, 126.9678], "혜화": [37.5820, 127.0010],
    "군자": [37.5571, 127.0794], "아차산": [37.5520, 127.0890], "성수": [37.5445, 127.0559], "왕십리": [37.5619, 127.0384],
    "상봉": [37.5954, 127.0858], "수유": [37.6370, 127.0250], "창동": [37.6530, 127.0470], "노원": [37.6542, 127.0568],
    "서부물류": [37.5113, 126.8373],
    "시흥": [37.3801, 126.8029], "안산": [37.3219, 126.8309], "부천": [37.5034, 126.7660], "김포": [37.6153, 126.7157], "광명": [37.4786, 126.8646],
    "수원": [37.2636, 127.0286], "화성": [37.1995, 126.8315], "오산": [37.1498, 127.0772], "평택": [36.9925, 127.1127], "안성": [37.0080, 127.2797],
    "군포": [37.3614, 126.9351], "산본": [37.3614, 126.9351], "의왕": [37.3447, 126.9739], "안양": [37.3943, 126.9568],
    "이천": [37.2811, 127.4358], "여주": [37.2983, 127.6370], "광주": [37.4294, 127.2550], "성남": [37.4200, 127.1265], "용인": [37.2410, 127.1775], "하남": [37.5393, 127.2149],
    "동두천": [37.9036, 127.0604], "구리": [37.6033, 127.1436], "남양주": [37.6360, 127.2165], "의정부": [37.7381, 127.0337], "양주": [37.7853, 127.0458], "포천": [37.8949, 127.2003],
    "파주": [37.7600, 126.7800], "인천": [37.4563, 126.7052],
    "강남": [37.4979, 127.0276], "서초": [37.4837, 127.0324], "송파": [37.5145, 127.1066], "강동": [37.5301, 127.1238],
    "강서": [37.5509, 126.8495], "양천": [37.5169, 126.8665], "구로": [37.4954, 126.8874], "금천": [37.4573, 126.8964],
    "영등포": [37.5264, 126.8962], "동작": [37.5124, 126.9393], "관악": [37.4784, 126.9516],
    "마포": [37.5663, 126.9016], "서대문": [37.5791, 126.9368], "은평": [37.6027, 126.9291], "용산": [37.5326, 126.9645],
    "종로": [37.5729, 126.9791], "중구": [37.5637, 126.9975], "성동": [37.5633, 127.0371], "광진": [37.5385, 127.0823],
    "동대문": [37.5714, 127.0097], "중랑": [37.6065, 127.0927], "성북": [37.5891, 127.0182], "강북": [37.6396, 127.0257], "도봉": [37.6688, 127.0471],
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

def get_coordinate_smart_jitter(store_name, base_lat, base_lon):
    if pd.isna(store_name): return base_lat, base_lon
    
    if "반추" in str(store_name):
        return base_lat, base_lon
        
    hash_obj = hashlib.md5(str(store_name).encode())
    hash_int = int(hash_obj.hexdigest(), 16)
    
    random.seed(hash_int) 
    lat_offset = random.uniform(-0.005, 0.005)
    lon_offset = random.uniform(-0.005, 0.005)
    
    return base_lat + lat_offset, base_lon + lon_offset

def get_base_coordinate(text):
    if pd.isna(text): return 37.5665, 126.9780 # 서울 기본값
    text = str(text)
    for city, coords in CITY_COORDS.items():
        if city in text:
            return coords[0], coords[1]
    return 37.5665, 126.9780

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
    if isinstance(file, str): 
        df = pd.read_excel(file, dtype=str)
    else: 
        df = pd.read_excel(file, dtype=str)
    
    boyu_col = None
    for col in df.columns:
        if '보유처' in str(col):
            boyu_col = col
            break
            
    if boyu_col:
        df[boyu_col] = df[boyu_col].astype(str).str.strip()
        df.loc[df[boyu_col].str.contains("반추", na=False), boyu_col] = "반추정보통신"
        
        clean_names = df[boyu_col].str.replace(r'^[^-\s]*\d[^-\s]*-', '', regex=True)
        base_coords = clean_names.apply(get_base_coordinate)
        
        final_lats = []
        final_lons = []
        for i, row in df.iterrows():
            b_lat, b_lon = base_coords[i]
            store_name = row[boyu_col]
            f_lat, f_lon = get_coordinate_smart_jitter(store_name, b_lat, b_lon)
            final_lats.append(f_lat)
            final_lons.append(f_lon)

        df['cached_lat'] = final_lats
        df['cached_lon'] = final_lons
        df['cached_region'] = clean_names.apply(get_region_category)
        df['cached_city'] = clean_names.apply(get_city_only)
        
    return df

# --- 세션 초기화 ---
if 'filtered_data' not in st.session_state:
    st.session_state['filtered_data'] = None
if 'selected_idx' not in st.session_state:
    st.session_state['selected_idx'] = None

# =========================================================
# 1. [상단] 파일 업로드 및 영구 저장 로직
# =========================================================
DATA_FILE = 'inventory_data.xlsx'
META_FILE = 'file_info.txt' 

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

if uploaded_file:
    with open(DATA_FILE, "wb") as f:
        f.write(uploaded_file.getbuffer())
    with open(META_FILE, "w", encoding="utf-8") as f:
        f.write(uploaded_file.name)
    st.success(f"✅ [{uploaded_file.name}] 파일이 서버에 저장되었습니다.")
    st.cache_data.clear()

df = None
if os.path.exists(DATA_FILE):
    try:
        df = load_data_optimized(DATA_FILE)
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
    
    row1_c1, row1_c2 = st.columns(2)
    with row1_c1:
        all_models = df[real_model].unique().tolist()
        selected_models = st.multiselect("모델 선택 (필수)", all_models, default=[], placeholder="모델을 선택해주세요")
        
    with row1_c2:
        all_owners = sorted(df[real_boyu].unique().tolist())
        selected_owners = st.multiselect("보유처 선택", ["전체"] + all_owners, default=["전체"])

    row2_c1, row2_c2, row2_c3 = st.columns([3, 3, 2])
    with row2_c1:
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

    with row2_c2:
        region_order = ["전체", "동남", "동북", "서남", "서북", "남부", "강원", "인천", "강변TM", "신도림TM"]
        selected_regions = st.multiselect("지역 선택", region_order, default=["전체"])

    with row2_c3:
        st.write("") 
        search_clicked = st.button("🚀 조회", type="primary", use_container_width=True)

    # =========================================================
    # 3. 조회 및 결과
    # =========================================================
    if search_clicked:
        if not selected_models and "전체" in selected_owners:
             st.warning("⚠️ 모델을 최소 1개 이상 선택해주세요. (데이터 과부하 방지)")
             st.session_state['filtered_data'] = None
        else:
            if selected_models:
                filtered_df = df[df[real_model].isin(selected_models)]
            else:
                filtered_df = df

            if "전체" not in selected_owners:
                filtered_df = filtered_df[filtered_df[real_boyu].isin(selected_owners)]
            
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

            # [우측] 리스트 (모바일 최적화: 2줄 보기)
            with right_col:
                st.subheader(f"📋 검색 결과 ({len(list_df)}건)")
                
                MAX_LIST_ITEMS = 100
                if len(list_df) > MAX_LIST_ITEMS:
                    st.warning(f"⚠️ 상위 {MAX_LIST_ITEMS}개만 표시합니다.")
                    display_df = list_df.head(MAX_LIST_ITEMS)
                else:
                    display_df = list_df

                selected_idx = st.session_state['selected_idx']
                
                # [모바일 최적화] 헤더 제거 (직관적으로 변경)
                # st.columns 헤더 삭제됨

                with st.container(height=500):
                    for idx, row in display_df.iterrows():
                        # [핵심] 리스트 아이템 레이아웃 (8:2 비율)
                        # 왼쪽: 정보 (2줄) / 오른쪽: 버튼 (📍)
                        c_info, c_btn = st.columns([8, 2])
                        
                        is_selected = (selected_idx == idx)
                        bg_style = "background-color: #ffecec;" if is_selected else ""
                        
                        with c_info:
                            # 1줄: 보유처 이름 (진하게)
                            store_name = row[real_boyu]
                            # 2줄: 모델 | 색상 | 상태 | 날짜
                            details = f"{row[real_model]} | {row[real_color] if real_color else '-'} | {row[real_status] if real_status else '-'} | {row[real_target] if real_target else '-'}"
                            
                            st.markdown(f"""
                            <div style='{bg_style} padding: 2px;'>
                                <div class='list-title'>{store_name}</div>
                                <div class='list-sub'>{details}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                        with c_btn:
                            if st.button("📍", key=f"btn_{idx}"):
                                st.session_state['selected_idx'] = idx
                                st.rerun()
                        
                        st.divider() # 얇은 구분선

            # [좌측] 지도
            with left_col:
                selected_index = st.session_state['selected_idx']

                # [상단 복사 패널]
                if selected_index is not None and selected_index in list_df.index:
                    selected_row = list_df.loc[selected_index]
                    target_store_name = selected_row[real_boyu]
                    
                    store_inventory = list_df[list_df[real_boyu] == target_store_name]
                    
                    copy_text_lines = [f"[{target_store_name}]"]
                    for _, row in store_inventory.iterrows():
                        c_name = row[real_color] if row[real_color] else "-"
                        copy_text_lines.append(f"{row[real_model]} {c_name}")
                    
                    final_copy_text = "\n".join(copy_text_lines)
                    
                    st.info(f"📍 **{target_store_name}** 선택됨")
                    st.code(final_copy_text, language='text')

                if not map_df.empty:
                    center_lat = map_df['cached_lat'].mean()
                    center_lon = map_df['cached_lon'].mean()
                    
                    # [모바일 최적화] 지도 높이 450px
                    m = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                    
                    if gesture_handling_available:
                        try:
                            GestureHandling().add_to(m)
                        except:
                            pass
                    
                    grouped_stores = map_df.groupby(['cached_lat', 'cached_lon', real_boyu])

                    for (lat, lon, store_name), group_df in grouped_stores:
                        
                        unique_colors = group_df[real_color].unique()
                        if len(unique_colors) == 1:
                            current_color_name = unique_colors[0]
                            icon_color_hex, _ = get_real_color(current_color_name)
                            if icon_color_hex.upper() == '#FFFFFF':
                                bg_color = "rgba(0, 0, 0, 0.4)"
                                icon_color = "white"
                            else:
                                bg_color = "rgba(255, 255, 255, 0.8)"
                                icon_color = icon_color_hex
                        else:
                            bg_color = "rgba(128, 0, 128, 0.8)"
                            icon_color = "white"

                        if selected_index in group_df.index:
                            bg_color = "rgba(255, 0, 0, 0.85)"
                            icon_color = "white"
                            z_index = 1000
                        else:
                            z_index = 1

                        copy_lines = [f"[{store_name}]"]
                        table_rows = ""
                        color_counts = group_df.groupby([real_model, real_color]).size().reset_index(name='count')
                        
                        for _, row in color_counts.iterrows():
                            c_name = row[real_color] if row[real_color] else "-"
                            qty = row['count']
                            table_rows += f"<tr><td>{row[real_model]}</td><td>{c_name}</td><td>{qty}</td></tr>"
                            copy_lines.append(f"{row[real_model]} {c_name} {qty}대")

                        full_copy_text = "\n".join(copy_lines)
                        safe_json_text = json.dumps(full_copy_text)

                        # [모바일 친화적 복사]
                        popup_html = f"""
                        <div id="popup-{random.randint(0,100000)}" style="cursor: pointer; width: 100%;"
                             onclick='
                                var text = {safe_json_text};
                                window.prompt("복사하려면 버튼을 누르세요 (모바일) / Ctrl+C (PC)", text);
                             '>
                            <h4 style='margin: 5px 0; font-size: 14px; color: #333;'>{store_name}</h4>
                            <div style='font-size: 10px; color: #666; margin-bottom: 5px;'>
                                {group_df['cached_region'].iloc[0]} ({group_df['cached_city'].iloc[0]})
                            </div>
                            <table class="popup-table">
                                <thead>
                                    <tr>
                                        <th>모델</th>
                                        <th>색상</th>
                                        <th>수</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {table_rows}
                                </tbody>
                            </table>
                            <div style='text-align: right; margin-top: 5px; font-weight: bold; font-size: 11px;'>
                                총계: {len(group_df)}대
                            </div>
                            <div style='text-align: center; color: blue; font-size: 10px; margin-top: 5px;'>
                                (클릭하여 복사)
                            </div>
                        </div>
                        """
                        
                        icon_html = f"""
                        <div style="
                            background-color: {bg_color};
                            color: {icon_color};
                            width: 32px;
                            height: 32px;
                            border-radius: 50%;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            font-size: 18px;
                            box-shadow: 2px 2px 5px rgba(0,0,0,0.3);">
                            <i class="fa fa-mobile"></i>
                        </div>
                        """
                        
                        folium.Marker(
                            location=[lat, lon],
                            icon=folium.DivIcon(html=icon_html),
                            popup=folium.Popup(popup_html, max_width=230),
                            z_index_offset=z_index
                        ).add_to(m)

                    st_folium(m, width="100%", height=450, returned_objects=[])

                else:
                     m = folium.Map(location=[37.5665, 126.9780], zoom_start=7)
                     st_folium(m, width="100%", height=450, returned_objects=[])
                     st.info("💡 지도에 표시할 데이터가 없습니다.")

        else:
            st.warning("조건에 맞는 데이터가 없습니다.")
else:
    st.info("☝️ 상단의 '📂 데이터 업로드' 버튼을 눌러 엑셀 파일을 올려주세요.")