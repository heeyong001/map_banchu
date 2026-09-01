import streamlit as st
import pandas as pd
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
from datetime import datetime, timedelta, timezone # [추가] 로그 시간 기록용 / 한국시간
from streamlit_gsheets import GSheetsConnection  # [추가] 구글 시트 연결 라이브러리
from streamlit_cookies_controller import CookieController

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


# ==============================================================================
# 대분류 확정 카테고리 (여러 함수에서 공유하므로 모듈 레벨에 둠)
# ==============================================================================
CANONICAL_DAE = [
    '사무실(반추정보통신)', '범인천', '수도권남부', '수도권동남',
    '수도권동북', '수도권서남', '수도권서북', '집단상가', '강원',
]

@st.cache_resource
def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def load_sheet(sheet_name, ttl="5m"):
    conn = get_gsheets_connection()
    return conn.read(spreadsheet=GSHEET_URL, worksheet=sheet_name, ttl=ttl)

def save_sheet(df, sheet_name, clear_cache=True):
    conn = get_gsheets_connection()
    conn.update(spreadsheet=GSHEET_URL, worksheet=sheet_name, data=df)
    if clear_cache:
        st.cache_data.clear()

def add_audit_log(username, action, details=""):
    import threading

    def _write():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1) append 방식: 시트 전체를 읽지 않고 마지막 줄에만 덧붙임
        try:
            conn = get_gsheets_connection()
            ws = conn.client._open_spreadsheet(spreadsheet=GSHEET_URL).worksheet("logs")
            ws.append_row([now, username, action, details], value_input_option="USER_ENTERED")
            return
        except Exception:
            pass

        # 2) append 실패 시에만 기존 방식으로 폴백 (캐시는 지우지 않음)
        try:
            log_df = load_sheet("logs", ttl=0)
            new_row = pd.DataFrame([{"발생시간": now, "작업자": username, "작업유형": action, "상세내역": details}])
            updated_log = pd.concat([log_df, new_row], ignore_index=True)
            save_sheet(updated_log, "logs", clear_cache=False)
        except Exception:
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
        
# 1. 화면 설정
st.set_page_config(layout="wide", page_title="재고 현황 대시보드", initial_sidebar_state="collapsed")

# ==============================================================================
# [마스터 디자인] 전역 다크/골드 테마 CSS (여기에만 존재해야 합니다!)
# ==============================================================================
st.markdown("""
    <style>
    /* 🚀 [추가] 모바일 가로 스크롤(화면 넘어감) 완벽 차단 */
    html, body, [data-testid="stAppViewContainer"], .block-container {
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
            
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
        margin: 0px 0px 10px 0px !important; /* 👈 위쪽 여백 삭제, 아래 여백만 10px 남김 */
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
    /* 🚀 [수정] 펼치기(Expander) 박스 클릭 시 하얗게 변하는 현상 방지 */
    [data-testid="stExpander"] {
        background-color: #182C24 !important;
        border: 1px solid #3A5A4A !important;
        border-radius: 8px !important;
    }
    [data-testid="stExpander"] details summary p {
        color: #D4AF37 !important; /* 제목을 금색으로 */
        font-weight: bold !important;
    }
    [data-testid="stExpanderDetails"] {
        background-color: #0A1712 !important; /* 펼쳐진 안쪽은 살짝 더 어두운 톤으로 */
        color: #E5E9F0 !important;
    }
    [data-testid="stExpander"] svg {
        color: #D4AF37 !important; /* 화살표 아이콘 금색 */
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
        /* 🚀 ① 탭 즉시 반응 — 서버 왕복 없이 브라우저가 바로 반응합니다 */
    div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button:active,
    div.element-container:has(.search-btn-marker) + div button:active {
        background-color: #D4AF37 !important;
        border-color: #D4AF37 !important;
        color: #0E1B14 !important;
        transform: scale(0.97);
    }
    div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button {
        transition: background-color 0.08s, border-color 0.08s, transform 0.08s;
        -webkit-tap-highlight-color: rgba(212,175,55,0.35);
    }

    /* 🚀 [업데이트] 우측 하단 Streamlit 기본 로고 및 워터마크 완벽 숨김 */
    footer { visibility: hidden !important; display: none !important; }

    /* 🚀 [최종 업데이트] 우측 하단 Streamlit 로고 및 워터마크 완벽 숨김 (버전 무관) */
    footer { 
        visibility: hidden !important; 
        display: none !important; 
    }

    /* 클래스명 뒤의 랜덤 해시값이 서버에서 바뀌어도 무조건 잡아내서 숨김 (^= 사용) */
    div[class^="viewerBadge"] { 
        display: none !important; 
    }

    /* 스트림릿 홈페이지로 연결되는 우측 하단 플로팅 링크 강제 차단 */
    a[href^="https://streamlit.io"] { 
        display: none !important; 
    }
            
    </style>
    <img src="error.png" style="display:none;" onerror="
        if (!window.parent.hasVisibilityListener) {
            window.parent.hasVisibilityListener = true;
            var hiddenTime = 0;
            window.parent.document.addEventListener('visibilitychange', function() {
                if (window.parent.document.visibilityState === 'hidden') {
                    // 화면을 벗어난 시간 기록
                    hiddenTime = new Date().getTime();
                } else if (window.parent.document.visibilityState === 'visible') {
                    // 화면으로 돌아왔을 때 계산
                    if (hiddenTime > 0) {
                        var awayTime = new Date().getTime() - hiddenTime;
                        if (awayTime > 180000) { // 3분(180,000ms) 이상 지났다면?
                            // 회원님 예상 1&2 완벽 구현: 화면을 강제 새로고침하여 통신망을 복구하고 쿠키를 다시 읽게 만듭니다!
                            window.parent.location.reload(); 
                        }
                    }
                }
            });
        }
    ">
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

# [보안 개선] 날짜 기반 세션 토큰 생성 함수
# 비밀번호 해시 + 오늘 날짜를 섞어 매일 자동 만료되는 토큰 생성
def make_session_token(password_hash):
    from datetime import date
    today = str(date.today())
    return hashlib.sha256((password_hash + today).encode()).hexdigest()

# ==============================================================================
# [중요] 세션 상태 초기화 & 새로고침 로그인 유지 (오직 순수 Cookie 방식)
# ==============================================================================
cookie_controller = CookieController()

# 1. 기본 상태 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.session_state['role'] = ""

# 🚀 [해결] CSS를 뿌리기 전에, 쿠키가 있는지부터 먼저 열어보고 상태를 확정합니다!
if not st.session_state['logged_in']:
    try:
        saved_token = cookie_controller.get('auth_token')
        saved_user = cookie_controller.get('auth_user')
        saved_role = cookie_controller.get('auth_role')
    except Exception: 
        saved_token, saved_user, saved_role = None, None, None
    
    if saved_token and saved_user and saved_role:
        st.session_state['logged_in'] = True
        st.session_state['username'] = saved_user
        st.session_state['role'] = saved_role
        # 쿠키가 확인되어 logged_in이 True로 변경됨!

# 🚀 [해결] 확정된 로그인 상태를 바탕으로 CSS를 주입합니다.
css_to_inject = """
<style>
/* 1. 쿠키 컨트롤러가 차지하는 상단 투명 블록 폭파 (여백 0) */
iframe[title*="cookie"] { display: none !important; }
div[data-testid="stElementContainer"]:has(iframe[title*="cookie"]) { 
    display: none !important; height: 0px !important; margin: 0px !important; padding: 0px !important; 
}
"""

# 2. 로그인 상태가 '거짓(False)'일 때만 사이드바를 숨깁니다.
if not st.session_state['logged_in']:
    css_to_inject += """
    /* 로그인 화면에서는 사이드바를 통째로 숨김 */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }

    /* 구글시트 캐시 로딩 시 뜨는 영문 "Running ..." 안내 숨김 */
    [data-testid="stSpinner"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    """

css_to_inject += "</style>"
st.markdown(css_to_inject, unsafe_allow_html=True)

# 2. 쿠키로 복구 
if not st.session_state['logged_in']:
    try:
        saved_token = cookie_controller.get('auth_token')
        saved_user = cookie_controller.get('auth_user')
        saved_role = cookie_controller.get('auth_role')
    except Exception: # 🚀 기존에 발생했던 TypeError 완벽 방어
        saved_token, saved_user, saved_role = None, None, None
    
    if saved_token and saved_user and saved_role:
        st.session_state['logged_in'] = True
        st.session_state['username'] = saved_user
        st.session_state['role'] = saved_role
        # 💡 쿠키가 있으면 딜레이 없이 즉시 대시보드로 넘어갑니다.

# --- 대시보드 상태 변수 유지 ---
if 'filtered_data' not in st.session_state: st.session_state['filtered_data'] = None
if 'selected_idx' not in st.session_state: st.session_state['selected_idx'] = None
if 'clicked_store_name' not in st.session_state: st.session_state['clicked_store_name'] = None
if 'search_clicked' not in st.session_state: st.session_state['search_clicked'] = False

# 🚀 [추가] 100배 빠른 조회를 위한 검색 결과 캐싱 함수 (중복 계산 방지)
@st.cache_data(ttl="1h", show_spinner=False)
def get_cached_search_results(_df, models, colors, owners, daes, sos, real_model, real_color, real_boyu):
    temp_df = _df.copy()
    if models: temp_df = temp_df[temp_df[real_model].isin(models)]
    if colors and real_color: temp_df = temp_df[temp_df[real_color].isin(colors)]
    if owners: temp_df = temp_df[temp_df[real_boyu].isin(owners)]
    if daes:
        actual_dae = [x for x in daes if x != "사무실(반추정보통신)"]
        mask_temp = temp_df['대분류_캐시'].isin(actual_dae)
        if "사무실(반추정보통신)" in daes:
            mask_temp |= temp_df[real_boyu].astype(str).str.contains("반추", na=False)
        temp_df = temp_df[mask_temp]
    if sos:
        mask = temp_df['소분류_캐시'].isin(sos) | temp_df['소분류_유추불가']
        if "집단상가" in sos and '대분류' in temp_df.columns:
            mask |= temp_df['대분류'].astype(str).str.contains("집단상가", na=False)
        temp_df = temp_df[mask]
        
    temp_df = temp_df.sort_values(by=real_boyu, ascending=True)
    map_filtered_df = temp_df[~temp_df[real_boyu].astype(str).str.startswith('도매-', na=False)]
    return temp_df, map_filtered_df

## ==============================================================================
# [2단계] 로그인 화면 및 화면 라우팅
# ==============================================================================
if not st.session_state['logged_in']:
    
    # 💡 쿠키가 준비되는 즉시 빠져나가도록 대기 간격을 점진적으로 늘립니다.
    #    (첫 바퀴 0.6초 — 모바일 통신 겹침 방지를 위해 보수적으로 설정)
    COOKIE_WAIT_STEPS = [0.6, 0.9, 1.2]
    current_wait_count = st.session_state.get('cookie_wait_count', 0)
    
    if current_wait_count < len(COOKIE_WAIT_STEPS):
        st.session_state['cookie_wait_count'] = current_wait_count + 1
        
        # 🚀 [잔상 완벽 해결] position: fixed 를 사용해 화면 중앙에 '로딩 박스'를 띄웁니다.
        # 프론트엔드 오류로 글자가 2번 출력되더라도 완벽하게 겹치므로 절대 2줄로 보이지 않습니다!
        st.markdown(f"""
            <div style='position: fixed; top: 40%; left: 50%; transform: translate(-50%, -50%); text-align: center; z-index: 9999; background-color: #122820; padding: 40px; border-radius: 15px; box-shadow: 0 0 20px rgba(212,175,55,0.1);'>
                <h3 style='color:#D4AF37; margin-bottom: 15px;'>🔄 잠시만 기다려주세요...</h3>
                <p style='color:#728A7C; margin: 0;'>안전한 접속을 위해 잠시만 기다려주세요.</p>
                <p style='color:#3E5147; margin: 8px 0 0 0; font-size: 11px;'>{current_wait_count + 1} / {len(COOKIE_WAIT_STEPS)}</p>
            </div>
        """, unsafe_allow_html=True)
        
        # 💡 첫 바퀴는 0.6초로 짧게, 이후 점차 늘려 통신 겹침을 방지합니다. (0.6 → 0.9 → 1.2)
        time.sleep(COOKIE_WAIT_STEPS[current_wait_count])
        
        # 삭제(empty) 코드 없이 바로 새로고침합니다.
        st.rerun()

    # 진짜로 쿠키가 없는(로그아웃된) 상태라면 아래의 로그인 폼을 보여줍니다.
    _, col_center, _ = st.columns([1, 1.2, 1])
    with col_center:
        # 🚀 [해결] 클라우드 서버에서도 파일을 잃어버리지 않도록 절대경로 생성
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 💡 주의: 깃허브에 올라간 실제 파일명(대소문자)과 정확히 똑같이 적어야 합니다!
        # 만약 깃허브에 'Logo.png' 라고 올라가 있다면 아래 "logo.png"를 "Logo.png"로 변경하세요.
        logo_path = os.path.join(current_dir, "logo.png")
        
        try:
            with open(logo_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
            st.markdown(f'<div class="logo-container"><img src="data:image/png;base64,{encoded_string}"></div>', unsafe_allow_html=True)
        except FileNotFoundError:
            # 에러 발생 시, 서버가 어디서 파일을 찾고 있었는지 경로를 화면에 출력해서 원인 파악을 돕습니다.
            st.markdown(f'<div class="logo-container"><span style="color:red; font-size:11px;">이미지를 찾을 수 없습니다.<br>검색 경로: {logo_path}</span></div>', unsafe_allow_html=True)
        
        # ... (로고 및 타이틀 표시 로직 기존과 동일하게 유지) ...
        st.markdown('<div class="title-text">반추 재고 통합시스템</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle-text">관리자 및 허가된 사원만 접근 가능합니다.</div>', unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("👤 아이디")
            password = st.text_input("🔑 비밀번호", type="password")
            submit_button = st.form_submit_button("로그인", use_container_width=True)

            if submit_button:
                if username and password:
                    # 🔐 영문 "Running ..." 대신 한글 안내를 화면 중앙에 표시
                    _login_ph = st.empty()
                    _login_ph.markdown("""
                        <div style='position: fixed; top: 40%; left: 50%; transform: translate(-50%, -50%); text-align: center; z-index: 9999; background-color: #122820; padding: 40px; border-radius: 15px; box-shadow: 0 0 20px rgba(212,175,55,0.1);'>
                            <h3 style='color:#D4AF37; margin-bottom: 15px;'>🔐 로그인 중입니다...</h3>
                            <p style='color:#728A7C; margin: 0;'>계정 정보를 확인하고 있습니다.</p>
                        </div>
                    """, unsafe_allow_html=True)

                    try:
                        users_df = load_sheet("users", ttl="10m")
                        user_match = users_df[users_df['username'] == username]
                    except Exception as _le:
                        _login_ph.empty()
                        st.error(f"⚠️ 계정 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요. ({_le})")
                        st.stop()
                    
                    if not user_match.empty and check_hashes(password, user_match.iloc[0]['password']):
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = username
                        st.session_state['role'] = user_match.iloc[0]['role']
                        
                        # 🚀 [추가] 뒤에서 쿠키를 구울 때 쓸 비밀번호 해시와 굽기 신호(플래그)를 세션에 임시 저장합니다.
                        st.session_state['user_pw_hash'] = user_match.iloc[0]['password']
                        st.session_state['needs_cookie_bake'] = True 
                        
                        add_audit_log(username, "시스템 로그인", "대시보드 정상 접속")
                        
                        # 🚀 성공 시 카운터 완료 처리 및 딜레이(time.sleep) 없이 0초 만에 즉시 대시보드로 진입!
                        st.session_state['cookie_wait_count'] = 99
                        st.success("✅ 로그인 성공! 대시보드로 이동합니다.")
                        st.rerun()
                    else:
                        _login_ph.empty()
                        st.error("⚠️ 아이디 또는 비밀번호가 일치하지 않습니다.")
    st.stop()

# ==============================================================================
# 🚀 [무중단 쿠키 굽기] 대시보드가 화면에 열린 상태에서, 방해 없이 조용히 쿠키를 저장합니다!
# ==============================================================================
if st.session_state.get('needs_cookie_bake', False):
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_until_midnight = int((next_midnight - now).total_seconds())

    if getattr(cookie_controller, '_CookieController__cookies', None) is None:
        cookie_controller._CookieController__cookies = {}
    
    # 여기서 쿠키를 브라우저로 쏩니다. 화면이 넘어간 상태라 절대 끊기거나 증발하지 않습니다.
    cookie_controller.set('auth_token', st.session_state['user_pw_hash'], max_age=seconds_until_midnight, path='/')
    cookie_controller.set('auth_user', st.session_state['username'], max_age=seconds_until_midnight, path='/')
    cookie_controller.set('auth_role', st.session_state['role'], max_age=seconds_until_midnight, path='/') 
    
    # 저장이 끝났으므로 신호를 끕니다.
    st.session_state['needs_cookie_bake'] = False

# --- 로그인 성공 시 나타나는 사이드바 메뉴 ---
with st.sidebar: # 👈 기존에 있던 코드
    st.success(f"👤 **{st.session_state['username']}**님 접속중")
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.clear()
        
        cookie_controller.remove('auth_token')
        cookie_controller.remove('auth_user')
        cookie_controller.remove('auth_role')

        # 🚀 방금 쿠키를 지웠으므로 쿠키 대기 루프(약 2.7초)를 건너뜁니다.
        st.session_state['cookie_wait_count'] = 99

        time.sleep(0.5) 
        st.rerun()

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
        # 🚀 [추가] 관리자 설정 모드일 때만 잔상 제거 CSS 작동
        st.markdown("""
            <style>
            /* 관리자 페이지에서만 stale(잔상) 요소를 숨김 */
            [data-stale="true"] {
                display: none !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        st.markdown("## ⚙️ 관리자 설정 대시보드")
        
        tab1, tab2, tab3, tab4 = st.tabs(["👥 계정 및 권한 관리", "🏢 보유처 주소록 DB 관리", "⚠️ 미매칭 보유처 확인", "🕒 시스템 변경 이력 (Log)"])
    
        # ---------------------------------------------------------
        # 탭 1: 계정 관리
        # ---------------------------------------------------------
        with tab1:
            users_df = load_sheet("users", ttl="10m")
            
            # 1. 상단: 계정 생성 및 수정/삭제 폼
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

            st.markdown("---") # 👈 구분선

            # 2. 하단: 현재 등록된 계정 목록 표시
            st.markdown("#### 📋 현재 등록된 계정 목록")
            if not users_df.empty and 'username' in users_df.columns:
                display_df = users_df[['username', 'role']].copy()
                display_df.columns = ['👤 아이디', '🔑 권한 (admin/user)']
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("등록된 계정이 없습니다.")

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

            all_data_df = load_sheet("stores", ttl="10m")
            
            c1, c2 = st.columns([7, 3])
            with c1: st.markdown(f"#### 🏢 보유처 주소록 DB 관리 (총 {len(all_data_df)}개)")
            with c2:
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer: all_data_df.to_excel(writer, index=False, sheet_name='stores_DB')
                st.download_button(label="📥 주소록 전체 다운로드 (Excel)", data=output.getvalue(), file_name=f"주소록_전체_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

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
                                # 🚀 [로직 개선] 기존 데이터 유지 + 겹치면 덮어쓰기 + 신규 추가 완벽 구현
                                bulk_df['접점코드'] = bulk_df['접점코드'].astype(str).str.strip()
                                # 혹시 모를 엑셀 파일 내의 중복 코드 제거 (맨 마지막 줄 기준)
                                bulk_df = bulk_df.drop_duplicates(subset=['접점코드'], keep='last')
                                
                                temp_all = all_data_df.copy()
                                if not temp_all.empty and '접점코드' in temp_all.columns:
                                    temp_all['접점코드'] = temp_all['접점코드'].astype(str).str.strip()
                                    
                                    # 1. 기존 DB와 새 엑셀 데이터를 위아래로 무식하게 합칩니다.
                                    combined_df = pd.concat([temp_all, bulk_df], ignore_index=True)
                                    
                                    # 2. 접점코드가 겹치면, 맨 밑에 붙은 '새로 업로드한 데이터(last)'를 남기고 예전 데이터를 삭제! (완벽한 업데이트)
                                    updated_all = combined_df.drop_duplicates(subset=['접점코드'], keep='last')
                                else: 
                                    updated_all = bulk_df
                                
                                # 🚀 [로직 개선] 구글 시트에 저장하기 직전, 누락된 좌표들만 골라서 자동 변환
                                with st.spinner("엑셀 데이터 병합 완료! 누락된 주소의 좌표를 네이버 API로 가져오는 중입니다... (데이터가 많으면 10초 이상 소요될 수 있습니다)"):
                                    if 'x좌표' not in updated_all.columns: updated_all['x좌표'] = ""
                                    if 'y좌표' not in updated_all.columns: updated_all['y좌표'] = ""
                                    updated_all['x좌표'] = updated_all['x좌표'].astype(object)
                                    updated_all['y좌표'] = updated_all['y좌표'].astype(object)
                                    
                                    for idx, row in updated_all.iterrows():
                                        addr = str(row.get('사업장주소', ''))
                                        if pd.notna(addr) and addr.strip() != "" and (not row.get('x좌표') or not row.get('y좌표') or str(row.get('x좌표')).lower() == 'nan'):
                                            n_lat, n_lon = get_lat_lon(addr)
                                            if n_lat:
                                                updated_all.at[idx, 'y좌표'] = n_lat
                                                updated_all.at[idx, 'x좌표'] = n_lon

                                save_sheet(updated_all, "stores")
                                
                                # 대량 등록도 로그에 남김
                                add_audit_log(st.session_state['username'], "보유처 대량 등록", f"엑셀 파일 업로드 ({len(bulk_df)}건 반영)")
                                
                                st.success(f"✅ 총 {len(bulk_df)}건의 데이터가 일괄 저장/업데이트 되었습니다. 구글 시트 동기화를 위해 잠시 대기합니다...")
                                
                                # 🚀 [핵심] 구글 시트에 데이터가 완전히 써질 수 있도록 1.5초 딜레이 부여! (미반영 현상 해결)
                                time.sleep(1.5) 
                                st.rerun()

            st.markdown("---")
            with st.expander("➕ 보유처 단건 등록 (클릭하여 열기)"):
                with st.form("single_store_form"):
                    s1, s2 = st.columns(2)
                    with s1:
                        single_code = st.text_input("접점코드 *", placeholder="예: A001")
                        single_name = st.text_input("보유처명 *", placeholder="예: 홍대 직영점")
                    with s2:
                        single_addr = st.text_input("사업장주소", placeholder="예: 서울특별시 마포구 ...")
                        single_region = st.text_input("대권역구분", placeholder="예: 서북")
                    single_so = st.text_input("상권구분(소분류)", placeholder="예: 홍대")
                    
                    if st.form_submit_button("➕ 등록하기", use_container_width=True):
                        if single_code and single_name:
                            # 🚀 [로직 개선] 등록과 동시에 좌표를 가져와서 한 번에 완성 (비용 방어: 주소가 있을 때만 호출)
                            with st.spinner("주소 좌표를 자동으로 변환하고 저장 중입니다..."):
                                n_lat, n_lon = None, None
                                if single_addr.strip():
                                    n_lat, n_lon = get_lat_lon(single_addr.strip())
                                    
                                new_store = pd.DataFrame([{
                                    "접점코드": single_code.strip(),
                                    "보유처명": single_name.strip(),
                                    "사업장주소": single_addr.strip(),
                                    "대권역구분": single_region.strip(),
                                    "상권구분": single_so.strip(),
                                    "x좌표": n_lon if n_lon else "",
                                    "y좌표": n_lat if n_lat else ""
                                }])
                            existing = all_data_df.copy()
                            if not existing.empty and single_code.strip() in existing['접점코드'].astype(str).values:
                                st.error(f"⚠️ 이미 존재하는 접점코드입니다: {single_code}")
                            else:
                                updated = pd.concat([existing, new_store], ignore_index=True)
                                save_sheet(updated, "stores")
                                add_audit_log(st.session_state['username'], "보유처 단건 등록", f"'{single_name}' ({single_code}) 등록")
                                # 🚀 [수정] 이제 자동으로 좌표가 따지므로 문구 변경
                                st.success(f"✅ '{single_name}' 등록 및 좌표 변환이 완료되었습니다!")
                                st.rerun()
                        else:
                            st.warning("⚠️ 접점코드와 보유처명은 필수입니다.")

            st.markdown("---")
            # 🚀 [수정] 글자 입력 시마다 새로고침 되는 것을 막기 위해 st.form으로 묶음
            with st.form("bulk_edit_form"):
                edited_df = st.data_editor(all_data_df, num_rows="dynamic", use_container_width=True, height=400, key="bulk_editor_v4")
                
                # form 안에서는 반드시 st.form_submit_button을 사용해야 합니다.
                submit_edit = st.form_submit_button("💾 위 표의 모든 변경사항 일괄 저장", use_container_width=True)
                
                if submit_edit:
                    # 🚀 [로직 개선] 저장 버튼 클릭 시, 빈칸 좌표만 쏙쏙 골라서 자동 채우기
                    with st.spinner("변경된 데이터를 분석하고 필요한 좌표를 가져오는 중입니다..."):
                        if 'x좌표' not in edited_df.columns: edited_df['x좌표'] = ""
                        if 'y좌표' not in edited_df.columns: edited_df['y좌표'] = ""
                        edited_df['x좌표'] = edited_df['x좌표'].astype(object)
                        edited_df['y좌표'] = edited_df['y좌표'].astype(object)
                        
                        for idx, row in edited_df.iterrows():
                            addr = str(row.get('사업장주소', ''))
                            if pd.notna(addr) and addr.strip() != "" and (not row.get('x좌표') or not row.get('y좌표') or str(row.get('x좌표')).lower() == 'nan'):
                                n_lat, n_lon = get_lat_lon(addr)
                                if n_lat:
                                    edited_df.at[idx, 'y좌표'] = n_lat
                                    edited_df.at[idx, 'x좌표'] = n_lon

                        save_sheet(edited_df, "stores")
                        add_audit_log(st.session_state['username'], "보유처 주소록 수정", "리스트에서 직접 데이터 변경 및 자동 좌표 저장")
                    
                    # 들여쓰기 라인 맞춤 완료!
                    st.success("✅ 저장이 완료되었습니다. 잠시 후 새로고침됩니다.")
                    time.sleep(1.5) # 성공 메시지를 읽을 수 있도록 1.5초 대기
                    st.rerun()

        # ---------------------------------------------------------
        # 탭 3: 미매칭 보유처 확인
        # ---------------------------------------------------------
        with tab3:
            st.markdown("#### ⚠️ 미매칭 보유처 확인")
            st.caption("현재 엑셀 데이터 중 주소록(DB)과 매칭되지 않는 목록을 상세 사유와 함께 표시합니다.")

            # 🚀 [수정] 탭 이동 시 자동 실행을 막고, 조회 버튼을 추가하여 최신 정보로 비교
            if st.button("🔄 최신 DB 기준으로 미매칭 데이터 조회", type="primary", use_container_width=True):
                # 핵심! 확실한 갱신을 위해 파이썬이 기억하는 이전 데이터 메모리를 한 번 날려줍니다.
                st.cache_data.clear()
                
                DATA_FILE = 'inventory_data.xlsx'
                if os.path.exists(DATA_FILE):
                    with st.spinner("최신 DB와 엑셀 데이터를 비교 분석 중입니다..."):
                        try:
                            # 1. 데이터 로드 및 전처리
                            raw_df = pd.read_excel(DATA_FILE, dtype=str)
                            raw_df.columns = raw_df.columns.astype(str).str.replace('▼', '').str.strip()
                            db_df = load_sheet("stores", ttl="10m")

                            # --- stores_inside(애칭 기준) 도 함께 로드 ---
                            def _pick_col(_df, keywords, fallback_idx):
                                for c in _df.columns:
                                    if any(k in str(c) for k in keywords):
                                        return c
                                if len(_df.columns) > fallback_idx:
                                    return _df.columns[fallback_idx]
                                return None

                            def _norm_key(v):
                                return str(v).strip().replace(" ", "").lower()

                            inside_map = {}   # 정규화된 애칭 -> (주소, x좌표)
                            try:
                                inside_df = load_sheet("stores_inside", ttl="10m")
                                if inside_df is not None and not inside_df.empty:
                                    nick_c = _pick_col(inside_df, ['애칭', '거래처'], 1)
                                    addr_c = _pick_col(inside_df, ['주소'], 15)
                                    x_c    = _pick_col(inside_df, ['x좌표', 'X좌표', '경도'], 17)
                                    if all([nick_c, addr_c, x_c]):
                                        for _, _r in inside_df.iterrows():
                                            _k = _norm_key(_r[nick_c])
                                            if _k and _k != 'nan':
                                                inside_map[_k] = (
                                                    str(_r[addr_c]).strip(),
                                                    str(_r[x_c]).strip().lower(),
                                                )
                            except Exception as _e:
                                st.info(f"ℹ️ stores_inside 시트를 읽지 못했습니다. stores 기준으로만 판정합니다. ({_e})")
                            
                            boyu_col = next((c for c in raw_df.columns if '보유처' in str(c).replace('▼','').strip()), None)
                            code_col = next((c for c in raw_df.columns if any(k in str(c) for k in ['접점번호', '접점코드'])), None)
                            
                            if boyu_col and code_col:
                                # "도매-" 또는 "반추"가 포함된 보유처는 목록에서 제외
                                raw_filtered = raw_df[
                                    (~raw_df[boyu_col].astype(str).str.contains("반추", na=False)) & 
                                    (~raw_df[boyu_col].astype(str).str.startswith("도매-", na=False))
                                ].copy()

                                # 중복 제거 (이름과 코드 조합 기준)
                                raw_unique = raw_filtered.drop_duplicates(subset=[boyu_col, code_col]).copy()
                                db_df['접점코드'] = db_df['접점코드'].astype(str).str.strip()

                                def _check_inside(row):
                                    """stores_inside 애칭 매칭 결과. 정상이면 'OK', 미등록이면 None"""
                                    info = inside_map.get(_norm_key(row[boyu_col]))
                                    if info is None:
                                        return None
                                    addr, x_val = info
                                    if not addr or addr == 'nan':
                                        return "📍 stores_inside에 애칭은 있으나 주소(P열)가 비어 있습니다."
                                    if not x_val or x_val in ('nan', 'none'):
                                        return "🌐 stores_inside에 주소는 있으나 좌표(R/S열)가 비어 있습니다."
                                    return "OK"

                                def get_unmatch_reason(row):
                                    code = str(row[code_col]).strip()

                                    # 1) 엑셀에 접점번호가 없는 경우 → 애칭으로 재확인
                                    if not code or code.lower() in ['nan', 'none', 'n/a', '']:
                                        r = _check_inside(row)
                                        if r == "OK": return None
                                        if r: return r
                                        return "❌ 엑셀 재고표에 접점번호가 없고, stores_inside 애칭에도 없습니다."

                                    # 2) stores에 접점코드가 없는 경우 → 애칭으로 재확인
                                    match = db_df[db_df['접점코드'] == code]
                                    if match.empty:
                                        r = _check_inside(row)
                                        if r == "OK": return None
                                        if r: return r
                                        return "❌ stores·stores_inside 어디에도 등록되지 않았습니다."

                                    # 3) stores에는 있으나 주소/좌표가 빈 경우 → 애칭이 대신 채워주는지 확인
                                    m_row = match.iloc[0]
                                    addr = str(m_row.get('사업장주소', '')).strip()
                                    x_val = str(m_row.get('x좌표', '')).strip().lower()

                                    if not addr or addr == 'nan':
                                        if _check_inside(row) == "OK": return None
                                        return "📍 stores에 등록은 되어있으나 주소 정보가 누락되었습니다."
                                    if not x_val or x_val in ('nan', 'none'):
                                        if _check_inside(row) == "OK": return None
                                        return "🌐 주소는 있으나 좌표(위경도) 생성에 실패한 매장입니다."
                                    return None

                                raw_unique['미매칭 사유'] = raw_unique.apply(get_unmatch_reason, axis=1)
                                unmapped_display = raw_unique[raw_unique['미매칭 사유'].notna()].copy()

                                if not unmapped_display.empty:
                                    st.warning(f"총 **{len(unmapped_display)}**건의 미매칭 데이터가 발견되었습니다.")
                                    final_cols = [boyu_col, '미매칭 사유']
                                    if '대분류' in unmapped_display.columns: final_cols.append('대분류')
                                    st.dataframe(unmapped_display[final_cols], use_container_width=True, hide_index=True)
                                else: 
                                    st.success("🎉 모든 데이터가 주소록 DB와 완벽하게 매칭되어 있습니다!")
                            else: st.error("엑셀 파일에서 '보유처' 또는 '접점코드' 컬럼을 식별할 수 없습니다.")
                        except Exception as e: st.error(f"데이터 분석 중 오류 발생: {e}")
                else: 
                    st.warning("📂 먼저 메인 화면에서 재고 엑셀 파일을 업로드해주세요.")
            else:
                st.info("👆 위 버튼을 눌러 최신 DB 데이터를 기준으로 미매칭 목록을 조회하세요.")

        # ---------------------------------------------------------
        # 탭 4: 시스템 변경 이력 (Audit Log)
        # ---------------------------------------------------------
        with tab4:
            st.markdown("#### 🕒 관리자 작업 이력")
            st.caption("누가, 언제, 어떤 작업을 수행했는지 확인합니다. (최근 100건)")
            
            try:
                log_df = load_sheet("logs", ttl="10m")
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

        # =========================================================
        # 🎨 색상 팔레트 (엑셀 '색상명' → 실제 표시 색상)
        #    새 색상이 추가되면 여기에 한 줄만 추가하면 됨
        # =========================================================
        COLOR_PALETTE = {
            # --- 블랙 계열 ---
            "제트블랙":   "#111111",
            "블랙":       "#000000",
            "차콜":       "#36454F",
            "그래파이트": "#4A4E54",
            # --- 그레이/실버 계열 ---
            "티타늄":     "#9AA0A6",
            "그레이":     "#808080",
            "실버쉐도우": "#8E8E93",
            "실버블루":   "#A7B8C8",
            "화이트실버": "#E6E8EA",
            "실버":       "#C0C0C0",
            # --- 화이트/크림 계열 ---
            "화이트":     "#FFFFFF",
            "크림":       "#F2E3C2",
            "베이지":     "#E8D5B7",
            # --- 웜 계열 ---
            "골드":       "#FFD700",
            "옐로우":     "#F5D000",
            "오렌지":     "#FF7F00",
            "레드":       "#E01B24",
            "핑크":       "#FFAFC5",
            "브라운":     "#7B4B2A",
            # --- 퍼플 계열 ---
            "라벤더":     "#B57EDC",
            "바이올렛":   "#8A5FD3",
            "퍼플":       "#7B2D8E",
            # --- 블루 계열 ---
            "네이비":     "#1F3864",
            "아이스블루": "#BEE3F0",
            "라이트블루": "#7EC8E3",
            "블루":       "#2058C8",
            # --- 그린 계열 ---
            "민트":       "#8FE3CF",
            "그린":       "#1F9E4F",
        }
        DEFAULT_COLOR = "#9E9E9E"  # 팔레트에 없는 색 → 회색(파랑으로 오인 방지)

        # 부분일치 검사 시 긴 이름부터 확인 (라이트블루가 블루보다 먼저 걸리도록)
        _SORTED_COLOR_KEYS = sorted(COLOR_PALETTE.keys(), key=len, reverse=True)

        def _get_luminance(hex_code):
            """0(검정) ~ 1(흰색) 사이의 밝기값 반환"""
            h = hex_code.lstrip('#')
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (0.299 * r + 0.587 * g + 0.114 * b) / 255

        def get_real_color(korean_color):
            """엑셀 색상명 → (배경 hex, 그 위에 얹을 글자 hex)"""
            if pd.isna(korean_color):
                return DEFAULT_COLOR, '#FFFFFF'

            c = str(korean_color).strip().replace(" ", "")

            # 1순위: 정확히 일치
            hex_c = COLOR_PALETTE.get(c)

            # 2순위: 부분 일치 (긴 이름 우선)
            if hex_c is None:
                for key in _SORTED_COLOR_KEYS:
                    if key in c:
                        hex_c = COLOR_PALETTE[key]
                        break

            if hex_c is None:
                hex_c = DEFAULT_COLOR

            text_c = '#000000' if _get_luminance(hex_c) > 0.6 else '#FFFFFF'
            return hex_c, text_c

        @st.cache_data(ttl="12h", show_spinner=False)
        def load_data_optimized(file):
            # 1. 데이터 로드 (parquet 캐시 우선, 없거나 실패하면 엑셀)
            df = None
            if isinstance(file, str):
                _pq = os.path.splitext(file)[0] + '.parquet'
                if os.path.exists(_pq):
                    try:
                        df = pd.read_parquet(_pq)
                    except Exception as _e:
                        print(f"[parquet 읽기 실패 → 엑셀로 대체] {_e}")
                        df = None
            if df is None:
                df = pd.read_excel(file, dtype=str)
            
                        # =========================================================
            # 2. 보유처명 정규화 (⚠️ 애칭 매칭 기준이므로 병합보다 먼저)
            # =========================================================
            boyu_col = next((col for col in df.columns if '보유처' in str(col)), None)
            if boyu_col:
                df[boyu_col] = df[boyu_col].astype(str).str.strip()
                df.loc[df[boyu_col].str.contains("반추", na=False), boyu_col] = "반추정보통신"
                # 애칭 대조용 키 (공백 제거 + 소문자)
                df['_보유처_키'] = df[boyu_col].str.replace(r"\s+", "", regex=True).str.lower()

            # 헤더 이름으로 먼저 찾고, 못 찾으면 지정한 열 위치로 대체
            def _pick_col(_df, keywords, fallback_idx):
                for c in _df.columns:
                    if any(k in str(c) for k in keywords):
                        return c
                if len(_df.columns) > fallback_idx:
                    return _df.columns[fallback_idx]
                return None

            df['주소출처'] = "미등록"   # 미등록 / 접점매칭 / 애칭매칭

            # =========================================================
            # 3. [1차] stores 시트 — 접점번호 기준
            # =========================================================
            try:
                addr_df = load_sheet("stores", ttl="10m")
            except Exception as e:
                addr_df = None
                print(f"[stores 로드 실패] {e}")

            target_code_col = next((col for col in df.columns if '접점번호' in str(col) or '접점코드' in str(col)), None)
            if target_code_col and addr_df is not None and not addr_df.empty and '접점코드' in addr_df.columns:
                df[target_code_col] = df[target_code_col].astype(str).str.strip()
                addr_df = addr_df.copy()
                addr_df['접점코드'] = addr_df['접점코드'].astype(str).str.strip()
                addr_df = addr_df.drop_duplicates(subset=['접점코드'], keep='last')
                df = pd.merge(df, addr_df, left_on=target_code_col, right_on='접점코드', how='left')

                if '사업장주소' in df.columns:
                    _ok = df['사업장주소'].notna() & (df['사업장주소'].astype(str).str.strip() != "")
                    df.loc[_ok, '주소출처'] = "접점매칭"

            # 이후 로직이 참조하는 표준 컬럼이 없으면 빈 칸으로 생성
            for _c in ['사업장주소', 'x좌표', 'y좌표']:
                if _c not in df.columns:
                    df[_c] = pd.NA

            # =========================================================
            # 4. [2차] stores_inside 시트 — 거래처 애칭 기준 (1차 미매칭 건만)
            #    B열=애칭 / P열=주소 / R열=x좌표 / S열=y좌표
            # =========================================================
            try:
                inside_df = load_sheet("stores_inside", ttl="10m")
            except Exception as e:
                inside_df = None
                print(f"[stores_inside 로드 실패] {e}")

            if boyu_col and inside_df is not None and not inside_df.empty:
                nick_c = _pick_col(inside_df, ['애칭', '거래처'], 1)
                addr_c = _pick_col(inside_df, ['주소'], 15)
                x_c    = _pick_col(inside_df, ['x좌표', 'X좌표', '경도'], 17)
                y_c    = _pick_col(inside_df, ['y좌표', 'Y좌표', '위도'], 18)
                print(f"[stores_inside 컬럼 감지] 애칭={nick_c} / 주소={addr_c} / x={x_c} / y={y_c}")

                if all([nick_c, addr_c, x_c, y_c]):
                    ins = inside_df[[nick_c, addr_c, x_c, y_c]].copy()
                    # 이름 충돌(_x/_y 접미사) 방지를 위해 전용 이름으로 변경
                    ins.columns = ['_ins_애칭', '_ins_주소', '_ins_x', '_ins_y']
                    ins['_ins_키'] = (ins['_ins_애칭'].astype(str).str.strip()
                                        .str.replace(r"\s+", "", regex=True).str.lower())
                    ins = ins[ins['_ins_키'] != ""]
                    ins = ins.drop_duplicates(subset=['_ins_키'], keep='last')

                    df = pd.merge(df, ins.drop(columns=['_ins_애칭']),
                                  left_on='_보유처_키', right_on='_ins_키', how='left')

                    # 1차에서 주소를 못 채운 행 && 애칭이 매칭된 행만 덮어쓰기
                    need = (df['사업장주소'].isna() | (df['사업장주소'].astype(str).str.strip() == "")) \
                           & df['_ins_주소'].notna() \
                           & (df['_ins_주소'].astype(str).str.strip() != "")

                    df.loc[need, '사업장주소'] = df.loc[need, '_ins_주소']
                    df.loc[need, 'x좌표']     = df.loc[need, '_ins_x']
                    df.loc[need, 'y좌표']     = df.loc[need, '_ins_y']
                    df.loc[need, '주소출처']   = "애칭매칭"

                    df = df.drop(columns=['_ins_주소', '_ins_x', '_ins_y', '_ins_키'], errors='ignore')
                else:
                    print("[stores_inside] 애칭/주소/좌표 컬럼을 찾지 못했습니다.")

            df = df.drop(columns=['_보유처_키'], errors='ignore')

            # 5. (이하 기존 로직 그대로 유지)
            if boyu_col:
                
                # =========================================================
                # 대분류 확정 카테고리 매핑
                #   1순위: 시트('대권역구분') 값을 확정 명칭으로 정규화
                #   2순위: 값이 없을 때만 보유처명에서 추출
                # =========================================================
                

                # ⚠️ 도매 계정(도매-○○○)을 넣을 카테고리. 확정 목록에 없어 기본 미분류.
                WHOLESALE_DAE = '미분류'

                # 구/약식 표기 → 확정 명칭
                DAE_ALIAS = {
                    '사무실(반추정보통신)': '사무실(반추정보통신)',
                    '반추정보통신': '사무실(반추정보통신)',
                    '반추':   '사무실(반추정보통신)',
                    '사무실': '사무실(반추정보통신)',
                    '본사':   '사무실(반추정보통신)',
                    '범인천': '범인천',      '인천': '범인천',
                    '수도권남부': '수도권남부', '남부': '수도권남부',
                    '수도권동남': '수도권동남', '동남': '수도권동남',
                    '수도권동북': '수도권동북', '동북': '수도권동북',
                    '수도권서남': '수도권서남', '서남': '수도권서남',
                    '수도권서북': '수도권서북', '서북': '수도권서북',
                    '집단상가': '집단상가', '테크노마트': '집단상가',
                    '강변TM': '집단상가',   '신도림TM': '집단상가',
                    '강원': '강원',
                    # --- 개별 등록 (규칙으로 안 잡히는 곳) ---
                    '미리별': '수도권서남',        
                    '세명네트웍스': '수도권서남',
                    '원텔레콤': '수도권서남',
                    '용인신갈': '수도권남부',
                    }

                _DAE_KEYS = sorted(DAE_ALIAS.keys(), key=len, reverse=True)  # 긴 키워드 우선
                _NULLS = {'', 'nan', 'none', '<na>', 'null', '-', '미분류'}

                def _canon_dae(value):
                    """임의 문자열 → 확정 카테고리. 못 찾으면 None"""
                    v = str(value).strip()
                    if v.lower() in _NULLS:
                        return None
                    if v in CANONICAL_DAE:
                        return v
                    for k in _DAE_KEYS:
                        if k in v:
                            return DAE_ALIAS[k]
                    return None

                def _resolve_region_from_name(name):
                    """보유처명에서 확정 카테고리 추출"""
                    n = str(name).strip()
                    toks = [t.strip() for t in n.split('-') if t.strip()]
                    # 1) 하이픈 토큰 완전일치 (지명 오인 방지, 최우선)
                    for t in toks:
                        if t in CANONICAL_DAE:
                            return t
                        if t in DAE_ALIAS:
                            return DAE_ALIAS[t]
                    # 2) 본사 / 집단상가 (이름 전체에서 탐색)
                    for k in ('반추', '강변TM', '신도림TM', '테크노마트'):
                        if k in n:
                            return DAE_ALIAS[k]
                    # 3) 토큰 내부 부분일치 (접두 코드가 붙은 경우)
                    for t in toks:
                        r = _canon_dae(t)
                        if r:
                            return r
                    # 4) 도매 계정
                    if '도매' in n:
                        return WHOLESALE_DAE
                    return '미분류'

                def _clean_series(col_names):
                    """컬럼을 읽되 빈문자/공백/'nan' 문자열을 전부 결측으로 통일"""
                    for c in col_names:
                        if c in df.columns:
                            s = df[c].astype(str).str.strip()
                            return s.mask(s.str.lower().isin(_NULLS), pd.NA)
                    return pd.Series(pd.NA, index=df.index, dtype='object')

                # --- 대분류 ---
                _dae_raw = _clean_series(['대권역구분', '대분류'])
                _dae = pd.Series(
                    [_canon_dae(v) if pd.notna(v) else None for v in _dae_raw],
                    index=df.index, dtype='object'
                )
                _need_dae = _dae.isna()
                if _need_dae.any():
                    _name_map = {n: _resolve_region_from_name(n)
                                 for n in df.loc[_need_dae, boyu_col].unique()}
                    _dae = _dae.mask(_need_dae, df[boyu_col].map(_name_map))
                df['대분류_캐시'] = _dae.fillna('미분류')

                # --- 소분류 (기존 로직 유지) ---
                df['소분류_캐시'] = _clean_series(['상권구분', '소분류']).fillna('미분류')
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

                # 🚀 [최적화 ⓑ] 좌표는 (보유처명 + x/y좌표)에만 의존하므로 고유 조합만 계산
                _key_cols = [boyu_col] + [c for c in ['y좌표', 'x좌표'] if c in df.columns]
                _k = df[_key_cols[0]].astype(str).fillna("")
                for _c in _key_cols[1:]:
                    _k = _k + "||" + df[_c].astype(str).fillna("")
                df['_좌표키'] = _k

                _uniq = df.drop_duplicates(subset=['_좌표키'])[['_좌표키'] + _key_cols].copy()
                _res = _uniq.apply(_calc_coord, axis=1)
                _uniq['cached_lat'] = _res.apply(lambda c: c[0])
                _uniq['cached_lon'] = _res.apply(lambda c: c[1])

                df['cached_lat'] = df['_좌표키'].map(dict(zip(_uniq['_좌표키'], _uniq['cached_lat'])))
                df['cached_lon'] = df['_좌표키'].map(dict(zip(_uniq['_좌표키'], _uniq['cached_lon'])))
                df = df.drop(columns=['_좌표키'], errors='ignore')
                
                # 집단구분이 있다면 대분류에 편입 (UI 필터 연동용)
                if '집단구분' in df.columns:
                    df.loc[df['집단구분'].astype(str).str.contains('집단상가', na=False), '대분류_캐시'] = '집단상가'

            return df

        # =========================================================
        # 메인 UI
        # =========================================================     
        DATA_FILE = 'inventory_data.xlsx'
        META_FILE = 'file_info.txt' 
        CACHE_FILE = 'inventory_data.parquet'   # 🚀 빠른 재로딩용 캐시

        # 1. 사이드바: 파일 업로드
        with st.sidebar:
            st.header("📂 데이터 관리")
            uploaded_file = st.file_uploader("파일 선택", type=["xlsx"])
            st.markdown("---")
            if st.button("🗑️ 데이터 초기화", type="secondary"):
                if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
                if os.path.exists(META_FILE): os.remove(META_FILE)
                if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
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
                    
                    # 🚀 parquet 캐시 생성 (실패 시 반드시 삭제 → 옛 데이터 잔존 방지)
                    try:
                        pd.read_excel(DATA_FILE, dtype=str).to_parquet(CACHE_FILE, index=False)
                    except Exception as _pe:
                        if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
                        print(f"[parquet 캐시 생성 실패 → 엑셀로 동작] {_pe}")

                    st.session_state['last_uploaded'] = current_file_id
                    st.success("저장 완료")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"⛔ 저장 실패: 파일을 닫고 다시 시도해주세요. ({e})")

        df = None
        if os.path.exists(DATA_FILE):
            try: 
                # 🚀 [수정] 요청하신 깔끔한 멘트로 변경 완료
                with st.spinner("🔄 자료를 갱신중입니다."):
                    df = load_data_optimized(DATA_FILE)
            except Exception as e:
                st.error(f"데이터 로드 오류: {e}")

       # 2. 메인 화면: 상태바
        st.markdown("""
            <style>
            /* 1. 부모 가로 블록: 모바일에서도 무조건 1줄(row) 강제 유지 */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important; 
            align-items: center !important; 
            gap: 8px !important; 
            margin-bottom: 0px !important;
            max-width: 100% !important;
            padding-right: 20px !important; /* 👈 [핵심] 우측 여백을 3배로 늘려서 버튼을 왼쪽으로 쑥 밀어냅니다! */
            box-sizing: border-box !important;
            }
            
            div[data-testid="stHorizontalBlock"]:has(.status-marker) * { margin: 0 !important; }
            
            /* 2. 컬럼 너비 강제 할당 및 높이 35px 고정 */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) > div[data-testid="column"] {
                width: auto !important;
                min-width: 0 !important; /* 👈 내부 텍스트가 팽창하는 것 방어 */
                padding: 0 !important;
                height: 35px !important; 
                display: flex !important;
                align-items: center !important;
            }

            /* 3. [왼쪽 상태바 영역] 버튼 크기와 여백을 뺀 나머지 공간 확보 */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) > div[data-testid="column"]:nth-child(1) {
                flex: 1 1 0px !important;  /* 👈 [수정] 빈 공간에서 시작해서 남는 공간만 채우도록 지시 */
                width: 0px !important;     /* 👈 [수정] 억지로 팽창하는 것을 차단 */
                overflow: hidden !important; /* 👈 내부 텍스트가 박스를 밀어내는 것 방어 */
            }

            /* 4. [오른쪽 버튼 영역] 35px 고정 */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) > div[data-testid="column"]:nth-child(2) {
                flex: 0 0 35px !important; 
                width: 35px !important;
                justify-content: center !important;   /* 👈 [수정] 칸의 중앙에 배치하여 시작점을 안쪽으로 당김 */
                
            }

            /* 🚀 5. [핵심 해결] 상태바 텍스트 1줄 강제 및 줄임표(...) 처리 */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) .file-status-bar {
                height: 35px !important; 
                width: 100% !important;
                display: block !important; /* flex 대신 block으로 텍스트 절단 허용 */
                line-height: 33px !important; /* 수직 중앙 정렬 보정 */
                padding: 0 10px !important; 
                box-sizing: border-box !important;
                background-color: #182C24 !important; 
                border: 1px solid #3A5A4A !important; 
                color: #D4AF37 !important;
                border-radius: 8px !important; 
                font-size: 14px !important; 
                font-weight: bold !important;
                
                /* 👇 2줄 꺾임 방지 절대 방어 코드 */
                white-space: nowrap !important; 
                overflow: hidden !important;
                text-overflow: ellipsis !important; 
            }

            /* 7. 새로고침 버튼 디자인 (흰색 배경 제거 및 골드 테마 적용) */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) button {
                width: 35px !important;
                height: 35px !important;
                min-height: 35px !important;
                padding: 0 !important;
                display: flex !important;
                justify-content: center !important;
                align-items: center !important;
                font-size: 16px !important; 
                border-radius: 8px !important; 
                box-sizing: border-box !important;

                /* 🚀 추가된 색상 코드 */
                background-color: #000000 !important; /* 배경을 검정색으로 고정 */
                color: #D4AF37 !important;           /* 아이콘(화살표)을 금색으로 */
                border: 1px solid #D4AF37 !important; /* 테두리를 금색으로 */
            }

            /* 마우스 올렸을 때(Hover) 효과 추가 */
            div[data-testid="stHorizontalBlock"]:has(.status-marker) button:hover {
                background-color: #1a1a1a !important;
                border-color: #FCECA1 !important;
                color: #FCECA1 !important;
            }

            /* 8. 모바일 폰트 크기 미세 조절 */
            @media (max-width: 400px) {
                div[data-testid="stHorizontalBlock"]:has(.status-marker) .file-status-bar {
                    font-size: 12px !important;
                    padding: 0 6px !important;
                }
            }
            </style>
            
        """, unsafe_allow_html=True)

        status_col, refresh_col = st.columns([9.5, 0.5])
        
        with status_col:
            if os.path.exists(META_FILE):
                with open(META_FILE, "r", encoding="utf-8") as f: f_name = f.read()
                st.markdown(f"<span class='status-marker' style='display:none;'></span><div class='file-status-bar'><span>✅ 저장 완료</span>&nbsp;&nbsp;<span>📂 <b>{f_name}</b></span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<span class='status-marker' style='display:none;'></span><div class='file-status-bar' style='background-color:#fff3e0 !important; color:#ef6c00 !important; border-color:#ef6c00 !important;'><span>⚠️ 파일 없음</span></div>", unsafe_allow_html=True)
                
        with refresh_col:
            if st.button("🔄", help="새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        
        if df is not None:
            # 컬럼 매핑
            col_map = {}
            for col in df.columns:
                c = str(col).replace('▼', '').strip()
                if '보유처' in c and '보유처' not in col_map: col_map['보유처'] = col
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

            # 🚀 [추가] 검색창 구역만 따로 새로고침되도록 격리 (화면 깜빡임 원천 차단)
            @st.fragment
            def search_filter_section():
                selected_colors = []   # real_color가 없는 경우 대비 (NameError 방지)

                c_model, c_dae, c_color = st.columns(3)

                with c_model:
                    # 🚀 [URL 복원] 이전 조회 조건 (보유처는 URL 길이 문제로 저장하지 않음)
                    def _qp_list(_key):
                        try:
                            return [str(v) for v in st.query_params.get_all(_key) if str(v).strip()]
                        except Exception:
                            return []
                    _init_models = _qp_list('m')
                    _init_dae    = _qp_list('d')
                    _init_colors = _qp_list('c')

                    # 1. 엑셀에 존재하는 순수 모델명들을 중복 없이 가져와서 정렬합니다.
                    raw_models = df[real_model].dropna().unique().tolist()
                    display_options = [str(m) for m in raw_models]
                    display_options.sort()

                    # 2. 그룹화 변환 로직 없이, 선택된 모델명들을 그대로 변수에 담습니다!
                    selected_models = st.multiselect("모델", display_options, placeholder="선택하세요",
                                                     default=[x for x in _init_models if x in display_options])

                with c_dae:
                    _present = set(df['대분류_캐시'].unique())
                    all_dae = [x for x in CANONICAL_DAE if x in _present]
                    all_dae += sorted([x for x in _present if x not in CANONICAL_DAE and x != "미분류"])

                    if "강원" in all_dae:
                        all_dae.remove("강원")
                        all_dae.append("강원")

                    if "사무실(반추정보통신)" not in all_dae:
                        all_dae.insert(0, "사무실(반추정보통신)")

                    selected_dae = st.multiselect("지역(대분류)", all_dae, placeholder="미선택 시 전체",
                                                  default=[x for x in _init_dae if x in all_dae])

                with c_color:
                    if real_color:
                        color_placeholder = "선택하세요"
                        if selected_models:
                            filtered_df = df[df[real_model].isin(selected_models)]
                            sorted_colors = sorted(filtered_df[real_color].dropna().unique().tolist())
                            color_placeholder = f"💡 {selected_models[0]}의 색상 선택 (미선택 시 전체)"
                        else:
                            sorted_colors = sorted(df[real_color].dropna().unique().tolist())

                        selected_colors = st.multiselect("색상", sorted_colors, placeholder=color_placeholder,
                                                         default=[x for x in _init_colors if x in sorted_colors])
                    else:
                        st.write("-")

                c_region_so, c_owner = st.columns(2)
                    
                with c_region_so:
                    if selected_dae:
                        actual_dae = [x for x in selected_dae if x != "사무실(반추정보통신)"]
                        mask_so = df['대분류_캐시'].isin(actual_dae)
                        if "사무실(반추정보통신)" in selected_dae:
                            mask_so |= df[real_boyu].astype(str).str.contains("반추", na=False)
                        so_options_df = df[mask_so]
                    else:
                        so_options_df = df
                        
                    raw_so = [x for x in so_options_df['소분류_캐시'].unique() if x not in ["미분류", "전체허용"]]
                    
                    so_priority = {}
                    if '사업장주소' in so_options_df.columns:
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
                    
                    if "집단상가" not in all_so:
                        all_so.insert(0, "집단상가")
                        
                    selected_so = st.multiselect("지역(소분류)", all_so, placeholder="미선택 시 전체 (대분류 선택 시 연동)")    
                    
                with c_owner:
                    _key = (
                        tuple(sorted(selected_models)),
                        tuple(sorted(selected_colors if selected_colors else [])),
                        tuple(sorted(selected_dae)),
                        tuple(sorted(selected_so))
                    )
                    if st.session_state.get('_owner_cache_key') != _key:
                        _odf = df.copy()
                        if selected_models:
                            _odf = _odf[_odf[real_model].isin(selected_models)]
                        if real_color and selected_colors:
                            _odf = _odf[_odf[real_color].isin(selected_colors)]
                        if selected_dae:
                            _adae = [x for x in selected_dae if x != "사무실(반추정보통신)"]
                            _mask = _odf['대분류_캐시'].isin(_adae)
                            if "사무실(반추정보통신)" in selected_dae:
                                _mask |= _odf[real_boyu].astype(str).str.contains("반추", na=False)
                            _odf = _odf[_mask]
                        if selected_so:
                            _odf = _odf[_odf['소분류_캐시'].isin(selected_so) | _odf['소분류_유추불가']]
                        st.session_state['_owner_cache_key'] = _key
                        st.session_state['_owner_cache_list'] = sorted(
                            [str(x) for x in _odf[real_boyu].unique() if pd.notna(x)]
                        )
                    all_owners = st.session_state.get('_owner_cache_list', [])
                    selected_owners = st.multiselect("보유처", all_owners, placeholder="미선택 시 전체")

                # 🚀 [핵심 추가] Fragment 밖의 버튼이 쓸 수 있도록 세션에 최신 상태 저장
                st.session_state['tmp_selected_models'] = selected_models
                st.session_state['tmp_selected_colors'] = selected_colors
                st.session_state['tmp_selected_dae'] = selected_dae
                st.session_state['tmp_selected_so'] = selected_so
                st.session_state['tmp_selected_owners'] = selected_owners

            # 🚀 검색창(드롭다운) 영역만 독립 실행
            search_filter_section()            

            # ⚠️ 슬롯은 반드시 마커보다 '위'에 있어야 합니다.
            #    마커와 버튼 사이에 두면 CSS 선택자(+ div)가 버튼을 못 찾습니다.
            _btn_css = st.empty()   # 실행 중 버튼 문구 변경용 (렌더 완료 후 원복)

            # 🚀 [버튼을 밖으로 꺼냄] 이 버튼을 누르면 "무조건" 전체 화면(지도 포함)이 새로고침 됩니다!
            st.markdown('<span class="search-btn-marker"></span>', unsafe_allow_html=True)
            
            if st.button("🚀 조회하기", use_container_width=True):
                # Fragment가 방금 저장해둔 최신 조건들을 불러옵니다
                s_models = st.session_state.get('tmp_selected_models', [])
                s_colors = st.session_state.get('tmp_selected_colors', [])
                s_dae = st.session_state.get('tmp_selected_dae', [])
                s_so = st.session_state.get('tmp_selected_so', [])
                s_owners = st.session_state.get('tmp_selected_owners', [])

                is_specific_owner = bool(s_owners)
                if not s_models and not is_specific_owner:
                    st.warning("⚠️ 모델을 선택하거나, 특정 보유처를 선택해주세요.")
                    st.session_state['filtered_data'] = None 
                else:
                    st.session_state['search_clicked'] = True
                    st.session_state['_searching'] = True   # 결과 렌더링까지 스피너 유지용

                    # ② 실행 중 — 버튼 문구 변경 + 중복 클릭 차단
                    _btn_css.markdown("""
                        <span class="btn-css-slot"></span>
                        <style>
                        /* CSS만 담는 슬롯이므로 화면에서 완전히 제거 (밀림 방지) */
                        div[data-testid="stElementContainer"]:has(.btn-css-slot),
                        div.element-container:has(.btn-css-slot) {
                            display: none !important;
                            height: 0px !important;
                            margin: 0px !important;
                            padding: 0px !important;
                        }
                        div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button {
                            border: 2px solid #D4AF37 !important;
                            background-color: rgba(212,175,55,0.15) !important;
                            pointer-events: none !important;
                        }
                        div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button p,
                        div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button > div,
                        div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button span {
                            visibility: hidden !important;
                            position: absolute !important;
                        }
                        div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button {
                            position: relative !important;
                        }
                        div[data-testid="stElementContainer"]:has(.search-btn-marker) + div button::after {
                            content: "🔍 조회하는 중입니다...";
                            position: absolute;
                            top: 0; left: 0; right: 0; bottom: 0;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            font-size: 18px;
                            font-weight: 600;
                            color: #D4AF37;
                        }
                        </style>
                    """, unsafe_allow_html=True)
                    
                    list_res, map_res = get_cached_search_results(
                        df, 
                        tuple(s_models), 
                        tuple(s_colors) if s_colors else tuple(), 
                        tuple(s_owners) if s_owners else tuple(), 
                        tuple(s_dae) if s_dae else tuple(), 
                        tuple(s_so) if s_so else tuple(),
                        real_model, real_color, real_boyu
                    )
                    
                    st.session_state['filtered_data'] = {'list': list_res, 'map': map_res}
                    st.session_state['selected_idx'] = None
                    st.session_state['clicked_store_name'] = None

                    # 🚀 [URL 저장] 모바일 복귀 시 조건 복원용 (보유처 제외 — URL 길이 초과 방지)
                    try:
                        _qp_new = {}
                        if s_models: _qp_new['m'] = list(s_models)
                        if s_dae:    _qp_new['d'] = list(s_dae)
                        if s_colors: _qp_new['c'] = list(s_colors)
                        st.query_params.clear()
                        if _qp_new:
                            st.query_params.update(_qp_new)
                    except Exception as _qe:
                        print(f"[URL 저장 실패] {_qe}")

        # 4. 결과 출력
        # 🚀 [최적화 2] 결과 화면(지도+리스트)을 독립된 구역(Fragment)으로 분리
        @st.fragment
        def display_results_section():
            if st.session_state.get('filtered_data') is not None:
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

                            # 🚀 [최적화 1] 지도를 그리기 직전에만 무거운 모듈을 불러옵니다 (Lazy Import)
                            import folium
                            from folium.features import DivIcon
                            from streamlit_folium import st_folium
                            from branca.element import Element 
                          
                            # 1. 안전한 기본 지도 생성
                            m = folium.Map(location=[c_lat, c_lon], zoom_start=10, attributionControl=False)
                            m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], max_zoom=12)
                            
                            folium.TileLayer(
                                 tiles='https://api.vworld.kr/req/wmts/1.0.0/0580472E-D858-365E-968B-F1FCE560F381/Base/{z}/{y}/{x}.png',
                                 attr='VWorld',
                                 name='브이월드 (한국형 상세지도)',
                                 overlay=True,
                                 control=True
                             ).add_to(m)
                            
                            # 우측 상단에 레이어 컨트롤러(설정창) 표시
                            # folium.LayerControl(position='topright').add_to(m)

                            # 🚀 [새로운 모바일 전용 제어 로직]
                            # 데스크탑: 클릭 드래그(이동), 휠(확대/축소) - 원래대로 자유롭게 유지
                            # 모바일: 한 손가락은 페이지 스크롤, '두 손가락'일 때만 지도 조작 가능
                            
                            map_id = m.get_name()
                            mobile_js = f"""
                            <script>
                            var map_obj = {map_id};
                            // 접속 기기가 모바일(터치 기기)인지 확인
                            if (/Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent)) {{
                                // 1. 모바일에서는 기본 드래그와 줌을 일단 비활성화 (페이지 스크롤 방해 방지)
                                map_obj.dragging.disable();
                                map_obj.touchZoom.disable();
                                
                                // 2. 손가락이 2개 이상(멀티터치)일 때만 기능을 켬
                                map_obj.on('touchstart', function(e) {{
                                    if (e.touches.length > 1) {{
                                        map_obj.dragging.enable();
                                        map_obj.touchZoom.enable();
                                    }}
                                }});
                                
                                // 3. 터치가 끝나면 다시 기능을 꺼서 실수로 지도가 움직이지 않게 방어
                                map_obj.on('touchend', function(e) {{
                                    map_obj.dragging.disable();
                                    map_obj.touchZoom.disable();
                                }});
                            }}
                            </script>
                            """
                            # 지도의 루트 HTML에 스크립트 주입
                            m.get_root().html.add_child(Element(mobile_js))
                            
                            # [주의] 사내망 방화벽 충돌을 막기 위해 클러스터링(MarkerCluster)을 제거하고 원복했습니다.

                            # 🚀 [최적화 ⓐ] 마커마다 groupby를 반복하지 않도록 전체를 한 번에 집계
                            _agg_cols = [real_model]
                            if real_color:  _agg_cols.append(real_color)
                            if real_type:   _agg_cols.append(real_type)
                            if real_status: _agg_cols.append(real_status)
                            if real_target: _agg_cols.append(real_target)

                            _grp_keys = ['cached_lat', 'cached_lon', real_boyu]
                            _summary_all = (map_df.groupby(_grp_keys + _agg_cols, dropna=False)
                                                  .size().reset_index(name='count'))
                            _summary_map = {k: v for k, v in _summary_all.groupby(_grp_keys, dropna=False)}
                            _empty_summary = _summary_all.iloc[0:0]

                            groups = map_df.groupby(_grp_keys)

                            for (lat, lon, name), g in groups:
                                if pd.isna(lat) or pd.isna(lon):
                                    continue
                                    
                                u_cols = g[real_color].unique()
                                is_office = "반추" in str(name)
                                
                                if len(u_cols) == 1:
                                    c_name = u_cols[0]
                                    hex_c, _ = get_real_color(c_name)
                                    # 변경: 밝은 색은 어두운 배경 위에 올려서 흰 배경에 묻히지 않게 함
                                    if _get_luminance(hex_c) > 0.75:
                                        bg_c, ic_c = "rgba(35,35,35,0.75)", hex_c
                                    else:
                                        bg_c, ic_c = "rgba(255,255,255,0.85)", hex_c
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
                                td_style = "border:1px solid #aaa; padding:5px; text-align:center;"
                                
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
                                
                                # --- [최적화] 루프 밖에서 미리 집계해둔 결과를 조회만 함 ---
                                summary_g = _summary_map.get((lat, lon, name), _empty_summary)
                                
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
                                    copy_text_lines.append(f"{r[real_model]} | {cn}")
                                    
                                # 1. 기본 복사 텍스트 세팅
                                copy_text = "\\n".join(copy_text_lines) + "\\n\\n사용가능할까요?"

                                # 2. HTML 팝업창 렌더링 (주석 제거 및 에러 완벽 방지)
                                popup_html = f"""
                                <div style='width:100%; min-width:280px; max-width:350px; font-family:sans-serif;'>
                                    
                                    <div style='font-size:14px; font-weight:bold; color:#000; margin-bottom:8px; text-align:center; position:relative;'>
                                        {popup_title}
                                        <textarea id='base_text_{uid}' style='display:none;'>{copy_text}</textarea>
                                        <i class="fa fa-clipboard" style="cursor:pointer; position:absolute; right:5px; top:0px; font-size:16px; color:#4a90e2;" onclick="
                                            try {{
                                                var nl = String.fromCharCode(10);
                                                var base = document.getElementById('base_text_{uid}').value;
                                                var memo = document.getElementById('memo_{uid}').value.trim();
                                                var finalTxt = base;
                                                
                                                if(memo !== '') {{
                                                    finalTxt += nl + memo + ' 이동합니다.';
                                                }} else {{
                                                    finalTxt += nl + '';
                                                }}
                                                
                                                var tempTa = document.createElement('textarea');
                                                tempTa.value = finalTxt;
                                                tempTa.style.position = 'fixed';
                                                document.body.appendChild(tempTa);
                                                tempTa.select();
                                                var success = document.execCommand('copy');
                                                document.body.removeChild(tempTa);
                                                
                                                if(success) {{
                                                    alert('✅ 목록이 복사되었습니다!');
                                                }} else {{
                                                    alert('⚠️ 복사에 실패했습니다. 브라우저 설정을 확인해주세요.');
                                                }}
                                            }} catch(err) {{
                                                alert('에러 발생: ' + err);
                                            }}
                                        " title="내용 복사"></i>
                                    </div>
                                    
                                    <div style='font-size:11px; color:#555; text-align:center; margin-bottom:8px; border-bottom:1px solid #ddd; padding-bottom:5px; word-break:keep-all;'>
                                        📍 {address_txt}
                                    </div>

                                    <div style='margin-bottom:8px; text-align:center;'>
                                        <input type='text' id='memo_{uid}' placeholder='이동할 곳만입력하세요, "이동합니다" 멘트와 함께 복사됩니다' 
                                               style='width:95%; padding:5px; font-size:11px; border:1px solid #aaa; border-radius:4px; box-sizing:border-box;'>
                                    </div>
                                    
                                    <div style='max-height: 150px; overflow-y: auto; border-bottom: 1px solid #eee;'>
                                        <table style='width:100%; border-collapse:collapse; font-size:11px;'>
                                            <thead>
                                                <tr style='background-color:#f0f0f0; position: sticky; top: 0; z-index: 1;'>
                                                    <th style='border:1px solid #aaa; padding:5px; text-align:center; white-space:nowrap;'>모델</th>
                                                    <th style='border:1px solid #aaa; padding:5px; text-align:center; white-space:nowrap;'>색상</th>
                                                    <th style='border:1px solid #aaa; padding:5px; text-align:center; white-space:nowrap;'>유형</th> 
                                                    <th style='border:1px solid #aaa; padding:5px; text-align:center; white-space:nowrap;'>상태</th>
                                                    <th style='border:1px solid #aaa; padding:5px; text-align:center; white-space:nowrap;'>출고일</th>
                                                    <th style='border:1px solid #aaa; padding:5px; text-align:center; white-space:nowrap;'>수량</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {t_rows}
                                            </tbody>
                                        </table>
                                    </div>
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
                                    popup=folium.Popup(popup_html, max_width=400, max_height=250),
                                    z_index_offset=z
                                ).add_to(m)

                            st_folium(m, width="100%", height=500, returned_objects=[], key="safe_map_view")

                        else:
                            st.info("지도 데이터 없음")

                    # 오른쪽: 리스트 뷰
                    with list_col:
                        
                        # 🚀 [업데이트] 라디오 버튼 모바일 한 줄 정렬 및 여백 극한 축소
                        st.markdown("""
                            <style>
                            /* 1. 라디오 버튼 위에 숨어있는 투명한 라벨 공간 삭제 */
                            div.stRadio > label { display: none !important; }
                            
                            /* 2. 라디오 버튼의 위/아래 위치 세밀 조절 (지도와 높이 맞춤) */
                            div[data-testid="stRadio"] {
                                margin-top: -20px !important; 
                                margin-bottom: -10px !important; 
                                margin-left: 15px !important;    
                            }

                            /* 3. 스크롤 박스 전체를 위로 끌어올리기 */
                            div[data-testid="stScrollableContainer"] {
                                margin-top: -15px !important; padding-top: 0px !important;
                            }
                            
                            /* 4. 스크롤 컨테이너 내부 100개 버튼들 사이의 간격 촘촘하게 */
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
                                det = f"{r_mod} | {r_col} | {r_typ} | {r_stat} | {r_tgt} | 일련 : {r_serial}"
                                
                                is_selected = st.session_state['clicked_store_name'] == str(row[real_boyu])
                                prefix = "✅ " if is_selected else ""
                                button_label = f"{prefix}{nm}  :  {det}"
                                
                                if st.button(button_label, key=f"btn_{idx}", use_container_width=True):
                                    st.session_state['selected_idx'] = idx
                                    st.session_state['clicked_store_name'] = str(row[real_boyu])
                                    
                else:
                    st.warning("조건에 맞는 결과가 없습니다.")

        # 조회 중 표시는 버튼 자체가 담당하므로 별도 스피너를 쓰지 않습니다.
        st.session_state.pop('_searching', None)
        display_results_section()

        # 결과 렌더링이 끝났으므로 조회하기 버튼 문구를 원래대로 되돌립니다.
        try:
            _btn_css.empty()
        except NameError:
            pass