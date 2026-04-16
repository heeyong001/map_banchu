import streamlit as st
import pandas as pd
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
from branca.element import Element  
import random
import os
import hashlib
import json
from streamlit_gsheets import GSheetsConnection
import urllib.request
import urllib.parse
import time
import json 
import base64
from io import BytesIO # [추가] 엑셀 다운로드를 위한 메모리 버퍼
from datetime import datetime # [추가] 로그 시간 기록용
from streamlit_gsheets import GSheetsConnection  # [추가] 구글 시트 연결 라이브러리

# ... (기존 NAVER API 세팅 및 함수 유지) ...

# ==============================================================================
# [1단계] 로컬 DB(SQLite) 초기 세팅 및 암호화 함수
# ==============================================================================
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

from streamlit_gsheets import GSheetsConnection

# ⚠️ 본인의 구글 시트 주소 ID로 반드시 변경하세요!
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1MtU3hxtUHLS3zT6NoOdsJe-yxJ2tETwfju_hi15U9vI/edit#gid=0"

@st.cache_resource
def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def load_sheet(sheet_name, ttl="5m"):
    conn = get_gsheets_connection()
    return conn.read(spreadsheet=GSHEET_URL, worksheet=sheet_name, ttl=ttl)

def save_sheet(df, sheet_name):
    conn = get_gsheets_connection()
    conn.update(spreadsheet=GSHEET_URL, worksheet=sheet_name, data=df)
    st.cache_data.clear()

def add_audit_log(username, action, details=""):
    import threading
    def _write():
        try:
            log_df = load_sheet("logs", ttl=0)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([{"발생시간": now, "작업자": username, "작업유형": action, "상세내역": details}])
            updated_log = pd.concat([log_df, new_row], ignore_index=True)
            save_sheet(updated_log, "logs")
        except:
            pass
    threading.Thread(target=_write, daemon=True).start()

# ==============================================================================
# [1번 과제 적용] 네이버 Geocoding API를 이용한 초고속 좌표 변환 함수
# ==============================================================================
# ⚠️ 여기에 네이버 클라우드에서 발급받은 본인의 키를 넣어주세요!
NAVER_CLIENT_ID = "iy4cjaxysr"
NAVER_CLIENT_SECRET = "3YMTgkDxS95RZL8byz6Bbc2lZhijO2vaoHUept5M"

# [핵심] 기존 x, y 좌표를 받아서, 있으면 API 안 부르고 바로 반환!
def get_lat_lon(address, existing_x=None, existing_y=None):
    # 1. [과금 방어] 이미 좌표가 있다면 API를 절대 호출하지 않음!
    if pd.notna(existing_x) and pd.notna(existing_y) and str(existing_x).strip() != "" and str(existing_x).lower() != "nan":
        return float(existing_y), float(existing_x)
        
    # 2. 좌표가 없을 때만 네이버 API 호출
    if not address or pd.isna(address) or str(address).strip() == "":
        return None, None
        
    try:
        enc_address = urllib.parse.quote(str(address).strip())
        url = f"https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query={enc_address}"
        request = urllib.request.Request(url)
        request.add_header("X-NCP-APIGW-API-KEY-ID", NAVER_CLIENT_ID)
        request.add_header("X-NCP-APIGW-API-KEY", NAVER_CLIENT_SECRET)
        response = urllib.request.urlopen(request)
        if response.getcode() == 200:
            data = json.loads(response.read())
            if data['addresses']:
                return float(data['addresses'][0]['y']), float(data['addresses'][0]['x'])
        return None, None
    except Exception as e:  # 👈 [핵심] 이 부분을 명확하게 변경하여 에러 원천 차단
        return None, None
        
# [기능 추가] 모바일 제스처 처리를 위한 플러그인 확인
try:
    from folium.plugins import GestureHandling
    gesture_handling_available = True
except ImportError:
    gesture_handling_available = False

# 1. 화면 설정
st.set_page_config(layout="wide", page_title="재고 현황 대시보드", initial_sidebar_state="collapsed")

# ==============================================================================
# [마스터 디자인] 전역 다크/골드 테마 CSS (여기에만 존재해야 합니다!)
# ==============================================================================
st.markdown("""
    <style>
    /* 1. 전역 다크 그린 격자 배경 */
    .stApp {
        background-color: #122820 !important;
        background-image: 
            linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px) !important;
        background-size: 40px 40px !important;
    }
    header[data-testid="stHeader"] { background-color: transparent !important; }
    .block-container { padding-top: 3.5rem !important; padding-bottom: 3rem !important; }
            
            /* [핵심] 가로선(---) 디자인: 금색 그라데이션 */
    hr {
        border: 0 !important;
        height: 2px !important;
        background-color: rgba(212, 175, 55, 0.2) !important; /* 금색에 투명도 20%를 적용하여 배경에 스며들게 함 */
        margin: 1rem 0 !important;
    }

    /* 2. 전역 텍스트 밝은 색상으로 통일 */
    .stMarkdown, .stText, p, span, label, h1, h2, h3, h4, h5, h6, li, div[data-testid="stMarkdownContainer"] {
        color: #E5E9F0 !important;
    }

    /* 3. 사이드바 다크 테마 */
    section[data-testid="stSidebar"] { 
        background-color: #0A1712 !important; 
        border-right: 1px solid #3A5A4A !important;
    }
        
    /* 🚀 [추가] 사이드바 구분선(---)과 아래 메뉴(라디오 버튼) 사이의 간격 넓히기 */
    section[data-testid="stSidebar"] hr {
        margin-bottom: 35px !important; /* 👈 이 숫자를 늘리면 아래쪽 간격이 더 넓어집니다! (기본값은 약 16px) */
    }
    
    /* 혹시 라디오 버튼 위쪽 여백을 더 밀고 싶다면 아래 코드도 적용됩니다 */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] {
        margin-top: 10px !important;
    }
    /* 4. 파일 업로더 (하얀 박스 완벽 철거) */
    [data-testid="stFileUploader"] div,
    [data-testid="stFileUploader"] section {
        background-color: #182C24 !important;
    }
            
    /* 🚀 [추가] 파일 업로더 안의 "Browse files" 버튼 전용 블랙&골드 스타일 */
    [data-testid="stFileUploader"] button {
        background-color: #000000 !important; /* 배경 검정 */
        color: #D4AF37 !important;           /* 글자 금색 */
        border: 1px solid #D4AF37 !important; /* 얇은 금색 테두리 */
        border-radius: 8px !important;
        font-weight: bold !important;
    }

    /* 마우스 올렸을 때 효과 */
    [data-testid="stFileUploader"] button:hover {
        background-color: #1a1a1a !important; 
        color: #FCECA1 !important;           /* 더 밝은 금색 */
        border-color: #FCECA1 !important;
        box-shadow: 0 0 10px rgba(212, 175, 55, 0.5) !important;
    }

    /* 클릭 시 다시 하얘지는 현상 방지 */
    [data-testid="stFileUploader"] button:focus,
    [data-testid="stFileUploader"] button:active {
        background-color: #000000 !important;
        color: #D4AF37 !important;
        border-color: #D4AF37 !important;
    }        

    [data-testid="stFileUploadDropzone"] {
        background-color: #182C24 !important;
        border: 2px dashed #728A7C !important;
        border-radius: 8px !important;
        padding: 20px !important;
    }
    [data-testid="stFileUploadDropzone"]:hover {
        border-color: #D4AF37 !important; 
        background-color: #24362E !important;
    }
    [data-testid="stFileUploadDropzone"] * { color: #E5E9F0 !important; }
    [data-testid="stFileUploadDropzone"] svg { fill: #E5E9F0 !important; }

    /* 5. 입력창 및 드롭다운 팝업창 */
    div[data-baseweb="select"] > div, 
    div[data-baseweb="base-input"] > input,
    div[data-testid="stTextInput"] input {
        background-color: #0A1712 !important; 
        color: #E5E9F0 !important; 
        border: 1px solid #3A5A4A !important;
        border-radius: 8px !important;
    }

    /* 검색창에 직접 타이핑하는 글씨 (선명한 흰색) */
    div[data-baseweb="select"] input {
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* [핵심 수정] 타이핑 전 안내문구(Placeholder)를 밝고 선명한 색상으로 변경 */
    input::placeholder, textarea::placeholder { 
        color: #A9BDB2 !important; /* 어두운 회색에서 밝은 파스텔 회녹색으로 변경 */
        opacity: 1 !important; /* 브라우저 기본 투명도 방지 */
    }
    
    /* 드롭다운의 "선택하세요" 등 미선택 안내문구 밝게 처리 */
    div[data-baseweb="select"] > div > div > div {
        color: #A9BDB2 !important;
    }

    /* 드롭다운 팝업창 ("No results" 하얀 박스 완벽 제압) */
    div[data-baseweb="popover"] > div,
    div[data-baseweb="popover"] > div > div,
    div[data-baseweb="popover"] ul {
        background-color: #182C24 !important;
    }
    
    ul[data-testid="stVirtualDropdown"], 
    ul[role="listbox"], 
    div[role="listbox"] {
        background-color: #182C24 !important;
        border: 1px solid #3A5A4A !important;
        padding: 0 !important;
    }

    /* "No results" 안내 텍스트 색상 */
    div[role="listbox"] span, div[role="listbox"] div {
        color: #E5E9F0 !important;
    }

    /* 팝업창 리스트 항목 */
    li[role="option"] {
        background-color: #182C24 !important;
        color: #E5E9F0 !important;
    }
    
    li[role="option"]:hover, 
    li[role="option"][aria-selected="true"] {
        background-color: #2D4A3E !important;
        color: #D4AF37 !important;
    }
    
    /* 선택된 태그(멀티셀렉트) */
    span[data-baseweb="tag"] { 
        background-color: #2D4A3E !important; color: #E8D5A5 !important; border: 1px solid #D4AF37 !important; 
    }

    /* 6. [최종 수정] 배경색이 흰색으로 돌아가지 않도록 강제 고정 */
    div.stButton > button, 
    div[data-testid="stFormSubmitButton"] > button,
    button[data-testid="stFormSubmitButton"] {
        background-color: #000000 !important; 
        color: #D4AF37 !important;           
        border: 1px solid #D4AF37 !important; 
        border-radius: 10px !important;
        font-weight: bold !important;
        width: 100% !important;              
        
        /* 🚀 [검색결과 박스 깨짐 해결] 높이 자동 조절 및 줄바꿈 최적화 */
        height: auto !important;         /* 👈 글자 길이에 맞춰 높이가 자동으로 늘어남 */
        min-height: 2em !important;      /* 👈 글자가 짧아도 최소한의 높이는 보장 */
        white-space: normal !important;  /* 👈 텍스트가 길면 박스를 뚫지 않고 아래로 줄바꿈 */
        word-break: keep-all !important; /* 👈 단어 중간에 어색하게 잘리지 않도록 보호 */
        line-height: 1.6 !important;     /* 👈 두 줄이 되었을 때 글자 위아래 간격 확보 */
        padding: 12px 15px !important;   /* 👈 상하좌우 여백을 줘서 텍스트가 테두리에 닿지 않게 함 */
        
        display: block !important;
    }

    /* 마우스 올렸을 때 (Hover) */
    div.stButton > button:hover, 
    button[data-testid="stFormSubmitButton"]:hover {
        background-color: #1a1a1a !important; /* 아주 진한 회색(검정에 가까움) */
        color: #FCECA1 !important;           /* 더 밝은 금색 */
        border-color: #FCECA1 !important;
        box-shadow: 0 0 10px rgba(212, 175, 55, 0.5) !important;
    }

    /* 클릭 시 또는 포커스 시 흰색으로 변하는 것 방지 */
    div.stButton > button:focus, 
    div.stButton > button:active {
        background-color: #000000 !important;
        color: #D4AF37 !important;
        border-color: #D4AF37 !important;
    }

    /* 7. 로그인 화면 전용 스타일 */
    .title-text { color: #E8D5A5; font-size: 32px; font-weight: bold; text-align: center; margin-top: 10px; margin-bottom: 10px; letter-spacing: 1px; }
    .subtitle-text { color: #728A7C; font-size: 14px; text-align: center; margin-bottom: 35px; }
    .logo-container { display: flex; justify-content: center; margin-bottom: -10px; }
    .logo-container img { max-width: 180px; height: auto; }
    div[data-testid="stForm"] {
        background-color: #182C24 !important; border: 1px solid #736343 !important;
        box-shadow: 0 0 25px rgba(212, 175, 55, 0.15) !important; border-radius: 12px !important; padding: 30px !important;
    }

    /* 8. 메인 대시보드 UI */
    .search-container {
        background-color: rgba(24, 44, 36, 0.8) !important; border: 1px solid #3A5A4A !important;
        padding: 15px; border-radius: 15px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3); margin-bottom: 15px;
    }
    .file-status-bar {
        background-color: #182C24 !important; border: 1px solid #3A5A4A !important; color: #D4AF37 !important;
        padding: 10px 15px; border-radius: 8px; font-size: 14px; font-weight: bold; margin-bottom: 15px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div.stButton > button {
        background: #0A1712 !important; color: #E5E9F0 !important; border: none !important;
        border-bottom: 1px solid #2D4A3E !important; border-left: 4px solid #728A7C !important; 
        border-radius: 0px !important; text-align: left !important; box-shadow: none !important;
        padding: 6px 8px !important; margin-bottom: 1px !important; height: auto !important; display: block !important; font-size: 13px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] div.stButton > button:active,
    div[data-testid="stVerticalBlockBorderWrapper"] div.stButton > button:hover {
        background-color: #182C24 !important; border-left-color: #D4AF37 !important; color: #E8D5A5 !important; box-shadow: none !important;
    }
    div[data-testid="stDataEditor"], div[data-testid="stDataFrame"] { background-color: #182C24 !important; border: 1px solid #3A5A4A !important; 
    }
            
    /* 🚀 [최종 잔상 박멸] 어떤 버전이든 이전 화면(stale)을 즉시 삭제 및 투명화 */
    *[data-stale="true"] {
        opacity: 0 !important;
        display: none !important;
        transition: none !important;
        pointer-events: none !important;
    }
    
    div[data-testid="stAppViewContainer"] > div:first-child {
        opacity: 1 !important;
    }
            /* 🚀 [추가] 다운로드 버튼 전용 블랙&골드 스타일 */
    [data-testid="stDownloadButton"] button {
        background-color: #000000 !important; /* 배경 검정 */
        color: #D4AF37 !important;           /* 글자 금색 */
        border: 1px solid #D4AF37 !important; /* 얇은 금색 테두리 */
        border-radius: 8px !important;
        font-weight: bold !important;
    }

    /* 마우스 올렸을 때 효과 */
    [data-testid="stDownloadButton"] button:hover {
        background-color: #1a1a1a !important; 
        color: #FCECA1 !important;           /* 더 밝은 금색 */
        border-color: #FCECA1 !important;
        box-shadow: 0 0 10px rgba(212, 175, 55, 0.5) !important;
    }

    /* 클릭 시 다시 하얘지는 현상 방지 */
    [data-testid="stDownloadButton"] button:focus,
    [data-testid="stDownloadButton"] button:active {
        background-color: #000000 !important;
        color: #D4AF37 !important;
        border-color: #D4AF37 !important;
    }

    /* 🚀 [수정] 조회하기 버튼 전용 세로 크기 조절 (이정표 기법) */
    
    /* 1. 이정표 영역 자체는 화면에서 완전히 숨김 (빈 공간 방지) */
    div[data-testid="stElementContainer"]:has(.search-btn-marker),
    div.element-container:has(.search-btn-marker) {
        display: none !important; 
    }

    /* 2. 이정표(marker)의 '바로 다음 컨테이너'에 들어있는 버튼 타겟팅 */
    div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button,
    div.element-container:has(.search-btn-marker) + div button {
        height: 20px !important;         /* 👈 여기서 세로 길이를 조절하세요 (예: 60px, 80px) */
        min-height: 40px !important;
        font-size: 18px !important;      /* 👈 글자 크기도 시원하게 키울 수 있습니다 */
        padding: 5px 15px !important;
    }
            
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# [1단계] 로컬 DB(SQLite) 초기 세팅 및 암호화 함수
# ==============================================================================
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return True
    return False

# ==============================================================================
# [중요] 세션 상태 초기화 & 새로고침 로그인 유지 (URL 보안 토큰 방식 적용)
# ==============================================================================
# 1. 기본 상태 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.session_state['role'] = ""

# 2. 새로고침 시 URL 토큰 복구 로직
if not st.session_state['logged_in']:
    auth_token = st.query_params.get("auth_token")
    if auth_token:
        try:
            users_df = load_sheet("users", ttl="10m")
            if not users_df.empty:
                matched_user = users_df[users_df['password'] == auth_token]
                if not matched_user.empty:
                    user_data = matched_user.iloc[0]
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = user_data['username']
                    # 'role'을 쓰셨다면 'user_role'로 통일하거나 맞춰서 사용하세요
                    st.session_state['role'] = user_data['role'] 
                    st.rerun()
        except:
            pass

# --- 아래 변수들은 대시보드 작동에 필수이므로 그대로 유지! ---
if 'filtered_data' not in st.session_state: st.session_state['filtered_data'] = None
if 'selected_idx' not in st.session_state: st.session_state['selected_idx'] = None
if 'clicked_store_name' not in st.session_state: st.session_state['clicked_store_name'] = None
if 'search_clicked' not in st.session_state: st.session_state['search_clicked'] = False

# ==============================================================================
# [2단계] 로그인 화면 및 화면 라우팅
# ==============================================================================
if not st.session_state['logged_in']:
    _, col_center, _ = st.columns([1, 1.2, 1])
    
    with col_center:
        try:
            with open("logo.png", "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
            st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{encoded_string}"></div>', unsafe_allow_html=True)
        except FileNotFoundError:
            st.markdown('<div class="logo-container"><span style="color:red; font-size:12px;">logo.png 파일이 없습니다</span></div>', unsafe_allow_html=True)

        st.markdown('<div class="title-text">반추 재고 통합시스템</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle-text">관리자 및 허가된 사원만 접근 가능합니다.</div>', unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("👤 아이디", placeholder="아이디를 입력하세요")
            password = st.text_input("🔑 비밀번호", type="password", placeholder="비밀번호를 입력하세요")
            
            submit_button = st.form_submit_button("로그인", use_container_width=True)

            if submit_button:
                if username and password:
                    try:
                        users_df = load_sheet("users", ttl="10m")
                        user_match = users_df[users_df['username'] == username]
                        
                        if not user_match.empty and check_hashes(password, user_match.iloc[0]['password']):
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = username
                            st.session_state['role'] = user_match.iloc[0]['role']
                            # 🚀 [추가됨] 로그인 성공 시 URL에 토큰 기록
                            st.query_params["auth_token"] = user_match.iloc[0]['password']
                            st.rerun()
                        else:
                            st.error("⚠️ 아이디 또는 비밀번호가 일치하지 않습니다.")
                    except Exception as e:
                        st.error(f"⚠️ 구글 시트를 읽을 수 없습니다: {e}")
                else:
                    st.warning("⚠️ 모든 항목을 입력해주세요.")
                    
    st.stop()

# --- 로그인 성공 시 나타나는 사이드바 메뉴 ---
with st.sidebar:
    st.success(f"👤 **{st.session_state['username']}**님 접속중")
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.clear()
        # [추가] 로그아웃 시 URL 파라미터 깔끔하게 삭제
        st.query_params.clear()
        st.rerun()
    st.markdown("---")

    menu = ["📊 대시보드"]
    # 관리자 권한(admin)일 때만 관리자 설정 메뉴가 보입니다.
    if st.session_state['role'] == 'admin':
        menu.append("⚙️ 관리자 설정")

    app_mode = st.radio("메뉴 이동", menu)

# ==============================================================================
# [3단계] 메인 화면 라우팅 (대시보드 / 관리자 설정)
# ==============================================================================
# 🚀 [수정] session_state에 저장하지 않고 매번 신선한 도화지만 깔아줍니다!
main_container = st.empty()

with main_container.container():
    if app_mode == "⚙️ 관리자 설정":
        st.markdown("## ⚙️ 관리자 설정 대시보드")
        
        tab1, tab2, tab3, tab4 = st.tabs(["👥 계정 및 권한 관리", "🏢 보유처 주소록 DB 관리", "⚠️ 미매칭 보유처 확인", "🕒 시스템 변경 이력 (Log)"])
    
        # ---------------------------------------------------------
        # 탭 1: 계정 관리
        # ---------------------------------------------------------
        with tab1:
            users_df = load_sheet("users", ttl=0)
            
            # 🚀 [추가] 현재 등록된 계정 목록을 상단에 깔끔하게 표로 출력
            st.markdown("#### 📋 현재 등록된 계정 목록")
            if not users_df.empty and 'username' in users_df.columns:
                # 비밀번호는 숨기고 아이디와 권한만 복사해서 표시
                display_df = users_df[['username', 'role']].copy()
                display_df.columns = ['👤 아이디', '🔑 권한 (admin/user)']
                
                # 표 형태로 출력 (가로 꽉 차게, 인덱스 번호는 숨김)
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("등록된 계정이 없습니다.")
                
            st.markdown("---") # 👈 목록과 수정 폼 사이에 구분선 추가
            
            col_new, col_edit = st.columns(2)
            
            with col_new:
                st.markdown("#### ➕ 신규 계정 생성")
                with st.container(border=True):
                    with st.form("create_account_form"):
                        new_user = st.text_input("새 아이디")
                        new_password = st.text_input("새 비밀번호", type="password")
                        new_role = st.selectbox("권한", ["user", "admin"])
                        if st.form_submit_button("계정 생성", use_container_width=True):
                            if new_user and new_password:
                                if not users_df.empty and new_user in users_df['username'].values:
                                    st.error("⚠️ 이미 존재하는 아이디입니다.")
                                else:
                                    new_row = pd.DataFrame([{"username": new_user, "password": make_hashes(new_password), "role": new_role}])
                                    updated_users = pd.concat([users_df, new_row], ignore_index=True)
                                    save_sheet(updated_users, "users")
                                    add_audit_log(st.session_state['username'], "계정 생성", f"신규 계정 '{new_user}' ({new_role}) 생성")
                                    st.success(f"✅ '{new_user}' 계정 생성 완료!")
                                    st.rerun()
                            else: st.warning("항목을 모두 입력해주세요.")
            
            with col_edit:
                st.markdown("#### 🔄 계정 정보 수정 (비밀번호/권한)")
                with st.container(border=True):
                    user_list = users_df['username'].tolist() if not users_df.empty else []
                    target_user = st.selectbox("수정할 아이디 선택", user_list)
                    new_pw_reset = st.text_input("새 비밀번호 (변경시에만 입력)", type="password", placeholder="빈칸으로 두면 기존 비밀번호 유지")
                    new_role_edit = st.selectbox("새 권한", ["user", "admin"], key="role_edit")
                    
                    col_btn1, col_btn2 = st.columns(2)
                    if col_btn1.button("💾 정보 수정", use_container_width=True, type="primary") and target_user:
                        idx = users_df.index[users_df['username'] == target_user].tolist()[0]
                        if new_pw_reset:
                            users_df.at[idx, 'password'] = make_hashes(new_pw_reset)
                            users_df.at[idx, 'role'] = new_role_edit
                            add_audit_log(st.session_state['username'], "계정 수정", f"'{target_user}' 비밀번호 및 권한({new_role_edit}) 변경")
                        else:
                            users_df.at[idx, 'role'] = new_role_edit
                            add_audit_log(st.session_state['username'], "계정 수정", f"'{target_user}' 권한({new_role_edit}) 변경")
                        save_sheet(users_df, "users")
                        st.success(f"✅ '{target_user}' 계정 정보가 수정되었습니다.")
                        st.rerun()
                        
                    if col_btn2.button("🗑️ 계정 삭제", use_container_width=True) and target_user:
                        if target_user == "admin": st.error("최고 관리자(admin)는 삭제할 수 없습니다.")
                        else:
                            users_df = users_df[users_df['username'] != target_user]
                            save_sheet(users_df, "users")
                            add_audit_log(st.session_state['username'], "계정 삭제", f"'{target_user}' 계정 삭제됨")
                            st.success(f"✅ '{target_user}' 계정이 삭제되었습니다.")
                            st.rerun()

        # ---------------------------------------------------------
        # 탭 2: 보유처 관리
        # ---------------------------------------------------------
        with tab2:
            import numpy as np
            
            # 툴바 디자인 유지
            st.markdown("""
                <style>
                div[data-testid="stElementToolbar"] { opacity: 1 !important; visibility: visible !important; display: flex !important; transform: scale(1.2) !important; border: none !important; background-color: transparent !important; position: absolute !important; right: 10px !important; top: -45px !important; z-index: 1000 !important; }
                div[data-testid="stElementToolbar"] button svg { stroke-width: 3px !important; color: #262730 !important; }
                </style>
            """, unsafe_allow_html=True)

            all_data_df = load_sheet("stores", ttl=0)
            
            c1, c2 = st.columns([7, 3])
            with c1: st.markdown(f"#### 🏢 보유처 주소록 DB 관리 (총 {len(all_data_df)}개)")
            with c2:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer: all_data_df.to_excel(writer, index=False, sheet_name='stores_DB')
                st.download_button(label="📥 주소록 전체 다운로드 (Excel)", data=output.getvalue(), file_name=f"주소록_전체_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            # ---------------------------------------------------------
            # [핵심] 🚀 관리자 전용 누락 좌표 채우기 버튼 (API 호출)
            # ---------------------------------------------------------
            st.markdown("---")
            st.markdown("##### 🚀 누락된 매장 좌표 일괄 생성 (API 호출)")
            st.info("💡 대량 업로드 등으로 'x좌표/y좌표'가 빈칸인 매장이 있을 때만 눌러주세요. 빈칸인 매장만 쏙쏙 골라서 네이버 지도로 좌표를 채워줍니다.")
            
            if st.button("⚡ 빈칸 좌표만 골라서 일괄 생성 (클릭)", type="primary", use_container_width=True):
                with st.spinner("좌표가 없는 매장을 찾아 API를 호출 중입니다..."):
                    opt_df = all_data_df.copy()
                    api_call_count = 0
                    
                    # 오직 '주소가 있는데 좌표가 비어있는 경우'에만 API 호출!
                    for idx, row in opt_df.iterrows():
                        addr = str(row.get('사업장주소', ''))
                        if pd.notna(addr) and addr.strip() != "" and (not row.get('x좌표') or not row.get('y좌표') or str(row.get('x좌표')).lower() == 'nan'):
                            n_lat, n_lon = get_lat_lon(addr)
                            if n_lat:
                                opt_df.at[idx, 'y좌표'] = str(n_lat)
                                opt_df.at[idx, 'x좌표'] = str(n_lon)
                                api_call_count += 1
                    
                    if api_call_count > 0:
                        save_sheet(opt_df, "stores")
                        add_audit_log(st.session_state['username'], "DB 좌표 보정", f"총 {api_call_count}건 누락 좌표 생성")
                        st.success(f"🎉 완벽합니다! 좌표가 비어있던 {api_call_count}개 매장의 위경도를 성공적으로 채웠습니다.")
                    else:
                        st.info("👍 모든 매장의 좌표가 이미 꽉 채워져 있습니다! (API 호출 0건)")
                    time.sleep(1.5)
                    st.rerun()

            # ---------------------------------------------------------
            # 대량 등록 및 개별 수정 폼 
            # ---------------------------------------------------------
            st.markdown("---")
            with st.expander("📥 엑셀 파일로 주소록 대량 등록 (클릭하여 열기)"):
                st.info("💡 엑셀 파일 첫 번째 줄(헤더)에 반드시 **접점코드, 보유처명, 사업장주소** 관련 컬럼이 있어야 합니다.")
                bulk_file = st.file_uploader("주소록 엑셀 업로드", type=["xlsx", "xls"], key="bulk_upload_addr")
                
                if bulk_file:
                    bulk_df = pd.read_excel(bulk_file, dtype=str)
                    bulk_df.columns = bulk_df.columns.astype(str).str.replace('▼', '').str.strip()
                    col_mapping = {}
                    for col in bulk_df.columns:
                        if '접점' in col: col_mapping[col] = '접점코드'
                        elif '보유처' in col: col_mapping[col] = '보유처명'
                        elif '주소' in col: col_mapping[col] = '사업장주소'
                    bulk_df.rename(columns=col_mapping, inplace=True)
                    
                    st.write("👀 데이터 미리보기 (최대 5건):")
                    st.dataframe(bulk_df.head(5), use_container_width=True)
                    
                    if st.button("💾 위 데이터를 DB에 일괄 추가/업데이트", type="primary"):
                        with st.spinner("구글 시트에 1차 저장 중... (저장 후 꼭 최적화 버튼을 눌러주세요)"):
                            req_cols = ['접점코드', '보유처명']
                            if not all(col in bulk_df.columns for col in req_cols):
                                st.error(f"⚠️ 엑셀에서 필수 컬럼을 찾지 못했습니다.")
                            else:
                                for col in ['x좌표', 'y좌표']:
                                    if col not in bulk_df.columns: bulk_df[col] = ""
                                bulk_df['접점코드'] = bulk_df['접점코드'].astype(str).str.strip()
                                bulk_df.set_index('접점코드', inplace=True)
                                
                                temp_all = all_data_df.copy()
                                if not temp_all.empty and '접점코드' in temp_all.columns:
                                    temp_all['접점코드'] = temp_all['접점코드'].astype(str).str.strip()
                                    temp_all.set_index('접점코드', inplace=True)
                                    temp_all.update(bulk_df)
                                    new_data = bulk_df[~bulk_df.index.isin(temp_all.index)]
                                    updated_all = pd.concat([temp_all, new_data]).reset_index()
                                else: updated_all = bulk_df.reset_index()
                                
                                save_sheet(updated_all, "stores")
                                st.success(f"✅ 일괄 저장이 완료되었습니다. 위쪽의 [전체 최적화] 버튼을 한 번 눌러주세요!")
                                st.rerun()

            st.markdown("---")
            edited_df = st.data_editor(all_data_df, num_rows="dynamic", use_container_width=True, height=400, key="bulk_editor_v3")
            if st.button("💾 위 표의 모든 변경사항 일괄 저장", use_container_width=True):
                save_sheet(edited_df, "stores")
                st.success("✅ 저장이 완료되었습니다. 위쪽의 [전체 최적화] 버튼을 한 번 눌러주세요!")
                st.rerun()

        # ---------------------------------------------------------
        # 탭 3: 미매칭 보유처 확인
        # ---------------------------------------------------------
        with tab3:
            st.markdown("#### ⚠️ 미매칭 보유처 확인")
            st.caption("현재 엑셀 데이터 중 주소록(DB)과 매칭되지 않아 지도에 위치표시가 정확하지 않은 목록입니다.")

            DATA_FILE = 'inventory_data.xlsx'
            
            if os.path.exists(DATA_FILE):
                try:
                    raw_df = pd.read_excel(DATA_FILE, dtype=str)
                    db_df = load_sheet("stores", ttl="5m")
                    
                    boyu_col = next((c for c in raw_df.columns if '보유처' in str(c).replace('▼','').strip()), None)
                    code_col = next((c for c in raw_df.columns if any(k in str(c) for k in ['접점번호', '접점코드'])), None)
                    
                    if boyu_col and code_col:
                        raw_unique = raw_df[~raw_df[boyu_col].astype(str).str.contains("반추", na=False)].drop_duplicates(subset=[boyu_col]).copy()
                        
                        def get_unmatch_reason(row):
                            code = str(row[code_col]).strip()
                            match = db_df[db_df['접점코드'].astype(str).str.strip() == code]
                            if match.empty: return "❌ 주소록 DB에 등록되지 않은 접점코드입니다."
                            m_row = match.iloc[0]
                            addr = str(m_row.get('사업장주소', '')).strip()
                            if not addr or addr.lower() == 'nan' or addr == "": return "📍 DB에 등록은 되어있으나 주소 정보가 누락되었습니다."
                            if not m_row.get('x좌표') or not m_row.get('y좌표'): return "🌐 주소는 있으나 좌표(위경도) 생성에 실패한 매장입니다."
                            return None 

                        raw_unique['미매칭 사유'] = raw_unique.apply(get_unmatch_reason, axis=1)
                        unmapped_display = raw_unique[raw_unique['미매칭 사유'].notna()].copy()

                        if not unmapped_display.empty:
                            st.warning(f"총 **{len(unmapped_display)}**건의 미매칭 데이터가 발견되었습니다.")
                            final_cols = [boyu_col, '미매칭 사유']
                            if '대분류' in unmapped_display.columns: final_cols.append('대분류')
                            
                            st.dataframe(unmapped_display[final_cols], use_container_width=True, hide_index=True)
                            
                            # [회원님 원본 복원] 미매칭 목록 다운로드 버튼
                            output = BytesIO()
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                unmapped_display[final_cols].to_excel(writer, index=False, sheet_name='미매칭_사유_목록')
                            st.download_button(
                                label="📥 미매칭 사유 목록 다운로드 (Excel)",
                                data=output.getvalue(),
                                file_name=f"미매칭사유_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        else: st.success("🎉 모든 데이터가 주소록 DB와 완벽하게 매칭되어 있습니다!")
                    else: st.error("엑셀 파일에서 '보유처' 또는 '접점코드' 컬럼을 식별할 수 없습니다.")
                except Exception as e: st.error(f"데이터 분석 중 오류 발생: {e}")
            else: st.warning("📂 먼저 메인 화면에서 재고 엑셀 파일을 업로드해주세요.")

        # ---------------------------------------------------------
        # 탭 4: 시스템 변경 이력 (Audit Log)
        # ---------------------------------------------------------
        with tab4:
            st.markdown("#### 🕒 관리자 작업 이력")
            st.caption("누가, 언제, 어떤 작업을 수행했는지 확인합니다. (최근 100건)")
            
            try:
                log_df = load_sheet("logs", ttl=0)
                if not log_df.empty:
                    # [회원님 원본 복원] 컬럼명 유지 및 역순 정렬
                    log_df = log_df.sort_values(by="발생시간", ascending=False).head(100)
                    st.dataframe(log_df, use_container_width=True, hide_index=True)
                else:
                    st.warning("아직 기록된 로그가 없거나 데이터베이스를 불러올 수 없습니다.")
            except Exception as e:
                st.warning("아직 기록된 로그가 없거나 데이터베이스를 불러올 수 없습니다.")
        
    # 🚀 여기서부터 대시보드 로직 시작 (elif 추가)
    elif app_mode == "📊 대시보드":

        # ==============================================================================
        # 2. 데이터 사전
        # ==============================================================================

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
            "일산": [37.6584, 126.8320]
        }

        NEIGHBORHOOD_COORDS = {
            # [수정] 사무실(반추) 좌표 영등포구 에이스하이테크로 업데이트
            "반추": [37.5144447, 126.8987734], "반추정보통신": [37.5144447, 126.8987734],
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
            "수유": [37.6370, 127.0250], "창동": [37.6530, 127.0470], "서부물류": [37.5113, 126.8373],
            "장항": [37.6629, 126.7697],"봉일":[37.7436, 126.8069],"광탄":[37.7975,126.8480]
        }

        def get_region_category(text):
            if pd.isna(text): return "기타"
            text = str(text).strip()
            best_match = None
            best_idx = len(text)
            for key in ["강변TM", "신도림TM", "동남", "동북", "서남", "서북", "남부", "강원", "인천"]:
                idx = text.find(key)
                if idx != -1 and idx < best_idx: 
                    best_idx = idx
                    best_match = key
            return best_match if best_match else "기타"

        def get_city_only(text):
            if pd.isna(text): return "미분류(서울)"
            text = str(text)
            best_match = None
            best_idx = len(text)
            
            for dong in NEIGHBORHOOD_COORDS.keys():
                idx = text.find(dong)
                if idx != -1 and idx < best_idx:
                    best_idx = idx
                    best_match = dong
                    
            for dist in DISTRICT_CENTERS.keys():
                idx = text.find(dist)
                if idx != -1 and idx < best_idx:
                    best_idx = idx
                    best_match = dist
                    
            return best_match if best_match else "미분류(서울)"

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
            best_coords = None
            best_idx = len(text)
            
            for name, coords in NEIGHBORHOOD_COORDS.items():
                idx = text.find(name)
                if idx != -1 and idx < best_idx:
                    best_idx = idx
                    best_coords = coords
                    
            for name, coords in DISTRICT_CENTERS.items():
                idx = text.find(name)
                if idx != -1 and idx < best_idx:
                    best_idx = idx
                    best_coords = coords
                    
            if best_coords is not None:
                return get_coordinate_smart_jitter(text, best_coords[0], best_coords[1])
                
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
            elif '퍼플' in c or '바이올렛' in c or 'violet' in c: return '#800080', '#FFFFFF'
            elif '레드' in c: return '#FF0000', '#FFFFFF' 
            return '#3388ff', '#000000'

        @st.cache_data(ttl="10m")
        def load_data_optimized(file):
            # 1. 엑셀 데이터 로드
            if isinstance(file, str): df = pd.read_excel(file, dtype=str)
            else: df = pd.read_excel(file, dtype=str)
            
            # 2. 구글 시트 주소록 로드
            addr_df = load_sheet("stores", ttl="10m")
            
            # 3. 접점코드로 단순 병합
            target_code_col = next((col for col in df.columns if '접점번호' in str(col) or '접점코드' in str(col)), None)
            if target_code_col and addr_df is not None and not addr_df.empty:
                df[target_code_col] = df[target_code_col].astype(str).str.strip()
                addr_df['접점코드'] = addr_df['접점코드'].astype(str).str.strip()
                df = pd.merge(df, addr_df, left_on=target_code_col, right_on='접점코드', how='left')
            
            # 4. 보유처명 예외 처리 및 [핵심] 기존 데이터 그대로 연결하기!
            boyu_col = next((col for col in df.columns if '보유처' in str(col)), None)
            if boyu_col:
                df[boyu_col] = df[boyu_col].astype(str).str.strip()
                df.loc[df[boyu_col].str.contains("반추", na=False), boyu_col] = "반추정보통신"
                
                # 🚀 [에러 원인 제거!] 글자 분석 안 함. 구글 시트/엑셀에 있는 '대권역구분', '상권구분'을 그대로 사용!
                df['대분류_캐시'] = df.get('대권역구분', df.get('대분류', '미분류')).fillna('미분류')
                df['소분류_캐시'] = df.get('상권구분', df.get('소분류', '미분류')).fillna('미분류')
                df['소분류_유추불가'] = (df['소분류_캐시'] == '미분류') & (df['대분류_캐시'] != '미분류')
                
                # 지도에 뿌려줄 좌표 연결 (Jittering 미세 분산 처리만 살짝 적용)
                lats, lons = [], []
                # 🚀 각 권역별 중심 좌표 (서울시청 몰림 방지용 임시 좌표)
                REGION_CENTER_COORDS = {
                    "서북": (37.6583, 126.8320), # 고양/일산 부근
                    "서남": (37.4782, 126.9515), # 구로/관악 부근
                    "동남": (37.4959, 127.1221), # 송파/강남 부근
                    "동북": (37.6482, 127.0505), # 노원 부근
                    "남부": (37.2636, 127.0286), # 수원 부근
                    "인천": (37.4563, 126.7052), # 인천시청 부근
                    "강원": (37.8813, 127.7298)  # 춘천시청 부근
                }

                # 지도에 뿌려줄 좌표 연결 (Jittering 미세 분산 처리)
                def _calc_coord(row):
                    y, x = row.get('y좌표'), row.get('x좌표')
                    boyu = str(row[boyu_col])
                    if pd.notna(y) and pd.notna(x) and str(y).strip() != "" and str(x).lower() != "nan":
                        return get_coordinate_smart_jitter(boyu, float(y), float(x))
                    for region, coords in REGION_CENTER_COORDS.items():
                        if region in boyu:
                            return get_coordinate_smart_jitter(boyu, coords[0], coords[1])
                    return get_coordinate_priority(boyu, 37.5665, 126.9780)

                coords_series = df.apply(_calc_coord, axis=1)
                df['cached_lat'] = coords_series.apply(lambda c: c[0])
                df['cached_lon'] = coords_series.apply(lambda c: c[1])
                
                # 집단구분이 있다면 대분류에 편입 (UI 필터 연동용)
                if '집단구분' in df.columns:
                    df.loc[df['집단구분'].astype(str).str.contains('집단상가', na=False), '대분류_캐시'] = '집단상가'

            return df

        # =========================================================
        # 메인 UI
        # =========================================================
        DATA_FILE = 'inventory_data.xlsx'
        META_FILE = 'file_info.txt' 

        # 1. 사이드바: 파일 업로드
        with st.sidebar:
            st.header("📂 데이터 관리")
            uploaded_file = st.file_uploader("파일 선택", type=["xlsx"])
            st.markdown("---")
            if st.button("🗑️ 데이터 초기화", type="secondary"):
                if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
                if os.path.exists(META_FILE): os.remove(META_FILE)
                st.session_state.clear()
                st.rerun()

        if 'last_uploaded' not in st.session_state: 
            st.session_state['last_uploaded'] = None

        if uploaded_file:
            current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state['last_uploaded'] != current_file_id:
                try:
                    with open(DATA_FILE, "wb") as f: f.write(uploaded_file.getbuffer())
                    with open(META_FILE, "w", encoding="utf-8") as f: f.write(uploaded_file.name)
                    
                    st.session_state['last_uploaded'] = current_file_id
                    st.success("저장 완료")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"⛔ 저장 실패: 파일을 닫고 다시 시도해주세요. ({e})")

        df = None
        if os.path.exists(DATA_FILE):
            try: 
                df = load_data_optimized(DATA_FILE)
            except Exception as e:
                st.error(f"데이터 로드 오류: {e}")

        # 2. 메인 화면: 상태바
        if os.path.exists(META_FILE):
            with open(META_FILE, "r", encoding="utf-8") as f: f_name = f.read()
            st.markdown(f"<div class='file-status-bar'><span>✅ 저장 완료</span><span>📂 사용 중: <b>{f_name}</b></span></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='file-status-bar' style='background-color:#fff3e0; color:#ef6c00;'><span>⚠️ <b>파일 없음</b>: 사이드바(>)에서 파일 업로드</span></div>", unsafe_allow_html=True)

        if df is not None:
            # 컬럼 매핑
            col_map = {}
            for col in df.columns:
                c = str(col).replace('▼', '').strip()
                if '보유처' in c: col_map['보유처'] = col
                elif '모델명' in c: col_map['모델명'] = col
                elif '색상' in c: col_map['색상'] = col
                elif any(k in c for k in ['재고', '상태', '등급']): col_map['status'] = col
                elif '일련번호' in c: col_map['일련번호'] = col
                elif '유형' in c: col_map['모델유형'] = col  # 👈 [추가] 엑셀에서 '유형' 글자가 들어간 열 찾기

            target_col = None
            for col in df.columns:
                c = str(col).replace('▼', '').strip()
                if any(k in c for k in ['출고일']): 
                    target_col = col
                    break
                    
            if target_col is None and len(df.columns) >= 14: 
                target_col = df.columns[13]

            real_boyu = col_map.get('보유처')
            real_model = col_map.get('모델명', df.columns[0])
            real_color = col_map.get('색상', None)
            real_type = col_map.get('모델유형', None) # 👈 [추가] 모델유형 변수 등록
            real_status = col_map.get('status', None)
            real_target = target_col
            real_serial = col_map.get('일련번호', None)

            # 3. 검색창
            st.markdown("---")
            c_model, c_color = st.columns(2)
            
            with c_model:
                raw_models = df[real_model].unique().tolist()
                display_options = []
                grouped_items = []
                for label, items in MODEL_GROUPS.items():
                    if any(i in raw_models for i in items):
                        display_options.append(label)
                        grouped_items.extend(items)
                for m in raw_models:
                    if m not in grouped_items: display_options.append(str(m))
                display_options.sort()
                
                selected_models_display = st.multiselect("모델", display_options, placeholder="선택하세요")
                
                selected_models = []
                for opt in selected_models_display:
                    if opt in MODEL_GROUPS: selected_models.extend(MODEL_GROUPS[opt])
                    else: selected_models.append(opt)

            with c_color:
                if real_color:
                    color_placeholder = "선택하세요"
                    if selected_models:
                        filtered_df = df[df[real_model].isin(selected_models)]
                        sorted_colors = sorted(filtered_df[real_color].dropna().unique().tolist())
                        color_placeholder = f"💡 {selected_models_display[0]} 등 선택하신 모델의 색상을 선택해주세요. (미선택 시 전체 조회)"
                    else:
                        sorted_colors = sorted(df[real_color].dropna().unique().tolist())
                    
                    selected_colors = st.multiselect("색상", sorted_colors, placeholder=color_placeholder)
                else:
                    st.write("-")

            c_region_dae, c_region_so, c_owner = st.columns(3)
            
            with c_region_dae:
                all_dae = sorted([x for x in df['대분류_캐시'].unique() if x != "미분류"])
                
                if "강원" in all_dae:
                    all_dae.remove("강원")
                    all_dae.append("강원")
                    
                # [수정] 사무실 전용 버튼 대분류에 추가
                if "사무실(반추정보통신)" not in all_dae:
                    all_dae.insert(0, "사무실(반추정보통신)")
                    
                selected_dae = st.multiselect("지역(대분류)", all_dae, placeholder="미선택 시 전체")
                
            with c_region_so:
                if selected_dae:
                    # 사무실 필터링 스마트 처리 
                    actual_dae = [x for x in selected_dae if x != "사무실(반추정보통신)"]
                    mask_so = df['대분류_캐시'].isin(actual_dae)
                    if "사무실(반추정보통신)" in selected_dae:
                        mask_so |= df[real_boyu].astype(str).str.contains("반추", na=False)
                    so_options_df = df[mask_so]
                else:
                    so_options_df = df
                    
                raw_so = [x for x in so_options_df['소분류_캐시'].unique() if x not in ["미분류", "전체허용"]]
                
                # [핵심 최적화 구간] 반복문 내의 무거운 필터링을 제거하고 100배 빠른 딕셔너리 매핑으로 교체
                so_priority = {}
                if '사업장주소' in so_options_df.columns:
                    # 중복을 제거하고 소분류별 첫 번째 주소만 남겨 '사전'으로 만듭니다.
                    valid_df = so_options_df.dropna(subset=['사업장주소']).drop_duplicates(subset=['소분류_캐시'])
                    addr_map = dict(zip(valid_df['소분류_캐시'], valid_df['사업장주소']))
                    
                    for so in raw_so:
                        prio = 5
                        addr = str(addr_map.get(so, "")).strip()
                        if addr.startswith("서울"): prio = 1
                        elif addr.startswith("인천"): prio = 2
                        elif addr.startswith("경기"): prio = 3
                        elif addr.startswith("강원"): prio = 4
                        so_priority[so] = prio
                else:
                    for so in raw_so:
                        so_priority[so] = 5
                        
                all_so = sorted(raw_so, key=lambda x: (so_priority[x], x))
                
                # [추가] 소분류 목록에 '집단상가'를 강제로 추가
                if "집단상가" not in all_so:
                    all_so.insert(0, "집단상가")
                    
                selected_so = st.multiselect("지역(소분류)", all_so, placeholder="미선택 시 전체 (대분류 선택 시 연동)")    
                
            with c_owner:
                owner_df = df.copy()
                if selected_models:
                    owner_df = owner_df[owner_df[real_model].isin(selected_models)]
                if real_color and selected_colors:
                    owner_df = owner_df[owner_df[real_color].isin(selected_colors)]
                    
                if selected_dae:
                    actual_dae = [x for x in selected_dae if x != "사무실(반추정보통신)"]
                    mask_owner = owner_df['대분류_캐시'].isin(actual_dae)
                    if "사무실(반추정보통신)" in selected_dae:
                        mask_owner |= owner_df[real_boyu].astype(str).str.contains("반추", na=False)
                    owner_df = owner_df[mask_owner]
                    
                if selected_so:
                    mask = owner_df['소분류_캐시'].isin(selected_so) | owner_df['소분류_유추불가']
                    owner_df = owner_df[mask]
                    
                # 빈칸(NaN)을 걸러내고 문자로 변환하여 안전하게 정렬합니다.
                safe_owners = [str(x) for x in owner_df[real_boyu].unique() if pd.notna(x)]
                all_owners = sorted(safe_owners)
                
                selected_owners = st.multiselect("보유처", all_owners, placeholder="미선택 시 전체")

            st.markdown('<span class="search-btn-marker"></span>', unsafe_allow_html=True)
            
            if st.button("🚀 조회하기", use_container_width=True):
                is_specific_owner = bool(selected_owners)
                
                if not selected_models and not is_specific_owner:  # 👈 끝부분 삭제됨
                    st.warning("⚠️ 모델을 선택하거나, 특정 보유처를 선택해주세요.")
                else:
                    st.session_state['search_clicked'] = True
                    
                    temp_df = df.copy()
                    
                    if selected_models:
                        temp_df = temp_df[temp_df[real_model].isin(selected_models)]
                    
                    if selected_colors:
                        temp_df = temp_df[temp_df[real_color].isin(selected_colors)]
                        
                    if selected_owners:
                        temp_df = temp_df[temp_df[real_boyu].isin(selected_owners)]
                    
                    if selected_dae:
                        actual_dae = [x for x in selected_dae if x != "사무실(반추정보통신)"]
                        mask_temp = temp_df['대분류_캐시'].isin(actual_dae)
                        if "사무실(반추정보통신)" in selected_dae:
                            mask_temp |= temp_df[real_boyu].astype(str).str.contains("반추", na=False)
                        temp_df = temp_df[mask_temp]
                        
                    if selected_so:
                        mask = temp_df['소분류_캐시'].isin(selected_so) | temp_df['소분류_유추불가']
                        if "집단상가" in selected_so and '대분류' in temp_df.columns:
                            mask |= temp_df['대분류'].astype(str).str.contains("집단상가", na=False)
                        temp_df = temp_df[mask]
                                
                    temp_df = temp_df.sort_values(by=real_boyu, ascending=True)
                    map_filtered_df = temp_df[~temp_df[real_boyu].astype(str).str.startswith('도매-', na=False)]
                    
                    st.session_state['filtered_data'] = {'list': temp_df, 'map': map_filtered_df}
                    st.session_state['selected_idx'] = None
                    st.session_state['clicked_store_name'] = None
                    st.rerun()


            # 4. 결과 출력
            if st.session_state['filtered_data'] is not None:
                data = st.session_state['filtered_data']
                list_df = data['list']
                map_df = data['map']

                st.markdown("""
                    <style>
                        div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stVerticalBlock"]) { gap: 0rem !important; }
                    </style>
                """, unsafe_allow_html=True)

                # [수정] 엑셀 다운로드 버튼을 삭제하고 제목만 깔끔하게 출력
                st.markdown(f"<h3 style='margin: 0px; padding: 0px; padding-top: 5px; color: #E8D5A5;'>검색 총수량 ({len(list_df)}건)</h3>", unsafe_allow_html=True)
                st.markdown("---")

                if not list_df.empty:
                    map_col, list_col = st.columns([6, 4])

                    # 왼쪽: 지도 뷰
                    with map_col:
                        clicked_name = st.session_state['clicked_store_name']
                        
                        if not map_df.empty:
                            # 🚀 [추가] 파이썬이 NaN을 무시해서 마커가 증발하는 현상 방어
                            map_df = map_df.copy()
                            fallback_col = next((c for c in map_df.columns if '보유처' in c and c != real_boyu), None)
                            if fallback_col:
                                map_df[real_boyu] = map_df[real_boyu].fillna("⚠️ " + map_df[fallback_col].astype(str) + " (미매칭)")
                            else:
                                map_df[real_boyu] = map_df[real_boyu].fillna("⚠️ 미등록 보유처")

                            min_lat = float(map_df['cached_lat'].min())
                            max_lat = float(map_df['cached_lat'].max())                   
                            min_lon = float(map_df['cached_lon'].min())
                            max_lon = float(map_df['cached_lon'].max())

                            c_lat = (min_lat + max_lat) / 2.0
                            c_lon = (min_lon + max_lon) / 2.0
                            
                            # 1. 안전한 기본 지도 생성
                            m = folium.Map(location=[c_lat, c_lon], zoom_start=10)
                            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], max_zoom=12)
                            
                            # 2. 브이월드 한국형 상세지도 추가 (우측 상단에서 켜고 끄기)
                            folium.TileLayer(
                                tiles='https://api.vworld.kr/req/wmts/1.0.0/70935515-5599-317A-B90F-23A25A93D063/Base/{z}/{y}/{x}.png',
                                attr='VWorld',
                                name='브이월드 (한국형 상세지도)',
                                overlay=False,
                                control=True
                            ).add_to(m)
                            
                            folium.LayerControl(position='topright').add_to(m)

                            if gesture_handling_available:
                                try: GestureHandling().add_to(m)
                                except: pass
                            
                            # [주의] 사내망 방화벽 충돌을 막기 위해 클러스터링(MarkerCluster)을 제거하고 원복했습니다.
                            groups = map_df.groupby(['cached_lat', 'cached_lon', real_boyu])

                            for (lat, lon, name), g in groups:
                                if pd.isna(lat) or pd.isna(lon):
                                    continue
                                    
                                u_cols = g[real_color].unique()
                                is_office = "반추" in str(name)
                                
                                if len(u_cols) == 1:
                                    c_name = u_cols[0]
                                    hex_c, _ = get_real_color(c_name)
                                    if hex_c.upper() == '#FFFFFF': bg_c, ic_c = "rgba(0,0,0,0.4)", "white"
                                    else: bg_c, ic_c = "rgba(255,255,255,0.8)", hex_c
                                else: bg_c, ic_c = "transparent; background: linear-gradient(135deg, red, orange, yellow, green, blue, purple)", "white"

                                z = 1000 if st.session_state['clicked_store_name'] == name else 1
                                if st.session_state['clicked_store_name'] == name: bg_c, ic_c = "rgba(255,0,0,0.85)", "white"

                                icon_shape = "fa-mobile"
                                border_style = "border-radius: 50%;"
                                
                                if is_office:
                                    icon_shape = "fa-star"
                                    bg_c = "rgba(255, 0, 0, 0.9)"
                                    ic_c = "white"
                                    border_style = "border-radius: 10%; border: 2px solid white;"

                                t_rows = ""
                                td_style = "border:1px solid #000; padding:5px; text-align:center;"
                                
                                uid = f"store_{hashlib.md5((str(name)+str(lat)+str(lon)).encode()).hexdigest()}"
                                popup_title = f"{name}"
                                
                                address_txt = ""
                                if is_office:
                                    address_txt = "서울특별시 영등포구 경인로775 에이스하이테크 417호"
                                elif '사업장주소' in g.columns and pd.notna(g['사업장주소'].iloc[0]) and str(g['사업장주소'].iloc[0]).strip() != "":
                                    address_txt = str(g['사업장주소'].iloc[0])
                                else:
                                    address_txt = "주소 미등록"

                                # [핵심 수정] 복사될 텍스트의 첫 줄에 "반추 재고요청드립니다" 추가
                                copy_text_lines = ["반추 재고요청드립니다", f"[{popup_title}]", f"📍 {address_txt}", ""]
                                
                                # --- [수정] 모델유형을 그룹화 기준에 추가 ---
                                agg_cols = [real_model]
                                if real_color: agg_cols.append(real_color)
                                if real_type: agg_cols.append(real_type) # 👈 [추가]
                                if real_status: agg_cols.append(real_status)
                                if real_target: agg_cols.append(real_target)
                                
                                summary_g = g.groupby(agg_cols, dropna=False).size().reset_index(name='count')
                                
                                for _, r in summary_g.iterrows():
                                    cn = r[real_color] if real_color and pd.notna(r[real_color]) else "-"
                                    typ = r[real_type] if real_type and pd.notna(r[real_type]) else "-" # 👈 [추가] 모델유형 데이터 추출
                                    stt = r[real_status] if real_status and pd.notna(r[real_status]) else "-"
                                    
                                    if "반추" in str(name):
                                        tgt = "-"
                                    else:
                                        tgt = r[real_target] if real_target and pd.notna(r[real_target]) else "-"
                                        
                                    qty = r['count']
                                    
                                    # [수정] 표 내용(td)에 유형(typ) 추가
                                    t_rows += f"<tr><td style='{td_style}'>{r[real_model]}</td><td style='{td_style}'>{cn}</td><td style='{td_style}'>{typ}</td><td style='{td_style}'>{stt}</td><td style='{td_style}'>{tgt}</td><td style='{td_style}'>{qty}</td></tr>"
                                    
                                    # [수정] 복사하기 텍스트에도 유형(typ) 추가
                                    copy_text_lines.append(f"{r[real_model]} | {cn} | {typ} | {stt} | {tgt}")
                                    
                                copy_text = "\\n".join(copy_text_lines) + "\\n\\n사용가능할까요?"

                                popup_html = f"""
                                <div style='width:100%; min-width:300px; font-family:sans-serif;'>
                                    <div style='font-size:14px; font-weight:bold; color:#000; margin-bottom:3px; text-align:center; position:relative;'>
                                        {popup_title}
                                        <textarea id='{uid}' style='display:none; white-space:pre;'>{copy_text}</textarea>
                                        <i class="fa fa-clipboard" style="cursor:pointer; position:absolute; right:5px; top:0px; font-size:16px; color:#4a90e2;" onclick="
                                            var ta = document.getElementById('{uid}');
                                            ta.style.display = 'block';
                                            ta.select();
                                            document.execCommand('copy');
                                            ta.style.display = 'none';
                                            alert('목록이 복사되었습니다!');
                                        " title="내용 복사"></i>
                                    </div>
                                    
                                    <div style='font-size:11px; color:#555; text-align:center; margin-bottom:10px; border-bottom:1px solid #ddd; padding-bottom:5px; word-break:keep-all;'>
                                        📍 {address_txt}
                                    </div>
                                    
                                    <table style='width:100%; border-collapse:collapse; font-size:11px;'>
                                        <thead>
                                            <tr style='background-color:#f0f0f0;'>
                                                <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>모델</th>
                                                <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>색상</th>
                                                <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>유형</th> <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>상태</th>
                                                <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>출고일</th>
                                                <th style='border:1px solid #000; padding:5px; text-align:center; white-space:nowrap;'>수량</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {t_rows}
                                        </tbody>
                                    </table>
                                </div>
                                """
                                
                                icon_html = f"""
                                <div style="
                                    background-color: {bg_c};
                                    color: {ic_c};
                                    width: 24px;
                                    height: 24px;
                                    {border_style}
                                    display: flex;
                                    justify-content: center;
                                    align-items: center;
                                    font-size: 12px;
                                    box-shadow: 1px 1px 3px rgba(0,0,0,0.3);">
                                    <i class="fa {icon_shape}"></i>
                                </div>
                                """
                                
                                # 기존 방식대로 지도(m)에 직접 추가합니다.
                                folium.Marker(
                                    location=[lat, lon],
                                    icon=folium.DivIcon(html=icon_html),
                                    popup=folium.Popup(popup_html, max_width=400),
                                    z_index_offset=z
                                ).add_to(m)

                            st_folium(m, width="100%", height=450, returned_objects=[], key="safe_map_view")

                        else:
                            st.info("지도 데이터 없음")

                    # 오른쪽: 리스트 뷰
                    with list_col:
                        
                        # [안전한 해결] 라디오 버튼 시작 위치(상단) 조절 기능 추가
                        st.markdown("""
                            <style>
                            /* 1. 라디오 버튼 위에 숨어있는 투명한 라벨 공간 삭제 */
                            div.stRadio > label { 
                                display: none !important; 
                            }
                            
                            /* 2. [핵심] 라디오 버튼의 위/아래 위치 세밀 조절 */
                            div[data-testid="stRadio"] {
                                margin-top: -20px !important;    /* 👈 [높이 조절] 이 숫자를 조절해서 지도 상단과 일직선을 맞추세요! (-20px, -40px 등) */
                                margin-bottom: -10px !important; /* 👈 아래 스크롤 박스와의 간격 조절 */
                            }

                            /* 3. 스크롤 박스 전체를 위로 끌어올리기 */
                            div[data-testid="stScrollableContainer"] {
                                margin-top: -15px !important;
                                padding-top: 0px !important;
                            }
                            
                            /* 4. 스크롤 컨테이너 내부 버튼들 사이의 간격 촘촘하게 */
                            div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {
                                gap: 1px !important; 
                            }
                            </style>
                        """, unsafe_allow_html=True)
                    
                        col_s1, col_s2 = st.columns(2)
                        with col_s1:
                            sort_target = st.radio("기준", ["보유처명", "출고일순"], index=0, horizontal=True, label_visibility="collapsed")
                        with col_s2:
                            sort_direction = st.radio("방향", ["내림차순", "오름차순"], index=0, horizontal=True, label_visibility="collapsed")
                        
                        is_ascending = True if sort_direction == "오름차순" else False
                        sort_by_col = real_target if sort_target == "출고일순" and real_target else real_boyu
                        
                        list_df = list_df.sort_values(by=sort_by_col, ascending=is_ascending)

                        with st.container(height=500):
                            for idx, row in list_df.head(100).iterrows():
                                
                                # 🚀 [수정] 'nan' 표시 방지 및 미매칭 시 원본 이름 출력
                                raw_nm = row[real_boyu]
                                if pd.isna(raw_nm) or str(raw_nm).lower() == 'nan':
                                    # DB에 없어서 nan이 뜨면, 엑셀에 있던 다른 '보유처' 컬럼값을 찾아서 보여줌
                                    fallback_col = next((c for c in list_df.columns if '보유처' in c and c != real_boyu), None)
                                    if fallback_col and pd.notna(row[fallback_col]):
                                        nm = f"⚠️ {str(row[fallback_col])} (미매칭)"
                                    else:
                                        nm = "⚠️ 미등록 보유처"
                                else:
                                    nm = str(raw_nm)
                                
                                r_mod = row[real_model] if pd.notna(row[real_model]) else '-'
                                r_col = row[real_color] if real_color and pd.notna(row[real_color]) else '-'
                                r_typ = row[real_type] if real_type and pd.notna(row[real_type]) else '-' 
                                r_stat = row[real_status] if real_status and pd.notna(row[real_status]) else '-'
                                
                                if "반추" in nm:
                                    r_tgt = "-"
                                else:
                                    r_tgt = row[real_target] if real_target and pd.notna(row[real_target]) else '-'
                                    
                                r_serial = str(row[real_serial]) if real_serial and pd.notna(row[real_serial]) else '-' 
                                
                                # [수정] 문자열 조립 시 r_col(색상)과 r_stat(상태) 사이에 r_typ(유형)을 끼워넣음
                                det = f"{r_mod} | {r_col} | {r_typ} | {r_stat} | {r_tgt} | {r_serial}"
                                
                                is_selected = st.session_state['clicked_store_name'] == str(row[real_boyu])
                                prefix = "✅ " if is_selected else ""
                                button_label = f"{prefix}{nm}  :  {det}"
                                
                                if st.button(button_label, key=f"btn_{idx}", use_container_width=True):
                                    st.session_state['selected_idx'] = idx
                                    st.session_state['clicked_store_name'] = str(row[real_boyu])
                                    st.rerun()

                else:
                    st.warning("조건에 맞는 결과가 없습니다.")