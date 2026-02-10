import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
import random
import os
import hashlib
import json

# [안전 장치] GestureHandling
try:
    from folium.plugins import GestureHandling
    gesture_handling_available = True
except ImportError:
    gesture_handling_available = False

# 1. 화면 설정
st.set_page_config(layout="wide", page_title="재고 현황 대시보드")

# ==============================================================================
# [스타일] 엑셀 스타일 팝업 & 모바일 최적화
# ==============================================================================
st.markdown("""
    <style>
        .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        
        div.stButton > button {
            width: 100%;
            height: auto;
            padding: 0.2rem 0.4rem;
            font-size: 13px;
            margin-top: 2px !important;
        }
        
        .list-item-container { padding: 4px 4px; }
        .list-title {
            font-weight: bold;
            font-size: 13px;
            color: #333;
            margin-bottom: 1px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 1.2;
        }
        .list-sub {
            font-size: 11px;
            color: #666;
            line-height: 1.2;
        }
        
        .compact-hr { 
            margin: 0px 0px 4px 0px !important; 
            border: 0; 
            border-top: 1px solid #eee; 
        }
        
        ul[data-testid="stVirtualDropdown"] { max-height: 200px !important; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. 데이터 사전 및 로직
# ==============================================================================

# [신규 기능] 모델 그룹 정의 (사용자가 요청한 묶음)
MODEL_GROUPS = {
    "SM-F766 (N0/NK 통합)": ["SM-F766N0", "SM-F766NK"],
    "SM-S937 (N0/NK 통합)": ["SM-S937N0", "SM-S937NK"]
}

DISTRICT_CENTERS = {
    "강남": [37.5172, 127.0473], "서초": [37.4837, 127.0324], "송파": [37.5145, 127.1066], 
    "강동": [37.5301, 127.1238], "영등포": [37.5264, 126.8962], "마포": [37.5663, 126.9016],
    "용산": [37.5326, 126.9645], "종로": [37.5729, 126.9791], "중구": [37.5637, 126.9975],
    "성동": [37.5633, 127.0371], "광진": [37.5385, 127.0823], "동대문": [37.5714, 127.0097],
    "성북": [37.5891, 127.0182], "강북": [37.6396, 127.0257], "도봉": [37.6688, 127.0471],
    "노원": [37.6542, 127.0568], "은평": [37.6027, 126.9291], "서대문": [37.5791, 126.9368],
    "양천": [37.5169, 126.8665], "강서": [37.5509, 126.8495], "구로": [37.4954, 126.8874],
    "금천": [37.4573, 126.8964], "동작": [37.5124, 126.9393], "관악": [37.4784, 126.9516],
    "중랑": [37.6065, 127.0927],
    "수원": [37.2636, 127.0286], "성남": [37.4200, 127.1265], "의정부": [37.7381, 127.0337],
    "안양": [37.3943, 126.9568], "부천": [37.5034, 126.7660], "광명": [37.4786, 126.8646],
    "평택": [36.9925, 127.1127], "동두천": [37.9036, 127.0604], "안산": [37.3219, 126.8309],
    "고양": [37.6584, 126.8320], "과천": [37.4292, 126.9877], "구리": [37.6033, 127.1436],
    "남양주": [37.6360, 127.2165], "오산": [37.1498, 127.0772], "시흥": [37.3801, 126.8029],
    "군포": [37.3614, 126.9351], "의왕": [37.3447, 126.9739], "하남": [37.5393, 127.2149],
    "용인": [37.2410, 127.1775], "파주": [37.7600, 126.7800], "이천": [37.2811, 127.4358],
    "안성": [37.0080, 127.2797], "김포": [37.6153, 126.7157], "화성": [37.1995, 126.8315],
    "광주": [37.4294, 127.2550], "양주": [37.7853, 127.0458], "포천": [37.8949, 127.2003],
    "여주": [37.2983, 127.6370], "연천": [38.0964, 127.0749], "가평": [37.8315, 127.5095],
    "양평": [37.4912, 127.4876], "인천": [37.4563, 126.7052], 
    "춘천": [37.8813, 127.7298], "원주": [37.3422, 127.9202], "강릉": [37.7519, 128.8760],
    "장안": [37.3036, 126.9745], "권선": [37.2575, 126.9715], "팔달": [37.2798, 127.0441], "영통": [37.2511, 127.0709],
    "수정": [37.4500, 127.1400], "중원": [37.4300, 127.1700], "분당": [37.3827, 127.1189],
    "만안": [37.4000, 126.9200], "동안": [37.3900, 126.9600],
    "덕양": [37.6380, 126.8330], "일산동": [37.6600, 126.7700], "일산서": [37.6700, 126.7500],
    "처인": [37.2300, 127.2000], "기흥": [37.2655, 127.1293], "수지": [37.3223, 127.0975],
}

NEIGHBORHOOD_COORDS = {
    "반추": [37.5156, 126.8950], "반추정보통신": [37.5156, 126.8950],
    "신도림TM": [37.5087, 126.8905], "테크노": [37.5351, 127.0957], "강변TM": [37.5351, 127.0957],
    "신원": [37.6744, 126.8653], "화정": [37.6346, 126.8326], "성사": [37.6533, 126.8430],
    "삼송": [37.6530, 126.8950], "원흥": [37.6500, 126.8730], "배곧": [37.3705, 126.7335],
    "정왕": [37.3450, 126.7400], "은행": [37.4360, 126.7970], "상동": [37.5050, 126.7530],
    "중동": [37.5020, 126.7640], "소사": [37.4830, 126.7940], "풍무": [37.6030, 126.7230],
    "사우": [37.6190, 126.7190], "구래": [37.6450, 126.6280], "철산": [37.4760, 126.8680],
    "하안": [37.4550, 126.8810], "우만": [37.2913, 127.0396], "동탄": [37.2005, 127.0976],
    "병점": [37.2070, 127.0330], "봉담": [37.2160, 126.9450], "향남": [37.1320, 126.9210],
    "장당": [37.0468, 127.0607], "송탄": [37.0820, 127.0570], "안중": [36.9930, 126.9310],
    "팽성": [36.9580, 127.0520], "공도": [37.0010, 127.1720], "대천": [37.0160, 127.2660],
    "판교": [37.3956, 127.1112], "야탑": [37.4110, 127.1280], "위례": [37.4787, 127.1458],
    "죽전": [37.3240, 127.1070], "미사": [37.5640, 127.1940], "경안": [37.4090, 127.2570],
    "태전": [37.3940, 127.2280], "홍문": [37.2960, 127.6365], "민락": [37.7470, 127.0990],
    "지행": [37.8935, 127.0545], "옥정": [37.8220, 127.0960], "덕정": [37.8420, 127.0620],
    "다산": [37.6230, 127.1570], "별내": [37.6440, 127.1150], "호평": [37.6550, 127.2430],
    "양수": [37.5452, 127.3276], "운정": [37.7160, 126.7450], "문산": [37.8550, 126.7940],
    "전곡": [38.0260, 127.0660], "원통": [38.1326, 128.2036], "인제": [38.0697, 128.1703],
    "송도": [37.3947, 126.6393], "청라": [37.5384, 126.6337], "구월": [37.4490, 126.7050],
    "주안": [37.4650, 126.6800], "검단": [37.5930, 126.6740], "여의도": [37.5219, 126.9242],
    "잠실": [37.5132, 127.1000], "천호": [37.5436, 127.1255], "홍대": [37.5575, 126.9245],
    "신촌": [37.5598, 126.9425], "합정": [37.5484, 126.9137], "연신내": [37.6186, 126.9207],
    "수색": [37.5802, 126.8958], "이태원": [37.5345, 126.9940], "청파": [37.5447, 126.9678],
    "혜화": [37.5820, 127.0010], "군자": [37.5571, 127.0794], "아차산": [37.5520, 127.0890],
    "성수": [37.5445, 127.0559], "왕십리": [37.5619, 127.0384], "상봉": [37.5954, 127.0858],
    "수유": [37.6370, 127.0250], "창동": [37.6530, 127.0470], "서부물류": [37.5113, 126.8373]
}

def get_region_category(text):
    if pd.isna(text): return "기타"
    text = str(text).strip()
    for key in ["강변TM", "신도림TM", "동남", "동북", "서남", "서북", "남부", "강원", "인천"]:
        if key in text: return key
    return "기타"

def get_city_only(text):
    if pd.isna(text): return "미분류(서울)"
    text = str(text)
    for dong in NEIGHBORHOOD_COORDS.keys():
        if dong in text: return dong
    for dist in DISTRICT_CENTERS.keys():
        if dist in text: return dist
    return "미분류(서울)"

def get_coordinate_smart_jitter(store_name, base_lat, base_lon):
    if "반추" in str(store_name): return base_lat, base_lon
    hash_obj = hashlib.md5(str(store_name).encode())
    hash_int = int(hash_obj.hexdigest(), 16)
    random.seed(hash_int) 
    lat_offset = random.uniform(-0.003, 0.003)
    lon_offset = random.uniform(-0.003, 0.003)
    return base_lat + lat_offset, base_lon + lon_offset

def get_coordinate_priority(text, base_lat, base_lon):
    if pd.isna(text): return base_lat, base_lon
    text = str(text)
    for name, coords in NEIGHBORHOOD_COORDS.items():
        if name in text:
            return get_coordinate_smart_jitter(text, coords[0], coords[1])
    for name, coords in DISTRICT_CENTERS.items():
        if name in text:
            return get_coordinate_smart_jitter(text, coords[0], coords[1])
    return get_coordinate_smart_jitter(text, base_lat, base_lon)

def get_real_color(korean_color):
    if pd.isna(korean_color): return '#3388ff', '#000000'
    c = str(korean_color).lower()
    if '블랙' in c or 'black' in c: return '#000000', '#FFFFFF' 
    elif '화이트' in c or 'white' in c or '실버' in c: return '#FFFFFF', '#000000' 
    elif '그레이' in c or '티타늄' in c: return '#808080', '#000000' 
    elif '블루' in c: return '#0000FF', '#FFFFFF' 
    elif '핑크' in c: return '#FFC0CB', '#000000' 
    elif '그린' in c: return '#008000', '#FFFFFF' 
    elif '골드' in c or '옐로우' in c: return '#FFD700', '#000000' 
    elif '퍼플' in c: return '#800080', '#FFFFFF' 
    elif '레드' in c: return '#FF0000', '#FFFFFF' 
    return '#3388ff', '#000000'

@st.cache_data
def load_data_optimized(file):
    if isinstance(file, str): df = pd.read_excel(file, dtype=str)
    else: df = pd.read_excel(file, dtype=str)
    
    boyu_col = None
    for col in df.columns:
        if '보유처' in str(col):
            boyu_col = col
            break
            
    if boyu_col:
        df[boyu_col] = df[boyu_col].astype(str).str.strip()
        df.loc[df[boyu_col].str.contains("반추", na=False), boyu_col] = "반추정보통신"
        
        final_lats = []
        final_lons = []
        for _, row in df.iterrows():
            f_lat, f_lon = get_coordinate_priority(row[boyu_col], 37.5665, 126.9780)
            final_lats.append(f_lat)
            final_lons.append(f_lon)

        df['cached_lat'] = final_lats
        df['cached_lon'] = final_lons
        clean_names = df[boyu_col].str.replace(r'^[^-\s]*\d[^-\s]*-', '', regex=True)
        df['cached_region'] = clean_names.apply(get_region_category)
        df['cached_city'] = clean_names.apply(get_city_only)
        
    return df

if 'filtered_data' not in st.session_state: st.session_state['filtered_data'] = None
if 'selected_idx' not in st.session_state: st.session_state['selected_idx'] = None

# =========================================================
# 메인 UI
# =========================================================
DATA_FILE = 'inventory_data.xlsx'
META_FILE = 'file_info.txt' 

with st.expander("📂 데이터 업로드", expanded=True):
    c1, c2 = st.columns([8, 2])
    with c1: uploaded_file = st.file_uploader("엑셀 파일 업로드", type=["xlsx"])
    with c2:
        if st.button("🗑️ 초기화"):
            if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
            if os.path.exists(META_FILE): os.remove(META_FILE)
            st.session_state['filtered_data'] = None
            st.session_state['clicked_store_name'] = None
            st.cache_data.clear()
            st.rerun()

if uploaded_file:
    with open(DATA_FILE, "wb") as f: f.write(uploaded_file.getbuffer())
    with open(META_FILE, "w", encoding="utf-8") as f: f.write(uploaded_file.name)
    st.success("저장 완료")
    st.cache_data.clear()

df = None
if os.path.exists(DATA_FILE):
    try: df = load_data_optimized(DATA_FILE)
    except: st.error("파일 오류")

if df is not None:
    # 컬럼 매핑
    col_map = {}
    for col in df.columns:
        c = str(col).replace('▼', '').strip()
        if '보유처' in c: col_map['보유처'] = col
        elif '모델명' in c: col_map['모델명'] = col
        elif '색상' in c: col_map['색상'] = col
        elif any(k in c for k in ['재고', '상태', '등급']): col_map['status'] = col

    target_col = None
    if len(df.columns) >= 14: target_col = df.columns[13]
    if target_col is None:
        for col in df.columns:
            c = str(col).replace('▼', '').strip()
            if any(k in c for k in ['출고', '날짜']): target_col = col; break

    real_boyu = col_map.get('보유처')
    real_model = col_map.get('모델명', df.columns[0])
    real_color = col_map.get('색상', None)
    real_status = col_map.get('status', None)
    real_target = target_col

    with st.expander("🔍 검색 조건", expanded=True):
        r1, r2 = st.columns(2)
        with r1:
            # [수정] 모델 리스트 생성 로직 (그룹 + 개별)
            raw_models = df[real_model].unique().tolist()
            display_options = []
            grouped_items = []
            
            # 1. 그룹 추가
            for label, items in MODEL_GROUPS.items():
                if any(i in raw_models for i in items):
                    display_options.append(label)
                    grouped_items.extend(items)
            
            # 2. 나머지 개별 모델 추가 (그룹에 포함 안 된 것만)
            for m in raw_models:
                if m not in grouped_items:
                    display_options.append(m)
            
            display_options.sort()
            selected_models_display = st.multiselect("모델", display_options, default=[], placeholder="선택하세요")
            
            # [수정] 선택된 옵션을 실제 모델명 리스트로 변환
            selected_models = []
            for opt in selected_models_display:
                if opt in MODEL_GROUPS:
                    selected_models.extend(MODEL_GROUPS[opt])
                else:
                    selected_models.append(opt)

        with r2:
            all_owners = sorted(df[real_boyu].unique().tolist())
            selected_owners = st.multiselect("보유처", ["전체"] + all_owners, default=[], placeholder="미선택 시 전체")

        r3, r4, r5 = st.columns([3, 3, 2])
        with r3:
            if real_color:
                if selected_models:
                    f_m = df[df[real_model].isin(selected_models)]
                    av_c = sorted(f_m[real_color].unique().tolist())
                else: 
                    av_c = sorted(df[real_color].unique().tolist())
                selected_colors = st.multiselect("색상", av_c, default=[], placeholder="선택하세요")
            else: st.write("-")
        with r4:
            reg_ord = ["전체", "동남", "동북", "서남", "서북", "남부", "강원", "인천", "강변TM", "신도림TM"]
            selected_regions = st.multiselect("지역", reg_ord, default=[], placeholder="전체")
        with r5:
            st.write("")
            search_clicked = st.button("🚀 조회", type="primary", use_container_width=True)

    if search_clicked:
        if not selected_models and (not selected_owners or "전체" in selected_owners):
             st.warning("모델 또는 보유처를 선택해주세요.")
             st.session_state['filtered_data'] = None
        else:
            f_df = df.copy()
            if selected_models: f_df = f_df[f_df[real_model].isin(selected_models)]
            if selected_owners and "전체" not in selected_owners:
                f_df = f_df[f_df[real_boyu].isin(selected_owners)]
            if real_color and selected_colors:
                f_df = f_df[f_df[real_color].isin(selected_colors)]
            if selected_regions and "전체" not in selected_regions:
                f_df = f_df[f_df['cached_region'].isin(selected_regions)]
            
            f_df = f_df.sort_values(by=real_boyu, ascending=True)
            map_df = f_df[~f_df[real_boyu].astype(str).str.startswith('도매-', na=False)]
            st.session_state['filtered_data'] = {'list': f_df, 'map': map_df}
            st.session_state['selected_idx'] = None

    st.markdown("---")

    if st.session_state['filtered_data'] is not None:
        data = st.session_state['filtered_data']
        list_df = data['list']
        map_df = data['map']

        if not list_df.empty:
            left, right = st.columns([6, 4])

            # 리스트
            with right:
                st.subheader(f"📋 ({len(list_df)}건)")
                MAX = 100
                d_df = list_df.head(MAX) if len(list_df) > MAX else list_df
                sel_idx = st.session_state['selected_idx']
                
                with st.container(height=500):
                    for idx, row in d_df.iterrows():
                        c_info, c_btn = st.columns([8, 2])
                        bg = "background-color: #ffecec;" if sel_idx == idx else ""
                        with c_info:
                            nm = row[real_boyu]
                            det = f"{row[real_model]} | {row[real_color] if real_color else '-'} | {row[real_status] if real_status else '-'} | {row[real_target] if real_target else '-'}"
                            st.markdown(f"<div class='list-item-container' style='{bg}'>\
                                            <div class='list-title'>{nm}</div>\
                                            <div class='list-sub'>{det}</div>\
                                         </div>", unsafe_allow_html=True)
                        with c_btn:
                            if st.button("📍", key=f"b_{idx}"):
                                st.session_state['selected_idx'] = idx
                                st.rerun()
                        st.markdown("<div class='compact-hr'></div>", unsafe_allow_html=True)

            # 지도
            with left:
                sel_idx = st.session_state['selected_idx']
                
                if not map_df.empty:
                    min_lat = map_df['cached_lat'].min()
                    max_lat = map_df['cached_lat'].max()
                    min_lon = map_df['cached_lon'].min()
                    max_lon = map_df['cached_lon'].max()

                    c_lat = (min_lat + max_lat) / 2
                    c_lon = (min_lon + max_lon) / 2
                    
                    m = folium.Map(location=[c_lat, c_lon], zoom_start=10)
                    m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], max_zoom=12)
                    
                    if gesture_handling_available:
                        try: GestureHandling().add_to(m)
                        except: pass
                    
                    groups = map_df.groupby(['cached_lat', 'cached_lon', real_boyu])

                    for (lat, lon, name), g in groups:
                        u_cols = g[real_color].unique()
                        if len(u_cols) == 1:
                            c_name = u_cols[0]
                            hex_c, _ = get_real_color(c_name)
                            if hex_c.upper() == '#FFFFFF': bg_c, ic_c = "rgba(0,0,0,0.4)", "white"
                            else: bg_c, ic_c = "rgba(255,255,255,0.8)", hex_c
                        else: bg_c, ic_c = "rgba(128,0,128,0.8)", "white"

                        z = 1000 if sel_idx in g.index else 1
                        if sel_idx in g.index: bg_c, ic_c = "rgba(255,0,0,0.85)", "white"

                        t_rows = ""
                        counts = g.groupby([real_model, real_color, real_status]).size().reset_index(name='cnt')
                        for _, r in counts.iterrows():
                            cn = r[real_color] if real_color else "-"
                            stt = r[real_status] if real_status else "-"
                            qty = r['cnt']
                            t_rows += f"<tr><td>{r[real_model]}</td><td>{cn}</td><td>{stt}</td><td>{qty}</td></tr>"

                        # [팝업 개선] 글씨 11px, 중앙 정렬, 엑셀 격자, 너비 260px (모바일 최적화)
                        popup_html = f"""
                        <div style='width:100%; min-width:260px; font-family:sans-serif;'>
                            <div style='font-size:14px; font-weight:bold; color:#000; margin-bottom:5px; text-align:center;'>{name}</div>
                            <div style='font-size:11px; color:gray; margin-bottom:10px; text-align:center;'>{g['cached_region'].iloc[0]}</div>
                            
                            <table style='width:100%; border-collapse:collapse; font-size:11px;'>
                                <thead>
                                    <tr style='background-color:#f0f0f0;'>
                                        <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>모델</th>
                                        <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>색상</th>
                                        <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>상태</th>
                                        <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>수</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {t_rows.replace('<tr>', '<tr>').replace('<td>', "<td style='border:1px solid #000; padding:5px; text-align:center;'>")}
                                </tbody>
                            </table>
                            
                            <div style='text-align:right; font-size:11px; font-weight:bold; margin-top:10px;'>
                                총: {len(g)}대
                            </div>
                        </div>
                        """
                        
                        icon_html = f"""
                        <div style="
                            background-color: {bg_c};
                            color: {ic_c};
                            width: 20px;
                            height: 20px;
                            border-radius: 50%;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            font-size: 10px;
                            box-shadow: 1px 1px 3px rgba(0,0,0,0.3);">
                            <i class="fa fa-mobile"></i>
                        </div>
                        """
                        
                        folium.Marker(
                            location=[lat, lon],
                            icon=folium.DivIcon(html=icon_html),
                            popup=folium.Popup(popup_html, max_width=350),
                            z_index_offset=z
                        ).add_to(m)

                    st_folium(m, width="100%", height=450, returned_objects=[])

                else:
                    st.info("지도 데이터 없음")
        else:
            st.warning("데이터 없음")