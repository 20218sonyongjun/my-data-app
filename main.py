# 박스오피스 조회 — KOBIS 일별 박스오피스 API
import datetime

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# 앱의 기본 설정 (웹 브라우저 탭 이름과 아이콘 등)
st.set_page_config(page_title="박스오피스 조회", page_icon="🎬", layout="wide")

# 인증키는 비밀 금고(secrets)에서 불러온다 — 코드에 직접 쓰지 않는다
API_KEY = st.secrets["KOBIS_KEY"]
URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 한국 시간 기준으로 '어제' 날짜를 구한다 (선택 가능한 가장 늦은 날짜)
KST = datetime.timezone(datetime.timedelta(hours=9))
yesterday = datetime.datetime.now(KST).date() - datetime.timedelta(days=1)

st.title("🎬 박스오피스 순위")

# 달력 위젯을 띄워 사용자가 날짜를 고르게 한다 (기본값과 최댓값은 어제)
selected_date = st.date_input("📅 조회할 날짜를 선택하세요:", value=yesterday, max_value=yesterday)
target_dt = selected_date.strftime("%Y%m%d")


@st.cache_data(ttl=3600)  # 같은 날짜는 한 시간 동안 기억해 두고 API를 다시 부르지 않는다
def fetch_boxoffice(date_str):
    """KOBIS API에서 해당 날짜의 일별 박스오피스를 받아 온다."""
    params = {"key": API_KEY, "targetDt": date_str}
    res = requests.get(URL, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


try:
    data = fetch_boxoffice(target_dt)
except requests.RequestException:
    st.error("서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 잠시 뒤 새로고침해 주세요.")
    st.stop()

# 인증키가 틀리면 상태코드는 200이지만 faultInfo 상자가 온다
if "faultInfo" in data:
    st.error(f"API가 오류를 돌려주었습니다: {data['faultInfo'].get('message', '')}")
    st.info("비밀 금고(secrets)의 KOBIS_KEY 값이 올바른지 확인해 주세요.")
    st.stop()

movies = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

# 영화 목록이 비어서 오면 — 아직 집계 전인 날짜다
if not movies:
    st.warning("그날은 아직 집계 전입니다.")
    st.stop()

df = pd.DataFrame(movies)

# 숫자가 글자로 오므로 숫자로 바꿔야 정렬, 계산, 그래프에 쓸 수 있다
# rankInten(전일 대비 순위 증감)도 추가로 숫자로 바꾼다
for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]:
    df[col] = pd.to_numeric(df[col])

# [기능 추가] 누적관객이 100만 명을 넘으면 영화명 뒤에 트로피(🏆) 이모지 붙이기
df["movieNm"] = df.apply(
    lambda row: f"{row['movieNm']} 🏆" if row["audiAcc"] >= 1000000 else row["movieNm"], 
    axis=1
)

# [기능 추가] 전날 대비 순위 증감(rankInten)에 따라 화살표 붙이기
def format_rank_change(inten):
    if inten > 0:
        return f"▲ {inten}"
    elif inten < 0:
        return f"▼ {abs(inten)}"
    else:
        return "-"

df["순위변동"] = df["rankInten"].apply(format_rank_change)


# 1위 영화는 지표 카드 세 장으로 크게
top = df.sort_values("rank").iloc[0]
st.subheader(f"🥇 1위 — {top['movieNm']}")
c1, c2, c3 = st.columns(3)
c1.metric("해당일 관객수", f"{top['audiCnt']:,}명")
c2.metric("누적 관객수", f"{top['audiAcc']:,}명")
c3.metric("스크린수", f"{top['scrnCnt']:,}개")


# 전체 순위표
st.subheader("📋 순위표")
# 필요한 컬럼만 뽑고, 이름도 예쁘게 바꾼다
table = df.sort_values("rank")[["rank", "순위변동", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]]
table.columns = ["순위", "순위변동", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 화살표 기호에 따라 글자 색상을 바꾸는 스타일 함수
def color_change(val):
    if isinstance(val, str):
        if "▲" in val:
            return "color: red"
        elif "▼" in val:
            return "color: blue"
    return ""

# 판다스(Pandas) 버전에 따라 스타일을 적용하는 명령어가 다를 수 있어서 안전하게 처리합니다
if hasattr(table.style, "map"):
    styled_table = table.style.map(color_change, subset=["순위변동"])
else:
    styled_table = table.style.applymap(color_change, subset=["순위변동"])

# 색상이 입혀진 스타일 테이블을 화면에 그립니다
st.dataframe(styled_table, hide_index=True, use_container_width=True)


# 관객수 상위 5편은 막대그래프로
st.subheader("📊 관객수 상위 5편")
top5 = df.sort_values("audiCnt", ascending=False).head(5)
fig = px.bar(top5, x="movieNm", y="audiCnt", labels={"movieNm": "영화명", "audiCnt": "해당일 관객수"})
st.plotly_chart(fig, use_container_width=True)
