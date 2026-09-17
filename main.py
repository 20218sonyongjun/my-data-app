import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz

# Streamlit 앱 기본 설정 (웹 브라우저 탭 이름과 레이아웃 설정)
st.set_page_config(page_title="어제 박스오피스", page_icon="🎬", layout="centered")

# @st.cache_data 데코레이터를 쓰면, 한 번 불러온 데이터를 ttl(초 단위, 3600초=1시간) 동안 기억합니다.
# 같은 날짜를 또 조회해도 1시간 안에는 API를 다시 부르지 않아 빠릅니다.
@st.cache_data(ttl=3600, show_spinner="박스오피스 데이터를 불러오는 중입니다...")
def fetch_boxoffice_data(target_date):
    """KOBIS API를 호출하여 박스오피스 데이터를 가져오는 함수"""
    
    # 1. 시크릿(비밀 금고)에서 KOBIS_KEY를 가져옵니다. 
    # 코드를 깃허브에 올려도 키가 노출되지 않게 해줍니다.
    api_key = st.secrets.get("KOBIS_KEY")
    if not api_key:
        return {"error": "API 키가 설정되지 않았습니다. Streamlit Cloud의 Secrets 설정을 확인해주세요."}

    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }
    
    # 2. API 서버에 요청을 보냅니다.
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # 인터넷 연결이나 서버에 문제가 있으면 여기서 오류를 발생시킵니다.
        data = response.json()
        
        # 3. KOBIS API 특성상 키가 틀려도 200 성공 코드가 오면서 faultInfo가 옵니다.
        if "faultInfo" in data:
            return {"error": f"API 인증에 실패했습니다. 키를 확인해주세요. ({data['faultInfo'].get('message', '')})"}
        
        return data

    except requests.exceptions.RequestException:
        # 네트워크 문제 등으로 요청이 실패했을 때의 처리
        return {"error": "네트워크 오류가 발생했습니다. KOBIS 서버 상태를 확인하거나 잠시 후 다시 시도해주세요."}

def get_yesterday_kst():
    """서버 시계와 상관없이 무조건 한국 시간(KST) 기준으로 '어제'를 계산합니다."""
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    yesterday = now_kst - timedelta(days=1)
    
    # API 요청용 여덟 자리 문자열 (예: 20231024)과, 
    # 화면 표시용 문자열을 함께 반환합니다.
    return yesterday.strftime("%Y%m%d"), yesterday.strftime("%Y년 %m월 %d일")

def main():
    st.title("🍿 어제의 박스오피스")
    
    # 어제 날짜 계산하기
    target_dt, display_date = get_yesterday_kst()
    st.subheader(f"📅 기준일: {display_date}")
    
    # 데이터 가져오기
    result = fetch_boxoffice_data(target_dt)
    
    # 에러가 발생했는지 먼저 확인합니다.
    if "error" in result:
        st.error(result["error"])
        st.info("💡 해결 방법: Streamlit Cloud 설정(Settings) -> Secrets 메뉴에 KOBIS_KEY가 올바르게 입력되었는지 확인하세요.")
        return
    
    # 정상적으로 응답이 왔지만, 영화 목록 데이터가 비어있는 경우
    boxoffice_list = result.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
    if not boxoffice_list:
        st.warning("이런! 해당 날짜의 박스오피스 결과가 없습니다.")
        st.info("💡 아직 영진위(KOBIS)에서 어제 데이터를 집계 중일 수 있습니다. 오후에 다시 확인해 보세요.")
        return

    # 목록 데이터를 판다스(Pandas) 데이터프레임(표 형식)으로 만듭니다.
    df = pd.DataFrame(boxoffice_list)
    
    # 숫자 계산과 정렬을 위해 문자열 형태의 숫자들을 정수형(int)으로 바꿔줍니다.
    numeric_columns = ['rank', 'audiCnt', 'audiAcc', 'scrnCnt']
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    # 순위(rank)를 기준으로 오름차순 정렬을 확실히 해줍니다.
    df = df.sort_values(by='rank')

    st.markdown("### 🏆 1위 영화")
    top_movie = df.iloc[0] # 정렬된 첫 번째 데이터가 1위
    
    # 화면을 3개의 세로 칸으로 나눕니다.
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="영화명", value=top_movie['movieNm'])
    with col2:
        # 숫자에 쉼표(,)를 넣어 천 단위마다 끊어 읽기 좋게 만듭니다.
        st.metric(label="일일 관객수", value=f"{top_movie['audiCnt']:,}명")
    with col3:
        st.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,}명")
        
    st.divider() # 구분선 긋기

    st.markdown("### 📊 관객수 TOP 5")
    # 일일 관객수(audiCnt) 기준으로 내림차순 정렬 후 위에서 5개를 뽑습니다.
    top5_df = df.sort_values(by='audiCnt', ascending=False).head(5)
    
    # Streamlit 기본 막대그래프를 그리기 위해, 영화 이름을 인덱스(기준)로 설정합니다.
    chart_data = top5_df.set_index('movieNm')[['audiCnt']]
    st.bar_chart(chart_data)
    
    st.divider()

    st.markdown("### 📋 전체 순위표")
    # 화면에 보여줄 열(column)만 선택하고, 보기 편하게 한글 이름으로 바꿉니다.
    display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
    display_df.columns = ['순위', '영화명', '개봉일', '관객수(명)', '누적관객(명)', '스크린수']
    
    # 표(Dataframe) 출력 (기본 인덱스 번호는 숨김 처리)
    st.dataframe(
        display_df, 
        hide_index=True,
        use_container_width=True # 화면 넓이에 맞게 꽉 채움
    )

# 이 파이썬 파일이 직접 실행될 때만 main() 함수를 실행하라는 의미입니다.
if __name__ == "__main__":
    main()
