import streamlit as st
import pandas as pd

# 기존 보유처 멀티셀렉트의 입력창에서 Enter를 감지합니다.
# Streamlit components v2 사용 (1.54.0에서 브라우저 검증).
@st.cache_resource
def _owner_enter_component():
    import streamlit.components.v2 as components_v2
    return components_v2.component(
        "owner_keyword_enter",
        js="""
        export default function({data, setTriggerValue}) {
            const selector = '.st-key-' + CSS.escape(data.widget_key);
            const filterSelector = '[class*="st-key-filter_multiselect_"]';
            // Close after BaseWeb has finished its own selection event. Observing
            // tags alone can miss changes when Streamlit remounts the component.
            const closeAfterSelection = (input) => {
                const box = input?.closest(filterSelector);
                if (!box) return;
                setTimeout(() => {
                    const current = input.isConnected ? input : box.querySelector('input');
                    if (current) current.blur();
                    document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                    document.body.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                    document.body.dispatchEvent(new MouseEvent('click', {bubbles:true}));
                }, 0);
            };
            const onOptionClick = (event) => {
                if (!(event.target instanceof Element)) return;
                const option = event.target.closest('[role="option"], [data-baseweb="menu"] li');
                if (!option || option.getAttribute('aria-disabled') === 'true') return;
                const input = document.activeElement;
                if (input instanceof HTMLInputElement && input.closest(filterSelector)) {
                    closeAfterSelection(input);
                }
            };
            const onFilterEnter = (event) => {
                if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229 || event.repeat) return;
                const input = event.target;
                if (input instanceof HTMLInputElement && input.closest(filterSelector) &&
                    input.getAttribute('aria-expanded') === 'true') closeAfterSelection(input);
            };
            document.addEventListener('click', onOptionClick, true);
            document.addEventListener('keydown', onFilterEnter, true);

            const onKeyDown = (event) => {
                const input = event.target;
                if (!(input instanceof HTMLInputElement) ||
                    !input.closest(selector) || event.key !== 'Enter') return;
                // 한글 조합 확정 Enter는 선택 동작으로 처리하지 않습니다.
                if (event.isComposing || event.keyCode === 229) return;
                const keyword = input.value.trim();
                if (!keyword) return; // 빈 입력은 원래 키보드 선택 동작 유지
                event.preventDefault();
                event.stopPropagation();
                event.stopImmediatePropagation();
                if (event.repeat) return;
                document.dispatchEvent(new CustomEvent('inventory-owner-intent', {detail: (data.options || []).filter(x => x.toLowerCase().includes(keyword.toLowerCase()))}));
                input.blur();
                setTriggerValue('keyword', keyword);
            };
            document.addEventListener('keydown', onKeyDown, true);
            const values = new Map();
            const closeChangedSelection = () => {
                document.querySelectorAll('[data-testid="stMultiSelect"]').forEach(box => {
                    const input = box.querySelector('input');
                    if (!input || !box.closest('[class*="st-key-filter_multiselect_"]')) return;
                    const signature = JSON.stringify(Array.from(box.querySelectorAll('[data-baseweb="tag"]')).map(x => x.textContent));
                    if (values.has(input) && values.get(input) !== signature) {
                        // BaseWeb closes its portal via an outside pointer event.
                        document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                        document.body.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                        document.body.dispatchEvent(new MouseEvent('click', {bubbles:true}));
                        input.blur();
                    }
                    values.set(input, signature);
                });
            };
            closeChangedSelection();
            const observer = new MutationObserver(closeChangedSelection);
            observer.observe(document.body, {childList:true, subtree:true});
            return () => {
                observer.disconnect();
                document.removeEventListener('keydown', onKeyDown, true);
                document.removeEventListener('keydown', onFilterEnter, true);
                document.removeEventListener('click', onOptionClick, true);
            };

        }
        """,
    )


# Browser-owned recovery: it remains able to detect a lost Python connection.
@st.cache_resource
def _recovery_component():
    import streamlit.components.v2 as components_v2
    return components_v2.component("inventory_recovery", js=r"""
    export default function({data, setTriggerValue}) {
        const root = window;
        root.__inventoryLoggingOut=false;
        const key = 'inventory-recovery-v2:' + location.pathname + ':' + data.user;
        let r = root.__inventoryRecovery;
        if (!r || r.key !== key) {
            if (r?.dispose) r.dispose();
            let saved = null;
            try { saved = JSON.parse(sessionStorage.getItem(key)); } catch (_) {}
            r = root.__inventoryRecovery = {key, draft:data.draft, last:data.last,
                pending:null, saved, loaded:false, timer:null, changedAt:0};
        }
        r.send = setTriggerValue;
        r.data = data;
        const persist = () => {
            try { sessionStorage.setItem(key, JSON.stringify({draft:r.draft,last:r.last,time:Date.now()})); } catch (_) {}
        };
        const status = (text, offerReload=false) => {
            if (r.disposed && text) return;
            const badge=document.getElementById('inv-connection-badge');
            if(badge)badge.textContent=!navigator.onLine?'● 연결 끊김':text?'● 연결 확인 중':'● 연결됨';
            r.statusText = text;
            r.offerReload = offerReload;
            const el = document.getElementById('inventory-connection-status');
            if (!el) return;
            const signature = JSON.stringify([text, offerReload]);
            if (el.dataset.recoveryStatus === signature) return;
            el.dataset.recoveryStatus = signature;
            el.replaceChildren();
            el.hidden = !text;
            if (!text) return;
            const label = document.createElement('span');
            label.textContent = text;
            el.appendChild(label);
            if (offerReload) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = '연결 복구';
                button.style.cssText = 'margin-left:8px;min-height:44px;cursor:pointer';
                button.onclick = () => {
                    // 기존 sessionStorage 복원 로직이 새 세션에서 사용합니다.
                    persist();
                    location.reload();
                };
                el.appendChild(button);
            }
        };
        // Native reruns also prove connectivity, without interrupting an active query.
        if (r.renderToken !== data.render_token) {
            r.renderToken=data.render_token;
            r.nativeDeadline=0;
        }
        const ping = (restore=false, resume=false) => {
            if (r.disposed || window.__inventoryLoggingOut) return;
            if (Date.now() < (r.queryQuietUntil || 0)) return;
            if (document.hidden || !navigator.onLine || r.pending) return;
            if (!document.querySelector('[class*="st-key-filter_multiselect_model_"]')) return;
            const nonce = String(Date.now()) + Math.random();
            r.pending = {nonce, time: Date.now()};
            r.send('request', {
                nonce, restore, resume, draft: r.draft, last: r.last
            });
        };
        if (data.reset_token && r.resetToken !== data.reset_token) {
            r.resetToken = data.reset_token;
            r.ownerIntent = null;
            r.pending = null;
            r.saved = null;
            r.loaded = true;
            r.draft = {...data.draft};
            r.last = null;
            r.changedAt = 0;
            r.captureUntil = 0;
            r.queryQuietUntil = 0;
            clearTimeout(r.resumeTimer);
            status('');
            persist();
        }
        if (r.ownerIntent && r.ownerIntent.every(x => data.draft.owners.includes(x))) r.ownerIntent=null;
        if (r.pending && data.ack === r.pending.nonce) {
            r.pending=null; status('');
            try { sessionStorage.removeItem(key+':attempts'); } catch(_) {}
            r.draft={...data.draft}; if(r.ownerIntent) r.draft.owners=r.ownerIntent; r.last = data.last ?? null; persist();
        } else if (!r.pending && r.loaded) {
            r.draft={...data.draft}; if(r.ownerIntent) r.draft.owners=r.ownerIntent; r.last = data.last ?? null; persist();
        }
        if (!r.loaded) {
            r.loaded=true;
            if (data.fresh && r.saved && Date.now()-r.saved.time < 86400000) {
                r.draft=r.saved.draft; r.last=r.saved.last; ping(true);
            } else { persist(); }
        }
        if (!r.timer) {
            const readDraft = () => {
                const next = {...r.draft};
                for (const [name,prefix] of Object.entries(r.data.prefixes)) {
                    const box = document.querySelector('[class*="st-key-'+prefix+'_"]');
                    // A missing/stale widget during rerender is not a user deletion.
                    if (!box || box.closest('[data-stale="true"]')) return null;
                    next[name]=Array.from(box.querySelectorAll('[data-baseweb="tag"]')).map(x=>x.querySelector('span[title]')?.getAttribute('title') || x.textContent.trim());
                }
                if (r.ownerIntent) next.owners=r.ownerIntent;
                const serialBox=document.querySelector('.st-key-filter_serial_query input');
                if (serialBox) next.serial=serialBox.value;
                return next;
            };
            const changed = () => {
                const next=readDraft();
                if (!next) return;
                if (JSON.stringify(next)!==JSON.stringify(r.draft)) {
                    r.draft=next; persist(); r.changedAt=Date.now();
                }
            };
            const interaction = (event) => {
                const target=event.target;
                if (!(target instanceof Element)) return;
                if (target.closest('[class*="st-key-filter_multiselect_"]') ||
                    target.closest('[role="option"]') || target.closest('.st-key-filter_serial_query')) {
                    r.captureUntil=Date.now()+1500;
                    // Probe connectivity without restoring/rewriting widget values.
                    clearTimeout(r.interactionTimer);
                    // Native widget events already contact the server.
                }
            };
            const resume = () => {
                if (document.hidden || r.disposed || window.__inventoryLoggingOut) return;
                if (!navigator.onLine) {
                    status('인터넷 연결을 기다리고 있습니다. 검색조건은 유지됩니다.');
                    return;
                }
                clearTimeout(r.resumeTimer);
                // 조회 처리 중에는 복구 요청으로 실행을 중단하지 않습니다.
                const wait = Math.max(0, (r.queryQuietUntil || 0) - Date.now());
                r.resumeTimer = setTimeout(() => {
                    if (document.hidden || r.disposed || window.__inventoryLoggingOut) return;
                    status('앱 연결을 확인하고 있습니다…');
                    ping(false, true);
                }, wait + 250);
            };
            const click = (event) => {
                if (event.target.closest('.st-key-inventory_logout_button')) {
                    window.__inventoryLoggingOut=true;
                    try { sessionStorage.removeItem(key); } catch(_) {}
                    r.dispose(); root.__inventoryRecovery=null; status(''); return;
                }
                if (event.target.closest('.st-key-inventory_search_button')) { changed(); r.last={...r.draft}; persist();
                    // Let the native search finish. A delayed health check must not
                    // interrupt the first map render with a second fragment run.
                    r.queryQuietUntil=Date.now()+30000;
                    r.nativeDeadline=Date.now()+30000;
                    clearTimeout(r.interactionTimer); }
            };
            const owner = (event) => {
                r.draft.owners=[...new Set([...r.draft.owners,...event.detail])];
                r.ownerIntent=r.draft.owners;
                persist(); r.changedAt=Date.now();
            };
            document.addEventListener('click',click,true);
            document.addEventListener('click',interaction,true);
            document.addEventListener('keydown',interaction,true);
            document.addEventListener('input',interaction,true);
            document.addEventListener('visibilitychange',resume);
            document.addEventListener('inventory-owner-intent',owner);
            window.addEventListener('online',resume);
            window.addEventListener('pageshow',resume);
            r.timer=setInterval(()=>{
                if(document.hidden || !document.querySelector('[class*="st-key-filter_multiselect_model_"]')) return;
                if (!r.pending && Date.now() < (r.captureUntil || 0)) changed();
                if (r.statusText) status(r.statusText, r.offerReload);
                if (r.nativeDeadline && Date.now()>r.nativeDeadline) {
                    r.nativeDeadline=0;
                }
                if(r.changedAt && Date.now()-r.changedAt>600 && !r.pending) {
                    r.changedAt=0;
                }
                // A delayed component callback is not evidence of a lost socket.
                // Streamlit owns reconnection; never reload a live page here.
                if (!navigator.onLine) {
                    status('인터넷 연결을 기다리고 있습니다. 검색조건은 유지됩니다.');
                } else if (r.pending && Date.now() - r.pending.time > 20000) {
                    status('서버 응답이 지연되고 있습니다. 계속 기다리거나 연결을 복구하세요.', true);
                }
                // 정상 응답 수신 시 기존 ack 분기가 status('')로 안내를 지웁니다.
            },300);
            r.dispose=()=>{
                r.disposed=true;
                r.pending=null;
                r.probeController?.abort();
                clearInterval(r.timer);
                clearTimeout(r.interactionTimer);
                clearTimeout(r.resumeTimer);
                document.removeEventListener('click',click,true);
                document.removeEventListener('click',interaction,true);
                document.removeEventListener('keydown',interaction,true);
                document.removeEventListener('input',interaction,true);
                document.removeEventListener('visibilitychange',resume);
                document.removeEventListener('inventory-owner-intent',owner);
                window.removeEventListener('online',resume);
                window.removeEventListener('pageshow',resume);
            };
        }
        // Do not remove the watchdog during a Streamlit component remount.
    }
    """)


@st.fragment
def render_recovery_bridge():
    if st.session_state.get("_logout_pending") or st.session_state.get("_explicit_logged_out"):
        return
    def _receive_recovery():
        if st.session_state.get("_logout_pending") or st.session_state.get("_explicit_logged_out"):
            return
        request = st.session_state.get("inventory_recovery_bridge", {}).get("request") or {}
        st.session_state["_recovery_ack"] = request.get("nonce")
        # Existing sessions only acknowledge a foreground probe. A fresh session
        # still restores filters/results through the explicit restore branch.
        if request.get("restore") and st.session_state.get("_recovery_fresh", True):
            draft = request.get("draft") or {}
            if isinstance(draft.get('serial'), str):
                st.session_state['_inv_serial_restore'] = draft['serial'][:256]
            for name, suffix in recovery_prefixes.items():
                values = draft.get(name)
                if isinstance(values, list) and all(isinstance(v, str) for v in values):
                    st.session_state["filter_selected_" + name] = list(dict.fromkeys(values))[:5000]
                    st.session_state["filter_multiselect_" + suffix + "_0"] = st.session_state["filter_selected_" + name]
            if st.session_state.get("_recovery_fresh", True):
                last = request.get("last")
                if isinstance(last, dict):
                    st.session_state["_last_search_conditions"] = last
                    st.session_state["_restore_last_result"] = True
            st.session_state["_recovery_fresh"] = False
            st.session_state["_recovery_full_rerun"] = True
        st.session_state["_recovery_fresh"] = False

    recovery_prefixes = {"models":"model", "colors":"color", "dae":"dae", "so":"so", "owners":"owner"}
    _recovery_component()(
        key="inventory_recovery_bridge",
        data={
            "render_token": time.time_ns(),
            "user": st.session_state.get("username", ""),
            "draft": {**{name: st.session_state.get("filter_selected_" + name, []) for name in recovery_prefixes},
                      "serial": st.session_state.get("filter_serial_query", "")},
            "serial": st.session_state.get("filter_serial_query", ""),
            "last": st.session_state.get("_last_search_conditions"),
            "fresh": st.session_state.get("_recovery_fresh", True),
            "ack": st.session_state.get("_recovery_ack"),
            "reset_token": st.session_state.get("_filter_reset_token"),
            "prefixes": {name: "filter_multiselect_" + suffix for name, suffix in recovery_prefixes.items()},
        },
        on_request_change=_receive_recovery,
        height=0,
    )
    if st.session_state.pop("_recovery_full_rerun", False):
        st.rerun(scope="app")



def normalize_owner_match_key(value):
    """비교할 때만 이름 맨 앞의 자음형 유형 머릿말을 무시합니다."""
    import re

    if value is None or pd.isna(value):
        return ""
    key = re.sub(r"\s+", "", str(value).strip()).lower()
    if key in {"", "nan", "none", "null", "<na>", "-"}:
        return ""
    # ㅌ01-, ㅌㅌ03-, ㅊ-, ㅊ인천-, ㅌ58인천- 등:
    # 선두 자음형 코드 + 선택적 숫자 + 선택적 하이픈만 비교 키에서 제거합니다.
    # ^로 시작 위치를 제한해 지역명·매장명 중간의 내용은 보존합니다.
    return re.sub(r"^(?:[ㄱ-ㅎ]+[0-9]*-?)+", "", key)


def build_store_location_hints(address_coordinate_rows):
    """DB의 정상 주소·좌표에서 지역별 대표 좌표를 만듭니다. 외부 API는 호출하지 않습니다."""
    import re
    import math
    from statistics import median
    from collections import defaultdict

    samples = defaultdict(list)
    token_pattern = re.compile(
        r'(?<![가-힣0-9])([가-힣][가-힣0-9.·]*?(?:특별자치시|특별시|광역시|시|군|구|읍|면|동|리))(?=\s|[(),]|$)'
    )
    metro_names = ('서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종')

    def add(parts, label, level, lat, lon):
        parts = tuple(dict.fromkeys(part for part in parts if len(part) >= 2))
        if parts:
            samples[(parts, label, level)].append((lat, lon))

    for address, x, y in address_coordinate_rows:
        try:
            lat, lon = float(y), float(x)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90
                and -180 <= lon <= 180 and lat != 0 and lon != 0):
            continue
        text = str(address).strip()
        if text.lower() in ('', 'nan', 'none', 'null', '<na>', '-', '주소 미등록', '미등록'):
            continue
        tokens = token_pattern.findall(text)
        city = ''
        for token in tokens:
            if token.endswith(('특별자치시', '특별시', '광역시')):
                city = re.sub(r'(특별자치시|특별시|광역시)$', '', token)
                break
            if token.endswith(('시', '군')):
                city = token[:-1]
                break
        if not city:
            city = next((name for name in metro_names if text.startswith(name + ' ')), '')
        if not city:
            continue
        add((city,), city, 2, lat, lon)
        districts = [token[:-1] for token in tokens if token.endswith('구') and len(token) >= 3]
        for district in districts:
            add((city, district), city + ' ' + district, 3, lat, lon)
        for token in tokens:
            if not token.endswith(('읍', '면', '동', '리')):
                continue
            local = token[:-1]
            aliases = {local, re.sub(r'[0-9.·]+$', '', local)}
            if local.endswith('본'):
                aliases.add(local[:-1])
            for alias in aliases:
                if len(alias) < 2:
                    continue
                add((city, alias), city + ' ' + alias, 5, lat, lon)
                for district in districts:
                    add((city, district, alias), city + ' ' + district + ' ' + alias, 6, lat, lon)
                    add((district, alias), city + ' ' + district + ' ' + alias, 4, lat, lon)
                # 단독 동 이름은 여러 지역에서 쓰이면 아래에서 제외합니다.
                add((alias,), city + ' ' + alias, 1, lat, lon)

    hints = []
    for (parts, label, level), coords in samples.items():
        unique = list(set(coords))
        lat = median(point[0] for point in unique)
        lon = median(point[1] for point in unique)
        # 같은 이름이 멀리 떨어진 곳에서 쓰이면 단일 위치로 단정하지 않습니다.
        distances = [math.hypot((point[0]-lat)*111, (point[1]-lon)*88) for point in unique]
        limit = 90 if level == 2 else 30 if level == 3 else 12
        if max(distances, default=0) > limit:
            continue
        hints.append((parts, label, lat, lon, level))
    single_labels = defaultdict(set)
    for parts, label, _, _, level in hints:
        if level in (1, 4):
            single_labels[parts].add(label)
    return [hint for hint in hints if hint[4] not in (1, 4) or len(single_labels[hint[0]]) == 1]


def infer_store_location(owner, db_hints, neighborhoods, districts, region_centers):
    """구체적인 지명 조합 > 시·구 > 고유 동명 > 넓은 권역 순서로 추정합니다."""
    import re
    text = normalize_owner_match_key(owner)
    candidates = []

    # 기존 좌표 사전의 동 이름에 도시 문맥을 붙여 동명이인을 줄입니다.
    parent_areas = {
        '용인': ('죽전',), '성남': ('판교', '야탑'),
        '고양': ('신원', '화정', '성사', '삼송', '원흥', '장항'),
        '시흥': ('배곧', '정왕', '은행'), '부천': ('상동', '중동', '소사'),
        '김포': ('풍무', '사우', '구래'), '광명': ('철산', '하안'),
        '수원': ('우만',), '화성': ('동탄', '병점', '봉담', '향남'),
        '평택': ('장당', '송탄', '안중', '팽성'), '안성': ('공도',),
        '하남': ('미사',), '광주': ('경안', '태전'), '여주': ('홍문',),
        '의정부': ('민락',), '동두천': ('지행',), '양주': ('옥정', '덕정'),
        '남양주': ('다산', '별내', '호평'), '양평': ('양수',),
        '파주': ('운정', '문산', '광탄', '봉일'), '연천': ('전곡',),
        '인제': ('원통',), '인천': ('송도', '청라', '구월', '주안', '검단'),
    }

    def offer(parts, label, lat, lon, level):
        if parts and all(part.lower() in text for part in parts):
            # 긴 지명과 더 구체적인 조합을 우선합니다. 이름의 앞쪽 권역에 끌려가지 않습니다.
            candidates.append(((level, sum(map(len, parts)), len(parts)), label, lat, lon))

    for parts, label, lat, lon, level in db_hints:
        offer(parts, label, lat, lon, level)
    for city, locals_ in parent_areas.items():
        for local in locals_:
            if local in neighborhoods:
                lat, lon = neighborhoods[local]
                offer((city, local), city + ' ' + local, lat, lon, 5)
    # 명확한 시설 이름만 우선합니다. '테크노' 같은 일반 상호 조각은 시설로 단정하지 않습니다.
    for facility in ('반추정보통신', '반추', '신도림TM', '강변TM'):
        if facility in neighborhoods:
            lat, lon = neighborhoods[facility]
            offer((facility,), facility, lat, lon, 7)

    # 기존 시·구 사전도 활용하되 '중구' 등 중복 지명은 단독으로 쓰지 않습니다.
    ambiguous_districts = {'중구', '강서', '동구', '서구', '남구', '북구', '중원', '수정', '장안', '동안', '만안'}
    for city, (lat, lon) in districts.items():
        if city not in ambiguous_districts:
            offer((city,), city, lat, lon, 2)
    # 정해진 권역명 자체와 '인천'이 넓은 단서인 경우는 구체적 동명보다 뒤로 미룹니다.
    specific = [candidate for candidate in candidates if candidate[0][0] >= 3]
    city_hits = [candidate for candidate in candidates if candidate[0][0] == 2 and candidate[1] not in region_centers]
    local_hits = [candidate for candidate in candidates if candidate[0][0] == 1]
    pool = specific or city_hits or local_hits or candidates
    if pool:
        _, label, lat, lon = max(pool, key=lambda item: item[0])
        return lat, lon, label
    # 마지막에만 넓은 권역 중심을 사용합니다.
    for region, (lat, lon) in region_centers.items():
        if region in text:
            return lat, lon, region + ' 권역'
    # 단서가 전혀 없으면 임의의 서울 위치를 만들지 않습니다. 목록에는 남습니다.
    return None, None, ''


def format_knote_contact(value):
    """누락된 첫 0을 보완하고 연락처 종류에 맞춰 하이픈을 넣습니다."""
    import re
    from decimal import Decimal, InvalidOperation

    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.casefold() in {"", "nan", "none", "null", "<na>", "-"}:
        return ""
    # 숫자로 읽힌 시트 값의 .0 및 지수 표기를 복원합니다.
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", text):
        try:
            number = Decimal(text)
            if number != number.to_integral_value():
                return ""
            text = format(number, "f").split(".")[0]
        except InvalidOperation:
            return ""
    # 전화번호의 기존 공백, 괄호, 하이픈은 제거 후 다시 배치합니다.
    if not re.fullmatch(r"[0-9\s()\-]+", text):
        return text  # 내선/메모 등이 있으면 숫자만 합쳐 잘못된 번호를 만들지 않습니다.
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return ""
    if not digits.startswith("0"):
        digits = "0" + digits

    if digits.startswith(("010", "070")):
        if len(digits) == 11:
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        return digits  # 자릿수가 맞지 않으면 숫자를 추가하거나 버리지 않습니다.

    area_codes = {
        "031", "032", "033", "041", "042", "043", "044",
        "051", "052", "053", "054", "055", "061", "062", "063", "064",
    }
    if digits.startswith("02") and len(digits) in (9, 10):
        return f"02-{digits[2:-4]}-{digits[-4:]}"
    if digits[:3] in area_codes and len(digits) in (10, 11):
        return f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
    return digits


def reset_inventory_filters():
    state = st.session_state
    for name, suffix in {
        "models": "model", "colors": "color", "dae": "dae",
        "so": "so", "owners": "owner",
    }.items():
        state["filter_selected_" + name] = []
        state["tmp_selected_" + name] = []
        state[f"filter_multiselect_{suffix}_0"] = []

    state['filter_serial_query'] = ''
    state.pop('_inv_serial_restore', None)
    state.pop('_inv_payload', None)
    state.pop('_inv_payload_key', None)
    state.pop('_inv_pending_query', None)
    state["filtered_data"] = None
    state["selected_idx"] = None
    state["clicked_store_name"] = None
    state["search_clicked"] = False
    state["_last_search_conditions"] = None
    state["_restore_last_result"] = False
    state["_recovery_fresh"] = False
    state["_filter_reset_token"] = str(time.time_ns())
    state.pop("filter_owner_keyword_message", None)
    state.pop("filter_owner_option_signature", None)

    # 검색용 파라미터만 삭제합니다.
    for key in ("m", "d", "c"):
        if key in st.query_params:
            del st.query_params[key]


def _begin_logout():
    # A callback runs before page routing; never rebuild the dashboard first.
    st.session_state["_logout_pending"] = True
    st.session_state["logged_in"] = False
    st.session_state["_explicit_logged_out"] = True
    st.session_state["needs_cookie_bake"] = False
    st.session_state["cookie_wait_count"] = 99
    st.session_state["username"] = ""
    st.session_state["role"] = ""
    st.session_state["_logout_attempt"] = st.session_state.get("_logout_attempt", 0) + 1


def _finish_logout():
    result = st.session_state.get("logout_cookie_cleanup", {}) or {}
    if result.get("done") is True:
        st.session_state.clear()
        st.session_state.update(logged_in=False, username="", role="",
                                cookie_wait_count=99, _explicit_logged_out=True)


@st.cache_resource
def _logout_component():
    import streamlit.components.v2 as components_v2
    return components_v2.component("logout_cleanup", js=r"""
    export default function({setStateValue, data}) {
        window.__inventoryLoggingOut=true;
        const recovery=window.__inventoryRecovery;
        if(recovery?.dispose) recovery.dispose();
        window.__inventoryRecovery=null;
        const banner=document.getElementById('inventory-connection-status');
        if(banner) {banner.hidden=true;banner.textContent='';}
        try {
            for(const key of Object.keys(sessionStorage)) {
                if(key.startsWith('inventory-recovery-v2:'+location.pathname+':')) sessionStorage.removeItem(key);
            }
        } catch (_) {}
        const names=['auth_token','auth_user','auth_role'];
        let attempts=0;
        const clear=()=>{
            try {
            for(const name of names) document.cookie=name+'=; Max-Age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Strict';
            const remaining=document.cookie.split(';').some(part=>names.includes(part.trim().split('=')[0]));
            if(!remaining) {setStateValue('done',true);return;}
            if(++attempts<5) timer=setTimeout(clear,200);
            else setStateValue('failed',true);
            } catch (_) {setStateValue('failed',true);}
        };
        let timer;
        clear();
        return ()=>clearTimeout(timer);
    }
    """)

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
st.markdown('<style>\n.stApp{background:#f4f7f3!important;background-image:none!important;color:#294a3c!important}\nheader[data-testid="stHeader"]{background:#f4f7f3!important}\n.stApp :is(.stMarkdown,.stText,p,span,label,h1,h2,h3,h4,h5,h6,li){color:#294a3c!important}\n.stApp .block-container{max-width:820px!important;padding-top:3.5rem!important;padding-bottom:1.4rem!important}\n.stApp section[data-testid="stSidebar"]{background:#edf3ed!important;border-color:#cfdacf!important}\ndiv[data-baseweb="select"]>div,div[data-baseweb="base-input"]>input,div[data-testid="stTextInput"] input{background:#fff!important;color:#294a3c!important;border:1px solid #cbd7ca!important;border-radius:6px!important}\ndiv[data-baseweb="select"] input{color:#294a3c!important;-webkit-text-fill-color:#294a3c!important}\ndiv[data-baseweb="select"]>div>div>div{color:#5d7467!important}\ninput::placeholder,textarea::placeholder{color:#738579!important;opacity:1!important}\ndiv[data-baseweb="popover"]>div,div[data-baseweb="popover"]>div>div,div[data-baseweb="popover"] ul,ul[role="listbox"],div[role="listbox"]{background:#fff!important;border-color:#cbd7ca!important}\ndiv[data-baseweb="popover"] :is(div,span,li),div[role="listbox"] :is(span,div){color:#294a3c!important}\nli[role="option"]{background:#fff!important;color:#294a3c!important}\nli[role="option"]:hover,li[role="option"][aria-selected="true"]{background:#e7eee3!important;color:#294a3c!important}\n.stApp span[data-baseweb="tag"]{background:#e6eddf!important;color:#294a3c!important;border:1px solid #c6d2bf!important}\n.stApp div.stButton>button,.stApp div[data-testid="stFormSubmitButton"]>button{background:#edf2e9!important;color:#365142!important;border:1px solid #ccd6c8!important;box-shadow:none!important}\n.stApp [data-testid="stFileUploadDropzone"]{background:#edf2e9!important;border:1px dashed #bccbb9!important}\n.stApp [data-testid="stFileUploadDropzone"] *{color:#365142!important}\n.stApp [data-testid="stFileUploadDropzone"] svg{fill:#365142!important}\n.stApp hr{background:#cbd7ca!important;height:1px!important}\n.stApp [data-testid="stExpander"]{border:0!important;border-radius:0!important;background:transparent!important}\n.stApp [data-testid="stExpander"] summary{padding:4px 0!important;min-height:36px!important}\n.stApp [data-testid="stExpander"] summary p{font-size:13px!important}\n.inv-brand{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0 13px;border-bottom:1px solid #cbd7ca;margin-bottom:2px;font-family:Arial,"Malgun Gothic",sans-serif;font-size:18px}\n.inv-file-heading{min-width:0;flex:1;display:grid;gap:3px}\n.stApp .inv-file-label{font-size:11px!important;color:#718575!important}\n.stApp .inv-file-name{display:block;color:#294a3c!important;font-size:16px;font-weight:500;line-height:1.45;overflow-wrap:anywhere;word-break:break-word}\n.stApp section[data-testid="stSidebar"] strong{color:#294a3c!important}\n.stApp .inv-brand #inv-connection-badge{font-size:12px!important;color:#287d53!important;white-space:nowrap}\n.stApp section[data-testid="stSidebar"] [data-testid="stRadio"]{margin-top:0!important}\n.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label{border-radius:7px;padding:7px 8px;margin:2px 0}\n.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:#e1ead8!important;border-left:3px solid #998347}\n.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked)>div:first-child{background:#998347!important}\n.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked)>div:first-child>div{background:#f8faf5!important}\n.stApp section[data-testid="stSidebar"] hr{margin:12px 0!important}\n.stApp section[data-testid="stSidebar"] [data-testid="stFileUploader"] :is(div,section){background:#edf3ed!important}\n.stApp section[data-testid="stSidebar"] [data-testid="stFileUploader"] button{background:#f8faf5!important;color:#365142!important;border:1px solid #bccbb9!important;box-shadow:none!important}\n.stApp section[data-testid="stSidebar"] [data-testid="stFileUploader"] button :is(p,span){color:#365142!important}\n.stApp section[data-testid="stSidebar"] [data-testid="stAlert"]{background:#e4eedf!important;border:1px solid #c9d9c3!important}\n.stApp [data-testid="stExpanderDetails"]{background:#f4f7f3!important;color:#294a3c!important}\n.stApp div[data-testid="stForm"]{background:#fbfcf9!important;border:1px solid #cbd7ca!important;box-shadow:none!important;border-radius:12px!important;padding:20px!important}\n.stApp .title-text{font-size:25px!important;font-weight:500!important;color:#294a3c!important;letter-spacing:0!important;margin:8px 0!important}\n.stApp .subtitle-text{font-size:13px!important;color:#6b7e6e!important;margin-bottom:18px!important}\n.st-key-inv_login_shell{max-width:420px!important;margin:20px auto!important}\n.stApp .logo-container img{max-width:130px!important}\n.stApp div[data-testid="stFormSubmitButton"]>button[data-testid]{background:#8d7837!important;border:1px solid #8d7837!important;border-radius:7px!important;box-shadow:none!important}\n.stApp [data-testid="stFormSubmitButton"]>button p{color:#fff!important;font-weight:400!important}\n.stApp .inv-auth-wait{background:#fbfcf9!important;border:1px solid #cbd7ca!important;box-shadow:0 4px 18px #294a3c12!important;padding:24px!important;width:min(360px,90vw)!important}\n.stApp .inv-auth-wait h3{font-size:18px!important;color:#826a2c!important}\n.inv-footer{border-top:1px solid #cbd7ca;padding-top:10px;margin-top:16px;display:flex;justify-content:space-between;gap:12px;font-size:11px}\n.st-key-inv_file_meta [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center!important}\n.st-key-inv_file_meta [data-testid="stColumn"]:first-child{min-width:0!important;flex:5 1 0!important;width:0!important}\n.st-key-inv_file_meta [data-testid="stColumn"]:last-child{min-width:78px!important;flex:1 1 0!important;width:0!important}\n.st-key-inv_refresh_sources div.stButton>button[data-testid]{background:transparent!important;border:0!important;padding:4px!important;min-height:32px!important;box-shadow:none!important}\n.st-key-inv_refresh_sources button p{font-size:12px!important}\n.st-key-inv_primary_filters [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:6px!important}\n.st-key-inv_primary_filters [data-testid="stColumn"],.st-key-inv_primary_filters [data-testid="column"]{min-width:0!important;flex:1 1 0!important;width:0!important}\n.st-key-inv_primary_filters [data-testid="stColumn"]:first-child{flex-grow:1.5!important}\n.st-key-inv_primary_filters [data-testid="stColumn"]:nth-child(2){flex-grow:.8!important}\n.st-key-inv_primary_filters [data-testid="stColumn"]:last-child{flex-grow:1.3!important}\n.st-key-inv_primary_filters label p{font-size:13px!important}\n.st-key-inv_primary_filters [data-baseweb="select"]>div{padding-left:5px!important;padding-right:3px!important;min-height:40px!important}\n.st-key-inv_primary_filters [data-baseweb="tag"]{max-width:100%!important;font-size:12px!important}\n.st-key-inv_primary_filters [data-baseweb="tag"] span[title]{font-size:12px!important}\n.st-key-inv_primary_filters [aria-label="Clear all"]{display:none!important}\n.st-key-inv_query_actions [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:8px!important}\n.st-key-inv_query_actions [data-testid="stColumn"]{min-width:0!important;flex:3 1 0!important;width:0!important}\n.st-key-inv_query_actions [data-testid="stColumn"]:last-child{flex-grow:1!important}\n.st-key-inventory_reset_filters div.stButton>button[data-testid]{background:transparent!important;color:#506b5b!important;border:0!important;font-size:12px!important;min-height:40px!important;padding:4px!important;box-shadow:none!important}\n.st-key-inventory_reset_filters button p{font-size:12px!important}\n.st-key-inventory_search_button div.stButton>button[data-testid]{background:#8d7837!important;color:#fff!important;border:1px solid #8d7837!important;min-height:40px!important;padding:6px!important;box-shadow:none!important}\n.st-key-inventory_search_button div.stButton>button[data-testid] p{color:#fff!important;font-weight:400!important;font-size:14px!important}\n.st-key-inventory_search_button div.stButton>button[data-testid]:disabled{background:#b6aa81!important;border-color:#b6aa81!important;opacity:1!important}\n#inventory-connection-status{background:#eef0df;color:#705e29;padding:9px;border-radius:6px;font-size:13px}\n@media(max-width:640px){\n .st-key-inv_primary_filters [data-testid="stHorizontalBlock"]{flex-direction:column!important;gap:2px!important;align-items:stretch!important}\n .st-key-inv_primary_filters [data-testid="stColumn"]:nth-child(n),\n .st-key-inv_primary_filters [data-testid="column"]:nth-child(n){width:100%!important;min-width:0!important;flex:0 0 auto!important;padding:0!important}\n .st-key-inv_primary_filters [data-testid="stVerticalBlock"]{gap:0!important}\n .st-key-inv_primary_filters [data-testid="stElementContainer"]{margin:0!important;padding:0!important}\n .st-key-inv_primary_filters [data-testid="stWidgetLabel"]{margin-bottom:0!important;min-height:18px!important;padding:0!important}\n .st-key-inv_primary_filters [data-testid="stWidgetLabel"] p{margin:0!important;line-height:18px!important}\n}\n\n.stApp .st-key-inv_admin_shell h2{font-size:23px!important;font-weight:500!important;padding:6px 0!important}\n.stApp .st-key-inv_admin_shell h3,.stApp .st-key-inv_admin_shell h4{font-size:17px!important;font-weight:500!important;padding:8px 0!important}\n.stApp .st-key-inv_admin_shell [data-baseweb="tab-list"]{background:transparent!important;gap:0!important;border-bottom:1px solid #cbd7ca!important}\n.stApp .st-key-inv_admin_shell [data-baseweb="tab"]{background:transparent!important;flex:1 1 0!important;padding:10px 6px!important;min-height:44px!important;white-space:nowrap!important}\n.stApp .st-key-inv_admin_shell [data-baseweb="tab"][aria-selected="true"]{background:#e7eee1!important}\n.stApp .st-key-inv_admin_shell [data-baseweb="tab-highlight"]{background:#8d7837!important}\n.stApp .st-key-inv_admin_shell [data-baseweb="tab"] p{font-size:13px!important}\n.stApp .st-key-inv_admin_shell [data-testid="stVerticalBlockBorderWrapper"]>div{border-color:#cbd7ca!important;border-radius:10px!important}\n.stApp .st-key-inv_admin_shell [data-testid="stAlert"]{background:#edf2e7!important;border:1px solid #ccd8c7!important;border-radius:7px!important}\n.stApp .st-key-inv_admin_shell [data-testid="stFileUploader"] button{background:#f8faf5!important;color:#365142!important;border:1px solid #bccbb9!important;box-shadow:none!important}\n.stApp .st-key-inv_admin_shell [data-testid="stFileUploader"] button :is(p,span){color:#365142!important}\n.stApp .st-key-inv_admin_shell [data-testid="stExpander"]{border-bottom:1px solid #cbd7ca!important;padding:4px 0!important}\n@media(max-width:640px){.stApp .st-key-inv_admin_shell [data-testid="stHorizontalBlock"]{flex-direction:column!important;gap:8px!important}.stApp .st-key-inv_admin_shell [data-testid="stColumn"]{width:100%!important;min-width:0!important;flex:1 1 auto!important}.stApp .st-key-inv_admin_shell div[data-testid="stForm"]{padding:14px!important}}\n\n\n.stApp .st-key-inv_admin_shell [data-testid="stExpander"]:is(:focus-within,:hover){border-color:#cbd7ca!important;outline:none!important;box-shadow:none!important}\n/* Override every old uploader descendant rule, including its hover/focus state. */\n.stApp [data-testid="stFileUploader"] :is(div,section,label,small){background-color:#edf3ed!important;background-image:none!important;color:#365142!important}\n.stApp [data-testid="stFileUploader"] :is(p,span){background-color:transparent!important;color:#365142!important}\n.stApp [data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"],\n.stApp [data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"]:hover,\n.stApp [data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"]:focus-within{background-color:#edf3ed!important;border:1px dashed #aebfa9!important;border-radius:8px!important;padding:14px!important}\n.stApp [data-testid="stFileUploader"] svg{fill:#62794f!important;color:#62794f!important}\n.stApp [data-testid="stFileUploader"] button,\n.stApp [data-testid="stFileUploader"] button:is(:hover,:focus,:active){background-color:#fbfcf8!important;color:#365142!important;border:1px solid #b9c9b3!important;box-shadow:none!important}\n.stApp [data-testid="stFileUploader"] button :is(p,span){color:#365142!important;background:transparent!important}\n.stApp .st-key-inv_admin_shell [data-testid="stExpander"] summary,\n.stApp .st-key-inv_admin_shell [data-testid="stExpander"] summary:is(:hover,:focus,:focus-visible){background:#eaf0e5!important;border:1px solid #cbd7ca!important;outline:none!important;box-shadow:none!important;border-radius:7px!important;padding:10px!important}\n\n</style>', unsafe_allow_html=True)

# [중요] 세션 상태 초기화 & 새로고침 로그인 유지 (오직 순수 Cookie 방식)
# ==============================================================================
if st.session_state.get("_logout_pending", False):
    st.info("로그아웃 중입니다…")
    cleanup = _logout_component()(
        key="logout_cookie_cleanup",
        data={"attempt": st.session_state.get("_logout_attempt", 0)},
        default={"done": False, "failed": False},
        on_done_change=_finish_logout,
        on_failed_change=lambda: None,
        height=0,
    )
    if cleanup.get("failed"):
        st.error("로그인 쿠키를 삭제하지 못했습니다. 다시 시도해 주세요.")
        if st.button("로그아웃 다시 시도"):
            st.session_state.pop("logout_cookie_cleanup", None)
            st.session_state["_logout_attempt"] = st.session_state.get("_logout_attempt", 0) + 1
            st.rerun()
    st.stop()

cookie_controller = CookieController()

# 1. 기본 상태 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.session_state['role'] = ""

# 🚀 [해결] CSS를 뿌리기 전에, 쿠키가 있는지부터 먼저 열어보고 상태를 확정합니다!
if not st.session_state['logged_in'] and not st.session_state.get('_explicit_logged_out', False):
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
    [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }

    /* 구글시트 캐시 로딩 시 뜨는 영문 "Running ..." 안내 숨김 */
    [data-testid="stSpinner"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    """

css_to_inject += "</style>"
st.markdown(css_to_inject, unsafe_allow_html=True)

# 2. 쿠키로 복구 
if not st.session_state['logged_in'] and not st.session_state.get('_explicit_logged_out', False):
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

# Dealership import: pure parsing/planning + atomic Google Sheets commit.
_DB_STORES = ['접점코드','보유처명','상권구분','대권역구분','사업장주소','집단구분','반추관설','대리점1','실적1','대리점2','실적1.1','x좌표','y좌표']
_DB_INSIDE = ['접점코드','거래처 애칭','거래처구분','거래처구분상세','소속담당그룹','거래처 실명','대표자명','팩스번호','사업자번호','거래상태','거래시작일','업태','업종','전화번호','우편번호','주소','등록일','X좌표','Y좌표']
_DB_TRACK = ['원본파일','자료기준일','반영시각','좌표기준주소','좌표상태','최근자료포함']


def _db_text(v):
    import math
    if v is None or (isinstance(v,float) and math.isnan(v)):
        return ''
    return str(v).strip()


def _db_address(v):
    value=_db_text(v)
    return '' if value.lower() in ('nan','none','null','<na>','-','미등록','주소 미등록') else value


def _db_key(v):
    import re
    return re.sub(r'\s+','',_db_text(v)).casefold()


def _db_schema(kind):
    if kind not in ('stores','stores_inside'):
        raise ValueError('자료 종류를 선택해주세요.')
    return list(_DB_STORES if kind=='stores' else _DB_INSIDE)


def _db_xy(x,y):
    import math
    try:
        x,y=float(x),float(y)
        return math.isfinite(x) and math.isfinite(y) and 124<=x<=132 and 33<=y<=39.5
    except (TypeError,ValueError):
        return False


def _db_frame(values):
    """Strict existing DB read; no positional guessing or duplicate-key deletion."""
    if not values:
        return pd.DataFrame()
    headers=[_db_text(v) for v in values[0]]
    used=[i for i,h in enumerate(headers) if h]
    names=[headers[i] for i in used]
    if len(names)!=len(set(names)):
        raise ValueError('기존 DB의 열 이름이 중복됩니다. 먼저 중복 열을 확인해주세요.')
    rows=[[_db_text(row[i]) if i<len(row) else '' for i in used] for row in values[1:] if any(_db_text(row[i]) for i in used if i<len(row))]
    frame=pd.DataFrame(rows,columns=names)
    if len(frame) and ('접점코드' not in frame or frame['접점코드'].eq('').any() or frame['접점코드'].duplicated().any()):
        raise ValueError('기존 DB의 접점코드가 누락되거나 중복됩니다. 자동 덮어쓰기를 중단합니다.')
    return frame


def _db_fingerprint(frame):
    import hashlib,json
    columns=[_db_text(c) for c in frame.columns]
    rows=[[_db_text(v) for v in row] for row in frame.itertuples(index=False,name=None)]
    return hashlib.sha256(json.dumps([columns,rows],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def _db_required(kind):
    return ['접점코드','보유처명','사업장주소','반추관설'] if kind=='stores' else ['접점코드','거래처 애칭','주소','전화번호']


def _db_aliases(kind):
    aliases={c:[c] for c in _db_schema(kind)}
    if kind=='stores':
        aliases.update({'접점코드':['접점코드','접점번호'],'보유처명':['접점명','보유처명'],'사업장주소':['사업장주소','주소'],'실적1':['판매건수','실적1'],'x좌표':['x좌표','경도'],'y좌표':['y좌표','위도']})
    else:
        aliases.update({'접점코드':['접점코드','접점번호'],'주소':['주소','사업장주소'],'X좌표':['X좌표','경도'],'Y좌표':['Y좌표','위도'],'비고':['비고']})
    return aliases


def _db_letter(index):
    text='';index+=1
    while index:index,part=divmod(index-1,26);text=chr(65+part)+text
    return text


def _db_auto_map(headers,kind):
    keys=[_db_key(v) for v in headers];mapping={}
    for field,labels in _db_aliases(kind).items():
        indices=[i for i,key in enumerate(keys) if key in {_db_key(v) for v in labels}]
        mapping[field]=indices[0] if len(indices)==1 else None
    return mapping


def _db_probe(raw_bytes,kind):
    # Probe only the first 30 rows; no worksheet writes or external requests.
    import io
    _db_schema(kind)
    book=pd.ExcelFile(io.BytesIO(raw_bytes),engine='openpyxl')
    candidates=[];sheets=list(book.sheet_names)
    try:
        for sheet in sheets:
            probe=pd.read_excel(book,sheet_name=sheet,header=None,nrows=30,dtype=str).fillna('')
            for index,row in probe.iterrows():
                mapping=_db_auto_map(list(row),kind)
                score=sum(mapping.get(field) is not None for field in _db_required(kind))
                if score>=2:candidates.append((score,sheet,int(index)+1))
    finally:book.close()
    if candidates:
        best=max(row[0] for row in candidates);best_rows=[row for row in candidates if row[0]==best]
        if len(best_rows)==1:return dict(sheets=sheets,sheet=best_rows[0][1],header_row=best_rows[0][2],automatic=True)
    return dict(sheets=sheets,sheet=sheets[0],header_row=1,automatic=False)


def _db_headers(raw_bytes,sheet,header_row):
    import io
    raw=pd.read_excel(io.BytesIO(raw_bytes),sheet_name=sheet,header=None,skiprows=header_row-1,nrows=6,dtype=str,engine='openpyxl').fillna('')
    if raw.empty:raise ValueError('선택한 제목행이 비어 있습니다.')
    return [_db_text(v) for v in raw.iloc[0]],raw.iloc[1:].reset_index(drop=True)


def _db_parse_table(raw,kind,column_map=None):
    headers=[_db_text(v) for v in raw.iloc[0]]
    keys=[_db_key(v) for v in headers]
    # Recognized source signatures prevent the common wrong-box upload.
    if kind=='stores' and '거래처애칭' in keys and '반추관설' not in keys:
        raise ValueError('대리점 거래처 파일입니다. 거래처 업로드 영역을 사용해주세요.')
    if kind=='stores_inside' and '반추관설' in keys and '거래처애칭' not in keys:
        raise ValueError('본사 판매여지도 파일입니다. 판매여지도 업로드 영역을 사용해주세요.')
    data=raw.iloc[1:].copy();data.columns=range(len(headers))
    choices=_db_auto_map(headers,kind)
    if column_map is not None:
        if set(column_map)-set(choices):raise ValueError('알 수 없는 DB 항목이 연결돼 있습니다.')
        choices.update(column_map)
    used=[value for value in choices.values() if value is not None]
    if any(isinstance(value,bool) or not isinstance(value,int) or not 0<=value<len(headers) for value in used):raise ValueError('선택한 원본 열을 다시 확인해주세요.')
    if len(used)!=len(set(used)):raise ValueError('같은 원본 열을 두 DB 항목에 중복 연결했습니다.')
    frame=pd.DataFrame(index=data.index);mapping={}
    for target,index in choices.items():
        if index is not None:
            mapping[target]=_db_letter(index)+'열 · '+(headers[index] or '이름 없는 열')
            frame[target]=data[index].map(_db_text)
    missing=[field for field in _db_required(kind) if field not in frame]
    if missing:raise ValueError('필수 열 연결 필요: '+', '.join(missing))
    for i,header in enumerate(headers):
        if i in used or header=='번호' or not data[i].map(_db_text).ne('').any():continue
        # Preserve added/unknown columns instead of dropping business data.
        label=header or '이름없는열_'+_db_letter(i)
        if header and keys.count(keys[i])>1:label+='_'+str(keys[:i+1].count(keys[i]))
        target='원본_'+label
        if target in frame:raise ValueError('보존할 원본 열 이름이 중복됩니다: '+label)
        frame[target]=data[i].map(_db_text)
    meaningful=frame.apply(lambda row:any(_db_text(v) for v in row),axis=1)
    frame=frame.loc[meaningful].copy()
    frame['접점코드']=frame['접점코드'].str.strip()
    if frame.empty:raise ValueError('반영할 거래처가 없습니다.')
    if frame['접점코드'].eq('').any():raise ValueError('접점코드가 빈 행이 있습니다. 해당 행을 확인해주세요.')
    if frame['접점코드'].duplicated().any():raise ValueError('접점코드가 중복됩니다. 마지막 행으로 임의 덮어쓰지 않습니다.')
    return frame.reset_index(drop=True),mapping


def _db_parse(raw_bytes,kind,sheet=None,header_row=None,column_map=None):
    import io
    if sheet is None or header_row is None:
        profile=_db_probe(raw_bytes,kind)
        if not profile['automatic']:raise ValueError('제목행을 자동 확정하지 못했습니다. 시트와 제목행을 직접 선택해주세요.')
        sheet,header_row=profile['sheet'],profile['header_row']
    if isinstance(header_row,bool) or not isinstance(header_row,int) or not 1<=header_row<=100:raise ValueError('제목행은 1~100행으로 지정해주세요.')
    raw=pd.read_excel(io.BytesIO(raw_bytes),sheet_name=sheet,header=None,skiprows=header_row-1,dtype=str,engine='openpyxl').fillna('')
    if raw.empty:raise ValueError('선택한 제목행에 데이터가 없습니다.')
    frame,mapping=_db_parse_table(raw,kind,column_map)
    return frame,dict(sheet=sheet,header_row=header_row,mapping=mapping,rows=len(frame))


def _db_plan(old,incoming,kind,filename,source_date,now):
    """Upsert by ID; keep omitted rows/custom columns, invalidate changed-address XY."""
    schema=_db_schema(kind);addr='사업장주소' if kind=='stores' else '주소'
    x,y=('x좌표','y좌표') if kind=='stores' else ('X좌표','Y좌표')
    old=old.copy().fillna('')
    if not old.empty:
        if '접점코드' not in old:raise ValueError('기존 DB에 접점코드가 없습니다.')
        old['접점코드']=old['접점코드'].map(_db_text)
        if old['접점코드'].duplicated().any() or old['접점코드'].eq('').any():raise ValueError('기존 DB 접점코드 중복/누락으로 저장을 중단합니다.')
    columns=list(dict.fromkeys(schema+[str(c) for c in old.columns]+[str(c) for c in incoming.columns]+_DB_TRACK))
    old=old.reindex(columns=columns,fill_value='')
    existing={row['접점코드']:row for row in old.to_dict('records')}
    result={k:dict(v) for k,v in existing.items()}
    for row in result.values():row['최근자료포함']='이전자료유지'
    changes=[]
    source_date=str(source_date)
    for fresh in incoming.to_dict('records'):
        code=fresh['접점코드'];previous=existing.get(code);row=dict(previous) if previous else dict.fromkeys(columns,'')
        old_address=_db_address(row.get(addr));new_address=_db_address(fresh.get(addr))
        changed_address=_db_key(old_address)!=_db_key(new_address)
        # No accidental downgrade by importing an older dated source.
        previous_date=_db_text(row.get('자료기준일'))
        if previous_date and source_date<previous_date:raise ValueError('더 최신 자료가 이미 반영된 거래처가 있습니다. 자료 기준일을 확인해주세요.')
        for col,value in fresh.items():
            if col not in (x,y):row[col]=_db_text(value)
        row[addr]=new_address
        tracked_address=_db_text(row.get('좌표기준주소'))
        trusted_old=bool(new_address) and _db_xy(row.get(x),row.get(y)) and not changed_address and (not tracked_address or _db_key(tracked_address)==_db_key(new_address))
        # Supplied XY is only accepted from named coordinate columns, never fallbacks.
        if new_address and _db_xy(fresh.get(x),fresh.get(y)):
            row[x],row[y]=_db_text(fresh[x]),_db_text(fresh[y]);row['좌표상태']='제공좌표'
        elif not trusted_old:
            row[x]=row[y]=''
            row['좌표상태']='주소누락' if not new_address else '좌표대기'
        else:row['좌표상태']='기존좌표유지'
        row['좌표기준주소']=new_address if _db_xy(row.get(x),row.get(y)) else ''
        row.update({'원본파일':filename,'자료기준일':source_date,'반영시각':now,'최근자료포함':'포함'})
        status='신규' if previous is None else '주소변경' if changed_address else '정보변경' if any(_db_text(previous.get(c))!=_db_text(row.get(c)) for c in incoming.columns if c not in (x,y)) else '유지'
        changes.append({'접점코드':code,'거래처':row.get('보유처명') or row.get('거래처 애칭'),'변경':status,'이전 주소':old_address,'새 주소':new_address,'좌표상태':row['좌표상태']})
        result[code]=row
    out=pd.DataFrame(list(result.values()),columns=columns).fillna('')
    stats={key:sum(c['변경']==key for c in changes) for key in ['신규','주소변경','정보변경','유지']}
    stats.update({'이전자료유지':len(set(existing)-set(incoming['접점코드'])),'좌표대기':int(out['좌표상태'].eq('좌표대기').sum()),'주소누락':sum(not _db_text(v) for v in incoming[addr])})
    return out,pd.DataFrame(changes),stats


def _db_revision():
    import os
    try:
        stat=os.stat('db_revision.txt')
        return (stat.st_mtime_ns,stat.st_size)
    except OSError:return (0,0)


def _db_touch_revision():
    import os,tempfile,uuid
    fd,path=tempfile.mkstemp(prefix='.db-revision-',dir='.')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as file:file.write(uuid.uuid4().hex)
        os.replace(path,'db_revision.txt')
    finally:
        if os.path.exists(path):os.remove(path)


def _db_open():
    # Same existing authenticated connection; no additional account/key required.
    return get_gsheets_connection().client._open_spreadsheet(spreadsheet=GSHEET_URL)


def _db_read(kind):
    book=_db_open();ws=book.worksheet(kind)
    return _db_frame(ws.get_all_values(value_render_option='FORMULA'))


def _db_commit(kind,expected,out):
    """Backup + data write are a single Sheets batch. No clear-then-write gap."""
    import uuid
    _db_schema(kind)
    book=_db_open();ws=book.worksheet(kind)
    current=_db_frame(ws.get_all_values(value_render_option='FORMULA'))
    if _db_fingerprint(current)!=expected:
        raise ValueError('미리보기 이후 DB가 변경됐습니다. 다시 비교해주세요.')
    stamp=datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S')
    backup=f'_backup_{kind}_{stamp}_{uuid.uuid4().hex[:6]}'
    values=[list(out.columns)]+[[_db_text(v) for v in row] for row in out.itertuples(index=False,name=None)]
    rows=max(ws.row_count,len(values));cols=max(ws.col_count,len(out.columns))
    original_by_id={row.get('접점코드'):row for row in current.to_dict('records')}
    def cell_values(index,row):
        previous=original_by_id.get(row[out.columns.get_loc('접점코드')],{}) if index else {}
        return [{'userEnteredValue':{('formulaValue' if index and str(value).startswith('=') and previous.get(out.columns[col])==value else 'stringValue'):_db_text(value)}} for col,value in enumerate(row)]
    requests=[{'duplicateSheet':{'sourceSheetId':ws.id,'newSheetName':backup}},
              {'updateSheetProperties':{'properties':{'sheetId':ws.id,'gridProperties':{'rowCount':rows,'columnCount':cols}},'fields':'gridProperties.rowCount,gridProperties.columnCount'}},
              {'updateCells':{'range':{'sheetId':ws.id,'startRowIndex':0,'endRowIndex':rows,'startColumnIndex':0,'endColumnIndex':cols},
                              'rows':[{'values':cell_values(i,row)} for i,row in enumerate(values)], 'fields':'userEnteredValue'}}]
    # Sheets applies this batch atomically. Concurrent edits between the read and
    # this request remain a limitation; we never claim a cross-client lock.
    book.batch_update({'requests':requests})
    verified=_db_frame(ws.get_all_values(value_render_option='FORMULA'))
    if _db_fingerprint(verified)!=_db_fingerprint(out):
        raise RuntimeError('반영 후 확인값이 다릅니다. 다시 저장하지 말고 백업 시트 '+backup+'를 확인해주세요.')
    _db_touch_revision()
    st.session_state.pop('_inv_payload_key',None);st.session_state.pop('_inv_option_key',None)
    st.cache_data.clear()
    audit=globals().get('add_audit_log')
    if callable(audit):
        try:audit(st.session_state.get('username','admin'),'거래처 자료 반영',f'{kind} {len(out)}건 · 백업 {backup}')
        except Exception:pass
    return backup


def _db_geocode(address):
    import urllib.request,urllib.parse,json
    cid=globals().get('NAVER_CLIENT_ID');secret=globals().get('NAVER_CLIENT_SECRET')
    if not cid or not secret:raise ValueError('주소 변환 API 설정을 확인해주세요.')
    request=urllib.request.Request('https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query='+urllib.parse.quote(address),headers={'X-NCP-APIGW-API-KEY-ID':cid,'X-NCP-APIGW-API-KEY':secret})
    with urllib.request.urlopen(request,timeout=5) as response:body=json.load(response)
    found=body.get('addresses',[])
    if not found:return None
    point=found[0]
    # Do not silently accept an ambiguous list of candidate addresses.
    if len(found)!=1:return None
    return (point['x'],point['y']) if _db_xy(point.get('x'),point.get('y')) else None


def _db_geocode_batch(frame,kind,geocoder,limit=20):
    addr='사업장주소' if kind=='stores' else '주소';x,y=('x좌표','y좌표') if kind=='stores' else ('X좌표','Y좌표')
    import time
    out=frame.copy();count=success=failed=0;memo={};deadline=time.monotonic()+20
    for index,row in out.iterrows():
        address=_db_address(row.get(addr))
        if not address or _db_xy(row.get(x),row.get(y)) or _db_text(row.get('좌표상태'))=='좌표확인필요':continue
        if count>=limit or time.monotonic()>=deadline:break
        count+=1
        try:
            key=_db_key(address)
            if key not in memo:memo[key]=geocoder(address)
            point=memo[key]
            if not point:raise ValueError('단일 좌표 없음')
            out.at[index,x],out.at[index,y]=map(str,point);out.at[index,'좌표기준주소']=address;out.at[index,'좌표상태']='좌표변환완료';success+=1
        except Exception:
            out.at[index,'좌표상태']='좌표확인필요';failed+=1
    return out,dict(attempted=count,success=success,failed=failed)


def _db_upload_panel():
    st.markdown('#### 거래처 자료 갱신')
    st.caption('파일명으로 구분하지 않습니다. 각 업로드 영역에서 파일 내부의 열을 검증합니다.')
    with st.expander('본사 판매여지도 업로드 → stores',expanded=False):
        _db_upload_source('stores')
    with st.expander('대리점 거래처 업로드 → inside',expanded=False):
        _db_upload_source('stores_inside')


def _db_upload_source(kind):
    import hashlib,json
    prefix='db_'+kind+'_'
    st.caption('저장 대상: '+kind+' · 기존 거래처는 자동 삭제하지 않습니다.')
    source_date=st.date_input('자료 기준일',value=datetime.now(timezone(timedelta(hours=9))).date(),key=prefix+'date')
    uploaded=st.file_uploader('본사 판매여지도 원본 엑셀' if kind=='stores' else '대리점 거래처 원본 엑셀',type=['xlsx'],key=prefix+'file')
    preview_key=prefix+'preview'
    if uploaded:
        data=uploaded.getvalue();file_key=hashlib.sha256(data).hexdigest()
        try:
            if st.session_state.get(prefix+'profile_key')!=file_key:
                st.session_state[prefix+'profile']=_db_probe(data,kind)
                st.session_state[prefix+'profile_key']=file_key
            profile=st.session_state[prefix+'profile']
            # A new file/layout has independent widget state. Never reuse a column
            # index from a previous file just because its filename is identical.
            file_prefix=prefix+file_key[:16]+'_'
            if not profile['automatic']:st.warning('제목행을 자동 확정하지 못했습니다. 아래에서 직접 지정해주세요.')
            sheet=st.selectbox('데이터 시트',profile['sheets'],index=profile['sheets'].index(profile['sheet']),key=file_prefix+'sheet')
            header_row=int(st.number_input('제목행 번호',min_value=1,max_value=100,value=profile['header_row'],step=1,key=file_prefix+'header'))
            layout=(file_key,sheet,header_row)
            if st.session_state.get(prefix+'layout')!=layout:
                st.session_state[prefix+'headers']=_db_headers(data,sheet,header_row)
                st.session_state[prefix+'layout']=layout
            headers,sample=st.session_state[prefix+'headers']
            defaults=_db_auto_map(headers,kind);mapping={}
            layout_key=hashlib.sha256(json.dumps(layout).encode()).hexdigest()[:12]
            with st.expander('열 연결 확인·수정 · 열 이름이 바뀌면 여기서 선택'):
                st.caption('필수 항목(*)을 확인하세요. 선택 안 함인 부가 항목은 기존 DB 값을 유지합니다.')
                for field,default in defaults.items():
                    options=[-1]+list(range(len(headers)))
                    selected_column=st.selectbox(field+(' *' if field in _db_required(kind) else ''),options,index=options.index(default if default is not None else -1),format_func=lambda i:'선택 안 함' if i==-1 else _db_letter(i)+'열 · '+(headers[i] or '이름 없는 열'),key=prefix+layout_key+'_'+field)
                    mapping[field]=None if selected_column==-1 else selected_column
                st.caption('선택한 제목행 아래의 원본 샘플')
                view=sample.copy();view.columns=[_db_letter(i)+' · '+(v or '이름 없음') for i,v in enumerate(headers)]
                st.dataframe(view,hide_index=True,use_container_width=True,height=180)
            missing=[field for field in _db_required(kind) if mapping[field] is None]
            chosen=[i for i in mapping.values() if i is not None]
            duplicate=len(chosen)!=len(set(chosen))
            if missing:st.warning('열 연결 필요: '+', '.join(missing))
            if duplicate:st.error('같은 원본 열을 여러 DB 항목에 연결할 수 없습니다.')
            token=hashlib.sha256(json.dumps([file_key,kind,str(source_date),sheet,header_row,mapping],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if st.button('변경사항 확인',key=prefix+'preview_button',disabled=bool(missing or duplicate),use_container_width=True):
                try:
                    incoming,info=_db_parse(data,kind,sheet,header_row,mapping);old=_db_read(kind)
                    now=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
                    out,changes,stats=_db_plan(old,incoming,kind,uploaded.name,source_date,now)
                    st.session_state[preview_key]=dict(token=token,expected=_db_fingerprint(old),out=out,changes=changes,stats=stats,info=info)
                except Exception as error:
                    st.session_state.pop(preview_key,None);st.error('반영하지 않았습니다: '+str(error))
            preview=st.session_state.get(preview_key)
            if preview and preview['token']!=token:
                st.session_state.pop(preview_key,None);preview=None
            if preview:
                info=preview['info']
                st.caption(f"{info['sheet']} · 제목 {info['header_row']}행 · {info['rows']:,}개 거래처")
                st.write(' · '.join(f'{k} {v:,}건' for k,v in preview['stats'].items()))
                st.dataframe(preview['changes'],hide_index=True,use_container_width=True,height=260)
                st.caption('기존 DB 백업 후 반영합니다. 주소가 바뀌면 기존 좌표를 그대로 쓰지 않습니다.')
                if st.button('백업 후 반영',key=prefix+'apply_button',type='primary',use_container_width=True):
                    try:
                        backup=_db_commit(kind,preview['expected'],preview['out'])
                        st.session_state[prefix+'success']='반영 완료 · 백업: '+backup
                        st.session_state.pop(preview_key,None);st.rerun()
                    except Exception as error:st.error('완료 여부를 확인하지 못했습니다. DB/백업을 확인한 뒤 다시 비교해주세요. '+str(error))
        except Exception as error:
            st.session_state.pop(preview_key,None);st.error('파일을 확인해주세요: '+str(error))
    else:
        st.session_state.pop(preview_key,None)
    if st.session_state.get(prefix+'success'):st.success(st.session_state[prefix+'success'])
    if st.button('현재 반영 상태 확인',key=prefix+'status',use_container_width=True):
        try:
            current=_db_read(kind);st.write(f'현재 {len(current):,}개 거래처')
            metadata=[c for c in ['원본파일','자료기준일','반영시각'] if c in current]
            if metadata:st.dataframe(current[metadata].drop_duplicates().tail(10),hide_index=True,use_container_width=True)
        except Exception as error:st.error('상태 확인 실패: '+str(error))
    st.caption('좌표는 관리자 화면에서 최대 20건씩 처리합니다. 조회 시 API를 호출하지 않습니다.')
    if st.button('미처리 좌표 생성 · 최대 20건',key=prefix+'geocode',use_container_width=True):
        try:
            with st.spinner('좌표 확인 중…'):
                current=_db_read(kind);expected=_db_fingerprint(current)
                out,stats=_db_geocode_batch(current,kind,_db_geocode)
                if stats['attempted']:
                    backup=_db_commit(kind,expected,out)
                    st.success(f"완료 {stats['success']}건 · 확인 필요 {stats['failed']}건 · 백업 {backup}")
                else:st.info('처리할 주소가 없습니다. 실패한 주소는 확인 후 원본을 다시 반영하면 재시도할 수 있습니다.')
        except Exception as error:st.error('좌표 처리 실패: '+str(error))

# Dashboard helpers: only read inventory data; never update Google Sheets.
def _inv_columns(frame):
    names = {str(c).replace('▼', '').strip(): c for c in frame.columns}
    def find(*parts):
        for part in parts:
            if part in names:
                return names[part]
        return next((c for c in frame.columns if any(p in str(c) for p in parts)), None)
    return dict(owner=find('보유처'), model=find('모델명'), color=find('색상명', '색상'),
                kind=find('모델유형', '유형'), status=find('재고상태', '상태', '등급'),
                target=find('출고일'), serial=find('일련번호'))


def _inv_sales_mask(values):
    return values.fillna('').astype(str).str.strip().str.match(r'^도매\s*[-－–—]', na=False)


def _inv_text(value):
    if value is None or pd.isna(value):
        return ''
    value = str(value).strip()
    return '' if value.lower() in ('nan', 'none', 'null', '<na>', '-') else value


def _inv_upload_info(data_path, name_path=None):
    """Read real persisted upload metadata; never use the current query time."""
    import os
    info = dict(filename='재고표가 없습니다', time_text='사이드메뉴에서 재고표를 업로드해주세요.', exists=False)
    if not data_path or not os.path.isfile(data_path):
        return info
    try:
        stat = os.stat(data_path)
    except OSError:
        return info
    info['exists'] = True
    info['filename'] = os.path.basename(data_path)
    if name_path:
        try:
            with open(name_path, encoding='utf-8') as file:
                info['filename'] = file.read().strip() or info['filename']
        except (OSError, UnicodeError):
            pass
    kst = timezone(timedelta(hours=9))
    try:
        with open(data_path + '.upload.json', encoding='utf-8') as file:
            meta = json.load(file)
        if meta.get('version') == [stat.st_mtime_ns, stat.st_size]:
            timestamp = datetime.fromisoformat(meta['uploaded_at'])
            if timestamp.tzinfo is not None:
                info['filename'] = str(meta.get('filename') or info['filename'])
                info['time_text'] = '업로드: ' + timestamp.astimezone(kst).strftime('%Y-%m-%d %H:%M:%S') + ' (한국시간)'
                return info
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    # Old inventories have no historical upload timestamp. State the fallback.
    info['time_text'] = '파일 저장: ' + datetime.fromtimestamp(stat.st_mtime, kst).strftime('%Y-%m-%d %H:%M:%S') + ' (한국시간 · 이전 업로드 기록 없음)'
    return info


def _inv_record_upload(data_path, filename):
    """Atomic metadata sidecar; original name text remains backward compatible."""
    import os, tempfile
    stat = os.stat(data_path)
    meta = dict(filename=filename, uploaded_at=datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
                version=[stat.st_mtime_ns, stat.st_size])
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=os.path.dirname(os.path.abspath(data_path)),
                                         prefix='.inventory-upload-', suffix='.tmp', delete=False) as file:
            temporary = file.name
            json.dump(meta, file, ensure_ascii=False)
        os.replace(temporary, data_path + '.upload.json')
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def _inv_map_tile_url(default_url):
    import re
    from urllib.parse import quote
    try:
        settings=st.secrets.get('maps',{})
        key=settings.get('vworld_key') or st.secrets.get('VWORLD_API_KEY')
    except Exception:key=None
    if not key:return default_url
    return re.sub(r'(/wmts/1\.0\.0/)[^/]+',lambda match:match.group(1)+quote(str(key).strip(),safe=''),default_url)


def _inv_source_header():
    from html import escape
    info = _inv_upload_info(globals().get('DATA_FILE'), globals().get('META_FILE'))
    st.markdown('<div class="inv-brand"><div class="inv-file-heading"><span class="inv-file-label">현재 재고표</span><strong class="inv-file-name">'
                + escape(info['filename']) + '</strong></div><span id="inv-connection-badge">● 연결됨</span></div>', unsafe_allow_html=True)
    with st.container(key='inv_file_meta'):
        left, right = st.columns([5,1], gap='small')
        with left:
            st.caption(info['time_text'])
        with right:
            if st.button('⟳ 갱신', key='inv_refresh_sources', use_container_width=True):
                st.cache_data.clear()
                st.session_state.pop('_inv_payload_key',None)
                st.session_state.pop('_inv_option_key',None)
                st.rerun(scope='app')
    return info


def _inv_filter(frame, conditions, cols):
    """Vectorized filtering once per query. Unassigned salespeople are references.

    Reference stock respects model/color/owner/serial, but is not silently included
    in the selected region's store quantity. No location is fabricated for sales.
    """
    mask = pd.Series(True, index=frame.index)
    for key, column in [('models', cols['model']), ('colors', cols['color']),
                        ('owners', cols['owner'])]:
        selected = conditions.get(key) or []
        if selected and column:
            mask &= frame[column].astype(str).isin(selected)
    serial = str(conditions.get('serial') or '').strip()
    if serial:
        if cols['serial']:
            mask &= frame[cols['serial']].fillna('').astype(str).str.contains(serial, regex=False, na=False)
        else:
            mask &= False
    sales = _inv_sales_mask(frame[cols['owner']])
    zone = frame.get('대분류_캐시', pd.Series('미분류', index=frame.index)).fillna('미분류')
    region_mask = pd.Series(True, index=frame.index)
    zones = conditions.get('dae') or []
    if zones:
        region_mask &= zone.isin(zones)
    small = conditions.get('so') or []
    if small:
        so = frame.get('소분류_캐시', pd.Series('미분류', index=frame.index))
        unknown = frame.get('소분류_유추불가', pd.Series(False, index=frame.index)).fillna(False)
        so_mask = so.isin(small) | unknown
        if '집단상가' in small:
            so_mask |= zone.eq('집단상가')
        region_mask &= so_mask
    matched = frame.loc[mask & region_mask].copy()
    # Only unassigned salespeople excluded by area filters are supplementary.
    unassigned = zone.astype(str).isin(['', '미분류', 'nan', 'None', '<NA>'])
    reference = frame.loc[mask & sales & unassigned & ~region_mask].copy()
    return matched, reference


def _inv_payload(matched, reference, cols, conditions, version, tile_url):
    """Compact arrays instead of pre-rendered HTML for every store popup."""
    import math
    buckets = {}
    sales_mask = _inv_sales_mask(matched[cols['owner']])
    stores = matched.loc[~sales_mask]
    grouped_inputs = [(stores, 'store', False), (matched.loc[sales_mask], 'sales', False),
                      (reference, 'sales', True)]
    for data, category, is_reference in grouped_inputs:
        item_cols = [cols.get(k) for k in ('model', 'color', 'kind', 'status', 'target', 'serial')]
        field_cols = [cols['owner'], *item_cols, '대분류_캐시', 'cached_lat', 'cached_lon',
                      '사업장주소', '위치표시방식', '추정지역', 'K노트 연락처']
        selected = data.reindex(columns=[c or '__missing__' for c in field_cols])
        # One tuple pass; no per-owner dataframe copies, apply(), or numeric casts.
        for row in selected.itertuples(index=False, name=None):
            name = _inv_text(row[0]) or '보유처 미등록'
            key = (name, category, is_reference)
            if key not in buckets:
                buckets[key] = dict(items=[], zones={}, addresses={}, phones={}, guesses={}, modes=set(), lat=None, lon=None)
            b = buckets[key]
            b['items'].append([_inv_text(v) for v in row[1:7]])
            b['zones'][_inv_text(row[7]) or '미분류'] = None
            for field, index in [('addresses',10), ('guesses',12), ('phones',13)]:
                value = _inv_text(row[index])
                if value:
                    b[field][value] = None
            b['modes'].add(_inv_text(row[11]))
            if category == 'store' and b['lat'] is None:
                try:
                    lat, lon = float(row[8]), float(row[9])
                    if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180 and lat!=0 and lon!=0:
                        b['lat'], b['lon'] = lat, lon
                except (TypeError, ValueError):
                    pass
    records = []
    for (name, category, is_reference), b in buckets.items():
            items, zone_values = b['items'], list(b['zones'])
            zone = zone_values[0] if len(zone_values) == 1 else '복수권역'
            lat, lon = b['lat'], b['lon']
            addresses = list(b['addresses'])
            address = addresses[0] if addresses else ''
            missing = address in ('', '미등록', '주소 미등록')
            modes = b['modes']
            approximate = '지역추정' in modes
            guesses = list(b['guesses'])
            if category == 'sales':
                address_label = '영업사원 보유 · 위치 마커 제외'
            elif approximate:
                address_label = '추정 위치: ' + (' / '.join(guesses) or zone) + ' 인근'
            else:
                address_label = address if not missing else '주소 미등록'
            phones = [v for v in b['phones'] if v not in ('미등록', '미확인')]
            ident = hashlib.sha256((category + '\x1f' + name + '\x1f' + str(is_reference)).encode()).hexdigest()[:20]
            records.append(dict(id=ident, name=name, category=category, reference=is_reference,
                                zone=zone, lat=lat, lon=lon, address=address_label,
                                missing=missing, approx=approximate, phone=' / '.join(phones) or '미등록',
                                items=items, qty=len(items)))
    return dict(version=version, records=records, conditions=conditions,
                matched=len(matched), storeQty=len(stores), salesQty=int(sales_mask.sum()),
                referenceQty=len(reference), tileUrl=tile_url,
                created=datetime.now(timezone(timedelta(hours=9))).strftime('%m/%d %H:%M:%S'))


def _inv_asset_version():
    return hashlib.sha256((_INV_RESULTS_JS+'\x00'+_INV_RESULTS_CSS).encode()).hexdigest()[:12]


@st.cache_resource(max_entries=4)
def _inv_results_component(asset_version):
    import streamlit.components.v2 as components_v2
    return components_v2.component('inventory_results_'+asset_version,
                                  html='<div class="inventory-results-root"></div>',
                                  css=_INV_RESULTS_CSS, js=_INV_RESULTS_JS)


def _inv_region_options(frame,zones):
    subset=frame
    if zones:
        zone=frame.get('대분류_캐시',pd.Series('미분류',index=frame.index))
        subset=frame.loc[zone.isin(zones)]
    if '소분류_캐시' not in subset:return []
    return sorted({_inv_text(v) for v in subset['소분류_캐시'].dropna().unique() if _inv_text(v)})


def _inv_facet_options(frame,cols,models,colors,zones=None,small=None):
    subset=frame
    if models:subset=subset.loc[subset[cols['model']].astype(str).isin(models)]
    available_colors=sorted({_inv_text(v) for v in subset[cols['color']].dropna().unique() if _inv_text(v)}) if cols['color'] else []
    colors=[v for v in colors if v in available_colors]
    if colors and cols['color']:subset=subset.loc[subset[cols['color']].astype(str).isin(colors)]
    zone=subset.get('대분류_캐시',pd.Series('미분류',index=subset.index))
    if zones:subset=subset.loc[zone.isin(zones)]
    if small:
        region=subset.get('소분류_캐시',pd.Series('미분류',index=subset.index))
        unknown=subset.get('소분류_유추불가',pd.Series(False,index=subset.index)).fillna(False)
        region_mask=region.isin(small)|unknown
        if '집단상가' in small:region_mask|=zone.reindex(subset.index).eq('집단상가')
        subset=subset.loc[region_mask]
    owners=sorted({_inv_text(v) for v in subset[cols['owner']].dropna().unique() if _inv_text(v)})
    return available_colors,owners


@st.fragment
def _inv_dashboard(frame, file_version, tile_url):
    from html import escape
    cols = _inv_columns(frame)
    if not cols['model'] or not cols['owner']:
        st.error('재고표에서 모델명/보유처 열을 찾지 못했습니다. 기존 파일은 수정하지 않았습니다.')
        return
    option_key = ('inventory-ui-v4', file_version, frame.attrs.get('_db_revision'))
    if st.session_state.get('_inv_option_key') != option_key:
        def values(column):
            return sorted({_inv_text(v) for v in frame[column].dropna().unique() if _inv_text(v)}) if column else []
        present = values('대분류_캐시') if '대분류_캐시' in frame else []
        zones = [v for v in CANONICAL_DAE if v in present] + [v for v in present if v not in CANONICAL_DAE]
        st.session_state['_inv_options'] = dict(models=values(cols['model']), colors=values(cols['color']),
                                                dae=zones, so=values('소분류_캐시') if '소분류_캐시' in frame else [],
                                                owners=values(cols['owner']))
        st.session_state['_inv_option_key'] = option_key
        # Only the options are rebuilt; preserve the last query's filters across uploads.
    options = dict(st.session_state['_inv_options'])
    selected_models=st.session_state.get('filter_selected_models')
    if not isinstance(selected_models,list):selected_models=list(st.query_params.get_all('m'))
    selected_models=[v for v in selected_models if v in options['models']]
    selected_colors=st.session_state.get('filter_selected_colors')
    if not isinstance(selected_colors,list):selected_colors=list(st.query_params.get_all('c'))
    selected_zones=st.session_state.get('filter_selected_dae')
    if not isinstance(selected_zones,list):selected_zones=list(st.query_params.get_all('d'))
    selected_zones=[v for v in selected_zones if v in options['dae']]
    options['so']=_inv_region_options(frame,selected_zones)
    selected_small=st.session_state.get('filter_selected_so',[])
    selected_small=[v for v in selected_small if v in options['so']] if isinstance(selected_small,list) else []
    options['colors'],options['owners']=_inv_facet_options(frame,cols,selected_models,selected_colors,selected_zones,selected_small)
    suffixes = dict(models='model', colors='color', dae='dae', so='so', owners='owner')
    qp = dict(models='m', colors='c', dae='d')
    for field, suffix in suffixes.items():
        selected_key = 'filter_selected_' + field
        if selected_key not in st.session_state:
            st.session_state[selected_key] = list(st.query_params.get_all(qp[field])) if field in qp else []
        if not isinstance(st.session_state[selected_key], list):
            st.session_state[selected_key] = []
        selected = [v for v in st.session_state[selected_key] if v in options[field]]
        st.session_state[selected_key] = selected
        widget = 'filter_multiselect_' + suffix + '_0'
        # Rehydrate before the widget is mounted. Mirror values survive collapsed UI.
        if st.session_state.get(widget) != selected:
            st.session_state[widget] = selected
    st.session_state.setdefault('filter_serial_query', '')
    if st.session_state.get('_inv_serial_restore') is not None:
        st.session_state['filter_serial_query'] = st.session_state.pop('_inv_serial_restore')

    def commit(field):
        widget = 'filter_multiselect_' + suffixes[field] + '_0'
        st.session_state['filter_selected_' + field] = list(st.session_state.get(widget, []))
        st.session_state['_recovery_fresh'] = False

    def picker(field, label):
        return st.multiselect(label, options[field], key='filter_multiselect_' + suffixes[field] + '_0',
                              placeholder='전체', on_change=commit, args=(field,))

    _inv_source_header()
    with st.container(key='inv_primary_filters'):
        a, b, c = st.columns([1.5, 1, 1.2], gap='small')
        with a:
            picker('models', '모델')
        with b:
            picker('colors', '색상')
        with c:
            picker('dae', '권역')
    selected_labels = [v for f in ('models', 'colors', 'dae')
                       for v in st.session_state.get('filter_selected_' + f, [])]
    if selected_labels:
        st.caption('선택 · ' + ' / '.join(selected_labels))
    with st.expander('상세조건', expanded=False):
        picker('so', '지역(소분류)')
        picker('owners', '보유처')
        st.text_input('일련번호 · 부분검색', key='filter_serial_query', placeholder='전체 번호 또는 일부 입력',
                      disabled=not bool(cols['serial']))
        if not cols['serial']:
            st.caption('이 재고표에는 일련번호 열이 없습니다.')
    draft = {field: list(st.session_state['filter_selected_' + field]) for field in suffixes}
    draft['serial'] = st.session_state.get('filter_serial_query', '').strip()
    with st.container(key='inv_query_actions'):
        left, right = st.columns([3, 1], gap='small')
    with left:
        requested = st.button('조회하기', key='inventory_search_button', type='primary', use_container_width=True,
                              disabled=not (draft['models'] or draft['owners'] or draft['serial']))
    with right:
        st.button('조건 초기화', key='inventory_reset_filters', on_click=reset_inventory_filters,
                  use_container_width=True)
    st.markdown('<div id="inventory-connection-status" role="status" aria-live="polite" hidden></div>',
                unsafe_allow_html=True)
    pending = st.session_state.pop('_inv_pending_query', None)
    if isinstance(pending, dict):
        draft = pending
        requested = True
    # Another user can upload a new inventory while this fragment stays alive.
    # Check only metadata on query; reload once rather than searching stale data.
    inventory_path = globals().get('DATA_FILE')
    if requested and '_db_revision' in frame.attrs and frame.attrs['_db_revision'] != _db_revision():
        st.session_state['_inv_pending_query'] = draft
        st.rerun(scope='app')
    if requested and inventory_path and os.path.exists(inventory_path):
        current_stat = os.stat(inventory_path)
        if (current_stat.st_mtime_ns, current_stat.st_size) != file_version:
            st.session_state['_inv_pending_query'] = draft
            st.rerun(scope='app')
    if requested:
        if not draft['models'] and not draft['owners'] and not draft['serial']:
            st.warning('모델명·보유처·일련번호 중 하나 이상을 입력하세요. 이전 결과는 유지됩니다.')
        else:
            st.session_state['_last_search_conditions'] = draft
            st.session_state['_inv_payload_key'] = None
            st.session_state['_recovery_fresh'] = False
            for field, param in qp.items():
                if draft[field]:
                    st.query_params[param] = draft[field]
                elif param in st.query_params:
                    del st.query_params[param]
    last = st.session_state.get('_last_search_conditions')
    if last is not None:
        normalized_last = {f: list(last.get(f) or []) for f in suffixes}
        normalized_last['serial'] = str(last.get('serial') or '')
        if draft != normalized_last:
            st.caption('조건이 변경됐습니다. 아래 결과는 이전 조회 기준이며, 조회하면 적용됩니다.')
    asset_version=_inv_asset_version()
    st.session_state.pop('_restore_last_result', None)
    if last is not None:
        # A restored browser payload is untrusted data: keep only known filter types.
        valid = all(isinstance(last.get(f, []), list) and all(isinstance(v, str) for v in last.get(f, []))
                    for f in suffixes) and isinstance(last.get('serial', ''), str)
        if not valid:
            st.warning('저장된 검색조건을 복원하지 못했습니다. 다시 조회해주세요.')
            return
        signature = hashlib.sha256(json.dumps([file_version, frame.attrs.get('_db_revision'), last], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if st.session_state.get('_inv_payload_key') != signature:
            matched, reference = _inv_filter(frame, last, cols)
            st.session_state['_inv_payload'] = _inv_payload(matched, reference, cols, last, signature, tile_url)
            st.session_state['_inv_payload_key'] = signature
        _inv_results_component(asset_version)(key='inventory_results_'+asset_version, data=st.session_state['_inv_payload'])
    else:
        _inv_results_component(asset_version)(key='inventory_results_'+asset_version, data={'version':'empty', 'records':[], 'empty':True})
    user = escape(str(st.session_state.get('username', '')))
    st.markdown('<div class="inv-footer"><span>DB 캐시 사용 · 화면 버전 '+asset_version[:8]+'</span><span>'+user+'</span></div>', unsafe_allow_html=True)


_INV_FILTER_CSS = """<style>
.stApp{background:#f4f7f3!important;background-image:none!important;color:#294a3c!important}
header[data-testid="stHeader"]{background:#f4f7f3!important}
.stApp :is(.stMarkdown,.stText,p,span,label,h1,h2,h3,h4,h5,h6,li){color:#294a3c!important}
.stApp .block-container{max-width:820px!important;padding-top:3.5rem!important;padding-bottom:1.4rem!important}
.stApp section[data-testid="stSidebar"]{background:#edf3ed!important;border-color:#cfdacf!important}
div[data-baseweb="select"]>div,div[data-baseweb="base-input"]>input,div[data-testid="stTextInput"] input{background:#fff!important;color:#294a3c!important;border:1px solid #cbd7ca!important;border-radius:6px!important}
div[data-baseweb="select"] input{color:#294a3c!important;-webkit-text-fill-color:#294a3c!important}
div[data-baseweb="select"]>div>div>div{color:#5d7467!important}
input::placeholder,textarea::placeholder{color:#738579!important;opacity:1!important}
div[data-baseweb="popover"]>div,div[data-baseweb="popover"]>div>div,div[data-baseweb="popover"] ul,ul[role="listbox"],div[role="listbox"]{background:#fff!important;border-color:#cbd7ca!important}
div[data-baseweb="popover"] :is(div,span,li),div[role="listbox"] :is(span,div){color:#294a3c!important}
li[role="option"]{background:#fff!important;color:#294a3c!important}
li[role="option"]:hover,li[role="option"][aria-selected="true"]{background:#e7eee3!important;color:#294a3c!important}
.stApp span[data-baseweb="tag"]{background:#e6eddf!important;color:#294a3c!important;border:1px solid #c6d2bf!important}
.stApp div.stButton>button,.stApp div[data-testid="stFormSubmitButton"]>button{background:#edf2e9!important;color:#365142!important;border:1px solid #ccd6c8!important;box-shadow:none!important}
.stApp [data-testid="stFileUploadDropzone"]{background:#edf2e9!important;border:1px dashed #bccbb9!important}
.stApp [data-testid="stFileUploadDropzone"] *{color:#365142!important}
.stApp [data-testid="stFileUploadDropzone"] svg{fill:#365142!important}
.stApp hr{background:#cbd7ca!important;height:1px!important}
.stApp [data-testid="stExpander"]{border:0!important;border-radius:0!important;background:transparent!important}
.stApp [data-testid="stExpander"] summary{padding:4px 0!important;min-height:36px!important}
.stApp [data-testid="stExpander"] summary p{font-size:13px!important}
.inv-brand{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:8px 0 13px;border-bottom:1px solid #cbd7ca;margin-bottom:2px;font-family:Arial,"Malgun Gothic",sans-serif;font-size:18px}
.inv-file-heading{min-width:0;flex:1;display:grid;gap:3px}
.stApp .inv-file-label{font-size:11px!important;color:#718575!important}
.stApp .inv-file-name{display:block;color:#294a3c!important;font-size:16px;font-weight:500;line-height:1.45;overflow-wrap:anywhere;word-break:break-word}
.stApp section[data-testid="stSidebar"] strong{color:#294a3c!important}
.stApp .inv-brand #inv-connection-badge{font-size:12px!important;color:#287d53!important;white-space:nowrap}
.stApp section[data-testid="stSidebar"] [data-testid="stRadio"]{margin-top:0!important}
.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label{border-radius:7px;padding:7px 8px;margin:2px 0}
.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:#e1ead8!important;border-left:3px solid #998347}
.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked)>div:first-child{background:#998347!important}
.stApp section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked)>div:first-child>div{background:#f8faf5!important}
.stApp section[data-testid="stSidebar"] hr{margin:12px 0!important}
.stApp section[data-testid="stSidebar"] [data-testid="stFileUploader"] :is(div,section){background:#edf3ed!important}
.stApp section[data-testid="stSidebar"] [data-testid="stFileUploader"] button{background:#f8faf5!important;color:#365142!important;border:1px solid #bccbb9!important;box-shadow:none!important}
.stApp section[data-testid="stSidebar"] [data-testid="stFileUploader"] button :is(p,span){color:#365142!important}
.stApp section[data-testid="stSidebar"] [data-testid="stAlert"]{background:#e4eedf!important;border:1px solid #c9d9c3!important}
.stApp [data-testid="stExpanderDetails"]{background:#f4f7f3!important;color:#294a3c!important}
.stApp div[data-testid="stForm"]{background:#fbfcf9!important;border:1px solid #cbd7ca!important;box-shadow:none!important;border-radius:12px!important;padding:20px!important}
.stApp .title-text{font-size:25px!important;font-weight:500!important;color:#294a3c!important;letter-spacing:0!important;margin:8px 0!important}
.stApp .subtitle-text{font-size:13px!important;color:#6b7e6e!important;margin-bottom:18px!important}
.st-key-inv_login_shell{max-width:420px!important;margin:20px auto!important}
.stApp .logo-container img{max-width:130px!important}
.stApp div[data-testid="stFormSubmitButton"]>button[data-testid]{background:#8d7837!important;border:1px solid #8d7837!important;border-radius:7px!important;box-shadow:none!important}
.stApp [data-testid="stFormSubmitButton"]>button p{color:#fff!important;font-weight:400!important}
.stApp .inv-auth-wait{background:#fbfcf9!important;border:1px solid #cbd7ca!important;box-shadow:0 4px 18px #294a3c12!important;padding:24px!important;width:min(360px,90vw)!important}
.stApp .inv-auth-wait h3{font-size:18px!important;color:#826a2c!important}
.inv-footer{border-top:1px solid #cbd7ca;padding-top:10px;margin-top:16px;display:flex;justify-content:space-between;gap:12px;font-size:11px}
.st-key-inv_file_meta [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center!important}
.st-key-inv_file_meta [data-testid="stColumn"]:first-child{min-width:0!important;flex:5 1 0!important;width:0!important}
.st-key-inv_file_meta [data-testid="stColumn"]:last-child{min-width:78px!important;flex:1 1 0!important;width:0!important}
.st-key-inv_refresh_sources div.stButton>button[data-testid]{background:transparent!important;border:0!important;padding:4px!important;min-height:32px!important;box-shadow:none!important}
.st-key-inv_refresh_sources button p{font-size:12px!important}
.st-key-inv_primary_filters [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:6px!important}
.st-key-inv_primary_filters [data-testid="stColumn"],.st-key-inv_primary_filters [data-testid="column"]{min-width:0!important;flex:1 1 0!important;width:0!important}
.st-key-inv_primary_filters [data-testid="stColumn"]:first-child{flex-grow:1.5!important}
.st-key-inv_primary_filters [data-testid="stColumn"]:nth-child(2){flex-grow:.8!important}
.st-key-inv_primary_filters [data-testid="stColumn"]:last-child{flex-grow:1.3!important}
.st-key-inv_primary_filters label p{font-size:13px!important}
.st-key-inv_primary_filters [data-baseweb="select"]>div{padding-left:5px!important;padding-right:3px!important;min-height:40px!important}
.st-key-inv_primary_filters [data-baseweb="tag"]{max-width:100%!important;font-size:12px!important}
.st-key-inv_primary_filters [data-baseweb="tag"] span[title]{font-size:12px!important}
.st-key-inv_primary_filters [aria-label="Clear all"]{display:none!important}
.st-key-inv_query_actions [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:8px!important}
.st-key-inv_query_actions [data-testid="stColumn"]{min-width:0!important;flex:3 1 0!important;width:0!important}
.st-key-inv_query_actions [data-testid="stColumn"]:last-child{flex-grow:1!important}
.st-key-inventory_reset_filters div.stButton>button[data-testid]{background:transparent!important;color:#506b5b!important;border:0!important;font-size:12px!important;min-height:40px!important;padding:4px!important;box-shadow:none!important}
.st-key-inventory_reset_filters button p{font-size:12px!important}
.st-key-inventory_search_button div.stButton>button[data-testid]{background:#8d7837!important;color:#fff!important;border:1px solid #8d7837!important;min-height:40px!important;padding:6px!important;box-shadow:none!important}
.st-key-inventory_search_button div.stButton>button[data-testid] p{color:#fff!important;font-weight:400!important;font-size:14px!important}
.st-key-inventory_search_button div.stButton>button[data-testid]:disabled{background:#b6aa81!important;border-color:#b6aa81!important;opacity:1!important}
#inventory-connection-status{background:#eef0df;color:#705e29;padding:9px;border-radius:6px;font-size:13px}
@media(max-width:640px){
 .st-key-inv_primary_filters [data-testid="stHorizontalBlock"]{flex-direction:column!important;gap:2px!important;align-items:stretch!important}
 .st-key-inv_primary_filters [data-testid="stColumn"]:nth-child(n),
 .st-key-inv_primary_filters [data-testid="column"]:nth-child(n){width:100%!important;min-width:0!important;flex:0 0 auto!important;padding:0!important}
 .st-key-inv_primary_filters [data-testid="stVerticalBlock"]{gap:0!important}
 .st-key-inv_primary_filters [data-testid="stElementContainer"]{margin:0!important;padding:0!important}
 .st-key-inv_primary_filters [data-testid="stWidgetLabel"]{margin-bottom:0!important;min-height:18px!important;padding:0!important}
 .st-key-inv_primary_filters [data-testid="stWidgetLabel"] p{margin:0!important;line-height:18px!important}
}

.stApp .st-key-inv_admin_shell h2{font-size:23px!important;font-weight:500!important;padding:6px 0!important}
.stApp .st-key-inv_admin_shell h3,.stApp .st-key-inv_admin_shell h4{font-size:17px!important;font-weight:500!important;padding:8px 0!important}
.stApp .st-key-inv_admin_shell [data-baseweb="tab-list"]{background:transparent!important;gap:0!important;border-bottom:1px solid #cbd7ca!important}
.stApp .st-key-inv_admin_shell [data-baseweb="tab"]{background:transparent!important;flex:1 1 0!important;padding:10px 6px!important;min-height:44px!important;white-space:nowrap!important}
.stApp .st-key-inv_admin_shell [data-baseweb="tab"][aria-selected="true"]{background:#e7eee1!important}
.stApp .st-key-inv_admin_shell [data-baseweb="tab-highlight"]{background:#8d7837!important}
.stApp .st-key-inv_admin_shell [data-baseweb="tab"] p{font-size:13px!important}
.stApp .st-key-inv_admin_shell [data-testid="stVerticalBlockBorderWrapper"]>div{border-color:#cbd7ca!important;border-radius:10px!important}
.stApp .st-key-inv_admin_shell [data-testid="stAlert"]{background:#edf2e7!important;border:1px solid #ccd8c7!important;border-radius:7px!important}
.stApp .st-key-inv_admin_shell [data-testid="stFileUploader"] button{background:#f8faf5!important;color:#365142!important;border:1px solid #bccbb9!important;box-shadow:none!important}
.stApp .st-key-inv_admin_shell [data-testid="stFileUploader"] button :is(p,span){color:#365142!important}
.stApp .st-key-inv_admin_shell [data-testid="stExpander"]{border-bottom:1px solid #cbd7ca!important;padding:4px 0!important}
@media(max-width:640px){.stApp .st-key-inv_admin_shell [data-testid="stHorizontalBlock"]{flex-direction:column!important;gap:8px!important}.stApp .st-key-inv_admin_shell [data-testid="stColumn"]{width:100%!important;min-width:0!important;flex:1 1 auto!important}.stApp .st-key-inv_admin_shell div[data-testid="stForm"]{padding:14px!important}}


.stApp .st-key-inv_admin_shell [data-testid="stExpander"]:is(:focus-within,:hover){border-color:#cbd7ca!important;outline:none!important;box-shadow:none!important}
/* Override every old uploader descendant rule, including its hover/focus state. */
.stApp [data-testid="stFileUploader"] :is(div,section,label,small){background-color:#edf3ed!important;background-image:none!important;color:#365142!important}
.stApp [data-testid="stFileUploader"] :is(p,span){background-color:transparent!important;color:#365142!important}
.stApp [data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"],
.stApp [data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"]:hover,
.stApp [data-testid="stFileUploader"] [data-testid="stFileUploadDropzone"]:focus-within{background-color:#edf3ed!important;border:1px dashed #aebfa9!important;border-radius:8px!important;padding:14px!important}
.stApp [data-testid="stFileUploader"] svg{fill:#62794f!important;color:#62794f!important}
.stApp [data-testid="stFileUploader"] button,
.stApp [data-testid="stFileUploader"] button:is(:hover,:focus,:active){background-color:#fbfcf8!important;color:#365142!important;border:1px solid #b9c9b3!important;box-shadow:none!important}
.stApp [data-testid="stFileUploader"] button :is(p,span){color:#365142!important;background:transparent!important}
.stApp .st-key-inv_admin_shell [data-testid="stExpander"] summary,
.stApp .st-key-inv_admin_shell [data-testid="stExpander"] summary:is(:hover,:focus,:focus-visible){background:#eaf0e5!important;border:1px solid #cbd7ca!important;outline:none!important;box-shadow:none!important;border-radius:7px!important;padding:10px!important}

</style>"""

_INV_RESULTS_JS = 'export default function({data, parentElement}) {\n    const root = parentElement.querySelector(\'.inventory-results-root\');\n    if (!root) return;\n    const storageKey = \'banchu-view-v3:\' + location.pathname;\n    let state = root._inventory;\n    if (!state) {\n        let saved = {};\n        try { saved = JSON.parse(sessionStorage.getItem(storageKey)) || {}; } catch (_) {}\n        state = root._inventory = {version:null, view:saved.view===\'list\'?\'list\':\'map\',\n            zone:\'\', page:0, sort:saved.sort||\'name\', selected:\'\', markers:new Map(), map:null,\n            epoch:0, repsOpen:false, detailPages:new Map(), data:null};\n    }\n    const persist = () => {\n        try {sessionStorage.setItem(storageKey,JSON.stringify({view:state.view,sort:state.sort}));}catch(_){}\n    };\n    if (state.version === data.version) return; // Filter edits / recovery never rebuild this map.\n    state.memos ??= new Map();\n    const previous = state.data;\n    state.version=data.version;state.data=data;state.epoch++;\n    if (previous && !data.empty && JSON.stringify(previous.conditions)!==JSON.stringify(data.conditions)) {\n        state.zone=\'\';state.page=0;state.selected=\'\';state.detailPages.clear();state.memos.clear();\n    }\n    if (data.empty) {\n        if(state.map)state.map.remove();state.map=null;state.markers.clear();\n        root.replaceChildren();const note=document.createElement(\'div\');note.className=\'iv-empty\';note.textContent=\'⌕  모델·보유처·일련번호 중 하나로 조회하세요\';root.append(note);return;\n    }\n    const records=data.records, stores=records.filter(r=>r.category===\'store\'), reps=records.filter(r=>r.category===\'sales\');\n    const direct=!!data.conditions.dae?.length;\n    if (direct) state.zone=\'\';\n    const validPoint=r=>Number.isFinite(r.lat)&&Number.isFinite(r.lon);\n    const fmt=n=>Number(n).toLocaleString(\'ko-KR\');\n    const escape=s=>String(s??\'\').replace(/[&<>"\']/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'}[c]));\n    const elem=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};\n    const button=(text,fn,cls=\'iv-button\')=>{const b=elem(\'button\',cls,text);b.type=\'button\';b.addEventListener(\'click\',event=>{event.stopPropagation();fn(event);});return b;};\n    const visibleStores=()=>stores.filter(r=>!state.zone||r.zone===state.zone);\n    // Keep the component shell and Leaflet map element stable on refreshed payloads.\n    if (!root.querySelector(\'.iv-shell\')) {\n        root.innerHTML=`<section class="iv-shell">\n          <header class="iv-heading"><div><span class="iv-muted">조회 결과</span><div class="iv-total"></div></div><span class="iv-time iv-muted"></span></header>\n          <div class="iv-conditions iv-muted"></div><div class="iv-counts iv-muted"></div>\n          <nav class="iv-tabs" aria-label="결과 보기"><button type="button" data-view="map">지도</button><button type="button" data-view="list">목록</button></nav>\n          <div class="iv-scope"></div>\n          <div class="iv-map-panel"><div class="iv-map-status iv-muted" role="status"></div><div class="iv-map" aria-label="재고 지도"></div><div class="iv-zone-buttons"></div><p class="iv-map-note iv-muted"></p></div>\n          <div class="iv-list-panel" hidden><div class="iv-list-controls"><span class="iv-range iv-muted"></span><label>정렬 <select class="iv-sort"><option value="name">보유처명</option><option value="qty">수량 많은 순</option><option value="date">출고일 빠른 순</option></select></label></div><div class="iv-list"></div><div class="iv-pager iv-list-pager"></div></div>\n          <section class="iv-sales" aria-label="영업사원 보유 재고"><div class="iv-sales-head"></div><div class="iv-sales-body" hidden></div></section>\n          <div class="iv-feedback" role="status" aria-live="polite"></div>\n        </section>`;\n    }\n    const q=s=>root.querySelector(s);\n    q(\'.iv-total\').textContent=fmt(data.matched)+\'대\';q(\'.iv-time\').textContent=data.created+\' 조회\';\n    q(\'.iv-counts\').textContent=`거래처 ${fmt(data.storeQty)}대 · 영업사원 ${fmt(data.salesQty)}대`+\n        (data.referenceQty?` · 권역 미지정 참고 ${fmt(data.referenceQty)}대 별도`:\'\');\n    q(\'.iv-conditions\').textContent=[...(data.conditions.models||[]),...(data.conditions.colors||[]),\n        ...(data.conditions.dae?.length?data.conditions.dae:[\'전체 권역\']),...(data.conditions.so||[]),\n        ...(data.conditions.owners||[]),data.conditions.serial?\'일련번호 포함: \'+data.conditions.serial:\'\'].filter(Boolean).join(\' · \');\n    let feedbackTimer;\n    function feedback(text){q(\'.iv-feedback\').textContent=text;root.querySelectorAll(\'.iv-local-feedback\').forEach(node=>node.textContent=text);clearTimeout(feedbackTimer);feedbackTimer=setTimeout(()=>{if(root.isConnected){q(\'.iv-feedback\').textContent=\'\';root.querySelectorAll(\'.iv-local-feedback\').forEach(node=>node.textContent=\'\');}},3500);}\n    function stockSummary(r){\n        const map=new Map();for(const item of r.items){const key=JSON.stringify(item.slice(0,5));const value=map.get(key);if(value)value.qty++;else map.set(key,{values:item.slice(0,5),qty:1});}return [...map.values()];\n    }\n    function dateParts(value){\n        const raw=String(value??\'\').trim();\n        const match=raw.match(/^(\\d{4})[-/.]?(\\d{2})[-/.]?(\\d{2})$/);\n        if(!match)return null;\n        const [,year,month,day]=match;\n        const date=new Date(Number(year),Number(month)-1,Number(day));\n        return date.getFullYear()===Number(year)&&date.getMonth()===Number(month)-1&&date.getDate()===Number(day)?[year,month+day]:null;\n    }\n    async function copy(text,silent=false){\n        try{await navigator.clipboard.writeText(text);if(!silent)feedback(\'복사되었습니다.\');return true;}\n        catch(_){const area=elem(\'textarea\');area.value=text;root.append(area);area.select();let ok=false;try{ok=document.execCommand(\'copy\');}catch(_){}area.remove();if(!ok)feedback(\'자동 복사가 제한돼 있습니다. 복사 권한을 확인해주세요.\');else if(!silent)feedback(\'복사되었습니다.\');return ok;}\n    }\n    async function shareText(text,copyArea){\n        // Invoke inside the real click, before any asynchronous work, so mobile\n        // browsers retain user activation. This is the OS share sheet, not an SDK.\n        copyArea.value=text;\n        if(window.isSecureContext&&typeof navigator.share===\'function\'){\n            try{\n                if(!navigator.canShare||navigator.canShare({text})){\n                    feedback(\'공유창에서 카카오톡을 선택하세요.\');\n                    await navigator.share({text});\n                    feedback(\'공유창 처리가 완료됐습니다.\');return;\n                }\n            }catch(error){if(error.name===\'AbortError\'){feedback(\'공유를 취소했습니다.\');return;}}\n        }\n        const copied=await copy(text,true);copyArea.hidden=copied;\n        feedback(copied?\'이 환경에서는 공유창을 열 수 없어 문구를 복사했습니다. 카카오톡에 붙여넣으세요.\':\'이 환경에서는 공유창을 열 수 없습니다. 아래 문구를 길게 눌러 복사하세요.\');\n    }\n    function detail(r, popup=false, showActions=true){\n        const wrap=elem(\'div\',\'iv-store-detail\'),title=elem(\'div\',\'iv-detail-title\',r.name+(r.missing&&r.category===\'store\'?\' · 주소 미등록\':\'\'));wrap.append(title);\n        wrap.append(elem(\'div\',\'iv-address\',(r.category===\'store\'?\'📍 \':\'\')+r.address));\n        wrap.append(elem(\'div\',\'iv-address iv-phone\',\'☎ K노트 연락처 : \'+r.phone));\n        if(showActions){\n        const memo=elem(\'input\',\'iv-memo\');memo.placeholder=\'이동할 곳 · 이동예정입니다\';memo.setAttribute(\'aria-label\',\'이동 예정 장소\');memo.value=state.memos.get(r.id)||\'\';memo.addEventListener(\'input\',()=>state.memos.set(r.id,memo.value));\n        const summary=stockSummary(r), lines=[\'반추 재고요청드립니다\',\'\',`[${r.name}]`];\n        if(r.category===\'store\')lines.push(\'📍 \'+r.address);else lines.push(\'영업사원 보유 재고\');\n        lines.push(\'☎ K노트 연락처 : \'+r.phone,\'\');\n        summary.forEach(v=>lines.push(v.values[0]+\' | \'+(v.values[1]||\'-\')+\' | \'+v.qty+\'대\'));\n        lines.push(\'\',\'사용가능할까요?\');\n        const copyArea=elem(\'textarea\',\'iv-copy-text\');copyArea.readOnly=true;copyArea.hidden=true;copyArea.setAttribute(\'aria-label\',\'복사 문구\');\n        const message=()=>lines.join(\'\\n\')+(memo.value.trim()?\'\\n\'+memo.value.trim()+\' 이동예정입니다.\':\'\');\n        const actions=elem(\'div\',\'iv-share-actions\');\n        actions.append(button(\'재고요청 복사\',()=>copy(message())),\n            button(\'공유(카카오톡)\',()=>shareText(message(),copyArea),\'iv-button iv-share-button\'));\n        const memoLabel=elem(\'label\',\'iv-memo-label\',\'이동 예정 장소\');\n        memoLabel.append(memo);\n        actions.lastChild.title=\'휴대폰 공유창에서 카카오톡을 선택하세요.\';\n        const copyStatus=elem(\'div\',\'iv-local-feedback\');copyStatus.setAttribute(\'role\',\'status\');\n        wrap.append(memoLabel,actions,copyStatus,copyArea);\n        }\n        const table=elem(\'table\',\'iv-stock-table \'+(popup?\'iv-popup-table\':\'iv-unit-table\')),thead=elem(\'thead\'),tr=elem(\'tr\');\n        (popup?[\'모델\',\'색상\',\'상태\',\'출고일\',\'수량\']:[\'모델\',\'색상\',\'일련번호\',\'유형\',\'상태\',\'출고일\',\'수량\']).forEach(v=>tr.append(elem(\'th\',\'\',v)));thead.append(tr);table.append(thead);\n        const displayed=r.items.map(item=>({values:item.slice(0,5),serial:item[5]||\'미등록\',qty:1}));\n        if(popup){\n            // Size columns from the longest visible text, including header labels.\n            // Keep one shared column layout across stock pages in this popup.\n            const context=document.createElement(\'canvas\').getContext(\'2d\');\n            const labels=[\'모델\',\'색상\',\'상태\',\'출고일\',\'수량\'];\n            const widths=labels.map(label=>{if(context)context.font=\'600 11px Arial, "Malgun Gothic", sans-serif\';return (context?context.measureText(label).width:label.length*11)+10;});\n            if(context)context.font=\'11px Arial, "Malgun Gothic", sans-serif\';\n            for(const item of r.items){\n                const parts=dateParts(item[4]);const date=parts?parts[0]+\'-\'+parts[1].slice(0,2)+\'-\'+parts[1].slice(2):String(item[4]||\'-\');\n                [item[0],item[1],item[3],date,\'1\'].forEach((value,index)=>{const text=String(value||\'-\');widths[index]=Math.max(widths[index],(context?context.measureText(text).width:text.length*11)+10);});\n            }\n            const total=widths.reduce((sum,width)=>sum+width,0),cols=elem(\'colgroup\');\n            widths.forEach(width=>{const col=elem(\'col\');col.style.width=(width/total*100)+\'%\';cols.append(col);});\n            table.prepend(cols);table.style.minWidth=Math.ceil(total)+\'px\';\n        }\n\n        const body=elem(\'tbody\');const perPage=popup?8:15;const pageKey=r.id+(popup?\':popup\':\':panel\');let page=state.detailPages.get(pageKey)||0;\n        page=Math.min(page,Math.max(0,Math.ceil(displayed.length/perPage)-1));\n        displayed.slice(page*perPage,(page+1)*perPage).forEach(v=>{const row=elem(\'tr\');const values=popup?[v.values[0],v.values[1],v.values[3],v.values[4],v.qty]:[v.values[0],v.values[1],v.serial,...v.values.slice(2),v.qty];values.forEach((value,index)=>{\n            const cell=elem(\'td\');const isDate=index===(popup?3:5);const parts=isDate?dateParts(value):null;\n            if(parts){cell.className=\'iv-date\';cell.setAttribute(\'aria-label\',`${parts[0]}년 ${parts[1].slice(0,2)}월 ${parts[1].slice(2)}일`);cell.textContent=parts[0]+\'-\'+parts[1].slice(0,2)+\'-\'+parts[1].slice(2);}\n            else {cell.textContent=String(value||\'-\');if(isDate)cell.className=\'iv-date\';}\n            row.append(cell);\n        });body.append(row);});table.append(body);const tableScroll=elem(\'div\',\'iv-table-scroll\');tableScroll.append(table);wrap.append(tableScroll);\n        if(displayed.length>perPage){const drawPage=next=>{state.detailPages.set(pageKey,next);if(popup)state.markers.get(r.id)?.getPopup()?.setContent(()=>detail(r,true));else wrap.replaceWith(detail(r,false,showActions));};const nav=elem(\'div\',\'iv-pager\');nav.append(button(\'이전\',()=>drawPage(Math.max(0,page-1))),elem(\'span\',\'iv-muted\',`${page+1}/${Math.ceil(displayed.length/perPage)}`),button(\'다음\',()=>drawPage(Math.min(Math.ceil(displayed.length/perPage)-1,page+1))));wrap.append(nav);}\n        return wrap;\n    }\n    function showDetail(r){\n        state.selected=r.id;\n        for(const [id,marker] of state.markers)marker.getElement?.()?.classList.toggle(\'iv-marker-selected\',id===r.id);\n        renderList();\n    }\n    function showRecordDialog(r){\n        showDetail(r);root.querySelector(\'.iv-stock-dialog\')?.remove();\n        const dialog=elem(\'dialog\',\'iv-stock-dialog\');dialog.setAttribute(\'aria-label\',\'재고 상세\');\n        dialog.append(button(\'닫기\',()=>dialog.close(),\'iv-text-button\'),detail(r));root.append(dialog);\n        dialog.addEventListener(\'close\',()=>dialog.remove(),{once:true});\n        if(dialog.showModal)dialog.showModal();else dialog.setAttribute(\'open\',\'\');\n    }\n    function renderSales(){\n        const head=q(\'.iv-sales-head\'),body=q(\'.iv-sales-body\');head.replaceChildren();body.replaceChildren();\n        head.append(button(`영업사원 보유 ${fmt(reps.reduce((n,r)=>n+r.qty,0))}대 · ${reps.length}명 ${state.repsOpen?\'접기\':\'펼치기\'}`,()=>{state.repsOpen=!state.repsOpen;renderSales();},\'iv-sales-toggle\'));\n        body.hidden=!state.repsOpen;\n        if(!state.repsOpen)return;\n        body.append(elem(\'p\',\'iv-muted\',\'위치 마커 제외 · 모델/색상/보유처/일련번호 조건 적용. 권역 미지정 참고 재고는 거래처 집계에 포함하지 않습니다.\'));\n        if(!reps.length)body.append(elem(\'p\',\'iv-muted\',\'해당 조건의 영업사원 재고가 없습니다.\'));\n        reps.forEach(r=>body.append(button(`${r.name} · ${fmt(r.qty)}대${r.reference?\' · 권역 미지정 참고\':\'\'}`,()=>showRecordDialog(r),\'iv-sales-row\')));\n    }\n    function renderList(revealSelected=false){\n        if(state.view!==\'list\')return;\n        const pageSize=6;\n        const rows=visibleStores().slice();\n        const earliest=r=>r.items.map(v=>v[4]).filter(Boolean).sort()[0]||\'9999\';\n        rows.sort(state.sort===\'qty\'?(a,b)=>b.qty-a.qty:state.sort===\'date\'?(a,b)=>earliest(a).localeCompare(earliest(b)):(a,b)=>a.name.localeCompare(b.name,\'ko\'));\n        if(revealSelected){const index=rows.findIndex(r=>r.id===state.selected);if(index>=0)state.page=Math.floor(index/pageSize);}\n        const pages=Math.max(1,Math.ceil(rows.length/pageSize));state.page=Math.min(state.page,pages-1);\n        q(\'.iv-range\').textContent=rows.length?`${fmt(state.page*pageSize+1)}–${fmt(Math.min(rows.length,(state.page+1)*pageSize))} / ${fmt(rows.length)}개 거래처`:\'해당 거래처 없음\';\n        const host=q(\'.iv-list\');host.replaceChildren();rows.slice(state.page*pageSize,(state.page+1)*pageSize).forEach(r=>{\n            const card=elem(\'article\',\'iv-store-card\');card.dataset.storeId=r.id;card.setAttribute(\'aria-label\',r.name+\' 재고 상세\');card.classList.toggle(\'iv-store-selected\',r.id===state.selected);\n            const toolbar=elem(\'div\',\'iv-card-toolbar\');toolbar.append(elem(\'span\',\'iv-muted\',`${r.zone} · ${fmt(r.qty)}대`),button(\'지도에서 보기\',()=>openStoreOnMap(r),\'iv-text-button\'));card.append(toolbar,detail(r,false,false));host.append(card);});\n        q(\'.iv-sort\').value=state.sort;q(\'.iv-sort\').onchange=event=>{state.sort=event.target.value;state.page=0;persist();renderList();};\n        const pager=q(\'.iv-list-pager\');pager.replaceChildren();const prev=button(\'이전\',()=>{state.page--;renderList();}),next=button(\'다음\',()=>{state.page++;renderList();});prev.disabled=state.page===0;next.disabled=state.page===pages-1;pager.append(prev,elem(\'span\',\'iv-muted\',`${state.page+1}/${pages}`),next);\n    }\n    function scope(){const host=q(\'.iv-scope\');host.replaceChildren();\n        if(state.zone)host.append(button(\'전체 권역 요약\',()=>{state.zone=\'\';state.page=0;scope();renderList();updateMap();},\'iv-text-button\'));}\n    function switchView(view,fromUser=false){state.view=view;persist();q(\'.iv-map-panel\').hidden=view!==\'map\';q(\'.iv-list-panel\').hidden=view!==\'list\';root.querySelectorAll(\'[data-view]\').forEach(b=>b.setAttribute(\'aria-pressed\',String(b.dataset.view===view)));\n        if(view===\'map\')return ensureMap();\n        renderList(fromUser);if(fromUser)requestAnimationFrame(()=>{if(state.view===\'list\')q(\'.iv-store-selected\')?.scrollIntoView({block:\'start\',behavior:\'auto\'});});\n    }\n    function popupOptions(){\n        return {maxWidth:Math.max(220,Math.min(300,state.map.getSize().x-28)),minWidth:Math.max(220,Math.min(260,state.map.getSize().x-28)),maxHeight:Math.max(180,state.map.getSize().y-70),autoPan:true,autoPanPadding:[8,8],keepInView:true};\n    }\n    function openMarkerDetail(r,marker){showDetail(r);marker.openPopup();}\n    async function openStoreOnMap(r){\n        showDetail(r);\n        if(!validPoint(r)){showRecordDialog(r);return;}\n        if(!direct){state.zone=r.zone;scope();}\n        const epoch=state.epoch;\n        await switchView(\'map\');\n        if(epoch!==state.epoch||state.view!==\'map\'||state.selected!==r.id||!root.isConnected)return;\n        const marker=state.markers.get(r.id);\n        if(!marker){feedback(\'지도 연결을 확인한 뒤 다시 선택하세요.\');return;}\n        state.map.setView([r.lat,r.lon],Math.max(state.map.getZoom(),15),{animate:false});\n        openMarkerDetail(r,marker);\n        q(\'.iv-map-panel\').scrollIntoView({block:\'start\',behavior:\'auto\'});\n    }\n    root.querySelectorAll(\'[data-view]\').forEach(b=>{b.onclick=()=>switchView(b.dataset.view,true);});\n    function leaflet(){\n        if(window.L)return Promise.resolve(window.L);\n        if(window.__banchuLeaflet)return window.__banchuLeaflet;\n        window.__banchuLeaflet=new Promise((resolve,reject)=>{const script=document.createElement(\'script\');script.src=\'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js\';script.onload=()=>resolve(window.L);script.onerror=()=>{window.__banchuLeaflet=null;reject(new Error(\'지도 라이브러리 연결 실패\'));};document.head.append(script);});return window.__banchuLeaflet;\n    }\n    function installBaseTiles(L){\n        const map=state.map,status=q(\'.iv-map-status\');\n        if(state.baseLayer)map.removeLayer(state.baseLayer);\n        if(state.primaryLayer)map.removeLayer(state.primaryLayer);\n        state.baseIsFallback=false;state.primaryLayer=null;\n        let baseLoaded=false,primaryLoaded=false,errors=0,timer;\n        const base=L.tileLayer(\'https://tile.openstreetmap.org/{z}/{x}/{y}.png\',{attribution:\'© OpenStreetMap contributors\',maxZoom:19,zIndex:0});\n        state.baseLayer=base;\n        const current=()=>root.isConnected&&state.map===map&&state.baseLayer===base;\n        const retry=()=>{if(current())status.replaceChildren(elem(\'span\',\'\',\'기본 배경지도를 불러오지 못했습니다. \'),button(\'배경지도 다시 시도\',()=>installBaseTiles(L)));};\n        base.on(\'tileload\',()=>{if(!current())return;baseLoaded=true;if(!primaryLoaded)status.textContent=\'기본 배경지도 표시 중\';});\n        base.on(\'tileerror\',()=>{if(++errors>=3&&!primaryLoaded)retry();});\n        base.on(\'remove\',()=>clearTimeout(timer));base.addTo(map);\n        if(!data.tileUrl)return;\n        const overlay=L.tileLayer(data.tileUrl,{attribution:\'VWorld\',maxZoom:19,zIndex:1,errorTileUrl:\'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=\'});\n        state.primaryLayer=overlay;let overlayErrors=0;\n        const keepBase=()=>{\n            if(!current()||state.primaryLayer!==overlay)return;\n            clearTimeout(timer);map.removeLayer(overlay);state.primaryLayer=null;state.baseIsFallback=true;\n            status.textContent=baseLoaded?\'VWorld 연결 실패 · 기본 배경지도 표시 중\':\'VWorld 연결 실패 · 기본 배경지도를 불러오는 중\';\n        };\n        overlay.on(\'tileload\',event=>{if(!current()||state.primaryLayer!==overlay)return;\n            if(event?.tile?.getAttribute(\'src\')===overlay.options?.errorTileUrl)return;\n            primaryLoaded=true;clearTimeout(timer);status.textContent=\'\';});\n        overlay.on(\'tileerror\',()=>{if(++overlayErrors>=3)keepBase();});\n        overlay.on(\'remove\',()=>clearTimeout(timer));overlay.addTo(map);\n        timer=setTimeout(()=>{if(!primaryLoaded)keepBase();},8000);\n    }\n    let mapSignature=\'\';\n    async function ensureMap(){\n        const epoch=state.epoch;const status=q(\'.iv-map-status\');\n        if(!stores.some(validPoint)){status.textContent=\'표시할 거래처 좌표가 없습니다. 목록과 영업사원 영역은 계속 이용할 수 있습니다.\';if(state.layer)state.layer.clearLayers();state.markers.clear();q(\'.iv-zone-buttons\').replaceChildren();q(\'.iv-map-note\').textContent=\'좌표가 없는 거래처도 목록에서 확인할 수 있습니다.\';return;}\n        try{\n            status.textContent=state.map?\'\':\'지도 준비 중…\';const L=await leaflet();if(epoch!==state.epoch||!root.isConnected)return;\n            if(!root.querySelector(\'link[data-leaflet]\')){const css=elem(\'link\');css.rel=\'stylesheet\';css.href=\'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css\';css.dataset.leaflet=\'1\';root.prepend(css);}\n            if(!state.map){\n                const node=q(\'.iv-map\');state.map=L.map(node,{scrollWheelZoom:!matchMedia(\'(pointer:coarse)\').matches,touchZoom:true,preferCanvas:true,zoomControl:false,attributionControl:true}).setView([37.5,127],9);\n                installBaseTiles(L);\n                state.layer=L.layerGroup().addTo(state.map);\n                state.map.on(\'click\',()=>{});\n                if(matchMedia(\'(pointer:coarse)\').matches){state.map.dragging.disable();\n                    node.addEventListener(\'touchstart\',event=>{if(event.touches.length>1){state.map.dragging.enable();}},{passive:true});\n                    node.addEventListener(\'touchend\',event=>{if(event.touches.length<2){state.map.dragging.disable();}},{passive:true});}\n            }\n            await new Promise(resolve=>requestAnimationFrame(resolve));\n            if(epoch!==state.epoch||!root.isConnected)return;\n            state.map.invalidateSize({pan:false});status.textContent=\'\';updateMap();\n        }catch(_){status.replaceChildren(elem(\'span\',\'\',\'지도를 불러오지 못했습니다. 목록을 이용하거나 다시 시도하세요. \'),button(\'지도 재시도\',()=>ensureMap()));}\n    }\n    function markerAppearance(items,name=\'\'){\n        const palette={"제트블랙":"#111111","블랙":"#000000","차콜":"#36454F","그래파이트":"#4A4E54","티타늄":"#9AA0A6","그레이":"#808080","실버쉐도우":"#8E8E93","실버블루":"#A7B8C8","화이트실버":"#E6E8EA","실버":"#C0C0C0","화이트":"#FFFFFF","크림":"#F2E3C2","베이지":"#E8D5B7","골드":"#FFD700","옐로우":"#F5D000","오렌지":"#FF7F00","레드":"#E01B24","버건디":"#800020","와인":"#800020","핑크":"#FFAFC5","브라운":"#7B4B2A","라벤더":"#B57EDC","바이올렛":"#8A5FD3","퍼플":"#7B2D8E","네이비":"#1F3864","아이스블루":"#BEE3F0","라이트블루":"#7EC8E3","블루":"#2058C8","민트":"#8FE3CF","그린":"#1F9E4F"};\n        const colors=[...new Set(items.map(item=>String(item[1]||\'\').trim().replace(/ /g,\'\')))];\n        const mixed=colors.length>1;\n        let hex=palette[colors[0]];\n        if(!hex){const key=Object.keys(palette).sort((a,b)=>b.length-a.length).find(k=>(colors[0]||\'\').includes(k));hex=palette[key]||\'#9E9E9E\';}\n        const office=String(name).includes(\'반추\');\n        if(office)hex=\'#e14444\';\n        const channels=hex.slice(1).match(/../g).map(v=>parseInt(v,16));\n        const light=(.299*channels[0]+.587*channels[1]+.114*channels[2])/255>.75;\n        return {hex,mixed:!office&&mixed,office,edge:light?\'#343a35\':\'#ffffff\',text:light?\'#213326\':\'#ffffff\',background:!office&&mixed?\'linear-gradient(135deg,red,orange,yellow,green,blue,purple)\':hex};\n    }\n    function updateMap(){\n        if(!state.map)return;\n        const signature=state.version+\'|\'+state.zone+\'|\'+direct;\n        if(mapSignature===signature)return;mapSignature=signature;\n        const L=window.L;state.layer.clearLayers();state.markers.clear();const bounds=[];\n        const host=q(\'.iv-zone-buttons\');host.replaceChildren();\n        if(!direct&&!state.zone){\n            const groups=new Map();stores.forEach(r=>{if(!groups.has(r.zone))groups.set(r.zone,[]);groups.get(r.zone).push(r);});\n            for(const [zone,group] of groups){\n                const qty=group.reduce((n,r)=>n+r.qty,0),valid=group.filter(validPoint);\n                const drill=()=>{state.zone=zone;state.page=0;scope();renderList();updateMap();};\n                host.append(button(`${zone} · ${fmt(qty)}대`,drill,\'iv-zone-button\'));\n                if(!valid.length)continue;\n                const median=a=>{a.sort((a,b)=>a-b);const n=a.length;return n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2;};\n                const point=[median(valid.map(r=>r.lat)),median(valid.map(r=>r.lon))];bounds.push(point);\n                const icon=L.divIcon({className:\'iv-zone-marker\',html:`<div><span>${escape(zone)}</span><strong>${fmt(qty)}대</strong></div>`,iconSize:[100,50],iconAnchor:[50,25]});\n                L.marker(point,{icon,title:zone+\' 권역 요약\'}).on(\'click\',drill).addTo(state.layer);\n            }\n            q(\'.iv-map-note\').textContent=\'권역별 요약 마커는 대표 위치입니다. 마커 또는 권역 버튼을 누르면 거래처가 표시됩니다. 영업사원은 마커에서 제외합니다.\';\n        }else{\n            for(const r of visibleStores().filter(validPoint)){\n                const point=[r.lat,r.lon];bounds.push(point);\n                const appearance=markerAppearance(r.items,r.name),uncertain=r.approx||r.missing;\n                const html=`<div class="iv-color-pin ${appearance.office?\'iv-office-pin\':\'\'}" style="background:${appearance.background};border:2px ${uncertain?\'dashed\':\'solid\'} ${uncertain?\'#e14444\':appearance.edge}">${appearance.office?\'★\':\'\'}</div>`;\n                const marker=L.marker(point,{icon:L.divIcon({className:\'iv-color-marker\'+(state.selected===r.id?\' iv-marker-selected\':\'\'),html,iconSize:[24,24],iconAnchor:[12,12]}),title:r.name});\n                marker.bindPopup(()=>detail(r,true),popupOptions());\n                marker.bindTooltip(escape(r.name),{direction:\'top\'});marker.on(\'click\',()=>openMarkerDetail(r,marker));marker.addTo(state.layer);state.markers.set(r.id,marker);\n            }\n            q(\'.iv-map-note\').textContent=\'개별 거래처 마커 · 빨간 점선은 주소 미등록 또는 추정 위치입니다. 상세는 마커를 누를 때 준비합니다.\';\n        }\n        if(bounds.length)state.map.fitBounds(bounds,{padding:[30,30],maxZoom:bounds.length===1?15:12,animate:false});\n    }\n    renderSales();scope();renderList();switchView(state.view);\n    const selected=records.find(r=>r.id===state.selected);if(selected)showDetail(selected);\n    // No Python callbacks for tabs, sorting, pages, sales expansion, or marker selection.\n    // Leave window scroll and focus untouched on query completion.\n    return ()=>queueMicrotask(()=>{if(!root.isConnected&&state.map){state.map.remove();state.map=null;}});\n}\n'
_INV_RESULTS_CSS = '.inventory-results-root{font-family:Arial,"Malgun Gothic",sans-serif;color:#294a3c;font-size:14px;line-height:1.5;--iv-bg:#f4f7f3;--iv-panel:#edf3e9;--iv-border:#cbd7ca;--iv-muted:#627968;--iv-gold:#826a2c}\n*{box-sizing:border-box}button,input,select,textarea{font:inherit}button{cursor:pointer}button:disabled{opacity:.45;cursor:default}[hidden]{display:none!important}\n.iv-shell{background:var(--iv-bg);padding:14px 0;overflow-wrap:anywhere}.iv-heading,.iv-sales-head,.iv-list-controls,.iv-scope,.iv-pager{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}\n.iv-total{font-size:26px;font-weight:600}.iv-muted{color:var(--iv-muted);font-size:12px}.iv-conditions,.iv-counts{margin-top:5px}.iv-time{font-variant-numeric:tabular-nums}\n.iv-sales{background:var(--iv-panel);border-left:3px solid var(--iv-gold);margin:12px 0;padding:9px 12px}.iv-sales-toggle{background:transparent;border:0;color:var(--iv-gold);padding:0;text-align:left;font-weight:600;min-height:32px}.iv-sales-row{display:block;width:100%;text-align:left;background:transparent;border:0;border-bottom:1px solid var(--iv-border);padding:9px 0;color:inherit}\n.iv-tabs{display:flex;margin:12px 0 4px;border-bottom:1px solid var(--iv-border)}.iv-tabs button{width:50%;background:transparent;border:0;border-bottom:2px solid transparent;color:var(--iv-muted);padding:10px}.iv-tabs button[aria-pressed=true]{border-color:var(--iv-gold);color:var(--iv-gold)}\n.iv-scope{font-size:12px;min-height:38px}.iv-text-button{background:transparent;border:0;color:var(--iv-gold);padding:7px 0}.iv-map{height:380px;background:#e5ede2;border-radius:8px;isolation:isolate}.iv-map-note{margin:8px 0}.iv-map-status:empty{display:none}.iv-zone-buttons{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.iv-zone-button{font-size:12px;padding:6px 9px;background:var(--iv-panel);color:inherit;border:1px solid var(--iv-border);border-radius:5px}\n.iv-zone-marker{background:#6f581b;color:#fff2c8;border:1px solid #d5bd75;border-radius:7px;text-align:center;padding:3px;box-shadow:0 2px 3px #0004}.iv-zone-marker span{display:block;font-size:11px}.iv-zone-marker strong{font-size:14px}\n.iv-list-controls{margin:9px 0}.iv-list-controls select{background:var(--iv-panel);color:inherit;border:1px solid var(--iv-border);padding:6px;border-radius:5px}.iv-list-controls label{font-size:12px}.iv-store-row{background:transparent;color:inherit;border:0;border-bottom:1px solid var(--iv-border);display:grid;grid-template-columns:minmax(0,1fr) auto;text-align:left;gap:3px 9px;width:100%;padding:11px 2px}.iv-store-row strong{font-size:13px;font-weight:500}.iv-store-row>.iv-muted{grid-column:1}.iv-qty{grid-column:2;grid-row:1 / 3;align-self:center;color:var(--iv-gold)}.iv-store-row[aria-pressed=true]{background:#e1ead9}.iv-pager{justify-content:center;margin:10px 0}\n.iv-button{background:#edf2e8;color:inherit;border:1px solid var(--iv-border);border-radius:6px;padding:7px 11px}.iv-detail{margin:12px 0;border-top:1px solid var(--iv-border);padding-top:9px}.iv-detail-title{font-size:14px;font-weight:600;margin:4px 0 7px}.iv-address{font-size:12px;font-weight:400;line-height:1.5}.iv-phone{border-bottom:1px solid var(--iv-border);padding-bottom:7px;margin-bottom:8px}.iv-memo,.iv-copy-text{width:100%;min-width:0;background:var(--iv-panel);color:inherit;border:1px solid var(--iv-border);padding:8px;border-radius:5px;margin-bottom:8px}.iv-copy-text{height:180px;margin-top:8px}.iv-stock-table{border-collapse:collapse;width:100%;font-size:11px;margin:8px 0;table-layout:fixed}.iv-stock-table th,.iv-stock-table td{border-bottom:1px solid var(--iv-border);text-align:left;padding:6px 3px;overflow-wrap:anywhere}.iv-stock-table th:first-child{width:26%}.iv-stock-table th:last-child{width:10%}.iv-unit{font-size:12px;border-bottom:1px solid var(--iv-border);padding:8px 0}.iv-feedback{color:#27724a;font-size:12px}.iv-feedback:empty{display:none}\n.leaflet-popup-content-wrapper{background:#fff;color:#222}.leaflet-popup-content .iv-store-detail{--iv-panel:#f4f7f4;--iv-border:#d1dad3;--iv-muted:#536258;color:#222;font-family:Arial,"Malgun Gothic",sans-serif}.leaflet-popup-content{max-width:calc(100vw - 70px)}.leaflet-popup-content .iv-button{background:#e8eee8;color:#222}.leaflet-container{font-family:Arial,"Malgun Gothic",sans-serif}\n@media(max-width:480px){.iv-map{height:330px}.iv-shell{padding:9px 0}.iv-heading{align-items:flex-end}.iv-stock-table{font-size:11px}.iv-time{font-size:11px}}\n@media(pointer:coarse){button{min-height:44px}input,select,textarea{font-size:16px}}\n\n.iv-empty{min-height:150px;display:flex;align-items:center;justify-content:center;text-align:center;color:#627968;font-size:13px;padding:20px 8px}\n.iv-share-actions{display:flex;flex-wrap:wrap;gap:7px}.iv-share-actions .iv-button{flex:1 1 125px;font-size:12px;min-height:40px}.iv-share-actions .iv-share-button{background:#edf2e8;color:inherit;border-color:var(--iv-border)}.iv-share-hint{margin:5px 0 8px;font-size:11px}\n\n.leaflet-popup-content .iv-share-actions .iv-button{flex:1 1 110px;white-space:nowrap;padding:6px 8px;min-height:36px}\n\n.iv-stock-heading{font-size:12px;font-weight:600;margin:8px 0 2px}.iv-share-tools{border-top:1px solid var(--iv-border);margin-top:10px;font-size:12px}.iv-share-tools>summary{cursor:pointer;min-height:36px;padding:9px 0;color:var(--iv-muted)}.iv-share-tools .iv-memo{margin-top:5px}.iv-share-tools:not([open])>:not(summary){display:none}\n.iv-stock-table td.iv-date{text-align:center;font-variant-numeric:tabular-nums}.iv-date>span{display:block;white-space:nowrap;overflow-wrap:normal;word-break:keep-all;line-height:1.4}\n\n.iv-color-marker{background:transparent;border:0}.iv-color-pin{width:24px;height:24px;border-radius:50%;box-shadow:0 1px 4px #0008}.iv-office-pin{border-radius:4px;color:white;text-align:center;line-height:20px;font-size:17px}.iv-marker-selected .iv-color-pin{outline:3px solid #294a3c;outline-offset:2px}.iv-zone-marker>div{min-height:42px;padding:2px;text-shadow:0 1px 2px #0009}\n\n.iv-share-actions{flex-wrap:nowrap;gap:6px;margin:5px 0}.iv-share-actions .iv-button,.leaflet-popup-content .iv-share-actions .iv-button{flex:1 1 0;min-width:0;white-space:nowrap;font-size:11px;padding:6px 5px;min-height:34px}\n.iv-map-tools{display:flex;align-items:center;justify-content:flex-end;gap:6px;margin:5px 0 8px;position:relative;z-index:1}.iv-map-tools>span{margin-right:auto}.iv-map-tools button{width:42px;height:38px;min-height:38px;background:#fbfcf8;color:#294a3c;border:1px solid #b8c8b1;border-radius:6px;font-size:22px;line-height:1}.iv-map-tools button:disabled{opacity:.4}\n\n.iv-table-scroll{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}.iv-stock-table{min-width:320px;table-layout:auto}.iv-stock-table th,.iv-stock-table td{white-space:nowrap;overflow-wrap:normal;word-break:normal}.iv-stock-table th:first-child{width:auto}.iv-stock-table th:last-child{width:auto}.iv-stock-table td.iv-date{white-space:nowrap;min-width:76px}.iv-unit-table{min-width:650px}.iv-unit-table th:nth-child(3),.iv-unit-table td:nth-child(3){min-width:105px}.leaflet-popup-content{max-width:calc(100vw - 48px)}\n\n.iv-local-feedback{font-size:11px;color:#27724a;margin:3px 0}.iv-local-feedback:empty{display:none}\n\n.leaflet-popup-content{margin:10px 12px!important}.leaflet-popup-content .iv-detail-title{padding-right:16px}\n\n.iv-memo-label{display:block;font-size:11px;line-height:1.4;margin:4px 0}.iv-memo-label .iv-memo{display:block;margin:4px 0 6px}\n\n.iv-scope:empty{display:none}\n\n.iv-stock-dialog{width:min(700px,94vw);max-height:85vh;overflow:auto;border:1px solid #cbd7ca;border-radius:10px;background:#fbfcf8;color:#294a3c;padding:14px}.iv-stock-dialog::backdrop{background:#0005}.iv-color-marker .iv-color-pin{box-sizing:border-box;width:24px;height:24px}\n\n.iv-store-card{border:1px solid var(--iv-border);border-radius:8px;padding:12px;margin:12px 0;background:#fbfcf8;scroll-margin-top:76px}.iv-store-selected{border-color:var(--iv-gold);box-shadow:inset 3px 0 var(--iv-gold)}.iv-card-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px}.iv-card-toolbar .iv-text-button{font-size:12px;padding:2px 0}.iv-store-card .iv-detail-title{margin-top:2px}.iv-list{overflow-anchor:none}\n\n.leaflet-popup-content .iv-popup-table{width:100%;min-width:0;table-layout:auto;margin:5px 0;font-size:11px}.leaflet-popup-content .iv-popup-table th,.leaflet-popup-content .iv-popup-table td{padding:3px 3px;min-width:0;text-align:left}.leaflet-popup-content .iv-popup-table th:first-child,.leaflet-popup-content .iv-popup-table th:last-child{width:auto}.leaflet-popup-content .iv-popup-table td.iv-date{min-width:0;text-align:left}.leaflet-popup-content .iv-popup-table th:last-child,.leaflet-popup-content .iv-popup-table td:last-child{text-align:right}.leaflet-popup-content .iv-detail-title{font-size:12px;margin:2px 0 4px}.leaflet-popup-content .iv-phone{padding-bottom:4px;margin-bottom:4px}.leaflet-popup-content .iv-memo{padding:5px 7px;margin-bottom:3px}.leaflet-popup-content .iv-memo-label{margin:2px 0}.leaflet-popup-content .iv-share-actions{margin:3px 0}.leaflet-popup-content .iv-pager{gap:6px;margin:5px 0}\n\n.leaflet-popup-content .iv-popup-table{table-layout:fixed}.leaflet-popup-content .iv-popup-table th,.leaflet-popup-content .iv-popup-table td{padding:3px 5px;text-align:left}.leaflet-popup-content .iv-popup-table th:nth-child(n+3),.leaflet-popup-content .iv-popup-table td:nth-child(n+3){text-align:center;font-variant-numeric:tabular-nums}\n'


# --- 대시보드 상태 변수 유지 ---
if 'filtered_data' not in st.session_state: st.session_state['filtered_data'] = None
if 'selected_idx' not in st.session_state: st.session_state['selected_idx'] = None
if 'clicked_store_name' not in st.session_state: st.session_state['clicked_store_name'] = None
if 'search_clicked' not in st.session_state: st.session_state['search_clicked'] = False

# 🚀 [추가] 100배 빠른 조회를 위한 검색 결과 캐싱 함수 (중복 계산 방지)
@st.cache_data(ttl="1h", show_spinner=False)
def get_cached_search_results(df, models, colors, owners, daes, sos, real_model, real_color, real_boyu):
    temp_df = df.copy()
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
    # 지역 단서가 없는 보유처를 임의의 서울 좌표에 표시하지 않습니다. 재고 목록에는 유지합니다.
    map_filtered_df = map_filtered_df.dropna(subset=['cached_lat', 'cached_lon'])
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
            <div class='inv-auth-wait' style='position: fixed; top: 40%; left: 50%; transform: translate(-50%, -50%); text-align: center; z-index: 9999; background-color: #122820; padding: 40px; border-radius: 15px; box-shadow: 0 0 20px rgba(212,175,55,0.1);'>
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
    with st.container(key="inv_login_shell"):
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
            st.markdown('<div class="logo-container" style="color:#826a2c;font-size:26px;">♧</div>', unsafe_allow_html=True)
        
        # ... (로고 및 타이틀 표시 로직 기존과 동일하게 유지) ...
        st.markdown('<div class="title-text">재고 조회 로그인</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle-text">등록된 계정으로 로그인하세요.</div>', unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            submit_button = st.form_submit_button("로그인", use_container_width=True)

            if submit_button:
                if username and password:
                    # 🔐 영문 "Running ..." 대신 한글 안내를 화면 중앙에 표시
                    _login_ph = st.empty()
                    _login_ph.markdown("""
                        <div class='inv-auth-wait' style='position: fixed; top: 40%; left: 50%; transform: translate(-50%, -50%); text-align: center; z-index: 9999; background-color: #122820; padding: 40px; border-radius: 15px; box-shadow: 0 0 20px rgba(212,175,55,0.1);'>
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
                        st.session_state['_explicit_logged_out'] = False
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
# Keep a permanent parent slot: one-time cookie components must not shift
# the dashboard's delta path on the first search after login.
with st.container(key="auth_cookie_write_slot"):
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
    st.button("🚪 로그아웃", key="inventory_logout_button", on_click=_begin_logout,
              use_container_width=True)

    menu = ["📊 대시보드"]
    # 관리자 권한(admin)일 때만 관리자 설정 메뉴가 보입니다.
    if st.session_state['role'] == 'admin':
        menu.append("⚙️ 관리자 설정")

    app_mode = st.radio("메뉴 이동", menu)

# ==============================================================================
# [3단계] 메인 화면 라우팅 (대시보드 / 관리자 설정)
# ==============================================================================
# 🚀 [수정] session_state에 저장하지 않고 매번 신선한 도화지만 깔아줍니다!
main_container = st.container(key="inventory_main")

with main_container:
    if app_mode == "⚙️ 관리자 설정":
        with st.container(key="inv_admin_shell"):
            # 🚀 [추가] 관리자 설정 모드일 때만 잔상 제거 CSS 작동
            st.markdown("""
                <style>
                /* 관리자 페이지에서만 stale(잔상) 요소를 숨김 */
                [data-stale="true"] {
                    display: none !important;
                }
                </style>
            """, unsafe_allow_html=True)
        
            st.markdown("## 관리자 설정")
            st.caption("거래처 주소록 · 계정 · 미매칭 · 작업 이력")
        
            admin_section = st.selectbox("관리할 항목", ["자료 갱신", "계정", "거래처", "미매칭", "작업 이력"], key="db_admin_section")
            if admin_section == "자료 갱신":
                _db_upload_panel()
    
            # ---------------------------------------------------------
            # 탭 1: 계정 관리
            # ---------------------------------------------------------
            if admin_section == "계정":
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
            if admin_section == "거래처":
                import numpy as np
            
                # 툴바 디자인 유지
                st.markdown("""
                    <style>
                    .st-key-inv_admin_shell [data-testid="stElementToolbar"] { transform:none!important; background:transparent!important; }
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
                st.info("판매여지도·거래처 원본 파일은 위 관리할 항목에서 ‘자료 갱신’을 선택해 업로드하세요.")

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
            if admin_section == "미매칭":
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
                                    return normalize_owner_match_key(v)

                                inside_map = {}   # 정규화된 애칭 -> (주소, x좌표, y좌표)
                                try:
                                    inside_df = load_sheet("stores_inside", ttl="10m")
                                    if inside_df is not None and not inside_df.empty:
                                        nick_c = _pick_col(inside_df, ['애칭', '거래처'], 1)
                                        addr_c = _pick_col(inside_df, ['주소'], 15)
                                        x_c    = _pick_col(inside_df, ['x좌표', 'X좌표', '경도'], 17)
                                        y_c    = _pick_col(inside_df, ['y좌표', 'Y좌표', '위도'], 18)
                                        if all([nick_c, addr_c, x_c, y_c]):
                                            for _, _r in inside_df.iterrows():
                                                _k = _norm_key(_r[nick_c])
                                                if _k and _k != 'nan':
                                                    inside_map[_k] = (
                                                        str(_r[addr_c]).strip(),
                                                        str(_r[x_c]).strip().lower(),
                                                        str(_r[y_c]).strip().lower(),
                                                    )
                                except Exception as _e:
                                    st.info(f"ℹ️ stores_inside 시트를 읽지 못했습니다. stores 기준으로만 판정합니다. ({_e})")
                            
                                boyu_col = next((c for c in raw_df.columns if '보유처' in str(c).replace('▼','').strip()), None)
                                code_col = next((c for c in raw_df.columns if any(k in str(c) for k in ['접점번호', '접점코드'])), None)
                            
                                if boyu_col:
                                    # "도매-" 또는 "반추"가 포함된 보유처는 목록에서 제외
                                    raw_filtered = raw_df[
                                        (~raw_df[boyu_col].astype(str).str.contains("반추", na=False)) & 
                                        (~raw_df[boyu_col].astype(str).str.startswith("도매-", na=False))
                                    ].copy()

                                    # 이름 매칭이므로 접점번호 유무와 무관하게 보유처별로 검사합니다.
                                    raw_unique = raw_filtered.drop_duplicates(subset=[boyu_col]).copy()
                                    if len(db_df.columns) > 6 and str(db_df.columns[6]).strip() == '반추관설':
                                        db_df = db_df.copy()
                                        db_df['_반추관설_키'] = db_df.iloc[:, 6].fillna('').map(_norm_key)
                                    else:
                                        db_df = db_df.iloc[0:0].copy()
                                        db_df['_반추관설_키'] = pd.Series(dtype=str)
                                        st.warning('stores G열 반추관설을 확인할 수 없습니다. inside 기준으로 검사합니다.')

                                    def _check_inside(row):
                                        """stores_inside 애칭 매칭 결과. 정상이면 'OK', 미등록이면 None"""
                                        info = inside_map.get(_norm_key(row[boyu_col]))
                                        if info is None:
                                            return None
                                        addr, x_val, y_val = info
                                        if addr.lower() in ('', 'nan', 'none', 'null', '<na>', '-', '미등록', '주소 미등록'):
                                            return "📍 stores_inside에 애칭은 있으나 주소(P열)가 비어 있습니다."
                                        x_num = pd.to_numeric(x_val, errors='coerce')
                                        y_num = pd.to_numeric(y_val, errors='coerce')
                                        if not (pd.notna(x_num) and pd.notna(y_num)
                                                and -180 <= x_num <= 180 and -90 <= y_num <= 90
                                                and x_num != 0 and y_num != 0):
                                            return "🌐 stores_inside에 주소는 있으나 좌표(R/S열)가 비어 있거나 올바르지 않습니다."
                                        return "OK"

                                    def get_unmatch_reason(row):
                                        # 1순위: inside의 거래처 애칭.
                                        inside_result = _check_inside(row)
                                        if inside_result == "OK":
                                            return None
                                        # 2순위: stores G열 반추관설과 재고 보유처 이름.
                                        owner_key = _norm_key(row[boyu_col])
                                        if owner_key in ('', 'nan', 'none', 'null', '<na>', '-'):
                                            return "❌ 재고표의 보유처 이름이 비어 있습니다."
                                        match = db_df[db_df['_반추관설_키'] == owner_key]
                                        if match.empty:
                                            return inside_result or "❌ inside 애칭과 stores 반추관설 어디에도 이름이 없습니다."
                                        m_row = match.iloc[-1]
                                        addr = str(m_row.get('사업장주소', '')).strip()
                                        x_num = pd.to_numeric(m_row.get('x좌표'), errors='coerce')
                                        y_num = pd.to_numeric(m_row.get('y좌표'), errors='coerce')
                                        if addr.lower() in ('', 'nan', 'none', 'null', '<na>', '-', '미등록', '주소 미등록'):
                                            return "📍 inside와 stores 반추관설에서 사용할 주소를 찾지 못했습니다."
                                        if not (pd.notna(x_num) and pd.notna(y_num)
                                                and -180 <= x_num <= 180 and -90 <= y_num <= 90
                                                and x_num != 0 and y_num != 0):
                                            return "🌐 inside와 stores 반추관설에 사용할 좌표(위경도)가 없습니다."
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
                                else: st.error("엑셀 파일에서 보유처 컬럼을 식별할 수 없습니다.")
                            except Exception as e: st.error(f"데이터 분석 중 오류 발생: {e}")
                    else: 
                        st.warning("📂 먼저 메인 화면에서 재고 엑셀 파일을 업로드해주세요.")
                else:
                    st.info("👆 위 버튼을 눌러 최신 DB 데이터를 기준으로 미매칭 목록을 조회하세요.")

            # ---------------------------------------------------------
            # 탭 4: 시스템 변경 이력 (Audit Log)
            # ---------------------------------------------------------
            if admin_section == "작업 이력":
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
            "버건디":     "#800020",  # 와인색
            "와인":       "#800020",
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

        def is_address_missing(address, owner=""):
            # 반추 사무실은 지도에 고정 주소를 사용하는 기존 규칙을 유지합니다.
            if "반추" in str(owner):
                return False
            if pd.isna(address):
                return True
            return str(address).strip().casefold() in {"", "nan", "none", "null", "<na>", "-", "미등록", "주소 미등록"}

        @st.cache_data(ttl="12h", show_spinner=False)
        def load_data_optimized(file, file_version=None, db_revision=None):
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
            boyu_col = (df.columns[13] if len(df.columns) > 13 and '보유처' in str(df.columns[13])
                        else next((col for col in df.columns if '보유처' in str(col)), None))
            if boyu_col:
                df[boyu_col] = df[boyu_col].astype(str).str.strip()
                df.loc[df[boyu_col].str.contains("반추", na=False), boyu_col] = "반추정보통신"
                # 애칭 대조용 키 (공백 제거 + 소문자)
                df['_보유처_키'] = df[boyu_col].map(normalize_owner_match_key)

            # 헤더 이름으로 먼저 찾고, 못 찾으면 지정한 열 위치로 대체
            def _pick_col(_df, keywords, fallback_idx):
                for c in _df.columns:
                    if any(k in str(c) for k in keywords):
                        return c
                if len(_df.columns) > fallback_idx:
                    return _df.columns[fallback_idx]
                return None

            df['주소출처'] = "미등록"   # 미등록 / 반추관설매칭 / 애칭매칭

            # =========================================================
            # 3. stores_inside를 먼저 읽고, stores는 미매칭 보완용으로 읽습니다.
            # stores의 다른 메타데이터도 유지하되 최종 주소·좌표는 아래에서 inside를 우선합니다.
            # =========================================================
            try:
                inside_df = load_sheet("stores_inside", ttl="10m")
            except Exception as e:
                inside_df = None
                print(f"[stores_inside 로드 실패] {e}")

            try:
                addr_df = load_sheet("stores", ttl="10m")
            except Exception as e:
                addr_df = None
                print(f"[stores 로드 실패] {e}")

            # stores는 G열 반추관설과 재고표 N열 보유처의 이름으로만 매칭합니다.
            # 아래 inside 우선 선택에서 필요한 경우에만 이 주소·좌표가 사용됩니다.
            # 원본 접점코드는 재고 데이터로 보존하며 조회 키로 사용하지 않습니다.
            if boyu_col and addr_df is not None and not addr_df.empty:
                if len(addr_df.columns) > 6 and str(addr_df.columns[6]).strip() == '반추관설':
                    addr_df = addr_df.copy()
                    addr_df['_stores_name_key'] = addr_df.iloc[:, 6].map(normalize_owner_match_key)
                    addr_df = addr_df[~addr_df['_stores_name_key'].isin(
                        ['', 'nan', 'none', 'null', '<na>', '-']
                    )].drop_duplicates('_stores_name_key', keep='last')
                    # 재고표에 이미 있는 접점코드 등의 열은 중복 병합하지 않습니다.
                    payload = addr_df.drop(columns=[
                        c for c in addr_df.columns if c in df.columns and c != '_stores_name_key'
                    ])
                    df = pd.merge(df, payload, left_on='_보유처_키',
                                  right_on='_stores_name_key', how='left', validate='many_to_one')
                    df = df.drop(columns=['_stores_name_key'], errors='ignore')
                    if '사업장주소' in df.columns:
                        _ok = df['사업장주소'].notna() & ~df['사업장주소'].astype(str).str.strip().str.lower().isin(
                            ['', 'nan', 'none', 'null', '<na>', '-', '미등록', '주소 미등록']
                        )
                        df.loc[_ok, '주소출처'] = "반추관설매칭"
                else:
                    print('[stores] G열 반추관설을 확인할 수 없어 stores 이름 매칭을 건너뜁니다.')

            # 이후 로직이 참조하는 표준 컬럼이 없으면 빈 칸으로 생성
            for _c in ['사업장주소', 'x좌표', 'y좌표']:
                if _c not in df.columns:
                    df[_c] = pd.NA

            # =========================================================
            # 4. [최우선] stores_inside 시트 — 거래처 애칭 기준
            #    B열=애칭 / P열=주소 / R열=x좌표 / S열=y좌표
            # =========================================================
            # K노트 연락처: 주소 매칭 성공 여부와 별개로 모든 보유처에 연결합니다.
            df['K노트 연락처'] = "미확인"
            if boyu_col and inside_df is not None and not inside_df.empty:
                contact_nick_col = _pick_col(inside_df, ['애칭', '거래처'], 1)
                # N열은 헤더 이름과 무관하게 14번째 열입니다.
                if contact_nick_col is not None and len(inside_df.columns) >= 14:
                    contact_keys = inside_df[contact_nick_col].map(normalize_owner_match_key)
                    contact_phone_col = next((c for c in inside_df.columns if str(c).strip()=='전화번호'), None)
                    contact_values = (inside_df[contact_phone_col] if contact_phone_col is not None else pd.Series('', index=inside_df.index)).map(format_knote_contact)
                    contact_rows = pd.DataFrame({"key": contact_keys, "contact": contact_values})
                    contact_rows = contact_rows[
                        ~contact_rows['key'].isin(['', 'nan', 'none', '<na>'])
                        & contact_rows['contact'].ne('')
                    ].drop_duplicates('key', keep='last')
                    contact_map = dict(zip(contact_rows['key'], contact_rows['contact']))
                    df['K노트 연락처'] = df['_보유처_키'].map(contact_map).fillna('미등록')
                else:
                    print('[K노트 연락처] stores_inside의 애칭 열 또는 N열을 확인할 수 없습니다.')

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
                    ins['_ins_키'] = ins['_ins_애칭'].map(normalize_owner_match_key)
                    ins = ins[ins['_ins_키'] != ""]
                    ins = ins.drop_duplicates(subset=['_ins_키'], keep='last')

                    df = pd.merge(df, ins.drop(columns=['_ins_애칭']),
                                  left_on='_보유처_키', right_on='_ins_키', how='left')

                    # inside의 주소·좌표를 최우선으로 선택합니다.
                    # 서로 다른 매장의 주소와 좌표를 섞지 않도록 한 묶음으로 교체합니다.
                    def _valid_address(values):
                        return values.notna() & ~values.astype(str).str.strip().str.lower().isin(
                            ['', 'nan', 'none', 'null', '<na>', '-', '미등록', '주소 미등록']
                        )

                    def _valid_xy(xs, ys):
                        x_num = pd.to_numeric(xs, errors='coerce')
                        y_num = pd.to_numeric(ys, errors='coerce')
                        return (x_num.between(-180, 180) & y_num.between(-90, 90)
                                & x_num.ne(0) & y_num.ne(0))

                    inside_address_ok = _valid_address(df['_ins_주소'])
                    inside_complete = inside_address_ok & _valid_xy(df['_ins_x'], df['_ins_y'])
                    stores_complete = (_valid_address(df['사업장주소'])
                                       & _valid_xy(df['x좌표'], df['y좌표']))
                    # inside가 완전하면 무조건 우선. 불완전하면 정상 stores로 보완합니다.
                    # 양쪽 모두 불완전한 경우에도 inside의 유효한 주소는 보존합니다.
                    need = inside_address_ok

                    df.loc[need, '사업장주소'] = df.loc[need, '_ins_주소']
                    inside_x = pd.to_numeric(df['_ins_x'], errors='coerce')
                    inside_y = pd.to_numeric(df['_ins_y'], errors='coerce')
                    inside_xy_ok = _valid_xy(df['_ins_x'], df['_ins_y'])
                    # 문자열 좌표 열에도 안전하게 숫자 좌표를 대입할 수 있도록 통일합니다.
                    df['x좌표'] = pd.to_numeric(df['x좌표'], errors='coerce')
                    df['y좌표'] = pd.to_numeric(df['y좌표'], errors='coerce')
                    df.loc[need, 'x좌표'] = inside_x.where(inside_xy_ok).loc[need]
                    df.loc[need, 'y좌표'] = inside_y.where(inside_xy_ok).loc[need]
                    df.loc[need, '주소출처'] = "애칭매칭"

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

                # DB 주소의 시·구·동별 좌표를 지역 추정용으로만 집계합니다.
                _hint_rows = []
                if addr_df is not None and not addr_df.empty:
                    if all(column in addr_df.columns for column in ('사업장주소', 'x좌표', 'y좌표')):
                        _hint_rows.extend(addr_df[['사업장주소', 'x좌표', 'y좌표']].itertuples(index=False, name=None))
                if inside_df is not None and not inside_df.empty:
                    _addr = _pick_col(inside_df, ['주소'], 15)
                    _x = _pick_col(inside_df, ['x좌표', 'X좌표', '경도'], 17)
                    _y = _pick_col(inside_df, ['y좌표', 'Y좌표', '위도'], 18)
                    if all(column is not None for column in (_addr, _x, _y)):
                        _hint_rows.extend(inside_df[[_addr, _x, _y]].itertuples(index=False, name=None))
                _location_hints = build_store_location_hints(_hint_rows)

                def _calc_coord(row):
                    import math
                    boyu = str(row[boyu_col])
                    try:
                        lat, lon = float(row.get('y좌표')), float(row.get('x좌표'))
                    except (TypeError, ValueError):
                        lat = lon = float('nan')
                    if (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90
                            and -180 <= lon <= 180 and lat != 0 and lon != 0):
                        lat, lon = get_coordinate_smart_jitter(boyu, lat, lon)
                        return lat, lon, 'DB좌표', ''
                    if '반추' in boyu:
                        lat, lon = NEIGHBORHOOD_COORDS['반추정보통신']
                        return lat, lon, '사무실고정좌표', ''
                    lat, lon, label = infer_store_location(
                        boyu, _location_hints, NEIGHBORHOOD_COORDS, DISTRICT_CENTERS, REGION_CENTER_COORDS
                    )
                    if lat is None or lon is None:
                        return float('nan'), float('nan'), '추정불가', ''
                    lat, lon = get_coordinate_smart_jitter(boyu, lat, lon)
                    return lat, lon, '지역추정', label

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
                _uniq['위치표시방식'] = _res.apply(lambda c: c[2])
                _uniq['추정지역'] = _res.apply(lambda c: c[3])

                df['cached_lat'] = df['_좌표키'].map(dict(zip(_uniq['_좌표키'], _uniq['cached_lat'])))
                df['cached_lon'] = df['_좌표키'].map(dict(zip(_uniq['_좌표키'], _uniq['cached_lon'])))
                df['위치표시방식'] = df['_좌표키'].map(dict(zip(_uniq['_좌표키'], _uniq['위치표시방식'])))
                df['추정지역'] = df['_좌표키'].map(dict(zip(_uniq['_좌표키'], _uniq['추정지역'])))
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
                if os.path.exists(DATA_FILE + '.upload.json'): os.remove(DATA_FILE + '.upload.json')
                if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
                st.session_state.clear()
                st.rerun()

        if 'last_uploaded' not in st.session_state: 
            st.session_state['last_uploaded'] = None

        if uploaded_file:
            current_file_id = f"{uploaded_file.name}_{hashlib.sha256(uploaded_file.getbuffer()).hexdigest()}"
            if st.session_state['last_uploaded'] != current_file_id:
                try:
                    with open(DATA_FILE, "wb") as f: f.write(uploaded_file.getbuffer())
                    with open(META_FILE, "w", encoding="utf-8") as f: f.write(uploaded_file.name)
                    try:
                        _inv_record_upload(DATA_FILE, uploaded_file.name)
                    except OSError:
                        # The inventory remains saved. Header falls back to file save time.
                        print('[업로드 시각 기록 실패: 파일 저장 시각을 표시합니다]')

                    
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
                    df = load_data_optimized(DATA_FILE, (os.stat(DATA_FILE).st_mtime_ns, os.stat(DATA_FILE).st_size), _db_revision())
                    if df is not None: df.attrs['_db_revision'] = _db_revision()
            except Exception as e:
                st.error(f"데이터 로드 오류: {e}")

        if df is not None:
            file_stat = os.stat(DATA_FILE)
            _inv_dashboard(df, (file_stat.st_mtime_ns, file_stat.st_size), _inv_map_tile_url('https://api.vworld.kr/req/wmts/1.0.0/0580472E-D858-365E-968B-F1FCE560F381/Base/{z}/{y}/{x}.png'))
        else:
            _inv_source_header()
        render_recovery_bridge()
